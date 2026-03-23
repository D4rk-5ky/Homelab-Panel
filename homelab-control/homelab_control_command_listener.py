#!/usr/bin/env python3
import json
import os
import subprocess
import sys

import paho.mqtt.client as mqtt

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")


def load_config() -> dict:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


CONFIG = load_config()

MQTT_HOST = CONFIG["mqtt"]["host"]
MQTT_PORT = CONFIG["mqtt"]["port"]
MQTT_USER = CONFIG["mqtt"]["user"]
MQTT_PASS = CONFIG["mqtt"]["pass"]
MQTT_KEEPALIVE = CONFIG["mqtt"]["keepalive"]

CLIENT_ID = CONFIG["client_ids"]["command_listener"]
TOPIC_CONTROL = CONFIG["topics"]["control_power"]
COMMAND_MAP = CONFIG["commands"]


def run_script(script_name: str) -> None:
    script_path = os.path.join(SCRIPTS_DIR, script_name)

    if not os.path.isfile(script_path):
        print(f"Script not found: {script_path}", flush=True)
        return

    if not os.access(script_path, os.X_OK):
        print(f"Script is not executable: {script_path}", flush=True)
        return

    try:
        result = subprocess.run(
            [script_path],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        print(f"Executed {script_name} rc={result.returncode}", flush=True)
        if result.stdout:
            print(result.stdout.strip(), flush=True)
        if result.stderr:
            print(result.stderr.strip(), flush=True)
    except Exception as exc:
        print(f"Failed to execute {script_name}: {exc}", flush=True)


def on_connect(*args):
    client = args[0]
    client.subscribe(TOPIC_CONTROL, qos=1)
    print(f"Subscribed to {TOPIC_CONTROL}", flush=True)


def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8", errors="replace").strip()
    print(f"Received command: {payload}", flush=True)

    script_name = COMMAND_MAP.get(payload)
    if not script_name:
        print(f"Unknown command: {payload}", flush=True)
        return

    run_script(script_name)


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
    client = build_client()

    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=MQTT_KEEPALIVE)
    client.loop_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
