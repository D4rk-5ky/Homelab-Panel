# Homelab Panel

Homelab Panel monitors and controls homelab devices through a Flask webpage and MQTT. It supports Wake-on-LAN, configured remote jobs, local shutdown/reboot controls, device history, and optional automatic Home Assistant buttons.

- `homelab-panel/`: webpage, ping/MQTT status, jobs, history, Home Assistant discovery, plus its own `configs/` and `modules/` directories.
- `homelab-control/`: optional agent on each remote Linux host; keeps its JSON configuration in `configs/`, its reusable shell helper in `modules/`, runs explicitly allowed scripts, and publishes status/results.
- `shared_modules/`: generic code that is genuinely reused by both components; currently MQTT transport only.
- `scripts/`: shared Linux shutdown/reboot scripts and their common helper.
- `tests/`: regression checks for Home Assistant, command dispatch, and Paho publishing; protocol tests use localhost only.

### Panel code layout

The panel is intentionally split by responsibility without turning every helper into a separate module:

| File | Responsibility |
|---|---|
| `homelab-panel/app.py` | Directly executable Flask entry point; routes/authentication plus shared panel persistence, history, jobs, expected-state/status evaluation, monitor orchestration, and thin delegates into `modules/` |
| `homelab-panel/configs/` | Active `config.py`/`devices.py` live here beside their tracked examples; `app.py` resolves this directory from its own location, not the shell working directory |
| `homelab-panel/modules/` | Panel-specific reusable Python implementations; kept separate from the entry point without becoming separate services |
| `homelab-panel/modules/panel_actions.py` | Local script execution guards, Wake-on-LAN retry/cancel mechanics, shutdown/reboot confirmation, and configured remote action dispatch |
| `homelab-panel/modules/panel_mqtt.py` | Panel-specific MQTT behavior only: topic selection, receive cache, diagnostics, HA birth handling, control/status/job dispatch, and panel event hooks; it uses the shared `MqttClient`/publisher instead of implementing Paho transport |
| `homelab-panel/modules/panel_home_assistant.py` | Home Assistant MQTT Discovery documents, local/remote buttons, HA availability snapshots, and per-device state payloads |
| `shared_modules/mqtt.py` | The single generic MQTT implementation for both components: common `MqttClient` lifecycle/subscriptions/decoded callbacks/publish/stop behavior, auth/Last Will/reconnect setup, topic derivation, bounded one-shot publishing, and the standalone MQTT CLI |

`app.py` remains the owner of persistent panel history/jobs/runtime state because those concerns are tightly coupled to status evaluation and the web views. Generic MQTT transport is implemented once in root `shared_modules/mqtt.py` and is imported independently by both `homelab-panel` and `homelab-control`; neither component imports the other component's modules. The three extracted modules receive callbacks/providers from `app.py` instead of duplicating that state. Panel configuration is loaded from `homelab-panel/configs/`; remote-agent configuration is loaded from `homelab-control/configs/`. Project-specific reusable implementations live under each component's `modules/` directory while entry points stay directly executable. Configuration keys, web routes, MQTT topics/payloads, Home Assistant entity IDs, safety allow-lists, and power-script behavior are unchanged by this layout.

`shared_modules/` is shared infrastructure, not another service and not a place for component-specific helpers. The panel can run without Homelab Control running, and Homelab Control can run without the panel running. If you deploy only the remote agent to another machine, keep `homelab-control/` under a project root that also contains `shared_modules/` and the shared `scripts/` needed by its configured actions; you do **not** need to copy `homelab-panel/` to that machine.

## Automatically create the webpage buttons in Home Assistant

1. Configure Home Assistant's **MQTT integration** with the same broker as Homelab Panel and leave MQTT discovery enabled.
2. In your active `homelab-panel/configs/config.py`, set:

   ```python
   HOME_ASSISTANT_CONFIG = {
       "enabled": True,
       "discovery_prefix": "homeassistant",
       "state_prefix": "homelab-panel/ha",
       "availability_topic": "homelab-panel/availability",
       "status_topic": "homeassistant/status",
       "status_online_payload": "online",
       "qos": 1,
       "retain": True,
   }
   ```

3. Set the broker/credentials in `MQTT_CONFIG`. Keep `panel_control_topic` nonempty and `MQTT_CONFIG["retain"] = False`.
4. Configure your webpage buttons in `homelab-panel/configs/devices.py` and restart Homelab Panel. No separate Home Assistant YAML is required for each button.
5. In Home Assistant, open **Settings → Devices & services → MQTT** to find the devices and their button entities. You can add these entities to your chosen dashboard; discovery does not edit an existing custom dashboard layout.

The following controls are created automatically:

| Webpage control | Home Assistant button / destination |
|---|---|
| Each enabled Wake-on-LAN button | Same configured `wol.label`, under the remote device |
| Cancel Wake-on-LAN | `Annullér Wake-on-LAN`, under the remote device |
| Every `REMOTE_DEVICES[...]["mqtt_controls"]["buttons"]` entry | Same configured label, under the remote device |
| Every `LOCAL_SERVER["buttons"]` entry | Same configured label, under a separate device named from required `LOCAL_SERVER["name"]` |

Local buttons act on **the machine running Homelab Panel**. Remote buttons retain their existing remote-device routing. Local and remote buttons can have the same ID without sharing an entity. Navigation, history filters, login, and logout are webpage controls rather than device action entities.

The cancel-WoL entity remains registered in Home Assistant; it only cancels an active WoL job. The webpage displays its cancel button only while a job is active. A Home Assistant press uses the same application action as the webpage, but the webpage's JavaScript confirmation dialog is not transferred to Home Assistant. Delayed shutdown/reboot scripts still schedule their action one minute later, and cancellation remains available.

Discovery runs when the panel connects/reconnects to MQTT and when Home Assistant announces its configured online status. Existing remote entity IDs are stable. Add or edit a button in `homelab-panel/configs/devices.py` and restart the panel to publish it. Removing a config entry prevents it from executing, but an old retained discovery entry/entity may need manual removal from the broker/Home Assistant. This app does not automatically delete previously discovered entities.

Home Assistant also receives combined-online and ping binary sensors, uptime, last-command, and job-status sensors for each remote device. Combined online requires both ping and fresh MQTT `power=online` while the panel is connected to the broker.

Protocol references: [Home Assistant MQTT discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery) and [MQTT buttons](https://www.home-assistant.io/integrations/button.mqtt/).

## Installation

Use **Python 3.10 or newer**. The agent, bundled power scripts, and systemd examples target Linux. The panel's ping helper supports Linux and macOS timeout units; Linux power commands do not become macOS-compatible merely by running the webpage on a Mac.

On Debian/Ubuntu:

```bash
sudo apt update
sudo apt install python3 python3-flask python3-paho-mqtt wakeonlan iputils-ping
```

`apt update` refreshes package metadata; `apt install` installs Python, Flask, the distribution Paho MQTT client, `wakeonlan`, and `ping`. The shared MQTT transport supports both the **Paho MQTT 1.x callback API** and **Paho MQTT 2.x callback API v2**. It automatically omits the v2-only constructor argument when `CallbackAPIVersion` is unavailable and accepts both callback signature shapes. `sudo` runs the package commands with administrator privileges. A reachable MQTT broker is needed for MQTT control/status and Home Assistant discovery. All application publishing and subscriptions use `paho-mqtt`; Mosquitto command-line clients are not required. A Mosquitto broker can still serve as your MQTT server. Install Paho in the Python environment used by both the panel and the agent/action scripts.

From the project root, create the active configs:

```bash
cp homelab-panel/configs/config.example.py homelab-panel/configs/config.py
cp homelab-panel/configs/devices.example.py homelab-panel/configs/devices.py
cp homelab-control/configs/config.example.json homelab-control/configs/config.json
chmod +x scripts/*.sh
```

`cp` copies each example to its active filename inside that component's `configs/` directory. Create the remote JSON config only on hosts using the agent. `chmod +x` makes the bundled action scripts executable. Edit hostnames, credentials, device addresses, MAC addresses, topics, and allowed commands before starting services. Keep the full project layout: the panel imports its own `configs/` and `modules/` relative to `app.py`, the remote agent resolves `configs/config.json` and `modules/homelab_control_lib.sh` relative to its own directory, and both independently add the project root only so they can import `shared_modules/` and find the shared `scripts/` directory. Neither component imports code from the other component.

The active configuration locations are exact: `homelab-panel/configs/config.py`, `homelab-panel/configs/devices.py`, and (when the agent is used) `homelab-control/configs/config.json`. Other config locations are not read.

Do not overwrite your active configs when upgrading. Copy relevant new options from the examples; the optional Home Assistant status-topic options have defaults when omitted. Active configs and runtime state/logs are ignored by Git and omitted from clean release packages.

### Start manually

```bash
cd homelab-panel
python3 app.py
```

The panel listens on `http://HOST:5000/` (bind address `0.0.0.0`, port `5000`). These are fixed in the entry point, not configurable CLI options. The panel starts its MQTT listener and status monitor even when imported, so use one process for this setup.

On a remote Linux host, run each agent in its own terminal, from the project root:

```bash
sudo python3 homelab-control/homelab_control_status_indicator.py
sudo python3 homelab-control/homelab_control_command_listener.py
```

The status indicator publishes availability, uptime, boot metadata, current command status, and history. The command listener accepts configured MQTT commands and runs their scripts. The provided services run these as root for power operations. Local webpage power actions use `sudo shutdown` when the panel runs without root; configure a suitably restricted noninteractive sudo policy for your installation.

### Run as systemd services

Edit each supplied unit's `User`, `Group`, `WorkingDirectory`, and `ExecStart` to match your host. `ExecStart` must point to the Python file in the retained full project layout. The existing example paths/usernames are deployment placeholders.

After editing, from the project root:

```bash
sudo cp homelab-panel/homelab-controll.service /etc/systemd/system/
sudo cp homelab-control/homelab-control-command-listener.service /etc/systemd/system/
sudo cp homelab-control/homelab-control-status-indicator.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now homelab-controll.service
sudo systemctl enable --now homelab-control-status-indicator.service homelab-control-command-listener.service
```

Install only the services used on that host. `daemon-reload` rereads unit files. `enable --now` enables startup at boot and starts the service immediately. The original panel unit filename is `homelab-controll.service`.

Useful service commands:

```bash
sudo systemctl restart homelab-controll.service
systemctl status homelab-controll.service
journalctl -u homelab-controll.service -f
```

`restart` reloads the app and its configuration. `status` shows service health. `journalctl -u UNIT` limits logs to that unit; `-f` follows new log entries. Substitute either agent service name when investigating that agent.

## Panel configuration: `homelab-panel/configs/config.py`

### General settings

| Option | Type / example or default | Effect |
|---|---|---|
| `WOL_BROADCAST` | String, `"255.255.255.255"` | Broadcast address passed to `wakeonlan -i` |
| `MQTT_ONLINE_TTL_SECONDS` | Integer, `90` | Maximum age of received MQTT power status for online/offline confirmation |
| `STATUS_MONITOR_INTERVAL_SECONDS` | Integer, `10`, minimum `2` | Delay between background status-monitor passes |
| `PAGE_REFRESH_SECONDS` | Integer, `15` | Browser auto-refresh interval |
| `PANEL_HISTORY_MAX_ENTRIES` | Integer, example `500`, minimum `1` | Maximum persisted panel events per device |
| `PANEL_JOB_MAX_ENTRIES` | Integer, `100`, minimum `1` | Maximum persisted/displayed panel jobs per device |

### `MQTT_CONFIG`

| Key | Type / example | Effect |
|---|---|---|
| `host` | String, `"192.168.1.10"` | Broker hostname/IP |
| `port` | Integer, `1883` | Broker port |
| `user` | String, `""` | Broker username; empty skips username authentication |
| `pass` | String, `""` | Broker password |
| `qos` | Integer, `0`, `1`, or `2` | QoS for commands sent by the shared Paho publisher |
| `retain` | Boolean, `False` | Retention for forwarded remote commands; keep **False** to avoid replaying a power command |
| `client_id_panel_status` | String, `"homelab-panel-status"` | MQTT subscriber client ID; use a unique ID per running client |
| `panel_control_topic` | String, `"homelab-panel/control"` | JSON command input used by HA buttons; empty disables this input and button discovery |

Use broker ACLs to restrict who can publish to control topics. Website login does not authenticate MQTT clients. Incoming retained messages on the **panel** control topic are rejected. The separate remote agent does not currently reject retained commands, so never retain commands sent directly to its control topic either.

### `HOME_ASSISTANT_CONFIG`

| Key | Default | Effect |
|---|---|---|
| `enabled` | `False` | Set `True` to publish sensors and all configured webpage action buttons |
| `discovery_prefix` | `"homeassistant"` | Must match Home Assistant's MQTT discovery prefix |
| `state_prefix` | `"homelab-panel/ha"` | Remote sensor state topic prefix |
| `availability_topic` | `"homelab-panel/availability"` | Panel online/offline topic used by HA entities |
| `status_topic` | `"homeassistant/status"` | HA birth/status topic; a **live** matching online message triggers rediscovery, while a retained replay after panel subscribe is ignored; `""` disables this subscription |
| `status_online_payload` | `"online"` | Exact payload on `status_topic` that a live HA birth message must match to trigger rediscovery; match any HA birth-message customization |
| `qos` | `1` | QoS for discovery, HA state, and panel availability publication |
| `retain` | `True` | Retains discovery documents at the broker; HA state/availability are retained independently |

Keep discovery, state, availability, HA status, and control topics distinct. The HA button's own MQTT command always has `retain=False`; it uses HA's default button command QoS of `0`. Discovery retention does not change the separate `MQTT_CONFIG["retain"]` setting used for forwarding remote commands.

The panel publishes one Home Assistant snapshot as part of its own MQTT connect callback. MQTT brokers normally replay the retained HA `online` status when the panel then subscribes to `status_topic`; that replay is deliberately ignored because the connection snapshot has already been sent. A later **live** HA birth `online` message still republishes the snapshot, so an HA restart can recover discovery without creating an immediate duplicate discovery refresh on every panel connection. This changes discovery refresh behavior only; it never executes a Home Assistant button command.

### `WEB_AUTH_CONFIG`

| Key | Type / example | Effect |
|---|---|---|
| `enabled` | Boolean, `False` | Enable session-based website login |
| `username` | String, `"admin"` | Login username |
| `password` | String | Replace the example placeholder before enabling login |
| `secret_key` | String | Long random Flask session-signing key; replace the placeholder |
| `session_cookie_secure` | Boolean, `False` | Set `True` only when accessing the panel through HTTPS |

Generate a session key with:

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Python's `-c` runs the quoted expression; it prints 32 random bytes as hexadecimal. When login is enabled, all application pages/actions require a session except login and static files. Use HTTPS through a configured reverse proxy when credentials cross an untrusted network.

## Device configuration: `homelab-panel/configs/devices.py`

`REMOTE_DEVICES` maps a unique device ID to its configuration. `LOCAL_SERVER` defines buttons on the panel host. The examples include remote, ping-only, and local configurations.

### Remote device fields

| Field | Meaning |
|---|---|
| `title` | Device name on the webpage and in HA |
| `expected_state_default` | Initial expectation, normally `"unknown"`; persisted runtime state takes precedence |
| `wol` | Wake settings and IP used for ping, even when Wake is disabled |
| `status` | MQTT telemetry topics listed below |
| `confirmation` | Shutdown/reboot confirmation timeouts |
| `mqtt_controls` | Remote command group; `None` disables that group's buttons |

`wol` options:

| Key | Meaning |
|---|---|
| `enabled` | Whether to offer the Wake button |
| `label` | Wake button name on both the webpage and HA |
| `mac` | Target MAC address for the magic packet |
| `ip` | Target IP/hostname for ping and power confirmation |
| `confirm` | Webpage confirmation text; `$TITLE` is replaced with the owning device `title`; empty skips the browser prompt |
| `retry.enabled` | Whether to send further packets while waiting for ping; default `False` |
| `retry.interval_seconds` | Ping-wait window between attempts; default `15`, minimum `1` |
| `retry.max_attempts` | Maximum send attempts when retry is enabled; default `20`, minimum `1`; disabled retry sends once |
| `retry.wait_for_mqtt_seconds` | Extra wait after ping for MQTT online; default `120`, minimum `0` |

`status` topic keys:

| Key | Expected content |
|---|---|
| `power_topic` | `online` / `offline` |
| `action_topic` | `idle`, `shutdown_pending`, or `reboot_pending` |
| `hostname_topic` | Remote hostname |
| `uptime_topic` | Uptime in seconds |
| `last_command_topic` | Most recent command description |
| `last_result_topic` | Most recent result/status |
| `last_message_topic` | Most recent command message |
| `last_updated_topic` | ISO timestamp of current command status |
| `history_topic` | JSON list of remote events |
| `jobs_topic` | JSON list of remote job records |
| `boot_id_topic` | Linux boot UUID |
| `boot_time_topic` | Approximate ISO boot time |

Each status topic is configured explicitly. An empty topic disables that specific subscription; the panel does not derive missing topic names from another topic.

`confirmation.shutdown_timeout_seconds` defaults to `180`; `confirmation.reboot_timeout_seconds` defaults to `300`. Both have a minimum of 10 seconds and are fallback physical-state confirmation deadlines. The supplied example sets both to `60`. If the selected remote button defines `job_timeout_seconds`, that per-job lifecycle deadline takes precedence for shutdown/reboot confirmation.

### Remote buttons

`mqtt_controls` contains `title` (web group heading), `topic` (remote control topic), and `buttons` (list). Every remote command is sent as the current JSON job envelope with `command`, `job_id`, and `source`, so agent results can update the corresponding panel job.

Every button supports:

| Key | Meaning |
|---|---|
| `id` | Unique command ID within that device; used by web routing and HA |
| `label` | Visible name on the webpage and in HA |
| `payload` | Command ID allowed by the remote agent's `commands` map |
| `category` | History/job category, such as `power`, `maintenance`, `backup`, or `command` |
| `confirmation` | `shutdown`, `reboot`, or `none`; configure it explicitly for each button |
| `job_timeout_seconds` | Optional positive integer. While the job is still `queued`, `running`, `waiting`, or `confirming`, the panel shows a countdown and changes it to `timed_out` when this many seconds have elapsed from `started_at` (or `queued_at` if it has not started). Omit it for no panel lifecycle timeout. This does **not** kill the remote script. |
| `color` | Web button CSS class: `ok`, `warn`, `danger`, or `neutral` |
| `icon` | Web label icon/emoji; not copied to HA's separate MDI-icon field |
| `confirm` | Browser confirmation text; `$TITLE` is replaced with the owning device `title`; empty skips the browser prompt |

Use nonempty, stable device/button IDs containing letters, digits, `_`, or `-` for routes/discovery. `power_on` and `cancel_wol` are the panel's built-in WoL action IDs; configured MQTT buttons use their own explicit IDs. Labels can contain spaces and Unicode.

Use `$TITLE` when a confirmation should follow the configured device title automatically. The supplied examples use `$TITLE` by default for every non-empty `confirm` value, so changing a device `title` automatically updates its browser prompts. The replacement is performed only for the browser confirmation text; it does not change the button label, MQTT device ID, command payload, or Home Assistant entity. For example:

```python
"title": "Zotac RI531",
# ...
"confirm": "Er du sikker på at du vil slukke '$TITLE' om 1 minut?",
```

renders as `Er du sikker på at du vil slukke 'Zotac RI531' om 1 minut?`. Literal confirmation strings without `$TITLE` continue to work unchanged. Confirmation strings are JSON-encoded when inserted into the page, so quotes in the resolved text cannot break the JavaScript confirmation call. The same placeholder is accepted by local button confirmations and resolves against `LOCAL_SERVER["title"]`.

Example custom button:

```python
{
    "id": "run_watchtower",
    "label": "Kør Watchtower",
    "payload": "run_watchtower",
    "category": "maintenance",
    "confirmation": "none",
    "job_timeout_seconds": 3600,
    "color": "ok",
    "icon": "🐳",
    "confirm": "Kør Watchtower på '$TITLE'?",
}
```

Its remote `homelab-control/configs/config.json` must independently allow `run_watchtower`. The example Watchtower script is **not bundled**: provide your reviewed custom script before using that button. Plain custom filenames resolve from the project root; nested/absolute paths and symlinks escaping the allowed directory are rejected. External integrations need an executable wrapper at that supported location. The shared `scripts/` directory contains the built-in power helpers.

### Local buttons

`LOCAL_SERVER` contains `title`, `name`, and `buttons`. `title` is the local section heading on the Homelab Panel webpage. `name` is the required Home Assistant device name and should normally be the real machine/device name, for example `"Mac Mini"`; Home Assistant combines that device name with each button label. Each button has `id`, `label`, `script`, `color`, `icon`, and `confirm`, with the same display meanings as above. The supplied non-empty local `confirm` examples also use `$TITLE`, which resolves from `LOCAL_SERVER["title"]` rather than the separate Home Assistant `name`. `script` is a direct executable filename inside the project's `scripts/` directory. Both web and HA commands select an existing button ID; incoming MQTT cannot supply a script path or command arguments.

## Remote agent configuration: `homelab-control/configs/config.json`

| Section / keys | Meaning |
|---|---|
| `mqtt.host`, `mqtt.port` | Broker hostname/IP and port, e.g. `1883` |
| `mqtt.user`, `mqtt.pass` | Credentials; empty user skips authentication |
| `mqtt.keepalive` | MQTT keepalive seconds for the two long-running agent services, example `30`; one-shot publication uses fixed `60` |
| `client_ids.status` | Unique MQTT client ID for status publisher |
| `client_ids.command_listener` | Separate unique MQTT client ID for command listener |
| `topics.control_power` | Command input topic matching the panel's device `mqtt_controls.topic` |
| `topics.status_power`, `status_action` | Power availability and pending-action output topics |
| `topics.status_hostname`, `status_uptime` | Hostname and uptime outputs |
| `topics.status_last_command`, `status_last_result`, `status_last_message`, `status_last_updated` | Current command fields |
| `topics.status_history`, `status_jobs` | Retained JSON history and jobs snapshots |
| `topics.status_boot_id`, `status_boot_time` | Linux boot metadata |
| `timing.publish_uptime_every` | Seconds between online/uptime publishes, example `30`; keep below the panel's MQTT TTL |
| `timing.history_max_entries` | Remote event limit, example `500`, minimum `1` |
| `timing.job_history_max_entries` | Remote job limit, example `100`, minimum `1` |
| `timing.max_parallel_jobs` | Maximum scripts running at once, example `4`, minimum `1` |
| `commands` | Explicit command-ID → script specification allow-list |

All status/history/jobs/boot topics are explicit current configuration keys. Match every output topic to the panel's corresponding device topic.

Each command is an object:

```json
"run_watchtower": {
  "script": "run_watchtower.sh",
  "label": "Kør Watchtower",
  "category": "maintenance",
  "timeout": 3600
}
```

- `script`: required direct filename. The four bundled power filenames resolve under `scripts/`; other filenames resolve from the project root.
- `label`: job display label, default command ID.
- `category`: event category, default `command` when omitted.
- `timeout`: maximum **remote script execution** duration in seconds, default `60`, minimum `1`. If this expires, Homelab Control stops waiting for the script and reports the job as `timed_out`. This is separate from the panel button's optional `job_timeout_seconds`, which only controls how long an unresolved active job is considered active by the panel.

The panel and agent each maintain their own allow-list. MQTT text is never executed as shell code.

## Commands and interfaces

### Application CLI

Every directly executable project command now has a safe information-only CLI surface. The three long-running Python programs accept only `-h` / `--help` and `--version`; they have no runtime tuning flags. Unknown extra arguments are rejected with exit status `2` before Flask, MQTT, or active configuration is loaded. Runtime behavior still comes from the tracked configuration files.

Examples:

```bash
python3 homelab-panel/app.py --help
python3 homelab-panel/app.py --version
python3 homelab-control/homelab_control_status_indicator.py --help
python3 homelab-control/homelab_control_command_listener.py --version
```

The four bundled power scripts also accept only `-h` / `--help` and `--version`. These information-only flags exit before optional Homelab Control configuration is loaded and before any `shutdown` command is run. Running a power script with **no arguments** keeps its existing action; any other argument is rejected with exit status `2`. There is still no dry-run or configurable-delay flag.

`shared_modules/mqtt.py` is the standalone publishing helper. It has the same safe `--version` flag plus its MQTT publishing options documented below. Its `--help` / `--version` preflight runs before importing Paho, so those information-only commands work even on a host where `paho-mqtt` is not installed.

The executable helper libraries `scripts/homelab_action_common.sh` and `homelab-control/modules/homelab_control_lib.sh` expose `--help` / `--version` when run directly. They are still intended to be sourced by the action/runtime code and have no standalone operational mode.

### Web routes

| Method / route | Purpose |
|---|---|
| `GET /` | Dashboard, remote statuses, jobs, and action buttons |
| `GET/POST /login` | Show login / submit username and password |
| `POST /logout` | Clear the login session |
| `GET /history/<device_id>` | Event timeline; `?filter=all`, `errors`, or a category selects events |
| `GET /mqtt-diagnostics` | Broker status, subscriptions, latest values, timestamps, age, retain/QoS, and expected topics |
| `POST /wol/<device_id>` | Start Wake-on-LAN |
| `POST /wol-cancel/<device_id>` | Cancel an active WoL workflow |
| `POST /mqtt/<device_id>/<button_id>` | Run a configured remote button |
| `POST /local/<button_id>` | Run a configured panel-host button |

When `WEB_AUTH_CONFIG.enabled=True`, web actions require an authenticated Flask session. MQTT access is controlled separately by broker authentication and ACLs.

### Panel MQTT control

Send non-retained JSON to `MQTT_CONFIG["panel_control_topic"]`:

```json
{"device_id":"aoostar_wtr","command":"power_on"}
{"device_id":"aoostar_wtr","command":"cancel_wol"}
{"device_id":"aoostar_wtr","command":"run_watchtower"}
{"target":"local","command":"shutdown_cancel"}
```

Remote envelopes require `target="remote"`, `device_id`, and `command`. Local envelopes require `target="local"`, an allowed local button ID, and **no `device_id` field**. An unknown remote device never falls back to local execution. HA buttons generate these envelopes automatically.

Example manual cancellation from the project root, using an agent-format JSON config for the same broker:

```bash
printf '%s' '{"target":"local","command":"shutdown_cancel"}' | python3 shared_modules/mqtt.py --config homelab-control/configs/config.json --topic homelab-panel/control --qos 0
```

This command cancels a scheduled power operation on the panel host. `printf '%s'` passes the JSON verbatim on stdin. `--config` selects broker credentials from the file's `mqtt` object, `--topic` selects the destination, and `--qos 0` selects the delivery level. Leave `--retain` off for commands. On a panel-only host, a separate JSON file containing `{"mqtt":{"host":"BROKER","port":1883,"user":"USER","pass":"PASSWORD"}}` is sufficient; pass its path to `--config`.

The panel's outgoing commands and the agent shell helper both go directly through `shared_modules/mqtt.py`; Python callers use `publish_message()` and shell callers execute the same module's CLI. Current Python callers supply QoS and retain explicitly; the CLI applies its documented flag defaults before calling the same shared publisher. Each publication gets a fresh Paho client with a clean session and no reconnection loop. The parent enforces a 20-second timeout, including DNS and connection setup; it kills and waits for a timed-out child. Broker credentials and payloads pass through stdin, not command-line arguments. On failure after sending, delivery can be unknown, so the publisher does not retry automatically. This preserves the panel's command timeout and also bounds shell telemetry calls. Persistent status/subscription clients retain their existing reconnect behavior.

QoS 0 success means the message was sent locally; QoS 1/2 success waits for the corresponding MQTT acknowledgement. Neither proves that a remote script ran or that a machine completed a power transition. The one-shot client uses MQTT 3.1.1 and a fixed 60-second keepalive. See the [Paho client API](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html) for protocol completion semantics.

### Direct remote-agent MQTT control

The agent's `topics.control_power` accepts only the current JSON job envelope:

```json
{"command":"run_watchtower","job_id":"abc123","source":"Homelab Panel"}
```

`command` selects its allow-list entry. `job_id` is required and correlates the result with the panel job. `source` is required and identifies the caller. Results are published on `status_jobs`, not on the panel control topic. Do not send a panel `target` envelope directly to the agent.

### Command flag reference

#### Long-running Python programs

These commands all expose the same two information-only flags:

- `python3 homelab-panel/app.py`
- `python3 homelab-control/homelab_control_status_indicator.py`
- `python3 homelab-control/homelab_control_command_listener.py`

| Flag | Value / default | What it does | Safety / behavior |
|---|---|---|---|
| `-h`, `--help` | No value | Prints the command description, supported flags, and exits `0` | Runs before Flask/Paho/config loading and does not start the service |
| `--version` | No value | Prints the executable name plus the root `VERSION` value and exits `0` | Runs before service startup and does not contact MQTT or read active config |

There are no operational CLI overrides for bind address, ports, topics, credentials, polling intervals, devices, or commands. Configure those in `homelab-panel/configs/` and `homelab-control/configs/config.json`. Unknown arguments exit `2`.

#### Bundled power scripts

`scripts/shutdown_delay.sh`, `shutdown_cancel.sh`, `reboot_delay.sh`, and `reboot_cancel.sh` accept:

| Flag | What it does |
|---|---|
| `-h`, `--help` | Prints the script action and exits without invoking `shutdown` |
| `--version` | Prints the script name and project version, then exits without invoking `shutdown` |

No arguments means **perform the existing power action**. Any other argument is rejected with exit status `2`. There is no dry-run and no CLI delay override.

#### MQTT publisher

```bash
python3 shared_modules/mqtt.py --help
python3 shared_modules/mqtt.py --version
```

`--help` is safe: argument parsing exits before the helper reads stdin/configuration or contacts a broker. `--help` and `--version` are handled before Paho is imported. Normal publishing mode reads the MQTT payload **verbatim from stdin**. The table below lists every supported flag, including the internal worker flag so the complete interface is documented.

| Publisher flag | Value / required / default | What it does | Example / safety notes |
|---|---|---|---|
| `-h`, `--help` | No value; optional | Prints the complete CLI help and exits with status `0` | Safe inspection mode; no MQTT or payload work is started |
| `--version` | No value; optional | Prints the executable name plus the root project version and exits `0` | Information-only; no Paho import, config read, stdin read, or broker connection |
| `--config PATH` | Path string; required for normal CLI mode; mutually exclusive with `--request-stdin` | Opens JSON at `PATH` and reads its required top-level `mqtt` object for host/port/credentials | `--config homelab-control/configs/config.json`; credentials stay in the file rather than argv |
| `--request-stdin` | Boolean flag; **internal only**; mutually exclusive with `--config` | Reads one complete JSON worker request from stdin and prints JSON `[success, message]` | Used by `publish_message()` so a parent process can enforce a hard timeout. Do not use this as the normal manual interface. |
| `--topic TOPIC` | String; required with `--config` | Selects one exact MQTT destination. Empty topics and `+` / `#` wildcard topics are rejected before connecting. | `--topic homelab-panel/control`; the message body itself still comes from stdin |
| `--qos {0,1,2}` | Integer; optional; default `1` | Chooses MQTT delivery QoS: `0` at-most-once, `1` at-least-once, `2` exactly-once at the MQTT protocol level | Commands may use the QoS required by your setup; this does **not** prove a remote script succeeded |
| `--retain` | Boolean flag; optional; default **off** | Sets the MQTT retained flag on the publication | Appropriate for status/telemetry when intended. **Never retain power/control commands**, because a broker could replay them to a reconnecting subscriber. |
| `--timeout SECONDS` | Positive finite number; optional; default `20` seconds | Sets the total publication deadline, covering worker startup, DNS, connect, publish, and any required MQTT acknowledgement | Decimal values are accepted, e.g. `--timeout 2.5`; zero, negative, NaN, or infinity are rejected |

Normal mode example, publishing retained telemetry:

```bash
printf '%s' 'online' \
  | python3 shared_modules/mqtt.py \
      --config homelab-control/configs/config.json \
      --topic aoostar/status/power \
      --qos 1 \
      --retain \
      --timeout 20
```

Command example — note that `--retain` is deliberately omitted:

```bash
printf '%s' '{"target":"local","command":"shutdown_cancel"}' \
  | python3 shared_modules/mqtt.py \
      --config homelab-control/configs/config.json \
      --topic homelab-panel/control \
      --qos 0 \
      --timeout 20
```

Normal helper exit codes are `0` for a completed publication, `1` for config/input/publication failure, and `2` for invalid CLI syntax/arguments from `argparse`. In internal `--request-stdin` mode the helper reports publication success/failure in the JSON response; a syntactically valid worker invocation returns process status `0` after producing that response, and the parent interprets the boolean result.

The remaining flags below belong to external tools. They are **not** additional application flags for `app.py`, either Homelab Control daemon, or the bundled power scripts.

| Tool / flag | Value and effect | Example / source |
|---|---|---|
| `wakeonlan -i ADDRESS` | `-i` selects the destination broadcast address | `WOL_BROADCAST`, example `255.255.255.255`; the target MAC is the following positional argument |
| `ping -c COUNT` | `-c` sets the number of echo requests | Fixed to `1` by the panel |
| `ping -W TIMEOUT` | `-W` sets the per-reply timeout; units depend on OS | Fixed to `1` second on Linux and `1000` milliseconds on macOS |
| `shutdown -h +1` | `-h` requests Linux shutdown/halt; `+1` is the positional delay in minutes | Bundled delayed-shutdown script |
| `shutdown -r +1` | `-r` requests Linux reboot; `+1` is the positional delay in minutes | Bundled delayed-reboot script |
| `shutdown -c` | `-c` cancels a scheduled Linux shutdown or reboot | Both bundled cancel scripts use the same operation |
| `systemctl enable --now UNIT` | `enable` configures start-at-boot; `--now` also starts immediately | Use only for the supplied units needed on that host |
| `journalctl -u UNIT -f` | `-u` selects one systemd unit; `-f` follows new entries | `journalctl -u homelab-controll.service -f` |
| `chmod +x FILE` | `+x` adds executable permission using symbolic mode syntax | `chmod +x scripts/*.sh` |
| `python3 -c CODE` | `-c` executes the supplied Python code string | Used above to generate a Flask session key |
| `python3 -B ...` | `-B` disables Python bytecode writes | Used by the offline test command so checks do not create `__pycache__` |
| `python3 -m unittest ...` | `-m` runs a module; `discover` enables test discovery; `-s tests` selects the test directory; `-v` prints individual results | `python3 -B -m unittest discover -s tests -v` from the project root |

### Bundled power scripts and external flags

All four action scripts perform the listed action only when run with no arguments. `-h` / `--help` and `--version` are information-only and exit first; unsupported arguments exit `2`.

| Script / command | Behavior |
|---|---|
| `scripts/shutdown_delay.sh` → `shutdown -h +1` | Schedule shutdown in one minute; `-h` requests shutdown/halt, `+1` is the delay in minutes |
| `scripts/reboot_delay.sh` → `shutdown -r +1` | Schedule reboot in one minute; `-r` requests reboot |
| `scripts/shutdown_cancel.sh` → `shutdown -c` | Cancel a scheduled shutdown or reboot; `-c` means cancel |
| `scripts/reboot_cancel.sh` → `shutdown -c` | Same cancellation operation |
| `scripts/homelab_action_common.sh` | Sourced helper; resolves shared paths and selects direct root shutdown or `sudo shutdown` |
| `homelab-control/modules/homelab_control_lib.sh` | Sourced helper for config, command status, history, and retained telemetry |
| `wakeonlan -i BROADCAST MAC` | Send a magic packet; `-i` selects the broadcast destination |
| `ping -c 1 -W TIMEOUT HOST` | Send one probe (`-c 1`); `-W` is `1` second on Linux or `1000` milliseconds on macOS; subprocess timeout is three seconds |

Run action scripts by their path only when you intend the power operation. When run as root with an active remote-agent config, shared scripts also update agent command status/history and MQTT. Telemetry uses retained MQTT messages; command messages must remain non-retained.

## Status, jobs, and history

The dashboard lists each device’s newest jobs first. Each list shows approximately five job cards at a time; scroll within it for older jobs, up to `PANEL_JOB_MAX_ENTRIES`. Keyboard users can focus the list with Tab and scroll with arrow/Page Up/Page Down keys. Each device’s scroll position is saved in browser session storage across automatic refreshes when that storage is available.

- Ping and MQTT are evaluated independently. Both online gives `Online`; one alone gives `Ikke fuldt online`; neither gives `Offline`.
- MQTT online/offline confirmation needs a connected broker and a recent power status. Broker loss invalidates cached online status during evaluation.
- WoL sends/retries until ping responds, then waits for MQTT online when configured. Without a power topic, WoL completion can use ping alone even though the dashboard's combined online state still requires MQTT.
- Shutdown confirmation watches for ping offline plus MQTT offline. Reboot confirmation watches for that offline phase followed by ping and MQTT online. These watchers run after successful command dispatch. A button-level `job_timeout_seconds` overrides the fallback confirmation deadline for that job.
- MQTT publication success means `sent`, not successful script execution. Agent jobs normally report `queued → running → success/failure`; a script execution deadline or an unresolved panel lifecycle deadline reports `timed_out` instead. A timed-out job is not counted as active. A later real remote success/failure can replace a display-time timeout when new job state arrives.
- Job cards use green for `success`, red for `failure`, yellow/orange for active waiting/running states, and purple for `timed_out`. Active jobs with `job_timeout_seconds` show the remaining timeout seconds in the job metadata; after expiry the card explicitly states that the job is no longer considered active.
- Remote listener startup marks interrupted active jobs as failures. Panel jobs and event history are persisted, but in-memory confirmation/WoL workers are not resumed across panel restarts.
- Expected states include `unknown`, `starting`, `online`, `offline_pending`, `offline`, and `restarting`. They distinguish planned power actions from unexpected downtime.
- History records commands, results/messages, jobs, WoL attempts, availability transitions/durations, boot events, and MQTT connection events. Category and error filters are available.
- A new Linux boot ID clears the current remote command fields, resets the action, and appends a boot event to history. Restarting only a service during the same boot does not perform boot cleanup.

Runtime data lives under `homelab-panel/state/`, `homelab-control/state/`, and `homelab-control/logs/`. Keep needed runtime data when upgrading; it is not part of the clean source ZIP.

## Troubleshooting

If HA buttons do not appear, verify `enabled=True`, matching brokers/discovery prefixes, a nonempty panel control topic, and MQTT ACL permissions for discovery/control/status topics. Restart the panel after changing its Python configuration. If HA's birth message is customized, match `status_topic` and `status_online_payload`. A retained matching status received immediately after the panel subscribes is expected to be logged as ignored; only a live later HA birth triggers rediscovery because the panel already published its snapshot when the MQTT connection came up.

Use `/mqtt-diagnostics` to inspect subscriptions and received messages, including HA's status topic when enabled. If a remote action fails, check the agent allow-list, executable script location, dependencies, service logs, and published job result. HA local actions need the same sudo permissions as the webpage.

Review scripts before allowing them, protect MQTT with authentication/ACLs, and configure website login/HTTPS as appropriate. Discovery is disabled by default; enabling it exposes the configured action buttons to authorized MQTT clients. A successful power-script exit only proves scheduling/cancellation, not that a host has completed its physical power transition.

## Offline checks

With Python 3.10+, Flask, and a supported **paho-mqtt 1.x or 2.x** installed, from the project root:

```bash
python3 -B -m unittest discover -s tests -v
```

`-B` disables bytecode writes; `-m unittest` runs Python's test runner; `discover` finds tests, `-s tests` selects the directory, and `-v` shows individual results. The panel tests mock broker/subprocess activity and use temporary runtime state. Publisher tests also run a small MQTT protocol peer bound only to `127.0.0.1` on a temporary port, exercising the real Paho client. They require permission for localhost sockets and do not contact your broker or run real power commands.

Read `commented_code_map.md` for implementation explanations and `VALIDATION.md` for package verification details.

---

<a id="disclaimer-liability"></a>

## ⚠️ Disclaimer / Liability

[Homelab Panel — Disclaimer / Liability](#disclaimer-liability)

**Use this script at your own risk.**

The author takes **no responsibility or liability** for any data loss, service disruption, misconfiguration, service outage, missed backups, credential exposure, or other damage that may occur from using this script.

Before running it in production, you **must**:

- Read the entire source code
- Understand exactly what it does (and what it does _not_ do)
- Review and adapt it to your own environment
- Test it carefully in a non‑production setup

By using this script, **you accept full responsibility** for its effects.

⚠️ AI-assisted / vibe-coded experimental software. Use at your own risk.

<a id="disclaimer"></a>

## Disclaimer

[Homelab Panel — Disclaimer](#disclaimer)

This project is AI-assisted / vibe-coded software created as a hobby project. It has not been professionally audited and may contain bugs, unsafe behavior, data-loss issues, security problems, or incorrect assumptions.

You are responsible for reviewing the code, testing it in a safe environment, making backups, and understanding what it does before using it on real data. The author is not responsible for damage, data loss, broken systems, security issues, or other problems caused by using this software.

----
