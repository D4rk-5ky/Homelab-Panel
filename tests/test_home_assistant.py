"""Offline panel/HA regression checks for the current configuration/protocol."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import paho.mqtt.client as mqtt


ROOT = Path(__file__).resolve().parents[1]


def load_panel():
    """Load the real Flask entry point with example configs and no background I/O."""
    modules = {}
    config_package = types.ModuleType("configs")
    config_package.__path__ = []
    modules["configs"] = config_package
    for name, filename in (("configs.config", "config.example.py"), ("configs.devices", "devices.example.py")):
        module = types.ModuleType(name)
        path = ROOT / "homelab-panel" / "configs" / filename
        exec(compile(path.read_text(), str(path), "exec"), module.__dict__)
        modules[name] = module
    path = ROOT / "homelab-panel/app.py"
    spec = importlib.util.spec_from_file_location("homelab_panel_test", path)
    panel = importlib.util.module_from_spec(spec)
    modules[spec.name] = panel
    with patch.dict(sys.modules, modules), patch("threading.Thread.start"), patch.object(mqtt, "Client"), contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(panel)
    return panel


class HomeAssistantTests(unittest.TestCase):
    """Exercise current discovery, dispatch, access control, and path guards."""

    def setUp(self):
        self.panel = load_panel()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for field, name in (("PANEL_HISTORY_FILE", "history.json"), ("PANEL_RUNTIME_FILE", "runtime.json"), ("PANEL_JOBS_FILE", "jobs.json")):
            setattr(self.panel, field, str(Path(self.temp.name) / name))
        self.panel.PANEL_STATE_DIR = self.temp.name
        self.panel.HOME_ASSISTANT_CONFIG["enabled"] = True
        self.panel.MQTT_RUNTIME.connected = True
        self.panel.app.config.update(TESTING=True, SECRET_KEY="offline-test-secret")
        self.client = self.panel.app.test_client()
        self.published = []

        def capture(topic, payload, qos=1, retain=True):
            self.published.append((topic, payload, qos, retain))
            return True

        self.panel.HOME_ASSISTANT._publish_direct = capture
        subprocess_mock = patch.object(self.panel.subprocess, "run", side_effect=AssertionError("Unexpected external command"))
        subprocess_mock.start()
        self.addCleanup(subprocess_mock.stop)

    def button_configs(self):
        return {topic: json.loads(payload) for topic, payload, _, _ in self.published if "/button/" in topic}

    def test_every_web_action_is_discovered_with_current_envelope(self):
        self.panel.HOME_ASSISTANT.publish_discovery()
        buttons = self.button_configs()
        self.assertEqual(len(buttons), 15)
        self.assertEqual(len({b["unique_id"] for b in buttons.values()}), 15)
        for device_id, device in self.panel.REMOTE_DEVICES.items():
            base = f"homeassistant/button/homelab_panel_{device_id}"
            if device.get("wol", {}).get("enabled"):
                wake = buttons[f"{base}/wake/config"]
                self.assertEqual(wake["name"], device["wol"]["label"])
                self.assertEqual(json.loads(wake["payload_press"]), {"target": "remote", "device_id": device_id, "command": "power_on"})
                self.assertEqual(json.loads(buttons[f"{base}/cancel_wol/config"]["payload_press"]), {"target": "remote", "device_id": device_id, "command": "cancel_wol"})
            for button in (device.get("mqtt_controls") or {}).get("buttons", []):
                config = buttons[f"{base}/{button['id']}/config"]
                self.assertEqual(config["name"], button["label"])
                self.assertEqual(json.loads(config["payload_press"]), {"target": "remote", "device_id": device_id, "command": button["id"]})
        for button in self.panel.LOCAL_SERVER["buttons"]:
            config = buttons[f"homeassistant/button/homelab_local_panel/{button['id']}/config"]
            self.assertEqual(config["device"]["name"], self.panel.LOCAL_SERVER["name"])
            self.assertEqual(json.loads(config["payload_press"]), {"target": "local", "command": button["id"]})
        self.assertTrue(all(not cfg["retain"] for cfg in buttons.values()))

    def test_custom_buttons_and_namespaces_dispatch_without_component_coupling(self):
        device = copy.deepcopy(self.panel.REMOTE_DEVICES["aoostar_wtr"])
        device["wol"]["enabled"] = False
        device["mqtt_controls"]["buttons"] = [{"id": "backup", "label": "Backup photos", "payload": "run_backup"}]
        self.panel.REMOTE_DEVICES = {"local": device}
        self.panel.LOCAL_SERVER["buttons"] = [{"id": "backup", "label": "Local backup", "script": "backup.sh"}]
        self.panel.HOME_ASSISTANT.publish_discovery()
        buttons = list(self.button_configs().values())
        self.assertEqual(len(buttons), 2)
        self.assertEqual(len({b["device"]["identifiers"][0] for b in buttons}), 2)
        with patch.object(self.panel, "execute_and_record_remote_action", return_value=(True, "sent")) as remote, \
             patch.object(self.panel.ACTION_MANAGER, "execute_local_action", return_value=(True, "done")) as local:
            for button in buttons:
                self.panel.process_panel_control_message(button["payload_press"])
        remote.assert_called_once_with("local", "backup", "MQTT homelab-panel/control")
        local.assert_called_once_with("backup")

    def test_discovery_respects_enabled_connection_and_control_topic(self):
        for enabled, connected in ((False, True), (True, False)):
            self.panel.HOME_ASSISTANT_CONFIG["enabled"] = enabled
            self.panel.MQTT_RUNTIME.connected = connected
            self.panel.HOME_ASSISTANT.publish_snapshot()
            self.assertEqual(self.published, [])
        self.panel.HOME_ASSISTANT_CONFIG["enabled"] = True
        self.panel.MQTT_RUNTIME.connected = True
        self.panel.MQTT_CONFIG["panel_control_topic"] = ""
        self.panel.HOME_ASSISTANT.publish_discovery()
        self.assertEqual(self.button_configs(), {})
        self.assertTrue(self.published)  # Sensors can still be discovered.

    def test_web_and_mqtt_local_buttons_use_same_allow_listed_script(self):
        scripts = Path(self.temp.name) / "scripts"
        scripts.mkdir()
        script = scripts / "shutdown_delay.sh"
        script.write_text("#!/bin/sh\nexit 0\n")
        script.chmod(0o755)
        self.panel.SCRIPTS_DIR = str(scripts)
        with patch.object(self.panel.ACTION_MANAGER, "_run_command", return_value=(True, "scheduled")) as run:
            self.assertEqual(self.client.post("/local/shutdown_delay").status_code, 302)
            run.assert_called_once_with([str(script)])
            run.reset_mock()
            self.panel.process_panel_control_message('{"target":"local","command":"shutdown_delay","script":"evil.sh"}')
            run.assert_called_once_with([str(script)])
            run.reset_mock()
            for payload in ('{"target":"local","command":"../shutdown_delay.sh"}', '{"target":"local","command":"unknown"}', '{"target":"local","device_id":"aoostar_wtr","command":"shutdown_delay"}', '{"command":"shutdown_delay"}', '{"target":"invalid","command":"shutdown_delay"}', '[]', 'invalid'):
                self.panel.process_panel_control_message(payload)
            run.assert_not_called()

    def test_web_login_is_the_only_web_access_gate(self):
        self.panel.WEB_AUTH_CONFIG["enabled"] = True
        with patch.object(self.panel.ACTION_MANAGER, "execute_local_action") as execute:
            response = self.client.post("/local/shutdown_delay?token=ignored")
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.location.endswith("/login"))
            execute.assert_not_called()

    def test_retained_panel_control_is_rejected(self):
        runtime_module = sys.modules[self.panel.MQTT_RUNTIME.__class__.__module__]
        for payload in ('{"target":"local","command":"shutdown_delay"}', '{"target":"remote","device_id":"aoostar_wtr","command":"shutdown_delay"}'):
            with patch.object(runtime_module.threading, "Thread") as thread:
                self.panel.MQTT_RUNTIME._message("homelab-panel/control", payload, True, 1)
                thread.assert_not_called()

    def test_live_panel_control_requires_explicit_target_and_dispatches_worker(self):
        runtime_module = sys.modules[self.panel.MQTT_RUNTIME.__class__.__module__]
        payload = '{"target":"remote","device_id":"aoostar_wtr","command":"run_watchtower"}'
        with patch.object(runtime_module.threading, "Thread") as thread:
            self.panel.MQTT_RUNTIME._message("homelab-panel/control", payload, False, 0)
            thread.assert_called_once_with(target=self.panel.process_panel_control_message, args=(payload,), daemon=True)
            thread.return_value.start.assert_called_once()
        with patch.object(self.panel, "execute_and_record_remote_action", return_value=(True, "sent")) as remote:
            self.panel.process_panel_control_message(payload)
            remote.assert_called_once_with("aoostar_wtr", "run_watchtower", "MQTT homelab-panel/control")
            self.panel.process_panel_control_message('{"device_id":"aoostar_wtr","command":"run_watchtower"}')
            self.assertEqual(remote.call_count, 1)

    def test_local_script_path_guards_are_preserved(self):
        folder = Path(self.temp.name) / "scripts"
        folder.mkdir()
        self.panel.SCRIPTS_DIR = str(folder)
        outside = Path(self.temp.name) / "outside.sh"
        outside.write_text("#!/bin/sh\nexit 0\n")
        outside.chmod(0o755)
        (folder / "escape.sh").symlink_to(outside)
        (folder / "not-executable.sh").write_text("#!/bin/sh\nexit 0\n")
        with patch.object(self.panel.ACTION_MANAGER, "_run_command") as run:
            for name in ("../shutdown_delay.sh", "/tmp/anything.sh", "escape.sh", "not-executable.sh", "missing.sh"):
                self.assertFalse(self.panel.ACTION_MANAGER.run_local_script(name)[0])
            run.assert_not_called()

    def test_home_assistant_birth_republishes_discovery_and_cached_state(self):
        self.panel.HOME_ASSISTANT_CONFIG["retain"] = False
        self.panel.DEVICE_STATUS_CACHE["aoostar_wtr"] = {"overall": "online", "ping_ok": True, "mqtt_online_ok": True}
        self.panel.MQTT_RUNTIME._message("homeassistant/status", "online", True, 1)
        self.assertEqual(len(self.button_configs()), 15)
        self.assertTrue(any(topic == "homelab-panel/availability" and payload == "online" for topic, payload, _, _ in self.published))
        self.assertTrue(any(topic == "homelab-panel/ha/aoostar_wtr/state" for topic, _, _, _ in self.published))
        self.assertTrue(all(not retain for topic, _, _, retain in self.published if topic.endswith("/config")))
        self.published.clear()
        self.panel.MQTT_RUNTIME._message("homeassistant/status", "offline", False, 0)
        self.assertEqual(self.published, [])

    def test_birth_topic_customization_and_disable_are_current_config(self):
        self.assertIn(("homeassistant/status", 1), self.panel.MQTT_RUNTIME.subscription_topics())
        self.panel.HOME_ASSISTANT_CONFIG.update(status_topic="ha/custom/status", status_online_payload="ready")
        topics = self.panel.MQTT_RUNTIME.subscription_topics()
        self.assertIn(("ha/custom/status", 1), topics)
        self.assertNotIn(("homeassistant/status", 1), topics)
        self.panel.MQTT_RUNTIME._message("ha/custom/status", "ready", False, 0)
        self.assertEqual(len(self.button_configs()), 15)
        self.panel.HOME_ASSISTANT_CONFIG["status_topic"] = ""
        self.assertNotIn(("ha/custom/status", 1), self.panel.MQTT_RUNTIME.subscription_topics())

    def test_confirmation_title_placeholder_resolves_and_is_js_safe(self):
        self.assertEqual(self.panel.resolve_confirmation_text("Sluk '$TITLE'?", "Zotac RI531"), "Sluk 'Zotac RI531'?")
        device = self.panel.REMOTE_DEVICES["aoostar_wtr"]
        device["title"] = "O'Brien Node"
        device["wol"]["confirm"] = "Tænd '$TITLE'?"
        device["mqtt_controls"]["buttons"][0]["confirm"] = "Sluk '$TITLE'?"
        with patch.object(self.panel, "ping_host", return_value=False):
            html = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("$TITLE", html)
        self.assertIn("O\\u0027Brien Node", html)

    def test_webpages_render(self):
        with patch.object(self.panel, "ping_host", return_value=False):
            for url in ("/", "/history/aoostar_wtr", "/mqtt-diagnostics"):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.panel.WEB_AUTH_CONFIG["enabled"] = True
        self.assertEqual(self.client.get("/login").status_code, 200)


if __name__ == "__main__":
    unittest.main()
