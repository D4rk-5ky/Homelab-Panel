#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
source "${BASE_DIR}/homelab_control_lib.sh"

CMD='shutdown -c'

if shutdown -c; then
    set_idle
    write_command_status "${CMD}" "success" "Shutdown/reboot cancelled"
    echo "Shutdown/reboot cancelled"
else
    write_command_status "${CMD}" "failure" "Could not cancel shutdown/reboot"
    echo "Could not cancel shutdown/reboot" >&2
    exit 1
fi
