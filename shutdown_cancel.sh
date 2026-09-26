#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/homelab_action_common.sh"

CMD='shutdown -c'

if run_shutdown_command -c; then
    if [[ "${CONTROL_STATUS_ENABLED}" -eq 1 ]]; then
        set_idle
        write_command_status "${CMD}" "success" "Shutdown/reboot cancelled"
    fi
    echo "Shutdown/reboot cancelled"
else
    if [[ "${CONTROL_STATUS_ENABLED}" -eq 1 ]]; then
        write_command_status "${CMD}" "failure" "Could not cancel shutdown/reboot"
    fi
    echo "Could not cancel shutdown/reboot" >&2
    exit 1
fi
