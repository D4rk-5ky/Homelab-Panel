# commented_code_map.md

Current-code map for Homelab Panel. This is not release history; it explains what each current function/command/file does and why it exists.

## `homelab-panel/app.py`

| Function | What / why |
|---|---|
| `web_auth_enabled()` | Returns whether optional session login is enabled; centralizes the feature gate so routes do not implement their own auth rules. |
| `validate_web_auth_config()` | Rejects empty/default credentials when login is enabled; fails closed before the server accepts requests. |
| `session_authenticated()` | Checks the Flask session authentication flag; keeps password data out of the session. |
| `credentials_match()` | Compares supplied/configured username and password with constant-time comparison; reduces trivial timing leakage. |
| `require_web_login()` | Global before-request guard that redirects every non-login/static route when authentication is required; protects current and future routes by default. |
| `check_token()` | Applies the legacy query token only when session login is disabled; preserves older deployments. |
| `run_command()` | Runs a fixed argv command with timeout and captured output; avoids shell=True and gives callers one error format. |
| `load_json_file()` | Loads a JSON runtime file with a safe default on missing/corrupt data; runtime state should not crash the panel. |
| `save_json_file_atomic()` | Writes JSON via temporary file + replace; prevents readers seeing partially written state. |
| `get_device_button()` | Finds a configured mqtt_controls button by ID; the same allow-list drives web, panel MQTT, jobs and HA. |
| `get_related_status_topic()` | Returns an explicit status topic or derives a sibling from last_message; keeps older active configs compatible. |
| `get_hostname_topic_for_status_cfg()` | Gets/derives the remote hostname topic; older devices.py files can expose hostname without immediate edits. |
| `get_uptime_topic_for_status_cfg()` | Gets/derives the remote uptime topic; older devices.py files can expose uptime/HA sensor without immediate edits. |
| `get_jobs_topic_for_status_cfg()` | Gets/derives the remote job snapshot topic; avoids duplicated topic-derivation logic. |
| `get_boot_id_topic_for_status_cfg()` | Gets/derives boot ID topic; supports boot detection without forcing immediate config migration. |
| `get_boot_time_topic_for_status_cfg()` | Gets/derives boot-time topic; provides boot metadata while keeping old configs valid. |
| `get_device_category()` | Resolves an event/job category from the button or command; powers history filtering and job grouping. |
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
| `mqtt_publish()` | Publishes a command with mosquitto_pub using configured credentials/QoS; preserves the existing external-client command path. |
| `send_wol()` | Sends a Wake-on-LAN magic packet through wakeonlan; isolates the OS command from retry/orchestration logic. |
| `run_local_script()` | Resolves a direct local action filename only inside `PROJECT_ROOT/scripts`, verifies it is executable, and runs it without `shell=True`; shared power helpers stay centralized and path traversal is rejected. |
| `ping_host()` | Runs one bounded Linux ping; ping remains independent from MQTT. |
| `set_mqtt_state()` | Caches payload, receive time, retain and QoS metadata; supports status evaluation and diagnostics. |
| `set_mqtt_connected()` | Tracks broker connectivity and connect/disconnect timestamps/reason; stale cached online data cannot count as current MQTT online. |
| `get_mqtt_connected()` | Returns current broker connection state. |
| `get_mqtt_state()` | Returns cached state for one topic; central read path for status/diagnostics. |
| `get_mqtt_payload_and_age()` | Returns stripped payload plus age in seconds; TTL checks use one implementation. |
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
| `wol_job_active()` | Reports whether a device has an active retryable WoL job; controls conditional cancel UI. |
| `finish_wol_job()` | Finalizes WoL job, expected state and history; success/failure/cancel share one terminal path. |
| `wol_worker()` | Runs WoL send/retry, ping confirmation and optional MQTT confirmation asynchronously; web requests remain responsive. |
| `start_wol_job()` | Validates WoL config, creates job/cancel event and starts worker; prevents duplicate concurrent WoL loops per device. |
| `cancel_wol_job()` | Signals the active WoL worker to stop and records the request; cancel exists only for an actual active job. |
| `cancel_power_confirmation()` | Stops an in-progress shutdown/reboot confirmation watcher for the device. |
| `power_confirmation_worker()` | Confirms shutdown by ping+MQTT offline and reboot by offline-then-online; physical state decides completion. |
| `execute_remote_action()` | Dispatches only configured WoL/cancel or dynamic device buttons, optionally with JSON job envelope; arbitrary commands remain rejected. |
| `execute_and_record_remote_action()` | Creates panel job/history around dispatch and starts expected-state/power confirmation when relevant; web and panel-control MQTT share one path. |
| `process_panel_control_message()` | Parses panel-control JSON device_id+command and routes it through the same allow-list dispatcher; retained messages are rejected before this function. |
| `process_remote_jobs_message()` | Parses retained remote job snapshots, archives unseen lifecycle changes and merges matching job IDs; script exit results reach the dashboard without using panel-control. |
| `handle_boot_id_message()` | Detects changed remote boot ID, clears provisional panel command state and records boot event; service restarts with same boot ID do not look like new boots. |
| `format_duration()` | Formats seconds for uptime/transition display. |
| `publish_mqtt_direct()` | Publishes through the live Paho client; HA state/discovery do not spawn mosquitto_pub processes. |
| `home_assistant_enabled()` | Returns the optional HA Discovery feature gate. |
| `ha_state_topic()` | Builds the per-device retained HA state topic from config. |
| `ha_device_block()` | Builds common Home Assistant device-registry metadata so all entities group under one device. |
| `publish_home_assistant_discovery()` | Publishes discovery sensors/buttons for every device and every configured custom button; UI allow-list automatically becomes HA controls. |
| `publish_home_assistant_state()` | Publishes combined status, ping, uptime, command/job and expected-state JSON for HA entities. |
| `monitor_device_transition()` | Persists true combined-state transitions and previous-state duration, marking unexpected offline as errors. |
| `status_monitor_loop()` | Periodically evaluates devices independent of page views, updates cache/history and HA state; ping works even when MQTT is absent. |
| `start_status_monitor()` | Starts exactly one background monitor thread per process. |
| `build_mqtt_diagnostics()` | Builds broker/subscription/topic metadata and per-device expected-topic table for the diagnostics page. |
| `on_connect_compat()` | Marks broker connected, subscribes all configured/derived topics, publishes HA discovery/availability and records MQTT connect event. |
| `on_disconnect_compat()` | Marks broker disconnected, stores reason and records MQTT disconnect events; cached online is no longer trusted. |
| `on_message_compat()` | Caches message metadata, dispatches panel-control, job and boot handlers, and power transitions; central MQTT receive path. |
| `build_mqtt_client()` | Creates Paho client with compatibility fallback, reconnect delay and optional HA LWT. |
| `start_mqtt_listener()` | Starts background status monitor and asynchronous MQTT reconnect loop; web/ping stay usable if broker is down at startup. |
| `login()` | GET/POST login route; creates session only after credential match. |
| `logout()` | POST route that clears the web session. |
| `index()` | Main dashboard route; renders cached remote status, jobs, controls and local actions. |
| `device_history()` | Per-device event/history route with category/errors filtering. |
| `wol()` | POST web route starting the shared asynchronous WoL workflow. |
| `wol_cancel()` | POST route cancelling an active WoL retry/confirmation workflow. |
| `mqtt_diagnostics()` | Protected diagnostics route showing broker/subscription/expected-topic state. |
| `mqtt_button()` | POST route dispatching any configured dynamic remote button through the shared action path. |
| `local_button()` | POST route executing only configured LOCAL_SERVER scripts. |

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

- `templates/index.html` — combined ping+MQTT status, expected state, current command fields, parallel job dashboard, WoL/cancel, all dynamic MQTT buttons, local controls and diagnostics link.
- `templates/history.html` — filtered event timeline plus separate Command/Result/Message history views.
- `templates/mqtt_diagnostics.html` — broker, subscription and per-device expected-topic diagnostics.
- `templates/login.html` — minimal username/password session login page.

## `homelab-control/homelab_control_command_listener.py`

| Function | What / why |
|---|---|
| `load_config()` | Loads the remote JSON config before constants are derived; remote behavior is explicit per host. |
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
| `on_message()` | Decodes payload and queues only configured command IDs. |
| `build_client()` | Creates compatible Paho client. |
| `main()` | Configures credentials/callbacks, connects and runs MQTT loop forever. |

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
| `build_client()` | Creates compatible Paho status client. |
| `main()` | Initializes boot state, MQTT LWT, sync threads, signals and clean offline publish. |
| `handle_signal()` *(nested in `main`)* | Sets the shared stop event for SIGTERM/SIGINT; lets the service exit through its clean offline publish/disconnect path. |

## Shell functions

| Function | What / why |
|---|---|
| `run_shutdown_command()` | Runs shutdown directly as root or through sudo otherwise; shared scripts work for remote agent and local panel. |
| `json_get()` | Reads required dotted JSON config key with Python parser. |
| `json_get_optional()` | Reads optional dotted key with default; older configs remain compatible. |
| `ensure_dirs()` | Creates remote state/log directories. |
| `timestamp_now()` | Returns local ISO command timestamp. |
| `mqtt_pub()` | Publishes retained remote status using configured credentials. |
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
- `scripts/homelab_action_common.sh` — resolves `SCRIPT_DIR`, then the parent project root, optionally loads `homelab-control/homelab_control_lib.sh` when run as root on a configured agent, and selects root-vs-sudo shutdown execution.

## Configuration files

- `homelab-panel/config.example.py` — all panel/MQTT/auth/Home Assistant/monitor/history/job options. Active `config.py` is local-only and ignored.
- `homelab-panel/devices.example.py` — device capabilities, WoL retry, status topics, expected-state defaults, confirmation and dynamic command buttons. Active `devices.py` is local-only and ignored.
- `homelab-control/config.example.json` — remote broker/client/topics/timing and strict command-to-script allow-list. Active `config.json` is local-only and ignored.

## Repository hygiene / `.gitignore`

- Active `homelab-panel/config.py`, `homelab-panel/devices.py`, and `homelab-control/config.json` remain ignored while their `*.example.*` templates remain tracked.
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
- MQTT control executes only device/button IDs configured in `devices.py`.
- Remote Homelab Control independently allow-lists command IDs in `config.json`; bundled power script names resolve from `PROJECT_ROOT/scripts`, while project-specific custom jobs are not moved by this release.
- Local panel power-script lookup rejects traversal/nested names, and the remote listener keeps strict direct-filename handling for its configured jobs.
- Retained panel-control messages are never executed.
- MQTT publish success means only “sent”; script success comes from remote job exit code, and power completion additionally uses ping/MQTT state confirmation.
