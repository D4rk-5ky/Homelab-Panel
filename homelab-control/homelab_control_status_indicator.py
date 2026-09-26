#!/usr/bin/env python3
import json
import os
import signal
import socket
import sys
import threading
import time
from datetime import datetime

import paho.mqtt.client as mqtt

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(BASE_DIR, "state")
LOG_DIR = os.path.join(BASE_DIR, "logs")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

ACTION_FILE = os.path.join(STATE_DIR, "action")
LAST_COMMAND_FILE = os.path.join(STATE_DIR, "last_command")
LAST_RESULT_FILE = os.path.join(STATE_DIR, "last_result")
LAST_MESSAGE_FILE = os.path.join(STATE_DIR, "last_message")
LAST_UPDATED_FILE = os.path.join(STATE_DIR, "last_updated")
HISTORY_FILE = os.path.join(STATE_DIR, "history.json")
BOOT_ID_FILE = os.path.join(STATE_DIR, "boot_id")

stop_event = threading.Event()
mqtt_client = None


def load_config() -> dict:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


CONFIG = load_config()

MQTT_HOST = CONFIG["mqtt"]["host"]
MQTT_PORT = CONFIG["mqtt"]["port"]
MQTT_USER = CONFIG["mqtt"]["user"]
MQTT_PASS = CONFIG["mqtt"]["pass"]
MQTT_KEEPALIVE = CONFIG["mqtt"]["keepalive"]

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

def derive_history_topic() -> str:
    explicit = str(CONFIG["topics"].get("status_history", "")).strip()
    if explicit:
        return explicit

    last_message_topic = str(CONFIG["topics"].get("status_last_message", "")).strip()
    suffix = "/last_message"
    if last_message_topic.endswith(suffix):
        return last_message_topic[:-len(suffix)] + "/history"
    return ""


TOPIC_HISTORY = derive_history_topic()

PUBLISH_UPTIME_EVERY = CONFIG["timing"]["publish_uptime_every"]
HISTORY_MAX_ENTRIES = max(1, int(CONFIG["timing"].get("history_max_entries", 100)))


def ensure_dirs() -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)


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


def parse_timestamp(value: str) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


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


def current_command_record() -> dict | None:
    command = read_text_file(LAST_COMMAND_FILE, "none")
    result = read_text_file(LAST_RESULT_FILE, "none")
    message = read_text_file(LAST_MESSAGE_FILE, "")
    timestamp = read_text_file(LAST_UPDATED_FILE, "")

    command_empty = command.lower() in {"", "none", "unknown"}
    result_empty = result.lower() in {"", "none", "unknown"}
    message_empty = message in {"", "No command executed yet", "No command executed in current boot"}

    if command_empty and result_empty and message_empty:
        return None

    now = datetime.now().isoformat(timespec="seconds")
    return {
        "timestamp": timestamp or now,
        "archived_at": now,
        "command": command,
        "result": result,
        "message": message,
        "source": "Remote enhed",
    }


def history_record_signature(record: dict) -> tuple[str, str, str, str]:
    return (
        str(record.get("timestamp", "")),
        str(record.get("command", "")),
        str(record.get("result", "")),
        str(record.get("message", "")),
    )


def append_history_record(record: dict, deduplicate: bool = False) -> bool:
    history = load_history()
    signature = history_record_signature(record)

    if deduplicate:
        for existing in reversed(history):
            if history_record_signature(existing) == signature:
                return False

    history.append(record)
    save_history(history)
    return True


def archive_current_command_status() -> bool:
    record = current_command_record()
    if record is None:
        return False

    # Newer releases append every command-status event immediately. The boot
    # rollover therefore only adds the old current status when it is not
    # already present (for example after upgrading from an older release).
    return append_history_record(record, deduplicate=True)


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
    if previous_boot_id:
        return previous_boot_id != current_boot_id

    record = current_command_record()
    if record is None:
        return False

    last_updated_epoch = parse_timestamp(str(record.get("timestamp", "")))
    boot_time_epoch = get_boot_time_epoch()
    if last_updated_epoch is None or boot_time_epoch is None:
        return False

    return last_updated_epoch < boot_time_epoch


def initialize_boot_state() -> bool:
    current_boot_id = get_current_boot_id()
    new_boot = is_new_machine_boot(current_boot_id)

    if new_boot:
        archive_current_command_status()
        clear_current_command_status()
        write_action("idle")

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


def on_connect(*args):
    publish(TOPIC_POWER, "online", retain=True, qos=1)
    publish(TOPIC_ACTION, read_action(), retain=True, qos=1)
    publish(TOPIC_INFO_HOSTNAME, HOSTNAME, retain=True, qos=1)
    publish_command_status()
    publish_history()


def on_disconnect(*args):
    pass


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


def build_client():
    try:
        return mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=CLIENT_ID,
            protocol=mqtt.MQTTv311,
        )
    except AttributeError:
        return mqtt.Client(
            client_id=CLIENT_ID,
            protocol=mqtt.MQTTv311,
        )


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

    client = build_client()

    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

    client.will_set(TOPIC_POWER, payload="offline", qos=1, retain=True)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    mqtt_client = client
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=MQTT_KEEPALIVE)
    client.loop_start()

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
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
