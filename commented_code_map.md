# commented_code_map.md

This file maps the current Homelab Panel codebase. It describes what each function, route, supplied command, service, and major data/configuration file does and why it exists.

## Root files

### `VERSION`

Contains the current tracked release number. It exists so a release can be identified without inferring a version from a ZIP filename.

### `README.md`

Current-use documentation only: installation, configuration, commands, supported interface, current behavior, security/safety notes, and disclaimers.

### `VERSIONING.md`

Defines the `0.0.1` increment rule, rollover behavior, and records all created releases and their changes.

---

# `homelab-control/` — remote MQTT control/status agent

## `homelab-control/config.json`

Runtime JSON configuration for the remote agent. It exists to keep broker details, MQTT topic names, client IDs, timing, and payload-to-script mappings outside Python/shell logic.

## `homelab-control/config.example.json`

Complete example copy containing every currently supported remote-agent configuration option. It exists so the expected configuration shape remains explicit when deployments customize `config.json`.

## `homelab-control/homelab_control_command_listener.py`

Long-running MQTT listener that converts allowed MQTT payloads into configured executable script filenames.

### `load_config() -> dict`

Reads and parses `config.json`.

**Why:** configuration must be external to the Python implementation so broker/topics/commands can be changed without editing listener logic.

### `run_script(script_name: str) -> None`

Builds the script path inside the fixed `scripts/` directory, verifies that it is a regular file and executable, then executes it with `subprocess.run()` using a 60-second timeout. It prints return code/stdout/stderr instead of interpreting arbitrary MQTT text as a command.

**Why:** this constrains remote control to script filenames that were explicitly mapped in configuration and prevents the MQTT payload from being passed directly to a shell.

### `on_connect(*args)`

MQTT connection callback. Subscribes to the configured control topic at QoS 1.

**Why:** the listener must re-establish its command subscription whenever the MQTT connection is established/re-established.

### `on_message(client, userdata, msg)`

Decodes the MQTT payload, looks it up in `COMMAND_MAP`, rejects unknown payloads, and calls `run_script()` for a known mapping.

**Why:** provides the allow-listed payload-to-script dispatch point.

### `build_client()`

Creates a Paho MQTT v3.1.1 client. It first requests Paho's VERSION2 callback API and falls back to the older constructor when `CallbackAPIVersion` is unavailable.

**Why:** maintains compatibility with both newer and older Paho installations.

### `main() -> int`

Builds the client, applies credentials when configured, installs callbacks, connects to the broker, and enters `loop_forever()`.

**Why:** this is the program entry point used by direct execution and the systemd service.

---

## `homelab-control/homelab_control_status_indicator.py`

Long-running status publisher that mirrors local state files to retained MQTT topics and periodically publishes online/uptime state.

### `load_config() -> dict`

Reads `config.json`.

**Why:** keeps remote status topics, broker settings, and timing configurable.

### `ensure_dirs() -> None`

Creates the runtime `state/` and `logs/` directories if absent.

**Why:** clean releases do not need to ship historical runtime files; the process can initialize its own storage locations.

### `read_text_file(path: str, default: str = "") -> str`

Reads/strips a text state file and returns a default for missing/empty/unreadable files.

**Why:** status reporting should continue even when a state file has not yet been created or cannot be read.

### `write_text_file(path: str, value: str) -> None`

Writes through `path.tmp` and atomically replaces the target with `os.replace()`.

**Why:** reduces the chance of readers observing a partially written state file.

### `read_action() -> str`

Reads the action file with `idle` as the default.

**Why:** centralizes the default action state.

### `write_action(value: str) -> None`

Writes the action state through `write_text_file()`.

**Why:** reuses the atomic state-file write path.

### `get_uptime_seconds() -> int`

Reads `/proc/uptime` and returns whole seconds, or `-1` on failure.

**Why:** provides a small Linux uptime value for MQTT status without invoking another process.

### `publish(topic: str, payload: str, retain: bool = True, qos: int = 1) -> None`

Publishes through the module's active MQTT client when one exists.

**Why:** centralizes MQTT publication defaults and safely does nothing before the client is assigned.

### `publish_command_status() -> None`

Reads the last command/result/message/update state files and publishes them retained.

**Why:** reconnects can republish the last known command state immediately.

### `on_connect(*args)`

Publishes online state, current action, hostname, and last command status when connected.

**Why:** quickly restores broker-visible retained state after a service/broker reconnect.

### `on_disconnect(*args)`

Current no-op disconnect callback.

**Why:** callback slot is present for compatibility/future handling; offline state is primarily handled through MQTT last-will and normal shutdown publication.

### `uptime_loop()`

Until `stop_event` is set, publishes retained `online` and uptime, then waits `publish_uptime_every` seconds.

**Why:** supplies both a heartbeat used for freshness and machine uptime.

### `action_sync_loop()`

Polls the local action file every two seconds and publishes when its value changes.

**Why:** shell action scripts and the Python status service communicate through a simple local file rather than sharing process memory.

### `command_status_sync_loop()`

Polls command/result/message/update files every two seconds and republishes the tuple when it changes.

**Why:** mirrors status written by shell scripts to MQTT even though the scripts and Python service are separate processes.

### `build_client()`

Creates a Paho MQTT v3.1.1 client with new-callback-API/legacy fallback.

**Why:** same Paho compatibility strategy as the command listener.

### `main() -> int`

Creates runtime directories/default state files, configures credentials and retained last-will `offline`, connects/starts the MQTT loop, starts the three background synchronization loops, installs SIGTERM/SIGINT handling, waits for shutdown, then attempts to publish `offline` and disconnect cleanly.

**Why:** coordinates the whole status service lifecycle and provides both abnormal-offline last-will behavior and best-effort normal shutdown state.

### nested `handle_signal(signum, frame)` inside `main()`

Sets `stop_event` when SIGTERM or SIGINT is received.

**Why:** lets all loops leave cooperatively and enables the `finally` cleanup path.

---

## `homelab-control/homelab_control_lib.sh`

Shared shell library sourced by all four remote action scripts.

### `json_get KEY.PATH`

Uses an embedded Python snippet to read a dot-separated value from `config.json`.

**Why:** avoids requiring `jq` while letting shell scripts consume the same configuration file as Python.

### `ensure_dirs`

Creates `state/` and `logs/`.

**Why:** every state/log writer can safely run on a clean installation.

### `timestamp_now`

Returns local time in `YYYY-MM-DDTHH:MM:SS` form.

**Why:** provides a consistent timestamp for state and command logs.

### `mqtt_pub TOPIC PAYLOAD`

Calls `mosquitto_pub` with broker host/port, optional user/password, retained publication, and QoS 1.

**Why:** all shell actions need the same MQTT publication behavior without repeating credentials/options.

### `write_action VALUE`

Writes the current action state file.

**Why:** gives the Python status process a simple local source for action state.

### `write_command_status COMMAND RESULT MESSAGE`

Writes last-command state files, appends one line to `logs/commands.log`, then publishes the same data to the configured retained MQTT topics.

**Why:** provides a single consistent status/logging path for all shutdown/reboot scripts.

### `set_idle`

Writes/publishes `idle`.

**Why:** centralizes the normal no-pending-action state.

### `set_shutdown_pending`

Writes/publishes `shutdown_pending`.

**Why:** reports that a shutdown has been requested but has not occurred yet.

### `set_reboot_pending`

Writes/publishes `reboot_pending`.

**Why:** reports that a reboot has been requested but has not occurred yet.

---

## Remote action command scripts

All four scripts use `set -euo pipefail`, find their own installation directory, and source `homelab_control_lib.sh`.

### `homelab-control/scripts/shutdown_delay.sh`

Sets `shutdown_pending`, records a `running` status, calls `shutdown -h +1`, then records `success`; on failure it restores `idle`, records `failure`, and exits nonzero.

**Why:** provides a one-minute delayed power-off with MQTT/local state feedback.

### `homelab-control/scripts/shutdown_cancel.sh`

Calls `shutdown -c`; on success sets `idle` and records success, otherwise records failure and exits nonzero.

**Why:** cancels a previously scheduled shutdown/reboot.

### `homelab-control/scripts/reboot_delay.sh`

Sets `reboot_pending`, records `running`, calls `shutdown -r +1`, then records success; on failure it restores `idle`, records failure, and exits nonzero.

**Why:** provides a one-minute delayed reboot with status feedback.

### `homelab-control/scripts/reboot_cancel.sh`

Calls `shutdown -c`; on success sets `idle` and records success, otherwise records failure and exits nonzero.

**Why:** exposes a dedicated reboot-cancel control even though Linux uses the same `shutdown -c` command to cancel either scheduled action.

---

## Remote systemd units

### `homelab-control-command-listener.service`

Runs the command listener as root after `network-online.target`, restarts it always after failures/exits, and uses the configured installation path in the unit.

**Why:** keeps the remote MQTT command subscriber continuously available.

### `homelab-control-status-indicator.service`

Runs the status indicator as root after `network-online.target` and restarts it always.

**Why:** keeps heartbeat/status publication running independently of the command listener.

---

# `homelab-panel/` — Flask web panel

## `homelab-panel/config.py`

Runtime panel settings: WoL broadcast address, broker connection/publication settings, optional query token, local script directory, MQTT freshness TTL, and page refresh interval.

## `homelab-panel/config.example.py`

Complete example copy containing every currently supported panel setting.

## `homelab-panel/devices.py`

Declarative data defining remote devices, their WoL/status/MQTT controls, and local server buttons.

**Why:** the HTML and Flask routes can be generic and data-driven instead of adding hard-coded route/template logic for every device.

## `homelab-panel/devices.example.py`

Complete example copy containing every currently supported device/button field.

---

## `homelab-panel/app.py`

Flask application plus MQTT state listener and helpers.

### `check_token() -> bool`

Allows all requests when `PANEL_TOKEN` is empty; otherwise compares the request's `token` query parameter with the configured value.

**Why:** provides the project's current optional lightweight access gate for every exposed route.

### `run_command(cmd: list[str], timeout: int = 20) -> tuple[bool, str]`

Runs a command without a shell, captures stdout/stderr, applies a timeout, and converts the return code/output/exception into `(success, message)`.

**Why:** WoL, MQTT publication, ping, and local scripts all need consistent subprocess handling.

### `mqtt_publish(topic: str, payload: str) -> tuple[bool, str]`

Builds a `mosquitto_pub` argument list from `MQTT_CONFIG`, optionally adds retain/user/password options, then calls `run_command()`.

**Why:** panel buttons publish through one controlled external-command path.

### `send_wol(mac: str) -> tuple[bool, str]`

Runs `wakeonlan -i WOL_BROADCAST MAC` through `run_command()`.

**Why:** provides one reusable WoL action for every device definition.

### `run_local_script(script_name: str) -> tuple[bool, str]`

Joins `LOCAL_SCRIPT_PATH` with the configured filename, checks file/executable status, then runs it without a shell.

**Why:** local control buttons can only reference executable files in the configured local script directory rather than arbitrary command strings.

### `ping_host(ip: str) -> bool`

Calls `ping -c 1 -W 1` with a three-second subprocess timeout.

**Why:** provides the network-reachability half of the panel's strict online determination.

### `set_mqtt_state(topic: str, payload: str) -> None`

Under a lock, stores the most recently received payload and current receipt timestamp for a topic.

**Why:** Flask request handling and the Paho network thread share status data safely.

### `set_mqtt_connected(value: bool) -> None`

Updates the module-level MQTT connection flag.

**Why:** records broker connection state for potential status use. The current device evaluation does not use this flag directly.

### `get_mqtt_connected() -> bool`

Returns the module-level MQTT connection flag.

**Why:** accessor paired with `set_mqtt_connected()`. It is not currently called by device-status evaluation.

### `get_mqtt_state(topic: str) -> dict | None`

Returns the stored state for a non-empty topic under the state lock.

**Why:** centralizes thread-safe MQTT state retrieval.

### `get_mqtt_payload_and_age(topic: str) -> tuple[str | None, int | None]`

Gets stored state, strips the payload, and computes age in seconds from the receipt timestamp.

**Why:** device status needs both the retained value and its local freshness.

### `action_to_danish(payload: str | None) -> str`

Maps known action states to Danish UI text, falling back to the original payload.

**Why:** keeps protocol values stable while presenting friendlier localized text.

### `result_to_danish(payload: str | None) -> str`

Maps `running`, `success`, and `failure` to Danish UI text.

**Why:** same protocol/UI separation for command results.

### `evaluate_remote_device_status(device: dict) -> dict`

Pings the device, reads configured MQTT state topics, applies the freshness TTL, and returns the complete display-state dictionary. Overall state is online only when ping succeeds and a fresh MQTT power payload equals `online`.

**Why:** consolidates the panel's status policy in one place.

### `build_remote_device_statuses() -> dict`

Runs `evaluate_remote_device_status()` for every entry in `REMOTE_DEVICES`.

**Why:** builds the template's status dictionary without duplicating loop logic in the route.

### `on_connect_compat(*args)`

Marks MQTT connected, collects all non-empty status topics from every configured remote device, subscribes once to each unique topic at QoS 1, and logs subscriptions.

**Why:** automatically adapts panel subscriptions to `devices.py` and avoids duplicate subscriptions.

### `on_disconnect_compat(*args)`

Marks MQTT disconnected and logs it.

**Why:** maintains connection-state tracking across broker/network loss.

### `on_message_compat(client, userdata, msg)`

Decodes an incoming MQTT payload and stores it with `set_mqtt_state()`.

**Why:** feeds the in-memory state used during page rendering.

### `build_mqtt_client()`

Creates a Paho MQTT v3.1.1 client using the configured panel client ID, with VERSION2/legacy constructor fallback, then configures reconnect delay from one to 30 seconds.

**Why:** provides compatibility plus bounded reconnect backoff.

### `start_mqtt_listener() -> None`

Builds/configures callbacks and credentials, attempts broker connection, starts Paho's background network loop, and stores the client. Connection failures are printed rather than crashing Flask startup.

**Why:** lets the web panel remain available even if the broker cannot be reached at startup.

### Flask route `index()` — `GET /`

Checks the optional token, builds all remote status values, and renders `templates/index.html` with devices, status, local controls, refresh interval, timestamp, and token.

**Why:** main control/status page.

### Flask route `wol(device_id)` — `POST /wol/<device_id>`

Checks token/device/existence/enabled state, sends WoL, flashes success/error, and redirects to the index.

**Why:** exposes only configured WoL targets through the web UI.

### Flask route `mqtt_button(device_id, button_id)` — `POST /mqtt/<device_id>/<button_id>`

Checks token/device/control/button definitions, publishes the preconfigured topic/payload, flashes the result, and redirects.

**Why:** browser users choose predefined actions rather than supplying arbitrary MQTT topic/payload values.

### Flask route `local_button(button_id)` — `POST /local/<button_id>`

Checks token and configured local button, runs the preconfigured script filename through `run_local_script()`, flashes the result, and redirects.

**Why:** browser users can only invoke local actions listed in `LOCAL_SERVER`.

### Module entry behavior

When executed directly, the module starts the MQTT listener and Flask on `0.0.0.0:5000`. When imported (for example by a WSGI loader), it also calls `start_mqtt_listener()`.

**Why:** current code expects status listening to accompany the Flask app in either launch style. Deployment with multiple imported worker processes should be reviewed because each importing process can start its own MQTT listener/client attempt.

---

## `homelab-panel/templates/index.html`

Jinja/HTML template for the dark control panel. It:

- auto-refreshes based on `PAGE_REFRESH_SECONDS`;
- renders flash messages;
- loops over all remote devices/statuses;
- renders enabled WoL buttons;
- renders configured MQTT control buttons;
- renders local action buttons;
- propagates the current token into generated form action URLs.

**Why:** keeps presentation separate from Flask/device configuration while making device sections data-driven.

---

## Local panel command scripts

All four use `set -euo pipefail` and call `sudo shutdown ...`.

### `homelab-panel/scripts/shutdown_delay.sh`

Schedules local shutdown in one minute and prints a Danish confirmation.

### `homelab-panel/scripts/shutdown_cancel.sh`

Runs `sudo shutdown -c` and prints a Danish confirmation.

### `homelab-panel/scripts/reboot_delay.sh`

Schedules local reboot in one minute and prints a Danish confirmation.

### `homelab-panel/scripts/reboot_cancel.sh`

Runs `sudo shutdown -c` and prints a Danish confirmation.

**Why these scripts exist:** `LOCAL_SERVER` buttons reference simple fixed script filenames, keeping privileged operating-system commands outside Flask route definitions.

---

## `homelab-panel/homelab-controll.service`

Current panel systemd unit. It runs `app.py` as the configured non-root user/group from its configured host-specific working directory and restarts on failure.

**Why:** provides automatic service startup/restart for the Flask panel. Paths/users are deployment-specific and must be reviewed before installation.

---

# Current external commands used by code

These are not project CLI flags; they are operating-system commands invoked by the application/scripts.

- `mosquitto_pub` — panel MQTT commands and remote shell status publication.
- `wakeonlan` — panel Wake-on-LAN packet transmission.
- `ping` — panel reachability check.
- `shutdown -h +1 ...` — schedule shutdown.
- `shutdown -r +1 ...` — schedule reboot.
- `shutdown -c` — cancel pending shutdown/reboot.
- `sudo` — used by local panel helper scripts around shutdown commands.

# Current supported application flags

There are **no supported CLI flags or subcommands** in version 0.0.1. All supported configuration is file-based and all user actions are web/MQTT/script based.
