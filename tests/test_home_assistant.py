"""Offline discovery/dispatch regression checks; never contact a broker or host.

Run from the project root with Python 3.10+ and Flask/paho-mqtt installed:
    python3 -B -m unittest discover -s tests -v
"""
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
from unittest.mock import Mock, patch

import paho.mqtt.client as mqtt


ROOT = Path(__file__).resolve().parents[1]


def load_panel():
    """Load real Flask code with example configs and block startup I/O/threads."""
    modules = {}
    for name, filename in (("config", "config.example.py"), ("devices", "devices.example.py")):
        module = types.ModuleType(name)
        path = ROOT / "homelab-panel" / filename
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
    """Exercise the actual app with temporary state and isolated external I/O."""

    def setUp(self):
        """Give every test fresh configuration, runtime files, and MQTT capture."""
        self.panel = load_panel()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for field, name in (("PANEL_HISTORY_FILE", "history.json"), ("PANEL_RUNTIME_FILE", "runtime.json"), ("PANEL_JOBS_FILE", "jobs.json")):
            setattr(self.panel, field, str(Path(self.temp.name) / name))
        self.panel.PANEL_STATE_DIR = self.temp.name
        self.panel.HOME_ASSISTANT_CONFIG["enabled"] = True
        self.panel.MQTT_CONNECTED = True
        self.panel.app.config.update(TESTING=True, SECRET_KEY="offline-test-secret")
        self.client = self.panel.app.test_client()
        self.published = []

        def capture(topic, payload, qos=1, retain=True):
            """Capture Paho-bound messages without opening a network socket."""
            self.published.append((topic, payload, qos, retain))
            return True

        publisher = patch.object(self.panel, "publish_mqtt_direct", side_effect=capture)
        publisher.start()
        self.addCleanup(publisher.stop)
        # Every subprocess call is blocked, including accidental power actions.
        subprocess_mock = patch.object(self.panel.subprocess, "run", side_effect=AssertionError("Unexpected external command"))
        subprocess_mock.start()
        self.addCleanup(subprocess_mock.stop)

    def button_configs(self):
        """Return captured button discovery documents keyed by their MQTT topic."""
        return {topic: json.loads(payload) for topic, payload, _, _ in self.published if "/button/" in topic}

    def test_every_web_action_is_discovered_with_its_label(self):
        """Examples produce all remote/WoL/local buttons without manual HA YAML."""
        self.panel.publish_home_assistant_discovery()
        buttons = self.button_configs()
        self.assertEqual(len(buttons), 15)
        self.assertEqual(len({b["unique_id"] for b in buttons.values()}), 15)
        for device_id, device in self.panel.REMOTE_DEVICES.items():
            base = f"homeassistant/button/homelab_panel_{device_id}"
            if device.get("wol", {}).get("enabled"):
                wake = buttons[f"{base}/wake/config"]
                self.assertEqual(wake["name"], device["wol"]["label"])
                self.assertEqual(wake["unique_id"], f"homelab_panel_{device_id}_wake")
                self.assertEqual(json.loads(wake["payload_press"]), {"device_id": device_id, "command": "power_on"})
                self.assertEqual(json.loads(buttons[f"{base}/cancel_wol/config"]["payload_press"])["command"], "cancel_wol")
            for button in (device.get("mqtt_controls") or {}).get("buttons", []):
                config = buttons[f"{base}/{button['id']}/config"]
                self.assertEqual(config["name"], button["label"])
                self.assertEqual(config["unique_id"], f"homelab_panel_{device_id}_{button['id']}")
                self.assertEqual(json.loads(config["payload_press"]), {"device_id": device_id, "command": button["id"]})
        for button in self.panel.LOCAL_SERVER["buttons"]:
            config = buttons[f"homeassistant/button/homelab_local_panel/{button['id']}/config"]
            self.assertEqual(config["name"], button["label"])
            self.assertEqual(config["device"]["name"], self.panel.LOCAL_SERVER["name"])
            self.assertEqual(json.loads(config["payload_press"]), {"target": "local", "command": button["id"]})
        for config in buttons.values():
            self.assertFalse(config["retain"])
            self.assertEqual(config["command_topic"], "homelab-panel/control")
            self.assertEqual(config["availability_topic"], "homelab-panel/availability")
        self.assertTrue(all(retain for _, _, _, retain in self.published))

    def test_local_device_name_falls_back_to_title_for_old_configs(self):
        """Existing devices.py files without name retain their previous HA device title."""
        expected = self.panel.LOCAL_SERVER["title"]
        self.panel.LOCAL_SERVER.pop("name", None)
        self.panel.publish_home_assistant_discovery()
        for config in self.button_configs().values():
            if config["device"]["identifiers"] == ["homelab_local_panel"]:
                self.assertEqual(config["device"]["name"], expected)

    def test_custom_buttons_and_namespace_do_not_need_code_changes(self):
        """New config IDs become entities; remote 'local' stays separate from host."""
        device = copy.deepcopy(self.panel.REMOTE_DEVICES["aoostar_wtr"])
        device["wol"]["enabled"] = False
        device["mqtt_controls"]["buttons"] = [{"id": "backup", "label": "Backup photos", "payload": "run_backup"}]
        self.panel.REMOTE_DEVICES = {"local": device}
        self.panel.LOCAL_SERVER["buttons"] = [{"id": "backup", "label": "Local backup", "script": "backup.sh"}]
        self.panel.publish_home_assistant_discovery()
        buttons = list(self.button_configs().values())
        self.assertEqual(len(buttons), 2)
        self.assertEqual(len({b["unique_id"] for b in buttons}), 2)
        self.assertEqual(len({b["device"]["identifiers"][0] for b in buttons}), 2)
        with patch.object(self.panel, "mqtt_publish", return_value=(True, "sent")) as publish, patch.object(self.panel, "run_local_script", return_value=(True, "done")) as run:
            for button in buttons:
                self.panel.process_panel_control_message(button["payload_press"])
            run.assert_called_once_with("backup.sh")
            self.assertEqual(json.loads(publish.call_args.args[1])["command"], "run_backup")

    def test_discovery_disabled_disconnected_or_missing_control_topic(self):
        """Opt-out is preserved; no unusable buttons are advertised without control."""
        for enabled, connected in ((False, True), (True, False)):
            with self.subTest(enabled=enabled, connected=connected):
                self.panel.HOME_ASSISTANT_CONFIG["enabled"] = enabled
                self.panel.MQTT_CONNECTED = connected
                self.panel.publish_home_assistant_snapshot()
                self.assertEqual(self.published, [])
        self.panel.HOME_ASSISTANT_CONFIG["enabled"] = True
        self.panel.MQTT_CONNECTED = True
        self.panel.MQTT_CONFIG["panel_control_topic"] = ""
        self.panel.publish_home_assistant_discovery()
        self.assertEqual(self.button_configs(), {})
        self.assertTrue(self.published)  # Status sensors remain supported.

    def test_web_and_mqtt_local_buttons_share_execution(self):
        """Both interfaces choose the same configured script; no shell text from MQTT."""
        with patch.object(self.panel, "run_local_script", return_value=(True, "scheduled")) as run:
            response = self.client.post("/local/shutdown_delay")
            self.assertEqual(response.status_code, 302)
            run.assert_called_once_with("shutdown_delay.sh")
            run.reset_mock()
            self.panel.process_panel_control_message('{"target":"local","command":"shutdown_delay","script":"evil.sh"}')
            run.assert_called_once_with("shutdown_delay.sh")
            run.reset_mock()
            for payload in ('{"target":"local","command":"../shutdown_delay.sh"}', '{"target":"local","command":"unknown"}', '{"target":"local","device_id":"aoostar_wtr","command":"shutdown_delay"}', '{"command":"shutdown_delay"}', '{"target":"invalid","command":"shutdown_delay"}', '[]', 'invalid'):
                self.panel.process_panel_control_message(payload)
            run.assert_not_called()

    def test_web_auth_and_token_still_protect_local_route(self):
        """Sharing the dispatcher does not bypass the existing web access gates."""
        with patch.object(self.panel, "execute_local_action") as execute:
            self.panel.PANEL_TOKEN = "test-token"
            self.assertEqual(self.client.post("/local/shutdown_delay").status_code, 403)
            self.panel.WEB_AUTH_CONFIG["enabled"] = True
            response = self.client.post("/local/shutdown_delay?token=test-token")
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.location.endswith("/login"))
            execute.assert_not_called()

    def test_retained_control_is_rejected_for_both_targets(self):
        """The common MQTT receive guard blocks stale remote and local power messages."""
        for payload in ('{"target":"local","command":"shutdown_delay"}', '{"device_id":"aoostar_wtr","command":"shutdown_delay"}'):
            msg = types.SimpleNamespace(topic="homelab-panel/control", payload=payload.encode(), retain=True, qos=1)
            with patch.object(self.panel.threading, "Thread") as thread, patch.object(self.panel, "execute_local_action") as local:
                self.panel.on_message_compat(None, None, msg)
                thread.assert_not_called()
                local.assert_not_called()

    def test_live_control_dispatches_worker_and_legacy_remote_envelope(self):
        """Fresh commands reach the existing worker path and remote JSON stays valid."""
        payload = '{"device_id":"aoostar_wtr","command":"run_watchtower"}'
        msg = types.SimpleNamespace(topic="homelab-panel/control", payload=payload.encode(), retain=False, qos=0)
        with patch.object(self.panel.threading, "Thread") as thread:
            self.panel.on_message_compat(None, None, msg)
            thread.assert_called_once_with(target=self.panel.process_panel_control_message, args=(payload,), daemon=True)
            thread.return_value.start.assert_called_once()
        with patch.object(self.panel, "execute_and_record_remote_action", return_value=(True, "sent")) as remote, patch.object(self.panel, "execute_local_action") as local:
            self.panel.process_panel_control_message(payload)
            remote.assert_called_once_with("aoostar_wtr", "run_watchtower", "MQTT homelab-panel/control")
            local.assert_not_called()

    def test_local_script_path_guards_are_preserved(self):
        """The new MQTT path retains filename containment and executable checks."""
        with patch.object(self.panel, "run_command") as run:
            self.assertFalse(self.panel.run_local_script("../shutdown_delay.sh")[0])
            self.assertFalse(self.panel.run_local_script("/tmp/anything.sh")[0])
            folder = Path(self.temp.name) / "scripts"
            folder.mkdir()
            outside = Path(self.temp.name) / "outside.sh"
            outside.write_text("#!/bin/sh\nexit 0\n")
            (folder / "escape.sh").symlink_to(outside)
            self.panel.SCRIPTS_DIR = str(folder)
            self.assertFalse(self.panel.run_local_script("escape.sh")[0])
            (folder / "not-executable.sh").write_text("#!/bin/sh\nexit 0\n")
            self.assertFalse(self.panel.run_local_script("not-executable.sh")[0])
            self.assertFalse(self.panel.run_local_script("missing.sh")[0])
            run.assert_not_called()

    def test_home_assistant_birth_republishes_discovery_and_cached_state(self):
        """HA restart restores entities even with discovery retain disabled."""
        self.panel.HOME_ASSISTANT_CONFIG["retain"] = False
        self.panel.DEVICE_STATUS_CACHE["aoostar_wtr"] = {"overall": "online", "ping_ok": True, "mqtt_online_ok": True}
        msg = types.SimpleNamespace(topic="homeassistant/status", payload=b"online", retain=True, qos=1)
        with patch.object(self.panel, "ping_host", side_effect=AssertionError("MQTT callback must not ping")):
            self.panel.on_message_compat(None, None, msg)
        self.assertEqual(len(self.button_configs()), 15)
        self.assertTrue(any(topic == "homelab-panel/availability" and payload == "online" for topic, payload, _, _ in self.published))
        self.assertTrue(any(topic == "homelab-panel/ha/aoostar_wtr/state" for topic, _, _, _ in self.published))
        self.assertTrue(all(not retain for topic, _, _, retain in self.published if topic.endswith("/config")))
        self.published.clear()
        msg.payload = b"offline"
        self.panel.on_message_compat(None, None, msg)
        self.assertEqual(self.published, [])

    def test_birth_defaults_customization_and_disabled_subscription(self):
        """Old configs use HA defaults; customized or disabled birth topics work."""
        self.panel.HOME_ASSISTANT_CONFIG.pop("status_topic")
        self.panel.HOME_ASSISTANT_CONFIG.pop("status_online_payload")
        client = Mock()
        self.panel.on_connect_compat(client, None, None, 0)
        self.assertIn("homeassistant/status", self.panel.MQTT_SUBSCRIPTIONS)
        self.assertEqual(len(self.button_configs()), 15)
        self.panel.HOME_ASSISTANT_CONFIG.update(status_topic="ha/custom/status", status_online_payload="ready")
        self.panel.on_connect_compat(client, None, None, 0)
        self.assertIn("ha/custom/status", self.panel.MQTT_SUBSCRIPTIONS)
        self.assertNotIn("homeassistant/status", self.panel.MQTT_SUBSCRIPTIONS)
        self.published.clear()
        msg = types.SimpleNamespace(topic="ha/custom/status", payload=b"ready", retain=False, qos=0)
        self.panel.on_message_compat(None, None, msg)
        self.assertEqual(len(self.button_configs()), 15)
        self.panel.HOME_ASSISTANT_CONFIG["status_topic"] = ""
        self.panel.on_connect_compat(client, None, None, 0)
        self.assertNotIn("ha/custom/status", self.panel.MQTT_SUBSCRIPTIONS)
        self.panel.HOME_ASSISTANT_CONFIG["enabled"] = False
        self.published.clear()
        self.panel.on_connect_compat(client, None, None, 0)
        self.assertEqual(self.published, [])

    def test_webpages_still_render(self):
        """Real Flask/Jinja render the unchanged pages with I/O controlled."""
        with patch.object(self.panel, "ping_host", return_value=False):
            for url in ("/", "/history/aoostar_wtr", "/mqtt-diagnostics"):
                with self.subTest(url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)
        self.panel.WEB_AUTH_CONFIG["enabled"] = True
        self.assertEqual(self.client.get("/login").status_code, 200)


if __name__ == "__main__":
    unittest.main()
