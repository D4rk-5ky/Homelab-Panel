#!/usr/bin/env python3
import os
import subprocess
import threading
import time
from datetime import datetime

from flask import Flask, render_template, redirect, url_for, flash, request
import paho.mqtt.client as mqtt

from config import (
    WOL_BROADCAST,
    MQTT_CONFIG,
    PANEL_TOKEN,
    LOCAL_SCRIPT_PATH,
    MQTT_ONLINE_TTL_SECONDS,
    PAGE_REFRESH_SECONDS,
)
from devices import REMOTE_DEVICES, LOCAL_SERVER

app = Flask(__name__)
app.secret_key = "SKIFT_DENNE_TIL_EN_LANG_TILFÆLDIG_HEMMELIG_NØGLE"

MQTT_STATE = {}
MQTT_STATE_LOCK = threading.Lock()
MQTT_CLIENT = None


def check_token() -> bool:
    if not PANEL_TOKEN:
        return True
    return request.args.get("token", "") == PANEL_TOKEN


def run_command(cmd: list[str], timeout: int = 20) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()

        if result.returncode == 0:
            return True, stdout or "OK"

        return False, stderr or stdout or f"Kommando fejlede med rc={result.returncode}"
    except Exception as exc:
        return False, str(exc)


def mqtt_publish(topic: str, payload: str) -> tuple[bool, str]:
    cmd = [
        "mosquitto_pub",
        "-h", MQTT_CONFIG["host"],
        "-p", str(MQTT_CONFIG["port"]),
        "-t", topic,
        "-m", payload,
        "-q", str(MQTT_CONFIG["qos"]),
    ]

    if MQTT_CONFIG["retain"]:
        cmd.append("-r")

    if MQTT_CONFIG["user"]:
        cmd.extend(["-u", MQTT_CONFIG["user"]])

    if MQTT_CONFIG["pass"]:
        cmd.extend(["-P", MQTT_CONFIG["pass"]])

    return run_command(cmd)


def send_wol(mac: str) -> tuple[bool, str]:
    cmd = [
        "wakeonlan",
        "-i", WOL_BROADCAST,
        mac,
    ]
    return run_command(cmd)


def run_local_script(script_name: str) -> tuple[bool, str]:
    script_path = os.path.join(LOCAL_SCRIPT_PATH, script_name)

    if not os.path.isfile(script_path):
        return False, f"Script findes ikke: {script_path}"

    if not os.access(script_path, os.X_OK):
        return False, f"Script er ikke eksekverbart: {script_path}"

    return run_command([script_path])


def ping_host(ip: str) -> bool:
    if not ip:
        return False

    ok, _ = run_command(["ping", "-c", "1", "-W", "1", ip], timeout=3)
    return ok


def set_mqtt_state(topic: str, payload: str) -> None:
    with MQTT_STATE_LOCK:
        MQTT_STATE[topic] = {
            "payload": payload,
            "timestamp": time.time(),
        }


def set_mqtt_connected(value: bool) -> None:
    global MQTT_CONNECTED
    MQTT_CONNECTED = value


def get_mqtt_connected() -> bool:
    return MQTT_CONNECTED


def get_mqtt_state(topic: str) -> dict | None:
    if not topic:
        return None
    with MQTT_STATE_LOCK:
        return MQTT_STATE.get(topic)


def get_mqtt_payload_and_age(topic: str) -> tuple[str | None, int | None]:
    state = get_mqtt_state(topic)
    if not state:
        return None, None
    payload = state["payload"].strip()
    age = int(time.time() - state["timestamp"])
    return payload, age


def action_to_danish(payload: str | None) -> str:
    if not payload:
        return "Ukendt"

    mapping = {
        "idle": "Ingen",
        "shutdown_pending": "Slukning planlagt",
        "reboot_pending": "Genstart planlagt",
    }
    return mapping.get(payload, payload)


def result_to_danish(payload: str | None) -> str:
    if not payload:
        return "Ukendt"

    mapping = {
        "running": "Kører",
        "success": "Succes",
        "failure": "Fejl",
    }
    return mapping.get(payload, payload)


def evaluate_remote_device_status(device: dict) -> dict:
    wol_cfg = device.get("wol", {})
    status_cfg = device.get("status", {})

    ip = wol_cfg.get("ip", "")
    ping_ok = ping_host(ip)

    power_payload, power_age = get_mqtt_payload_and_age(status_cfg.get("power_topic", ""))
    action_payload, _ = get_mqtt_payload_and_age(status_cfg.get("action_topic", ""))
    last_command_payload, _ = get_mqtt_payload_and_age(status_cfg.get("last_command_topic", ""))
    last_result_payload, _ = get_mqtt_payload_and_age(status_cfg.get("last_result_topic", ""))
    last_message_payload, _ = get_mqtt_payload_and_age(status_cfg.get("last_message_topic", ""))
    last_updated_payload, _ = get_mqtt_payload_and_age(status_cfg.get("last_updated_topic", ""))

    mqtt_power_payload = power_payload.lower() if power_payload else None
    mqtt_power_fresh = power_age is not None and power_age <= MQTT_ONLINE_TTL_SECONDS
    mqtt_online_ok = mqtt_power_payload == "online" and mqtt_power_fresh

    # Ny streng logik:
    # Kun online hvis BÅDE ping virker OG MQTT siger online og er frisk
    if ping_ok and mqtt_online_ok:
        overall = "online"
        overall_text = "Online"
        status_class = "status-online"
    else:
        overall = "offline"
        overall_text = "Offline"
        status_class = "status-offline"

    if mqtt_power_payload is None:
        mqtt_info = "Ingen MQTT-status"
    elif power_age is not None:
        mqtt_info = f"{mqtt_power_payload} ({power_age}s siden)"
    else:
        mqtt_info = mqtt_power_payload

    return {
        "overall": overall,
        "overall_text": overall_text,
        "status_class": status_class,
        "ping_ok": ping_ok,
        "ping_text": "Svarer" if ping_ok else "Svarer ikke",
        "mqtt_info": mqtt_info,
        "mqtt_online_ok": mqtt_online_ok,
        "action_text": action_to_danish(action_payload.lower() if action_payload else None),
        "last_command": last_command_payload or "Ingen",
        "last_result": result_to_danish(last_result_payload.lower() if last_result_payload else None),
        "last_message": last_message_payload or "Ingen",
        "last_updated": last_updated_payload or "Ukendt",
        "ip": ip,
    }


def build_remote_device_statuses() -> dict:
    result = {}
    for device_id, device in REMOTE_DEVICES.items():
        result[device_id] = evaluate_remote_device_status(device)
    return result


def on_connect_compat(*args):
    client = args[0]
    set_mqtt_connected(True)

    print("Homelab-panel MQTT connected", flush=True)

    topics = set()

    for device in REMOTE_DEVICES.values():
        status_cfg = device.get("status", {})
        for key in (
            "power_topic",
            "action_topic",
            "last_command_topic",
            "last_result_topic",
            "last_message_topic",
            "last_updated_topic",
        ):
            topic = status_cfg.get(key, "").strip()
            if topic:
                topics.add(topic)

    for topic in topics:
        client.subscribe(topic, qos=1)
        print(f"Homelab-panel subscribed to {topic}", flush=True)

def on_disconnect_compat(*args):
    set_mqtt_connected(False)
    print("Homelab-panel MQTT disconnected", flush=True)

def on_message_compat(client, userdata, msg):
    payload = msg.payload.decode("utf-8", errors="replace").strip()
    set_mqtt_state(msg.topic, payload)
    print(f"Homelab-panel MQTT message: {msg.topic} = {payload}", flush=True)


def build_mqtt_client():
    try:
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=MQTT_CONFIG["client_id_panel_status"],
            protocol=mqtt.MQTTv311,
        )
    except AttributeError:
        client = mqtt.Client(
            client_id=MQTT_CONFIG["client_id_panel_status"],
            protocol=mqtt.MQTTv311,
        )

    client.reconnect_delay_set(min_delay=1, max_delay=30)
    return client


def start_mqtt_listener() -> None:
    global MQTT_CLIENT

    client = build_mqtt_client()

    if MQTT_CONFIG["user"]:
        client.username_pw_set(MQTT_CONFIG["user"], MQTT_CONFIG["pass"])

    client.on_connect = on_connect_compat
    client.on_disconnect = on_disconnect_compat
    client.on_message = on_message_compat

    try:
        client.connect(MQTT_CONFIG["host"], MQTT_CONFIG["port"], keepalive=60)
        client.loop_start()
        MQTT_CLIENT = client
        print("Homelab-panel MQTT listener started", flush=True)
    except Exception as exc:
        print(f"MQTT listener kunne ikke starte: {exc}", flush=True)


@app.route("/")
def index():
    if not check_token():
        return "Forbudt", 403

    remote_statuses = build_remote_device_statuses()

    return render_template(
        "index.html",
        remote_devices=REMOTE_DEVICES,
        remote_statuses=remote_statuses,
        local_server=LOCAL_SERVER,
        page_refresh_seconds=PAGE_REFRESH_SECONDS,
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        token=request.args.get("token", ""),
    )


@app.post("/wol/<device_id>")
def wol(device_id: str):
    if not check_token():
        return "Forbudt", 403

    device = REMOTE_DEVICES.get(device_id)
    if not device:
        flash("Ukendt WoL-enhed.", "error")
        return redirect(url_for("index", token=request.args.get("token", "")))

    wol_cfg = device.get("wol", {})
    if not wol_cfg.get("enabled"):
        flash("WoL er ikke aktiveret for denne enhed.", "error")
        return redirect(url_for("index", token=request.args.get("token", "")))

    ok, msg = send_wol(wol_cfg["mac"])

    if ok:
        flash(f"Wake-on-LAN sendt til {wol_cfg['label']} ({wol_cfg['mac']}): {msg}", "success")
    else:
        flash(f"Wake-on-LAN fejlede for {wol_cfg['label']}: {msg}", "error")

    return redirect(url_for("index", token=request.args.get("token", "")))


@app.post("/mqtt/<device_id>/<button_id>")
def mqtt_button(device_id: str, button_id: str):
    if not check_token():
        return "Forbudt", 403

    device = REMOTE_DEVICES.get(device_id)
    if not device:
        flash("Ukendt remote enhed.", "error")
        return redirect(url_for("index", token=request.args.get("token", "")))

    mqtt_cfg = device.get("mqtt_controls")
    if not mqtt_cfg:
        flash("Der er ingen MQTT-kontrol for denne enhed.", "error")
        return redirect(url_for("index", token=request.args.get("token", "")))

    button = next((b for b in mqtt_cfg["buttons"] if b["id"] == button_id), None)
    if not button:
        flash("Ukendt MQTT-handling.", "error")
        return redirect(url_for("index", token=request.args.get("token", "")))

    ok, msg = mqtt_publish(mqtt_cfg["topic"], button["payload"])

    if ok:
        flash(f"MQTT sendt til {device['title']}: payload='{button['payload']}'", "success")
    else:
        flash(f"MQTT fejlede for {device['title']}: {msg}", "error")

    return redirect(url_for("index", token=request.args.get("token", "")))


@app.post("/local/<button_id>")
def local_button(button_id: str):
    if not check_token():
        return "Forbudt", 403

    button = next((b for b in LOCAL_SERVER["buttons"] if b["id"] == button_id), None)
    if not button:
        flash("Ukendt lokal handling.", "error")
        return redirect(url_for("index", token=request.args.get("token", "")))

    ok, msg = run_local_script(button["script"])

    if ok:
        flash(f"Kørte lokalt script: {button['script']} -> {msg}", "success")
    else:
        flash(f"Lokalt script fejlede: {button['script']} -> {msg}", "error")

    return redirect(url_for("index", token=request.args.get("token", "")))


if __name__ == "__main__":
    start_mqtt_listener()
    app.run(host="0.0.0.0", port=5000)
else:
    start_mqtt_listener()
