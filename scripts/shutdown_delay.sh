#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/homelab_action_common.sh"

CMD='shutdown -h +1 "Shutdown requested from Homelab Control Panel"'

if [[ "${CONTROL_STATUS_ENABLED}" -eq 1 ]]; then
    set_shutdown_pending
    write_command_status "${CMD}" "running" "Attempting to schedule shutdown in 1 minute"
fi

if run_shutdown_command -h +1 "Shutdown requested from Homelab Control Panel"; then
    if [[ "${CONTROL_STATUS_ENABLED}" -eq 1 ]]; then
        write_command_status "${CMD}" "success" "Shutdown scheduled in 1 minute"
    fi
    echo "Shutdown scheduled in 1 minute"
else
    if [[ "${CONTROL_STATUS_ENABLED}" -eq 1 ]]; then
        set_idle
        write_command_status "${CMD}" "failure" "Could not schedule shutdown"
    fi
    echo "Could not schedule shutdown" >&2
    exit 1
fi
