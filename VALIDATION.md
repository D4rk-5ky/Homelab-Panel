# Homelab Panel 0.0.11 — validation

## Result

The release contains all **24 original files** plus **2 new files**, for **26 files** total. No original paths were deleted or renamed. Seven original files were updated and seventeen remain byte-for-byte identical. Executable bits supplied by the original ZIP are preserved; ordinary files use mode 0644 and executable source files use mode 0755.

Original archive SHA-256: `40edac14bec3d0619c58e23398f4c799d7a84cd7012830488710e485fc2b358e`.

## What changed

- Local webpage action buttons now have Home Assistant MQTT discovery and use the same allow-listed local dispatcher as web requests.
- Remote MQTT and Wake/cancel discovery is retained; Wake labels match the webpage and existing remote IDs remain stable.
- Discovery refreshes on panel MQTT connection/reconnection and Home Assistant's configured online message, including when discovery retention is disabled.
- HA button command messages explicitly have retention disabled. Existing panel retained-command rejection, auth/token checks, script containment and power delays are preserved.
- Added optional `status_topic` and `status_online_payload` settings; discovery remains disabled by default until enabled in the active config.
- Updated current-use documentation, configuration comments, function/command map and version history. Original disclaimer sections are preserved verbatim.

## Checks completed

Environment: macOS, Python 3.13.15, real installed Flask/Jinja/Paho packages; network and subprocess execution mocked during regression tests.

- **11/11 regression tests passed**, run with `python3 -B -m unittest discover -s tests -v`.
- Discovery tests verified all **15 action buttons** in the example config: five remote MQTT commands, three Wake buttons, three cancel-WoL buttons and four local buttons. All 15 remote status sensor entities remain present in the discovery loop.
- Custom local/remote buttons, same-ID separation, script payload selection, existing remote envelopes, HA restart recovery, disabled discovery, empty command topic and custom/disabled HA birth settings were checked.
- Retained local/remote control rejection, unknown/ambiguous local commands, web session/token protection, path traversal, symlink escape, missing and non-executable scripts were checked.
- Real Flask test-client requests rendered dashboard, history, diagnostics and login templates successfully with network/ping mocked.
- Compiled **six Python files** and **four embedded Python blocks** without writing bytecode into the project.
- Passed `bash -n` for **six shell files**, JSON parsing for the remote example and Jinja parsing for **four templates**.
- Verified the function map covers every named Python/test function and shell function; documented browser callbacks separately.
- Verified all **55 distinct panel/device example dictionary keys** are named in the README.
- Compared nine existing execution/auth/WoL/power-confirmation function ASTs against the original: unchanged.
- Every remote-agent/config/service file and shared shell script remains byte-for-byte unchanged.
- Verified version increment from 0.0.10 to 0.0.11 and retained the 0.0.99 → 0.1.0 rollover policy.
- ZIP verification checked exact file names, CRC integrity, file bytes/checksums, executable bits, and the original/final manifest comparison.
- Clean archive contains no `__pycache__`, `.pyc`, `.pyo`, build caches, active configs, runtime state/logs, dependency environments, or temporary files.

The separate `Homelab-Panel-0.0.11-manifest.json` records every packaged file's original/final SHA-256 and status. `Homelab-Panel-0.0.11.zip.sha256` records the final ZIP checksum.

## Not fully tested

- No live Home Assistant instance or broker was connected. Entity appearance and presses in a running Home Assistant installation require deployment verification; published discovery documents and dispatch paths were checked offline against the documented MQTT protocol.
- No real Wake-on-LAN, shutdown, reboot, remote custom jobs, root execution or sudo policy was exercised.
- Linux systemd execution/unit verification was unavailable on this macOS host (`systemd-analyze` is not installed). Supplied units are unchanged and need installation-specific paths/users.
- No browser interaction or visual layout check was run. Templates are unchanged, and Flask/Jinja rendering was checked.
- No app `--help`/dry-run command was executed because the applications and power scripts do not implement those flags; they can start normal work when passed extra arguments.

## Enable the feature

Set `HOME_ASSISTANT_CONFIG["enabled"] = True` in your active `homelab-panel/config.py`, configure the same broker as Home Assistant and restart Homelab Panel. Keep `MQTT_CONFIG["retain"] = False`. The new birth-topic settings use defaults when absent from an existing config. Local buttons act on the panel host. Home Assistant entity discovery does not automatically edit a custom dashboard or reproduce browser confirmation dialogs.

## File comparison

| Project-relative file | Compared with original ZIP |
|---|---|
| `.gitignore` | Unchanged |
| `README.md` | Updated |
| `VALIDATION.md` | Added |
| `VERSION` | Updated |
| `VERSIONING.md` | Updated |
| `commented_code_map.md` | Updated |
| `homelab-control/config.example.json` | Unchanged |
| `homelab-control/homelab-control-command-listener.service` | Unchanged |
| `homelab-control/homelab-control-status-indicator.service` | Unchanged |
| `homelab-control/homelab_control_command_listener.py` | Unchanged |
| `homelab-control/homelab_control_lib.sh` | Unchanged |
| `homelab-control/homelab_control_status_indicator.py` | Unchanged |
| `homelab-panel/app.py` | Updated |
| `homelab-panel/config.example.py` | Updated |
| `homelab-panel/devices.example.py` | Updated |
| `homelab-panel/homelab-controll.service` | Unchanged |
| `homelab-panel/templates/history.html` | Unchanged |
| `homelab-panel/templates/index.html` | Unchanged |
| `homelab-panel/templates/login.html` | Unchanged |
| `homelab-panel/templates/mqtt_diagnostics.html` | Unchanged |
| `scripts/homelab_action_common.sh` | Unchanged |
| `scripts/reboot_cancel.sh` | Unchanged |
| `scripts/reboot_delay.sh` | Unchanged |
| `scripts/shutdown_cancel.sh` | Unchanged |
| `scripts/shutdown_delay.sh` | Unchanged |
| `tests/test_home_assistant.py` | Added |
