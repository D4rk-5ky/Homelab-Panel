# Homelab Panel

**Current version: 0.0.1**

Homelab Panel is a small Flask-based homelab control panel plus an MQTT-driven remote control/status agent.

The project has two parts:

- `homelab-panel/` — the Flask web panel. It can show device state, send Wake-on-LAN packets, publish MQTT control messages, and run local shutdown/reboot helper scripts.
- `homelab-control/` — the remote agent. It subscribes to an MQTT control topic, runs only configured command scripts, stores status locally, and publishes retained MQTT status information.

## ⚠️ Disclaimer / Liability

**Use this project at your own risk.**

The author takes **no responsibility or liability** for any data loss, service disruption, misconfiguration, service outage, missed backups, credential exposure, or other damage that may occur from using this project.

Before running it in production, you **must**:

- Read the entire source code
- Understand exactly what it does (and what it does *not* do)
- Review and adapt it to your own environment
- Test it carefully in a non-production setup

By using this project, **you accept full responsibility** for its effects.

⚠️ AI-assisted / vibe-coded experimental software. Use at your own risk.

## Disclaimer

This project is AI-assisted / vibe-coded software created as a hobby project. It has not been professionally audited and may contain bugs, unsafe behavior, data-loss issues, security problems, or incorrect assumptions.

You are responsible for reviewing the code, testing it in a safe environment, making backups, and understanding what it does before using it on real data. The author is not responsible for damage, data loss, broken systems, security issues, or other problems caused by using this software.

---

## 1. Current behavior

### Web panel

The panel:

- serves a Flask web UI on `0.0.0.0:5000` when `app.py` is run directly;
- optionally checks a query-string token before allowing panel access or actions;
- pings each configured remote device;
- listens for configured retained MQTT status topics;
- considers a configured device **online only when both** its ping succeeds **and** its MQTT power state is `online` and fresh enough;
- sends Wake-on-LAN packets through the external `wakeonlan` command;
- publishes control payloads through the external `mosquitto_pub` command;
- runs configured local scripts for local shutdown/reboot actions;
- refreshes the browser page automatically at the configured interval.

### Remote agent

The remote agent consists of two long-running Python services plus shared shell helpers:

- `homelab_control_command_listener.py` subscribes to the configured MQTT control topic. A received payload is looked up in `config.json`; only a mapped script filename is run.
- `homelab_control_status_indicator.py` publishes retained power/action/host/command status and periodically publishes uptime.
- `homelab_control_lib.sh` is sourced by the remote shutdown/reboot scripts. It writes state, appends command logs, and publishes command status through `mosquitto_pub`.

The status indicator creates `state/` and `logs/` automatically when required. Runtime log/state files are intentionally not shipped in the clean release archive.

## 2. Dependencies

### Common Linux tools

The project expects these commands to exist where they are used:

- `python3`
- `ping`
- `shutdown`
- `systemctl` when using the included systemd units

### Panel host

Python packages:

```bash
python3 -m pip install flask paho-mqtt
```

System commands used by the panel:

```bash
sudo apt install mosquitto-clients wakeonlan
```

### Remote agent host

Python package:

```bash
python3 -m pip install paho-mqtt
```

System command used by the remote shell helper:

```bash
sudo apt install mosquitto-clients
```

The included remote systemd units run as `root`, because their scripts call `shutdown` directly. Review this before installation.

## 3. Configuration files

The release includes active sample configuration files and matching explicit example copies:

- `homelab-panel/config.py`
- `homelab-panel/config.example.py`
- `homelab-panel/devices.py`
- `homelab-panel/devices.example.py`
- `homelab-control/config.json`
- `homelab-control/config.example.json`

The example copies contain every configuration field currently supported by the code.

### 3.1 `homelab-panel/config.py`

#### `WOL_BROADCAST`

Broadcast address passed to `wakeonlan -i`. Example: `255.255.255.255`.

#### `MQTT_CONFIG`

- `host` — MQTT broker hostname or IP address.
- `port` — MQTT broker TCP port.
- `user` — broker username. Empty disables username authentication.
- `pass` — broker password.
- `qos` — QoS used by panel-originated `mosquitto_pub` messages.
- `retain` — whether panel-originated command messages are retained.
- `client_id_panel_status` — MQTT client ID used by the panel status listener.

#### `PANEL_TOKEN`

Optional token checked against `?token=...` on panel requests.

- Empty string: token checking is disabled.
- Non-empty string: the exact token must be present in the URL query string.

This is only a simple application-level gate. It is not a substitute for HTTPS, network access control, a reverse proxy, or proper authentication.

#### `LOCAL_SCRIPT_PATH`

Directory containing scripts named by `LOCAL_SERVER` in `devices.py`.

The included scripts are in `homelab-panel/scripts/`; set the path to the absolute installed location you actually use.

#### `MQTT_ONLINE_TTL_SECONDS`

Maximum age, in seconds, for the most recently received MQTT power message to count as fresh.

#### `PAGE_REFRESH_SECONDS`

Browser auto-refresh interval used by the HTML template.

### 3.2 `homelab-panel/devices.py`

`REMOTE_DEVICES` is a dictionary keyed by a unique device ID. Each device supports:

#### Device-level fields

- `title` — display name.
- `wol` — Wake-on-LAN settings.
- `status` — MQTT status topic settings.
- `mqtt_controls` — MQTT action panel or `None`.

#### `wol` fields

- `enabled` — show/use Wake-on-LAN for this device.
- `label` — button label.
- `mac` — target MAC address.
- `ip` — IP address used by the panel's ping status check.
- `confirm` — browser confirmation text.

#### `status` fields

- `power_topic`
- `action_topic`
- `last_command_topic`
- `last_result_topic`
- `last_message_topic`
- `last_updated_topic`

Empty topic strings disable reception for that individual status field. Because overall online state requires a fresh MQTT `power_topic` value of `online`, a device without a configured power topic will not be reported as fully online by the current logic even if ping succeeds.

#### `mqtt_controls` fields

Set the whole value to `None` when a device has no MQTT control buttons. Otherwise it supports:

- `title` — heading displayed in the web UI.
- `topic` — MQTT topic to publish button payloads to.
- `buttons` — list of button definitions.

Each button supports:

- `id` — URL/button identifier. It must be unique inside that device.
- `label` — visible label.
- `payload` — MQTT payload.
- `color` — CSS button class. The supplied template defines `warn`, `danger`, and `ok`.
- `icon` — visible icon/text prefix.
- `confirm` — optional browser confirmation message. Empty means no explicit confirmation attribute is added for MQTT buttons.

#### `LOCAL_SERVER`

- `title` — heading for local actions.
- `buttons` — list of local script buttons.

Each local button supports:

- `id`
- `label`
- `script`
- `color`
- `icon`
- `confirm`

### 3.3 `homelab-control/config.json`

#### `mqtt`

- `host` — MQTT broker hostname/IP.
- `port` — broker port.
- `user` — username; empty disables username authentication.
- `pass` — password.
- `keepalive` — MQTT keepalive in seconds for the Python clients.

#### `client_ids`

- `status` — client ID for `homelab_control_status_indicator.py`.
- `command_listener` — client ID for `homelab_control_command_listener.py`.

Each simultaneously connected MQTT client should have a unique ID.

#### `topics`

- `control_power` — topic subscribed to by the command listener.
- `status_power` — retained `online`/`offline` state.
- `status_action` — retained action state such as `idle`, `shutdown_pending`, or `reboot_pending`.
- `status_hostname` — retained hostname.
- `status_uptime` — retained uptime in seconds.
- `status_last_command` — retained last system command string.
- `status_last_result` — retained result (`running`, `success`, or `failure` from the supplied scripts).
- `status_last_message` — retained human-readable result message.
- `status_last_updated` — retained ISO-like local timestamp.

#### `timing.publish_uptime_every`

Seconds between power heartbeat/uptime publications by the status indicator.

#### `commands`

Mapping from received MQTT payload to a script filename in `homelab-control/scripts/`.

The supplied mapping is:

| MQTT payload | Script |
| --- | --- |
| `shutdown_delay` | `shutdown_delay.sh` |
| `shutdown_cancel` | `shutdown_cancel.sh` |
| `reboot_delay` | `reboot_delay.sh` |
| `reboot_cancel` | `reboot_cancel.sh` |

The listener does not execute an MQTT payload directly as a shell command. It first resolves the payload through this mapping and then runs the mapped executable file.

## 4. Commands and flags

### Important: there are currently no CLI flags

None of the Python entry points or supplied shell scripts implements command-line argument parsing. There are therefore no supported `--flags`, short options, subcommands, or positional configuration parameters to document in version 0.0.1.

Configuration is file-based. Operational control is performed by starting services/programs, using the web routes, or publishing one of the configured MQTT payloads.

### 4.1 Run the web panel directly

From the panel directory:

```bash
cd homelab-panel
python3 app.py
```

This starts the MQTT listener and Flask development server on port 5000.

### 4.2 Run the remote command listener directly

```bash
cd homelab-control
python3 homelab_control_command_listener.py
```

It subscribes to `topics.control_power` and runs only scripts mapped in `commands`.

### 4.3 Run the remote status indicator directly

```bash
cd homelab-control
python3 homelab_control_status_indicator.py
```

It publishes retained status and runs its periodic sync loops until terminated.

### 4.4 Remote action scripts

These scripts take no supported arguments:

```bash
homelab-control/scripts/shutdown_delay.sh
homelab-control/scripts/shutdown_cancel.sh
homelab-control/scripts/reboot_delay.sh
homelab-control/scripts/reboot_cancel.sh
```

The delay scripts request a shutdown/reboot in one minute. The cancel scripts call `shutdown -c`.

### 4.5 Local panel action scripts

These scripts also take no supported arguments:

```bash
homelab-panel/scripts/shutdown_delay.sh
homelab-panel/scripts/shutdown_cancel.sh
homelab-panel/scripts/reboot_delay.sh
homelab-panel/scripts/reboot_cancel.sh
```

They use `sudo shutdown ...`; the service account therefore needs suitable privilege configuration if these actions are enabled.

### 4.6 MQTT control from a shell

Using the sample Aoostar topic:

```bash
mosquitto_pub -h YOUR_BROKER -t 'aoostar/control/power' -m 'shutdown_delay'
mosquitto_pub -h YOUR_BROKER -t 'aoostar/control/power' -m 'shutdown_cancel'
mosquitto_pub -h YOUR_BROKER -t 'aoostar/control/power' -m 'reboot_delay'
mosquitto_pub -h YOUR_BROKER -t 'aoostar/control/power' -m 'reboot_cancel'
```

Add broker authentication options as required by your environment.

### 4.7 Observe MQTT state

```bash
mosquitto_sub -h YOUR_BROKER -t 'aoostar/#' -v
```

### 4.8 Flask HTTP routes

The template calls these routes:

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/` | Render current panel and device status. |
| `POST` | `/wol/<device_id>` | Send WoL to a configured/enabled device. |
| `POST` | `/mqtt/<device_id>/<button_id>` | Publish the configured MQTT button payload. |
| `POST` | `/local/<button_id>` | Run a configured local helper script. |

If `PANEL_TOKEN` is set, include `?token=THE_TOKEN` in these requests. The generated forms preserve the token when the index page was opened with it.

## 5. systemd installation

Three service-unit files are included:

- `homelab-control/homelab-control-command-listener.service`
- `homelab-control/homelab-control-status-indicator.service`
- `homelab-panel/homelab-controll.service`

**Review and edit all paths, users, and groups before installing them.** The uploaded project contains host-specific paths/users in these units; version 0.0.1 preserves that runtime configuration rather than silently changing deployment behavior.

Typical installation flow after editing a unit:

```bash
sudo cp your-edited.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now your-edited.service
```

Useful checks:

```bash
systemctl status homelab-control-command-listener.service
systemctl status homelab-control-status-indicator.service
journalctl -u homelab-control-command-listener.service
journalctl -u homelab-control-status-indicator.service
```

Use the actual installed panel unit name when checking the panel service.

## 6. Security and safety notes

Before production use:

- Restrict the web panel to trusted networks or protect it behind a properly configured reverse proxy/authentication layer.
- Use MQTT authentication and broker ACLs so untrusted clients cannot publish control payloads.
- Do not expose the MQTT broker or Flask development server directly to the public Internet.
- Change the Flask `app.secret_key` value in `homelab-panel/app.py`; the current source contains a clear placeholder string.
- Treat `PANEL_TOKEN` as a basic extra gate only. Query-string secrets can appear in browser history, proxy logs, and other logs.
- Review every shell script before allowing the panel/agent to run it.
- Review root/sudo privileges carefully. Shutdown/reboot control is intentionally powerful.
- Test Wake-on-LAN broadcast routing on your network before relying on it.
- Use unique MQTT client IDs.
- Back up configuration before changes.

## 7. Status logic

For a remote device to show **Online**, current code requires:

1. the configured IP address responds to `ping`;
2. a message has been received on the configured `power_topic`;
3. its payload is `online` (case-insensitive after receipt); and
4. the received message age is not greater than `MQTT_ONLINE_TTL_SECONDS`.

If any requirement fails, the device is displayed as Offline.

The remote status process also uses an MQTT last-will message of `offline` on `status_power`, and publishes `online` repeatedly along with uptime.

## 8. Runtime files

`homelab-control/homelab_control_status_indicator.py` and `homelab_control_lib.sh` create/use:

```text
homelab-control/state/action
homelab-control/state/last_command
homelab-control/state/last_result
homelab-control/state/last_message
homelab-control/state/last_updated
homelab-control/logs/commands.log
```

These files contain machine-specific runtime state/history. The clean release intentionally ships the `state/` and `logs/` directories empty; the software creates the files when required.

## 9. Project documentation

- `README.md` — current installation, configuration, commands, behavior, and safety notes only.
- `commented_code_map.md` — map of every function, route, supplied command script, service, and major configuration/data file, including why it exists.
- `VERSIONING.md` — version policy and per-version change history.
- `VERSION` — current release number.

## 10. Extending the project

To add a new remote device, add a new entry in `REMOTE_DEVICES` in `homelab-panel/devices.py`. The supplied template loops over that data, so ordinary device additions do not require new HTML.

To add a new remote MQTT command:

1. create an executable script in `homelab-control/scripts/`;
2. add a payload-to-filename entry in `homelab-control/config.json` under `commands`;
3. if it should be shown in the panel, add a corresponding button in the target device's `mqtt_controls.buttons` list;
4. update `config.example.json`, `devices.example.py`, `README.md`, and `commented_code_map.md` so the release stays synchronized.

Test new destructive actions outside production first.
