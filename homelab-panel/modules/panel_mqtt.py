#!/usr/bin/env python3
"""Panel-specific MQTT routing/cache/diagnostics on the shared MQTT transport."""

import threading
import time
from datetime import datetime

from shared_modules.mqtt import MqttClient


STATUS_TOPIC_KEYS = (
    "power_topic", "action_topic", "hostname_topic", "uptime_topic",
    "last_command_topic", "last_result_topic", "last_message_topic", "last_updated_topic",
    "history_topic", "jobs_topic", "boot_id_topic", "boot_time_topic",
)


class PanelMqttRuntime:
    """Own panel-specific MQTT state and dispatch; shared code owns transport mechanics."""

    def __init__(self, *, mqtt_config, ha_config, remote_devices, home_assistant_enabled,
                 publish_home_assistant_snapshot, record_device_event,
                 process_panel_control_message, handle_device_power_transition,
                 process_remote_jobs_message, handle_boot_id_message, start_status_monitor):
        self._mqtt_config, self._ha_config = mqtt_config, ha_config
        self._remote_devices = remote_devices
        self._home_assistant_enabled = home_assistant_enabled
        self._publish_home_assistant_snapshot = publish_home_assistant_snapshot
        self._record_device_event = record_device_event
        self._process_panel_control_message = process_panel_control_message
        self._handle_device_power_transition = handle_device_power_transition
        self._process_remote_jobs_message = process_remote_jobs_message
        self._handle_boot_id_message = handle_boot_id_message
        self._start_status_monitor = start_status_monitor
        self.state, self.state_lock, self.subscriptions = {}, threading.Lock(), set()
        self.connection_info = {"connected_at": "", "disconnected_at": "", "disconnect_reason": ""}
        self.connected, self.transport = False, None

    def set_state(self, topic: str, payload: str, retain: bool, qos: int) -> str | None:
        with self.state_lock:
            previous = self.state.get(topic)
            self.state[topic] = {"payload": payload, "timestamp": time.time(),
                                 "received_at": datetime.now().isoformat(timespec="seconds"),
                                 "retain": bool(retain), "qos": int(qos)}
        return None if not previous else str(previous.get("payload", ""))

    def set_connected(self, value: bool, reason: str = "") -> None:
        self.connected = bool(value)
        now = datetime.now().isoformat(timespec="seconds")
        if value:
            self.connection_info.update(connected_at=now, disconnect_reason="")
        else:
            self.connection_info.update(disconnected_at=now, disconnect_reason=reason)

    def get_state(self, topic: str) -> dict | None:
        if not topic:
            return None
        with self.state_lock:
            value = self.state.get(topic)
            return dict(value) if isinstance(value, dict) else None

    def get_payload_and_age(self, topic: str) -> tuple[str | None, int | None]:
        state = self.get_state(topic)
        return (None, None) if not state else (str(state["payload"]).strip(), int(time.time() - float(state["timestamp"])))

    def publish_direct(self, topic: str, payload: str, qos: int, retain: bool) -> bool:
        if self.transport is None or not self.connected:
            return False
        try:
            return self.transport.publish(topic, payload, qos=qos, retain=retain)
        except Exception as exc:
            print(f"MQTT direct publish failed for {topic}: {exc}", flush=True)
            return False

    def subscription_topics(self) -> list[tuple[str, int]]:
        topics = set()
        for device in self._remote_devices().values():
            status_cfg = device.get("status", {})
            for key in STATUS_TOPIC_KEYS:
                if topic := str(status_cfg.get(key, "")).strip():
                    topics.add(topic)
        if topic := str(self._mqtt_config().get("panel_control_topic", "")).strip():
            topics.add(topic)
        if self._home_assistant_enabled():
            if topic := str(self._ha_config()["status_topic"]).strip():
                topics.add(topic)
        self.subscriptions.clear()
        self.subscriptions.update(topics)
        return [(topic, 1) for topic in sorted(topics)]

    def build_diagnostics(self) -> dict:
        now_epoch = time.time()
        with self.state_lock:
            states = {topic: dict(value) for topic, value in self.state.items()}
        topic_rows = []
        for topic in sorted(self.subscriptions):
            state = states.get(topic, {})
            age = max(0, int(now_epoch - float(state["timestamp"]))) if state.get("timestamp") else None
            topic_rows.append({"topic": topic, "payload": state.get("payload", ""), "received_at": state.get("received_at", ""), "age": age, "retain": state.get("retain"), "qos": state.get("qos")})
        devices = {}
        for device_id, device in self._remote_devices().items():
            status_cfg, expected = device.get("status", {}), []
            for key in STATUS_TOPIC_KEYS:
                if topic := str(status_cfg.get(key, "")).strip():
                    expected.append((key, topic))
            rows = []
            for key, topic in expected:
                state = states.get(topic, {})
                age = max(0, int(now_epoch - float(state["timestamp"]))) if state.get("timestamp") else None
                rows.append({"key": key, "topic": topic, "seen": bool(state), "payload": state.get("payload", ""), "age": age})
            devices[device_id] = rows
        cfg = self._mqtt_config()
        return {"connected": self.connected, "client_id": str(cfg.get("client_id_panel_status", "")),
                "host": str(cfg.get("host", "")), "port": cfg.get("port", 1883),
                "control_topic": str(cfg.get("panel_control_topic", "")), "connection": dict(self.connection_info),
                "topics": topic_rows, "devices": devices}

    def _connected(self) -> None:
        had_previous_connection = bool(self.connection_info.get("connected_at"))
        self.set_connected(True)
        print("Homelab-panel MQTT connected", flush=True)
        for topic in sorted(self.subscriptions):
            print(f"Homelab-panel subscribed to {topic}", flush=True)
        self._publish_home_assistant_snapshot()
        event_type = "mqtt_reconnect" if had_previous_connection else "mqtt_connect"
        for device_id, device in self._remote_devices().items():
            if str(device.get("status", {}).get("power_topic", "")).strip():
                self._record_device_event(device_id, category="mqtt", event_type=event_type, result="success",
                                          message="Homelab Panel connected to MQTT broker", source="Homelab Panel")

    def _disconnected(self, reason: str = "") -> None:
        self.set_connected(False, reason)
        print(f"Homelab-panel MQTT disconnected: {reason}", flush=True)
        for device_id, device in self._remote_devices().items():
            if str(device.get("status", {}).get("power_topic", "")).strip():
                self._record_device_event(device_id, category="mqtt", event_type="mqtt_disconnect", result="failure",
                                          message=f"Homelab Panel disconnected from MQTT broker{': ' + reason if reason else ''}",
                                          source="Homelab Panel", severity="error")

    def _message(self, topic: str, payload: str, retain: bool, qos: int) -> None:
        panel_control_topic = str(self._mqtt_config().get("panel_control_topic", "")).strip()
        previous_payload = self.set_state(topic, payload, retain=retain, qos=qos)
        if panel_control_topic and topic == panel_control_topic:
            if retain:
                print("Homelab-panel control rejected: retained control messages are not executed", flush=True)
                return
            handler = self._process_panel_control_message()
            threading.Thread(target=handler, args=(payload,), daemon=True).start()
            return
        ha_cfg = self._ha_config()
        if self._home_assistant_enabled() and topic == str(ha_cfg["status_topic"]).strip():
            if payload == str(ha_cfg["status_online_payload"]):
                # The broker replays a retained HA status immediately after subscribe.
                # _connected() already published this connection's HA snapshot, so
                # replaying it here would cause a duplicate discovery refresh. A live
                # HA birth message (retain=False) still requests a fresh snapshot.
                if retain:
                    print("Homelab-panel HA status replay ignored: retained online payload", flush=True)
                else:
                    self._publish_home_assistant_snapshot()
            return
        self._handle_device_power_transition(topic, previous_payload, payload)
        self._process_remote_jobs_message(topic, payload)
        self._handle_boot_id_message(topic, payload)
        print(f"Homelab-panel MQTT message: {topic} = {payload}", flush=True)

    def _ensure_transport(self) -> MqttClient:
        if self.transport is not None:
            return self.transport
        cfg, will = self._mqtt_config(), None
        if self._home_assistant_enabled():
            ha_cfg = self._ha_config()
            if topic := str(ha_cfg["availability_topic"]).strip():
                will = {"topic": topic, "payload": "offline", "qos": int(ha_cfg["qos"]), "retain": True}
        self.transport = MqttClient(cfg, client_id=cfg["client_id_panel_status"], will=will,
                                    subscriptions=self.subscription_topics, on_connect=self._connected,
                                    on_disconnect=self._disconnected, on_message=self._message,
                                    reconnect_min=1, reconnect_max=30)
        return self.transport

    def start(self) -> None:
        self._start_status_monitor()
        try:
            self._ensure_transport().start(mode="async_thread")
            print("Homelab-panel MQTT listener started; broker connection runs in background", flush=True)
        except Exception as exc:
            print(f"MQTT listener kunne ikke starte: {exc}", flush=True)
