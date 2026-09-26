# Homelab Panel 0.0.12 — validation

## Result

Version 0.0.12 was created from the user-provided **0.0.11** baseline. The release keeps the same **26 project paths**: no original path was removed or renamed and no new runtime/source path was added. Eight baseline files are updated for the feature, release metadata, documentation, tests, and validation; all other files remain byte-for-byte unchanged.

Original 0.0.11 archive SHA-256: `e3e68ccd77207c82eb76b66d2656f44366c4878f08dd7ebb074e69af864b6e08`.

## What changed

- Added optional `LOCAL_SERVER["name"]` as the local **Home Assistant device name**.
- Kept `LOCAL_SERVER["title"]` as the Homelab Panel webpage section title.
- Local HA MQTT discovery now prefers `LOCAL_SERVER.name`; older active `devices.py` files without the new key fall back to `LOCAL_SERVER.title`, then `"Homelab Panel"`.
- Local button labels still come from each existing button `label`. Home Assistant therefore has a real device name to combine with the button name, matching the naming pattern used by remote devices.
- Discovery topic `homelab_local_panel`, identifiers, unique IDs, command payloads, scripts, allow-listing, auth/token checks, retained-command rejection, shutdown/reboot delays, and all remote-device behavior are unchanged.

## Checks completed

Environment: Linux 6.18.44 x86_64, Python 3.13.5.

- Compiled all **6 Python source/test files** in memory with Python `compile()` successfully.
- Passed `bash -n` for all **6 shell files**.
- Parsed `homelab-control/config.example.json` successfully.
- Parsed all **4 Jinja templates** successfully.
- `systemd-analyze verify` passed for all **3 supplied service files**.
- Compared top-level function ASTs in `homelab-panel/app.py` against 0.0.11: **only `publish_home_assistant_discovery()` changed**. Existing execution, authentication, WoL, power-confirmation, MQTT dispatch, and script-safety functions are unchanged.
- Ran a targeted import/execution check of the real `app.py` discovery path with temporary dependency stubs and all external thread/network work blocked. It verified all four local buttons publish `device.name = LOCAL_SERVER["name"]`, and verified the old-config fallback to `LOCAL_SERVER["title"]`.
- Added project regression assertions for explicit local HA device naming and a dedicated fallback test for old configs.
- Confirmed the README disclaimer/liability and AI-assisted disclaimer text remains unchanged from 0.0.11.
- Verified the final project tree contains no `__pycache__`, `.pyc`, `.pyo`, build-cache, dependency-environment, active-config, runtime-state, log, or temporary files.

## Full regression-suite limitation

`python3 -B -m unittest discover -s tests -v` could not run in this execution environment because `paho-mqtt` and Flask are not installed. The suite stops during import at `ModuleNotFoundError: No module named 'paho'`. A temporary `pip --target` installation of Flask and Paho was attempted outside the project, but the environment has no working package-index/DNS access, so no dependencies could be downloaded.

This is an environment limitation rather than a failing project assertion. The new discovery behavior was still exercised through the targeted dependency-stub check described above.

## Not fully tested

- No live Home Assistant instance or MQTT broker was connected, so final device/entity presentation in a live HA registry still requires deployment verification.
- No real Wake-on-LAN, shutdown, reboot, sudo/root action, or remote custom job was executed.
- The full Flask/Paho regression suite could not execute because those dependencies are unavailable in this environment.
- No interactive browser layout test was run; templates themselves are unchanged and parse successfully.

## Upgrade note

Existing active `homelab-panel/devices.py` files continue to work without modification. To give the local Home Assistant device a distinct host name, add `name` next to `title`, for example:

```python
LOCAL_SERVER = {
    "title": "Lokal enhedskontrol",
    "name": "Mac Mini",
    "buttons": [
        # existing buttons unchanged
    ],
}
```

After changing `devices.py`, restart Homelab Panel so MQTT discovery is republished. Existing retained Home Assistant discovery uses the same local identifier and entity unique IDs, so this changes the device name rather than intentionally creating a second local device.

## File comparison against 0.0.11

| Project-relative file | Status |
|---|---|
| `.gitignore` | Unchanged |
| `README.md` | Updated |
| `VALIDATION.md` | Updated |
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
| `homelab-panel/config.example.py` | Unchanged |
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
| `tests/test_home_assistant.py` | Updated |
