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

## 0.0.12 — 2026-09-26

### Configurable local Home Assistant device name

- Added optional `LOCAL_SERVER["name"]` for the local Home Assistant MQTT device name, separate from the webpage-only `LOCAL_SERVER["title"]`.
- Home Assistant local button discovery now uses `LOCAL_SERVER.name`, so the device name can be the actual host name and HA can present button names in the same device/entity naming pattern as remote devices.
- Preserved backwards compatibility: active `devices.py` files without `name` continue using `LOCAL_SERVER.title`, then `"Homelab Panel"` as the final fallback.
- No discovery topic, identifier, unique ID, command payload, script mapping, authentication, retained-message guard, or local execution safety behavior changed.

### Documentation and verification

- Updated `devices.example.py`, README current-use documentation, the complete code map, tests, and validation notes for the new local device-name option.
- Added regression coverage that checks both the explicit local HA device name and the old-config title fallback.
- Preserved the existing README disclaimer wording unchanged.

## 0.0.11 — 2026-09-26

### Automatic Home Assistant action buttons

- Added MQTT discovery for every configured `LOCAL_SERVER.buttons` entry, grouped under the local server title and the separate `homelab_local_panel` identifier/topic namespace.
- Retained discovery for remote device MQTT buttons and enabled Wake/cancel-WoL controls; existing remote entity IDs and topics remain unchanged.
- Wake buttons now use the same configured label as the webpage; cancel-WoL uses the webpage's label.
- Added `publish_home_assistant_button()` to share button discovery generation across local, remote and WoL controls. Button command payloads explicitly set `retain=False`; discovery retention remains configurable.
- Added `publish_home_assistant_snapshot()` to republish discovery, panel availability and cached device state on broker connection or Home Assistant's online birth message. It does not run pings inside the MQTT callback.
- Added optional `HOME_ASSISTANT_CONFIG.status_topic` (default `homeassistant/status`; empty disables the subscription) and `status_online_payload` (default `online`). Older configs use these defaults.
- Discovery remains opt-in through `HOME_ASSISTANT_CONFIG.enabled`; example/default is still False. Config changes take effect after restarting the panel.

### Shared local command handling

- Added `execute_local_action()` so the webpage and MQTT both select local scripts from `LOCAL_SERVER.buttons` and reuse existing path/executable/privilege checks.
- Added explicit panel-control JSON `{"target":"local","command":"<button-id>"}`. A local envelope containing `device_id` is rejected, and a missing or unknown remote device never falls back to local execution.
- Existing remote `device_id`/`command` messages remain valid; an optional explicit `target=remote` is accepted. Unknown targets and missing commands are rejected.
- Retained panel-control rejection covers both local and remote commands. Web auth/token guards and all existing shutdown/reboot delays, allow-lists, and confirmation code remain intact.
- The remote agent and bundled scripts were not modified. Browser confirmation prompts do not transfer to Home Assistant MQTT button presses.

### Documentation and verification

- Reworked README into a current-use guide covering automatic HA setup, all configuration fields, web/MQTT/script commands, external command flags, installation, systemd usage, and limitations. It explicitly distinguishes HA entities from dashboard placement.
- Updated both affected panel configuration examples and the complete function/command map, including browser callbacks and regression-test helpers.
- Preserved both original README disclaimer sections verbatim because no replacement disclaimer was supplied.
- Added `tests/test_home_assistant.py` with 11 offline regression tests using real Flask/Jinja and mocked external I/O, plus `VALIDATION.md` for reproducible checks and manifest accounting.
- Verified all 24 original files remain present; original executable bits are preserved. All newly added project files are included in the clean ZIP.
- Python compile checks, shell syntax checks, embedded Python compilation, JSON/Jinja parsing, regression tests, documentation coverage and final ZIP checks are recorded in `VALIDATION.md`.
- Live Home Assistant/MQTT integration, real power/WoL operations, browser interaction, and Linux systemd execution were not tested in this macOS workspace.

## 0.0.10 — 2026-09-26

### Shared power scripts moved to `scripts/`

- Added a tracked `scripts/` directory at the project root for Homelab Panels shared shutdown/reboot helpers only.
- Moved `shutdown_delay.sh`, `shutdown_cancel.sh`, `reboot_delay.sh`, `reboot_cancel.sh`, and `homelab_action_common.sh` from the project root into `scripts/`.
- Kept `homelab-control/homelab_control_lib.sh` in `homelab-control/`; it belongs to the remote agent rather than the shared power-script bundle.
- Project-specific jobs such as Watchtower/backup/Syncerate are not moved into `scripts/`; they remain owned by their own project/integration.

### Path resolution

- Added panel `SCRIPTS_DIR = PROJECT_ROOT/scripts`; local `LOCAL_SERVER` scripts now resolve only from that directory and reject nested/path-traversal names.
- Added remote `SCRIPTS_DIR` plus an explicit shared-power-script allow-list. The four bundled power script names automatically resolve from `PROJECT_ROOT/scripts/`, so existing `config.json` entries such as `"script": "shutdown_delay.sh"` remain valid.
- Preserved 0.0.9 behavior for non-bundled custom job filenames; this release does not relocate those project-specific scripts.
- Updated `homelab_action_common.sh` for its new location: it treats its directory as `SCRIPT_DIR`, then resolves `PROJECT_ROOT` as the parent and finds `homelab-control/` from there.
- The four action scripts continue to source `homelab_action_common.sh` relative to their own directory, so they do not depend on the shell working directory.

### Git/development hygiene

- Updated `.gitignore` to ignore `.venv/`, Python bytecode/cache files, and macOS `.DS_Store` in addition to the existing active-config/runtime exclusions.
- `scripts/` is intentionally tracked source and is not ignored.

### Validation performed for this release

- Started from the user-provided 0.0.9 release ZIP.
- Verified that all five shared power/helper shell files exist under `scripts/` and no duplicate copies remain at project root.
- Verified panel local-script resolution points into `PROJECT_ROOT/scripts`.
- Verified remote built-in power commands resolve into `PROJECT_ROOT/scripts` while non-bundled custom filenames retain the previous resolution behavior.
- Verified `homelab_action_common.sh` resolves the correct project root and `homelab-control` directory from its new location.
- Re-ran Python syntax/compile, shell `bash -n`, JSON, Jinja, systemd, `.gitignore`, function-map, manifest, and final ZIP cleanliness checks.
- No real shutdown/reboot commands were executed during validation.

## 0.0.9 — 2026-09-26

### Optional Home Assistant MQTT Discovery

- Added optional `HOME_ASSISTANT_CONFIG`; disabled by default.
- Added MQTT Discovery entities for combined online, ping, uptime, last command, and job status.
- Added Home Assistant buttons for Wake-on-LAN, cancel-WoL, and every configured `mqtt_controls.buttons` entry.
- Added retained per-device JSON state topics and panel availability/LWT for Home Assistant.
- Kept combined HA online strict: both ping and fresh MQTT-online must be true simultaneously.

### Generic allow-listed remote jobs

- Extended remote `commands` entries to accept either the legacy `"id": "script.sh"` form or objects containing `script`, `label`, `category`, and `timeout`.
- Added optional JSON command envelopes carrying `command`, `job_id`, and `source`, while preserving legacy plain-text command payloads.
- Added script-path containment validation so configured jobs cannot traverse outside the shared project root.
- Existing dynamic `devices.py` buttons remain the panel allow-list; any added button is also exposed through Home Assistant Discovery.
- Script result data is published through the separate remote job-status topic, not through `homelab-panel/control`.

### Job lifecycle and parallel execution

- Added remote job state `queued -> running -> success/failure`, including queued/start/finish timestamps, runtime, return code, and bounded stdout/stderr summary.
- Added retained `status_jobs` snapshots and persistent remote `state/jobs.json`.
- Added configurable `max_parallel_jobs` and `job_history_max_entries`.
- Listener startup marks leftover active jobs as failure so interrupted work cannot remain falsely active after a service restart.
- The command listener now starts independent worker threads so multiple allow-listed jobs/hosts can run concurrently.
- Added a panel Job Status dashboard that combines panel-side confirmation jobs and remote job results.
- Added optional `json_jobs=True` per device so the panel and agent can share the exact same job ID.

### Event journal and transition history

- Expanded panel history records with `category`, `event_type`, `severity`, job metadata, and optional duration.
- Added an event timeline with category filters and an Errors filter while retaining the separate Command/Result/Message history sections.
- Added panel MQTT connect/reconnect/disconnect events.
- Added combined availability transition events and previous-state duration.
- Added remote boot events and optional/derived boot ID and boot time topics.
- Preserved existing boot cleanup: previous current command state remains in history, while current command/result/message is cleared on a real new Linux boot.

### Expected-state and completion confirmation

- Added persistent per-device expected-state tracking for starting, online, shutdown pending/offline, and rebooting.
- Expected shutdown state is distinguished from an unexpected offline transition.
- Added shutdown confirmation requiring both ping offline and MQTT `power=offline`.
- Added reboot confirmation requiring an offline phase followed by both ping and MQTT online.
- Existing `shutdown_delay` and `reboot_delay` buttons get confirmation automatically even when older active `devices.py` files do not contain the new `confirmation` field.

### Wake-on-LAN retry/cancel

- Added optional per-device WoL retry interval/max attempts and MQTT-online confirmation timeout.
- WoL now records each attempt and can confirm completion with ping followed by MQTT.
- Added a cancel button on the device status card that is shown only while a WoL job is active.
- Added `cancel_wol` as a panel-control action and Home Assistant button.

### MQTT diagnostics

- Added `/mqtt-diagnostics` showing broker/client state, subscriptions, expected topics by device, latest payload, receive timestamp, age, retained flag, and QoS.
- Added subscriptions/display support for hostname, uptime, jobs, boot ID, and boot time topics, with sibling-topic derivation for older active device configs.
- Diagnostics is protected by the same web-login/token guard as all other application pages.

### Configuration and compatibility

- Added `STATUS_MONITOR_INTERVAL_SECONDS`, `PANEL_JOB_MAX_ENTRIES`, and optional Home Assistant settings to `config.example.py`.
- Added jobs/boot topics, job limits, parallel-job limit, and object-style command examples to remote `config.example.json`.
- Added WoL retry, confirmation, expected-state, jobs/boot/uptime/hostname topics, `json_jobs`, and a generic Watchtower example to `devices.example.py`.
- Older active configs remain valid through defaults/topic derivation and legacy command formats.

### Validation performed for this release

- Re-inspected the full 0.0.8 package before changes.
- Python compile, shell `bash -n`, JSON parse, Jinja parse, and systemd unit verification.
- Offline panel tests for arbitrary dynamic commands, HA Discovery generation/disabled mode, remote job correlation, independent ping/strict combined online, expected-state display, diagnostics inventory, and conditional WoL cancellation.
- Remote listener tests for legacy/plain JSON payload compatibility, parallel script execution, success lifecycle, legacy command mappings, and path-traversal rejection.
- Remote status tests for derived boot/history topics and true-boot archive/clear/boot-event behavior.
- Live Home Assistant, live MQTT broker, real Wake-on-LAN, shutdown, reboot, and production scripts were not executed in the release environment.

## 0.0.8 — 2026-09-25

### Independent ping and MQTT status

- Kept ping evaluation independent from MQTT so a responding device is visibly shown as `Ping: Svarer` even when MQTT is not configured, not connected, or has not published status yet.
- Added a three-state combined device presentation: green `Online`, yellow `Ikke fuldt online`, and red `Offline`.
- The combined green `Online` state now requires ping and MQTT-online to be true at the same time.
- MQTT-online now additionally requires Homelab Panel's MQTT client to be currently connected to the broker; a cached/fresh-looking previous `online` payload alone no longer counts after broker disconnect.
- Added explicit MQTT display states for not configured, broker disconnected, broker connected without a device status, stale power status, and fresh power status.
- Added separate ping/MQTT status indicators in the device card so partial connectivity is visible instead of being hidden behind a single red overall result.
- Changed panel MQTT startup from blocking `connect()` to `connect_async()` plus the existing background loop/reconnect delay. The web panel and ping therefore keep working when the broker is unavailable at startup, and MQTT can connect later without restarting Homelab Panel.
- No ping command semantics, MQTT topics, device control, command history, web authentication, shutdown/reboot safety, or config format were changed.

### Validation performed for this release

- Re-reviewed the complete 0.0.7 project before modification.
- Targeted status-model tests cover ping-only, MQTT-only, both online, neither online, broker-disconnected cached MQTT, unconfigured MQTT, and stale MQTT.
- Targeted MQTT-startup test verifies `connect_async()` is scheduled and the network loop starts without waiting for a successful broker connection.
- Python compile/syntax, shell syntax, JSON, Jinja, systemd, documentation/function-map, manifest, and release-artifact cleanliness checks were repeated for the final package.
- A real ICMP ping could not be executed inside the release container because raw-socket permission is denied there; ping behavior was therefore verified through the panel's status logic with controlled ping results rather than by live ICMP from the container.

## 0.0.7 — 2026-09-25

### Event-based device history

- Changed remote command history from one previous-boot snapshot to an event stream: every `write_command_status()` call now appends its own command/result/message/timestamp entry before the current status is overwritten.
- Intermediate messages such as `running` followed by `success` are therefore both preserved instead of only the final message surviving until the next boot.
- Added a `source` field to new history events (`Remote enhed` or `Homelab Panel`).
- Kept `timing.history_max_entries` as the cap for remote history events.
- Added file locking and atomic replacement when the shell helper appends remote history, reducing the risk of a partially written `history.json`.
- The complete updated remote history is published retained after each command-status event.

### Clean current status on a new online boot

- Preserved Linux boot-ID detection so a service restart during the same boot does not incorrectly clear status.
- On a real new boot, the previous current command/result/message is archived only when an identical event is not already present, then the current fields are cleared before the new online state is published.
- This provides migration safety for older installations while preventing the final event from being duplicated in 0.0.7 history.

### Panel-originated history and online transition

- Panel-originated WoL and remote MQTT dispatches are now persisted per device in `homelab-panel/state/panel_action_history.json`, capped by new optional `PANEL_HISTORY_MAX_ENTRIES` (default 100).
- A provisional panel action remains visible in the current status card while appropriate, but when that device transitions from non-online/unknown to MQTT `online`, the provisional current panel status is cleared.
- The same panel action remains in history after the current card is cleared.
- The per-device history page merges panel-originated and remote-agent events, sorts them newest-first, and shows the source alongside each timestamp.

### Backward-compatible history topic discovery

- `homelab-control` now derives `<prefix>/history` from `status_last_message=<prefix>/last_message` when an older active `config.json` has no `status_history`.
- Homelab Panel performs the same derivation when an older active `devices.py` has no `history_topic`.
- Explicit `status_history` / `history_topic` remains supported and is still shown in the example configs.
- This allows the user's existing `aoostar/status/...` configuration to begin carrying history without requiring an immediate local config edit.

### Configuration and repository hygiene

- Added `PANEL_HISTORY_MAX_ENTRIES = 100` to `homelab-panel/config.example.py`.
- Added runtime state/log directories to `.gitignore`; active config ignore behavior and all example configs remain unchanged.
- Updated `README.md`, `commented_code_map.md`, and `VERSION` for current 0.0.7 behavior.

### Validation performed for this release

- Re-reviewed the full 0.0.6 project before modification.
- Python compile/syntax checks and shell `bash -n` checks.
- Targeted remote-helper test verified two consecutive status messages create two distinct history events and that an omitted `status_history` derives `aoostar/status/history`.
- Targeted boot rollover test verified an event already in history is not duplicated, current fields are cleared on a real new boot, and a legacy current status missing from history is archived once.
- Targeted panel test verified a panel WoL action is persisted, an MQTT offline→online transition clears only its provisional current state, and panel plus remote history events merge without losing messages.
- Final JSON/Jinja/systemd/manifest/forbidden-artifact checks are recorded with the release package.

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
