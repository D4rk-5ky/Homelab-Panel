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

MQTT_HOST="$(json_get mqtt.host)"
MQTT_PORT="$(json_get mqtt.port)"
MQTT_USER="$(json_get mqtt.user)"
MQTT_PASS="$(json_get mqtt.pass)"

TOPIC_POWER="$(json_get topics.status_power)"
TOPIC_ACTION="$(json_get topics.status_action)"
TOPIC_LAST_COMMAND="$(json_get topics.status_last_command)"
TOPIC_LAST_RESULT="$(json_get topics.status_last_result)"
TOPIC_LAST_MESSAGE="$(json_get topics.status_last_message)"
TOPIC_LAST_UPDATED="$(json_get topics.status_last_updated)"

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

    if [[ -n "${MQTT_USER}" ]]; then
        mosquitto_pub \
            -h "${MQTT_HOST}" \
            -p "${MQTT_PORT}" \
            -u "${MQTT_USER}" \
            -P "${MQTT_PASS}" \
            -t "${topic}" \
            -m "${payload}" \
            -r \
            -q 1
    else
        mosquitto_pub \
            -h "${MQTT_HOST}" \
            -p "${MQTT_PORT}" \
            -t "${topic}" \
            -m "${payload}" \
            -r \
            -q 1
    fi
}

write_action() {
    local value="$1"
    ensure_dirs
    printf '%s\n' "${value}" > "${ACTION_FILE}"
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

    mqtt_pub "${TOPIC_LAST_COMMAND}" "${command}"
    mqtt_pub "${TOPIC_LAST_RESULT}" "${result}"
    mqtt_pub "${TOPIC_LAST_MESSAGE}" "${message}"
    mqtt_pub "${TOPIC_LAST_UPDATED}" "${now}"
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
