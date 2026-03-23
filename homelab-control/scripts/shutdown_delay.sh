#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
source "${BASE_DIR}/homelab_control_lib.sh"

CMD='shutdown -h +1 "Shutdown requested from Homelab Control Panel"'

set_shutdown_pending
write_command_status "${CMD}" "running" "Attempting to schedule shutdown in 1 minute"

if shutdown -h +1 "Shutdown requested from Homelab Control Panel"; then
    write_command_status "${CMD}" "success" "Shutdown scheduled in 1 minute"
    echo "Shutdown scheduled in 1 minute"
else
    set_idle
    write_command_status "${CMD}" "failure" "Could not schedule shutdown"
    echo "Could not schedule shutdown" >&2
    exit 1
fi
