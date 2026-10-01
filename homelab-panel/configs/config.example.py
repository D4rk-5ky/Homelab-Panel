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
    # Paho-publisherens QoS for remote kommandoer: 0, 1 eller 2.
    "qos": 0,
    # Kommandoer må ikke være retained, så de ikke genafspilles efter reconnect.
    "retain": False,
    "client_id_panel_status": "homelab-panel-status",
    "panel_control_topic": "homelab-panel/control",
}

# ============================================================
# VALGFRI HOME ASSISTANT MQTT DISCOVERY
# ============================================================
# Når enabled=True opretter Homelab Panel automatisk MQTT Discovery entities
# for hver REMOTE_DEVICES-enhed, alle mqtt_controls.buttons og LOCAL_SERVER.buttons.
# WoL-knapper bruger samme label som websiden. Genstart panelet efter ændringer
# i configs/devices.py; Home Assistant-knapperne oprettes uden manuel YAML.
# Ingen Home Assistant-konfiguration er nødvendig ud over en fungerende MQTT
# integration der bruger samme broker.
HOME_ASSISTANT_CONFIG = {
    "enabled": False,
    "discovery_prefix": "homeassistant",
    "state_prefix": "homelab-panel/ha",
    "availability_topic": "homelab-panel/availability",
    # Home Assistants birth-topic/payload. En live online-besked genudsender discovery.
    # En retained online-besked, som broker replay'er ved subscribe, ignoreres fordi
    # panelet allerede har sendt et snapshot i MQTT connect-callbacken.
    # Brug tom status_topic for at deaktivere denne genudsendelse.
    "status_topic": "homeassistant/status",
    "status_online_payload": "online",
    "qos": 1,
    # Retain gælder discovery-konfiguration. HA-knapkommandoer er aldrig retained.
    "retain": True,
}

# ============================================================
# VALGFRI WEB-LOGIN
# ============================================================
# enabled=False: ingen username/password-login.
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

# Hvor længe MQTT online-status må være gammel før den ikke længere tæller som frisk.
MQTT_ONLINE_TTL_SECONDS = 90

# Hvor ofte baggrundsmonitoren pinger enheder, registrerer state transitions,
# opdaterer status-cache og publicerer Home Assistant state.
# WoL/power-confirmation kører i deres egne baggrundstråde.
STATUS_MONITOR_INTERVAL_SECONDS = 10

# Auto refresh i browseren.
PAGE_REFRESH_SECONDS = 15

# Maksimalt antal panel-oprettede event/historikposter pr. remote enhed.
PANEL_HISTORY_MAX_ENTRIES = 500

# Maksimalt antal panel-jobs der bevares pr. enhed i runtime state/historik.
PANEL_JOB_MAX_ENTRIES = 100
