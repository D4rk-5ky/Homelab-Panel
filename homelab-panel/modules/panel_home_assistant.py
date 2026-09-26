#!/usr/bin/env python3
"""Home Assistant MQTT discovery/state integration for Homelab Panel."""

import json


class HomeAssistantIntegration:
    """Publish HA discovery and state while keeping Flask/MQTT transport separate."""

    def __init__(
        self,
        *,
        config,
        mqtt_config,
        remote_devices,
        local_server,
        is_mqtt_connected,
        publish_direct,
        status_cache_snapshot,
        combined_device_jobs,
        wol_job_active,
    ):
        self._config = config
        self._mqtt_config = mqtt_config
        self._remote_devices = remote_devices
        self._local_server = local_server
        self._is_mqtt_connected = is_mqtt_connected
        self._publish_direct = publish_direct
        self._status_cache_snapshot = status_cache_snapshot
        self._combined_device_jobs = combined_device_jobs
        self._wol_job_active = wol_job_active

    def enabled(self) -> bool:
        """Return whether MQTT discovery/state integration is enabled."""
        return bool(self._config().get("enabled", False))

    def state_topic(self, device_id: str) -> str:
        """Build the retained JSON state topic for one remote device."""
        prefix = str(self._config().get("state_prefix", "homelab-panel/ha")).strip().rstrip("/")
        return f"{prefix}/{device_id}/state"

    @staticmethod
    def device_block(device_id: str, device: dict) -> dict:
        """Build the common Home Assistant device registry block."""
        return {
            "identifiers": [f"homelab_panel_{device_id}"],
            "name": str(device.get("title") or device_id),
            "manufacturer": "Homelab Panel",
            "model": "Homelab Control Device",
        }

    def publish_button(self, node_id: str, button_id: str, label: str, command_payload: dict, device: dict) -> None:
        """Publish one HA MQTT button backed by the panel control topic."""
        if not self.enabled() or not self._is_mqtt_connected():
            return
        control_topic = str(self._mqtt_config().get("panel_control_topic", "")).strip()
        if not control_topic or not button_id:
            return
        cfg = self._config()
        discovery_prefix = str(cfg.get("discovery_prefix", "homeassistant")).strip().rstrip("/")
        config = {
            "name": label,
            "unique_id": f"{node_id}_{button_id}",
            "command_topic": control_topic,
            "payload_press": json.dumps(command_payload, ensure_ascii=False, separators=(",", ":")),
            "retain": False,
            "availability_topic": str(cfg.get("availability_topic", "homelab-panel/availability")).strip(),
            "device": device,
        }
        topic = f"{discovery_prefix}/button/{node_id}/{button_id}/config"
        self._publish_direct(topic, json.dumps(config, ensure_ascii=False, separators=(",", ":")), qos=int(cfg.get("qos", 1)), retain=bool(cfg.get("retain", True)))

    def publish_discovery(self) -> None:
        """Publish all remote sensors/buttons and configured local buttons."""
        if not self.enabled() or not self._is_mqtt_connected():
            return
        cfg = self._config()
        discovery_prefix = str(cfg.get("discovery_prefix", "homeassistant")).strip().rstrip("/")
        availability_topic = str(cfg.get("availability_topic", "homelab-panel/availability")).strip()
        qos = int(cfg.get("qos", 1))
        retain = bool(cfg.get("retain", True))

        for device_id, device in self._remote_devices().items():
            state_topic = self.state_topic(device_id)
            dev = self.device_block(device_id, device)
            base = {
                "state_topic": state_topic,
                "availability_topic": availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": dev,
            }
            entities = [
                ("binary_sensor", "online", {**base, "name": "Online", "unique_id": f"homelab_panel_{device_id}_online", "value_template": "{{ 'ON' if value_json.online else 'OFF' }}", "payload_on": "ON", "payload_off": "OFF", "device_class": "connectivity"}),
                ("binary_sensor", "ping", {**base, "name": "Ping", "unique_id": f"homelab_panel_{device_id}_ping", "value_template": "{{ 'ON' if value_json.ping else 'OFF' }}", "payload_on": "ON", "payload_off": "OFF", "device_class": "connectivity"}),
                ("sensor", "uptime", {**base, "name": "Uptime", "unique_id": f"homelab_panel_{device_id}_uptime", "value_template": "{{ value_json.uptime | int(0) }}", "unit_of_measurement": "s", "device_class": "duration"}),
                ("sensor", "last_command", {**base, "name": "Last command", "unique_id": f"homelab_panel_{device_id}_last_command", "value_template": "{{ value_json.last_command }}"}),
                ("sensor", "job_status", {**base, "name": "Job status", "unique_id": f"homelab_panel_{device_id}_job_status", "value_template": "{{ value_json.job_status }}"}),
            ]
            for component, object_id, entity_config in entities:
                topic = f"{discovery_prefix}/{component}/homelab_panel_{device_id}/{object_id}/config"
                self._publish_direct(topic, json.dumps(entity_config, ensure_ascii=False, separators=(",", ":")), qos=qos, retain=retain)

            node_id = f"homelab_panel_{device_id}"
            wol_cfg = device.get("wol", {})
            if wol_cfg.get("enabled"):
                self.publish_button(node_id, "wake", str(wol_cfg.get("label") or "Wake"), {"device_id": device_id, "command": "power_on"}, dev)
                self.publish_button(node_id, "cancel_wol", "Annullér Wake-on-LAN", {"device_id": device_id, "command": "cancel_wol"}, dev)
            for button in (device.get("mqtt_controls") or {}).get("buttons", []):
                command_id = str(button.get("id", "")).strip()
                self.publish_button(node_id, command_id, str(button.get("label") or command_id), {"device_id": device_id, "command": command_id}, dev)

        local = self._local_server()
        local_device = {
            "identifiers": ["homelab_local_panel"],
            "name": str(local.get("name") or local.get("title") or "Homelab Panel"),
            "manufacturer": "Homelab Panel",
            "model": "Local Panel Controls",
        }
        for button in local.get("buttons", []):
            command_id = str(button.get("id", "")).strip()
            self.publish_button("homelab_local_panel", command_id, str(button.get("label") or command_id), {"target": "local", "command": command_id}, local_device)

    def publish_snapshot(self) -> None:
        """Republish HA availability/discovery and the current cached states."""
        if not self.enabled() or not self._is_mqtt_connected():
            return
        cfg = self._config()
        availability_topic = str(cfg.get("availability_topic", "homelab-panel/availability")).strip()
        self._publish_direct(availability_topic, "online", qos=int(cfg.get("qos", 1)), retain=True)
        self.publish_discovery()
        statuses = self._status_cache_snapshot()
        for device_id, device in self._remote_devices().items():
            if device_id in statuses:
                self.publish_state(device_id, device, statuses[device_id])

    def publish_state(self, device_id: str, device: dict, status: dict) -> None:
        """Publish one retained HA state JSON payload for a remote device."""
        if not self.enabled():
            return
        jobs = self._combined_device_jobs(device_id, device)
        latest_job = jobs[0] if jobs else {}
        payload = {
            "online": status.get("overall") == "online",
            "overall": status.get("overall", "offline"),
            "ping": bool(status.get("ping_ok")),
            "mqtt_online": bool(status.get("mqtt_online_ok")),
            "hostname": status.get("hostname", ""),
            "uptime": status.get("uptime_seconds", 0),
            "last_command": status.get("last_command", "Ingen"),
            "last_result": status.get("last_result", "Ingen"),
            "last_message": status.get("last_message", ""),
            "expected_state": status.get("expected_state", "unknown"),
            "job_status": str(latest_job.get("status") or "idle"),
            "job_command": str(latest_job.get("command") or ""),
            "wol_active": self._wol_job_active(device_id),
        }
        cfg = self._config()
        self._publish_direct(self.state_topic(device_id), json.dumps(payload, ensure_ascii=False, separators=(",", ":")), qos=int(cfg.get("qos", 1)), retain=True)
