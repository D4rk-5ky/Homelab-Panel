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

PUBLISH_UPTIME_EVERY = CONFIG["timing"]["publish_uptime_every"]


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


def publish(topic: str, payload: str, retain: bool = True, qos: int = 1) -> None:
    global mqtt_client
    if mqtt_client is None:
        return
    mqtt_client.publish(topic, payload, qos=qos, retain=retain)


def publish_command_status() -> None:
    publish(TOPIC_LAST_COMMAND, read_text_file(LAST_COMMAND_FILE, "unknown"), retain=True, qos=1)
    publish(TOPIC_LAST_RESULT, read_text_file(LAST_RESULT_FILE, "unknown"), retain=True, qos=1)
    publish(TOPIC_LAST_MESSAGE, read_text_file(LAST_MESSAGE_FILE, ""), retain=True, qos=1)
    publish(TOPIC_LAST_UPDATED, read_text_file(LAST_UPDATED_FILE, ""), retain=True, qos=1)


def on_connect(*args):
    publish(TOPIC_POWER, "online", retain=True, qos=1)
    publish(TOPIC_ACTION, read_action(), retain=True, qos=1)
    publish(TOPIC_INFO_HOSTNAME, HOSTNAME, retain=True, qos=1)
    publish_command_status()


def on_disconnect(*args):
    pass


def uptime_loop():
    while not stop_event.is_set():
        # Send heartbeat for power status
        publish(TOPIC_POWER, "online", retain=True, qos=1)

        # Send uptime
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
            read_text_file(LAST_COMMAND_FILE, "unknown"),
            read_text_file(LAST_RESULT_FILE, "unknown"),
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
    if not os.path.exists(LAST_COMMAND_FILE):
        write_text_file(LAST_COMMAND_FILE, "none")
    if not os.path.exists(LAST_RESULT_FILE):
        write_text_file(LAST_RESULT_FILE, "none")
    if not os.path.exists(LAST_MESSAGE_FILE):
        write_text_file(LAST_MESSAGE_FILE, "No command executed yet")
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
