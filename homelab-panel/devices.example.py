#!/usr/bin/env python3

# ============================================================
# REMOTE ENHEDER
# ============================================================
# Alle entries i mqtt_controls.buttons bliver automatisk:
#   1. vist som knap i Homelab Panel,
#   2. accepteret som allow-listet panel-command,
#   3. oprettet som Home Assistant MQTT Discovery button når HA er enabled.
# Payload skal samtidig findes i homelab-control/config.json -> commands på den
# remote enhed. Arbitrære shell-kommandoer accepteres aldrig fra MQTT.

REMOTE_DEVICES = {
    "aoostar_wtr": {
        "title": "Aoostar WTR",
        # unknown = ingen fejlmarkering før panelet har lært en forventet state.
        # Panel actions opdaterer automatisk forventet state for power/reboot.
        "expected_state_default": "unknown",

        "wol": {
            "enabled": True,
            "label": "Tænd Aoostar WTR",
            "mac": "AA:BB:CC:DD:EE:FF",
            "ip": "10.0.0.53",
            "confirm": "Er du sikker på at du vil tænde Aoostar WTR?",
            # Retry er valgfri. Når enabled=True fortsætter panelet indtil ping
            # svarer, max_attempts nås eller brugeren trykker Annuller WoL.
            "retry": {
                "enabled": True,
                "interval_seconds": 15,
                "max_attempts": 20,
                "wait_for_mqtt_seconds": 120
            }
        },

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
        },

        "confirmation": {
            "shutdown_timeout_seconds": 180,
            "reboot_timeout_seconds": 300
        },

        "mqtt_controls": {
            "title": "Aoostar WTR kontrol",
            "topic": "aoostar/control/power",
            # True sender JSON med command+job_id. 0.0.9 Homelab Control kan
            # dermed rapportere resultater på præcis samme job i panelet.
            # False/udeladt beholder legacy plain-text payloads.
            "json_jobs": True,
            "buttons": [
                {
                    "id": "shutdown_delay",
                    "label": "Sluk om 1 minut",
                    "payload": "shutdown_delay",
                    "category": "power",
                    "confirmation": "shutdown",
                    "color": "warn",
                    "icon": "⚠️",
                    "confirm": "Er du sikker på at du vil slukke Aoostar WTR om 1 minut?"
                },
                {
                    "id": "shutdown_cancel",
                    "label": "Annullér slukning",
                    "payload": "shutdown_cancel",
                    "category": "power",
                    "confirmation": "none",
                    "color": "danger",
                    "icon": "⛔",
                    "confirm": ""
                },
                {
                    "id": "reboot_delay",
                    "label": "Genstart om 1 minut",
                    "payload": "reboot_delay",
                    "category": "power",
                    "confirmation": "reboot",
                    "color": "warn",
                    "icon": "🔄",
                    "confirm": "Er du sikker på at du vil genstarte Aoostar WTR om 1 minut?"
                },
                {
                    "id": "reboot_cancel",
                    "label": "Annullér genstart",
                    "payload": "reboot_cancel",
                    "category": "power",
                    "confirmation": "none",
                    "color": "danger",
                    "icon": "⛔",
                    "confirm": ""
                },
                # Eksempel på et generisk allow-listet job. Opret tilsvarende
                # run_watchtower command i remote homelab-control/config.json.
                {
                    "id": "run_watchtower",
                    "label": "Kør Watchtower",
                    "payload": "run_watchtower",
                    "category": "maintenance",
                    "confirmation": "none",
                    "color": "ok",
                    "icon": "🐳",
                    "confirm": "Kør Watchtower på Aoostar WTR?"
                },
            ],
        },
    },

    "nas": {
        "title": "NAS",
        "expected_state_default": "unknown",
        "wol": {
            "enabled": True,
            "label": "Tænd NAS",
            "mac": "11:22:33:44:55:66",
            "ip": "10.0.0.20",
            "confirm": "Er du sikker på at du vil tænde NAS?",
            "retry": {"enabled": False, "interval_seconds": 15, "max_attempts": 20, "wait_for_mqtt_seconds": 120}
        },
        "status": {
            "power_topic": "",
            "action_topic": "",
            "hostname_topic": "",
            "uptime_topic": "",
            "last_command_topic": "",
            "last_result_topic": "",
            "last_message_topic": "",
            "last_updated_topic": "",
            "history_topic": "",
            "jobs_topic": "",
            "boot_id_topic": "",
            "boot_time_topic": "",
        },
        "mqtt_controls": None,
    },

    "proxmox_node": {
        "title": "Proxmox-node",
        "expected_state_default": "unknown",
        "wol": {
            "enabled": True,
            "label": "Tænd Proxmox-node",
            "mac": "77:88:99:AA:BB:CC",
            "ip": "10.0.0.30",
            "confirm": "Er du sikker på at du vil tænde Proxmox-node?",
            "retry": {"enabled": False, "interval_seconds": 15, "max_attempts": 20, "wait_for_mqtt_seconds": 120}
        },
        "status": {
            "power_topic": "",
            "action_topic": "",
            "hostname_topic": "",
            "uptime_topic": "",
            "last_command_topic": "",
            "last_result_topic": "",
            "last_message_topic": "",
            "last_updated_topic": "",
            "history_topic": "",
            "jobs_topic": "",
            "boot_id_topic": "",
            "boot_time_topic": "",
        },
        "mqtt_controls": None,
    },
}

# ============================================================
# LOKAL KONTROL FOR HOMELAB-SERVEREN
# ============================================================

LOCAL_SERVER = {
    "title": "Lokal enhedskontrol",
    "buttons": [
        {
            "id": "shutdown_delay",
            "label": "Sluk om 1 minut",
            "script": "shutdown_delay.sh",
            "color": "warn",
            "icon": "⚠️",
            "confirm": "Er du sikker på at du vil slukke denne homelab-server om 1 minut?"
        },
        {
            "id": "shutdown_cancel",
            "label": "Annullér slukning",
            "script": "shutdown_cancel.sh",
            "color": "danger",
            "icon": "⛔",
            "confirm": ""
        },
        {
            "id": "reboot_delay",
            "label": "Genstart om 1 minut",
            "script": "reboot_delay.sh",
            "color": "warn",
            "icon": "🔄",
            "confirm": "Er du sikker på at du vil genstarte denne homelab-server om 1 minut?"
        },
        {
            "id": "reboot_cancel",
            "label": "Annullér genstart",
            "script": "reboot_cancel.sh",
            "color": "danger",
            "icon": "⛔",
            "confirm": ""
        },
    ],
}
