#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
CONTROL_DIR="${PROJECT_ROOT}/homelab-control"
CONTROL_LIB="${CONTROL_DIR}/modules/homelab_control_lib.sh"
CONTROL_CONFIG="${CONTROL_DIR}/configs/config.json"
CONTROL_STATUS_ENABLED=0

power_script_cli() {
    local description="$1"
    shift
    [[ "$#" -gt 0 ]] || return 0
    if [[ "$#" -eq 1 ]]; then
        case "$1" in
            -h|--help)
                printf 'Usage: %s [--help | --version]\n\n%s\n\n' "${0##*/}" "${description}"
                printf '%s\n' 'Options:' '  -h, --help  Show this help and exit without taking action.' '  --version   Show the packaged Homelab Panel version and exit.' '' 'Run without arguments to perform the action. No dry-run or delay override is provided.'
                exit 0
                ;;
            --version)
                printf '%s ' "${0##*/}"
                cat "${PROJECT_ROOT}/VERSION"
                exit 0
                ;;
        esac
    fi
    printf 'Error: unsupported arguments. Use %s --help.\n' "${0##*/}" >&2
    exit 2
}

load_control_status() {
    # Keep private config/status integration after inspection-option parsing.
    if [[ "$(id -u)" -eq 0 && -f "${CONTROL_LIB}" && -f "${CONTROL_CONFIG}" ]]; then
        # shellcheck source=/dev/null
        source "${CONTROL_LIB}"
        CONTROL_STATUS_ENABLED=1
    fi
}

run_shutdown_command() {
    if [[ "$(id -u)" -eq 0 ]]; then
        shutdown "$@"
    else
        sudo shutdown "$@"
    fi
}
