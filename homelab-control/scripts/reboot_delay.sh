#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
source "${BASE_DIR}/homelab_control_lib.sh"

CMD='shutdown -r +1 "Reboot requested from Homelab Control Panel"'

set_reboot_pending
write_command_status "${CMD}" "running" "Attempting to schedule reboot in 1 minute"

if shutdown -r +1 "Reboot requested from Homelab Control Panel"; then
    write_command_status "${CMD}" "success" "Reboot scheduled in 1 minute"
    echo "Reboot scheduled in 1 minute"
else
    set_idle
    write_command_status "${CMD}" "failure" "Could not schedule reboot"
    echo "Could not schedule reboot" >&2
    exit 1
fi
