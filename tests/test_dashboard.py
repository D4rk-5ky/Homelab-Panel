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
            self.assertEqual(set(fields), {"status", "jobs", "jobs_total", "jobs_limit"})
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
        self.assertIn('data-panel-countdown="1800000030.0"', first["devices"]["aoostar_wtr"]["jobs"])
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
            # Existing active configs may omit the optional paging setting.
            module.__dict__.pop("DASHBOARD_JOB_PAGE_SIZE", None)
            fixtures[name] = module
        with patch.dict(sys.modules, fixtures), patch.object(sys, "argv", ["app.py"]), patch("threading.Thread.start"), \
             patch("paho.mqtt.client.Client"), patch("waitress.serve") as serve, \
             patch("flask.Flask.run") as development, contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(str(ROOT / "homelab-panel/app.py"), run_name="__main__")
        serve.assert_called_once()
        self.assertEqual(serve.call_args.kwargs, {"host": "0.0.0.0", "port": 5000, "threads": 4})
        development.assert_not_called()

    def seed_jobs(self, count=100, device_id="aoostar_wtr"):
        """Write one realistic bounded source without repeated per-job fixture saves."""
        jobs = {device_id: [{"job_id": f"job-{n}", "status": "success",
                            "message": f"Completed {n}", "updated_at": f"{n:04d}"}
                           for n in range(count)]}
        self.panel.save_json_file_atomic(self.panel.PANEL_JOBS_FILE, jobs)
        return jobs

    def test_prepared_snapshot_reuses_all_work_and_batches_source_loads(self):
        self.seed_jobs()
        original = self.panel.JSON_FILE_CACHE.load
        with patch.object(self.panel.JSON_FILE_CACHE, "load", wraps=original) as load:
            first = self.poll().get_json()
        self.assertEqual([call.args[0] for call in load.call_args_list],
                         [self.panel.PANEL_RUNTIME_FILE, self.panel.PANEL_JOBS_FILE])
        with patch.object(self.panel.JSON_FILE_CACHE, "load", side_effect=AssertionError("Warm source loaded")), \
             patch.object(self.panel, "build_device_status", side_effect=AssertionError("Warm status rebuilt")), \
             patch.object(self.panel, "apply_job_timeout", side_effect=AssertionError("Warm job evaluated")), \
             patch.object(self.panel.DASHBOARD_CACHE, "_render", side_effect=AssertionError("Warm HTML rendered")):
            for client in (self.client, self.panel.app.test_client()):
                self.assertEqual(self.poll(first, client=client).get_json()["devices"], {})

    def test_age_and_countdown_do_not_invalidate_before_server_deadline(self):
        self.seed_ping()
        device = self.panel.REMOTE_DEVICES["aoostar_wtr"]
        self.panel.MQTT_RUNTIME.connected = True
        self.panel.MQTT_RUNTIME.set_state(device["status"]["power_topic"], "online", False, 0)
        self.panel.update_panel_job("aoostar_wtr", "clock", status="confirming", command="reboot_delay",
                                    started_at=self.panel.datetime.fromtimestamp(self.now).isoformat(),
                                    job_timeout_seconds=60)
        first = self.poll().get_json()
        self.assertIn("data-panel-age", first["devices"]["aoostar_wtr"]["status"])
        self.assertIn("data-panel-countdown", first["devices"]["aoostar_wtr"]["jobs"])
        with patch.object(self.panel.time, "time", return_value=self.now + 15), \
             patch.object(self.panel, "build_device_status", side_effect=AssertionError("Clock-only rebuild")):
            self.assertEqual(self.poll(first).get_json()["devices"], {})
        with patch.object(self.panel.time, "time", return_value=self.now + 60):
            expired = self.poll(first).get_json()["devices"]["aoostar_wtr"]["jobs"]
        self.assertIn('class="job timed_out"', expired)
        self.assertNotIn("data-panel-countdown", expired)
        self.assertIn("no longer considered active", expired)

    def test_prepared_cache_enforces_mqtt_and_monitor_expiry_and_clock_rewind(self):
        self.panel.STATUS_MONITOR_INTERVAL_SECONDS = 100
        self.panel.MQTT_ONLINE_TTL_SECONDS = 5
        self.seed_ping()
        device = self.panel.REMOTE_DEVICES["aoostar_wtr"]
        runtime = self.panel.MQTT_RUNTIME
        runtime.connected = True
        runtime.set_state(device["status"]["power_topic"], "online", False, 0)
        first = self.poll().get_json()
        self.assertIn('status-online', first["devices"]["aoostar_wtr"]["status"])
        with patch.object(self.panel.time, "time", return_value=self.now + 5):
            self.assertEqual(self.poll(first).get_json()["devices"], {})
        with patch.object(self.panel.time, "time", return_value=self.now + 6):
            expired = self.poll(first).get_json()
        self.assertIn("for gammel", expired["devices"]["aoostar_wtr"]["status"])
        self.assertNotIn("status-online", expired["devices"]["aoostar_wtr"]["status"])
        # A backward wall-clock step invalidates prepared expiry classifications.
        with patch.object(self.panel.time, "time", return_value=self.now + 2):
            rewound = self.poll(expired).get_json()
        self.assertIn("status-online", rewound["devices"]["aoostar_wtr"]["status"])
        with patch.object(self.panel.time, "time", return_value=self.now + 209):
            stale = self.poll(rewound).get_json()
        self.assertIn("Statusmåling er for gammel", stale["devices"]["aoostar_wtr"]["status"])

    def test_prepared_sources_invalidate_on_runtime_jobs_mqtt_actions_and_wol(self):
        first = self.poll().get_json()
        self.panel.update_device_runtime("aoostar_wtr", expected_state="offline", expected_state_reason="planned")
        second = self.poll(first).get_json()
        self.assertIn("planned", second["devices"]["aoostar_wtr"]["status"])
        self.panel.MQTT_RUNTIME.set_state("aoostar/status/hostname", "new-host", False, 0)
        third = self.poll(second).get_json()
        self.assertIn("new-host", third["devices"]["aoostar_wtr"]["status"])
        self.panel.record_panel_action("aoostar_wtr", "run_watchtower", False, "failed example", "test", self.now + 1, "now")
        fourth = self.poll(third).get_json()
        self.assertIn("failed example", fourth["devices"]["aoostar_wtr"]["status"])
        with patch.object(self.panel.ACTION_MANAGER, "wol_job_active", return_value=True):
            fifth = self.poll(fourth).get_json()
        self.assertIn("wol-cancel", fifth["devices"]["aoostar_wtr"]["status"])
        self.panel.REMOTE_DEVICES["aoostar_wtr"]["title"] = "Renamed"
        self.assertIn("Renamed", self.poll(fifth).get_json()["devices"]["aoostar_wtr"]["status"])

    def test_external_source_replacement_corruption_and_deletion_invalidate_prepared_view(self):
        self.panel.update_device_runtime("aoostar_wtr", expected_state="offline", expected_state_reason="first")
        first = self.poll().get_json()
        self.panel.save_json_file_atomic(self.panel.PANEL_RUNTIME_FILE, {"aoostar_wtr": {"expected_state_reason": "external"}})
        second = self.poll(first).get_json()
        self.assertIn("external", second["devices"]["aoostar_wtr"]["status"])
        Path(self.panel.PANEL_RUNTIME_FILE).write_text("corrupt")
        third = self.poll(second).get_json()
        self.assertNotIn("external", third["devices"]["aoostar_wtr"]["status"])
        self.seed_jobs(10)
        fourth = self.poll(third).get_json()
        Path(self.panel.PANEL_JOBS_FILE).unlink()
        fifth = self.poll(fourth).get_json()
        self.assertEqual(fifth["devices"]["aoostar_wtr"]["jobs_total"], 0)
        self.assertIn("Ingen jobs", fifth["devices"]["aoostar_wtr"]["jobs"])

    def test_lazy_jobs_render_only_requested_rows_and_reuse_bounded_row_cache(self):
        jobs = self.seed_jobs()
        first = self.poll().get_json()
        card = first["devices"]["aoostar_wtr"]
        self.assertEqual(card["jobs"].count('<li class="job '), 5)
        self.assertEqual((card["jobs_total"], card["jobs_limit"]), (100, 5))
        self.assertIn('data-job-id="job-99"', card["jobs"])
        self.assertNotIn('data-job-id="job-94"', card["jobs"])
        self.assertIn("data-jobs-sentinel", card["jobs"])
        original = self.panel.DASHBOARD_CACHE._render
        with patch.object(self.panel.DASHBOARD_CACHE, "_render", wraps=original) as render:
            expanded = self.client.get("/api/jobs/aoostar_wtr?limit=10").get_json()
        self.assertEqual(render.call_count, 5)
        self.assertEqual(expanded["devices"]["aoostar_wtr"]["jobs"].count('<li class="job '), 10)
        with patch.object(self.panel.DASHBOARD_CACHE, "_render", side_effect=AssertionError("Rows rendered twice")):
            self.client.get("/api/jobs/aoostar_wtr?limit=10")
            self.client.get("/api/jobs/aoostar_wtr?limit=7")
        self.assertEqual(self.panel.load_panel_jobs_unlocked(), jobs)
        self.assertEqual(len(self.panel.DASHBOARD_CACHE._cards["aoostar_wtr"]["jobs"]["rows"]), 100)
        self.assertEqual(self.panel.DASHBOARD_CACHE.snapshot(self.panel.REMOTE_DEVICES,
            self.panel.build_remote_device_statuses())["devices"]["aoostar_wtr"]["jobs_limit"], 5)
        # The no-JavaScript fallback can still show all retained jobs.
        self.assertEqual(self.client.get("/?jobs=all").data.count(b'<li class="job '), 100)

    def test_expanded_windows_stay_current_on_new_jobs_and_timeout(self):
        self.seed_jobs(12)
        self.client.get("/api/jobs/aoostar_wtr?limit=10")
        first = self.poll().get_json()
        self.panel.update_panel_job("aoostar_wtr", "inserted", status="running", updated_at="9999",
                                    started_at=self.panel.datetime.fromtimestamp(self.now).isoformat(), job_timeout_seconds=5)
        query = {"since": first["revision"], "instance": first["instance"], "jobs": json.dumps({"aoostar_wtr": 10})}
        second = self.client.get("/api/dashboard", query_string=query).get_json()["devices"]["aoostar_wtr"]
        self.assertEqual(second["jobs"].count('<li class="job '), 10)
        self.assertIn('data-job-id="inserted"', second["jobs"])
        self.assertEqual(second["jobs_total"], 13)
        with patch.object(self.panel.time, "time", return_value=self.now + 5):
            expired = self.client.get("/api/jobs/aoostar_wtr?limit=10").get_json()
        self.assertIn('class="job timed_out"', expired["devices"]["aoostar_wtr"]["jobs"])

    def test_job_window_auth_validation_escape_and_no_shared_session_data(self):
        self.seed_jobs(10)
        self.panel.update_panel_job("aoostar_wtr", "unsafe", status="success", updated_at="9999", message="<script>unsafe</script>")
        for query in ("", "?limit=0", "?limit=-1", "?limit=101", "?limit=invalid"):
            self.assertEqual(self.client.get("/api/jobs/aoostar_wtr" + query).status_code, 400)
        self.assertEqual(self.client.get("/api/jobs/unknown?limit=5").status_code, 404)
        for value in ('[]', '{"unknown":5}', '{"aoostar_wtr":true}', '{"aoostar_wtr":101}', 'bad'):
            self.assertEqual(self.client.get("/api/dashboard", query_string={"jobs": value}).status_code, 400)
        response = self.client.get("/api/jobs/aoostar_wtr?limit=10")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertIn("&lt;script&gt;", response.get_json()["devices"]["aoostar_wtr"]["jobs"])
        self.panel.WEB_AUTH_CONFIG["enabled"] = True
        blocked = self.client.get("/api/jobs/aoostar_wtr?limit=10")
        self.assertEqual(blocked.status_code, 401)
        self.assertEqual(blocked.get_json()["error"], "login_required")

    def test_unloaded_job_deadline_still_updates_active_count(self):
        jobs = self.seed_jobs(30)
        jobs["aoostar_wtr"][0].update(status="running", job_timeout_seconds=5,
            started_at=self.panel.datetime.fromtimestamp(self.now).isoformat())
        self.panel.save_json_file_atomic(self.panel.PANEL_JOBS_FILE, jobs)
        first = self.poll().get_json()
        self.assertNotIn('data-job-id="job-0"', first["devices"]["aoostar_wtr"]["jobs"])
        self.assertIn("Aktive jobs: 1", first["devices"]["aoostar_wtr"]["status"])
        with patch.object(self.panel.time, "time", return_value=self.now + 5):
            expired = self.poll(first).get_json()
            older = self.client.get("/api/jobs/aoostar_wtr?limit=30").get_json()
        self.assertNotIn("Aktive jobs:", expired["devices"]["aoostar_wtr"]["status"])
        self.assertIn('class="job timed_out"', older["devices"]["aoostar_wtr"]["jobs"])
        self.assertNotIn("data-jobs-sentinel", older["devices"]["aoostar_wtr"]["jobs"])
        self.assertEqual(self.panel.load_panel_jobs_unlocked(), jobs)

    def test_custom_initial_batch_does_not_change_retention(self):
        self.seed_jobs(12)
        self.panel.DASHBOARD_JOB_PAGE_SIZE = 2
        self.panel.DASHBOARD_CACHE = self.panel.PanelDashboardCache(self.panel.render_template, 2)
        card = self.poll().get_json()["devices"]["aoostar_wtr"]
        self.assertEqual(card["jobs_limit"], 2)
        self.assertEqual(card["jobs"].count('<li class="job '), 2)
        self.assertEqual(card["jobs_total"], 12)
        self.assertEqual(len(self.panel.get_panel_jobs("aoostar_wtr")), 12)

    def test_mqtt_payload_logging_is_optional_without_silencing_errors(self):
        runtime = self.panel.MQTT_RUNTIME
        for setting in (None, False, True):
            self.panel.MQTT_CONFIG.pop("log_payloads", None)
            if setting is not None:
                self.panel.MQTT_CONFIG["log_payloads"] = setting
            with patch("builtins.print") as log:
                runtime._message("unknown/status", "large telemetry", False, 0)
            self.assertEqual(log.call_count, 1 if setting else 0)
            self.assertEqual(runtime.get_state("unknown/status")["payload"], "large telemetry")
        self.panel.MQTT_CONFIG["log_payloads"] = False
        with patch("builtins.print") as log:
            runtime._message(self.panel.MQTT_CONFIG["panel_control_topic"], "unsafe retained command", True, 0)
            runtime._disconnected("test disconnect")
        self.assertTrue(any("retained control" in str(call) for call in log.call_args_list))
        self.assertTrue(any("disconnected" in str(call) for call in log.call_args_list))

    def test_prepared_cache_build_is_serialized_across_threads(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        cache = self.panel.PanelDashboardCache(lambda *args, **kwargs: "")
        barrier = threading.Barrier(6)
        def read():
            barrier.wait(timeout=5)
            return cache.prepare(("same",), build)
        with patch.object(self.panel, "build_device_status") as build:
            build.return_value = ({"prepared": True}, self.now + 20)
            with ThreadPoolExecutor(max_workers=6) as pool:
                results = list(pool.map(lambda _: read(), range(6)))
        build.assert_called_once()
        self.assertTrue(all(result is results[0] for result in results))


if __name__ == "__main__":
    unittest.main()

