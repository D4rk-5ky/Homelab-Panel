#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared_modules.version import build_info_parser

if __name__ == "__main__":
    build_info_parser(
        'Run the Homelab Control MQTT command listener using the allow-list in homelab-control/configs/config.json.'
    ).parse_args()

from shared_modules.mqtt import MqttClient
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
CONFIG_FILE = os.path.join(BASE_DIR, "configs", "config.json")
STATE_DIR = os.path.join(BASE_DIR, "state")
JOBS_FILE = os.path.join(STATE_DIR, "jobs.json")


with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)


CLIENT_ID = CONFIG["client_ids"]["command_listener"]
TOPIC_CONTROL = CONFIG["topics"]["control_power"]
COMMAND_MAP = CONFIG["commands"]
SHARED_POWER_SCRIPTS = {
    "shutdown_delay.sh",
    "shutdown_cancel.sh",
    "reboot_delay.sh",
    "reboot_cancel.sh",
}
MAX_PARALLEL_JOBS = max(1, int(CONFIG["timing"]["max_parallel_jobs"]))
JOB_HISTORY_MAX_ENTRIES = max(1, int(CONFIG["timing"]["job_history_max_entries"]))

JOBS_LOCK = threading.Lock()
JOB_SEMAPHORE = threading.Semaphore(MAX_PARALLEL_JOBS)
MQTT_CLIENT = None


TOPIC_JOBS = CONFIG["topics"]["status_jobs"]


def timestamp_now() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def normalize_command_spec(command: str, raw_spec) -> dict | None:
    if not isinstance(raw_spec, dict):
        return None
    spec = dict(raw_spec)
    script = str(spec.get("script", "")).strip()
    if not script:
        return None
    spec["script"] = script
    spec["label"] = str(spec.get("label") or command)
    spec["category"] = str(spec.get("category") or "command").strip().lower()
    try:
        spec["timeout"] = max(1, int(spec.get("timeout", 60)))
    except (TypeError, ValueError):
        spec["timeout"] = 60
    return spec


def resolve_script_path(script_name: str) -> str | None:
    # Bundled shutdown/reboot helpers live under PROJECT_ROOT/scripts. Other
    # configured job scripts resolve from PROJECT_ROOT. MQTT selects only an
    # allow-listed command ID and never supplies a script path directly.
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
    MQTT_CLIENT.publish(TOPIC_JOBS, payload, qos=1, retain=True, wait_timeout=5)


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
                status="timed_out",
                finished_at=finished_at,
                updated_at=finished_at,
                message=(
                    f"Command timed out after {int(spec.get('timeout', 60))} seconds; "
                    "job is no longer considered active"
                ),
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


def queue_command(command: str, requested_job_id: str, source: str) -> str | None:
    raw_spec = COMMAND_MAP.get(command)
    spec = normalize_command_spec(command, raw_spec)
    if not spec:
        print(f"Unknown command: {command}", flush=True)
        return None

    job_id = "".join(ch for ch in requested_job_id if ch.isalnum() or ch in "-_")[:64]
    if not job_id:
        print("Rejected command without a valid job_id", flush=True)
        return None
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


def parse_control_payload(payload: str) -> tuple[str, str, str] | None:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    command = str(data.get("command", "")).strip()
    job_id = str(data.get("job_id", "")).strip()
    source = str(data.get("source", "")).strip()
    if not command or not job_id or not source:
        return None
    return command, job_id, source


def on_connect() -> None:
    print(f"Subscribed to {TOPIC_CONTROL}", flush=True)
    publish_jobs()


def on_message(topic: str, payload: str, retain: bool, qos: int) -> None:
    parsed = parse_control_payload(payload)
    if parsed is None:
        print("Rejected invalid command payload; expected JSON command/job_id/source", flush=True)
        return
    command, requested_job_id, source = parsed
    print(f"Received command: {command}", flush=True)

    job_id = queue_command(command, requested_job_id, source)
    if job_id:
        print(f"Queued command={command} job_id={job_id}", flush=True)


def main() -> int:
    global MQTT_CLIENT
    os.makedirs(STATE_DIR, exist_ok=True)
    recover_interrupted_jobs()
    MQTT_CLIENT = MqttClient(
        CONFIG["mqtt"],
        client_id=CLIENT_ID,
        subscriptions=[(TOPIC_CONTROL, 1)],
        on_connect=on_connect,
        on_message=on_message,
    )
    MQTT_CLIENT.start(mode="forever")
    return 0


if __name__ == "__main__":
    sys.exit(main())
