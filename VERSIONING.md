# VERSIONING.md

## Version policy

This project uses three-part numeric versions and increments every created release by exactly `0.0.1`.

Examples:

- `0.0.1` → `0.0.2`
- `0.0.98` → `0.0.99`
- `0.0.99` → `0.1.0`

The rollover is **not** `0.0.100`.

Every created release must update:

- `VERSION`
- `VERSIONING.md`
- `README.md` when current behavior/usage/configuration changes
- `commented_code_map.md` when functions, routes, scripts, commands, or architecture change
- all affected configuration example files

Release ZIPs must exclude generated Python bytecode/cache files and temporary/build artifacts. Runtime logs/state should not be shipped as historical machine data unless there is a specific reason to preserve them.

---

## 0.0.6 — 2026-09-25

### Panel-control actions now appear in Remote enhedsstatus

- Fixed incoming `MQTT_CONFIG["panel_control_topic"]` actions being executed/logged without any immediate visible information in Homelab Panel.
- Added a thread-safe per-device provisional panel-action state for actions initiated through either incoming panel MQTT control or the web panel's remote WoL/MQTT buttons.
- Added `execute_and_record_remote_action()` so web and MQTT entry points reuse one dispatch-and-record path rather than duplicating status handling.
- Successful panel dispatch is represented as protocol result `sent`, displayed as Danish `Afsendt`; this intentionally means the WoL/MQTT command was sent, not that the remote operation has completed.
- Added friendly display mappings for `power_on`, shutdown/cancel, and reboot/cancel panel command names.
- Improved successful dispatch messages so WoL reports a magic packet sent to the selected device and remote MQTT controls report the configured payload/topic that was published.
- `evaluate_remote_device_status()` now prefers a newer provisional panel action over older remote command status, then automatically returns to the real remote-agent fields as soon as newer remote command state is received.
- The comparison uses the panel's local MQTT receipt/event times instead of comparing clocks across separate homelab machines.
- Provisional panel action state is intentionally in-memory only; a panel restart clears it, while retained remote-agent status/history is unchanged.
- No remote command allow-list, retained-control rejection, website authentication, shutdown/reboot safety behavior, or history format was weakened or removed.

### Documentation

- Updated `README.md` to explain exactly what an incoming `homelab-panel/control` command displays and the difference between `Afsendt` and a confirmed remote result.
- Updated `commented_code_map.md` for the new panel-action state helpers and revised status-selection/dispatch flow.
- Updated `VERSION` to `0.0.6`.

### Validation performed for this release

- Re-reviewed the complete 0.0.5 project before modification.
- Python compile/syntax checks.
- Targeted offline tests with stubbed Flask/Paho and command execution verified that older retained/current remote state is temporarily overlaid by a newer panel `power_on`, successful dispatch displays `Afsendt`, failure displays `Fejl`, and a newer real remote-agent state supersedes the provisional panel state.
- Verified the incoming JSON MQTT control path records `device_id`, command, configured panel-control topic source, result, message, and timestamp.
- Shell/JSON/Jinja/systemd and final ZIP cleanliness/manifest checks repeated for the finished release.
- A real MQTT broker, actual WoL target, and destructive shutdown/reboot operations were not used during release testing.

## 0.0.5 — 2026-09-25

### Optional website username/password authentication

- Added optional `WEB_AUTH_CONFIG` to `homelab-panel/config.example.py` with `enabled`, `username`, `password`, `secret_key`, and `session_cookie_secure`.
- Added a global Flask `before_request` authentication guard so, when enabled, all current and future web page/control routes require an authenticated session except the login/static endpoints.
- Added `GET/POST /login` with generic failed-login feedback and constant-time username/password comparison via `hmac.compare_digest`.
- Added `POST /logout` and logout controls to the dashboard and device-history page.
- The signed session stores only an authenticated flag and username; the password is not stored in the session or URL.
- Configured session cookies as `HttpOnly` and `SameSite=Lax`; optional `session_cookie_secure` is available for HTTPS deployments.
- Added startup validation that rejects empty auth credentials and unchanged `CHANGE_ME` password/session-secret placeholders when login is enabled.
- Preserved upgrade compatibility: an existing 0.0.4 `config.py` without `WEB_AUTH_CONFIG` continues with web login disabled.
- Preserved the legacy `PANEL_TOKEN` gate when web login is disabled. When web login is enabled, the session replaces the query-string token so users are not required to pass both.
- Added `homelab-panel/templates/login.html`.
- MQTT control/authentication is unchanged and remains governed by broker authentication/ACLs rather than the website session.
- No Wake-on-LAN, MQTT dispatch, shutdown/reboot, history, or remote-agent behavior was changed.

### Documentation/configuration

- Updated `README.md` for current 0.0.5 login setup, routes, upgrade behavior, and security limitations.
- Updated `commented_code_map.md` for all new authentication functions/routes/template behavior.
- Updated `VERSION` to `0.0.5`.

### Validation performed for this release

- Re-reviewed the complete 0.0.4 project before modification.
- Python compile/syntax checks.
- Shell `bash -n`, JSON parse, Jinja template parse, and systemd unit checks repeated.
- Offline auth-flow tests with stubbed Flask/Paho interfaces verified: enabled/disabled auth, unauthenticated protection for all existing control/page endpoints plus a simulated future endpoint, correct and failed login, UTF-8 credentials, logout/session clearing, legacy `PANEL_TOKEN` behavior, old-config fallback, cookie settings, and fail-closed credential/secret validation.
- Verified `commented_code_map.md` covers all current Python and shell functions and README covers all panel config-example fields.
- Rechecked `.gitignore` behavior: local active configs are ignored while all three example configs remain trackable.
- Compared the final manifest with 0.0.4 and accounted for every changed/new file; no original project files were removed.
- Flask/Paho runtime packages were not available in the execution environment and could not be installed because outbound package access was unavailable, so a real Flask test-client/browser session against the actual Flask package could not be performed here.
- Final ZIP scanned for forbidden Python bytecode/cache and temporary artifacts.

## 0.0.4 — 2026-09-25

### Shared script location

- Consolidated the four shutdown/reboot action scripts into the project root, beside `homelab-panel/` and `homelab-control/`.
- Removed the duplicate `homelab-panel/scripts/` and `homelab-control/scripts/` copies.
- Added `homelab_action_common.sh` so both panel and remote-agent execution reuse one privilege/status integration path.
- `homelab-panel/app.py` now derives the common project root from its own `__file__` location and no longer requires `LOCAL_SCRIPT_PATH`.
- `homelab-control/homelab_control_command_listener.py` now derives the same common project root from its own `__file__` location.
- Root execution continues to use direct `shutdown` and existing remote status/MQTT helpers when an active remote config exists; non-root panel execution continues to use `sudo shutdown`.
- Removed `LOCAL_SCRIPT_PATH` from `config.example.py` because script discovery is automatic.
- Updated README/current-use documentation and `commented_code_map.md` for the shared layout and all affected functions/scripts.

### Validation performed for this release

- Re-reviewed the complete 0.0.3 project before modification.
- Python compile/syntax checks.
- Shell `bash -n` checks for all shell files.
- JSON and Python example-config parsing/compile checks.
- Verified both Python callers resolve action scripts to the same parent directory independent of current working directory.
- Verified root/shared action-script status integration with command stubs so no real shutdown/reboot was performed.
- Verified non-root action path selects `sudo shutdown` through a stubbed environment.
- Compared the final manifest with 0.0.3 and accounted for each moved/added/removed file.
- Final ZIP scanned for forbidden Python bytecode/cache and temporary artifacts.

## 0.0.3 — 2026-09-25

### Configuration files and Git hygiene

- Added a root `.gitignore` with path-scoped rules for the panel and remote-agent configuration areas.
- `homelab-panel/config.py`, `homelab-panel/devices.py`, and `homelab-control/config.json` are now local-only files and are intentionally excluded from Git and clean release ZIPs.
- Preserved all three complete tracked examples:
  - `homelab-panel/config.example.py`
  - `homelab-panel/devices.example.py`
  - `homelab-control/config.example.json`
- Used path-scoped ignore rules so the panel and control `config*` rules cannot accidentally re-ignore each other's example files.
- Updated `README.md` with the required copy-from-example setup commands and current release behavior.
- Updated `commented_code_map.md` to explain the local-only active configuration model and `.gitignore` rationale.
- No application runtime logic, MQTT behavior, history behavior, shutdown/reboot behavior, or safety behavior was changed.

### Validation performed for this release

- Verified each active 0.0.2 configuration exactly matched its corresponding example before removing the active copies.
- Verified `.gitignore` ignores exactly the three active configuration paths while leaving all three example files unignored.
- Python compile/syntax checks performed using temporary generated active configs outside the release tree.
- Shell `bash -n`, JSON parsing, Jinja template parsing, and systemd unit verification repeated.
- Final ZIP manifest compared with 0.0.2: only the three requested active config files were removed; `.gitignore` was added; existing source/runtime files were preserved.
- Final ZIP scanned for forbidden bytecode/cache/temporary artifacts.

## 0.0.2 — 2026-09-25

### MQTT control through Homelab Panel

- Added `MQTT_CONFIG["panel_control_topic"]` so the panel can receive structured JSON control messages from Home Assistant or another trusted MQTT client.
- Added `execute_remote_action()` as a shared allow-listed dispatcher used by both web routes and incoming panel MQTT control.
- Added `power_on` through the existing configured Wake-on-LAN path.
- Added panel MQTT handling for configured `shutdown_delay`, `shutdown_cancel`, `reboot_delay`, and `reboot_cancel` actions.
- Added user-friendly `shutdown` and `reboot` aliases that resolve to the existing one-minute delayed controls rather than introducing immediate destructive actions.
- Incoming MQTT control cannot choose an arbitrary shell command, topic, or payload; it must resolve through `REMOTE_DEVICES`.
- Retained incoming panel-control messages are rejected to prevent stale shutdown/reboot commands from replaying after reconnect.
- MQTT control work is dispatched from the Paho callback to a daemon thread so external command execution does not block the MQTT network loop.

### Per-boot command history

- Added `status_history` to the remote-agent MQTT topic configuration and `history_topic` to panel device status configuration.
- Added `history_max_entries` with a default/sample value of 100.
- Added persistent `state/history.json` and `state/boot_id` runtime state.
- Added Linux boot-ID detection so command state rolls into history only after an actual machine reboot, not after a status-service restart.
- Added migration fallback for installations without an existing `boot_id`: existing status is archived only when its `last_updated` timestamp clearly predates the current Linux boot time.
- On a detected new machine boot, the previous meaningful last command/result/message is archived with its original timestamp, current fields are cleared, and action state is reset to `idle`.
- History is capped before save to prevent unbounded runtime file growth.
- The remote status service publishes the complete capped history as retained JSON after MQTT connection.

### Web history UI

- Added `GET /history/<device_id>`.
- Added a History button to every remote-device status card.
- Added `templates/history.html` with separate Command, Result, and Message categories.
- Every history value is displayed with the original event date/time.
- Devices without a configured history topic receive a valid empty-history page rather than an error.

### Current-status display

- Added display normalization so cleared `none`/`unknown` command sentinel values render as `Ingen`.
- Added `none` result display handling.
- Initialized the existing MQTT connection flag explicitly in `app.py`.

### Configuration and documentation

- Updated active and example panel configs with `panel_control_topic`.
- Updated active and example device configs with `history_topic`.
- Updated active and example remote configs with `status_history` and `history_max_entries`.
- Rewrote `README.md` for current 0.0.2 usage only, including all MQTT message formats, history behavior, routes, configuration options, safety notes, and the existing disclaimer/liability text.
- Updated `commented_code_map.md` for every current Python/shell function, route, command interface, service, and new history component.

### Validation performed for this release

- Full 0.0.1 project inventory and relevant runtime code reviewed before modification.
- Python compile checks.
- Shell `bash -n` checks.
- JSON parse checks.
- Offline targeted tests for boot/history rollover, duplicate-history prevention on same boot, and remote-action dispatch.
- Final config-example synchronization checks.
- Jinja template parse checks where available.
- Final ZIP forbidden-artifact scan and original/final manifest comparison.

## 0.0.1 — 2026-09-25

Initial tracked release created from the uploaded, previously unversioned `Homelab-Panel-main` baseline.

### Runtime code

- Preserved the existing Python, shell, HTML, systemd, and active configuration behavior unchanged.
- Normalized the command-listener systemd unit file mode from executable (`0755`) to normal unit-file permissions (`0644`); unit contents were not changed.
- Did not refactor, rename, or alter shutdown/reboot, MQTT, Wake-on-LAN, ping, token, or status logic in this release.

### Documentation and release structure

- Rewrote `README.md` so it documents current application behavior and usage only, rather than acting as historical release notes.
- Added the requested liability/disclaimer language and adapted `script` wording to the Homelab Panel project where appropriate.
- Documented every current configuration option in `homelab-panel/config.py`, `homelab-panel/devices.py`, and `homelab-control/config.json`.
- Documented the complete current command surface: Python entry points, shell scripts, MQTT command payloads, Flask routes, and systemd usage.
- Explicitly documented that version 0.0.1 has no supported CLI flags or argument parser.
- Added `commented_code_map.md` with function/command/file purpose and rationale.
- Added explicit configuration examples:
  - `homelab-control/config.example.json`
  - `homelab-panel/config.example.py`
  - `homelab-panel/devices.example.py`
- Added `VERSION` containing `0.0.1`.

### Clean-package changes

- Removed the uploaded `homelab-panel/__pycache__/` directory and its `.pyc` files from the release package.
- Removed historical machine runtime data from `homelab-control/logs/commands.log` and `homelab-control/state/*` in the release package.
- Preserved the empty `logs/` and `state/` directories because the runtime uses those locations and creates their contents as needed.

### Validation performed for this release

- Full source/config/template/service inventory reviewed before modification.
- Python source compile checks performed without writing bytecode into the project tree.
- Shell scripts checked with `bash -n`.
- JSON configuration/example files parsed as JSON.
- Python config/example files syntax-checked.
- Release ZIP checked for forbidden cache/bytecode files.
- Final release manifest compared with the uploaded baseline so removals and additions are accounted for.

Any environment-dependent checks that could not be safely executed are reported with the delivered release rather than being represented as tested.
