# commented_code_map.md

Current-code map for Homelab Panel. This is not release history; it explains what each current function/command/file does and why it exists.

## `homelab-panel/app.py`

| Function | What / why |
|---|---|
| `web_auth_enabled()` | Returns whether optional session login is enabled; centralizes the feature gate so routes do not implement their own auth rules. |
| `validate_web_auth_config()` | When login is enabled, rejects empty username/password/secret and password/secret values containing `CHANGE_ME`; catches incomplete setup before startup. It does not check password strength or every possible placeholder. |
| `session_authenticated()` | Checks the Flask session authentication flag; keeps password data out of the session. |
| `credentials_match()` | Compares supplied/configured username and password with constant-time comparison; reduces trivial timing leakage. |
| `require_web_login()` | Global before-request guard that redirects every non-login/static route when authentication is required; protects current and future routes by default. |
| `check_token()` | Applies the legacy query token only when session login is disabled; preserves older deployments. |
| `run_command()` | Runs a fixed argv command with timeout and captured output; avoids shell=True and gives callers one error format. |
| `load_json_file()` | Loads a JSON runtime file with a safe default on missing/corrupt data; runtime state should not crash the panel. |
| `save_json_file_atomic()` | Writes JSON via temporary file + replace; prevents readers seeing partially written state. |
| `get_device_button()` | Finds a configured mqtt_controls button by ID; the same allow-list drives web, panel MQTT, jobs and HA. |
| `resolve_confirmation_text()` | Replaces the optional `$TITLE` token with the owning device title for browser prompts; literal text remains unchanged and the template performs JSON-safe JavaScript encoding. |
| `get_related_status_topic()` | Returns an explicit status topic or derives a sibling from last_message; keeps older active configs compatible. |
| `get_hostname_topic_for_status_cfg()` | Gets/derives the remote hostname topic; older devices.py files can expose hostname without immediate edits. |
| `get_uptime_topic_for_status_cfg()` | Gets/derives the remote uptime topic; older devices.py files can expose uptime/HA sensor without immediate edits. |
| `get_jobs_topic_for_status_cfg()` | Gets/derives the remote job snapshot topic; avoids duplicated topic-derivation logic. |
| `get_boot_id_topic_for_status_cfg()` | Gets/derives boot ID topic; supports boot detection without forcing immediate config migration. |
| `get_boot_time_topic_for_status_cfg()` | Gets/derives boot-time topic; provides boot metadata while keeping old configs valid. |
| `get_device_category()` | Resolves an event/job category from the button or command; powers history filtering and job grouping. |
| `_sync_mqtt_connected()` | Mirrors MQTT runtime connectivity into the legacy module-level `MQTT_CONNECTED` flag so existing callers/tests keep working after transport ownership moved to `panel_mqtt.py`. |
| `_device_status_cache_snapshot()` | Copies the monitor cache under lock for HA birth snapshots; keeps lock ownership in `app.py` while the HA module receives an isolated status dictionary. |
| `load_runtime_state_unlocked()` | Loads persistent per-device runtime/expected-state data; state survives panel restart. |
| `save_runtime_state_unlocked()` | Atomically saves runtime state; avoids corruption during monitor updates. |
| `get_device_runtime()` | Returns one device runtime state under lock; callers cannot mutate shared data unsafely. |
| `update_device_runtime()` | Merges and persists per-device runtime fields under lock; centralizes expected/transition state writes. |
| `get_expected_state()` | Returns persisted expected state or device default; distinguishes planned downtime from faults. |
| `set_expected_state()` | Persists expected state, reason and timestamp; power workflows can explain why offline is expected. |
| `load_panel_jobs_unlocked()` | Loads persistent panel-side job records; job display survives panel restarts. |
| `save_panel_jobs_unlocked()` | Caps and atomically saves panel jobs; prevents unbounded runtime growth. |
| `update_panel_job()` | Creates/updates one panel job by ID; all lifecycle writers share the same format. |
| `get_panel_jobs()` | Returns a copy of stored panel jobs for one device; protects shared state. |
| `history_contains_event()` | Checks whether a remote job lifecycle event was already archived; prevents retained snapshot duplicates after reconnect/restart. |
| `record_device_event()` | Creates a normalized categorized history record and appends it; one event schema is used across power, MQTT, availability and jobs. |
| `active_job_status()` | Defines which lifecycle states count as active; UI logic has one source of truth. |
| `combined_device_jobs()` | Merges panel jobs with retained remote jobs and sorts newest-first; dashboard can show parallel work from both sides. |
| `mqtt_publish()` | Compatibility/dependency boundary that delegates one-shot command publication to `PanelMqttRuntime.publish_command()`; callers keep the existing `(ok, message)` contract while MQTT transport logic stays out of Flask routing/state code. |
| `send_wol()` | Thin compatibility delegate to `PanelActionManager.send_wol()`; keeps the old app-level call surface while the action implementation lives in `panel_actions.py`. |
| `run_local_script()` | Thin compatibility delegate to the action module. The actual path-containment/executable checks are implemented once in `PanelActionManager.run_local_script()`. |
| `execute_local_action()` | Delegates local button execution to `PanelActionManager`; web and panel MQTT still share the same configured allow-list and cannot supply a script path. |
| `ping_host()` | Runs one bounded ping with Linux seconds or macOS milliseconds for `-W`; ping remains independent from MQTT. |
| `set_mqtt_state()` | Compatibility delegate to `PanelMqttRuntime.set_state()`; the MQTT module owns the receive cache and metadata. |
| `set_mqtt_connected()` | Delegates connection-state changes to `PanelMqttRuntime`, which also updates timestamps/reason and mirrors the legacy app-level boolean. |
| `get_mqtt_connected()` | Returns the compatibility broker-connected flag and keeps it synchronized with `PanelMqttRuntime`; preserves existing app/test callers. |
| `get_mqtt_state()` | Delegates one cached-topic lookup to the MQTT runtime. |
| `get_mqtt_payload_and_age()` | Delegates payload/age calculation to the MQTT runtime so TTL users share one cache implementation. |
| `action_to_danish()` | Maps internal action states to Danish UI text while preserving unknown custom values. |
| `result_to_danish()` | Maps lifecycle/result states to Danish UI text while preserving custom values. |
| `command_to_danish()` | Maps built-in power commands to friendly Danish labels; custom command IDs still remain visible. |
| `get_history_topic_for_status_cfg()` | Gets/derives remote history topic; backwards-compatible with older devices.py. |
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
| `evaluate_remote_device_status()` | Computes ping, MQTT, combined online, expected-state text, current command fields, uptime and jobs; green Online remains strict ping+MQTT. |
| `build_remote_device_statuses()` | Uses recent monitor cache when possible and refreshes volatile job/WoL fields; avoids unnecessary page-load pings. |
| `device_mqtt_online()` | Tests current connected/fresh power=online state; confirmation workers use the same strict MQTT rule. |
| `device_mqtt_offline()` | Tests current connected/fresh power=offline state; shutdown/reboot are not confirmed merely by publish success. |
| `wol_job_active()` | Delegates active-WoL lookup to `PanelActionManager`; the in-memory WoL job registry is owned by the action module. |
| `cancel_power_confirmation()` | Delegates cancellation to `PanelActionManager`, which owns confirmation cancel events. |
| `power_confirmation_worker()` | Compatibility thread target delegating shutdown/reboot confirmation to `PanelActionManager`; `app.py` keeps job/history orchestration while action mechanics stay modular. |
| `execute_remote_action()` | Delegates allow-listed remote dispatch to `PanelActionManager`; configured WoL/cancel/buttons and JSON job envelopes remain the only accepted action paths. |
| `execute_and_record_remote_action()` | Creates panel job/history around dispatch and starts expected-state/power confirmation when relevant; web and panel-control MQTT share one path. |
| `process_panel_control_message()` | Parses panel-control JSON. Remote commands require `device_id`; explicit `target=local` requires a configured local button ID and rejects any `device_id` field. Unknown/missing remote devices never fall back to the panel host. Retained messages are rejected by the receive callback before dispatch. |
| `process_remote_jobs_message()` | Parses retained remote job snapshots, archives unseen lifecycle changes and merges matching job IDs; script exit results reach the dashboard without using panel-control. |
| `handle_boot_id_message()` | Detects changed remote boot ID, clears provisional panel command state and records boot event; service restarts with same boot ID do not look like new boots. |
| `format_duration()` | Formats seconds for uptime/transition display. |
| `publish_mqtt_direct()` | Delegates telemetry/discovery publication to the long-running `PanelMqttRuntime` client; it remains separate from disposable command publishing. |
| `home_assistant_enabled()` | Delegates the feature gate to `HomeAssistantIntegration.enabled()`. |
| `publish_home_assistant_discovery()` | Compatibility delegate to `HomeAssistantIntegration.publish_discovery()`; configuration-derived entities/IDs and local naming behavior are unchanged. |
| `publish_home_assistant_snapshot()` | Compatibility delegate to `HomeAssistantIntegration.publish_snapshot()`; broker-connect/HA-birth behavior still reuses cached status instead of pinging in the MQTT callback. |
| `publish_home_assistant_state()` | Compatibility delegate to `HomeAssistantIntegration.publish_state()` for retained per-device HA JSON. |
| `monitor_device_transition()` | Persists true combined-state transitions and previous-state duration, marking unexpected offline as errors. |
| `status_monitor_loop()` | Periodically evaluates devices independent of page views, updates cache/history and HA state; ping works even when MQTT is absent. |
| `start_status_monitor()` | Starts exactly one background monitor thread per process. |
| `build_mqtt_diagnostics()` | Delegates diagnostics construction to `PanelMqttRuntime`, which owns subscriptions, receive cache and connection metadata. |
| `on_connect_compat()` | Compatibility Paho callback delegating connect/subscription/HA snapshot/history work to `PanelMqttRuntime.on_connect()`. |
| `on_disconnect_compat()` | Compatibility Paho callback delegating disconnect state/history handling to `PanelMqttRuntime.on_disconnect()`. |
| `on_message_compat()` | Compatibility Paho callback delegating receive-cache/control/HA-birth/job/boot/power dispatch to `PanelMqttRuntime.on_message()` while preserving the actual panel control handler as the worker target. |
| `start_mqtt_listener()` | Delegates startup of the status monitor and asynchronous broker loop to `PanelMqttRuntime.start()`. |
| `login()` | GET/POST login route; creates session only after credential match. |
| `logout()` | POST route that clears the web session. |
| `index()` | Main dashboard route; renders cached remote status, jobs, controls and local actions. |
| `device_history()` | Per-device event/history route with category/errors filtering. |
| `wol()` | POST web route starting the shared asynchronous WoL workflow. |
| `wol_cancel()` | POST route cancelling an active WoL retry/confirmation workflow. |
| `mqtt_diagnostics()` | Protected diagnostics route showing broker/subscription/expected-topic state. |
| `mqtt_button()` | POST route dispatching any configured dynamic remote button through the shared action path. |
| `local_button()` | Protected POST route calling `execute_local_action()` and flashing its result; reuses the same local allow-list/runner as HA commands without changing session/token checks. |


## `homelab-panel/modules/panel_actions.py`

`PanelActionManager` owns action mechanics that previously made `app.py` large. It receives configuration/state callbacks from the app instead of duplicating persistence, history, status evaluation, or config globals.

| Method | What / why |
|---|---|
| `PanelActionManager.__init__()` | Stores dynamic config/callback providers and creates private WoL/power-confirmation locks/state; dependency injection keeps the module reusable and avoids circular imports. |
| `PanelActionManager.send_wol()` | Builds the fixed `wakeonlan -i BROADCAST MAC` argv and uses the app's bounded `run_command()` callback; no shell text is accepted. |
| `PanelActionManager.run_local_script()` | Enforces direct filename, scripts-directory containment, file existence and executable permission before invoking the app command runner; preserves local path-traversal safety in one implementation. |
| `PanelActionManager.execute_local_action()` | Resolves only configured `LOCAL_SERVER.buttons` IDs and calls the injected app-level script runner; web/HA/MQTT clients still cannot provide a script path. |
| `PanelActionManager.wol_job_active()` | Checks the manager-owned WoL job registry under lock; used by UI/state publishing and duplicate-start prevention. |
| `PanelActionManager._finish_wol_job()` | Finalizes WoL expected state, panel job, history and active marker through injected app persistence callbacks; all terminal outcomes share one path. |
| `PanelActionManager._wol_worker()` | Performs retryable WoL sends, bounded ping confirmation and optional fresh MQTT-online confirmation asynchronously; records attempts/results through app callbacks. |
| `PanelActionManager.start_wol_job()` | Validates configured WoL settings, rejects duplicate active jobs, creates cancellation state and starts `_wol_worker()`. |
| `PanelActionManager.cancel_wol_job()` | Signals an active WoL job and records the request; it cannot create or cancel arbitrary commands. |
| `PanelActionManager.cancel_power_confirmation()` | Signals the current shutdown/reboot confirmation event for one device. |
| `PanelActionManager.power_confirmation_worker()` | Confirms shutdown by ping+MQTT offline and reboot by offline-then-ping+MQTT-online; updates expected state/jobs/history only through app callbacks. |
| `PanelActionManager.execute_remote_action()` | Resolves configured aliases/buttons, WoL and cancel-WoL; publishes only the configured topic/payload and optional JSON job envelope through the injected MQTT publisher. |

## `homelab-panel/modules/panel_home_assistant.py`

`HomeAssistantIntegration` contains only MQTT Discovery/state formatting and publication. It receives current configs/devices/cache/jobs/WoL state via callbacks, so it does not own panel state or command execution.

| Method | What / why |
|---|---|
| `HomeAssistantIntegration.__init__()` | Stores dynamic providers/callbacks for configs, devices, MQTT publication, status cache, jobs and WoL state; keeps HA logic independent of Flask globals. |
| `HomeAssistantIntegration.enabled()` | Returns the current `HOME_ASSISTANT_CONFIG.enabled` feature gate. |
| `HomeAssistantIntegration.state_topic()` | Builds the per-device state topic from the configured state prefix. |
| `HomeAssistantIntegration.device_block()` | Builds stable HA device-registry metadata for a remote panel device. |
| `HomeAssistantIntegration.publish_button()` | Publishes one configured MQTT button discovery document with non-retained command semantics and configurable retained discovery. |
| `HomeAssistantIntegration.publish_discovery()` | Publishes remote sensors, WoL/cancel controls, all configured remote buttons, and local buttons in the separate local namespace/name fallback. |
| `HomeAssistantIntegration.publish_snapshot()` | Publishes panel availability, discovery and cached states on broker connect/HA birth without performing ping I/O in the callback. |
| `HomeAssistantIntegration.publish_state()` | Publishes retained per-device combined status, ping/MQTT, uptime, command, expected state, latest job and WoL-active JSON. |

## `homelab-panel/modules/panel_mqtt.py`

`PanelMqttRuntime` owns only the panel-specific reconnecting MQTT state, subscriptions, dispatch, diagnostics, and cache. Generic Paho construction/auth/connect/publish behavior and one-shot transport live once in root `shared_modules/mqtt.py`.

| Method | What / why |
|---|---|
| `PanelMqttRuntime.__init__()` | Stores config/dispatch callbacks and creates the receive cache, subscription set, connection metadata, lock and client reference. |
| `PanelMqttRuntime.publish_command()` | Calls the shared disposable Paho publisher with current panel QoS/retain settings; command failure is never queued for later reconnect. |
| `PanelMqttRuntime.set_state()` | Stores latest payload, time, retained flag and QoS under lock and returns the previous payload for transition handling. |
| `PanelMqttRuntime.set_connected()` | Updates connected state plus connect/disconnect timestamps/reason and mirrors it to the app compatibility flag. |
| `PanelMqttRuntime.get_state()` | Returns an isolated copy of one cached topic record. |
| `PanelMqttRuntime.get_payload_and_age()` | Returns stripped cached payload and receive age for TTL/status evaluation. |
| `PanelMqttRuntime.publish_direct()` | Publishes HA/telemetry via the connected long-running client and reports immediate Paho publication failure. |
| `PanelMqttRuntime._related_topics()` | Applies the app-provided topic helper functions for hostname/uptime/history/jobs/boot metadata without duplicating backwards-compatible derivation rules. |
| `PanelMqttRuntime.build_diagnostics()` | Builds connection/subscription/cache and per-device expected-topic data for `/mqtt-diagnostics`. |
| `PanelMqttRuntime.on_connect()` | Marks connected, rebuilds/subscribes the topic set, republishes HA snapshot and records connect/reconnect events. |
| `PanelMqttRuntime.on_disconnect()` | Marks disconnected with reason and records per-device broker disconnect events. |
| `PanelMqttRuntime.on_message()` | Caches messages, rejects retained panel controls, dispatches fresh controls on a worker, handles HA birth, then forwards status/job/boot transitions to app callbacks. |
| `PanelMqttRuntime.start()` | Starts the app status monitor, supplies panel callbacks/optional HA Last Will to the shared MQTT client factory, then starts the shared asynchronous-threaded connection mode. |

## Flask routes

- `GET/POST /login` → `login()` — only public application route when optional session auth is enabled.
- `POST /logout` → `logout()` — clears authenticated session.
- `GET /` → `index()` — main remote status/job/control dashboard.
- `GET /history/<device_id>` → `device_history()` — merged event journal with filters.
- `POST /wol/<device_id>` → `wol()` — starts async WoL retry/confirmation.
- `POST /wol-cancel/<device_id>` → `wol_cancel()` — cancels active WoL job.
- `POST /mqtt/<device_id>/<button_id>` → `mqtt_button()` — dispatches configured dynamic button only.
- `GET /mqtt-diagnostics` → `mqtt_diagnostics()` — broker/subscription/expected-topic troubleshooting page.
- `POST /local/<button_id>` → `local_button()` — runs configured local script only.

## Panel templates

- `templates/index.html` — combined ping+MQTT status, expected state, current command fields, parallel job dashboard, WoL/cancel, all dynamic MQTT buttons, local controls and diagnostics link; browser confirmations resolve optional `$TITLE` and use JSON-safe JavaScript string encoding.
- `templates/history.html` — filtered event timeline plus separate Command/Result/Message history views.
- `templates/mqtt_diagnostics.html` — broker, subscription and per-device expected-topic diagnostics.
- `templates/login.html` — minimal username/password session login page.

## `homelab-control/homelab_control_command_listener.py`

| Function | What / why |
|---|---|
| `load_config()` | Loads `configs/config.json` relative to the remote-agent entry point before constants are derived; remote behavior is explicit per host and independent of the shell working directory. |
| `derive_jobs_topic()` | Uses explicit status_jobs or derives sibling /jobs topic; old configs can upgrade without immediate edits. |
| `timestamp_now()` | Returns millisecond ISO timestamp; quick queued/running transitions remain distinguishable. |
| `normalize_command_spec()` | Normalizes legacy string or object command entries into one structure; keeps compatibility while enabling category/timeout metadata. |
| `resolve_script_path()` | Special-resolves the four bundled shutdown/reboot filenames from `PROJECT_ROOT/scripts`; non-bundled custom filenames keep the prior project-root lookup for compatibility. MQTT still selects only an allow-listed command ID, never an arbitrary path. |
| `load_jobs_unlocked()` | Loads persisted remote jobs with malformed-file fallback. |
| `save_jobs_unlocked()` | Caps and atomically persists remote job snapshots. |
| `update_job()` | Creates/updates one remote job by ID under lock. |
| `get_jobs_snapshot()` | Returns a safe copy of persisted jobs for MQTT publication. |
| `publish_jobs()` | Publishes the complete retained jobs snapshot; panel can catch up after reconnect. |
| `recover_interrupted_jobs()` | Converts leftover queued/running/waiting/confirming jobs to failure on listener startup; a service restart cannot leave stale jobs looking active forever. |
| `clean_output()` | Combines and caps stdout/stderr; useful diagnostics without unbounded MQTT payloads. |
| `run_job()` | Waits for parallel slot, runs allow-listed script with timeout, records running/success/failure/runtime and republishes snapshot. |
| `queue_command()` | Validates command mapping, creates queued job and starts worker; MQTT callback never blocks on long scripts. |
| `parse_control_payload()` | Accepts legacy plain command or JSON envelope with job_id/source; supports gradual agent upgrades. |
| `on_connect()` | Subscribes control topic and republishes retained jobs on reconnect. |
| `on_message()` | Decodes plain/JSON payloads and queues only configured command IDs; this remote callback has no retained-message rejection, so the sender must keep command retention off. |
| `main()` | Supplies command-listener callbacks/settings to the shared MQTT client factory, then uses the shared blocking loop mode; job execution remains local to this component. |

### Remote command protocol

`control_power` accepts either a legacy plain command ID such as `shutdown_delay`, or JSON such as `{"command":"run_watchtower","job_id":"abc123","source":"Homelab Panel"}`. Both forms are looked up in `config.json -> commands`; received text is never executed as shell code.

## `homelab-control/homelab_control_status_indicator.py`

| Function | What / why |
|---|---|
| `load_config()` | Loads remote status config. |
| `derive_related_topic()` | Gets explicit topic or derives sibling from last_message; boot topics work with older configs. |
| `derive_history_topic()` | Gets explicit history topic or derives /history for backward compatibility. |
| `ensure_dirs()` | Creates remote state/log directories before file writes. |
| `read_text_file()` | Reads state text with safe default. |
| `write_text_file()` | Atomically writes state text so sync loops do not see partial values. |
| `read_action()` | Reads current action with idle fallback. |
| `write_action()` | Writes current action atomically. |
| `get_uptime_seconds()` | Reads Linux /proc/uptime for retained uptime telemetry. |
| `get_current_boot_id()` | Reads Linux boot UUID used to distinguish reboot from service restart. |
| `get_boot_time_epoch()` | Computes approximate boot epoch from uptime. |
| `get_boot_time_iso()` | Formats boot epoch for MQTT/UI metadata. |
| `parse_timestamp()` | Parses stored ISO status timestamp for migration/boot comparison. |
| `load_history()` | Loads remote command/event history with malformed-file fallback. |
| `save_history()` | Caps and atomically writes remote history. |
| `current_command_record()` | Builds archive record from current last-command fields when meaningful. |
| `history_record_signature()` | Creates dedupe identity for command records. |
| `append_history_record()` | Appends history with optional dedupe. |
| `archive_current_command_status()` | Archives pre-boot current status only if not already stored. |
| `clear_current_command_status()` | Clears current command/result/message on a real new boot. |
| `is_new_machine_boot()` | Compares saved/current boot IDs with migration fallback; service restart does not trigger cleanup. |
| `append_boot_history()` | Adds categorized boot event with boot ID/time. |
| `initialize_boot_state()` | Performs boot rollover archive/clear/action reset and saves current boot ID. |
| `publish()` | Common retained/non-retained Paho publish helper. |
| `publish_history()` | Publishes complete retained remote history JSON. |
| `publish_command_status()` | Publishes current command/result/message/timestamp topics. |
| `on_connect()` | Publishes online/action/hostname/uptime/boot/current status/history after reconnect. |
| `on_disconnect()` | Placeholder callback; LWT/clean shutdown handle power availability. |
| `uptime_loop()` | Periodically republishes online and uptime. |
| `action_sync_loop()` | Republishes action only when local action file changes. |
| `command_status_sync_loop()` | Republishes current command fields only when local state changes. |
| `main()` | Initializes boot state, supplies status callbacks/LWT to the shared MQTT factory, starts the shared threaded loop, then owns local sync threads/signals/clean offline shutdown. |
| `handle_signal()` *(nested in `main`)* | Sets the shared stop event for SIGTERM/SIGINT; lets the service exit through its clean offline publish/disconnect path. |

## Shell functions

| Function | What / why |
|---|---|
| `run_shutdown_command()` | Runs shutdown directly as root or through sudo otherwise; shared scripts work for remote agent and local panel. |
| `json_get()` | Reads required dotted JSON config key with Python parser. |
| `json_get_optional()` | Reads optional dotted key with default; older configs remain compatible. |
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
- `status_topic` defaults to `homeassistant/status`; an empty string disables the birth subscription. `status_online_payload` defaults to `online`. Older configs use these defaults without edits.
- On broker connect or HA birth, `publish_home_assistant_snapshot()` offers discovery, online availability and cached sensor state. Subsequent monitor passes publish fresh state.
- Remote discovery topics remain `<discovery_prefix>/button/homelab_panel_<device_id>/<button_id>/config`; Wake uses the existing `wake` ID. Local buttons use `<discovery_prefix>/button/homelab_local_panel/<button_id>/config` to avoid a remote device called `local` colliding with the host.
- Remote `payload_press` is `{"device_id":"...","command":"..."}`. Local `payload_press` is `{"target":"local","command":"..."}`. Both go to the panel control topic and select configured IDs rather than executable text.
- HA button labels come from the same `label` fields as web buttons. Local grouping uses `LOCAL_SERVER.name` as the Home Assistant device name; older configs without `name` fall back to `LOCAL_SERVER.title`. This keeps the webpage section heading separate from the HA device identity. Cancel-WoL stays registered in HA and refuses cancellation without an active job.
- Navigation/history filters/login/logout do not represent device actions and have no HA button entities.
- Discovery creates entities, not custom dashboard cards. Python configuration is loaded at startup; adding/editing buttons requires a panel restart. Removing a config entry prevents its execution but does not automatically delete a retained discovery document.

## Browser functions and callbacks in `templates/index.html`

| Function / callback | What / why |
|---|---|
| `fitFiveJobs()` | Measures the first five job cards and caps the list's height so older jobs remain reachable by scrolling. |
| `.job-list` `forEach` callback | Initializes each device's list independently and restores its saved scroll offset after page refresh. |
| `scroll` event callback | Saves that device list's scroll offset to session storage; errors are ignored when storage is unavailable. |
| `ResizeObserver` callback | Recalculates the five-job height only when width changes, avoiding repeated work from height-only updates. The window resize listener supplies a fallback. |
| Form `confirm(...)` handlers | Ask for the configured browser confirmation before a web action is submitted; they do not execute on HA MQTT presses. |

## External commands and embedded Python

| Command / block | What / why |
|---|---|
| `python3 app.py` | Starts Flask plus the panel MQTT/status background workers; there are no app CLI flags. |
| `python3 homelab_control_command_listener.py` | Loads the agent allow-list and runs the MQTT command listener. |
| `python3 homelab_control_status_indicator.py` | Starts Linux availability/boot/uptime/current-status publication; Linux `/proc` supplies uptime and boot identity. |
| `python3 homelab_mqtt.py --config PATH --topic TOPIC --qos 1 --retain` | Publishes the stdin payload as retained telemetry through Paho. The same CLI without `--retain` can send commands. The JSON config supplies credentials without placing them in argv. |
| `wakeonlan -i BROADCAST MAC` | Sends a magic packet to the configured broadcast destination. |
| `ping -c 1 -W TIMEOUT HOST` | Gets one bounded reachability sample: `-c 1` sends one probe and `-W` uses seconds on Linux or milliseconds on macOS; the caller also applies a three-second process timeout. |
| `shutdown -h +1`, `shutdown -r +1`, `shutdown -c` | `-h` schedules shutdown/halt, `-r` schedules reboot, `+1` is one minute, and `-c` cancels either operation. The shared helper uses `sudo` only for non-root execution. |
| `json_get` / `json_get_optional` Python heredocs | Parse dotted JSON keys rather than evaluating shell text; the optional variant supplies missing-key defaults. |
| `append_command_history` Python heredoc | Locks the shared event file, classifies the command, appends/caps history and replaces the file atomically. |
| `history_payload` Python heredoc | Produces compact JSON for retained history publication, with malformed/missing-file fallback. |
| `systemctl daemon-reload`, `enable --now`, `restart`, `status` | Reload unit definitions, enable/start services, reload app configuration, or inspect service state. |
| `journalctl -u UNIT -f` | Restricts log output to one unit and follows new messages. |
| `python3 -B -m unittest discover -s tests -v` | Runs the offline regression checks without writing bytecode; verbose discovery selects the included test directory. |

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

The README's **Command flag reference** documents the values, units, and examples for operator-facing commands. The three long-running Python applications and power scripts have no argument parser; passing `--help` to those entry points does not create a safe inspection mode. The separate `homelab_mqtt.py` publisher does support safe `--help`.

## `tests/test_home_assistant.py`

Panel tests use real Flask/Jinja with example configuration, temporary runtime files, captured publications and blocked subprocess/network startup. The shared Paho publisher is blocked explicitly in the fixture. No live MQTT, WoL or power commands run.

| Function / method | What / why |
|---|---|
| `load_panel()` | Imports the real app with example config modules while mocking MQTT-client construction and thread startup, keeping tests independent of active configs and networks. |
| `setUp()` | Gives each test a fresh panel, temporary state directory, Flask client, publication capture, and blockers for subprocesses and the shared Paho publisher. |
| `capture()` (nested) | Records MQTT publication arguments for assertions without contacting a broker. |
| `button_configs()` | Extracts button discovery JSON from captured messages for entity/payload checks. |
| `test_every_web_action_is_discovered_with_its_label()` | Verifies every example remote/WoL/local action, label, stable ID, topic, and non-retained command. |
| `test_local_device_name_falls_back_to_title_for_old_configs()` | Removes the new local `name` setting and verifies older configs still publish the previous `title` as the HA device name. |
| `test_custom_buttons_and_namespace_do_not_need_code_changes()` | Adds custom local/remote buttons via config and checks discovery plus actual shared dispatch; a remote device named local cannot collide with the panel host. |
| `test_discovery_disabled_disconnected_or_missing_control_topic()` | Checks discovery opt-out, broker gating, and omission of buttons when no usable command topic exists. |
| `test_web_and_mqtt_local_buttons_share_execution()` | Checks that web/MQTT choose the same configured script and reject unknown/ambiguous targets or path-like IDs. |
| `test_web_auth_and_token_still_protect_local_route()` | Confirms that refactoring the local dispatcher preserves session/token access protection. |
| `test_retained_control_is_rejected_for_both_targets()` | Verifies stale retained local and remote commands never start a worker. |
| `test_live_control_dispatches_worker_and_legacy_remote_envelope()` | Verifies fresh messages use the worker dispatcher and existing remote JSON remains supported. |
| `test_local_script_path_guards_are_preserved()` | Checks traversal, absolute paths, symlink escapes, missing files, and non-executable files without running a command. |
| `test_home_assistant_birth_republishes_discovery_and_cached_state()` | Checks restart recovery with discovery retention disabled, retained availability/state, and no callback pings. |
| `test_birth_defaults_customization_and_disabled_subscription()` | Verifies old-config defaults, custom HA topic/payload, empty-topic opt-out and globally disabled discovery. |
| `test_confirmation_title_placeholder_resolves_and_is_js_safe()` | Verifies `$TITLE` resolves from the configured device title, literal confirmations remain unchanged, and apostrophes are safely JSON-encoded in rendered JavaScript. |
| `test_webpages_still_render()` | Exercises the real Flask/Jinja dashboard, history, diagnostics and login pages after the integration change. |

## `shared_modules/mqtt.py`

| Function | What it does / why it exists |
|---|---|
| `create_client()` | The single project-wide long-running client factory: builds Paho MQTT v3.1.1 with callback-API compatibility, optional reconnect backoff, auth, Last Will, and caller-owned callbacks. Both components use it without importing each other. |
| `connect_client()` | Starts a configured client in the requested synchronous, threaded, asynchronous-threaded, or connect-only network-loop mode; preserves each service's previous loop semantics. |
| `derive_related_topic()` | Resolves an explicitly configured status topic or derives a sibling from `/last_message`; replaces duplicated topic-derivation logic in panel and control status code. |
| `decode_message_payload()` | Decodes MQTT message payloads as stripped UTF-8 with replacement for malformed bytes; panel and control listener use the same safe behavior. |
| `publish_client_message()` | Publishes through an existing client, normalizes Paho return status, and optionally waits for local publish completion; reused by panel and both control processes. |
| `_publish_once()` | Implements the no-reconnect disposable MQTT send used by command/status one-shot publishing, including validation, deadline processing, and transport shutdown on uncertain failure. |
| `network_step()` (nested in `_publish_once`) | Advances the disposable client network loop only within the remaining hard deadline and turns Paho loop errors/timeouts into a failed one-shot send. |
| `publish_message()` | Runs `_publish_once()` by launching `shared_modules/mqtt.py` itself as the worker process, so DNS/connect/send are bounded by a hard parent timeout and credentials/payload stay off argv; the root CLI wrapper is not part of transport execution. |
| `cli_main()` | Implements the standalone MQTT CLI argument/config/stdin handling once inside the shared module; root `homelab_mqtt.py` is only an executable adapter. |

`shared_modules/mqtt.py` is intentionally the only shared Python implementation module in this release. Component-specific panel state/HA/actions and control jobs/status remain inside their own directories so the two components share infrastructure, not each other's application logic.

## `homelab_mqtt.py`

This root executable intentionally contains no MQTT implementation functions. It imports `cli_main` as `main` plus the one-shot publish symbols from `shared_modules/mqtt.py` for CLI use/backward import compatibility, then exits with `main()` when executed. Keeping this adapter at the root preserves existing shell/service paths while the implementation exists only once.


## `tests/test_mqtt_publish.py`

Unit tests use fake clients/processes where precise failure injection is needed. Protocol tests use the actual installed Paho client and the production child-process path against a minimal peer on `127.0.0.1`, with ephemeral ports, socket timeouts, and bounded thread joins. No real homelab device, power action, or external MQTT broker is used.

| Function / method | What / why |
|---|---|
| `PublisherTests.client()` | Builds a controllable MQTT client test double so unit cases can inject broker acceptance and acknowledgements. |
| `connect_callback()` | Invokes the real callback with a chosen CONNACK result without opening a socket. |
| `test_settings_payload_qos_and_retention_are_preserved()` | Checks broker credentials, port, exact Unicode/whitespace payload, fixed keepalive, QoS 0/1/2, retention, and absence of retry/background-loop calls. |
| `test_default_command_is_nonretained_and_unauthenticated()` | Checks default command retention, optional authentication, port, and keepalive. |
| `test_refused_connection_never_publishes()` | Confirms rejected connections cannot send a command and close the transport. |
| `test_connect_exception_and_publish_error_fail()` | Confirms socket exceptions and non-success publish return codes propagate as failures. |
| `test_timeout_closes_socket_before_disconnect_without_retry()` | Verifies failure cleanup order prevents disconnect from flushing a late command. |
| `test_invalid_inputs_fail_before_connecting()` | Rejects empty/wildcard topics, invalid QoS, and nonpositive/nonfinite deadlines before client creation. |
| `test_client_construction_supports_paho_callback_versions()` | Checks API v2 construction and an emulated older Paho constructor. |
| `test_parent_bounds_worker_and_keeps_credentials_off_argv()` | Checks the same interpreter, private stdin request, timeout, and handling of a killed worker. |
| `test_panel_reuses_shared_publisher_and_config()` | Checks panel delegation, retained config semantics, and error propagation without an external command call in the panel dispatcher. |
| `test_cli_reads_credentials_from_config_and_payload_from_stdin()` | Checks exact input forwarding, flag values, and success/failure exit codes. |
| `test_cli_help_and_config_errors()` | Checks safe help and missing-file errors without network activity. |
| `test_shell_bridge_payload_and_failure_exit()` | Executes the actual Bash library with a Python shim to verify argv, exact stdin, quiet empty-topic handling, and propagated failure. Config-reading commands still run through real Python. |
| `WireTests.read_packet()` | Reads an MQTT packet with its variable-length header for assertions on real wire bytes. |
| `read_string()` | Decodes MQTT length-prefixed fields so credentials, topic, and payload can be checked independently. |
| `exchange()` | Starts the bounded localhost peer and invokes the production Paho publishing path, then checks thread completion/errors. |
| `serve()` (nested in `exchange`) | Receives CONNECT/PUBLISH, returns configured CONNACK/PUBACK or QoS 2 handshake packets, and observes transport shutdown. |
| `test_real_paho_qos_zero_one_two_and_retention()` | Verifies real authentication flags, clean session, exact topic/payload bytes, retained flag, and all three QoS completion paths. |
| `test_real_paho_rejected_connection_sends_no_command()` | Rejects a real connection and verifies no PUBLISH follows. |
| `test_real_paho_missing_ack_times_out_and_closes()` | Withholds PUBACK, verifies uncertain-delivery failure and socket closure without retry. |

## Release support files

- `VERSION` contains the current three-part version.
- `VERSIONING.md` records the version policy and each release's actual changes.
- `VALIDATION.md` records checks, environment limits, and the original/final file comparison for this package.
