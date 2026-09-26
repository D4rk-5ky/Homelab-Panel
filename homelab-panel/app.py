#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import threading
import time
import hmac
import uuid
from datetime import datetime

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(APP_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, render_template, redirect, url_for, flash, request, session
from configs.config import (
    WOL_BROADCAST,
    MQTT_CONFIG,
    PANEL_TOKEN,
    MQTT_ONLINE_TTL_SECONDS,
    PAGE_REFRESH_SECONDS,
)
from configs.devices import REMOTE_DEVICES, LOCAL_SERVER

try:
    from configs.config import WEB_AUTH_CONFIG
except ImportError:
    WEB_AUTH_CONFIG = {
        "enabled": False,
        "username": "",
        "password": "",
        "secret_key": "SKIFT_DENNE_TIL_EN_LANG_TILFÆLDIG_HEMMELIG_NØGLE",
        "session_cookie_secure": False,
    }

try:
    from configs.config import PANEL_HISTORY_MAX_ENTRIES
except ImportError:
    PANEL_HISTORY_MAX_ENTRIES = 100

PANEL_HISTORY_MAX_ENTRIES = max(1, int(PANEL_HISTORY_MAX_ENTRIES))

try:
    from configs.config import HOME_ASSISTANT_CONFIG
except ImportError:
    HOME_ASSISTANT_CONFIG = {
        "enabled": False,
        "discovery_prefix": "homeassistant",
        "state_prefix": "homelab-panel/ha",
        "availability_topic": "homelab-panel/availability",
        "status_topic": "homeassistant/status",
        "status_online_payload": "online",
        "qos": 1,
        "retain": True,
    }

try:
    from configs.config import STATUS_MONITOR_INTERVAL_SECONDS
except ImportError:
    STATUS_MONITOR_INTERVAL_SECONDS = 10

try:
    from configs.config import PANEL_JOB_MAX_ENTRIES
except ImportError:
    PANEL_JOB_MAX_ENTRIES = 100

STATUS_MONITOR_INTERVAL_SECONDS = max(2, int(STATUS_MONITOR_INTERVAL_SECONDS))
PANEL_JOB_MAX_ENTRIES = max(1, int(PANEL_JOB_MAX_ENTRIES))

# The panel and control components share generic MQTT transport primitives.
from shared_modules.mqtt import derive_related_topic

# Keep the Flask entry point focused on web/state orchestration. Project-specific
# implementations live under homelab-panel/modules while this entry point remains
# directly executable from any working directory.
from modules.panel_actions import PanelActionManager
from modules.panel_home_assistant import HomeAssistantIntegration
from modules.panel_mqtt import PanelMqttRuntime

SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
PANEL_STATE_DIR = os.path.join(APP_DIR, "state")
PANEL_HISTORY_FILE = os.path.join(PANEL_STATE_DIR, "panel_action_history.json")
PANEL_RUNTIME_FILE = os.path.join(PANEL_STATE_DIR, "device_runtime_state.json")
PANEL_JOBS_FILE = os.path.join(PANEL_STATE_DIR, "panel_jobs.json")
LEGACY_FALLBACK_SECRET_KEY = "SKIFT_DENNE_TIL_EN_LANG_TILFÆLDIG_HEMMELIG_NØGLE"

app = Flask(__name__)
app.config.update(
    SECRET_KEY=str(WEB_AUTH_CONFIG.get("secret_key", "") or LEGACY_FALLBACK_SECRET_KEY),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(WEB_AUTH_CONFIG.get("session_cookie_secure", False)),
)

# MQTT_CONNECTED remains as a compatibility mirror for callers/tests that
# previously inspected this module-level flag directly. PanelMqttRuntime owns
# the broker client and mutable MQTT caches.
MQTT_CONNECTED = False
PANEL_ACTION_STATE = {}
PANEL_ACTION_STATE_LOCK = threading.Lock()
PANEL_HISTORY_LOCK = threading.Lock()
DEVICE_STATUS_CACHE = {}
DEVICE_STATUS_CACHE_LOCK = threading.Lock()
DEVICE_RUNTIME_LOCK = threading.Lock()
PANEL_JOBS_LOCK = threading.Lock()
BACKGROUND_MONITOR_STARTED = False
BACKGROUND_MONITOR_LOCK = threading.Lock()
REMOTE_JOB_EVENT_SEEN = set()


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



def load_json_file(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
        return default
    return data


def save_json_file_atomic(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def get_device_button(device: dict, command: str) -> dict | None:
    mqtt_cfg = device.get("mqtt_controls") or {}
    for button in mqtt_cfg.get("buttons", []):
        if str(button.get("id", "")) == command:
            return button
    return None


def resolve_confirmation_text(configured_text, title: str) -> str:
    """Resolve the optional $TITLE placeholder used by browser confirmations."""
    return str(configured_text or "").replace("$TITLE", str(title or ""))


def get_related_status_topic(status_cfg: dict, explicit_key: str, suffix: str) -> str:
    return derive_related_topic(
        status_cfg, explicit_key, suffix, base_key="last_message_topic"
    )


def get_hostname_topic_for_status_cfg(status_cfg: dict) -> str:
    return get_related_status_topic(status_cfg, "hostname_topic", "/hostname")


def get_uptime_topic_for_status_cfg(status_cfg: dict) -> str:
    return get_related_status_topic(status_cfg, "uptime_topic", "/uptime")


def get_jobs_topic_for_status_cfg(status_cfg: dict) -> str:
    return get_related_status_topic(status_cfg, "jobs_topic", "/jobs")


def get_boot_id_topic_for_status_cfg(status_cfg: dict) -> str:
    return get_related_status_topic(status_cfg, "boot_id_topic", "/boot_id")


def get_boot_time_topic_for_status_cfg(status_cfg: dict) -> str:
    return get_related_status_topic(status_cfg, "boot_time_topic", "/boot_time")


def get_device_category(device: dict, command: str) -> str:
    if command == "power_on" or command == "cancel_wol":
        return "power"
    button = get_device_button(device, command)
    if button:
        return str(button.get("category") or "command").strip().lower()
    if command.startswith(("shutdown", "reboot")):
        return "power"
    return "command"


def _sync_mqtt_connected(value: bool) -> None:
    """Mirror PanelMqttRuntime connectivity for legacy module-level readers."""
    global MQTT_CONNECTED
    MQTT_CONNECTED = bool(value)


def _device_status_cache_snapshot() -> dict:
    """Return an isolated copy of cached device statuses for HA birth snapshots."""
    with DEVICE_STATUS_CACHE_LOCK:
        return {key: dict(value) for key, value in DEVICE_STATUS_CACHE.items()}


ACTION_MANAGER = PanelActionManager(
    remote_devices=lambda: REMOTE_DEVICES,
    local_server=lambda: LOCAL_SERVER,
    scripts_dir=lambda: SCRIPTS_DIR,
    wol_broadcast=lambda: WOL_BROADCAST,
    run_command=lambda *args, **kwargs: run_command(*args, **kwargs),
    mqtt_publish=lambda *args, **kwargs: mqtt_publish(*args, **kwargs),
    local_script_runner=lambda *args, **kwargs: run_local_script(*args, **kwargs),
    ping_host=lambda *args, **kwargs: ping_host(*args, **kwargs),
    get_device_button=lambda *args, **kwargs: get_device_button(*args, **kwargs),
    update_panel_job=lambda *args, **kwargs: update_panel_job(*args, **kwargs),
    record_device_event=lambda *args, **kwargs: record_device_event(*args, **kwargs),
    set_expected_state=lambda *args, **kwargs: set_expected_state(*args, **kwargs),
    device_mqtt_online=lambda *args, **kwargs: device_mqtt_online(*args, **kwargs),
    device_mqtt_offline=lambda *args, **kwargs: device_mqtt_offline(*args, **kwargs),
)

HOME_ASSISTANT = HomeAssistantIntegration(
    config=lambda: HOME_ASSISTANT_CONFIG,
    mqtt_config=lambda: MQTT_CONFIG,
    remote_devices=lambda: REMOTE_DEVICES,
    local_server=lambda: LOCAL_SERVER,
    is_mqtt_connected=lambda: get_mqtt_connected(),
    publish_direct=lambda *args, **kwargs: publish_mqtt_direct(*args, **kwargs),
    status_cache_snapshot=lambda: _device_status_cache_snapshot(),
    combined_device_jobs=lambda *args, **kwargs: combined_device_jobs(*args, **kwargs),
    wol_job_active=lambda *args, **kwargs: wol_job_active(*args, **kwargs),
)

MQTT_RUNTIME = PanelMqttRuntime(
    mqtt_config=lambda: MQTT_CONFIG,
    ha_config=lambda: HOME_ASSISTANT_CONFIG,
    remote_devices=lambda: REMOTE_DEVICES,
    home_assistant_enabled=lambda: home_assistant_enabled(),
    publish_home_assistant_snapshot=lambda: publish_home_assistant_snapshot(),
    record_device_event=lambda *args, **kwargs: record_device_event(*args, **kwargs),
    process_panel_control_message=lambda: process_panel_control_message,
    handle_device_power_transition=lambda *args, **kwargs: handle_device_power_transition(*args, **kwargs),
    process_remote_jobs_message=lambda *args, **kwargs: process_remote_jobs_message(*args, **kwargs),
    handle_boot_id_message=lambda *args, **kwargs: handle_boot_id_message(*args, **kwargs),
    start_status_monitor=lambda: start_status_monitor(),
    topic_helpers={
        "hostname": lambda status_cfg: get_hostname_topic_for_status_cfg(status_cfg),
        "uptime": lambda status_cfg: get_uptime_topic_for_status_cfg(status_cfg),
        "history": lambda status_cfg: get_history_topic_for_status_cfg(status_cfg),
        "jobs": lambda status_cfg: get_jobs_topic_for_status_cfg(status_cfg),
        "boot_id": lambda status_cfg: get_boot_id_topic_for_status_cfg(status_cfg),
        "boot_time": lambda status_cfg: get_boot_time_topic_for_status_cfg(status_cfg),
    },
    connected_changed=lambda value: _sync_mqtt_connected(value),
)

# Mutable aliases are retained for compatibility/diagnostics while ownership
# lives in PanelMqttRuntime.
MQTT_STATE = MQTT_RUNTIME.state
MQTT_STATE_LOCK = MQTT_RUNTIME.state_lock
MQTT_SUBSCRIPTIONS = MQTT_RUNTIME.subscriptions
MQTT_CONNECTION_INFO = MQTT_RUNTIME.connection_info


def load_runtime_state_unlocked() -> dict:
    data = load_json_file(PANEL_RUNTIME_FILE, {})
    return data if isinstance(data, dict) else {}


def save_runtime_state_unlocked(data: dict) -> None:
    save_json_file_atomic(PANEL_RUNTIME_FILE, data)


def get_device_runtime(device_id: str) -> dict:
    with DEVICE_RUNTIME_LOCK:
        data = load_runtime_state_unlocked()
        value = data.get(device_id, {})
        return dict(value) if isinstance(value, dict) else {}


def update_device_runtime(device_id: str, **updates) -> dict:
    with DEVICE_RUNTIME_LOCK:
        data = load_runtime_state_unlocked()
        current = data.get(device_id, {})
        if not isinstance(current, dict):
            current = {}
        current.update(updates)
        data[device_id] = current
        save_runtime_state_unlocked(data)
        return dict(current)


def get_expected_state(device_id: str, device: dict) -> str:
    runtime = get_device_runtime(device_id)
    return str(runtime.get("expected_state") or device.get("expected_state_default") or "unknown")


def set_expected_state(device_id: str, state: str, reason: str = "") -> None:
    update_device_runtime(
        device_id,
        expected_state=state,
        expected_state_reason=reason,
        expected_state_updated=datetime.now().isoformat(timespec="seconds"),
    )


def load_panel_jobs_unlocked() -> dict:
    data = load_json_file(PANEL_JOBS_FILE, {})
    if not isinstance(data, dict):
        return {}
    result = {}
    for device_id, jobs in data.items():
        if isinstance(jobs, list):
            result[str(device_id)] = [job for job in jobs if isinstance(job, dict)]
    return result


def save_panel_jobs_unlocked(data: dict) -> None:
    trimmed = {}
    for device_id, jobs in data.items():
        if isinstance(jobs, list):
            trimmed[device_id] = jobs[-PANEL_JOB_MAX_ENTRIES:]
    save_json_file_atomic(PANEL_JOBS_FILE, trimmed)


def update_panel_job(device_id: str, job_id: str, **updates) -> dict:
    with PANEL_JOBS_LOCK:
        data = load_panel_jobs_unlocked()
        jobs = data.setdefault(device_id, [])
        job = next((item for item in jobs if str(item.get("job_id")) == job_id), None)
        if job is None:
            job = {"job_id": job_id}
            jobs.append(job)
        job.update(updates)
        data[device_id] = jobs[-PANEL_JOB_MAX_ENTRIES:]
        save_panel_jobs_unlocked(data)
        return dict(job)


def get_panel_jobs(device_id: str) -> list[dict]:
    with PANEL_JOBS_LOCK:
        data = load_panel_jobs_unlocked()
        return [dict(item) for item in data.get(device_id, [])]


def history_contains_event(device_id: str, job_id: str, status: str, timestamp: str) -> bool:
    if not job_id:
        return False
    for item in get_panel_history(device_id):
        if (
            str(item.get("job_id", "")) == job_id
            and str(item.get("job_status", item.get("result", ""))) == status
            and str(item.get("timestamp", "")) == timestamp
        ):
            return True
    return False


def record_device_event(
    device_id: str,
    *,
    category: str,
    event_type: str,
    message: str,
    command: str = "",
    result: str = "",
    source: str = "Homelab Panel",
    severity: str = "info",
    timestamp: str | None = None,
    **extra,
) -> dict:
    when = timestamp or datetime.now().isoformat(timespec="seconds")
    record = {
        "timestamp": when,
        "archived_at": when,
        "command": command,
        "result": result,
        "message": message,
        "source": source,
        "category": category or "other",
        "event_type": event_type or "event",
        "severity": severity or "info",
    }
    record.update(extra)
    append_panel_history_event(device_id, record)
    return record


def active_job_status(status: str) -> bool:
    return status in {"queued", "running", "waiting", "confirming"}


def combined_device_jobs(device_id: str, device: dict) -> list[dict]:
    jobs = get_panel_jobs(device_id)
    jobs_topic = get_jobs_topic_for_status_cfg(device.get("status", {}))
    payload, _ = get_mqtt_payload_and_age(jobs_topic)
    if payload:
        try:
            remote_jobs = json.loads(payload)
        except (json.JSONDecodeError, TypeError, ValueError):
            remote_jobs = []
        if isinstance(remote_jobs, list):
            known = {(str(j.get("job_id")), str(j.get("updated_at"))) for j in jobs}
            for job in remote_jobs:
                if not isinstance(job, dict):
                    continue
                key = (str(job.get("job_id")), str(job.get("updated_at")))
                if key not in known:
                    jobs.append({**job, "origin": "Homelab Control"})
    jobs.sort(key=lambda j: str(j.get("updated_at") or j.get("queued_at") or ""), reverse=True)
    return jobs[:PANEL_JOB_MAX_ENTRIES]


def mqtt_publish(topic: str, payload: str) -> tuple[bool, str]:
    """Publish one remote command through the shared disposable MQTT publisher."""
    return MQTT_RUNTIME.publish_command(topic, payload)



def send_wol(mac: str) -> tuple[bool, str]:
    """Compatibility delegate for one Wake-on-LAN send."""
    return ACTION_MANAGER.send_wol(mac)



def run_local_script(script_name: str) -> tuple[bool, str]:
    """Compatibility delegate for guarded local script execution."""
    return ACTION_MANAGER.run_local_script(script_name)



def execute_local_action(command: str) -> tuple[bool, str]:
    """Execute one configured local button through the action module."""
    return ACTION_MANAGER.execute_local_action(command)



def ping_host(ip: str) -> bool:
    if not ip:
        return False

    # macOS uses milliseconds for -W; Linux uses seconds.
    reply_timeout = "1000" if sys.platform == "darwin" else "1"
    ok, _ = run_command(["ping", "-c", "1", "-W", reply_timeout, ip], timeout=3)
    return ok


def set_mqtt_state(topic: str, payload: str, retain: bool = False, qos: int = 0) -> str | None:
    """Store one received MQTT value in the runtime cache."""
    return MQTT_RUNTIME.set_state(topic, payload, retain=retain, qos=qos)



def set_mqtt_connected(value: bool, reason: str = "") -> None:
    """Update MQTT runtime connectivity and the compatibility mirror."""
    MQTT_RUNTIME.set_connected(value, reason)



def get_mqtt_connected() -> bool:
    """Return broker connectivity, honoring direct legacy mirror updates."""
    if MQTT_RUNTIME.connected != bool(MQTT_CONNECTED):
        MQTT_RUNTIME.connected = bool(MQTT_CONNECTED)
    return bool(MQTT_CONNECTED)



def get_mqtt_state(topic: str) -> dict | None:
    """Return one cached MQTT topic record."""
    return MQTT_RUNTIME.get_state(topic)



def get_mqtt_payload_and_age(topic: str) -> tuple[str | None, int | None]:
    """Return one cached MQTT payload and age."""
    return MQTT_RUNTIME.get_payload_and_age(topic)



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
        "queued": "I kø",
        "running": "Kører",
        "waiting": "Venter",
        "confirming": "Bekræfter",
        "cancelled": "Annulleret",
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

    device = REMOTE_DEVICES[device_id]
    record = {
        "timestamp": event_timestamp,
        "archived_at": event_timestamp,
        "command": command,
        "result": "sent" if ok else "failure",
        "message": f"{source}: {message}",
        "source": "Homelab Panel",
        "category": get_device_category(device, command),
        "event_type": "command_dispatch",
        "severity": "info" if ok else "error",
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
                        "category": str(item.get("category") or "command").lower(),
                        "event_type": str(item.get("event_type") or "command_status"),
                        "severity": str(item.get("severity") or ("error" if str(item.get("result", "")).lower() == "failure" else "info")),
                        "job_id": str(item.get("job_id") or ""),
                        "job_status": str(item.get("job_status") or ""),
                        "duration_seconds": item.get("duration_seconds"),
                    })

    for item in get_panel_history(device_id):
        entries.append({
            "timestamp": str(item.get("timestamp") or item.get("archived_at") or "Ukendt"),
            "archived_at": str(item.get("archived_at") or "Ukendt"),
            "command": command_to_danish(str(item.get("command") or "")),
            "result": result_to_danish(str(item.get("result") or "").lower() or None),
            "message": str(item.get("message") or "Ingen"),
            "source": str(item.get("source") or "Homelab Panel"),
            "category": str(item.get("category") or "command").lower(),
            "event_type": str(item.get("event_type") or "event"),
            "severity": str(item.get("severity") or ("error" if str(item.get("result", "")).lower() == "failure" else "info")),
            "job_id": str(item.get("job_id") or ""),
            "job_status": str(item.get("job_status") or ""),
            "duration_seconds": item.get("duration_seconds"),
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
    hostname_payload, _ = get_mqtt_payload_and_age(get_hostname_topic_for_status_cfg(status_cfg))
    uptime_payload, _ = get_mqtt_payload_and_age(get_uptime_topic_for_status_cfg(status_cfg))
    boot_time_payload, _ = get_mqtt_payload_and_age(get_boot_time_topic_for_status_cfg(status_cfg))

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
    expected_state = get_expected_state(device_id, device)
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
        if expected_state == "offline":
            overall_text = "Offline (forventet)"
            status_class = "status-expected-offline"
        elif expected_state == "starting":
            overall_text = "Offline (starter)"
            status_class = "status-partial"
        elif expected_state == "restarting":
            overall_text = "Offline (genstarter)"
            status_class = "status-partial"
        elif expected_state == "online":
            overall_text = "Offline (uventet)"
            status_class = "status-offline"
        else:
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

    try:
        uptime_seconds = int(str(uptime_payload or "0"))
    except ValueError:
        uptime_seconds = 0
    jobs = combined_device_jobs(device_id, device)
    active_jobs = [job for job in jobs if active_job_status(str(job.get("status", "")).lower())]
    latest_job = jobs[0] if jobs else {}

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
        "hostname": hostname_payload or "",
        "uptime_seconds": uptime_seconds,
        "uptime_text": format_duration(uptime_seconds) if uptime_seconds >= 0 else "Ukendt",
        "boot_time": boot_time_payload or "",
        "expected_state": expected_state,
        "expected_state_reason": str(get_device_runtime(device_id).get("expected_state_reason", "")),
        "jobs": jobs,
        "active_jobs": active_jobs,
        "latest_job": latest_job,
        "wol_active": wol_job_active(device_id),
    }


def build_remote_device_statuses() -> dict:
    result = {}
    now = time.time()
    for device_id, device in REMOTE_DEVICES.items():
        with DEVICE_STATUS_CACHE_LOCK:
            cached = DEVICE_STATUS_CACHE.get(device_id)
            cached = dict(cached) if cached else None
        if cached and now - float(cached.get("cached_at", 0)) <= STATUS_MONITOR_INTERVAL_SECONDS * 2:
            cached.pop("cached_at", None)
            cached["wol_active"] = wol_job_active(device_id)
            cached["jobs"] = combined_device_jobs(device_id, device)
            cached["active_jobs"] = [job for job in cached["jobs"] if active_job_status(str(job.get("status", "")).lower())]
            cached["latest_job"] = cached["jobs"][0] if cached["jobs"] else {}
            cached["expected_state"] = get_expected_state(device_id, device)
            cached["expected_state_reason"] = str(get_device_runtime(device_id).get("expected_state_reason", ""))
            result[device_id] = cached
        else:
            result[device_id] = evaluate_remote_device_status(device_id, device)
    return result



def device_mqtt_online(device: dict) -> bool:
    status_cfg = device.get("status", {})
    power_topic = str(status_cfg.get("power_topic", "")).strip()
    if not power_topic or not get_mqtt_connected():
        return False
    payload, age = get_mqtt_payload_and_age(power_topic)
    return bool(
        payload
        and payload.strip().lower() == "online"
        and age is not None
        and age <= MQTT_ONLINE_TTL_SECONDS
    )


def device_mqtt_offline(device: dict) -> bool:
    status_cfg = device.get("status", {})
    power_topic = str(status_cfg.get("power_topic", "")).strip()
    if not power_topic or not get_mqtt_connected():
        return False
    payload, age = get_mqtt_payload_and_age(power_topic)
    return bool(
        payload
        and payload.strip().lower() == "offline"
        and age is not None
        and age <= MQTT_ONLINE_TTL_SECONDS
    )


def wol_job_active(device_id: str) -> bool:
    """Return whether the action module has an active WoL job."""
    return ACTION_MANAGER.wol_job_active(device_id)











def cancel_power_confirmation(device_id: str) -> None:
    """Cancel an outstanding shutdown/reboot confirmation worker."""
    ACTION_MANAGER.cancel_power_confirmation(device_id)



def power_confirmation_worker(device_id: str, command: str, job_id: str, confirmation: str) -> None:
    """Delegate shutdown/reboot confirmation to the action module."""
    ACTION_MANAGER.power_confirmation_worker(device_id, command, job_id, confirmation)



def execute_remote_action(device_id: str, command: str, job_id: str = "", source: str = "Homelab Panel") -> tuple[bool, str]:
    """Execute one configured remote action through the action module."""
    return ACTION_MANAGER.execute_remote_action(device_id, command, job_id=job_id, source=source)



def execute_and_record_remote_action(
    device_id: str,
    command: str,
    source: str,
) -> tuple[bool, str]:
    device = REMOTE_DEVICES.get(device_id)
    if not device:
        return False, f"Ukendt remote enhed: {device_id}"

    # WoL has its own asynchronous retry/confirmation job and records every
    # attempt/result itself.
    if command == "power_on":
        ok, message = execute_remote_action(device_id, command, source=source)
        event_epoch = time.time()
        event_timestamp = datetime.now().isoformat(timespec="seconds")
        record_panel_action(device_id, command, ok, message, source, event_epoch, event_timestamp)
        return ok, message

    if command == "cancel_wol":
        ok, message = execute_remote_action(device_id, command, source=source)
        event_epoch = time.time()
        event_timestamp = datetime.now().isoformat(timespec="seconds")
        record_panel_action(device_id, command, ok, message, source, event_epoch, event_timestamp)
        return ok, message

    command_aliases = {"shutdown": "shutdown_delay", "reboot": "reboot_delay"}
    resolved_command = command_aliases.get(command, command)
    button = get_device_button(device, resolved_command)
    category = get_device_category(device, resolved_command)
    job_id = f"panel-{uuid.uuid4().hex[:10]}"
    now = datetime.now().isoformat(timespec="seconds")
    update_panel_job(
        device_id,
        job_id,
        command=resolved_command,
        label=str((button or {}).get("label") or resolved_command),
        category=category,
        source=source,
        status="queued",
        queued_at=now,
        started_at="",
        finished_at="",
        updated_at=now,
        message="Queued for MQTT dispatch",
    )

    ok, message = execute_remote_action(device_id, resolved_command, job_id=job_id, source=source)
    event_epoch = time.time()
    event_timestamp = datetime.now().isoformat(timespec="seconds")
    record_panel_action(device_id, resolved_command, ok, message, source, event_epoch, event_timestamp)

    status = "sent" if ok else "failure"
    update_panel_job(
        device_id,
        job_id,
        status=status,
        started_at=event_timestamp,
        updated_at=event_timestamp,
        finished_at="" if ok else event_timestamp,
        message=message,
    )
    record_device_event(
        device_id,
        category=category,
        event_type="job_dispatch",
        command=resolved_command,
        result=status,
        message=message,
        source=source,
        severity="info" if ok else "error",
        timestamp=event_timestamp,
        job_id=job_id,
        job_status=status,
    )

    if not ok:
        return False, message

    inferred_confirmation = {
        "shutdown_delay": "shutdown",
        "shutdown": "shutdown",
        "reboot_delay": "reboot",
        "reboot": "reboot",
    }.get(resolved_command, "none")
    confirmation = str((button or {}).get("confirmation") or inferred_confirmation).lower()
    if resolved_command in {"shutdown_cancel", "reboot_cancel"}:
        cancel_power_confirmation(device_id)
        set_expected_state(device_id, "online", "Power cancellation command sent")
    elif confirmation == "shutdown":
        set_expected_state(device_id, "offline_pending", "Shutdown requested")
        threading.Thread(
            target=power_confirmation_worker,
            args=(device_id, resolved_command, job_id, "shutdown"),
            daemon=True,
        ).start()
    elif confirmation == "reboot":
        set_expected_state(device_id, "restarting", "Reboot requested")
        threading.Thread(
            target=power_confirmation_worker,
            args=(device_id, resolved_command, job_id, "reboot"),
            daemon=True,
        ).start()

    return True, message


def process_panel_control_message(payload: str) -> None:
    try:
        command_data = json.loads(payload)
    except json.JSONDecodeError as exc:
        print(f"Homelab-panel control rejected: invalid JSON: {exc}", flush=True)
        return

    if not isinstance(command_data, dict):
        print("Homelab-panel control rejected: payload must be a JSON object", flush=True)
        return

    command = str(command_data.get("command", "")).strip()
    target = str(command_data.get("target", "remote")).strip()
    if not command or target not in {"remote", "local"}:
        print("Homelab-panel control rejected: command and a valid target are required", flush=True)
        return

    device_id = str(command_data.get("device_id", "")).strip()
    if target == "local":
        # Require an unambiguous local envelope; never fall back to local
        # execution for a missing/unknown remote device.
        if "device_id" in command_data:
            print("Homelab-panel control rejected: local target must not include device_id", flush=True)
            return
        ok, message = execute_local_action(command)
    else:
        if not device_id:
            print("Homelab-panel control rejected: device_id is required for remote commands", flush=True)
            return
        panel_control_topic = MQTT_CONFIG.get("panel_control_topic", "").strip() or "panel-control"
        ok, message = execute_and_record_remote_action(
            device_id,
            command,
            f"MQTT {panel_control_topic}",
        )
    outcome = "success" if ok else "failure"
    print(
        f"Homelab-panel control {outcome}: target={target} device_id={device_id} command={command} message={message}",
        flush=True,
    )



def process_remote_jobs_message(topic: str, payload: str) -> None:
    device_match = None
    for device_id, device in REMOTE_DEVICES.items():
        if get_jobs_topic_for_status_cfg(device.get("status", {})) == topic:
            device_match = (device_id, device)
            break
    if not device_match:
        return

    device_id, device = device_match
    try:
        jobs = json.loads(payload)
    except (json.JSONDecodeError, TypeError, ValueError):
        record_device_event(
            device_id,
            category="mqtt",
            event_type="invalid_job_payload",
            result="failure",
            message=f"Invalid JSON on remote jobs topic {topic}",
            severity="error",
        )
        return
    if not isinstance(jobs, list):
        return

    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_id = str(job.get("job_id", "")).strip()
        status = str(job.get("status", "")).strip().lower()
        updated_at = str(job.get("updated_at") or job.get("finished_at") or job.get("started_at") or job.get("queued_at") or "")
        if not job_id or not status or not updated_at:
            continue
        signature = (device_id, job_id, status, updated_at)
        if signature in REMOTE_JOB_EVENT_SEEN or history_contains_event(device_id, job_id, status, updated_at):
            REMOTE_JOB_EVENT_SEEN.add(signature)
            continue
        REMOTE_JOB_EVENT_SEEN.add(signature)

        command = str(job.get("command", ""))
        category = str(job.get("category") or get_device_category(device, command) or "command").lower()
        message = str(job.get("message") or status)
        severity = "error" if status == "failure" else "info"
        runtime = job.get("runtime_seconds")
        record_device_event(
            device_id,
            category=category,
            event_type="job_status",
            command=command,
            result=status,
            message=message,
            source="Homelab Control",
            severity=severity,
            timestamp=updated_at,
            job_id=job_id,
            job_status=status,
            duration_seconds=runtime,
            queued_at=job.get("queued_at", ""),
            started_at=job.get("started_at", ""),
            finished_at=job.get("finished_at", ""),
        )

        # If the panel created the same job ID using json_jobs=True, merge the
        # real remote result into the panel job rather than treating MQTT publish
        # success as script success.
        if any(str(item.get("job_id")) == job_id for item in get_panel_jobs(device_id)):
            update_panel_job(
                device_id,
                job_id,
                status=status,
                updated_at=updated_at,
                started_at=str(job.get("started_at") or ""),
                finished_at=str(job.get("finished_at") or ""),
                runtime_seconds=runtime,
                message=message,
                remote_result=True,
            )


def handle_boot_id_message(topic: str, payload: str) -> None:
    for device_id, device in REMOTE_DEVICES.items():
        status_cfg = device.get("status", {})
        if get_boot_id_topic_for_status_cfg(status_cfg) != topic:
            continue
        boot_id = payload.strip()
        if not boot_id:
            return
        runtime = get_device_runtime(device_id)
        previous = str(runtime.get("boot_id", ""))
        if previous and previous != boot_id:
            clear_panel_action_state(device_id)
            record_device_event(
                device_id,
                category="availability",
                event_type="boot",
                command="boot",
                result="success",
                message="New Linux boot session detected; current command card cleared",
                source="Homelab Panel",
                boot_id=boot_id,
                previous_boot_id=previous,
            )
        update_device_runtime(device_id, boot_id=boot_id)
        return


def format_duration(seconds) -> str:
    try:
        seconds = int(float(seconds))
    except (TypeError, ValueError):
        return ""
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def publish_mqtt_direct(topic: str, payload: str, qos: int = 1, retain: bool = True) -> bool:
    """Publish telemetry/discovery through the connected MQTT runtime client."""
    return MQTT_RUNTIME.publish_direct(topic, payload, qos=qos, retain=retain)



def home_assistant_enabled() -> bool:
    """Return whether the Home Assistant integration is enabled."""
    return HOME_ASSISTANT.enabled()









def publish_home_assistant_discovery() -> None:
    """Publish Home Assistant MQTT discovery via the integration module."""
    HOME_ASSISTANT.publish_discovery()



def publish_home_assistant_snapshot() -> None:
    """Republish HA availability/discovery and cached device states."""
    HOME_ASSISTANT.publish_snapshot()



def publish_home_assistant_state(device_id: str, device: dict, status: dict) -> None:
    """Publish one Home Assistant device state via the integration module."""
    HOME_ASSISTANT.publish_state(device_id, device, status)



def monitor_device_transition(device_id: str, device: dict, status: dict) -> None:
    runtime = get_device_runtime(device_id)
    previous = str(runtime.get("overall", ""))
    previous_changed = str(runtime.get("overall_changed_at", ""))
    current = str(status.get("overall", "offline"))
    now = datetime.now().isoformat(timespec="seconds")

    if not previous:
        update_device_runtime(
            device_id,
            overall=current,
            overall_changed_at=now,
            ping_ok=bool(status.get("ping_ok")),
            mqtt_online_ok=bool(status.get("mqtt_online_ok")),
        )
        return

    if previous != current:
        duration_seconds = None
        try:
            duration_seconds = max(0, int(datetime.now().timestamp() - datetime.fromisoformat(previous_changed).timestamp()))
        except (ValueError, TypeError):
            pass
        expected = get_expected_state(device_id, device)
        severity = "info"
        if current == "offline" and expected == "online":
            severity = "error"
        message = f"Device state changed: {previous} -> {current}"
        if duration_seconds is not None:
            message += f" after {format_duration(duration_seconds)}"
        if current == "offline" and expected == "offline":
            message += " (expected offline)"
        elif current == "offline" and expected in {"starting", "restarting"}:
            message += f" (expected while {expected})"
        elif current == "offline" and expected == "online":
            message += " (unexpected offline)"
        record_device_event(
            device_id,
            category="availability",
            event_type="state_transition",
            result=current,
            message=message,
            severity=severity,
            previous_state=previous,
            current_state=current,
            duration_seconds=duration_seconds,
            expected_state=expected,
        )
        update_device_runtime(device_id, overall=current, overall_changed_at=now)

    ping_value = bool(status.get("ping_ok"))
    mqtt_value = bool(status.get("mqtt_online_ok"))
    if runtime.get("ping_ok") != ping_value or runtime.get("mqtt_online_ok") != mqtt_value:
        update_device_runtime(device_id, ping_ok=ping_value, mqtt_online_ok=mqtt_value)


def status_monitor_loop() -> None:
    while True:
        try:
            for device_id, device in REMOTE_DEVICES.items():
                status = evaluate_remote_device_status(device_id, device)
                with DEVICE_STATUS_CACHE_LOCK:
                    DEVICE_STATUS_CACHE[device_id] = {**status, "cached_at": time.time()}
                monitor_device_transition(device_id, device, status)
                publish_home_assistant_state(device_id, device, status)
        except Exception as exc:
            print(f"Status monitor error: {exc}", flush=True)
        time.sleep(STATUS_MONITOR_INTERVAL_SECONDS)


def start_status_monitor() -> None:
    global BACKGROUND_MONITOR_STARTED
    with BACKGROUND_MONITOR_LOCK:
        if BACKGROUND_MONITOR_STARTED:
            return
        BACKGROUND_MONITOR_STARTED = True
        threading.Thread(target=status_monitor_loop, daemon=True).start()


def build_mqtt_diagnostics() -> dict:
    """Build MQTT diagnostics from the runtime module."""
    return MQTT_RUNTIME.build_diagnostics()



def on_connect_compat(*args):
    """Compatibility callback delegating broker connect handling to the MQTT module."""
    return MQTT_RUNTIME.on_connect(*args)



def on_disconnect_compat(*args):
    """Compatibility callback delegating disconnect handling to the MQTT module."""
    return MQTT_RUNTIME.on_disconnect(*args)



def on_message_compat(client, userdata, msg):
    """Compatibility callback delegating incoming messages to the MQTT module."""
    return MQTT_RUNTIME.on_message(client, userdata, msg)



def start_mqtt_listener() -> None:
    """Start the long-running MQTT runtime and status monitor."""
    MQTT_RUNTIME.start()



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
        home_assistant_enabled=home_assistant_enabled(),
        resolve_confirmation_text=resolve_confirmation_text,
    )


@app.route("/history/<device_id>")
def device_history(device_id: str):
    if not check_token():
        return "Forbudt", 403

    device = REMOTE_DEVICES.get(device_id)
    if not device:
        return "Ukendt remote enhed", 404

    all_history = get_device_history(device_id, device)
    selected_filter = str(request.args.get("filter", "all")).strip().lower() or "all"
    if selected_filter == "errors":
        history = [entry for entry in all_history if entry.get("severity") == "error" or str(entry.get("result", "")).lower() in {"fejl", "failure"}]
    elif selected_filter == "all":
        history = all_history
    else:
        history = [entry for entry in all_history if str(entry.get("category", "")).lower() == selected_filter]
    categories = sorted({str(entry.get("category", "other")).lower() for entry in all_history if entry.get("category")})

    return render_template(
        "history.html",
        device_id=device_id,
        device=device,
        history=history,
        history_count_total=len(all_history),
        categories=categories,
        selected_filter=selected_filter,
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


@app.post("/wol-cancel/<device_id>")
def wol_cancel(device_id: str):
    if not check_token():
        return "Forbudt", 403
    device = REMOTE_DEVICES.get(device_id)
    if not device:
        flash("Ukendt WoL-enhed.", "error")
        return redirect(url_for("index", token=request.args.get("token", "")))
    ok, msg = execute_and_record_remote_action(device_id, "cancel_wol", "Webpanel")
    flash(msg, "success" if ok else "error")
    return redirect(url_for("index", token=request.args.get("token", "")))


@app.route("/mqtt-diagnostics")
def mqtt_diagnostics():
    if not check_token():
        return "Forbudt", 403
    return render_template(
        "mqtt_diagnostics.html",
        diagnostics=build_mqtt_diagnostics(),
        remote_devices=REMOTE_DEVICES,
        token=request.args.get("token", ""),
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        web_auth_enabled=web_auth_enabled(),
        logged_in_username=session.get("username", ""),
    )


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

    ok, msg = execute_local_action(button_id)
    flash(msg, "success" if ok else "error")

    return redirect(url_for("index", token=request.args.get("token", "")))


if __name__ == "__main__":
    validate_web_auth_config()
    start_mqtt_listener()
    app.run(host="0.0.0.0", port=5000)
else:
    validate_web_auth_config()
    start_mqtt_listener()
