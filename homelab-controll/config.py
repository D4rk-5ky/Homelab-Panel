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
}

PANEL_TOKEN = ""

LOCAL_SCRIPT_PATH = "Your Scripts for reboot and shutdown Path"

# Hvor længe MQTT online-status må være gammel før den ikke længere tæller som frisk
MQTT_ONLINE_TTL_SECONDS = 90

# Auto refresh i browseren
PAGE_REFRESH_SECONDS = 15
