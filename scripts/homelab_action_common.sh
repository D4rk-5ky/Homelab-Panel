#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
CONTROL_DIR="${PROJECT_ROOT}/homelab-control"
CONTROL_LIB="${CONTROL_DIR}/modules/homelab_control_lib.sh"
CONTROL_CONFIG="${CONTROL_DIR}/configs/config.json"
VERSION_FILE="${PROJECT_ROOT}/VERSION"
CONTROL_STATUS_ENABLED=0

project_version() {
    if [[ -r "${VERSION_FILE}" ]]; then
        tr -d '\r\n' < "${VERSION_FILE}"
    else
        printf '%s' 'unknown'
    fi
}

action_cli_description() {
    case "$(basename -- "$0")" in
        shutdown_delay.sh) printf '%s' 'Schedule a Linux shutdown in one minute.' ;;
        shutdown_cancel.sh) printf '%s' 'Cancel a scheduled Linux shutdown or reboot.' ;;
        reboot_delay.sh) printf '%s' 'Schedule a Linux reboot in one minute.' ;;
        reboot_cancel.sh) printf '%s' 'Cancel a scheduled Linux shutdown or reboot.' ;;
        homelab_action_common.sh) printf '%s' 'Shared Homelab Panel power-action helper; normally sourced by another script.' ;;
        *) printf '%s' 'Homelab Panel power-action script.' ;;
    esac
}

show_action_cli_help() {
    local script_name
    script_name="$(basename -- "$0")"
    printf 'Usage: %s [--help | --version]\n\n' "${script_name}"
    printf '%s\n\n' "$(action_cli_description)"
    if [[ "$(basename -- "$0")" == "homelab_action_common.sh" ]]; then
        printf 'This helper has no standalone operational mode.\n'
    else
        printf 'Run with no arguments to perform the configured action.\n'
    fi
    printf '  -h, --help     show this help and exit without performing an action\n'
    printf '      --version  show the Homelab Panel project version and exit\n'
}

handle_action_cli_args() {
    if [[ "$#" -eq 0 ]]; then
        if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
            printf 'homelab_action_common.sh is a sourced helper and has no standalone operational mode.\n' >&2
            exit 2
        fi
        return 0
    fi
    if [[ "$#" -ne 1 ]]; then
        printf 'Error: this action accepts no operational arguments.\n' >&2
        show_action_cli_help >&2
        exit 2
    fi
    case "$1" in
        -h|--help)
            show_action_cli_help
            exit 0
            ;;
        --version)
            printf '%s %s\n' "$(basename -- "$0")" "$(project_version)"
            exit 0
            ;;
        *)
            printf 'Error: unknown argument: %s\n' "$1" >&2
            show_action_cli_help >&2
            exit 2
            ;;
    esac
}

# Parse information-only flags before loading optional remote-agent configuration.
# This keeps --help/--version safe even when the host is not configured.
handle_action_cli_args "$@"

# The remote command listener runs as root. When the control agent is configured
# on this host, reuse its status/MQTT functions so these action scripts also
# publish the remote agent status/history updates.
if [[ "$(id -u)" -eq 0 && -f "${CONTROL_LIB}" && -f "${CONTROL_CONFIG}" ]]; then
    # shellcheck source=/dev/null
    source "${CONTROL_LIB}"
    CONTROL_STATUS_ENABLED=1
fi

run_shutdown_command() {
    if [[ "$(id -u)" -eq 0 ]]; then
        shutdown "$@"
    else
        sudo shutdown "$@"
    fi
}
