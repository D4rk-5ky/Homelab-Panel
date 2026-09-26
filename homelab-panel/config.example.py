#!/usr/bin/env python3

# ============================================================
# GENEREL KONFIGURATION
# ============================================================

WOL_BROADCAST = "255.255.255.255"

MQTT_CONFIG = {
    "host": "YOUR.IP.Or.HostName",
    "port": 1883,
    "user": "",
    "pass": "",
    "qos": 0,
    "retain": False,
    "client_id_panel_status": "homelab-panel-status",
    "panel_control_topic": "homelab-panel/control",
}

# ============================================================
# VALGFRI HOME ASSISTANT MQTT DISCOVERY
# ============================================================
# Når enabled=True opretter Homelab Panel automatisk MQTT Discovery entities
# for hver REMOTE_DEVICES-enhed og for hver knap i mqtt_controls.buttons.
# Ingen Home Assistant-konfiguration er nødvendig ud over en fungerende MQTT
# integration der bruger samme broker.
HOME_ASSISTANT_CONFIG = {
    "enabled": False,
    "discovery_prefix": "homeassistant",
    "state_prefix": "homelab-panel/ha",
    "availability_topic": "homelab-panel/availability",
    "qos": 1,
    "retain": True,
}

# ============================================================
# VALGFRI WEB-LOGIN
# ============================================================
# enabled=False: ingen username/password-login; PANEL_TOKEN nedenfor kan stadig bruges.
# enabled=True: alle web-sider og web-kontrolroutes kræver login-session.
# Skift altid password og secret_key før enabled sættes til True.
WEB_AUTH_CONFIG = {
    "enabled": False,
    "username": "admin",
    "password": "CHANGE_ME_TO_A_STRONG_PASSWORD",
    "secret_key": "CHANGE_ME_TO_A_LONG_RANDOM_FLASK_SECRET_KEY",
    # Sæt kun True når panelet tilgås via HTTPS. Ved almindelig HTTP skal den være False.
    "session_cookie_secure": False,
}

# Legacy query-string token. Bruges kun når WEB_AUTH_CONFIG["enabled"] er False.
# Eksempel: http://panel:5000/?token=DIN_TOKEN
PANEL_TOKEN = ""

# Hvor længe MQTT online-status må være gammel før den ikke længere tæller som frisk.
MQTT_ONLINE_TTL_SECONDS = 90

# Hvor ofte baggrundsmonitoren pinger enheder, registrerer state transitions,
# opdaterer job/WoL confirmation og publicerer Home Assistant state.
STATUS_MONITOR_INTERVAL_SECONDS = 10

# Auto refresh i browseren.
PAGE_REFRESH_SECONDS = 15

# Maksimalt antal panel-oprettede event/historikposter pr. remote enhed.
PANEL_HISTORY_MAX_ENTRIES = 500

# Maksimalt antal panel-jobs der bevares pr. enhed i runtime state/historik.
PANEL_JOB_MAX_ENTRIES = 100
