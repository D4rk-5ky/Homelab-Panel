# commented_code_map.md

This file maps the current Homelab Panel codebase and explains what each function, route, script, service, command interface, and major data file does and why it exists.

## Root files

### `VERSION`
Stores the current release number.

### `README.md`
Current-use documentation only: installation, configuration, MQTT payloads, routes, commands, behavior, safety notes, and disclaimers.

### `VERSIONING.md`
Defines version increment/rollover rules and records release changes.

### `.gitignore`
Ignores the machine-specific active panel/control configuration files while explicitly preserving the three tracked `*.example.*` configuration files, and ignores runtime panel/control state/log directories.

**Why:** prevents host-specific settings, credentials, history state, and runtime logs from being committed while keeping complete configuration templates under version control.

---

## Shared project-root action scripts

These files live beside `homelab-panel/` and `homelab-control/`, so both components resolve the same action files without an absolute script path or duplicate script trees.

### `homelab_action_common.sh`
Finds the common project root and optionally loads `homelab-control/homelab_control_lib.sh` when the action runs as root and an active remote-agent config exists. It exposes `CONTROL_STATUS_ENABLED` and the shared `run_shutdown_command()` helper.

### `run_shutdown_command()`
Runs `shutdown` directly when already root; otherwise runs `sudo shutdown`.

**Why:** preserves the old remote-agent root behavior and old panel sudo behavior while letting both callers reuse the exact same action scripts.

### `shutdown_delay.sh`
Schedules shutdown in one minute. When remote control status integration is active, it also sets `shutdown_pending` and records/publishes running plus success/failure state.

### `shutdown_cancel.sh`
Cancels a pending shutdown/reboot. When remote control status integration is active, it sets idle and records/publishes the result.

### `reboot_delay.sh`
Schedules reboot in one minute. When remote control status integration is active, it also sets `reboot_pending` and records/publishes running plus success/failure state.

### `reboot_cancel.sh`
Cancels a pending shutdown/reboot. When remote control status integration is active, it sets idle and records/publishes the result.

**Why:** there is one allow-listed set of privileged action scripts for both the web panel and MQTT command listener, eliminating the previous duplicate copies under each component.

---

# `homelab-panel/`

## `homelab-panel/config.py`
Local-only panel runtime settings: WoL broadcast address, MQTT broker credentials/settings, optional username/password web authentication, Flask session secret/cookie behavior, legacy token gate, MQTT freshness TTL, page refresh interval, and the per-device panel-history cap. This file is created from `config.example.py` and is intentionally excluded from Git/release ZIPs.

## `homelab-panel/config.example.py`
Complete example copy of every panel configuration field, including the optional `WEB_AUTH_CONFIG` username/password/session settings and `PANEL_HISTORY_MAX_ENTRIES`.

## `homelab-panel/devices.py`
Local-only device configuration defining `REMOTE_DEVICES` and `LOCAL_SERVER`. Device records contain display data, WoL configuration, status/history topics, and allow-listed MQTT button definitions. This file is created from `devices.example.py` and is intentionally excluded from Git/release ZIPs.

## `homelab-panel/devices.example.py`
Complete example copy of the device/local-control configuration structure.

## `homelab-panel/app.py`
Flask application plus panel-side MQTT listener/control dispatcher.

### `web_auth_enabled() -> bool`
Returns whether `WEB_AUTH_CONFIG["enabled"]` is active.

**Why:** all login/session decisions use one normalized switch.

### `validate_web_auth_config() -> None`
When web login is enabled, requires non-empty credentials/session secret and rejects unchanged `CHANGE_ME` password/secret placeholders. When login is disabled, the legacy fallback session secret keeps existing 0.0.4 configurations working.

**Why:** authentication should fail closed at startup rather than silently run with missing/default credentials. Existing 0.0.4 configs without `WEB_AUTH_CONFIG` fall back to disabled login for upgrade compatibility.

### `session_authenticated() -> bool`
Checks the signed Flask session for the authenticated flag.

**Why:** templates/routes never need to inspect passwords or duplicate session details.

### `credentials_match(username, password) -> bool`
Compares submitted username/password with configured values using `hmac.compare_digest`.

**Why:** centralizes credential comparison and avoids ordinary early-exit string comparison.

### `require_web_login()` — Flask `before_request` guard
When web authentication is enabled, permits only the login/static endpoints before authentication and redirects all other requests to `/login`.

**Why:** a single guard protects current and future page/control routes instead of relying on every route author to remember a separate check.

### `check_token() -> bool`
When username/password web authentication is enabled, returns true because the `before_request` session guard is authoritative. Otherwise it preserves the legacy optional `PANEL_TOKEN` query-string check.

**Why:** existing token-only installations remain compatible while login-enabled installations do not require both a session and URL token.

### `run_command(cmd, timeout=20) -> tuple[bool, str]`
Runs an external command without a shell, captures output, applies a timeout, and returns success plus a useful message.

**Why:** centralizes safe subprocess invocation and avoids duplicating return-code/error handling.

### `mqtt_publish(topic, payload) -> tuple[bool, str]`
Builds a `mosquitto_pub` command from `MQTT_CONFIG` and calls `run_command()`.

**Why:** one reusable path handles all panel-originated MQTT publication.

### `send_wol(mac) -> tuple[bool, str]`
Runs `wakeonlan -i <broadcast> <mac>` through `run_command()`.

**Why:** centralizes Wake-on-LAN behavior for both web actions and MQTT-driven panel actions.

### `run_local_script(script_name) -> tuple[bool, str]`
Resolves the configured script filename in the common project root (the parent directory of `homelab-panel/`), verifies it exists and is executable, then runs it.

**Why:** local web actions remain restricted to configured script filenames rather than arbitrary commands.

### `ping_host(ip) -> bool`
Runs one short ping to the configured device IP and returns that ICMP result without depending on MQTT state.

**Why:** ping is an independent connectivity signal. The UI must still show a successful ping when MQTT is unavailable, while combined Online status is decided later by `evaluate_remote_device_status()`.

### `set_mqtt_state(topic, payload) -> str | None`
Stores the latest received status/history payload and local receipt time under a lock, then returns the previous payload when one existed.

**Why:** MQTT callbacks run in a background thread while Flask reads state, and online-transition handling needs to know whether a power message actually changed from non-online to `online`.

### `set_mqtt_connected(value) -> None`
Updates the module MQTT connection flag.

### `get_mqtt_connected() -> bool`
Returns the module MQTT connection flag.

**Why:** MQTT device status only counts as currently online while the panel itself is connected to the broker; this prevents a cached `online` payload from producing a false combined Online result after disconnect.

### `get_mqtt_state(topic) -> dict | None`
Returns stored MQTT state for a non-empty topic under the state lock.

**Why:** one thread-safe state lookup path is reused by status/history helpers.

### `get_mqtt_payload_and_age(topic) -> tuple[str | None, int | None]`
Returns a stored payload plus seconds since the panel received it.

**Why:** power state must be both correct and fresh.

### `action_to_danish(payload) -> str`
Maps protocol action values such as `idle`, `shutdown_pending`, and `reboot_pending` to Danish UI text.

**Why:** protocol values remain stable while the UI stays readable.

### `result_to_danish(payload) -> str`
Maps `none`, `unknown`, `running`, `sent`, `success`, and `failure` to Danish UI text. `sent` is shown as `Afsendt` so a successful panel dispatch is not mislabeled as confirmed remote success.

**Why:** separates stored protocol values from display wording and preserves the distinction between dispatch success and remote execution success.

### `command_to_danish(payload) -> str`
Displays missing/`none`/`unknown` current commands as `Ingen` and maps the panel-control IDs (`power_on`, shutdown/cancel, reboot/cancel) to readable Danish labels. Arbitrary remote shell command text is still passed through unchanged.

**Why:** cleared sentinel values and machine-oriented panel command IDs should not leak directly into the UI.

### `get_history_topic_for_status_cfg(status_cfg) -> str`
Returns explicit `history_topic` when configured; otherwise derives a sibling `/history` topic from a standard `/last_message` topic.

**Why:** older local `devices.py` files can gain history without an immediate config migration while explicit topic configuration remains authoritative.

### `load_panel_history_unlocked() -> dict`
Loads/validates persistent panel-originated history from `homelab-panel/state/panel_action_history.json`.

### `save_panel_history_unlocked(history) -> None`
Atomically writes panel action history through a temporary file.

**Why:** panel history should survive a panel restart without exposing a partially written JSON file.

### `append_panel_history_event(device_id, record) -> None`
Appends one panel-originated event for a configured remote device and trims that device to `PANEL_HISTORY_MAX_ENTRIES`.

### `get_panel_history(device_id) -> list[dict]`
Returns copies of the persisted panel events for one device under the history lock.

### `clear_panel_action_state(device_id) -> None`
Removes only the provisional in-memory current panel action for one device. It does not delete the persisted history event.

### `handle_device_power_transition(topic, previous_payload, payload) -> None`
Detects a configured device power topic changing from unknown/non-online to `online` and clears that device's provisional current panel action.

**Why:** a newly online device must start with a clean current panel status while the prior WoL/control dispatch remains available in history. Repeated `online` heartbeats do not repeatedly clear state.

### `history_timestamp_sort_key(entry) -> str`
Provides the timestamp/archived-time key used to sort merged panel and remote history newest-first.

### `record_panel_action(device_id, command, ok, message, source, event_epoch, event_timestamp) -> None`
Stores the most recent panel-originated action in thread-safe provisional `PANEL_ACTION_STATE` and appends the same event to persistent per-device panel history. Successful dispatch is stored as protocol result `sent`; failures as `failure`.

**Why:** the action is visible immediately in the status card, but it is also preserved after the device comes online or the panel process restarts.

### `get_panel_action_state(device_id) -> dict | None`
Returns a copy of the current provisional panel-action record for one device under a lock.

**Why:** status rendering must not expose or race on the mutable shared dictionary used by the MQTT worker thread and Flask request threads.

### `get_remote_command_state_received_at(status_cfg) -> float`
Finds the newest local receipt timestamp among the configured remote `last_command`, `last_result`, `last_message`, and `last_updated` MQTT fields.

**Why:** lets the panel decide whether its own provisional action or the remote agent's command state is newer without comparing wall clocks from different machines.

### `get_device_history(device_id, device) -> list[dict]`
Loads the retained remote history from the explicit/derived history topic, validates/normalizes each event, merges it with persistent panel-originated history for the same device, and sorts the combined list newest-first.

**Why:** one device history page must include both the panel dispatch message and every remote execution-status message instead of losing intermediate events.

### `evaluate_remote_device_status(device_id, device) -> dict`
Pings a device independently, reads all configured MQTT status fields, reads the panel's current MQTT-broker connection flag, applies the freshness TTL, and builds the display model for one status card. Ping and MQTT each get their own result. Combined status is green `Online` only when ping and a fresh MQTT `online` signal are simultaneously valid while the broker connection is active; one valid side becomes yellow `Ikke fuldt online`; neither becomes red `Offline`. For command/result/message/time fields it compares the latest provisional panel action with the latest locally received remote command state: a newer panel action is shown immediately, but a later remote-agent update automatically takes over.

**Why:** preserves independent diagnostics (especially ping before MQTT is available), prevents stale/cached MQTT from causing a false Online state, and keeps the strict requirement that both health signals agree before the device is called Online.

### `build_remote_device_statuses() -> dict`
Calls `evaluate_remote_device_status(device_id, device)` for every configured remote device.

**Why:** keeps the index route small and data-driven.

### `execute_remote_action(device_id, command) -> tuple[bool, str]`
Central allow-listed action dispatcher used underneath both web routes and incoming panel-control MQTT. Successful WoL/MQTT dispatches return an informative message suitable for both logs and the provisional panel status.

Behavior:

- `power_on` resolves only the configured/enabled WoL MAC and calls `send_wol()`.
- `shutdown` aliases to the configured `shutdown_delay` button.
- `reboot` aliases to the configured `reboot_delay` button.
- all other remote commands must match an existing `mqtt_controls.buttons[].id` for that exact device.
- the published topic/payload always comes from `devices.py`; incoming MQTT cannot choose an arbitrary target topic or shell command.

**Why:** all target/topic/payload authorization remains centralized instead of drifting across callers.

### `execute_and_record_remote_action(device_id, command, source) -> tuple[bool, str]`
Captures the action-start time, calls `execute_remote_action()`, then records the provisional result through `record_panel_action()`. Both the incoming panel MQTT path and web remote-action routes use this helper.

**Why:** guarantees that actions from either interface get the same immediate status-card feedback while reusing the existing allow-listed dispatcher.

### `process_panel_control_message(payload) -> None`
Parses incoming panel-control JSON, requires a JSON object containing `device_id` and `command`, calls `execute_and_record_remote_action()` with the configured panel-control topic as the source label, and logs success/failure.

**Why:** gives Home Assistant/other MQTT clients a structured control interface and now also makes those externally initiated actions visible in Homelab Panel.

### `on_connect_compat(*args)`
Marks the panel connected, discovers all configured device status/history topics plus the optional panel-control topic, and subscribes to each unique topic.

**Why:** subscriptions automatically follow configuration and reconnects.

### `on_disconnect_compat(*args)`
Marks the panel disconnected and logs the event.

### `on_message_compat(client, userdata, msg)`
Routes received MQTT messages:

- if the message is on `panel_control_topic`, retained messages are rejected;
- non-retained panel-control messages are processed on a daemon thread so WoL/MQTT subprocess execution does not block the Paho callback loop;
- all other subscribed messages are stored as status/history state;
- power-topic payload changes are passed to `handle_device_power_transition()` so a newly online device drops provisional current panel state without deleting history.

**Why:** separates control traffic from status traffic, prevents dangerous retained command replay, and gives device-online transitions explicit current-state cleanup.

### `build_mqtt_client()`
Creates a Paho MQTT v3.1.1 client with VERSION2 callback API when available and a legacy fallback, then sets reconnect backoff.

**Why:** maintains compatibility across Paho versions.

### `start_mqtt_listener() -> None`
Builds the MQTT client, applies optional broker credentials, installs compatibility callbacks, schedules an asynchronous broker connection with `connect_async()`, starts the network loop immediately, and stores the client globally. The reconnect delay configured in `build_mqtt_client()` allows the MQTT client to keep trying when the broker is unavailable at panel startup. Startup/setup failures are logged without crashing the Flask app.

**Why:** Flask and independent ping/status rendering must remain available before MQTT connects, while MQTT should be able to come online later without restarting Homelab Panel.


### `login()` — `GET/POST /login`
Public login endpoint only when web authentication is enabled. GET renders the login form; POST validates credentials, clears any previous session, stores only authenticated state/username, and redirects to the dashboard. When login is disabled it redirects to `/`.

**Why:** credentials never need to appear in URLs and the password is not stored in the session.

### `logout()` — `POST /logout`
Clears the browser session and redirects to `/login` when authentication is enabled, otherwise back to `/`.

**Why:** provides an explicit way to invalidate the current authenticated browser session.

### `index()` — `GET /`
After the global session guard and legacy token check, builds remote statuses and renders `templates/index.html`.

**Why:** main dashboard/status/control page.

### `device_history(device_id)` — `GET /history/<device_id>`
After the global session guard, checks legacy token/device, loads the selected device's parsed retained history, and renders `templates/history.html`.

**Why:** gives every remote status card a dedicated history view without crowding the main page.

### `wol(device_id)` — `POST /wol/<device_id>`
After the global session guard, checks legacy token/device and calls `execute_and_record_remote_action(device_id, "power_on", "Webpanel")` so WoL appears immediately in the device status card.

**Why:** web WoL uses the same core dispatcher as MQTT-driven WoL.

### `mqtt_button(device_id, button_id)` — `POST /mqtt/<device_id>/<button_id>`
After the global session guard, checks legacy token/device and passes the configured button ID to `execute_and_record_remote_action(..., "Webpanel")` so remote MQTT button dispatch is immediately visible in the device status card.

**Why:** browser remote actions and MQTT remote actions use the same allow-list logic.

### `local_button(button_id)` — `POST /local/<button_id>`
After the global session guard, looks up a local button in `LOCAL_SERVER` and executes its configured script via `run_local_script()`.

**Why:** local actions remain fixed/configured rather than accepting arbitrary user commands.

### Module entry behavior
Validates web-auth/session configuration first, then starts the MQTT listener whether executed directly or imported; direct execution also starts Flask on `0.0.0.0:5000`.

**Why:** MQTT status/control listening accompanies the web application. Multi-worker WSGI deployments should be reviewed because each importing worker could attempt its own MQTT client.

---

## `homelab-panel/templates/index.html`
Main dark dashboard template. It renders:

- three-state combined remote status (Online / Ikke fuldt online / Offline);
- independent ping and MQTT indicators so one working signal remains visible when the other is unavailable;
- a History button in every remote status card;
- Wake-on-LAN buttons;
- configured remote MQTT buttons;
- configured local controls;
- flash messages and auto-refresh;
- authenticated username plus POST logout control when web login is enabled.

## `homelab-panel/templates/login.html`
Standalone username/password form used only when optional web authentication is enabled. It displays a generic failed-login message and does not place credentials in the URL.

**Why:** unauthenticated users need exactly one minimal public application page before the global request guard allows access to the panel.

## `homelab-panel/templates/history.html`
Per-device history page. It renders newest-first history in three separate categories:

- Command history;
- Result history;
- Message history.

Every item shows the original event timestamp. When web login is enabled, the page also exposes a POST logout control.

---

## `homelab-panel/homelab-controll.service`
Systemd unit for the panel using deployment-specific user/group/path values.

---

# `homelab-control/`

## `homelab-control/config.json`
Local-only remote-agent runtime configuration created from `config.example.json`; intentionally excluded from Git/release ZIPs.

Remote runtime MQTT/client/topic/timing/command mapping configuration.

## `homelab-control/config.example.json`
Complete example of every current remote configuration option, including `status_history` and `history_max_entries`.

## `homelab_control_command_listener.py`
Remote MQTT payload-to-script listener.

### `load_config() -> dict`
Reads `config.json`.

### `run_script(script_name) -> None`
Resolves the mapped filename in the common project root (the parent directory of `homelab-control/`), checks file/executable status, and runs it with a timeout.

**Why:** received MQTT text is never executed directly as shell input.

### `on_connect(*args)`
Subscribes to the configured `control_power` topic at QoS 1.

### `on_message(client, userdata, msg)`
Decodes the payload, looks it up in `COMMAND_MAP`, rejects unknown values, and runs only the configured mapped script.

### `build_client()`
Creates a Paho MQTT v3.1.1 client with new/legacy API compatibility.

### `main() -> int`
Applies credentials, attaches callbacks, connects, and enters `loop_forever()`.

---

## `homelab_control_status_indicator.py`
Remote retained status/history publisher, event-history reader, and boot-transition state manager.

### `load_config() -> dict`
Reads `config.json`.

### `derive_history_topic() -> str`
Returns configured `topics.status_history`, or derives `<prefix>/history` from `topics.status_last_message=<prefix>/last_message` when an older active config lacks the explicit history key.

**Why:** keeps old local configs compatible while retaining explicit topic control in current examples.

### `ensure_dirs() -> None`
Creates runtime `state/` and `logs/` directories.

### `read_text_file(path, default="") -> str`
Reads stripped text and returns a default for missing/empty/unreadable files.

### `write_text_file(path, value) -> None`
Writes through a temporary file and atomically replaces the destination.

**Why:** readers should not observe partially written state files.

### `read_action() -> str`
Reads action with `idle` fallback.

### `write_action(value) -> None`
Writes action using the atomic text writer.

### `get_uptime_seconds() -> int`
Reads `/proc/uptime` and returns whole seconds or `-1` on error.

### `get_current_boot_id() -> str`
Reads Linux `/proc/sys/kernel/random/boot_id`.

**Why:** a machine reboot can be distinguished from a mere service restart.

### `get_boot_time_epoch() -> float | None`
Computes approximate boot epoch from current time minus uptime.

**Why:** migration from 0.0.1 has no stored boot ID; boot time lets the code decide whether existing command state clearly belongs to an earlier boot.

### `parse_timestamp(value) -> float | None`
Parses the existing ISO-style timestamp to epoch seconds.

### `load_history() -> list[dict]`
Reads and validates `state/history.json`; malformed/missing history safely behaves as empty.

### `save_history(entries) -> None`
Keeps only the newest `HISTORY_MAX_ENTRIES`, writes formatted JSON via temporary file, and atomically replaces `history.json`.

**Why:** history persists across reboots without unbounded growth.

### `current_command_record() -> dict | None`
Builds an archive record from current last-command/result/message/timestamp. Sentinel/empty state returns `None`.

**Why:** boots with no meaningful previous command should not create useless history entries.

### `history_record_signature(record) -> tuple[str, str, str, str]`
Builds the timestamp/command/result/message identity used for boot-rollover deduplication.

### `append_history_record(record, deduplicate=False) -> bool`
Appends a history record through the existing capped save path, optionally refusing an identical already-stored event.

### `archive_current_command_status() -> bool`
Archives a meaningful pre-boot current command only when an identical event is not already present.

**Why:** event history is recorded immediately, so boot cleanup must preserve migration data without duplicating the final event.

### `clear_current_command_status() -> None`
Clears current-boot command/result/message and updates `last_updated` to the clearing time.

**Why:** a new boot begins with clean current-command fields while previous data remains in history.

### `is_new_machine_boot(current_boot_id) -> bool`
Compares stored/current boot IDs. When no stored ID exists yet, it falls back to comparing existing `last_updated` against calculated current boot time.

**Why:** avoids false history rollover on service restarts and handles upgrades from 0.0.1 safely.

### `initialize_boot_state() -> bool`
Performs boot transition handling: deduplicate/archive any old meaningful current command, clear current fields, reset action to `idle`, and save the current boot ID. Returns whether a real new boot was detected.

### `publish(topic, payload, retain=True, qos=1) -> None`
Publishes through the active Paho client and ignores empty topic strings.

### `publish_history() -> None`
Serializes the capped history list to compact JSON and publishes it retained on `status_history` when configured.

### `publish_command_status() -> None`
Publishes retained current command/result/message/update values.

### `on_connect(*args)`
Publishes online state, action, hostname, current command status, and retained history after each MQTT connection.

**Why:** panel state/history repopulates after panel or broker reconnects.

### `on_disconnect(*args)`
Current no-op callback placeholder.

### `uptime_loop()`
Periodically republishes retained online state and uptime.

### `action_sync_loop()`
Polls the local action file and republishes only when the value changes.

### `command_status_sync_loop()`
Polls current command files and republishes the retained set whenever it changes.

### `build_client()`
Creates compatible Paho MQTT client.

### `main() -> int`
Creates runtime directories/default action, initializes boot/history state, creates missing current-state defaults, configures MQTT/LWT, starts sync threads, handles SIGTERM/SIGINT, and publishes offline before clean shutdown.

### `handle_signal(signum, frame)`
Nested signal handler created by `main()` that sets the shared stop event for SIGTERM/SIGINT.

**Why:** lets the status service leave its main loop and run the existing clean-shutdown/offline publication path instead of terminating abruptly.

---

## `homelab_control_lib.sh`
Shared remote script helper.

### `json_get()`
Reads a required dotted path from `config.json` using Python JSON parsing.

### `json_get_optional()`
Reads an optional dotted path and returns a caller-supplied default when it is absent.

**Why:** history additions remain compatible with older active configs that do not yet contain `status_history` or `history_max_entries`.

### `ensure_dirs()`
Creates state/log directories.

### `timestamp_now()`
Returns local ISO-like date/time.

### `mqtt_pub(topic, payload)`
Publishes a retained QoS 1 status value using configured broker credentials; empty topics are safely ignored.

### `write_action(value)`
Writes the local action file.

### `append_command_history(command, result, message, timestamp)`
Uses a small Python helper plus `fcntl.flock` to append one event to `state/history.json`, cap it to `history_max_entries`, and atomically replace the file.

**Why:** every command-status transition must survive even if the next transition overwrites the current files almost immediately.

### `history_payload()`
Reads/validates history and prints compact JSON suitable for MQTT.

### `publish_history()`
Publishes the complete retained history on the explicit or automatically derived history topic.

### `write_command_status(command, result, message)`
Writes current command/result/message/time, appends `logs/commands.log`, immediately appends the exact event to history, publishes the four current retained status fields, then republishes retained history.

**Why:** the history page must contain all sent execution messages, not just whichever message happened to be current at the next reboot.

### `set_idle()`
Writes/publishes `idle`.

### `set_shutdown_pending()`
Writes/publishes `shutdown_pending`.

### `set_reboot_pending()`
Writes/publishes `reboot_pending`.

---

## Remote systemd units

### `homelab-control-command-listener.service`
Runs the remote command listener as root using deployment-specific paths.

### `homelab-control-status-indicator.service`
Runs the remote status/history publisher as root using deployment-specific paths.

---

# Command interfaces

## Panel-control MQTT JSON
Topic: `MQTT_CONFIG["panel_control_topic"]`.

Required keys:

- `device_id`
- `command`

Recognized command names:

- `power_on`
- `shutdown`
- `shutdown_delay`
- `shutdown_cancel`
- `reboot`
- `reboot_delay`
- `reboot_cancel`

`shutdown` and `reboot` are aliases to the configured delayed controls. Retained incoming panel-control messages are rejected.

## Direct remote-agent MQTT payloads
Default allow-list:

- `shutdown_delay`
- `shutdown_cancel`
- `reboot_delay`
- `reboot_cancel`

## External OS commands used

- `mosquitto_pub`
- `wakeonlan`
- `ping`
- `shutdown -h +1 ...`
- `shutdown -r +1 ...`
- `shutdown -c`
- `sudo` for local panel helper scripts

## CLI flags
There are no supported CLI flags, subcommands, or positional runtime arguments in version 0.0.2. Configuration remains file-based.
