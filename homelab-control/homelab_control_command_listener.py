#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime

import paho.mqtt.client as mqtt

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
STATE_DIR = os.path.join(BASE_DIR, "state")
JOBS_FILE = os.path.join(STATE_DIR, "jobs.json")


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
COMMAND_MAP = CONFIG.get("commands", {})
SHARED_POWER_SCRIPTS = {
    "shutdown_delay.sh",
    "shutdown_cancel.sh",
    "reboot_delay.sh",
    "reboot_cancel.sh",
}
MAX_PARALLEL_JOBS = max(1, int(CONFIG.get("timing", {}).get("max_parallel_jobs", 4)))
JOB_HISTORY_MAX_ENTRIES = max(1, int(CONFIG.get("timing", {}).get("job_history_max_entries", 100)))

JOBS_LOCK = threading.Lock()
JOB_SEMAPHORE = threading.Semaphore(MAX_PARALLEL_JOBS)
MQTT_CLIENT = None


def derive_jobs_topic() -> str:
    explicit = str(CONFIG.get("topics", {}).get("status_jobs", "")).strip()
    if explicit:
        return explicit

    last_message_topic = str(CONFIG.get("topics", {}).get("status_last_message", "")).strip()
    suffix = "/last_message"
    if last_message_topic.endswith(suffix):
        return last_message_topic[:-len(suffix)] + "/jobs"
    return ""


TOPIC_JOBS = derive_jobs_topic()


def timestamp_now() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def normalize_command_spec(command: str, raw_spec) -> dict | None:
    if isinstance(raw_spec, str):
        script = raw_spec.strip()
        spec = {
            "script": script,
            "label": command,
            "category": "power" if command.startswith(("shutdown", "reboot")) else "command",
            "timeout": 60,
        }
    elif isinstance(raw_spec, dict):
        spec = dict(raw_spec)
        script = str(spec.get("script", "")).strip()
        spec["script"] = script
        spec["label"] = str(spec.get("label") or command)
        spec["category"] = str(spec.get("category") or "command").strip().lower()
        try:
            spec["timeout"] = max(1, int(spec.get("timeout", 60)))
        except (TypeError, ValueError):
            spec["timeout"] = 60
    else:
        return None

    if not spec.get("script"):
        return None
    return spec


def resolve_script_path(script_name: str) -> str | None:
    # The bundled shutdown/reboot helpers are shared Homelab Panel scripts and
    # live under PROJECT_ROOT/scripts. Other configured job scripts are not
    # moved by Homelab Panel; for backward compatibility a plain custom filename
    # continues to resolve from PROJECT_ROOT as it did in 0.0.9. MQTT can only
    # select a command ID from COMMAND_MAP, never supply a script path directly.
    if os.path.basename(script_name) != script_name or script_name in {".", ".."}:
        return None

    if script_name in SHARED_POWER_SCRIPTS:
        candidate = os.path.realpath(os.path.join(SCRIPTS_DIR, script_name))
        if os.path.dirname(candidate) != os.path.realpath(SCRIPTS_DIR):
            return None
        return candidate

    candidate = os.path.realpath(os.path.join(PROJECT_ROOT, script_name))
    if os.path.dirname(candidate) != os.path.realpath(PROJECT_ROOT):
        return None
    return candidate


def load_jobs_unlocked() -> list[dict]:
    try:
        with open(JOBS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def save_jobs_unlocked(jobs: list[dict]) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    jobs = jobs[-JOB_HISTORY_MAX_ENTRIES:]
    tmp = JOBS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, JOBS_FILE)


def update_job(job_id: str, **updates) -> dict:
    with JOBS_LOCK:
        jobs = load_jobs_unlocked()
        job = next((item for item in jobs if str(item.get("job_id")) == job_id), None)
        if job is None:
            job = {"job_id": job_id}
            jobs.append(job)
        job.update(updates)
        save_jobs_unlocked(jobs)
        return dict(job)


def get_jobs_snapshot() -> list[dict]:
    with JOBS_LOCK:
        return [dict(item) for item in load_jobs_unlocked()]


def publish_jobs() -> None:
    if MQTT_CLIENT is None or not TOPIC_JOBS:
        return
    payload = json.dumps(get_jobs_snapshot(), ensure_ascii=False, separators=(",", ":"))
    info = MQTT_CLIENT.publish(TOPIC_JOBS, payload=payload, qos=1, retain=True)
    try:
        info.wait_for_publish(timeout=5)
    except Exception:
        pass


def recover_interrupted_jobs() -> None:
    with JOBS_LOCK:
        jobs = load_jobs_unlocked()
        changed = False
        now = timestamp_now()
        for job in jobs:
            if str(job.get("status", "")).lower() in {"queued", "running", "waiting", "confirming"}:
                job["status"] = "failure"
                job["finished_at"] = now
                job["updated_at"] = now
                job["message"] = "Command listener restarted before this job completed"
                changed = True
        if changed:
            save_jobs_unlocked(jobs)


def clean_output(stdout: str, stderr: str) -> str:
    parts = []
    if stdout and stdout.strip():
        parts.append(stdout.strip())
    if stderr and stderr.strip():
        parts.append(stderr.strip())
    text = " | ".join(parts) or "No output"
    return text[:2000]


def run_job(job_id: str, command: str, spec: dict) -> None:
    queued_at = time.time()
    with JOB_SEMAPHORE:
        started_at_epoch = time.time()
        started_at = timestamp_now()
        update_job(
            job_id,
            status="running",
            started_at=started_at,
            updated_at=started_at,
            message="Command started",
            runtime_seconds=0.0,
        )
        publish_jobs()

        script_path = resolve_script_path(str(spec.get("script", "")))
        if not script_path:
            finished_at = timestamp_now()
            update_job(
                job_id,
                status="failure",
                finished_at=finished_at,
                updated_at=finished_at,
                message="Configured script path is not allowed",
                runtime_seconds=round(time.time() - started_at_epoch, 3),
            )
            publish_jobs()
            print(f"Rejected script path for command {command}", flush=True)
            return

        if not os.path.isfile(script_path):
            finished_at = timestamp_now()
            update_job(
                job_id,
                status="failure",
                finished_at=finished_at,
                updated_at=finished_at,
                message=f"Script not found: {script_path}",
                runtime_seconds=round(time.time() - started_at_epoch, 3),
            )
            publish_jobs()
            print(f"Script not found: {script_path}", flush=True)
            return

        if not os.access(script_path, os.X_OK):
            finished_at = timestamp_now()
            update_job(
                job_id,
                status="failure",
                finished_at=finished_at,
                updated_at=finished_at,
                message=f"Script is not executable: {script_path}",
                runtime_seconds=round(time.time() - started_at_epoch, 3),
            )
            publish_jobs()
            print(f"Script is not executable: {script_path}", flush=True)
            return

        try:
            result = subprocess.run(
                [script_path],
                capture_output=True,
                text=True,
                timeout=int(spec.get("timeout", 60)),
                check=False,
            )
            finished_at = timestamp_now()
            status = "success" if result.returncode == 0 else "failure"
            message = clean_output(result.stdout or "", result.stderr or "")
            update_job(
                job_id,
                status=status,
                finished_at=finished_at,
                updated_at=finished_at,
                message=message,
                return_code=result.returncode,
                runtime_seconds=round(time.time() - started_at_epoch, 3),
            )
            publish_jobs()
            print(
                f"Executed command={command} script={spec['script']} job_id={job_id} rc={result.returncode}",
                flush=True,
            )
            if result.stdout:
                print(result.stdout.strip(), flush=True)
            if result.stderr:
                print(result.stderr.strip(), flush=True)
        except subprocess.TimeoutExpired:
            finished_at = timestamp_now()
            update_job(
                job_id,
                status="failure",
                finished_at=finished_at,
                updated_at=finished_at,
                message=f"Command timed out after {int(spec.get('timeout', 60))} seconds",
                runtime_seconds=round(time.time() - started_at_epoch, 3),
            )
            publish_jobs()
            print(f"Command timed out: {command} job_id={job_id}", flush=True)
        except Exception as exc:
            finished_at = timestamp_now()
            update_job(
                job_id,
                status="failure",
                finished_at=finished_at,
                updated_at=finished_at,
                message=f"Execution failed: {exc}",
                runtime_seconds=round(time.time() - started_at_epoch, 3),
            )
            publish_jobs()
            print(f"Failed to execute {spec['script']}: {exc}", flush=True)


def queue_command(command: str, requested_job_id: str = "", source: str = "MQTT direct") -> str | None:
    raw_spec = COMMAND_MAP.get(command)
    spec = normalize_command_spec(command, raw_spec)
    if not spec:
        print(f"Unknown command: {command}", flush=True)
        return None

    safe_requested = "".join(ch for ch in requested_job_id if ch.isalnum() or ch in "-_")[:64]
    job_id = safe_requested or uuid.uuid4().hex[:12]
    now = timestamp_now()
    update_job(
        job_id,
        command=command,
        label=spec.get("label", command),
        category=spec.get("category", "command"),
        source=source,
        status="queued",
        queued_at=now,
        started_at="",
        finished_at="",
        updated_at=now,
        runtime_seconds=0.0,
        message="Queued",
        script=spec.get("script", ""),
    )
    publish_jobs()
    threading.Thread(target=run_job, args=(job_id, command, spec), daemon=True).start()
    return job_id


def parse_control_payload(payload: str) -> tuple[str, str, str]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return payload.strip(), "", "MQTT direct"

    if not isinstance(data, dict):
        return "", "", "MQTT direct"
    return (
        str(data.get("command", "")).strip(),
        str(data.get("job_id", "")).strip(),
        str(data.get("source", "MQTT JSON")).strip() or "MQTT JSON",
    )


def on_connect(*args):
    client = args[0]
    client.subscribe(TOPIC_CONTROL, qos=1)
    print(f"Subscribed to {TOPIC_CONTROL}", flush=True)
    publish_jobs()


def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8", errors="replace").strip()
    command, requested_job_id, source = parse_control_payload(payload)
    print(f"Received command: {command}", flush=True)

    if not command:
        print("Rejected empty/invalid command payload", flush=True)
        return

    job_id = queue_command(command, requested_job_id, source)
    if job_id:
        print(f"Queued command={command} job_id={job_id}", flush=True)


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
    global MQTT_CLIENT
    os.makedirs(STATE_DIR, exist_ok=True)
    recover_interrupted_jobs()
    client = build_client()
    MQTT_CLIENT = client

    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=MQTT_KEEPALIVE)
    client.loop_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
