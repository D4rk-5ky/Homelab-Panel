#!/bin/bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CONTROL_DIR="${PROJECT_ROOT}/homelab-control"
CONTROL_LIB="${CONTROL_DIR}/homelab_control_lib.sh"
CONTROL_CONFIG="${CONTROL_DIR}/config.json"
CONTROL_STATUS_ENABLED=0

# The remote command listener runs as root. When the control agent is configured
# on this host, reuse its existing status/MQTT functions so shared action scripts
# keep the same remote status behavior as before.
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
