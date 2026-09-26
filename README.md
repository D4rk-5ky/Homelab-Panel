# Homelab Panel

**Current version: 0.0.8**

Homelab Panel is a Flask-based homelab control panel plus an MQTT-driven remote control/status agent.

The project has two parts:

- `homelab-panel/` — web panel, Wake-on-LAN sender, MQTT status listener, MQTT control receiver, and local shutdown/reboot controls.
- `homelab-control/` — remote MQTT agent that executes only configured command scripts and publishes retained device/status/history information.
- project-root action scripts — one shared set of shutdown/reboot helpers located beside `homelab-panel/` and `homelab-control/`.

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
- optionally protects every web page and web control route with a username/password login session;
- keeps the legacy query-string token available when username/password login is disabled;
- pings configured remote devices;
- listens for retained MQTT power/action/command/result/message/history state;
- considers a device online only when both ping succeeds and a fresh MQTT power state equals `online`;
- sends Wake-on-LAN through the external `wakeonlan` command;
- publishes configured remote control payloads through `mosquitto_pub`;
- accepts a dedicated MQTT control topic so another MQTT client, such as Home Assistant, can tell the panel to power on, shut down, cancel shutdown, reboot, or cancel reboot for a configured remote device;
- immediately shows panel-originated web/MQTT actions in the existing `Sidste kommando`, `Sidste resultat`, `Sidste besked`, and `Sidst opdateret` status fields; successful dispatch is shown as `Afsendt` until a newer real remote-agent command status arrives;
- rejects retained incoming panel-control messages so an old destructive command is not replayed after reconnect;
- exposes a History button in every remote-device status card;
- stores panel-originated device actions in persistent per-device panel history and merges them with remote-agent history;
- displays every stored command-status event in separate Command, Result, and Message categories with the original date/time and source;
- runs configured local shutdown/reboot scripts from the common project root;
- refreshes the main browser page automatically at the configured interval.

### Remote agent

The remote agent consists of two Python services plus shared shell helpers:

- `homelab_control_command_listener.py` subscribes to `topics.control_power`. Only payloads present in `commands` can launch a script.
- `homelab_control_status_indicator.py` publishes retained power/action/hostname/uptime/current-command state plus retained command history.
- `homelab_action_common.sh` is shared by all four root action scripts. When a script is executed as root and an active `homelab-control/config.json` exists, it reuses `homelab_control_lib.sh` so remote status/history behavior is preserved.

Every call to the remote helper's `write_command_status()` immediately appends a history event before the current status can be overwritten. A shutdown/reboot flow can therefore keep multiple messages, for example both `Attempting to schedule ...` and the later `... scheduled` result, instead of only preserving the final message.

On a real machine reboot, before the status service announces the new boot as online, it:

1. detects the changed Linux boot ID;
2. checks the previous current command/result/message;
3. adds that old current value to history only if an identical event is not already present;
4. clears current `last_command`, `last_result`, and `last_message`;
5. resets `action` to `idle`;
6. publishes `online`, the cleared current values, and the retained event history over MQTT.

Restarting only the status service during the same Linux boot does **not** clear the current status or create a duplicate boot-history event.

For migration from an older release that did not append every event, the boot rollover still archives a meaningful old current status when it is missing from history.

Panel-originated WoL/MQTT dispatches are also written to `homelab-panel/state/panel_action_history.json`. The dispatch remains visible as provisional current status until the remote device transitions to MQTT `online` or publishes newer real command status. On an `online` transition, the provisional panel status is cleared from the device card while its already-saved history event remains available on the History page.

## 2. Project layout

Keep the two application directories and the shared action scripts under the same parent directory:

```text
Homelab-Panel/
├── homelab-panel/
├── homelab-control/
├── homelab_action_common.sh
├── shutdown_delay.sh
├── shutdown_cancel.sh
├── reboot_delay.sh
└── reboot_cancel.sh
```

`homelab-panel/app.py` and `homelab-control/homelab_control_command_listener.py` locate the shared scripts from their own `__file__` path, not from the current shell directory or a configured absolute path. This means the layout can be moved as a unit without editing a script directory setting.

## 3. Dependencies

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

The supplied remote units run as root because the shared root action scripts invoke `shutdown` directly when executed by the remote command listener. When the same scripts are launched by a non-root panel process, they invoke `sudo shutdown`. Review sudo/root permissions before installation.

## 4. Panel configuration

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

`WEB_AUTH_CONFIG["enabled"]`
: Enables/disables username/password protection for the website. `False` keeps the previous behavior. `True` requires a valid login session before any panel/history/control route is accessible.

`WEB_AUTH_CONFIG["username"]`
: Username accepted by `/login`.

`WEB_AUTH_CONFIG["password"]`
: Password accepted by `/login`. Keep the active `config.py` private and choose a strong password. The password is compared in memory and is not stored in the browser session.

`WEB_AUTH_CONFIG["secret_key"]`
: Flask session-signing secret. Replace the example placeholder with a long random value before enabling web login. The application refuses to start with web login enabled while the example `CHANGE_ME` password/secret remains.

`WEB_AUTH_CONFIG["session_cookie_secure"]`
: Set `True` only when the panel is accessed over HTTPS. Leave `False` for direct plain-HTTP LAN access, otherwise the browser will not return the session cookie. Session cookies are also configured `HttpOnly` and `SameSite=Lax`.

`PANEL_TOKEN`
: Legacy optional query-string token. It is used only while `WEB_AUTH_CONFIG["enabled"]` is `False`. Empty disables token checking. When username/password login is enabled, the login session replaces the query-string token so both are not required at once.

`MQTT_ONLINE_TTL_SECONDS`
: Maximum age of the last received MQTT power message before it is treated as stale.

`PAGE_REFRESH_SECONDS`
: Browser auto-refresh interval for the main page.

`PANEL_HISTORY_MAX_ENTRIES`
: Maximum number of panel-originated history events retained per remote device in `homelab-panel/state/panel_action_history.json`. Older active configs that omit this option use 100.

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
- `history_topic` — retained JSON event history published by the remote status agent. If omitted/empty and `last_message_topic` ends in `/last_message`, the panel automatically derives the sibling `/history` topic for backward compatibility.

An empty/non-derivable topic disables remote history reception. Panel-originated history can still be shown for that device.

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

## 5. Web login

Username/password login is optional and disabled by default. Configure it in the local `homelab-panel/config.py` copied from `config.example.py`:

```python
WEB_AUTH_CONFIG = {
    "enabled": True,
    "username": "admin",
    "password": "YOUR_STRONG_PASSWORD",
    "secret_key": "YOUR_LONG_RANDOM_SECRET_KEY",
    "session_cookie_secure": False,
}
```

Generate a suitable random session secret, for example:

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

With `enabled=True`:

1. opening `/`, `/history/...`, or any web control endpoint redirects an unauthenticated browser to `/login`;
2. `/login` is the only application page available before authentication;
3. a successful login stores only an authenticated flag and username in the signed Flask session cookie;
4. the password is never put in the URL or stored in the session;
5. the **Log ud** button clears the session;
6. the login cookie is a browser-session cookie unless deployment code changes Flask's session lifetime behavior;
7. the legacy `PANEL_TOKEN` is not additionally required.

If a local `config.py` does not contain `WEB_AUTH_CONFIG`, the application treats username/password login as disabled. Add the block from `config.example.py` when you want to enable it.

This is intentionally simple application authentication. It does not provide TLS encryption or login rate limiting. Use HTTPS/reverse-proxy protection when traffic leaves a trusted LAN, and do not expose the Flask development server directly to the Internet.

## 6. Remote-agent configuration

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
- `status_history` — retained JSON array containing command-status events. If omitted and `status_last_message` ends in `/last_message`, the remote agent automatically derives the sibling `/history` topic.

#### `timing`

- `publish_uptime_every` — seconds between power heartbeat/uptime publications.
- `history_max_entries` — maximum remote command-status events retained in `state/history.json` and published on `status_history`. Minimum effective value is 1.

#### `commands`

Mapping from received remote-agent payload to a script filename in the common project root, beside `homelab-panel/` and `homelab-control/`.

Default mapping:

| Payload | Script |
| --- | --- |
| `shutdown_delay` | `shutdown_delay.sh` |
| `shutdown_cancel` | `shutdown_cancel.sh` |
| `reboot_delay` | `reboot_delay.sh` |
| `reboot_cancel` | `reboot_cancel.sh` |

The remote listener never passes the received payload directly to a shell.

## 7. MQTT control of Homelab Panel

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

Do **not** publish panel control requests with MQTT retain enabled. The panel rejects incoming control messages when the MQTT message itself is marked retained.

MQTT control is separate from the website login and `PANEL_TOKEN`; it is protected by your MQTT broker authentication and ACL rules. Restrict who can publish to the panel control topic.

### What appears in Remote enhedsstatus

When a valid panel-control message is accepted, Homelab Panel immediately records the dispatch for the selected device. It becomes visible in the existing status card on the next browser page load/automatic refresh:

- `Sidste kommando` shows the requested action, for example `Tænd / Wake-on-LAN`.
- `Sidste resultat` shows `Afsendt` when Homelab Panel successfully dispatched the WoL packet or MQTT publish. This means **sent**, not that the remote machine has already completed the requested action.
- `Sidste besked` includes the source (`MQTT <panel_control_topic>` or `Webpanel`) and a useful dispatch message.
- `Sidst opdateret` is the time the panel action started.

The current panel-side status is provisional and held in panel memory, but every panel-originated action is also persisted to `homelab-panel/state/panel_action_history.json`. If the remote agent later publishes newer `last_command`, `last_result`, `last_message`, and `last_updated` state, that real remote status automatically replaces the provisional panel result. When the device transitions to MQTT `online`, the provisional panel status is cleared from the status card; its history event is preserved. A Homelab Panel process restart clears only the provisional in-memory current state, not the persisted panel action history.

## 8. Direct remote-agent MQTT control

You can still publish directly to a remote agent without going through the panel:

```bash
mosquitto_pub -h YOUR_BROKER -t 'aoostar/control/power' -m 'shutdown_delay'
mosquitto_pub -h YOUR_BROKER -t 'aoostar/control/power' -m 'shutdown_cancel'
mosquitto_pub -h YOUR_BROKER -t 'aoostar/control/power' -m 'reboot_delay'
mosquitto_pub -h YOUR_BROKER -t 'aoostar/control/power' -m 'reboot_cancel'
```

## 9. Command history

History is event-based. Each call to the remote helper's `write_command_status()` creates its own entry immediately, so intermediate messages are not lost when the current status files are overwritten. Panel-originated WoL/MQTT dispatches create separate panel-history events as well.

Remote-agent history is stored in:

```text
homelab-control/state/history.json
```

Panel-originated action history is stored in:

```text
homelab-panel/state/panel_action_history.json
```

A history entry contains:

- `timestamp` — when that exact status/message event happened;
- `archived_at` — when the event was written/archived;
- `command`;
- `result`;
- `message`;
- `source` — normally `Remote enhed` or `Homelab Panel`.

The remote helper publishes the complete capped remote history as retained JSON on `topics.status_history`. When `status_history` is missing, `/history` is automatically derived from `status_last_message` when possible. The panel performs the same derivation when a device lacks explicit `history_topic`.

The History button on each remote status card opens:

```text
/history/<device_id>
```

The panel merges remote-agent history with its own panel-action history and sorts the combined events newest-first. The history page displays three separate categories:

- Command history
- Result history
- Message history

Every displayed value includes its event timestamp and source.

When a real remote machine boot is detected, any meaningful pre-existing current status is archived only if it is not already represented by an event, then the current command/result/message are cleared before the new online status is published. This prevents a previous boot's final status from remaining as the new boot's current status while avoiding duplicate history entries.

## 10. Commands and flags

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

### Shared shutdown/reboot scripts

The scripts are located in the same directory that contains `homelab-panel/` and `homelab-control/`:

```bash
./shutdown_delay.sh
./shutdown_cancel.sh
./reboot_delay.sh
./reboot_cancel.sh
```

Both the panel and remote command listener derive this directory from their own file location. No absolute script-path setting is required.

### Observe MQTT

```bash
mosquitto_sub -h YOUR_BROKER -t 'aoostar/#' -v
mosquitto_sub -h YOUR_BROKER -t 'homelab-panel/#' -v
```

## 11. Flask routes

| Method | Route | Purpose |
| --- | --- | --- |
| `GET`, `POST` | `/login` | Public login page when web authentication is enabled. |
| `POST` | `/logout` | Clear the authenticated browser session. |
| `GET` | `/` | Main control/status page. |
| `GET` | `/history/<device_id>` | Per-device history page. |
| `POST` | `/wol/<device_id>` | Send configured Wake-on-LAN. |
| `POST` | `/mqtt/<device_id>/<button_id>` | Execute a configured remote MQTT control. |
| `POST` | `/local/<button_id>` | Execute a configured local helper script. |

When `WEB_AUTH_CONFIG["enabled"]` is `True`, all routes except `/login` (and Flask's static endpoint, if used) require an authenticated session. When web login is disabled and `PANEL_TOKEN` is non-empty, include `?token=...`; generated panel/history links preserve the token.

## 12. Status logic

Ping and MQTT are evaluated and displayed independently. A working ping is therefore visible even when MQTT is not configured, the broker is disconnected, or no MQTT device-status message has been received yet.

The status card uses three combined states:

- **Online** (green) only when the configured IP responds to ping **and** Homelab Panel is currently connected to the MQTT broker **and** the device's fresh `power_topic` value is `online`.
- **Ikke fuldt online** (yellow) when exactly one side is currently online, for example ping works but MQTT is unavailable, or MQTT says online while ping does not answer.
- **Offline** (red) when neither ping nor a valid current MQTT-online signal is available.

For MQTT to count as online, all of these must be true at the same time:

1. a non-empty `power_topic` is configured for the device;
2. Homelab Panel's MQTT client is currently connected to the broker;
3. the received power payload is `online`;
4. the local receipt age is within `MQTT_ONLINE_TTL_SECONDS`.

A previously received/cached `online` payload does not keep the device Online after the panel loses its broker connection. The MQTT line explicitly distinguishes not configured, broker disconnected, connected without device status, stale status, and fresh status.

Homelab Panel starts the MQTT client asynchronously. If the broker is unavailable when the panel starts, the web interface and ping checks still work immediately while Paho keeps retrying the broker connection in the background. A panel restart is therefore not required merely because MQTT was unavailable at startup.

The remote status service uses an MQTT last-will of `offline` and republishes `online` with its uptime heartbeat.

## 13. Runtime files

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

## 14. systemd installation

Included units:

- `homelab-control/homelab-control-command-listener.service`
- `homelab-control/homelab-control-status-indicator.service`
- `homelab-panel/homelab-controll.service`

Review and edit host-specific paths, users, and groups before installing. Keep `homelab-panel/`, `homelab-control/`, and the shared root action scripts under the same parent directory; the Python services derive action-script paths from that layout.

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

## 15. Security and safety notes

- Restrict Flask to trusted networks or a properly secured reverse proxy.
- Use MQTT authentication and ACLs.
- Permit publishing to the panel control topic only from trusted clients.
- Never expose the development Flask server or unauthenticated MQTT broker directly to the Internet.
- Keep panel control messages non-retained.
- Keep `MQTT_CONFIG["retain"] = False` for destructive device-control payloads unless you fully understand the replay implications.
- If web login is enabled, replace both the example web password and `WEB_AUTH_CONFIG["secret_key"]` before startup.
- Set `session_cookie_secure=True` only behind HTTPS; use HTTPS whenever the panel is exposed beyond a trusted LAN.
- Username/password login is simple session authentication and has no built-in rate limiting.
- Treat legacy `PANEL_TOKEN` only as a basic URL gate, not username/password authentication.
- Review all root/sudo privileges and scripts.
- Test shutdown, reboot, cancellation, history rollover, and Wake-on-LAN outside production first.

## 16. Project documentation

- `README.md` — current usage/configuration/behavior only.
- `commented_code_map.md` — every current function, route, script, service, command interface, and its purpose.
- `VERSIONING.md` — release history and version policy.
- `VERSION` — current release number.
- `.gitignore` — keeps machine-specific active configuration files out of Git while preserving the three example configuration files.

## 17. Adding a device

1. Add the device to `REMOTE_DEVICES`.
2. Configure Wake-on-LAN if needed.
3. Configure status topics.
4. Configure `history_topic` explicitly when desired; if omitted, the panel can derive `/history` from a standard `.../last_message` topic.
5. Configure `mqtt_controls` if shutdown/reboot control is required.
6. Install/configure the remote agent on that machine when status/control/history is needed.
7. Keep local active configuration files updated on installed systems, and update the tracked example files whenever available configuration options change. Active `config.py`, `devices.py`, and `config.json` are intentionally ignored and excluded from release ZIPs.
