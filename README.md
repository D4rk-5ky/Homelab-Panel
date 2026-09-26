# Homelab Panel

Homelab Panel er et hobbyprojekt til at overvåge og styre homelab-enheder fra ét Flask-webpanel og via MQTT.

Projektet består af:

- `homelab-panel/` — webpanel, ping/MQTT-status, Home Assistant MQTT Discovery, eventhistorik, jobs, WoL og MQTT-styring.
- `homelab-control/` — valgfri remote agent der modtager allow-listede MQTT-kommandoer, kører scripts og publicerer status/jobs/historik.
- `scripts/` — kun de fælles Homelab Panel power-scripts (shutdown/reboot og deres fælleshjælper), som både panel og remote agent kan bruge.

Der er **ingen CLI flags** i den nuværende app. Konfiguration sker i `config.py`, `devices.py` og remote `config.json`. Webhandlinger sker gennem Flask-routes, og remote handlinger gennem MQTT.

---

## Projektstruktur

```text
Homelab-Panel/
├── README.md
├── VERSION
├── VERSIONING.md
├── commented_code_map.md
├── scripts/
│   ├── homelab_action_common.sh
│   ├── shutdown_delay.sh
│   ├── shutdown_cancel.sh
│   ├── reboot_delay.sh
│   └── reboot_cancel.sh
├── homelab-panel/
│   ├── app.py
│   ├── config.example.py
│   ├── devices.example.py
│   ├── homelab-controll.service
│   └── templates/
│       ├── index.html
│       ├── history.html
│       ├── login.html
│       └── mqtt_diagnostics.html
└── homelab-control/
    ├── config.example.json
    ├── homelab_control_command_listener.py
    ├── homelab_control_status_indicator.py
    ├── homelab_control_lib.sh
    ├── homelab-control-command-listener.service
    └── homelab-control-status-indicator.service
```

Runtime state/logs bliver oprettet lokalt og er ignoreret af Git:

```text
homelab-panel/state/
homelab-control/state/
homelab-control/logs/
```

Aktive credentials/configs er også ignoreret og er ikke med i release ZIP.

---

# Installation

## Panel dependencies

På Debian/Ubuntu:

```bash
sudo apt update
sudo apt install python3 python3-flask python3-paho-mqtt mosquitto-clients wakeonlan iputils-ping
```

Projektet kræver desuden en MQTT broker, hvis MQTT-status/kontrol eller Home Assistant Discovery skal bruges.

## Opret aktive panel configs

Fra projektroden:

```bash
cp homelab-panel/config.example.py homelab-panel/config.py
cp homelab-panel/devices.example.py homelab-panel/devices.py
```

Redigér derefter begge lokale filer.

## Opret remote Homelab Control config

På hver remote host der skal bruge `homelab-control`:

```bash
cp homelab-control/config.example.json homelab-control/config.json
```

Tilpas broker, client IDs, topics og command allow-list.

---

# Start Homelab Panel manuelt

```bash
cd homelab-panel
python3 app.py
```

Standard Flask-adresse:

```text
http://HOST:5000/
```

Systemd-servicefilen er et eksempel med deployment-specifikke `User`, `Group`, `WorkingDirectory` og `ExecStart`. Tilpas disse til den faktiske placering før installation.

---

# `homelab-panel/config.py`

## `WOL_BROADCAST`

Broadcast-adressen der bruges af `wakeonlan`.

```python
WOL_BROADCAST = "255.255.255.255"
```

## `MQTT_CONFIG`

```python
MQTT_CONFIG = {
    "host": "192.168.1.10",
    "port": 1883,
    "user": "mqtt-user",
    "pass": "mqtt-password",
    "qos": 0,
    "retain": False,
    "client_id_panel_status": "homelab-panel-status",
    "panel_control_topic": "homelab-panel/control",
}
```

`panel_control_topic` er den fælles JSON-indgang til Homelab Panel.

Eksempel — Wake-on-LAN:

```json
{"device_id":"aoostar_wtr","command":"power_on"}
```

Eksempel — custom job:

```json
{"device_id":"aoostar_wtr","command":"run_watchtower"}
```

Control-messages på panel-control topic må **ikke** være retained. Panelet afviser retained control-messages for at undgå at en gammel shutdown/reboot bliver genudført ved reconnect.

## `WEB_AUTH_CONFIG`

Valgfri sessionbaseret web-login:

```python
WEB_AUTH_CONFIG = {
    "enabled": True,
    "username": "admin",
    "password": "CHANGE_ME",
    "secret_key": "CHANGE_ME_TO_A_LONG_RANDOM_VALUE",
    "session_cookie_secure": False,
}
```

Generér eksempelvis secret key med:

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

`session_cookie_secure=True` må kun bruges, når siden faktisk tilgås via HTTPS.

Når web-login er aktiveret, er kun login-siden offentlig. Alle øvrige sider og kontrolroutes kræver en gyldig session.

## `PANEL_TOKEN`

Legacy query-string token. Bruges kun når web-login er deaktiveret.

```python
PANEL_TOKEN = ""
```

## `MQTT_ONLINE_TTL_SECONDS`

Hvor gammel remote `power=online` må være, før den ikke længere tæller som frisk MQTT online-status.

```python
MQTT_ONLINE_TTL_SECONDS = 90
```

## `STATUS_MONITOR_INTERVAL_SECONDS`

Baggrundsmonitorens interval for ping, state-transition detection og Home Assistant state-publicering.

```python
STATUS_MONITOR_INTERVAL_SECONDS = 10
```

## `PAGE_REFRESH_SECONDS`

Browserens auto-refresh interval.

```python
PAGE_REFRESH_SECONDS = 15
```

## `PANEL_HISTORY_MAX_ENTRIES`

Maksimalt antal panel-eventposter pr. remote enhed.

```python
PANEL_HISTORY_MAX_ENTRIES = 500
```

## `PANEL_JOB_MAX_ENTRIES`

Maksimalt antal panel-jobs der bevares pr. enhed.

```python
PANEL_JOB_MAX_ENTRIES = 100
```

---

# Valgfri Home Assistant MQTT Discovery

Home Assistant integrationen er helt valgfri.

```python
HOME_ASSISTANT_CONFIG = {
    "enabled": False,
    "discovery_prefix": "homeassistant",
    "state_prefix": "homelab-panel/ha",
    "availability_topic": "homelab-panel/availability",
    "qos": 1,
    "retain": True,
}
```

Når `enabled=True`, publicerer panelet MQTT Discovery for hver remote enhed.

Standard entities omfatter:

- combined `online` binary sensor;
- `ping` binary sensor;
- `uptime` sensor;
- `last_command` sensor;
- `job_status` sensor;
- Wake button, hvis WoL er aktiveret;
- Cancel Wake-on-LAN button;
- **én Home Assistant button for hver entry i `mqtt_controls.buttons`.**

Det betyder, at en custom `run_watchtower`, `start_backup`, `syncerate` osv. automatisk bliver en Home Assistant button, når den står i `devices.py`.

Combined `online` er kun `ON`, når **ping og frisk MQTT `power=online` er sande samtidigt**.

Home Assistant command buttons publicerer JSON til `MQTT_CONFIG["panel_control_topic"]`. Script-resultater sendes ikke tilbage gennem dette control topic; de kommer på remote job-status topic.

---

# `homelab-panel/devices.py`

Hver remote enhed har typisk:

```python
"aoostar_wtr": {
    "title": "Aoostar WTR",
    "expected_state_default": "unknown",
    "wol": {...},
    "status": {...},
    "confirmation": {...},
    "mqtt_controls": {...},
}
```

## Ping og combined online-status

IP læses fra:

```python
"wol": {
    "ip": "192.168.1.200"
}
```

Ping beregnes uafhængigt af MQTT.

- ping online + MQTT mangler/offline = `Ikke fuldt online`;
- MQTT online + ping fejler = `Ikke fuldt online`;
- ping online + frisk MQTT online = `Online`;
- begge offline = `Offline`.

## Status topics

Aktuelle options:

```python
"status": {
    "power_topic": "aoostar/status/power",
    "action_topic": "aoostar/status/action",
    "hostname_topic": "aoostar/status/hostname",
    "uptime_topic": "aoostar/status/uptime",
    "last_command_topic": "aoostar/status/last_command",
    "last_result_topic": "aoostar/status/last_result",
    "last_message_topic": "aoostar/status/last_message",
    "last_updated_topic": "aoostar/status/last_updated",
    "history_topic": "aoostar/status/history",
    "jobs_topic": "aoostar/status/jobs",
    "boot_id_topic": "aoostar/status/boot_id",
    "boot_time_topic": "aoostar/status/boot_time",
}
```

Hvis `hostname_topic`, `uptime_topic`, `history_topic`, `jobs_topic`, `boot_id_topic` eller `boot_time_topic` mangler, kan panelet udlede dem fra et `.../last_message` topic. Eksempelfilen bruger eksplicitte topics for tydelighed.

---

# Dynamiske custom commands

Alle entries i:

```python
device["mqtt_controls"]["buttons"]
```

bliver automatisk webknapper.

Når Home Assistant integration er aktiveret, bliver de samme entries automatisk HA MQTT buttons.

Eksempel:

```python
{
    "id": "run_watchtower",
    "label": "Kør Watchtower",
    "payload": "run_watchtower",
    "category": "maintenance",
    "confirmation": "none",
    "color": "ok",
    "icon": "🐳",
    "confirm": "Kør Watchtower?"
}
```

Remote agenten skal stadig eksplicit tillade payloaden i `homelab-control/config.json`:

```json
"run_watchtower": {
  "script": "run_watchtower.sh",
  "label": "Kør Watchtower",
  "category": "maintenance",
  "timeout": 3600
}
```

`run_watchtower.sh` er et eksempel på et **projekt-specifikt** job og bliver ikke flyttet til Homelab Panels `scripts/`-mappe af denne release. Projekt-specifikke scripts skal blive i den mappe/struktur, der hører til deres eget projekt eller integration. `scripts/` er reserveret til Homelab Panels fælles shutdown/reboot-hjælpere.

Det er med vilje en dobbelt allow-list:

1. `devices.py` bestemmer hvad panel/HA kan tilbyde;
2. remote `config.json -> commands` bestemmer hvad Homelab Control faktisk må køre.

MQTT-payload bruges aldrig som shell-kommando.

Path traversal/nested script paths som `../script.sh` afvises af remote command listeneren.

## `json_jobs`

Valgfri præcis job-korrelation:

```python
"mqtt_controls": {
    "topic": "aoostar/control/power",
    "json_jobs": True,
    "buttons": [...]
}
```

- `False`/udeladt: legacy plain-text payload sendes. Den aktuelle remote agent rapporterer stadig jobstatus, men genererer selv job-id.
- `True`: panelet sender `command`, `job_id` og `source` som JSON. Remote-agentens resultat kan dermed opdatere præcis samme panel-job.

Den aktuelle remote agent accepterer begge formater.

---

# Remote `homelab-control/config.json`

## MQTT

```json
"mqtt": {
  "host": "192.168.1.10",
  "port": 1883,
  "user": "",
  "pass": "",
  "keepalive": 30
}
```

## Client IDs

```json
"client_ids": {
  "status": "aoostar-wtr-status",
  "command_listener": "aoostar-wtr-command-listener"
}
```

Brug unikke client IDs pr. host.

## Topics

```json
"topics": {
  "control_power": "aoostar/control/power",
  "status_power": "aoostar/status/power",
  "status_action": "aoostar/status/action",
  "status_hostname": "aoostar/status/hostname",
  "status_uptime": "aoostar/status/uptime",
  "status_last_command": "aoostar/status/last_command",
  "status_last_result": "aoostar/status/last_result",
  "status_last_message": "aoostar/status/last_message",
  "status_last_updated": "aoostar/status/last_updated",
  "status_history": "aoostar/status/history",
  "status_jobs": "aoostar/status/jobs",
  "status_boot_id": "aoostar/status/boot_id",
  "status_boot_time": "aoostar/status/boot_time"
}
```

## Timing/jobs

```json
"timing": {
  "publish_uptime_every": 30,
  "history_max_entries": 500,
  "job_history_max_entries": 100,
  "max_parallel_jobs": 4
}
```

`max_parallel_jobs` begrænser hvor mange allow-listede scripts remote command listeneren må køre samtidigt.

## Commands

Legacy format virker stadig:

```json
"run_watchtower": "run_watchtower.sh"
```

Det anbefalede format er:

```json
"run_watchtower": {
  "script": "run_watchtower.sh",
  "label": "Kør Watchtower",
  "category": "maintenance",
  "timeout": 3600
}
```

Options:

- `script` — de fire indbyggede shutdown/reboot-filnavne resolves automatisk fra `PROJECT_ROOT/scripts/`; non-bundled custom jobs flyttes ikke af denne release og beholder deres eksisterende project-specific integration/placering.
- `label` — visningsnavn i jobdata;
- `category` — f.eks. `power`, `backup`, `maintenance`, `command`;
- `timeout` — maksimal script-runtime i sekunder.

---

# Job lifecycle

Remote Homelab Control publicerer retained job-snapshot til `status_jobs`.

Hvert job kan gå gennem:

```text
queued -> running -> success
                  -> failure
```

Jobdata indeholder bl.a.:

- job ID;
- command;
- label;
- category;
- source;
- queued time;
- start time;
- finish time;
- runtime seconds;
- result/status;
- return code;
- kort stdout/stderr message.

Flere jobs kan køre parallelt op til `max_parallel_jobs`.

Hvis command listeneren genstartes mens et job står queued/running/waiting/confirming, bliver det efterladte job markeret `failure` ved næste start i stedet for at stå aktivt for evigt.

Panelet viser jobs fra flere hosts samtidigt.

Et succesfuldt MQTT publish tæller kun som **sent/afsendt**. Et remote job er først `success`, når scriptet har returneret exit code 0.

Script-resultater publiceres på remote job-status topic — ikke tilbage på `homelab-panel/control`.

---

# Power completion confirmation

## Wake-on-LAN

WoL kan bruge valgfri retry:

```python
"retry": {
    "enabled": True,
    "interval_seconds": 15,
    "max_attempts": 20,
    "wait_for_mqtt_seconds": 120
}
```

Flow:

```text
WoL sent
-> wait for ping
-> retry WoL if configured
-> ping confirmed
-> wait for MQTT online
-> completed only when ping + MQTT are online
```

Hvis enheden ikke har `power_topic`, kan WoL kun bekræftes med ping.

Mens WoL retry er aktivt, vises **Annullér Wake-on-LAN** på enhedens statuskort. Knappen forsvinder igen, når jobbet afsluttes eller annulleres.

## Shutdown

For `shutdown_delay`/`shutdown`:

```text
command sent
-> remote script success/failure
-> wait until ping offline AND MQTT power=offline
-> shutdown confirmed
```

## Reboot

For `reboot_delay`/`reboot`:

```text
command sent
-> remote script success/failure
-> wait until ping offline AND MQTT power=offline
-> wait until ping online AND MQTT power=online
-> reboot confirmed
```

Timeouts kan sættes pr. device:

```python
"confirmation": {
    "shutdown_timeout_seconds": 180,
    "reboot_timeout_seconds": 300
}
```

Eksisterende configs uden `confirmation` genkender automatisk `shutdown_delay` og `reboot_delay`.

---

# Expected-state logic

Panelet opretholder en intern forventet state pr. device.

Eksempler:

- WoL -> `starting` -> `online` ved bekræftet start;
- shutdown requested -> `offline_pending` -> `offline` ved bekræftet shutdown;
- reboot -> `restarting` -> `online` ved bekræftet reboot;
- cancel shutdown/reboot -> `online`.

Dermed kan panelet skelne mellem:

```text
Offline (forventet)
Offline (starter)
Offline (genstarter)
Offline (uventet)
```

Runtime expected state gemmes i `homelab-panel/state/` og er ikke en tracked configfil.

---

# Eventhistorik

Historik er en permanent eventjournal, ikke kun det aktuelle device-kort.

Panelet kan gemme events som:

- command dispatch;
- queued/running/success/failure jobs;
- power actions;
- WoL attempts/result;
- boot detection;
- online/offline/partial transitions;
- hvor længe forrige availability state varede;
- MQTT connect/reconnect/disconnect;
- backup/maintenance/custom job events;
- errors.

Historiksiden har filtre baseret på kategori plus `Errors`.

Den beholder også de tre separate visninger:

- Kommando-historik;
- Resultat-historik;
- Besked-historik.

## Boot cleanup

`homelab-control` bruger Linux `boot_id`.

Ved en **rigtig ny boot**:

1. en eventuel sidste command status sikres i historikken;
2. current `last_command`, `last_result`, `last_message` clears;
3. action sættes til `idle`;
4. boot event gemmes;
5. ny online/current status publiceres.

Et almindeligt service restart under samme Linux boot udfører ikke boot cleanup.

---

# Offline/online transition history

Baggrundsmonitoren registrerer ændringer i combined state i stedet for at logge hvert refresh.

Eksempel:

```text
06:12 online
08:43 offline after 2h 31m
17:14 online after 8h 31m
```

Hvis en offline-state er forventet efter en bekræftet shutdown, markeres den ikke som en unexpected error.

---

# MQTT diagnostics

Websiden:

```text
/mqtt-diagnostics
```

viser:

- broker host/port;
- MQTT client ID;
- connected/disconnected state;
- seneste connect/disconnect tid;
- disconnect reason hvis tilgængelig;
- panel control topic;
- alle aktive subscriptions;
- seneste payload pr. topic;
- receive timestamp;
- payload age;
- retained flag;
- QoS;
- forventede topics pr. device;
- om hvert forventet topic nogensinde er set.

Siden er beskyttet af samme optional web-login/token som resten af panelet.

---

# Direkte MQTT til Homelab Control

Remote control topic accepterer fortsat legacy plain text:

```text
shutdown_delay
run_watchtower
```

Remote agenten accepterer desuden JSON job-envelope:

```json
{"command":"run_watchtower","job_id":"abc123","source":"Homelab Panel"}
```

Kun commands der findes i remote `config.json -> commands` køres.

---

# Standard power scripts

De fælles Homelab Panel power-scripts ligger samlet i projektrodens `scripts/`-mappe:

```text
scripts/
├── shutdown_delay.sh
├── shutdown_cancel.sh
├── reboot_delay.sh
├── reboot_cancel.sh
└── homelab_action_common.sh
```

`homelab-panel/app.py` resolver lokale power-knapper til `PROJECT_ROOT/scripts/<filnavn>`. Remote `homelab-control` special-resolver de fire indbyggede power-scriptnavne til samme mappe, så eksisterende command-configs fortsat kan bruge f.eks. `"script": "shutdown_delay.sh"`.

`homelab_action_common.sh` finder først sin egen `scripts/`-mappe, går ét niveau op til projektroden og finder derefter `homelab-control/homelab_control_lib.sh`. Derfor er sourcing uafhængig af current working directory.

Når power-scripts køres af remote Homelab Control som root, genbruger de `homelab_control_lib.sh` til command status/history/MQTT.

Når de køres lokalt fra webpanelet uden root, bruger fælleshjælperen `sudo shutdown`.

Sudo-policy skal derfor konfigureres sikkert af administratoren, hvis lokale power-buttons skal bruges uden interaktiv adgangskode.

---

# Security notes

- Brug MQTT username/password og broker ACLs.
- Brug aldrig retained messages på command topics.
- Aktiver web-login hvis panelet er tilgængeligt for andre end dig selv.
- Brug HTTPS/reverse proxy hvis credentials sendes over et ikke-betroet netværk.
- Custom scripts er allow-listede i remote config; arbitrary MQTT shell code udføres ikke.
- De indbyggede shutdown/reboot-scriptnavne resolves kun fra `PROJECT_ROOT/scripts/`; øvrige project-specific jobs flyttes ikke af denne release og forbliver separat allow-listede.
- Review alle scripts før de tillades i `commands`.
- Power confirmation reducerer falske success-resultater, men er ikke en erstatning for korrekt backup/HA/storage safety.

---

# ⚠️ Disclaimer / Liability

**Use this script at your own risk.**

The author takes **no responsibility or liability** for any data loss, service disruption, misconfiguration, service outage, missed backups, credential exposure, or other damage that may occur from using this script.

Before running it in production, you **must**:

- Read the entire source code
- Understand exactly what it does (and what it does *not* do)
- Review and adapt it to your own environment
- Test it carefully in a non‑production setup

By using this script, **you accept full responsibility** for its effects.

⚠️ AI-assisted / vibe-coded experimental software. Use at your own risk.

## Disclaimer

This project is AI-assisted / vibe-coded software created as a hobby project. It has not been professionally audited and may contain bugs, unsafe behavior, data-loss issues, security problems, or incorrect assumptions.

You are responsible for reviewing the code, testing it in a safe environment, making backups, and understanding what it does before using it on real data. The author is not responsible for damage, data loss, broken systems, security issues, or other problems caused by using this software.

---
