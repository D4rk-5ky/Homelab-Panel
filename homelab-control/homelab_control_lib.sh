#!/bin/bash
set -euo pipefail

BASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${BASE_DIR}/state"
LOG_DIR="${BASE_DIR}/logs"
CONFIG_FILE="${BASE_DIR}/config.json"

ACTION_FILE="${STATE_DIR}/action"
LAST_COMMAND_FILE="${STATE_DIR}/last_command"
LAST_RESULT_FILE="${STATE_DIR}/last_result"
LAST_MESSAGE_FILE="${STATE_DIR}/last_message"
LAST_UPDATED_FILE="${STATE_DIR}/last_updated"
HISTORY_FILE="${STATE_DIR}/history.json"
HISTORY_LOCK_FILE="${STATE_DIR}/history.lock"
COMMAND_LOG_FILE="${LOG_DIR}/commands.log"

json_get() {
    local key="$1"
    python3 - "$CONFIG_FILE" "$key" <<'PY'
import json, sys
config_path = sys.argv[1]
key_path = sys.argv[2].split(".")
with open(config_path, "r", encoding="utf-8") as f:
    data = json.load(f)
for part in key_path:
    data = data[part]
print(data)
PY
}

json_get_optional() {
    local key="$1"
    local default_value="${2:-}"
    python3 - "$CONFIG_FILE" "$key" "$default_value" <<'PY'
import json, sys
config_path = sys.argv[1]
key_path = sys.argv[2].split(".")
default = sys.argv[3]
with open(config_path, "r", encoding="utf-8") as f:
    data = json.load(f)
try:
    for part in key_path:
        data = data[part]
except (KeyError, TypeError):
    print(default)
else:
    print(data)
PY
}

TOPIC_POWER="$(json_get topics.status_power)"
TOPIC_ACTION="$(json_get topics.status_action)"
TOPIC_LAST_COMMAND="$(json_get topics.status_last_command)"
TOPIC_LAST_RESULT="$(json_get topics.status_last_result)"
TOPIC_LAST_MESSAGE="$(json_get topics.status_last_message)"
TOPIC_LAST_UPDATED="$(json_get topics.status_last_updated)"
TOPIC_HISTORY="$(json_get_optional topics.status_history '')"
HISTORY_MAX_ENTRIES="$(json_get_optional timing.history_max_entries '100')"

# Compatibility with older active configs: derive aoostar/status/history from
# aoostar/status/last_message when status_history has not yet been added.
if [[ -z "${TOPIC_HISTORY}" && "${TOPIC_LAST_MESSAGE}" == */last_message ]]; then
    TOPIC_HISTORY="${TOPIC_LAST_MESSAGE%/last_message}/history"
fi

if ! [[ "${HISTORY_MAX_ENTRIES}" =~ ^[0-9]+$ ]] || [[ "${HISTORY_MAX_ENTRIES}" -lt 1 ]]; then
    HISTORY_MAX_ENTRIES=100
fi

ensure_dirs() {
    mkdir -p "${STATE_DIR}"
    mkdir -p "${LOG_DIR}"
}

timestamp_now() {
    date '+%Y-%m-%dT%H:%M:%S'
}

mqtt_pub() {
    local topic="$1"
    local payload="$2"

    [[ -n "${topic}" ]] || return 0

    # Keep payload bytes on stdin and credentials in the existing JSON config.
    # The shared Python helper owns all MQTT transport and reports failure via rc.
    printf '%s' "${payload}" | python3 "${BASE_DIR}/../homelab_mqtt.py" \
        --config "${CONFIG_FILE}" --topic "${topic}" --qos 1 --retain > /dev/null
}

write_action() {
    local value="$1"
    ensure_dirs
    printf '%s\n' "${value}" > "${ACTION_FILE}"
}

append_command_history() {
    local command="$1"
    local result="$2"
    local message="$3"
    local timestamp="$4"

    ensure_dirs
    python3 - \
        "${HISTORY_FILE}" \
        "${HISTORY_LOCK_FILE}" \
        "${HISTORY_MAX_ENTRIES}" \
        "${command}" \
        "${result}" \
        "${message}" \
        "${timestamp}" <<'PY'
import fcntl
import json
import os
import sys

history_file, lock_file, max_entries, command, result, message, timestamp = sys.argv[1:]
try:
    max_entries = max(1, int(max_entries))
except ValueError:
    max_entries = 100

os.makedirs(os.path.dirname(history_file), exist_ok=True)
with open(lock_file, "a+", encoding="utf-8") as lock:
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
    try:
        with open(history_file, "r", encoding="utf-8") as f:
            history = json.load(f)
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
        history = []

    if not isinstance(history, list):
        history = []

    command_lower = command.lower()
    if "shutdown" in command_lower or "reboot" in command_lower:
        category = "power"
    elif "backup" in command_lower or "sync" in command_lower:
        category = "backup"
    elif "watchtower" in command_lower or "update" in command_lower:
        category = "maintenance"
    else:
        category = "command"

    history.append({
        "timestamp": timestamp,
        "archived_at": timestamp,
        "command": command,
        "result": result,
        "message": message,
        "source": "Remote enhed",
        "category": category,
        "event_type": "command_status",
        "severity": "error" if result.lower() == "failure" else "info",
    })
    history = history[-max_entries:]

    tmp = history_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, history_file)
PY
}

history_payload() {
    python3 - "${HISTORY_FILE}" <<'PY'
import json, sys
path = sys.argv[1]
try:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
    data = []
if not isinstance(data, list):
    data = []
print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
PY
}

publish_history() {
    [[ -n "${TOPIC_HISTORY}" ]] || return 0
    mqtt_pub "${TOPIC_HISTORY}" "$(history_payload)"
}

write_command_status() {
    local command="$1"
    local result="$2"
    local message="$3"
    local now
    now="$(timestamp_now)"

    ensure_dirs

    printf '%s\n' "${command}" > "${LAST_COMMAND_FILE}"
    printf '%s\n' "${result}" > "${LAST_RESULT_FILE}"
    printf '%s\n' "${message}" > "${LAST_MESSAGE_FILE}"
    printf '%s\n' "${now}" > "${LAST_UPDATED_FILE}"

    printf '%s | command=%s | result=%s | message=%s\n' \
        "${now}" "${command}" "${result}" "${message}" >> "${COMMAND_LOG_FILE}"

    # Every status/message transition is a history event immediately. This
    # preserves intermediate running/success/failure messages that would be
    # overwritten if history were only captured on the next boot.
    append_command_history "${command}" "${result}" "${message}" "${now}"

    mqtt_pub "${TOPIC_LAST_COMMAND}" "${command}"
    mqtt_pub "${TOPIC_LAST_RESULT}" "${result}"
    mqtt_pub "${TOPIC_LAST_MESSAGE}" "${message}"
    mqtt_pub "${TOPIC_LAST_UPDATED}" "${now}"
    publish_history
}

set_idle() {
    write_action "idle"
    mqtt_pub "${TOPIC_ACTION}" "idle"
}

set_shutdown_pending() {
    write_action "shutdown_pending"
    mqtt_pub "${TOPIC_ACTION}" "shutdown_pending"
}

set_reboot_pending() {
    write_action "reboot_pending"
    mqtt_pub "${TOPIC_ACTION}" "reboot_pending"
}
