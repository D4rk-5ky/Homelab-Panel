# Homelab Panel

**Current version: 0.0.3**

Homelab Panel is a Flask-based homelab control panel plus an MQTT-driven remote control/status agent.

The project has two parts:

- `homelab-panel/` — web panel, Wake-on-LAN sender, MQTT status listener, MQTT control receiver, and local shutdown/reboot controls.
- `homelab-control/` — remote MQTT agent that executes only configured command scripts and publishes retained device/status/history information.

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
- optionally checks a query-string token before allowing web access/actions;
- pings configured remote devices;
- listens for retained MQTT power/action/command/result/message/history state;
- considers a device online only when both ping succeeds and a fresh MQTT power state equals `online`;
- sends Wake-on-LAN through the external `wakeonlan` command;
- publishes configured remote control payloads through `mosquitto_pub`;
- accepts a dedicated MQTT control topic so another MQTT client, such as Home Assistant, can tell the panel to power on, shut down, cancel shutdown, reboot, or cancel reboot for a configured remote device;
- rejects retained incoming panel-control messages so an old destructive command is not replayed after reconnect;
- exposes a History button in every remote-device status card;
- displays remote history in separate Command, Result, and Message categories with the original date/time;
- runs configured local shutdown/reboot scripts;
- refreshes the main browser page automatically at the configured interval.

### Remote agent

The remote agent consists of two Python services plus shared shell helpers:

- `homelab_control_command_listener.py` subscribes to `topics.control_power`. Only payloads present in `commands` can launch a script.
- `homelab_control_status_indicator.py` publishes retained power/action/hostname/uptime/current-command state plus retained command history.
- `homelab_control_lib.sh` is sourced by the remote shutdown/reboot scripts and writes current status plus a runtime command log.

On a real machine reboot, the status indicator:

1. detects the changed Linux boot ID;
2. archives the previous boot's last command/result/message if it contains meaningful command data;
3. preserves the original `last_updated` time as the history event timestamp;
4. stores the archive in `state/history.json`;
5. limits history to `timing.history_max_entries`;
6. clears current `last_command`, `last_result`, and `last_message`;
7. resets `action` to `idle`;
8. publishes the cleared current values and complete retained history over MQTT.

Restarting only the status service during the same Linux boot does **not** create another history entry or clear the current status.

For migration from a version that did not yet store `boot_id`, the agent compares `last_updated` with the current Linux boot time. It archives only when the existing status clearly predates the current boot.

## 2. Dependencies

### Common Linux commands

- `python3`
- `ping`
- `shutdown`
- `systemctl` when using the included systemd units

### Panel host

Python packages:

```bash
python3 -m pip install flask paho-mqtt
```

System commands:

```bash
sudo apt install mosquitto-clients wakeonlan
```

### Remote agent host

Python package:

```bash
python3 -m pip install paho-mqtt
```

System command:

```bash
sudo apt install mosquitto-clients
```

The supplied remote units run as root because the remote scripts invoke `shutdown` directly. Review this before installation.

## 3. Panel configuration

The active panel configuration files are intentionally **not shipped or tracked**, because they contain machine-specific settings and may contain credentials. Create them from the supplied examples before starting the panel:

```bash
cp homelab-panel/config.example.py homelab-panel/config.py
cp homelab-panel/devices.example.py homelab-panel/devices.py
```

Edit the newly created local files for your environment. Git ignores `homelab-panel/config*` and `homelab-panel/devices*` except for the two `*.example.py` files.

### `homelab-panel/config.py`

`WOL_BROADCAST`
: Broadcast address passed to `wakeonlan -i`.

`MQTT_CONFIG["host"]`
: MQTT broker hostname/IP.

`MQTT_CONFIG["port"]`
: MQTT TCP port.

`MQTT_CONFIG["user"]`
: MQTT username. Empty disables username authentication.

`MQTT_CONFIG["pass"]`
: MQTT password.

`MQTT_CONFIG["qos"]`
: QoS used by panel-originated `mosquitto_pub` messages.

`MQTT_CONFIG["retain"]`
: Whether panel-originated device-control MQTT messages are retained. For shutdown/reboot control, `False` is strongly recommended to avoid replaying an old command.

`MQTT_CONFIG["client_id_panel_status"]`
: MQTT client ID for the panel listener.

`MQTT_CONFIG["panel_control_topic"]`
: Topic the panel subscribes to for JSON control requests. Set it to an empty string to disable MQTT control of the panel.

`PANEL_TOKEN`
: Optional web query-string token. Empty disables token checking.

`LOCAL_SCRIPT_PATH`
: Absolute directory containing the local panel helper scripts.

`MQTT_ONLINE_TTL_SECONDS`
: Maximum age of the last received MQTT power message before it is treated as stale.

`PAGE_REFRESH_SECONDS`
: Browser auto-refresh interval for the main page.

### `homelab-panel/devices.py`

`REMOTE_DEVICES` is keyed by a unique `device_id` such as `aoostar_wtr`.

Each device supports:

- `title`
- `wol`
- `status`
- `mqtt_controls`

#### `wol`

- `enabled` — whether Wake-on-LAN is allowed/shown.
- `label` — UI label.
- `mac` — MAC address used by Wake-on-LAN.
- `ip` — IP address used for ping status.
- `confirm` — browser confirmation text.

#### `status`

- `power_topic`
- `action_topic`
- `last_command_topic`
- `last_result_topic`
- `last_message_topic`
- `last_updated_topic`
- `history_topic` — retained JSON history published by the remote status agent.

An empty topic disables reception of that field. History pages for devices without `history_topic` simply show that no history is available.

#### `mqtt_controls`

Set to `None` when the device has no remote MQTT controls. Otherwise:

- `title` — UI heading.
- `topic` — remote agent control topic.
- `buttons` — allow-listed controls.

Each button contains:

- `id`
- `label`
- `payload`
- `color`
- `icon`
- `confirm`

The panel MQTT-control receiver reuses these button definitions. It does not accept an arbitrary target MQTT topic or arbitrary payload from the incoming control JSON.

#### `LOCAL_SERVER`

Local panel action definitions. Each button contains:

- `id`
- `label`
- `script`
- `color`
- `icon`
- `confirm`

## 4. Remote-agent configuration

The active remote-agent configuration is also intentionally **not shipped or tracked**. Create it from the supplied example on each remote host:

```bash
cp homelab-control/config.example.json homelab-control/config.json
```

Edit `config.json` for that host. Git ignores `homelab-control/config*` except for `config.example.json`.

### `homelab-control/config.json`

#### `mqtt`

- `host`
- `port`
- `user`
- `pass`
- `keepalive`

#### `client_ids`

- `status` — status publisher client ID.
- `command_listener` — remote command listener client ID.

Use unique client IDs for simultaneously connected clients.

#### `topics`

- `control_power` — remote command listener subscription.
- `status_power` — retained `online`/`offline`.
- `status_action` — retained `idle`, `shutdown_pending`, or `reboot_pending`.
- `status_hostname` — retained hostname.
- `status_uptime` — retained uptime seconds.
- `status_last_command` — retained current-boot last command.
- `status_last_result` — retained current-boot last result.
- `status_last_message` — retained current-boot last message.
- `status_last_updated` — retained current-boot timestamp.
- `status_history` — retained JSON array containing archived previous-boot status entries.

#### `timing`

- `publish_uptime_every` — seconds between power heartbeat/uptime publications.
- `history_max_entries` — maximum archived boot-session entries retained in `state/history.json` and published on `status_history`. Minimum effective value is 1.

#### `commands`

Mapping from received remote-agent payload to a script filename under `homelab-control/scripts/`.

Default mapping:

| Payload | Script |
| --- | --- |
| `shutdown_delay` | `shutdown_delay.sh` |
| `shutdown_cancel` | `shutdown_cancel.sh` |
| `reboot_delay` | `reboot_delay.sh` |
| `reboot_cancel` | `reboot_cancel.sh` |

The remote listener never passes the received payload directly to a shell.

## 5. MQTT control of Homelab Panel

The panel can receive a JSON object on `MQTT_CONFIG["panel_control_topic"]`.

Required fields:

- `device_id` — exact key from `REMOTE_DEVICES`.
- `command` — one of the supported actions below.

Supported panel commands:

| Command | Behavior |
| --- | --- |
| `power_on` | Send Wake-on-LAN to the configured device. |
| `shutdown` | Alias for the configured `shutdown_delay` button; supplied config schedules shutdown in 1 minute. |
| `shutdown_delay` | Execute the configured remote `shutdown_delay` control. |
| `shutdown_cancel` | Execute the configured remote shutdown/reboot cancel control. |
| `reboot` | Alias for the configured `reboot_delay` button; supplied config schedules reboot in 1 minute. |
| `reboot_delay` | Execute the configured remote `reboot_delay` control. |
| `reboot_cancel` | Execute the configured remote shutdown/reboot cancel control. |

Only commands backed by the selected device's existing configuration are executed. For example, a device with only Wake-on-LAN and `mqtt_controls = None` can receive `power_on` but cannot receive shutdown/reboot through the panel.

### Examples

Power on Aoostar WTR:

```bash
mosquitto_pub \
  -h YOUR_BROKER \
  -t 'homelab-panel/control' \
  -m '{"device_id":"aoostar_wtr","command":"power_on"}'
```

Schedule shutdown:

```bash
mosquitto_pub \
  -h YOUR_BROKER \
  -t 'homelab-panel/control' \
  -m '{"device_id":"aoostar_wtr","command":"shutdown"}'
```

Cancel shutdown:

```bash
mosquitto_pub \
  -h YOUR_BROKER \
  -t 'homelab-panel/control' \
  -m '{"device_id":"aoostar_wtr","command":"shutdown_cancel"}'
```

Schedule reboot:

```bash
mosquitto_pub \
  -h YOUR_BROKER \
  -t 'homelab-panel/control' \
  -m '{"device_id":"aoostar_wtr","command":"reboot"}'
```

Cancel reboot:

```bash
mosquitto_pub \
  -h YOUR_BROKER \
  -t 'homelab-panel/control' \
  -m '{"device_id":"aoostar_wtr","command":"reboot_cancel"}'
```

Add `-u USER -P PASSWORD` when required by the broker.

### Important retained-message rule

Do **not** publish panel control requests with MQTT retain enabled. Version 0.0.2 explicitly rejects an incoming control message when the MQTT message itself is marked retained.

MQTT control is not protected by `PANEL_TOKEN`; it is protected by your MQTT broker authentication and ACL rules. Restrict who can publish to the panel control topic.

## 6. Direct remote-agent MQTT control

You can still publish directly to a remote agent without going through the panel:

```bash
mosquitto_pub -h YOUR_BROKER -t 'aoostar/control/power' -m 'shutdown_delay'
mosquitto_pub -h YOUR_BROKER -t 'aoostar/control/power' -m 'shutdown_cancel'
mosquitto_pub -h YOUR_BROKER -t 'aoostar/control/power' -m 'reboot_delay'
mosquitto_pub -h YOUR_BROKER -t 'aoostar/control/power' -m 'reboot_cancel'
```

## 7. Command history

The remote agent stores history in:

```text
homelab-control/state/history.json
```

A history entry contains:

- `timestamp` — when the archived command/result/message last changed;
- `archived_at` — when a later machine boot moved it into history;
- `command`;
- `result`;
- `message`.

The status agent publishes the complete capped list to `topics.status_history` as retained JSON.

The panel reads the configured `history_topic` and the History button on each remote status card opens:

```text
/history/<device_id>
```

The history page displays three separate categories:

- Command history
- Result history
- Message history

Every displayed value includes the original `timestamp`.

## 8. Commands and flags

### No CLI flags

There is currently no argument parser in any supplied Python entry point or shell script. There are no supported `--flags`, short options, subcommands, or positional configuration arguments.

### Run the panel

```bash
cd homelab-panel
python3 app.py
```

### Run the remote command listener

```bash
cd homelab-control
python3 homelab_control_command_listener.py
```

### Run the remote status indicator

```bash
cd homelab-control
python3 homelab_control_status_indicator.py
```

### Remote scripts

```bash
homelab-control/scripts/shutdown_delay.sh
homelab-control/scripts/shutdown_cancel.sh
homelab-control/scripts/reboot_delay.sh
homelab-control/scripts/reboot_cancel.sh
```

### Local panel scripts

```bash
homelab-panel/scripts/shutdown_delay.sh
homelab-panel/scripts/shutdown_cancel.sh
homelab-panel/scripts/reboot_delay.sh
homelab-panel/scripts/reboot_cancel.sh
```

### Observe MQTT

```bash
mosquitto_sub -h YOUR_BROKER -t 'aoostar/#' -v
mosquitto_sub -h YOUR_BROKER -t 'homelab-panel/#' -v
```

## 9. Flask routes

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/` | Main control/status page. |
| `GET` | `/history/<device_id>` | Per-device history page. |
| `POST` | `/wol/<device_id>` | Send configured Wake-on-LAN. |
| `POST` | `/mqtt/<device_id>/<button_id>` | Execute a configured remote MQTT control. |
| `POST` | `/local/<button_id>` | Execute a configured local helper script. |

When `PANEL_TOKEN` is non-empty, include `?token=...`. Generated panel/history links preserve the current token.

## 10. Status logic

A device is displayed as Online only when:

1. its configured IP responds to ping;
2. the panel has received its MQTT `power_topic`;
3. the MQTT value is `online`;
4. the message age is within `MQTT_ONLINE_TTL_SECONDS`.

Otherwise the device is displayed Offline.

The remote status service uses an MQTT last-will of `offline` and republishes `online` with its uptime heartbeat.

## 11. Runtime files

Remote runtime state may include:

```text
homelab-control/state/action
homelab-control/state/last_command
homelab-control/state/last_result
homelab-control/state/last_message
homelab-control/state/last_updated
homelab-control/state/boot_id
homelab-control/state/history.json
homelab-control/logs/commands.log
```

These machine-specific runtime files are intentionally not included in clean release ZIPs.

## 12. systemd installation

Included units:

- `homelab-control/homelab-control-command-listener.service`
- `homelab-control/homelab-control-status-indicator.service`
- `homelab-panel/homelab-controll.service`

Review and edit host-specific paths, users, and groups before installing.

Typical flow:

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

## 13. Security and safety notes

- Restrict Flask to trusted networks or a properly secured reverse proxy.
- Use MQTT authentication and ACLs.
- Permit publishing to the panel control topic only from trusted clients.
- Never expose the development Flask server or unauthenticated MQTT broker directly to the Internet.
- Keep panel control messages non-retained.
- Keep `MQTT_CONFIG["retain"] = False` for destructive device-control payloads unless you fully understand the replay implications.
- Change the placeholder Flask `app.secret_key`.
- Treat `PANEL_TOKEN` only as a basic web gate, not full authentication.
- Review all root/sudo privileges and scripts.
- Test shutdown, reboot, cancellation, history rollover, and Wake-on-LAN outside production first.

## 14. Project documentation

- `README.md` — current usage/configuration/behavior only.
- `commented_code_map.md` — every current function, route, script, service, command interface, and its purpose.
- `VERSIONING.md` — release history and version policy.
- `VERSION` — current release number.
- `.gitignore` — keeps machine-specific active configuration files out of Git while preserving the three example configuration files.

## 15. Adding a device

1. Add the device to `REMOTE_DEVICES`.
2. Configure Wake-on-LAN if needed.
3. Configure status topics.
4. Configure `history_topic` if the remote agent publishes history.
5. Configure `mqtt_controls` if shutdown/reboot control is required.
6. Install/configure the remote agent on that machine when status/control/history is needed.
7. Keep local active configuration files updated on installed systems, and update the tracked example files whenever available configuration options change. Active `config.py`, `devices.py`, and `config.json` are intentionally ignored and excluded from release ZIPs.
