#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/homelab_action_common.sh"

CMD='shutdown -r +1 "Reboot requested from Homelab Control Panel"'

if [[ "${CONTROL_STATUS_ENABLED}" -eq 1 ]]; then
    set_reboot_pending
    write_command_status "${CMD}" "running" "Attempting to schedule reboot in 1 minute"
fi

if run_shutdown_command -r +1 "Reboot requested from Homelab Control Panel"; then
    if [[ "${CONTROL_STATUS_ENABLED}" -eq 1 ]]; then
        write_command_status "${CMD}" "success" "Reboot scheduled in 1 minute"
    fi
    echo "Reboot scheduled in 1 minute"
else
    if [[ "${CONTROL_STATUS_ENABLED}" -eq 1 ]]; then
        set_idle
        write_command_status "${CMD}" "failure" "Could not schedule reboot"
    fi
    echo "Could not schedule reboot" >&2
    exit 1
fi
