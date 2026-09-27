#!/usr/bin/env python3
import json
import os
import signal
import socket
import sys
import threading
import time
from datetime import datetime


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared_modules.mqtt import MqttClient
STATE_DIR = os.path.join(BASE_DIR, "state")
CONFIG_FILE = os.path.join(BASE_DIR, "configs", "config.json")

ACTION_FILE = os.path.join(STATE_DIR, "action")
LAST_COMMAND_FILE = os.path.join(STATE_DIR, "last_command")
LAST_RESULT_FILE = os.path.join(STATE_DIR, "last_result")
LAST_MESSAGE_FILE = os.path.join(STATE_DIR, "last_message")
LAST_UPDATED_FILE = os.path.join(STATE_DIR, "last_updated")
HISTORY_FILE = os.path.join(STATE_DIR, "history.json")
BOOT_ID_FILE = os.path.join(STATE_DIR, "boot_id")

stop_event = threading.Event()
mqtt_client = None


with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)


CLIENT_ID = CONFIG["client_ids"]["status"]
HOSTNAME = socket.gethostname()

TOPIC_POWER = CONFIG["topics"]["status_power"]
TOPIC_ACTION = CONFIG["topics"]["status_action"]
TOPIC_INFO_HOSTNAME = CONFIG["topics"]["status_hostname"]
TOPIC_INFO_UPTIME = CONFIG["topics"]["status_uptime"]
TOPIC_LAST_COMMAND = CONFIG["topics"]["status_last_command"]
TOPIC_LAST_RESULT = CONFIG["topics"]["status_last_result"]
TOPIC_LAST_MESSAGE = CONFIG["topics"]["status_last_message"]
TOPIC_LAST_UPDATED = CONFIG["topics"]["status_last_updated"]

TOPIC_HISTORY = CONFIG["topics"]["status_history"]
TOPIC_BOOT_ID = CONFIG["topics"]["status_boot_id"]
TOPIC_BOOT_TIME = CONFIG["topics"]["status_boot_time"]


PUBLISH_UPTIME_EVERY = CONFIG["timing"]["publish_uptime_every"]
HISTORY_MAX_ENTRIES = max(1, int(CONFIG["timing"]["history_max_entries"]))


def ensure_dirs() -> None:
    os.makedirs(STATE_DIR, exist_ok=True)


def read_text_file(path: str, default: str = "") -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            value = f.read().strip()
            return value if value else default
    except FileNotFoundError:
        return default
    except Exception:
        return default


def write_text_file(path: str, value: str) -> None:
    ensure_dirs()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(value.strip() + "\n")
    os.replace(tmp, path)


def read_action() -> str:
    return read_text_file(ACTION_FILE, "idle")


def write_action(value: str) -> None:
    write_text_file(ACTION_FILE, value)


def get_uptime_seconds() -> int:
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as f:
            return int(float(f.read().split()[0]))
    except Exception:
        return -1


def get_current_boot_id() -> str:
    return read_text_file("/proc/sys/kernel/random/boot_id", "")


def get_boot_time_epoch() -> float | None:
    uptime = get_uptime_seconds()
    if uptime < 0:
        return None
    return time.time() - uptime


def get_boot_time_iso() -> str:
    boot_epoch = get_boot_time_epoch()
    if boot_epoch is None:
        return ""
    return datetime.fromtimestamp(boot_epoch).isoformat(timespec="seconds")


def load_history() -> list[dict]:
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError, TypeError):
        return []

    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def save_history(entries: list[dict]) -> None:
    ensure_dirs()
    trimmed = entries[-HISTORY_MAX_ENTRIES:]
    tmp = HISTORY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, HISTORY_FILE)


def append_history_record(record: dict) -> None:
    history = load_history()
    history.append(record)
    save_history(history)


def clear_current_command_status() -> None:
    now = datetime.now().isoformat(timespec="seconds")
    write_text_file(LAST_COMMAND_FILE, "none")
    write_text_file(LAST_RESULT_FILE, "none")
    write_text_file(LAST_MESSAGE_FILE, "")
    write_text_file(LAST_UPDATED_FILE, now)


def is_new_machine_boot(current_boot_id: str) -> bool:
    if not current_boot_id:
        return False
    previous_boot_id = read_text_file(BOOT_ID_FILE, "")
    return bool(previous_boot_id and previous_boot_id != current_boot_id)


def append_boot_history(current_boot_id: str) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    append_history_record({
        "timestamp": now,
        "archived_at": now,
        "command": "boot",
        "result": "success",
        "message": "Device started a new Linux boot session",
        "source": "Remote enhed",
        "category": "availability",
        "event_type": "boot",
        "severity": "info",
        "boot_id": current_boot_id,
        "boot_time": get_boot_time_iso(),
    })


def initialize_boot_state() -> bool:
    current_boot_id = get_current_boot_id()
    new_boot = is_new_machine_boot(current_boot_id)

    if new_boot:
        clear_current_command_status()
        write_action("idle")
        append_boot_history(current_boot_id)

    if current_boot_id:
        write_text_file(BOOT_ID_FILE, current_boot_id)

    return new_boot


def publish(topic: str, payload: str, retain: bool = True, qos: int = 1) -> None:
    global mqtt_client
    if mqtt_client is None or not topic:
        return
    mqtt_client.publish(topic, payload, qos=qos, retain=retain)


def publish_history() -> None:
    if not TOPIC_HISTORY:
        return
    payload = json.dumps(load_history(), ensure_ascii=False, separators=(",", ":"))
    publish(TOPIC_HISTORY, payload, retain=True, qos=1)


def publish_command_status() -> None:
    publish(TOPIC_LAST_COMMAND, read_text_file(LAST_COMMAND_FILE, "none"), retain=True, qos=1)
    publish(TOPIC_LAST_RESULT, read_text_file(LAST_RESULT_FILE, "none"), retain=True, qos=1)
    publish(TOPIC_LAST_MESSAGE, read_text_file(LAST_MESSAGE_FILE, ""), retain=True, qos=1)
    publish(TOPIC_LAST_UPDATED, read_text_file(LAST_UPDATED_FILE, ""), retain=True, qos=1)


def on_connect() -> None:
    publish(TOPIC_POWER, "online", retain=True, qos=1)
    publish(TOPIC_ACTION, read_action(), retain=True, qos=1)
    publish(TOPIC_INFO_HOSTNAME, HOSTNAME, retain=True, qos=1)
    publish(TOPIC_INFO_UPTIME, str(get_uptime_seconds()), retain=True, qos=0)
    publish(TOPIC_BOOT_ID, get_current_boot_id(), retain=True, qos=1)
    publish(TOPIC_BOOT_TIME, get_boot_time_iso(), retain=True, qos=1)
    publish_command_status()
    publish_history()


def uptime_loop():
    while not stop_event.is_set():
        publish(TOPIC_POWER, "online", retain=True, qos=1)
        publish(TOPIC_INFO_UPTIME, str(get_uptime_seconds()), retain=True, qos=0)
        stop_event.wait(PUBLISH_UPTIME_EVERY)


def action_sync_loop():
    last_value = None
    while not stop_event.is_set():
        current = read_action()
        if current != last_value:
            publish(TOPIC_ACTION, current, retain=True, qos=1)
            last_value = current
        stop_event.wait(2)


def command_status_sync_loop():
    last_state = None
    while not stop_event.is_set():
        current_state = (
            read_text_file(LAST_COMMAND_FILE, "none"),
            read_text_file(LAST_RESULT_FILE, "none"),
            read_text_file(LAST_MESSAGE_FILE, ""),
            read_text_file(LAST_UPDATED_FILE, ""),
        )
        if current_state != last_state:
            publish(TOPIC_LAST_COMMAND, current_state[0], retain=True, qos=1)
            publish(TOPIC_LAST_RESULT, current_state[1], retain=True, qos=1)
            publish(TOPIC_LAST_MESSAGE, current_state[2], retain=True, qos=1)
            publish(TOPIC_LAST_UPDATED, current_state[3], retain=True, qos=1)
            last_state = current_state
        stop_event.wait(2)


def main() -> int:
    global mqtt_client

    ensure_dirs()

    if not os.path.exists(ACTION_FILE):
        write_action("idle")

    initialize_boot_state()

    if not os.path.exists(LAST_COMMAND_FILE):
        write_text_file(LAST_COMMAND_FILE, "none")
    if not os.path.exists(LAST_RESULT_FILE):
        write_text_file(LAST_RESULT_FILE, "none")
    if not os.path.exists(LAST_MESSAGE_FILE):
        write_text_file(LAST_MESSAGE_FILE, "")
    if not os.path.exists(LAST_UPDATED_FILE):
        write_text_file(LAST_UPDATED_FILE, datetime.now().isoformat(timespec="seconds"))

    mqtt_client = MqttClient(
        CONFIG["mqtt"],
        client_id=CLIENT_ID,
        will={"topic": TOPIC_POWER, "payload": "offline", "qos": 1, "retain": True},
        on_connect=on_connect,
    )
    mqtt_client.start(mode="thread")

    threading.Thread(target=uptime_loop, daemon=True).start()
    threading.Thread(target=action_sync_loop, daemon=True).start()
    threading.Thread(target=command_status_sync_loop, daemon=True).start()

    def handle_signal(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        while not stop_event.is_set():
            time.sleep(1)
    finally:
        try:
            publish(TOPIC_POWER, "offline", retain=True, qos=1)
            time.sleep(0.4)
        except Exception:
            pass
        mqtt_client.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
