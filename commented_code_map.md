# commented_code_map.md

Current-code map for Homelab Panel. This is not release history; it explains what each current function/command/file does and why it exists.

## `homelab-panel/app.py`

| Function | What / why |
|---|---|
| `web_auth_enabled()` | Returns whether optional session login is enabled; centralizes the feature gate so routes do not implement their own auth rules. |
| `validate_web_auth_config()` | When login is enabled, rejects empty username/password/secret and password/secret values containing `CHANGE_ME`; catches incomplete setup before startup. It does not check password strength or every possible placeholder. |
| `session_authenticated()` | Checks the Flask session authentication flag; keeps password data out of the session. |
| `credentials_match()` | Compares supplied/configured username and password with constant-time comparison; reduces trivial timing leakage. |
| `require_web_login()` | Global before-request guard protecting pages, actions and JSON updates; redirects ordinary requests and returns JSON 401 for API/fetch clients. |
| `private_web_response()` | Adds private/no-store and Vary: Cookie to dynamic responses, including JSON and action results. |
| `action_response()` | Returns JSON to the initiating fetch request or preserves normal form redirect/flash behavior. |
| `build_device_status()` | Combines measured ping with current or batch-supplied MQTT/runtime/jobs. Its nested `payload_and_age()` reuses the shared MQTT resolver. Emits a stable receive timestamp rather than age text and reads per-device runtime once; never probes devices. |
| `dashboard_updates()` | Protected GET /api/dashboard returning per-browser changed fragments plus revision/instance/time metadata. |
| `run_command()` | Runs a fixed argv command with timeout and captured output; avoids shell=True and gives callers one error format. |
| `load_json_file()` | Uses PanelJsonCache to parse one version per state file, return isolated copies, and detect changes/deletion/corruption. |
| `save_json_file_atomic()` | Writes JSON via temporary file + replace; prevents readers seeing partially written state. |
| `get_device_button()` | Finds a configured mqtt_controls button by ID; the same allow-list drives web, panel MQTT, jobs and HA. |
| `resolve_confirmation_text()` | Replaces the optional `$TITLE` token with the owning device title for browser prompts; literal text remains unchanged and the template performs JSON-safe JavaScript encoding. |
| `get_device_category()` | Returns `power` for the built-in WoL actions or the configured button category for remote commands; keeps job/history categorization tied to current configuration. |
| `_device_status_cache_snapshot()` | Copies the monitor cache under lock for HA birth snapshots; keeps lock ownership in `app.py` while the HA module receives an isolated status dictionary. |
| `load_runtime_state_unlocked()` | Loads persistent per-device runtime/expected-state data; state survives panel restart. |
| `save_runtime_state_unlocked()` | Atomically saves runtime state; avoids corruption during monitor updates. |
| `get_device_runtime()` | Returns one device runtime state under lock; callers cannot mutate shared data unsafely. |
| `update_device_runtime()` | Merges and persists per-device runtime fields under lock; centralizes expected/transition state writes. |
| `get_expected_state()` | Returns expected state from an optional batched runtime record or the existing live reader, then the device default; keeps planned-downtime interpretation in one function. |
| `set_expected_state()` | Persists expected state, reason and timestamp; power workflows can explain why offline is expected. |
| `load_panel_jobs_unlocked()` | Loads persistent panel-side job records; job display survives panel restarts. |
| `save_panel_jobs_unlocked()` | Caps and atomically saves panel jobs; prevents unbounded runtime growth. |
| `update_panel_job()` | Creates/updates one panel job by ID; all lifecycle writers share the same format. |
| `get_panel_jobs()` | Returns a copy of stored panel jobs for one device; protects shared state. |
| `history_contains_event()` | Checks whether a remote job lifecycle event was already archived; prevents retained snapshot duplicates after reconnect/restart. |
| `record_device_event()` | Creates a normalized categorized history record and appends it; one event schema is used across power, MQTT, availability and jobs. |
| `active_job_status()` | Defines which lifecycle states count as active (`queued`, `running`, `waiting`, `confirming`); `timed_out` is deliberately terminal/non-active. |
| `apply_job_timeout()` | Builds a non-mutating job view that applies the optional per-button `job_timeout_seconds`, exposes a remaining-seconds counter, and converts unresolved active work to `timed_out` with an explicit note when the deadline passes. |
| `combined_device_jobs()` | Merges panel/remote sources through PanelJobsCache and applies the shared timeout evaluator with an optional batch time/source snapshot; direct monitor/HA callers retain live defaults. |
| `ping_host()` | Runs one bounded ping with Linux seconds or macOS milliseconds for `-W`; ping remains independent from MQTT. |
| `action_to_danish()` | Maps internal action states to Danish UI text while preserving unknown custom values. |
| `result_to_danish()` | Maps lifecycle/result states to Danish UI text while preserving custom values. |
| `command_to_danish()` | Maps built-in power commands to friendly Danish labels; custom command IDs still remain visible. |
| `load_panel_history_unlocked()` | Loads per-device panel event history and tolerates missing/corrupt runtime files. |
| `save_panel_history_unlocked()` | Atomically saves panel history. |
| `append_panel_history_event()` | Appends and caps one device event; prevents unlimited history growth. |
| `get_panel_history()` | Returns a copy of one device panel history under lock. |
| `clear_panel_action_state()` | Clears provisional current-card panel action; old command remains in persistent history. |
| `handle_device_power_transition()` | Clears provisional panel action when remote MQTT transitions online; a fresh boot/session does not display stale command state. |
| `history_timestamp_sort_key()` | Returns a stable timestamp key for merged panel/remote history sorting. |
| `record_panel_action()` | Stores a panel-originated dispatch as provisional current state and permanent categorized history. |
| `get_panel_action_state()` | Returns provisional current panel action safely. |
| `get_remote_command_state_received_at()` | Finds newest receive time across remote current command topics; decides whether remote truth supersedes provisional panel state. |
| `get_device_history()` | Merges remote retained history and panel event history with normalized fields; one page shows the full device journal. |
| `evaluate_remote_device_status()` | Actively measures ping in the monitor, then delegates to build_device_status(); web routes never call this measurement path. |
| `build_remote_device_statuses()` | Checks source identities and server deadlines before reusing one shared prepared view. Its nested `build()` loads runtime/jobs once, snapshots MQTT once, builds all devices, and computes the next MQTT/monitor/job expiry. Web views never ping. |
| `device_mqtt_online()` | Tests current connected/fresh power=online state; confirmation workers use the same strict MQTT rule. |
| `device_mqtt_offline()` | Tests current connected/fresh power=offline state; shutdown/reboot are not confirmed merely by publish success. |
| `execute_and_record_remote_action()` | Creates panel job/history around dispatch and starts expected-state/power confirmation when relevant; web and panel-control MQTT share one path. |
| `process_panel_control_message()` | Parses panel-control JSON. Remote commands require `device_id`; explicit `target=local` requires a configured local button ID and rejects any `device_id` field. Unknown/missing remote devices never fall back to the panel host. Retained messages are rejected by the receive callback before dispatch. |
| `process_remote_jobs_message()` | Parses retained remote job snapshots, archives unseen lifecycle changes and merges matching job IDs; script exit results reach the dashboard without using panel-control. |
| `handle_boot_id_message()` | Detects changed remote boot ID, clears provisional panel command state and records boot event; service restarts with same boot ID do not look like new boots. |
| `format_duration()` | Formats seconds for uptime/transition display. |
| `monitor_device_transition()` | Persists true combined-state transitions and previous-state duration, marking unexpected offline as errors. |
| `status_monitor_loop()` | Periodically evaluates devices independent of page views, updates cache/history and HA state; ping works even when MQTT is absent. |
| `start_status_monitor()` | Starts exactly one background monitor thread per process. |
| `login()` | GET/POST login route; creates session only after credential match. |
| `logout()` | POST route that clears the web session. |
| `index()` | Renders the shell with shared cached status/job fragments and private username/flash content. |
| `device_history()` | Per-device event/history route with category/errors filtering. |
| `wol()` | POST web route starting the shared asynchronous WoL workflow. |
| `wol_cancel()` | POST route cancelling an active WoL retry/confirmation workflow. |
| `mqtt_diagnostics()` | Protected diagnostics route showing broker/subscription/expected-topic state. |
| `mqtt_button()` | POST route dispatching any configured dynamic remote button through the shared action path. |
| `local_button()` | Protected POST route calling execute_local_action(); returns a per-request JSON result or ordinary redirect/flash through action_response(). |


## `homelab-panel/modules/panel_actions.py`

`PanelActionManager` owns action mechanics that previously made `app.py` large. It receives configuration/state callbacks from the app instead of duplicating persistence, history, status evaluation, or config globals.

| Method | What / why |
|---|---|
| `PanelActionManager.__init__()` | Stores dynamic config/callback providers and creates private WoL/power-confirmation locks/state; dependency injection keeps the module reusable and avoids circular imports. |
| `PanelActionManager.send_wol()` | Builds the fixed `wakeonlan -i BROADCAST MAC` argv and uses the app's bounded `run_command()` callback; no shell text is accepted. |
| `PanelActionManager.configured_job_timeout_seconds()` | Resolves and validates the optional positive `job_timeout_seconds` on one configured remote button; app display logic and power-confirmation workers reuse the same interpretation instead of duplicating timeout parsing. |
| `PanelActionManager.run_local_script()` | Enforces direct filename, scripts-directory containment, file existence and executable permission before invoking the app command runner; preserves local path-traversal safety in one implementation. |
| `PanelActionManager.execute_local_action()` | Resolves only configured `LOCAL_SERVER.buttons` IDs and calls the injected app-level script runner; web/HA/MQTT clients still cannot provide a script path. |
| `PanelActionManager.wol_job_active()` | Checks the manager-owned WoL job registry under lock; used by UI/state publishing and duplicate-start prevention. |
| `PanelActionManager._finish_wol_job()` | Finalizes WoL expected state, panel job, history and active marker through injected app persistence callbacks; all terminal outcomes share one path. |
| `PanelActionManager._wol_worker()` | Performs retryable WoL sends, bounded ping confirmation and optional fresh MQTT-online confirmation asynchronously; records attempts/results through app callbacks. |
| `PanelActionManager.start_wol_job()` | Validates configured WoL settings, rejects duplicate active jobs, creates cancellation state and starts `_wol_worker()`. |
| `PanelActionManager.cancel_wol_job()` | Signals an active WoL job and records the request; it cannot create or cancel arbitrary commands. |
| `PanelActionManager.cancel_power_confirmation()` | Signals the current shutdown/reboot confirmation event for one device. |
| `PanelActionManager.power_confirmation_worker()` | Confirms shutdown by ping+MQTT offline and reboot by offline-then-ping+MQTT-online. A button lifecycle timeout overrides the legacy confirmation fallback; expiry records `timed_out`/warning rather than falsely classifying an unconfirmed action as `failure`. |
| `PanelActionManager.execute_remote_action()` | Resolves only current WoL/cancel-WoL IDs or a configured remote button and publishes the required JSON `command`/`job_id`/`source` envelope through `shared_modules/mqtt.py`. |

## `homelab-panel/modules/panel_home_assistant.py`

`HomeAssistantIntegration` contains only MQTT Discovery/state formatting and publication. It receives current configs/devices/cache/jobs/WoL state via callbacks, so it does not own panel state or command execution.

| Method | What / why |
|---|---|
| `HomeAssistantIntegration.__init__()` | Stores dynamic providers/callbacks for configs, devices, MQTT publication, status cache, jobs and WoL state; keeps HA logic independent of Flask globals. |
| `HomeAssistantIntegration.enabled()` | Returns the current `HOME_ASSISTANT_CONFIG.enabled` feature gate. |
| `HomeAssistantIntegration.state_topic()` | Builds the per-device state topic from the configured state prefix. |
| `HomeAssistantIntegration.device_block()` | Builds stable HA device-registry metadata from the required current remote `title`. |
| `HomeAssistantIntegration.publish_button()` | Publishes one configured MQTT button discovery document with non-retained command semantics and configurable retained discovery. |
| `HomeAssistantIntegration.publish_discovery()` | Publishes remote sensors, WoL/cancel controls, all configured remote buttons, and local buttons using required `LOCAL_SERVER["name"]`; all remote control payloads include explicit `target="remote"`. |
| `HomeAssistantIntegration.publish_snapshot()` | Publishes panel availability, discovery and cached states on broker connect/HA birth without performing ping I/O in the callback. |
| `HomeAssistantIntegration.publish_state()` | Publishes retained per-device combined status, ping/MQTT, uptime, command, expected state, latest job and WoL-active JSON. |

## `homelab-panel/modules/panel_mqtt.py`

`PanelMqttRuntime` owns only panel-specific MQTT topic selection, cache, diagnostics, routing, HA birth handling, and panel event hooks. It never constructs a Paho client or performs broker transport directly; those mechanics live in root `shared_modules/mqtt.py`.

| Method | What / why |
|---|---|
| `PanelMqttRuntime.__init__()` | Stores dynamic panel providers/callbacks plus panel receive cache, subscription set and diagnostics metadata. The actual long-running transport object is created lazily from the shared module. |
| `PanelMqttRuntime.set_state()` | Stores payload/receive metadata under lock, increments source revision and returns the previous payload; incoming updates invalidate prepared dashboard state. |
| `PanelMqttRuntime.set_connected()` | Stores broker connectivity plus connect/disconnect timestamps/reason for current panel status evaluation and diagnostics. |
| `PanelMqttRuntime.get_state()` | Returns an isolated copy of one cached topic record. |
| `PanelMqttRuntime.get_payload_and_age()` | Resolves a live topic or batch snapshot with optional shared time; clamps negative ages after clock rewinds and preserves integer-second TTL evaluation. |
| `PanelMqttRuntime.snapshot()` | Copies receive metadata once under lock for a consistent prepared rebuild; immutable payload strings are shared. |
| `PanelMqttRuntime.publish_direct()` | Sends HA/telemetry through the shared long-running `MqttClient.publish()` path; no Paho publish handling is duplicated here. |
| `PanelMqttRuntime.subscription_topics()` | Builds the panel-specific topic set from the explicit current status-topic keys, panel control topic and optional HA birth topic; shared `MqttClient` performs subscribe calls. |
| `PanelMqttRuntime.build_diagnostics()` | Builds `/mqtt-diagnostics` rows from panel cache/subscription metadata and expected device topics. |
| `PanelMqttRuntime._connected()` | Runs only panel work after the shared client has connected/subscribed: update diagnostics, publish HA snapshot and record connect/reconnect history. |
| `PanelMqttRuntime._disconnected()` | Runs only panel disconnect work: update diagnostics and append per-device broker-disconnect history. |
| `PanelMqttRuntime._message()` | Handles the shared decoded callback shape `(topic, payload, retain, qos)`: cache, retained-control rejection, worker dispatch, HA birth, status/jobs/boot routing. Full telemetry prints only when optional `log_payloads` is True; error, connection and action logs remain independent. |
| `PanelMqttRuntime._ensure_transport()` | Creates one shared `MqttClient` with current panel settings, subscriptions, callbacks, reconnect policy and optional HA Last Will. |
| `PanelMqttRuntime.start()` | Starts the panel monitor and the shared client in asynchronous-threaded reconnect mode. |

## Flask routes

- `GET/POST /login` → `login()` — only public application route when optional session auth is enabled.
- `POST /logout` → `logout()` — clears authenticated session.
- `GET /` → `index()` — dashboard shell, cached cards and private session fields.
- `GET /api/dashboard` → `dashboard_updates()` — incremental JSON with since/instance cursors; never consumes flashes.
- `GET /history/<device_id>` → `device_history()` — merged event journal with filters.
- `POST /wol/<device_id>` → `wol()` — starts async WoL retry/confirmation.
- `POST /wol-cancel/<device_id>` → `wol_cancel()` — cancels active WoL job.
- `POST /mqtt/<device_id>/<button_id>` → `mqtt_button()` — dispatches configured dynamic button only.
- `GET /mqtt-diagnostics` → `mqtt_diagnostics()` — broker/subscription/expected-topic troubleshooting page.
- `POST /local/<button_id>` → `local_button()` — runs configured local script only.

## Panel templates

- `templates/index.html` — combined ping+MQTT status, expected state, current command fields, parallel job dashboard, WoL/cancel, all dynamic MQTT buttons, local controls and diagnostics link; browser confirmations resolve optional `$TITLE` and use JSON-safe JavaScript string encoding.
- `templates/_device_status.html` — escaped shared device/status fields and optional WoL cancel form; no session or flash data.
- `templates/_device_jobs.html` — escaped shared job list items with stable job IDs for scroll anchoring.
- `templates/history.html` — filtered event timeline plus separate Command/Result/Message history views.
- `templates/mqtt_diagnostics.html` — broker, subscription and per-device expected-topic diagnostics.
- `templates/login.html` — minimal username/password session login page.

## `homelab-control/homelab_control_command_listener.py`

| Function | What / why |
|---|---|
| `timestamp_now()` | Returns millisecond ISO timestamps so fast queued/running transitions remain distinguishable. |
| `normalize_command_spec()` | Validates one current command object and normalizes its script/label/category/timeout fields; non-object command specs are rejected. |
| `resolve_script_path()` | Resolves only allow-listed filenames; bundled power scripts come from root `scripts/`, custom filenames keep project-root lookup. MQTT never supplies an arbitrary path. |
| `load_jobs_unlocked()` | Loads persisted remote jobs with malformed-file fallback. |
| `save_jobs_unlocked()` | Caps and atomically writes the remote jobs snapshot. |
| `update_job()` | Creates/updates one remote job under lock. |
| `get_jobs_snapshot()` | Returns a safe copy of current job records for publication. |
| `publish_jobs()` | Publishes retained job JSON via the same shared `MqttClient.publish()` API used elsewhere. |
| `recover_interrupted_jobs()` | Marks leftover active jobs failed on service restart so stale work never stays active forever. |
| `clean_output()` | Combines/caps script stdout/stderr for bounded diagnostics. |
| `run_job()` | Executes one allow-listed script under timeout/semaphore and records running/success/failure/runtime; an actual subprocess execution deadline records the distinct terminal `timed_out` state. |
| `queue_command()` | Validates command mapping, creates the queued job and starts a daemon worker so MQTT receive never blocks. |
| `parse_control_payload()` | Accepts only the current JSON object containing nonempty `command`, `job_id`, and `source`; plain strings or partial envelopes are rejected. |
| `on_connect()` | Component-only post-connect hook: logs the already-shared subscription and republishes retained jobs. |
| `on_message()` | Receives the common decoded `(topic, payload, retain, qos)` callback from `MqttClient` and queues only configured command IDs. Retention policy remains the sender's responsibility for this direct-agent topic. |
| `main()` | Creates the shared `MqttClient` with the control subscription/callbacks and runs it in blocking `forever` mode; all job/script behavior stays local to this component. |

### Remote command protocol

`control_power` accepts only JSON such as `{"command":"run_watchtower","job_id":"abc123","source":"Homelab Panel"}`. All three fields are required, `command` is looked up in `config.json -> commands`, and received text is never executed as shell code.

## `homelab-control/homelab_control_status_indicator.py`

| Function | What / why |
|---|---|
| `ensure_dirs()` | Creates the remote runtime state directory before status-file/history writes. |
| `read_text_file()` | Reads state text with a safe default. |
| `write_text_file()` | Atomically writes state text so sync loops never observe partial data. |
| `read_action()` | Reads current action with `idle` fallback. |
| `write_action()` | Writes current action atomically. |
| `get_uptime_seconds()` | Reads Linux `/proc/uptime` for retained uptime telemetry. |
| `get_current_boot_id()` | Reads Linux boot UUID to distinguish reboot from service restart. |
| `get_boot_time_epoch()` | Computes approximate boot epoch from uptime. |
| `get_boot_time_iso()` | Formats boot epoch for MQTT/UI metadata. |
| `load_history()` | Loads remote history with malformed-file fallback. |
| `save_history()` | Caps and atomically writes remote history. |
| `append_history_record()` | Appends one current event record and saves the capped history. |
| `clear_current_command_status()` | Clears current command/result/message after a real new boot. |
| `is_new_machine_boot()` | Compares the saved boot ID with the current Linux boot ID; first run or a same-boot service restart does not trigger cleanup. |
| `append_boot_history()` | Adds a categorized boot event with boot ID/time. |
| `initialize_boot_state()` | On a detected new Linux boot, clears current command fields, resets action to idle, appends a boot event, then stores the current boot ID. |
| `publish()` | Component convenience wrapper around the shared long-running `MqttClient.publish()` method. |
| `publish_history()` | Publishes the complete retained remote history JSON. |
| `publish_command_status()` | Publishes current command/result/message/timestamp topics. |
| `on_connect()` | Component-only post-connect hook that publishes online/action/hostname/uptime/boot/current status/history after the shared client connects. |
| `uptime_loop()` | Periodically republishes online and uptime. |
| `action_sync_loop()` | Republishes action only when the local action file changes. |
| `command_status_sync_loop()` | Republishes command fields only when local state changes. |
| `main()` | Initializes boot state, creates the shared `MqttClient` with LWT, starts threaded networking plus local sync loops/signals, publishes offline on clean exit and calls shared `.stop()`. |
| `handle_signal()` *(nested in `main`)* | Sets the shared stop event for SIGTERM/SIGINT so shutdown follows the clean offline/disconnect path. |

## Shell functions

| Function | What / why |
|---|---|
| `power_script_cli()` | Handles the four power scripts’ help/version using root `VERSION`, or rejects unsupported arguments with exit 2; called before config/privilege/state/power work. |
| `load_control_status()` | Loads the existing agent shell integration only for root with an active config, after CLI inspection; normal power/status behavior stays centralized. |
| `run_shutdown_command()` | Runs shutdown directly as root or through sudo otherwise; shared scripts work for remote agent and local panel. |
| `json_get()` | Reads required dotted JSON config key with Python parser. |
| `ensure_dirs()` | Creates remote state/log directories. |
| `timestamp_now()` | Returns local ISO command timestamp. |
| `mqtt_pub()` | Invokes the shared Paho CLI with the config path, exact payload on stdin, QoS 1 and retention; empty topics remain no-ops, success output is suppressed, and failure status reaches the calling script. |
| `write_action()` | Writes current action file used by status service. |
| `append_command_history()` | File-locks, appends categorized command event and atomically saves capped history. |
| `history_payload()` | Serializes remote history to compact JSON. |
| `publish_history()` | Publishes retained history when a history topic exists. |
| `write_command_status()` | Updates current command files/log, immediately archives every intermediate event, and publishes MQTT fields/history. |
| `set_idle()` | Sets/publishes idle action. |
| `set_shutdown_pending()` | Sets/publishes shutdown_pending action. |
| `set_reboot_pending()` | Sets/publishes reboot_pending action. |

## `scripts/` shared power scripts

- `scripts/shutdown_delay.sh` — sets shutdown pending/current history, calls `shutdown -h +1`, then records success/failure.
- `scripts/shutdown_cancel.sh` — calls `shutdown -c`, restores idle, and records success/failure.
- `scripts/reboot_delay.sh` — sets reboot pending/current history, calls `shutdown -r +1`, then records success/failure.
- `scripts/reboot_cancel.sh` — calls `shutdown -c`, restores idle, and records success/failure.
- `scripts/homelab_action_common.sh` — resolves `SCRIPT_DIR`, then the parent project root, optionally loads `homelab-control/modules/homelab_control_lib.sh` when run as root and `homelab-control/configs/config.json` exists, and selects root-vs-sudo shutdown execution.

## Component-local folders

- `homelab-panel/configs/__init__.py` — marks the panel configuration directory as an explicit Python package. The active `config.py` and `devices.py` are imported from here, so `app.py` remains directly executable without another service or a special working directory.
- `homelab-panel/modules/__init__.py` — marks the panel implementation directory as an explicit Python package. The entry point imports `modules.panel_actions`, `modules.panel_home_assistant`, and `modules.panel_mqtt`; the modules are libraries, not standalone services.
- `homelab-control/modules/homelab_control_lib.sh` — reusable remote-agent shell module for config access, status/history writes, and retained MQTT telemetry. It derives the agent root from its own location after moving under `modules/`.
- `homelab-control/configs/` — owns the remote agent JSON config/example. Both Python entry points and the shell module resolve `configs/config.json` relative to the agent directory, so they do not depend on the current working directory.

## Configuration files

- `homelab-panel/configs/config.example.py` — all panel/MQTT/auth/Home Assistant/monitor/history/job options. Active `config.py` is local-only and ignored.
- `homelab-panel/configs/devices.example.py` — device capabilities, WoL retry, status topics, expected-state defaults, confirmation, dynamic command buttons, and the separate local Home Assistant device `name`; non-empty example confirmation strings use `$TITLE` by default so prompts follow the configured title. Active `devices.py` is local-only and ignored.
- `homelab-control/configs/config.example.json` — remote broker/client/topics/timing and strict command-to-script allow-list. Active `config.json` is local-only and ignored.

## Repository hygiene / `.gitignore`

- Active `homelab-panel/configs/config.py`, `homelab-panel/configs/devices.py`, and `homelab-control/configs/config.json` are ignored while the examples and package markers remain tracked.
- Runtime `homelab-panel/state/`, `homelab-control/state/`, and `homelab-control/logs/` remain ignored.
- `.venv/`, `__pycache__/`, `*.pyc`, `*.pyo`, and macOS `.DS_Store` are ignored.
- `scripts/` is intentionally **not** ignored because the shared shutdown/reboot helpers are project source.

## Runtime files

- `homelab-panel/state/panel_action_history.json` — persistent per-device panel event journal.
- `homelab-panel/state/device_runtime_state.json` — expected state, transition/boot metadata.
- `homelab-panel/state/panel_jobs.json` — bounded panel-side job/confirmation records.
- `homelab-control/state/history.json` — remote command/boot history.
- `homelab-control/state/jobs.json` — bounded remote job lifecycle snapshot.
- other `homelab-control/state/*` files — current action, command/result/message/update and boot ID. Runtime state/logs are ignored and excluded from releases.

## Systemd units

All three included units are deployment examples; their `User`, `Group`, `WorkingDirectory`, and `ExecStart` values must match the host installation. The two remote services intentionally run as root because power scripts require system shutdown privileges.

## Safety model

- Web/session protection is global when enabled.
- MQTT control executes only device/button IDs configured in `homelab-panel/configs/devices.py`.
- Remote Homelab Control independently allow-lists command IDs in `homelab-control/configs/config.json`; bundled power scripts resolve from `PROJECT_ROOT/scripts`, while custom direct filenames resolve from `PROJECT_ROOT`.
- Local panel power-script lookup rejects traversal/nested names, and the remote listener keeps strict direct-filename handling for its configured jobs.
- Retained panel-control messages are never executed, including the explicit local target. HA button discovery sets command `retain=False`; remote forwarding still uses `MQTT_CONFIG["retain"]`, which must remain False.
- Local HA commands reuse the webpage runner and its privilege/path checks; local buttons affect the panel host. Browser confirmation prompts do not transfer to HA.
- The separate remote command listener does not reject retained commands; never publish retained messages to its command topic.
- MQTT publish success means only “sent”. Agent script results and panel power-confirmation workers can both update the matching panel job; a script exit code by itself does not prove physical power completion.


## Home Assistant discovery and commands

- `HOME_ASSISTANT_CONFIG.enabled` keeps discovery optional, with default `False`.
- `status_topic` is explicitly configured (the example uses `homeassistant/status`); an empty string disables the birth subscription. `status_online_payload` is also an explicit current key (example `online`).
- On broker connect or HA birth, `HomeAssistantIntegration.publish_snapshot()` publishes discovery, online availability and cached sensor state. Subsequent monitor passes publish fresh state.
- Remote discovery topics remain `<discovery_prefix>/button/homelab_panel_<device_id>/<button_id>/config`; Wake uses the existing `wake` ID. Local buttons use `<discovery_prefix>/button/homelab_local_panel/<button_id>/config` to avoid a remote device called `local` colliding with the host.
- Remote `payload_press` is `{"target":"remote","device_id":"...","command":"..."}`. Local `payload_press` is `{"target":"local","command":"..."}`. Both go to the panel control topic and select configured IDs rather than executable text.
- HA button labels come from the same `label` fields as web buttons. Local grouping requires `LOCAL_SERVER.name` as the Home Assistant device name, keeping the webpage section heading (`title`) separate from HA identity. Cancel-WoL stays registered in HA and refuses cancellation without an active job.
- Navigation/history filters/login/logout do not represent device actions and have no HA button entities.
- Discovery creates entities, not custom dashboard cards. Python configuration is loaded at startup; adding/editing buttons requires a panel restart. Removing a config entry prevents its execution but does not automatically delete a retained discovery document.

## Shared in-memory caches

| Class / method | What / why |
|---|---|
| `PanelJsonCache.__init__()` | Creates one lock and file-version dictionary for the fixed runtime files. |
| `PanelJsonCache.version()` | Returns inode/mtime/ctime/size, or None when missing, without loading/copying cached data; prepared requests detect external edits with one check per source. |
| `PanelJsonCache.load()` | Checks inode/mtime/ctime/size, parses changed JSON, and returns deep copies; missing/corrupt files evict old data. |
| `PanelJobsCache.__init__()` | Creates one lock and current source/result entry per configured device. |
| `PanelJobsCache.merge()` | Merges/de-duplicates/sorts panel and remote job sources only when content changes; returns isolated copies before time-dependent timeout evaluation. |
| `PanelDashboardCache.__init__()` | Creates separate prepare/render locks, one prepared view, process-instance/revision state and bounded per-device row caches. |
| `PanelDashboardCache.snapshot()` | Synchronizes changed sources once, returns status/job revision deltas and only each browser’s requested prefix, and keeps all private session content outside the cache. |

## Browser functions and callbacks in `static/dashboard.js`

| Function / callback | What / why |
|---|---|
| `fitFiveJobs()` | Measures current first-five-job height after updates and width changes. |
| `updateJobs()` | Replaces only job items while preserving the list element, focus and scroll anchor. |
| `updateStatus()` | Replaces only one changed status card; preserves focused action and pending button state. |
| `loginRequired()` | Returns to login when the API or action response reports session expiry (401). |
| `poll()` | Serializes global polls and pending older-job reads with one in-flight request; carries loaded counts, preserves the global cursor after one-device responses, handles timeout/retry and pauses while hidden. |
| `showMessage()` | Displays a result only in the initiating browser using textContent. |
| Submit callback | Respects cancelled inline confirmation, disables pending actions, POSTs once, shows private result and polls; never retries a command. |
| Visibility callback | Pauses hidden-tab polling and refreshes immediately when visible again. |
| ResizeObserver / resize callback | Recalculates job-list height on width changes. |
| Form `confirm(...)` handlers | Preserve configured confirmation before web actions; not used by HA MQTT presses. |

## External commands and embedded Python

| Command / block | What / why |
|---|---|
| `python3 app.py` | Starts one Waitress process with four request threads plus panel MQTT/status workers with no arguments; help/version exit before startup. |
| `python3 homelab_control_command_listener.py` | Loads the agent allow-list and runs the MQTT command listener. |
| `python3 homelab_control_status_indicator.py` | Starts Linux availability/boot/uptime/current-status publication; Linux `/proc` supplies uptime and boot identity. |
| `python3 shared_modules/mqtt.py --config PATH --topic TOPIC --qos 1 --retain` | Publishes the stdin payload as retained telemetry through Paho. The same CLI without `--retain` can send commands. The JSON config supplies credentials without placing them in argv. |
| `wakeonlan -i BROADCAST MAC` | Sends a magic packet to the configured broadcast destination. |
| `ping -c 1 -W TIMEOUT HOST` | Gets one bounded reachability sample: `-c 1` sends one probe and `-W` uses seconds on Linux or milliseconds on macOS; the caller also applies a three-second process timeout. |
| `shutdown -h +1`, `shutdown -r +1`, `shutdown -c` | `-h` schedules shutdown/halt, `-r` schedules reboot, `+1` is one minute, and `-c` cancels either operation. The shared helper uses `sudo` only for non-root execution. |
| `json_get` Python heredoc | Parses required dotted JSON keys rather than evaluating shell text; missing required configuration fails immediately under `set -e`. |
| `append_command_history` Python heredoc | Locks the shared event file, classifies the command, appends/caps history and replaces the file atomically. |
| `history_payload` Python heredoc | Produces compact JSON for retained history publication, with malformed/missing-file fallback. |
| `systemctl daemon-reload`, `enable --now`, `restart`, `status` | Reload unit definitions, enable/start services, reload app configuration, or inspect service state. |
| `journalctl -u UNIT -f` | Restricts log output to one unit and follows new messages. |
| `python3 -B -m unittest discover -s tests -v` | Runs the offline regression checks without writing bytecode; verbose discovery selects the included test directory. |

### `shared_modules/mqtt.py` CLI flags

The shared publisher has publishing options plus help/version. The three service entry points reuse `shared_modules/cli.py` for help/version before private configuration or runtime imports. The four power scripts reuse `power_script_cli()` before `load_control_status()`. Runtime settings remain in the configuration examples.

| Flag | What it does / why it exists |
|---|---|
| `-h`, `--help` | Lets an operator inspect the complete publisher interface without reading stdin/config or contacting MQTT. |
| `--version` | Prints the program name and packaged root `VERSION`, then exits before reading publishing inputs. |
| `--config PATH` | Selects normal CLI mode and reads the required top-level `mqtt` object from JSON. Broker credentials therefore remain in the config file instead of argv. |
| `--request-stdin` | Internal mutually exclusive worker mode used by `publish_message()`. The entire request arrives as JSON on stdin and the worker emits `[success, message]`, allowing the parent to impose a hard process timeout. |
| `--topic TOPIC` | Selects the exact publication destination in normal mode. `_publish_once()` rejects empty names and MQTT `+` / `#` wildcard publication topics before connecting. |
| `--qos {0,1,2}` | Selects protocol delivery QoS; normal CLI default is `1`. Python production callers pass QoS explicitly instead of relying on this CLI default. |
| `--retain` | Enables retained publication; default is off. It is used by retained telemetry helpers and must remain off for command/control messages to avoid broker replay. |
| `--timeout SECONDS` | Sets the positive finite end-to-end publication deadline, default `20` seconds, including worker startup, DNS, connect, publish and acknowledgement. Decimal seconds are accepted. |

The parser help includes the normal stdin contract, a retained-telemetry example, and the command-retain safety warning so the executable itself remains self-describing even when README.md is not open.

### Shell plumbing and service commands

| Command / construct | What / why |
|---|---|
| `set -euo pipefail` | Exits on unhandled command failures (`-e`), unset variables (`-u`), or failing pipeline members (`pipefail`); avoids continuing after setup/status errors. Commands tested by `if` use explicit success/failure branches. |
| `cd --`, `dirname --`, `pwd`, `${BASH_SOURCE[0]}` | Find the helper's own directory and project root independently of the caller's working directory. `--` ends option parsing. |
| `source FILE` | Loads the shared helper into the current shell so the action scripts reuse its functions and config. |
| `id -u` | Reads the numeric effective user ID; UID 0 selects direct shutdown and optional agent status integration. |
| `sudo shutdown ...` | Runs the configured power operation with elevated privileges when the caller is not root. |
| `mkdir -p DIR` | Creates state/log directories, including parents, and tolerates existing directories. |
| `date '+%Y-%m-%dT%H:%M:%S'` | Produces local ISO-style timestamps so command logs and history use the same format. |
| `python3 - ARG... <<'PY'` | Runs Python from standard input and passes data as positional arguments. The quoted heredoc delimiter prevents shell expansion of Python source. |
| `printf`, `echo`, `>`, `>>`, `>&2` | Write current fields, append logs, and print results/errors. `>` replaces a file, `>>` appends, and `>&2` sends diagnostics to stderr. |
| `exit 1` | Reports an unsuccessful power action so the listener records job failure. |
| `apt update`, `apt install ...` | Refresh package metadata and install the documented runtime tools on Debian/Ubuntu. |
| `cp SOURCE DEST`, `chmod +x FILE` | Create editable active configs/install service units and make scripts executable. `+x` adds execute permission. |
| `python3 -c CODE` | Runs the documented session-secret generator without starting the application. |
| Unit `After` / `Wants` | Order startup after and request `network-online.target`; this does not prove that the MQTT broker is reachable. |
| Unit `User` / `Group`, `WorkingDirectory`, `ExecStart` | Select service identity, working directory, and Python entry point; deployment paths must match the complete installed tree. |
| Unit `Restart`, `RestartSec`, `WantedBy` | Select restart policy/delay and boot target; the panel restarts on failure, while both agent units restart on any exit. |

The README's **Command flag reference** documents the values, units, and examples for operator-facing commands. All eight operator entry points support safe `-h`/`--help` and `--version`. Service programs reject unknown arguments before configuration/import startup. Power scripts reject unsupported/extra arguments before privilege checks or agent setup; running with no arguments performs the power operation. Shell libraries are sourced helpers.

## `tests/test_home_assistant.py`

Panel tests load the real Flask/Jinja entry point with example configuration, temporary runtime files, captured HA publication, and blocked background/external I/O.

| Function / method | What / why |
|---|---|
| `load_panel()` | Imports the real panel with example config modules while mocking Paho client construction and thread startup; tests do not need active private configs or a broker. |
| `setUp()` | Gives each test fresh runtime paths, a Flask client, current HA enabled/connected state, publication capture, and a subprocess blocker. |
| `capture()` (nested) | Records HA publication arguments instead of opening a broker connection. |
| `button_configs()` | Extracts captured HA button discovery JSON for concise payload/device assertions. |
| `test_every_web_action_is_discovered_with_current_envelope()` | Verifies all example remote/WoL/local actions and that remote HA payloads explicitly use `target="remote"`. |
| `test_custom_buttons_and_namespaces_dispatch_without_component_coupling()` | Adds config-only local/remote buttons, verifies separate HA namespaces, and checks current panel dispatch without either component importing the other. |
| `test_discovery_respects_enabled_connection_and_control_topic()` | Verifies HA feature/broker gates and that buttons are omitted when the panel command topic is empty. |
| `test_web_and_mqtt_local_buttons_use_same_allow_listed_script()` | Verifies web and panel MQTT both resolve a local button ID to the same configured script and ignore an injected `script` field. |
| `test_web_login_is_the_only_web_access_gate()` | Confirms session login protects action routes and a query `token` parameter has no access-control role. |
| `test_retained_panel_control_is_rejected()` | Verifies retained local/remote panel-control messages never start execution workers. |
| `test_live_panel_control_requires_explicit_target_and_dispatches_worker()` | Verifies fresh explicit-target envelopes are dispatched and target-less remote envelopes are rejected. |
| `test_local_script_path_guards_are_preserved()` | Checks traversal, absolute paths, symlink escapes, missing files and non-executable files without running a command. |
| `test_home_assistant_birth_republishes_discovery_and_cached_state()` | Verifies the configured HA birth payload republishes discovery/availability/cached state without ping I/O. |
| `test_birth_topic_customization_and_disable_are_current_config()` | Verifies explicit custom HA status topic/payload and empty-topic opt-out. |
| `test_confirmation_title_placeholder_resolves_and_is_js_safe()` | Verifies `$TITLE` replacement and JSON-safe browser rendering for quoted titles. |
| `test_job_lifecycle_timeout_is_optional_distinct_and_non_active()` | Verifies configured 60-second shutdown/reboot lifecycle timeouts, visible remaining time, non-mutating `timed_out` conversion, optional/no-timeout behavior, and protection of already-terminal success. |
| `test_combined_jobs_and_power_confirmation_use_timed_out_state()` | Verifies combined dashboard jobs expire to non-active `timed_out` and the shutdown/reboot confirmation worker uses the same distinct timeout result rather than failure. |
| `test_webpages_render()` | Exercises dashboard, history, diagnostics and login rendering under isolated I/O. |

## `shared_modules/mqtt.py`

This is the **only generic MQTT implementation** in production. Both `homelab-panel` and `homelab-control` use the same long-running `MqttClient` API; the same file also implements the bounded one-shot publisher and standalone CLI. No component imports Paho directly.

| Function / method | What / why |
|---|---|
| `MqttClient.__init__()` | Stores common broker settings, optional client ID/LWT/subscription provider/component callbacks and reconnect policy without knowing panel/control behavior. |
| `MqttClient._build_client()` | The single Paho client-construction path: MQTT 3.1.1, auth, LWT, reconnect delay and shared callbacks. It requests callback API v2 when Paho exposes `CallbackAPIVersion` and omits that v2-only constructor keyword for Paho 1.x. |
| `MqttClient._subscription_items()` | Resolves the current static/callable iterable of `(topic, qos)` pairs into unique sorted subscriptions; obsolete string-only subscription entries are not accepted. |
| `MqttClient._handle_connect()` | Shared connect callback accepts both Paho 1.x's four-argument callback and Paho 2.x VERSION2's properties argument, then normalizes success/subscription handling for components. |
| `MqttClient._handle_disconnect()` | Shared disconnect callback normalizes Paho 1.x `(rc)` and Paho 2.x VERSION2 `(flags, reason_code, properties)` shapes before clearing connection state and passing reason text to the component hook. |
| `MqttClient._handle_message()` | Decodes Paho bytes once and invokes every component with the same `(topic, payload, retain, qos)` shape. |
| `MqttClient.start()` | Starts one current long-running mode: blocking `forever`, background `thread`, or reconnecting `async_thread`; broker/port/keepalive come from component settings. |
| `MqttClient.publish()` | Common publish path for long-running clients, including Paho immediate status and a bounded `is_published()` completion wait that works across the supported Paho 1.x/2.x APIs without relying on version-specific `wait_for_publish()` signatures. |
| `MqttClient.stop()` | Stops threaded loops when used and disconnects safely. |
| `_publish_once()` | Performs one no-reconnect/no-retry send with input validation, deadline handling and hard socket shutdown when delivery becomes uncertain. |
| `on_connect()` *(nested in `_publish_once`)* | Captures CONNACK for the bounded publisher and accepts both Paho 1.x and Paho 2.x callback argument counts without exposing a component callback. |
| `network_step()` *(nested in `_publish_once`)* | Advances the disposable Paho loop only within the remaining deadline. |
| `publish_message()` | Runs `_publish_once()` in a child invocation of this same module so DNS/connect/send are bounded by a hard parent timeout and credentials/payload remain off argv. |
| `cli_main()` | Implements the standalone `shared_modules/mqtt.py` CLI. It defines every flag, value metavariable, default/safety help text, the normal stdin example, normal config/topic validation, the internal JSON worker path, and exit-status mapping. |

`shared_modules/cli.py` also provides generic CLI inspection/version reporting. `shared_modules/` intentionally contains no panel history/HA/actions and no control jobs/status logic. Those are application responsibilities rather than reusable transport.

## `tests/test_mqtt_publish.py`

| Function / method | What / why |
|---|---|
| `PublisherTests.client()` | Builds a controllable Paho test double with chosen CONNACK and acknowledgement behavior. |
| `test_settings_payload_qos_and_retention_are_preserved()` | Verifies auth/port/exact payload/QoS 0-2/retain and no reconnect/background loop for one-shot sends. |
| `connect_once()` *(nested in `PublisherTests.client`)* | Delivers the configured fake CONNACK from the client builder without adding a separate reusable test API. |
| `test_unauthenticated_publish_uses_explicit_nonretained_command_settings()` | Verifies optional broker authentication while using the same explicit command QoS/retain values supplied by current production callers. |
| `test_refused_connection_never_publishes()` | Ensures a rejected broker connection sends no command. |
| `test_connect_exception_and_publish_error_fail()` | Propagates socket and Paho publish failures. |
| `test_timeout_closes_socket_before_disconnect_without_retry()` | Verifies uncertain one-shot delivery closes hard and is never retried. |
| `test_invalid_inputs_fail_before_connecting()` | Rejects invalid topic/QoS/deadline before client construction. |
| `test_shared_long_running_client_api()` | Exercises the one shared long-running client path, including current Paho 2.x callback API v2 when available, MQTT 3.1.1 construction, auth/LWT, subscriptions, decoded callbacks, publish, and disconnect behavior used by both components. |
| `test_paho_v1_constructor_and_callback_shapes_are_supported()` | Simulates Paho 1.x with no `CallbackAPIVersion`, verifies the constructor omits the unsupported keyword, and exercises legacy connect/disconnect callback signatures. |
| `test_paho_v1_one_shot_connect_callback_is_supported()` | Simulates the Paho 1.x four-argument CONNACK callback in the disposable publisher so old API support covers both long-running and one-shot clients. |
| `test_parent_bounds_worker_and_keeps_credentials_off_argv()` | Verifies the hard parent timeout and stdin-only request carrying credentials/payload. |
| `test_panel_actions_reuse_shared_publisher_and_current_json_envelope()` | Verifies panel remote actions call shared `publish_message()` with current `command`/`job_id`/`source` JSON. |
| `test_cli_reads_credentials_from_config_and_payload_from_stdin()` | Verifies CLI config/payload handling and publication exit status. |
| `test_cli_help_and_config_errors()` | Verifies safe help lists every supported publisher flag plus stdin/retain safety guidance, then verifies missing-config failure without network work. |
| `test_shell_bridge_payload_and_failure_exit()` | Executes the actual shell library with a shim to verify exact stdin/argv and failure propagation to shell callers. |
| `WireTests.read_packet()` | Reads one MQTT packet including its variable-length remaining-length field. |
| `read_string()` | Decodes one MQTT length-prefixed byte string. |
| `exchange()` | Runs a bounded localhost MQTT peer around the production one-shot publisher. |
| `serve()` (nested in `exchange`) | Implements the tiny local CONNECT/PUBLISH acknowledgement peer for wire assertions. |
| `test_real_paho_qos_zero_one_two_and_retention()` | Verifies real Paho wire behavior for auth, exact bytes, retain and QoS 0/1/2. |
| `test_real_paho_rejected_connection_sends_no_command()` | Verifies rejected real CONNACK sends no PUBLISH. |
| `test_real_paho_missing_ack_times_out_and_closes()` | Verifies missing acknowledgement causes bounded uncertain-delivery failure and closure. |

## Release support files

- `VERSION` contains the current three-part version.
- `VERSIONING.md` records the version policy and each release's actual changes.
- `VALIDATION.md` records checks, environment limits, and the original/final file comparison for this package.

## Dashboard regression checks

`tests/test_dashboard.py` uses `load_panel()` with isolated temporary state, a fixed clock and a ping guard.

| Function | What / why |
|---|---|
| `DashboardTests.setUp()` | Loads isolated app/state, holds time constant and fails any request-time ping. |
| `DashboardTests.poll()` | Requests JSON with the optional prior revision/instance for a selected session. |
| `DashboardTests.seed_ping()` | Supplies monitor measurements without network I/O. |
| `test_startup_and_expired_cache_never_ping_and_show_unknown()` | Checks absent/stale cache behavior and no full-page refresh. |
| `test_unchanged_requests_reuse_fragments_and_send_no_cards()` | Checks zero template rendering and compact unchanged responses. |
| `test_only_changed_device_fragment_is_returned_and_restart_resets()` | Checks per-card/per-tab deltas and process reset behavior. |
| `test_broker_loss_and_mqtt_expiry_cannot_leave_green_online()` | Checks connection/TTL changes use current MQTT state. |
| `test_job_sources_invalidate_and_timeouts_progress_without_new_mqtt()` | Checks persisted/remote changes and time-dependent expiry. |
| `test_state_cache_reuses_decoded_data_and_notices_replace_delete_corruption()` | Checks no redundant parsing and runtime-file invalidation. |
| `test_login_and_action_results_remain_private_and_json_requires_auth()` | Checks two-session isolation, retained private flashes and blocked expired commands. |
| `test_shared_html_escapes_device_and_job_payloads()` | Checks unsafe device/job text is escaped inside shared fragments. |
| `test_script_entry_uses_waitress_once_instead_of_development_server()` | Checks direct startup uses Waitress and never Flask.run(). |

`tests/dashboard_browser.cjs` runs an optional real Chromium/Waitress check. Its localhost-only Python fixture uses `fake_action()`, `add_jobs()`, `change_job()` and `restart_cache()` exclusively inside the test process; these endpoints do not exist in the production application. The test covers login, incremental updates, no navigation on commands, confirmation cancellation, XSS escaping, job focus/scroll, private results, network recovery, hidden-tab pause, process-cache reset, mobile width and session expiry. All external device/MQTT work is mocked.


## Shared CLI inspection: `shared_modules/cli.py`

| Function / block | What / why |
|---|---|
| `add_version_argument()` | Reads root `VERSION` once when building a parser and registers argparse’s version action; all Python entry points reuse the same version source. |
| `parse_service_cli()` | Defines service help/version, rejects unsupported arguments, and returns only for a normal no-argument start; called before service config/dependency imports to prevent accidental startup during inspection. |
| Entry-point `if __name__ == "__main__"` inspection blocks | Apply the shared parser to direct service execution only, preserving existing import behavior and one-process Waitress startup. |
| MQTT direct-file path setup | Adds the project root so both direct-file execution and imported callers find the same `shared_modules.cli`; publishing remains in the existing MQTT implementation. |
| Power-script preamble | Sources common definitions, calls `power_script_cli()` with that action’s description, then `load_control_status()`; no-argument paths keep original command arguments and status transitions. |

## `tests/test_cli.py`

| Function | What / why |
|---|---|
| `test_service_inspection_precedes_dependencies_and_private_configs()` | Launches all three service CLIs from another directory with Python `-S` (no installed site packages), covering help/version, unknown flags and positional errors before startup. |
| `test_publisher_version_precedes_input_and_publication()` | Blocks private-config opening/publication and verifies version exits without required publishing options. |
| `prepare_scripts()` | Creates a disposable scripts/VERSION install for tests so shell checks cannot use host power commands. |
| `test_power_inspection_and_errors_never_enter_privileged_setup()` | Traps id/sudo/shutdown/Python and installs invalid agent config/library; all four scripts must inspect/reject arguments without invoking setup or writing runtime state. |
| `test_power_actions_preserve_root_sudo_argv_and_failure_status()` | Captures all four real script argv paths using stubs, for root/non-root and success/failure; verifies exact original delay/cancellation arguments and exit status without a real power action. |

`tests/test_dashboard.py` patches `sys.argv` to an actual no-argument `app.py` invocation in its runpy startup test; unittest runner arguments are not service arguments. `config.example.py` includes optional panel `keepalive` (default 60) consumed by the existing shared long-running MQTT client. Both disclaimer blocks remain in README with project-local links.


## Prepared dashboard and lazy job interfaces

| Function / method / block | What / why |
|---|---|
| `PanelDashboardCache.prepare()` | Shares one build under a lock per source generation, expiry deadline or backwards clock step; warm polls avoid state loads/status construction/job evaluation. Returned view is private read-only app state. |
| `PanelDashboardCache._sync()` | Skips all source comparison for the same prepared object, prunes removed devices, rebuilds only changed escaped status sources, and resets job rows only when their source changes. |
| `PanelDashboardCache._job_window()` | Lazily renders missing rows up to a requested count, reuses each row across window sizes, and returns total/count metadata; cache stores at most one HTML string per retained row. |
| `PanelDashboardCache.job_window()` | Returns one device’s expanded prefix under the render lock without retaining per-browser windows. |
| `build()` (nested in `build_remote_device_statuses()`) | Loads runtime/job sources once under their existing locks and MQTT once; constructs stable status/job views, removes display-only remaining seconds, and returns the earliest future freshness/timeout deadline. |
| `payload_and_age()` (nested in `build_device_status()`) | Passes the optional common MQTT snapshot/time to the existing receive-age resolver so batch evaluation stays consistent. |
| `dashboard_response()` | Adds fresh server epoch and display time to a response outside shared HTML, allowing independent browser clocks without shared cache churn. |
| `older_device_jobs()` | Protected GET `/api/jobs/<device_id>?limit=N`; validates device/count and returns an escaped current prefix without mutating history or executing commands. |
| `dashboard_updates()` | Validates optional JSON `jobs` counts alongside existing revision/instance cursors; rejects non-object, unknown-device, boolean, negative and over-limit windows before rendering. |
| `index()` | Uses the configured initial batch; explicit `?jobs=all` preserves a no-JavaScript path to all retained jobs. |
| `apply_job_timeout()` | Keeps existing countdown/terminal classification and additionally exposes a stable numeric `timeout_deadline`; batch callers provide one time and the browser only displays remaining seconds. |
| `get_remote_command_state_received_at()` | Accepts the same optional MQTT snapshot so provisional-versus-remote precedence uses one coherent receive view. |
| `updateClocks()` | Updates only age/countdown text once per visible second using server epoch plus monotonic browser elapsed time; never changes authoritative state or sends requests. |
| `syncClock()` | Resynchronizes the local display clock after each successful shared/older-job response. |
| `updateMoreButton()` | Hides the older-jobs button after all available rows are loaded and disables duplicate pending loads. |
| `requestMoreJobs()` | Queues one bounded next-prefix request per device; normal polling and loads use the same request queue. |
| `applyFragments()` | Applies shared status/job responses, updates loaded-count metadata and button state, and synchronizes display clocks; no session data enters fragments. |
| `atBottom()` / scroll / wheel / keydown callbacks | Detect user demand for older rows; support an initially non-scrollable five-row list, keyboard navigation, and ignore programmatic scroll while replacing rows. |
| Older-jobs click callback | Offers an accessible explicit load/retry action using the same queue as scroll/key demand. |
| Visibility callback | Pauses both polling and the display-clock interval while hidden; resumes clocks/polling once visible. |
| `[hidden]` CSS rule | Makes hidden controls reliably disappear despite the existing generic button display rule. |

`DASHBOARD_JOB_PAGE_SIZE` is optional in existing active configs (default 5, min 1, capped by the retention limit); `MQTT_CONFIG.log_payloads` is optional (default False). The existing monitor, MQTT transport, action allow-lists, direct-agent behavior, persistence formats and command CLI flags are preserved. Snapshot keys include MQTT revision/connectivity, ping measurements, provisional actions, WoL activity, device settings and runtime/job file identities. Server deadlines cover integer-second MQTT TTL expiry, stale monitor measurements and every active retained job, including unloaded rows.

## Performance regression functions in `tests/test_dashboard.py`

| Function | What / why |
|---|---|
| `seed_jobs()` | Writes a full bounded example source in one fixture save. |
| `test_prepared_snapshot_reuses_all_work_and_batches_source_loads()` | Requires exactly two state loads on a cold build and zero loads/status builds/timeout evaluations/renders across unchanged polls from two clients. |
| `test_age_and_countdown_do_not_invalidate_before_server_deadline()` | Requires clock-only polls to reuse HTML, then verifies server timeout at the exact deadline. |
| `test_prepared_cache_enforces_mqtt_and_monitor_expiry_and_clock_rewind()` | Tests integer TTL boundary, monitor expiry and backwards server clock invalidation without new MQTT messages. |
| `test_prepared_sources_invalidate_on_runtime_jobs_mqtt_actions_and_wol()` | Exercises source changes including expected state, MQTT hostname, provisional action, WoL activity and device configuration. |
| `test_external_source_replacement_corruption_and_deletion_invalidate_prepared_view()` | Ensures file replacement, corruption and deletion cannot retain stale prepared data. |
| `test_lazy_jobs_render_only_requested_rows_and_reuse_bounded_row_cache()` | Verifies initial five of 100, five extra renders for a ten-row window, row reuse, independent browser windows, full retained data and no-JavaScript access. |
| `test_expanded_windows_stay_current_on_new_jobs_and_timeout()` | Verifies inserted jobs reorder expanded prefixes correctly and server timeout remains active on older-job requests. |
| `test_job_window_auth_validation_escape_and_no_shared_session_data()` | Tests protected/escaped read-only windows, private headers and invalid input bounds. |
| `test_mqtt_payload_logging_is_optional_without_silencing_errors()` | Checks absent/False/True logging settings, receive state updates and retained-control/disconnection messages. |
| `test_prepared_cache_build_is_serialized_across_threads()` | Starts six simultaneous readers and requires exactly one shared preparation build. |
| `read()` (nested in that test) | Synchronizes concurrent fixture callers at a barrier before reading the cache. |

The browser fixture also defines `add_clocks()` (receive time plus a short active deadline) and `many_jobs()` (a 30-row retained source), only inside the test process. Browser checks cover local clock ticks without DOM replacement, server timeout, initial batching, explicit/wheel/keyboard expansion, failed-read retry and serialization with a delayed global poll. Production has no `_test` routes.


- `test_unloaded_job_deadline_still_updates_active_count()` verifies that an active older job outside the initial five still expires server-side, updates the active count, remains available on expansion and leaves persisted data unchanged.
- `test_custom_initial_batch_does_not_change_retention()` verifies a configured two-row initial batch independently of the retained job count.
- `_job_window()` appends a small scroll-for-more sentinel when older rows exist, providing a scroll target even if the initial batch exactly fits the list. It disappears after the complete prefix is loaded. The existing Waitress startup fixture also omits `DASHBOARD_JOB_PAGE_SIZE` to exercise the default for older active configs.
