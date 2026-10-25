"""Dashboard cache/delta, per-session responses and server startup regressions."""
import contextlib
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from test_home_assistant import ROOT, load_panel


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.panel = load_panel()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for field, filename in (("PANEL_HISTORY_FILE", "history.json"),
                                ("PANEL_RUNTIME_FILE", "runtime.json"),
                                ("PANEL_JOBS_FILE", "jobs.json")):
            setattr(self.panel, field, str(Path(self.temp.name) / filename))
        self.panel.app.config.update(TESTING=True, SECRET_KEY="dashboard-tests")
        self.client = self.panel.app.test_client()
        # Hold time still so MQTT ages and lifecycle countdowns have deterministic deltas.
        clock = patch.object(self.panel.time, "time", return_value=1800000000.0)
        self.now = clock.start().return_value
        self.addCleanup(clock.stop)
        network = patch.object(self.panel, "ping_host", side_effect=AssertionError("Web request pinged a device"))
        network.start()
        self.addCleanup(network.stop)

    def poll(self, previous=None, client=None):
        query = {} if previous is None else {"since": previous["revision"], "instance": previous["instance"]}
        return (client or self.client).get("/api/dashboard", query_string=query)

    def seed_ping(self, device_id="aoostar_wtr", *, age=0):
        self.panel.DEVICE_STATUS_CACHE[device_id] = {"ping_ok": True, "cached_at": self.now - age}

    def test_startup_and_expired_cache_never_ping_and_show_unknown(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertNotIn('http-equiv="refresh"', html)
        self.assertIn("Afventer statusmonitor", html)
        self.assertIn("dashboard.js", html)
        self.seed_ping(age=1000)
        data = self.poll().get_json()
        self.assertIn("Statusmåling er for gammel", data["devices"]["aoostar_wtr"]["status"])

    def test_unchanged_requests_reuse_fragments_and_send_no_cards(self):
        first = self.poll().get_json()
        with patch.object(self.panel.DASHBOARD_CACHE, "_render", side_effect=AssertionError("Unchanged fragment rendered")):
            response = self.poll(first)
        self.assertEqual(response.get_json()["devices"], {})
        self.assertEqual(response.get_json()["revision"], first["revision"])
        self.assertLess(len(response.data), 200)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertIn("Cookie", response.headers["Vary"])

    def test_only_changed_device_fragment_is_returned_and_restart_resets(self):
        first = self.poll().get_json()
        self.seed_ping()
        second = self.poll(first).get_json()
        self.assertEqual(set(second["devices"]), {"aoostar_wtr"})
        self.assertEqual(set(second["devices"]["aoostar_wtr"]), {"status"})
        # Every tab has its own revision cursor; one tab must not consume another's delta.
        self.assertEqual(self.poll(first).get_json()["devices"], second["devices"])
        reset = self.client.get("/api/dashboard", query_string={"since": second["revision"], "instance": "previous-process"}).get_json()
        self.assertEqual(set(reset["devices"]), set(self.panel.REMOTE_DEVICES))
        for fields in reset["devices"].values():
            self.assertEqual(set(fields), {"status", "jobs"})
        self.assertEqual(set(self.client.get("/api/dashboard?since=bad").get_json()["devices"]), set(self.panel.REMOTE_DEVICES))

    def test_broker_loss_and_mqtt_expiry_cannot_leave_green_online(self):
        device = self.panel.REMOTE_DEVICES["aoostar_wtr"]
        self.seed_ping()
        runtime = self.panel.MQTT_RUNTIME
        runtime.connected = True
        runtime.set_state(device["status"]["power_topic"], "online", False, 0)
        self.assertIn('status-online', self.poll().get_json()["devices"]["aoostar_wtr"]["status"])
        runtime.connected = False
        offline = self.poll().get_json()["devices"]["aoostar_wtr"]["status"]
        self.assertNotIn('status-online', offline)
        runtime.connected = True
        runtime.state[device["status"]["power_topic"]]["timestamp"] = self.now - 1000
        expired = self.poll().get_json()["devices"]["aoostar_wtr"]["status"]
        self.assertNotIn('status-online', expired)
        self.assertIn("for gammel", expired)

    def test_job_sources_invalidate_and_timeouts_progress_without_new_mqtt(self):
        self.panel.update_panel_job("aoostar_wtr", "job-1", command="reboot_delay", status="confirming",
                                    queued_at=self.panel.datetime.fromtimestamp(self.now - 30).isoformat(),
                                    message="Waiting", job_timeout_seconds=60)
        first = self.poll().get_json()
        self.assertIn("timeout om 30s", first["devices"]["aoostar_wtr"]["jobs"])
        with patch.object(self.panel.time, "time", return_value=self.now + 31):
            expired = self.poll(first).get_json()["devices"]["aoostar_wtr"]["jobs"]
        self.assertIn('class="job timed_out"', expired)
        self.assertIn("no longer considered active", expired)
        self.panel.update_panel_job("aoostar_wtr", "job-1", status="success", message="Finished")
        finished = self.poll(first).get_json()["devices"]["aoostar_wtr"]["jobs"]
        self.assertIn('class="job success"', finished)
        self.assertIn("Finished", finished)
        # Remote-only changes must also invalidate the merged-job cache.
        topic = self.panel.REMOTE_DEVICES["aoostar_wtr"]["status"]["jobs_topic"]
        self.panel.MQTT_RUNTIME.set_state(topic, json.dumps([{"job_id": "remote-2", "status": "running", "message": "remote"}]), False, 0)
        self.assertIn("remote-2", self.poll().get_json()["devices"]["aoostar_wtr"]["jobs"])

    def test_state_cache_reuses_decoded_data_and_notices_replace_delete_corruption(self):
        path = self.panel.PANEL_RUNTIME_FILE
        self.panel.save_json_file_atomic(path, {"value": {"nested": 1}})
        loaded = self.panel.load_json_file(path, {})
        loaded["value"]["nested"] = 99
        with patch("builtins.open", side_effect=AssertionError("Unchanged JSON reopened")):
            self.assertEqual(self.panel.load_json_file(path, {}), {"value": {"nested": 1}})
        self.panel.save_json_file_atomic(path, {"value": 2})
        self.assertEqual(self.panel.load_json_file(path, {}), {"value": 2})
        Path(path).write_text("invalid")
        self.assertEqual(self.panel.load_json_file(path, {}), {})
        Path(path).unlink()
        self.assertEqual(self.panel.load_json_file(path, []), [])

    def test_login_and_action_results_remain_private_and_json_requires_auth(self):
        self.panel.WEB_AUTH_CONFIG.update(enabled=True, username="admin", password="test-password")
        anonymous = self.panel.app.test_client()
        self.assertEqual(self.poll(client=anonymous).status_code, 401)
        self.assertEqual(anonymous.get("/").status_code, 302)
        for client, username in ((self.client, "Alice"), (anonymous, "Bob")):
            with client.session_transaction() as session:
                session["authenticated"] = True
                session["username"] = username
        # A private flash must survive polling and appear only in its owner's shell.
        with self.client.session_transaction() as session:
            session["_flashes"] = [("success", "Alice-private-message")]
        first = self.poll().get_json()
        self.assertNotIn("Alice", json.dumps(first))
        self.assertNotIn("Bob", json.dumps(first))
        self.assertEqual(self.poll(first, client=anonymous).get_json()["devices"], {})
        bob_html = anonymous.get("/").get_data(as_text=True)
        self.assertIn("Logget ind som Bob", bob_html)
        self.assertNotIn("Alice-private-message", bob_html)
        alice_html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Logget ind som Alice", alice_html)
        self.assertIn("Alice-private-message", alice_html)
        with patch.object(self.panel.ACTION_MANAGER, "execute_local_action", return_value=(True, "Only Alice")):
            result = self.client.post("/local/shutdown_cancel", headers={"Accept": "application/json"})
        self.assertEqual(result.get_json(), {"ok": True, "message": "Only Alice"})
        self.assertNotIn("Only Alice", anonymous.get("/").get_data(as_text=True))
        self.client.post("/logout")
        with patch.object(self.panel.ACTION_MANAGER, "execute_local_action") as execute:
            blocked = self.client.post("/local/shutdown_cancel", headers={"Accept": "application/json"})
        self.assertEqual(blocked.status_code, 401)
        execute.assert_not_called()

    def test_shared_html_escapes_device_and_job_payloads(self):
        self.panel.REMOTE_DEVICES["aoostar_wtr"]["title"] = '<img src=x onerror="alert(1)">'
        self.panel.update_panel_job("aoostar_wtr", "unsafe", status="running", message="<script>alert(1)</script>")
        data = self.poll().get_json()["devices"]["aoostar_wtr"]
        self.assertNotIn("<img", data["status"])
        self.assertNotIn("<script>", data["jobs"])
        self.assertIn("&lt;script&gt;", data["jobs"])

    def test_script_entry_uses_waitress_once_instead_of_development_server(self):
        package = types.ModuleType("configs")
        package.__path__ = []
        fixtures = {"configs": package}
        for name, filename in (("configs.config", "config.example.py"), ("configs.devices", "devices.example.py")):
            module = types.ModuleType(name)
            exec((ROOT / "homelab-panel/configs" / filename).read_text(), module.__dict__)
            fixtures[name] = module
        with patch.dict(sys.modules, fixtures), patch("threading.Thread.start"), \
             patch("paho.mqtt.client.Client"), patch("waitress.serve") as serve, \
             patch("flask.Flask.run") as development, contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(str(ROOT / "homelab-panel/app.py"), run_name="__main__")
        serve.assert_called_once()
        self.assertEqual(serve.call_args.kwargs, {"host": "0.0.0.0", "port": 5000, "threads": 4})
        development.assert_not_called()


if __name__ == "__main__":
    unittest.main()

