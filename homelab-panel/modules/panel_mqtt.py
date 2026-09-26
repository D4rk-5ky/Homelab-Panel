#!/usr/bin/env python3
"""Long-running MQTT runtime for the Homelab Panel web application."""

import threading
import time
from datetime import datetime

import paho.mqtt.client as mqtt


class PanelMqttRuntime:
    """Own broker state, subscriptions, callbacks, diagnostics and listener client."""

    def __init__(
        self,
        *,
        mqtt_config,
        ha_config,
        remote_devices,
        publish_message,
        home_assistant_enabled,
        publish_home_assistant_snapshot,
        record_device_event,
        process_panel_control_message,
        handle_device_power_transition,
        process_remote_jobs_message,
        handle_boot_id_message,
        start_status_monitor,
        topic_helpers,
        connected_changed=None,
    ):
        self._mqtt_config = mqtt_config
        self._ha_config = ha_config
        self._remote_devices = remote_devices
        self._publish_message = publish_message
        self._home_assistant_enabled = home_assistant_enabled
        self._publish_home_assistant_snapshot = publish_home_assistant_snapshot
        self._record_device_event = record_device_event
        self._process_panel_control_message = process_panel_control_message
        self._handle_device_power_transition = handle_device_power_transition
        self._process_remote_jobs_message = process_remote_jobs_message
        self._handle_boot_id_message = handle_boot_id_message
        self._start_status_monitor = start_status_monitor
        self._topic_helpers = topic_helpers
        self._connected_changed = connected_changed
        self.state = {}
        self.state_lock = threading.Lock()
        self.subscriptions = set()
        self.connection_info = {"connected_at": "", "disconnected_at": "", "disconnect_reason": ""}
        self.connected = False
        self.client = None

    def publish_command(self, topic: str, payload: str) -> tuple[bool, str]:
        """Publish a command using the disposable shared publisher, never reconnect queueing."""
        cfg = self._mqtt_config()
        return self._publish_message(cfg, topic, payload, qos=int(cfg["qos"]), retain=bool(cfg["retain"]))

    def set_state(self, topic: str, payload: str, retain: bool = False, qos: int = 0) -> str | None:
        """Cache the latest received MQTT value and return the previous payload."""
        with self.state_lock:
            previous = self.state.get(topic)
            self.state[topic] = {
                "payload": payload,
                "timestamp": time.time(),
                "received_at": datetime.now().isoformat(timespec="seconds"),
                "retain": bool(retain),
                "qos": int(qos),
            }
        return None if not previous else str(previous.get("payload", ""))

    def set_connected(self, value: bool, reason: str = "") -> None:
        """Update broker connectivity timestamps and notify the app mirror."""
        self.connected = bool(value)
        now = datetime.now().isoformat(timespec="seconds")
        if value:
            self.connection_info["connected_at"] = now
            self.connection_info["disconnect_reason"] = ""
        else:
            self.connection_info["disconnected_at"] = now
            self.connection_info["disconnect_reason"] = reason
        if self._connected_changed:
            self._connected_changed(self.connected)

    def get_state(self, topic: str) -> dict | None:
        """Return the cached MQTT record for a topic."""
        if not topic:
            return None
        with self.state_lock:
            value = self.state.get(topic)
            return dict(value) if isinstance(value, dict) else None

    def get_payload_and_age(self, topic: str) -> tuple[str | None, int | None]:
        """Return cached payload plus age in seconds."""
        state = self.get_state(topic)
        if not state:
            return None, None
        return str(state["payload"]).strip(), int(time.time() - float(state["timestamp"]))

    def publish_direct(self, topic: str, payload: str, qos: int = 1, retain: bool = True) -> bool:
        """Publish telemetry/discovery through the connected long-running client."""
        if self.client is None or not self.connected or not topic:
            return False
        try:
            info = self.client.publish(topic, payload=payload, qos=qos, retain=retain)
            return getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) == mqtt.MQTT_ERR_SUCCESS
        except Exception as exc:
            print(f"MQTT direct publish failed for {topic}: {exc}", flush=True)
            return False

    def _related_topics(self, status_cfg: dict):
        helpers = self._topic_helpers
        return (
            ("hostname_topic", helpers["hostname"](status_cfg)),
            ("uptime_topic", helpers["uptime"](status_cfg)),
            ("history_topic", helpers["history"](status_cfg)),
            ("jobs_topic", helpers["jobs"](status_cfg)),
            ("boot_id_topic", helpers["boot_id"](status_cfg)),
            ("boot_time_topic", helpers["boot_time"](status_cfg)),
        )

    def build_diagnostics(self) -> dict:
        """Build the web diagnostics view from cached subscriptions and connection data."""
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
            status_cfg = device.get("status", {})
            expected = []
            for key in ("power_topic", "action_topic", "last_command_topic", "last_result_topic", "last_message_topic", "last_updated_topic"):
                topic = str(status_cfg.get(key, "")).strip()
                if topic:
                    expected.append((key, topic))
            for key, topic in self._related_topics(status_cfg):
                if topic:
                    expected.append((key, topic))
            rows = []
            for key, topic in expected:
                state = states.get(topic, {})
                age = max(0, int(now_epoch - float(state["timestamp"]))) if state.get("timestamp") else None
                rows.append({"key": key, "topic": topic, "seen": bool(state), "payload": state.get("payload", ""), "age": age})
            devices[device_id] = rows
        cfg = self._mqtt_config()
        return {
            "connected": self.connected,
            "client_id": str(cfg.get("client_id_panel_status", "")),
            "host": str(cfg.get("host", "")),
            "port": cfg.get("port", 1883),
            "control_topic": str(cfg.get("panel_control_topic", "")),
            "connection": dict(self.connection_info),
            "topics": topic_rows,
            "devices": devices,
        }

    def on_connect(self, *args):
        """Subscribe to configured status/control topics and republish HA snapshot."""
        client = args[0]
        had_previous_connection = bool(self.connection_info.get("connected_at"))
        self.set_connected(True)
        print("Homelab-panel MQTT connected", flush=True)
        topics = set()
        for device in self._remote_devices().values():
            status_cfg = device.get("status", {})
            for key in ("power_topic", "action_topic", "last_command_topic", "last_result_topic", "last_message_topic", "last_updated_topic"):
                topic = str(status_cfg.get(key, "")).strip()
                if topic:
                    topics.add(topic)
            for _, topic in self._related_topics(status_cfg):
                if topic:
                    topics.add(topic)
        panel_control_topic = str(self._mqtt_config().get("panel_control_topic", "")).strip()
        if panel_control_topic:
            topics.add(panel_control_topic)
        if self._home_assistant_enabled():
            status_topic = str(self._ha_config().get("status_topic", "homeassistant/status")).strip()
            if status_topic:
                topics.add(status_topic)
        self.subscriptions.clear()
        self.subscriptions.update(topics)
        for topic in sorted(topics):
            client.subscribe(topic, qos=1)
            print(f"Homelab-panel subscribed to {topic}", flush=True)
        self._publish_home_assistant_snapshot()
        event_type = "mqtt_reconnect" if had_previous_connection else "mqtt_connect"
        for device_id, device in self._remote_devices().items():
            if str(device.get("status", {}).get("power_topic", "")).strip():
                self._record_device_event(device_id, category="mqtt", event_type=event_type, result="success", message="Homelab Panel connected to MQTT broker", source="Homelab Panel")

    def on_disconnect(self, *args):
        """Record broker disconnect state and per-device history entries."""
        reason = str(args[3]) if len(args) >= 4 else (str(args[2]) if len(args) >= 3 else "")
        self.set_connected(False, reason)
        print(f"Homelab-panel MQTT disconnected: {reason}", flush=True)
        for device_id, device in self._remote_devices().items():
            if str(device.get("status", {}).get("power_topic", "")).strip():
                self._record_device_event(device_id, category="mqtt", event_type="mqtt_disconnect", result="failure", message=f"Homelab Panel disconnected from MQTT broker{': ' + reason if reason else ''}", source="Homelab Panel", severity="error")

    def on_message(self, client, userdata, msg):
        """Cache and dispatch incoming MQTT messages without executing retained controls."""
        payload = msg.payload.decode("utf-8", errors="replace").strip()
        panel_control_topic = str(self._mqtt_config().get("panel_control_topic", "")).strip()
        previous_payload = self.set_state(msg.topic, payload, retain=bool(getattr(msg, "retain", False)), qos=int(getattr(msg, "qos", 0)))
        if panel_control_topic and msg.topic == panel_control_topic:
            if getattr(msg, "retain", False):
                print("Homelab-panel control rejected: retained control messages are not executed", flush=True)
                return
            handler = self._process_panel_control_message()
            threading.Thread(target=handler, args=(payload,), daemon=True).start()
            return
        ha_cfg = self._ha_config()
        if self._home_assistant_enabled() and msg.topic == str(ha_cfg.get("status_topic", "homeassistant/status")).strip():
            if payload == str(ha_cfg.get("status_online_payload", "online")):
                self._publish_home_assistant_snapshot()
            return
        self._handle_device_power_transition(msg.topic, previous_payload, payload)
        self._process_remote_jobs_message(msg.topic, payload)
        self._handle_boot_id_message(msg.topic, payload)
        print(f"Homelab-panel MQTT message: {msg.topic} = {payload}", flush=True)

    def build_client(self):
        """Create the reconnecting Paho client with compatibility for callback API v1/v2."""
        cfg = self._mqtt_config()
        try:
            client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=cfg["client_id_panel_status"], protocol=mqtt.MQTTv311)
        except AttributeError:
            client = mqtt.Client(client_id=cfg["client_id_panel_status"], protocol=mqtt.MQTTv311)
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        if self._home_assistant_enabled():
            ha_cfg = self._ha_config()
            availability_topic = str(ha_cfg.get("availability_topic", "homelab-panel/availability")).strip()
            if availability_topic:
                client.will_set(availability_topic, payload="offline", qos=int(ha_cfg.get("qos", 1)), retain=True)
        return client

    def start(self) -> None:
        """Start the status monitor and reconnecting MQTT network loop."""
        self._start_status_monitor()
        client = self.build_client()
        cfg = self._mqtt_config()
        if cfg["user"]:
            client.username_pw_set(cfg["user"], cfg["pass"])
        client.on_connect = self.on_connect
        client.on_disconnect = self.on_disconnect
        client.on_message = self.on_message
        try:
            self.client = client
            client.connect_async(cfg["host"], cfg["port"], keepalive=60)
            client.loop_start()
            print("Homelab-panel MQTT listener started; broker connection runs in background", flush=True)
        except Exception as exc:
            print(f"MQTT listener kunne ikke starte: {exc}", flush=True)
