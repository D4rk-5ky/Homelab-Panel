#!/usr/bin/env python3
import json
import os
import subprocess
import threading
import time
import hmac
from datetime import datetime

from flask import Flask, render_template, redirect, url_for, flash, request, session
import paho.mqtt.client as mqtt

from config import (
    WOL_BROADCAST,
    MQTT_CONFIG,
    PANEL_TOKEN,
    MQTT_ONLINE_TTL_SECONDS,
    PAGE_REFRESH_SECONDS,
)
from devices import REMOTE_DEVICES, LOCAL_SERVER

try:
    from config import WEB_AUTH_CONFIG
except ImportError:
    WEB_AUTH_CONFIG = {
        "enabled": False,
        "username": "",
        "password": "",
        "secret_key": "SKIFT_DENNE_TIL_EN_LANG_TILFÆLDIG_HEMMELIG_NØGLE",
        "session_cookie_secure": False,
    }

try:
    from config import PANEL_HISTORY_MAX_ENTRIES
except ImportError:
    PANEL_HISTORY_MAX_ENTRIES = 100

PANEL_HISTORY_MAX_ENTRIES = max(1, int(PANEL_HISTORY_MAX_ENTRIES))

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(APP_DIR)
PANEL_STATE_DIR = os.path.join(APP_DIR, "state")
PANEL_HISTORY_FILE = os.path.join(PANEL_STATE_DIR, "panel_action_history.json")
LEGACY_FALLBACK_SECRET_KEY = "SKIFT_DENNE_TIL_EN_LANG_TILFÆLDIG_HEMMELIG_NØGLE"

app = Flask(__name__)
app.config.update(
    SECRET_KEY=str(WEB_AUTH_CONFIG.get("secret_key", "") or LEGACY_FALLBACK_SECRET_KEY),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(WEB_AUTH_CONFIG.get("session_cookie_secure", False)),
)

MQTT_STATE = {}
MQTT_STATE_LOCK = threading.Lock()
PANEL_ACTION_STATE = {}
PANEL_ACTION_STATE_LOCK = threading.Lock()
PANEL_HISTORY_LOCK = threading.Lock()
MQTT_CLIENT = None
MQTT_CONNECTED = False


def web_auth_enabled() -> bool:
    return bool(WEB_AUTH_CONFIG.get("enabled", False))


def validate_web_auth_config() -> None:
    secret_key = str(WEB_AUTH_CONFIG.get("secret_key", ""))

    if not web_auth_enabled():
        return

    username = str(WEB_AUTH_CONFIG.get("username", ""))
    password = str(WEB_AUTH_CONFIG.get("password", ""))

    if not username or not password or not secret_key:
        raise RuntimeError("WEB_AUTH_CONFIG username/password/secret_key må ikke være tomme når web-login er aktiveret")

    if "CHANGE_ME" in password or "CHANGE_ME" in secret_key:
        raise RuntimeError("Skift WEB_AUTH_CONFIG password og secret_key før web-login aktiveres")


def session_authenticated() -> bool:
    return session.get("authenticated") is True


def credentials_match(username: str, password: str) -> bool:
    configured_username = str(WEB_AUTH_CONFIG.get("username", ""))
    configured_password = str(WEB_AUTH_CONFIG.get("password", ""))

    username_ok = hmac.compare_digest(username.encode("utf-8"), configured_username.encode("utf-8"))
    password_ok = hmac.compare_digest(password.encode("utf-8"), configured_password.encode("utf-8"))
    return username_ok and password_ok


@app.before_request
def require_web_login():
    if not web_auth_enabled():
        return None

    if request.endpoint in {"login", "static"}:
        return None

    if not session_authenticated():
        return redirect(url_for("login"))

    return None


def check_token() -> bool:
    if web_auth_enabled():
        return True
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
    script_path = os.path.join(PROJECT_ROOT, script_name)

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


def set_mqtt_state(topic: str, payload: str) -> str | None:
    with MQTT_STATE_LOCK:
        previous = MQTT_STATE.get(topic)
        MQTT_STATE[topic] = {
            "payload": payload,
            "timestamp": time.time(),
        }
    if not previous:
        return None
    return str(previous.get("payload", ""))


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
        "none": "Ingen",
        "unknown": "Ukendt",
        "running": "Kører",
        "sent": "Afsendt",
        "success": "Succes",
        "failure": "Fejl",
    }
    return mapping.get(payload, payload)


def command_to_danish(payload: str | None) -> str:
    if not payload or payload.lower() in {"none", "unknown"}:
        return "Ingen"

    mapping = {
        "power_on": "Tænd / Wake-on-LAN",
        "shutdown": "Sluk om 1 minut",
        "shutdown_delay": "Sluk om 1 minut",
        "shutdown_cancel": "Annullér slukning/genstart",
        "reboot": "Genstart om 1 minut",
        "reboot_delay": "Genstart om 1 minut",
        "reboot_cancel": "Annullér slukning/genstart",
    }
    return mapping.get(payload, payload)


def get_history_topic_for_status_cfg(status_cfg: dict) -> str:
    explicit = str(status_cfg.get("history_topic", "")).strip()
    if explicit:
        return explicit

    last_message_topic = str(status_cfg.get("last_message_topic", "")).strip()
    suffix = "/last_message"
    if last_message_topic.endswith(suffix):
        return last_message_topic[:-len(suffix)] + "/history"

    return ""


def load_panel_history_unlocked() -> dict:
    try:
        with open(PANEL_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
        return {}

    if not isinstance(data, dict):
        return {}

    result = {}
    for device_id, entries in data.items():
        if isinstance(entries, list):
            result[str(device_id)] = [entry for entry in entries if isinstance(entry, dict)]
    return result


def save_panel_history_unlocked(history: dict) -> None:
    os.makedirs(PANEL_STATE_DIR, exist_ok=True)
    tmp = PANEL_HISTORY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, PANEL_HISTORY_FILE)


def append_panel_history_event(device_id: str, record: dict) -> None:
    if device_id not in REMOTE_DEVICES:
        return

    with PANEL_HISTORY_LOCK:
        history = load_panel_history_unlocked()
        entries = history.setdefault(device_id, [])
        entries.append(record)
        history[device_id] = entries[-PANEL_HISTORY_MAX_ENTRIES:]
        save_panel_history_unlocked(history)


def get_panel_history(device_id: str) -> list[dict]:
    with PANEL_HISTORY_LOCK:
        history = load_panel_history_unlocked()
        return [dict(entry) for entry in history.get(device_id, [])]


def clear_panel_action_state(device_id: str) -> None:
    with PANEL_ACTION_STATE_LOCK:
        PANEL_ACTION_STATE.pop(device_id, None)


def handle_device_power_transition(topic: str, previous_payload: str | None, payload: str) -> None:
    if payload.strip().lower() != "online":
        return
    if previous_payload is not None and previous_payload.strip().lower() == "online":
        return

    for device_id, device in REMOTE_DEVICES.items():
        power_topic = str(device.get("status", {}).get("power_topic", "")).strip()
        if power_topic and power_topic == topic:
            # Panel-originated state is already persisted in panel history when it
            # is created. Once the device announces a new online transition, it
            # must no longer remain as the current status card value.
            clear_panel_action_state(device_id)


def history_timestamp_sort_key(entry: dict) -> str:
    return str(entry.get("timestamp") or entry.get("archived_at") or "")


def record_panel_action(
    device_id: str,
    command: str,
    ok: bool,
    message: str,
    source: str,
    event_epoch: float,
    event_timestamp: str,
) -> None:
    if device_id not in REMOTE_DEVICES:
        return

    record = {
        "timestamp": event_timestamp,
        "archived_at": event_timestamp,
        "command": command,
        "result": "sent" if ok else "failure",
        "message": f"{source}: {message}",
        "source": "Homelab Panel",
    }

    with PANEL_ACTION_STATE_LOCK:
        PANEL_ACTION_STATE[device_id] = {
            **record,
            "recorded_at": event_epoch,
        }

    append_panel_history_event(device_id, record)


def get_panel_action_state(device_id: str) -> dict | None:
    with PANEL_ACTION_STATE_LOCK:
        state = PANEL_ACTION_STATE.get(device_id)
        return dict(state) if state else None


def get_remote_command_state_received_at(status_cfg: dict) -> float:
    received_at = 0.0
    for key in (
        "last_command_topic",
        "last_result_topic",
        "last_message_topic",
        "last_updated_topic",
    ):
        topic = status_cfg.get(key, "").strip()
        state = get_mqtt_state(topic)
        if state:
            received_at = max(received_at, float(state.get("timestamp", 0.0)))
    return received_at


def get_device_history(device_id: str, device: dict) -> list[dict]:
    entries = []
    history_topic = get_history_topic_for_status_cfg(device.get("status", {}))

    if history_topic:
        payload, _ = get_mqtt_payload_and_age(history_topic)
        if payload:
            try:
                raw_entries = json.loads(payload)
            except (TypeError, ValueError, json.JSONDecodeError):
                raw_entries = []

            if isinstance(raw_entries, list):
                for item in raw_entries:
                    if not isinstance(item, dict):
                        continue
                    entries.append({
                        "timestamp": str(item.get("timestamp") or item.get("archived_at") or "Ukendt"),
                        "archived_at": str(item.get("archived_at") or "Ukendt"),
                        "command": command_to_danish(str(item.get("command") or "")),
                        "result": result_to_danish(str(item.get("result") or "").lower() or None),
                        "message": str(item.get("message") or "Ingen"),
                        "source": str(item.get("source") or "Remote enhed"),
                    })

    for item in get_panel_history(device_id):
        entries.append({
            "timestamp": str(item.get("timestamp") or item.get("archived_at") or "Ukendt"),
            "archived_at": str(item.get("archived_at") or "Ukendt"),
            "command": command_to_danish(str(item.get("command") or "")),
            "result": result_to_danish(str(item.get("result") or "").lower() or None),
            "message": str(item.get("message") or "Ingen"),
            "source": str(item.get("source") or "Homelab Panel"),
        })

    entries.sort(key=history_timestamp_sort_key, reverse=True)
    return entries


def evaluate_remote_device_status(device_id: str, device: dict) -> dict:
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

    power_topic = str(status_cfg.get("power_topic", "")).strip()
    mqtt_configured = bool(power_topic)
    mqtt_connected = get_mqtt_connected()
    mqtt_power_payload = power_payload.lower() if power_payload else None
    mqtt_power_fresh = power_age is not None and power_age <= MQTT_ONLINE_TTL_SECONDS

    # MQTT counts as online only while the panel is currently connected to the
    # broker and has a fresh device power=online message. A cached retained/state
    # value alone must never make the device appear online after broker loss.
    mqtt_online_ok = bool(
        mqtt_configured
        and mqtt_connected
        and mqtt_power_payload == "online"
        and mqtt_power_fresh
    )

    # Ping and MQTT are intentionally evaluated independently. This lets the UI
    # show that ICMP works before MQTT is configured/connected, while the strict
    # combined Online state still requires both signals at the same time.
    if ping_ok and mqtt_online_ok:
        overall = "online"
        overall_text = "Online"
        status_class = "status-online"
    elif ping_ok or mqtt_online_ok:
        overall = "partial"
        overall_text = "Ikke fuldt online"
        status_class = "status-partial"
    else:
        overall = "offline"
        overall_text = "Offline"
        status_class = "status-offline"

    if not mqtt_configured:
        mqtt_info = "Ikke konfigureret"
    elif not mqtt_connected:
        if mqtt_power_payload is None:
            mqtt_info = "Ikke tilsluttet MQTT-broker"
        elif power_age is not None:
            mqtt_info = f"Ikke tilsluttet broker · sidst: {mqtt_power_payload} ({power_age}s siden)"
        else:
            mqtt_info = f"Ikke tilsluttet broker · sidst: {mqtt_power_payload}"
    elif mqtt_power_payload is None:
        mqtt_info = "Broker tilsluttet · ingen enhedsstatus"
    elif not mqtt_power_fresh:
        mqtt_info = f"{mqtt_power_payload} · for gammel ({power_age}s siden)"
    elif power_age is not None:
        mqtt_info = f"{mqtt_power_payload} ({power_age}s siden)"
    else:
        mqtt_info = mqtt_power_payload

    panel_action = get_panel_action_state(device_id)
    remote_command_received_at = get_remote_command_state_received_at(status_cfg)
    use_panel_action = bool(
        panel_action
        and float(panel_action.get("recorded_at", 0.0)) > remote_command_received_at
    )

    if use_panel_action:
        display_last_command = command_to_danish(str(panel_action.get("command", "")))
        display_last_result = result_to_danish(str(panel_action.get("result", "")).lower() or None)
        display_last_message = str(panel_action.get("message") or "Ingen")
        display_last_updated = str(panel_action.get("timestamp") or "Ukendt")
    else:
        display_last_command = command_to_danish(last_command_payload)
        display_last_result = result_to_danish(last_result_payload.lower() if last_result_payload else None)
        display_last_message = last_message_payload or "Ingen"
        display_last_updated = last_updated_payload or "Ukendt"

    return {
        "overall": overall,
        "overall_text": overall_text,
        "status_class": status_class,
        "ping_ok": ping_ok,
        "ping_text": "Svarer" if ping_ok else "Svarer ikke",
        "mqtt_info": mqtt_info,
        "mqtt_configured": mqtt_configured,
        "mqtt_connected": mqtt_connected,
        "mqtt_online_ok": mqtt_online_ok,
        "action_text": action_to_danish(action_payload.lower() if action_payload else None),
        "last_command": display_last_command,
        "last_result": display_last_result,
        "last_message": display_last_message,
        "last_updated": display_last_updated,
        "ip": ip,
    }


def build_remote_device_statuses() -> dict:
    result = {}
    for device_id, device in REMOTE_DEVICES.items():
        result[device_id] = evaluate_remote_device_status(device_id, device)
    return result


def execute_remote_action(device_id: str, command: str) -> tuple[bool, str]:
    device = REMOTE_DEVICES.get(device_id)
    if not device:
        return False, f"Ukendt remote enhed: {device_id}"

    if command == "power_on":
        wol_cfg = device.get("wol", {})
        if not wol_cfg.get("enabled"):
            return False, f"Wake-on-LAN er ikke aktiveret for {device['title']}"
        mac = wol_cfg.get("mac", "").strip()
        if not mac:
            return False, f"Wake-on-LAN MAC mangler for {device['title']}"
        ok, message = send_wol(mac)
        if ok:
            return True, f"Wake-on-LAN magic packet sendt til {device['title']}"
        return False, message

    command_aliases = {
        "shutdown": "shutdown_delay",
        "reboot": "reboot_delay",
    }
    resolved_command = command_aliases.get(command, command)

    mqtt_cfg = device.get("mqtt_controls")
    if not mqtt_cfg:
        return False, f"Der er ingen MQTT-kontrol for {device['title']}"

    button = next((b for b in mqtt_cfg.get("buttons", []) if b.get("id") == resolved_command), None)
    if not button:
        return False, f"Ukendt handling '{command}' for {device['title']}"

    topic = mqtt_cfg.get("topic", "").strip()
    payload = str(button.get("payload", "")).strip()
    if not topic or not payload:
        return False, f"Ufuldstændig MQTT-konfiguration for handling '{command}'"

    ok, message = mqtt_publish(topic, payload)
    if ok:
        return True, f"MQTT payload '{payload}' sendt til '{topic}'"
    return False, message


def execute_and_record_remote_action(
    device_id: str,
    command: str,
    source: str,
) -> tuple[bool, str]:
    event_epoch = time.time()
    event_timestamp = datetime.now().isoformat(timespec="seconds")
    ok, message = execute_remote_action(device_id, command)
    record_panel_action(
        device_id,
        command,
        ok,
        message,
        source,
        event_epoch,
        event_timestamp,
    )
    return ok, message


def process_panel_control_message(payload: str) -> None:
    try:
        command_data = json.loads(payload)
    except json.JSONDecodeError as exc:
        print(f"Homelab-panel control rejected: invalid JSON: {exc}", flush=True)
        return

    if not isinstance(command_data, dict):
        print("Homelab-panel control rejected: payload must be a JSON object", flush=True)
        return

    device_id = str(command_data.get("device_id", "")).strip()
    command = str(command_data.get("command", "")).strip()
    if not device_id or not command:
        print("Homelab-panel control rejected: device_id and command are required", flush=True)
        return

    panel_control_topic = MQTT_CONFIG.get("panel_control_topic", "").strip() or "panel-control"
    ok, message = execute_and_record_remote_action(
        device_id,
        command,
        f"MQTT {panel_control_topic}",
    )
    outcome = "success" if ok else "failure"
    print(
        f"Homelab-panel control {outcome}: device_id={device_id} command={command} message={message}",
        flush=True,
    )


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
            topic = str(status_cfg.get(key, "")).strip()
            if topic:
                topics.add(topic)

        history_topic = get_history_topic_for_status_cfg(status_cfg)
        if history_topic:
            topics.add(history_topic)

    panel_control_topic = MQTT_CONFIG.get("panel_control_topic", "").strip()
    if panel_control_topic:
        topics.add(panel_control_topic)

    for topic in topics:
        client.subscribe(topic, qos=1)
        print(f"Homelab-panel subscribed to {topic}", flush=True)


def on_disconnect_compat(*args):
    set_mqtt_connected(False)
    print("Homelab-panel MQTT disconnected", flush=True)


def on_message_compat(client, userdata, msg):
    payload = msg.payload.decode("utf-8", errors="replace").strip()
    panel_control_topic = MQTT_CONFIG.get("panel_control_topic", "").strip()

    if panel_control_topic and msg.topic == panel_control_topic:
        if getattr(msg, "retain", False):
            print("Homelab-panel control rejected: retained control messages are not executed", flush=True)
            return
        threading.Thread(
            target=process_panel_control_message,
            args=(payload,),
            daemon=True,
        ).start()
        return

    previous_payload = set_mqtt_state(msg.topic, payload)
    handle_device_power_transition(msg.topic, previous_payload, payload)
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
        # Start the network loop even when the broker is not reachable yet.
        # connect_async() lets Paho retry in the background using the configured
        # reconnect delay, while the web panel remains available for ping/status.
        client.connect_async(MQTT_CONFIG["host"], MQTT_CONFIG["port"], keepalive=60)
        client.loop_start()
        MQTT_CLIENT = client
        print("Homelab-panel MQTT listener started; broker connection runs in background", flush=True)
    except Exception as exc:
        print(f"MQTT listener kunne ikke starte: {exc}", flush=True)


@app.route("/login", methods=["GET", "POST"])
def login():
    if not web_auth_enabled():
        return redirect(url_for("index"))

    if session_authenticated():
        return redirect(url_for("index"))

    error = ""

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if credentials_match(username, password):
            session.clear()
            session["authenticated"] = True
            session["username"] = str(WEB_AUTH_CONFIG.get("username", ""))
            return redirect(url_for("index"))

        error = "Forkert brugernavn eller adgangskode."

    return render_template("login.html", error=error)


@app.post("/logout")
def logout():
    session.clear()
    if web_auth_enabled():
        return redirect(url_for("login"))
    return redirect(url_for("index"))


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
        web_auth_enabled=web_auth_enabled(),
        logged_in_username=session.get("username", ""),
    )


@app.route("/history/<device_id>")
def device_history(device_id: str):
    if not check_token():
        return "Forbudt", 403

    device = REMOTE_DEVICES.get(device_id)
    if not device:
        return "Ukendt remote enhed", 404

    return render_template(
        "history.html",
        device_id=device_id,
        device=device,
        history=get_device_history(device_id, device),
        token=request.args.get("token", ""),
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        web_auth_enabled=web_auth_enabled(),
        logged_in_username=session.get("username", ""),
    )


@app.post("/wol/<device_id>")
def wol(device_id: str):
    if not check_token():
        return "Forbudt", 403

    device = REMOTE_DEVICES.get(device_id)
    if not device:
        flash("Ukendt WoL-enhed.", "error")
        return redirect(url_for("index", token=request.args.get("token", "")))

    ok, msg = execute_and_record_remote_action(device_id, "power_on", "Webpanel")

    if ok:
        flash(f"Wake-on-LAN sendt til {device['title']}: {msg}", "success")
    else:
        flash(f"Wake-on-LAN fejlede for {device['title']}: {msg}", "error")

    return redirect(url_for("index", token=request.args.get("token", "")))


@app.post("/mqtt/<device_id>/<button_id>")
def mqtt_button(device_id: str, button_id: str):
    if not check_token():
        return "Forbudt", 403

    device = REMOTE_DEVICES.get(device_id)
    if not device:
        flash("Ukendt remote enhed.", "error")
        return redirect(url_for("index", token=request.args.get("token", "")))

    ok, msg = execute_and_record_remote_action(device_id, button_id, "Webpanel")

    if ok:
        flash(f"MQTT-handling sendt til {device['title']}: '{button_id}'", "success")
    else:
        flash(f"MQTT-handling fejlede for {device['title']}: {msg}", "error")

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
    validate_web_auth_config()
    start_mqtt_listener()
    app.run(host="0.0.0.0", port=5000)
else:
    validate_web_auth_config()
    start_mqtt_listener()
