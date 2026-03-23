#!/usr/bin/env python3

# ============================================================
# REMOTE ENHEDER
# ============================================================

REMOTE_DEVICES = {
    "aoostar_wtr": {
        "title": "Aoostar WTR",

        "wol": {
            "enabled": True,
            "label": "Tænd Aoostar WTR",
            "mac": "AA:BB:CC:DD:EE:FF",
            "ip": "10.0.0.53",
            "confirm": "Er du sikker på at du vil tænde Aoostar WTR?"
        },

        "status": {
            "power_topic": "aoostar/status/power",
            "action_topic": "aoostar/status/action",
            "last_command_topic": "aoostar/status/last_command",
            "last_result_topic": "aoostar/status/last_result",
            "last_message_topic": "aoostar/status/last_message",
            "last_updated_topic": "aoostar/status/last_updated",
        },

        "mqtt_controls": {
            "title": "Aoostar WTR kontrol",
            "topic": "aoostar/control/power",
            "buttons": [
                {
                    "id": "shutdown_delay",
                    "label": "Sluk om 1 minut",
                    "payload": "shutdown_delay",
                    "color": "warn",
                    "icon": "⚠️",
                    "confirm": "Er du sikker på at du vil slukke Aoostar WTR om 1 minut?"
                },
                {
                    "id": "shutdown_cancel",
                    "label": "Annullér slukning",
                    "payload": "shutdown_cancel",
                    "color": "danger",
                    "icon": "⛔",
                    "confirm": ""
                },
                {
                    "id": "reboot_delay",
                    "label": "Genstart om 1 minut",
                    "payload": "reboot_delay",
                    "color": "warn",
                    "icon": "🔄",
                    "confirm": "Er du sikker på at du vil genstarte Aoostar WTR om 1 minut?"
                },
                {
                    "id": "reboot_cancel",
                    "label": "Annullér genstart",
                    "payload": "reboot_cancel",
                    "color": "danger",
                    "icon": "⛔",
                    "confirm": ""
                },
            ],
        },
    },

    "nas": {
        "title": "NAS",

        "wol": {
            "enabled": True,
            "label": "Tænd NAS",
            "mac": "11:22:33:44:55:66",
            "ip": "10.0.0.20",
            "confirm": "Er du sikker på at du vil tænde NAS?"
        },

        "status": {
            "power_topic": "",
            "action_topic": "",
            "last_command_topic": "",
            "last_result_topic": "",
            "last_message_topic": "",
            "last_updated_topic": "",
        },

        "mqtt_controls": None,
    },

    "proxmox_node": {
        "title": "Proxmox-node",

        "wol": {
            "enabled": True,
            "label": "Tænd Proxmox-node",
            "mac": "77:88:99:AA:BB:CC",
            "ip": "10.0.0.30",
            "confirm": "Er du sikker på at du vil tænde Proxmox-node?"
        },

        "status": {
            "power_topic": "",
            "action_topic": "",
            "last_command_topic": "",
            "last_result_topic": "",
            "last_message_topic": "",
            "last_updated_topic": "",
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
