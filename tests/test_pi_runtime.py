"""Pi resource bounds, durable runtime updates and configured Waitress regressions."""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

from test_home_assistant import ROOT, load_panel


class PiRuntimeTests(unittest.TestCase):
    def setUp(self):
        """Load the real panel with mocked background I/O and disposable state files."""
        self.panel = load_panel()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.panel.PANEL_RUNTIME_FILE = str(self.root / "runtime.json")

    def source(self, name, data):
        """Write a cache source and return its path and exact serialized size."""
        path = self.root / name
        content = json.dumps(data)
        path.write_text(content, encoding="utf-8")
        return str(path), len(content.encode("utf-8"))

    def test_json_cache_evicts_least_recently_used_file_by_count(self):
        """Warm reads update recency; evicted data reloads without altering disk."""
        cache = self.panel.PanelJsonCache(max_files=2)
        paths = [self.source(str(i), {"n": i})[0] for i in range(3)]
        cache.load(paths[0], {})
        cache.load(paths[1], {})
        cache.load(paths[0], {})
        cache.load(paths[2], {})
        self.assertEqual(set(cache._files), {paths[0], paths[2]})
        self.assertEqual(cache.load(paths[1], {}), {"n": 1})
        self.assertTrue(all(Path(path).exists() for path in paths))

    def test_total_source_budget_and_oversized_bypass_preserve_data(self):
        """The combined byte budget is enforced; large files are readable, uncached."""
        first, size = self.source("one", {"n": 1})
        second, _ = self.source("two", {"n": 2})
        big, _ = self.source("big", {"text": "x" * 100})
        cache = self.panel.PanelJsonCache(max_files=3, max_bytes=size)
        cache.load(first, {})
        cache.load(second, {})
        self.assertEqual(set(cache._files), {second})
        self.assertLessEqual(cache._source_bytes, size)
        self.assertEqual(cache.load(big, {}), {"text": "x" * 100})
        self.assertNotIn(big, cache._files)
        self.assertEqual(cache.load(first, {}), {"n": 1})

    def test_disabled_cache_reopens_sources_and_keeps_no_entries(self):
        """Diagnostic bypass affects JSON reuse only and returns independent reads."""
        cache = self.panel.PanelJsonCache(enabled=False)
        path, _ = self.source("disabled", {"nested": [1]})
        first = cache.load(path, {})
        first["nested"].append(2)
        with patch("builtins.open", wraps=open) as opened:
            self.assertEqual(cache.load(path, {}), {"nested": [1]})
        opened.assert_called_once()
        self.assertEqual(cache._files, {})
        self.assertEqual(cache._source_bytes, 0)

    def test_cache_releases_accounting_on_corruption_delete_and_growth(self):
        """Failures and oversized replacements cannot leave stale retained objects."""
        cache = self.panel.PanelJsonCache(max_bytes=32)
        path, _ = self.source("changing", {"v": 1})
        for replacement in ("broken", None, json.dumps({"v": "x" * 100})):
            Path(path).write_text('{"v":1}')
            cache.load(path, {})
            if replacement is None:
                Path(path).unlink()
            else:
                Path(path).write_text(replacement)
            data = cache.load(path, {})
            self.assertEqual(data, {"v": "x" * 100} if replacement and len(replacement) > 32 else {})
            self.assertEqual(cache._source_bytes, 0)
            self.assertNotIn(path, cache._files)

    def test_concurrent_cold_reads_parse_once_and_return_isolated_objects(self):
        """Waitress readers share a parse without exposing mutable cached state."""
        cache = self.panel.PanelJsonCache()
        path, _ = self.source("parallel", {"values": [1]})
        barrier = threading.Barrier(4)

        def read():
            """Synchronize cold readers so they contend for the production lock."""
            barrier.wait(timeout=5)
            return cache.load(path, {})

        with patch("builtins.open", wraps=open) as opened:
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _: read(), range(4)))
        opened.assert_called_once()
        results[0]["values"].append(2)
        self.assertEqual(results[1], {"values": [1]})

    def test_repeated_runtime_update_skips_write_but_real_changes_persist(self):
        """Repeated boot IDs do not write the SD card or invalidate the dashboard."""
        self.panel.update_device_runtime("node", boot_id="boot-1", expected_state="online")
        original = Path(self.panel.PANEL_RUNTIME_FILE).read_bytes()
        identity = self.panel.JSON_FILE_CACHE.version(self.panel.PANEL_RUNTIME_FILE)
        with patch.object(self.panel, "save_runtime_state_unlocked", side_effect=AssertionError("Redundant write")):
            result = self.panel.update_device_runtime("node", boot_id="boot-1")
        result["boot_id"] = "mutated-return"
        self.assertEqual(Path(self.panel.PANEL_RUNTIME_FILE).read_bytes(), original)
        self.assertEqual(self.panel.JSON_FILE_CACHE.version(self.panel.PANEL_RUNTIME_FILE), identity)
        self.panel.update_device_runtime("node", boot_id="boot-2")
        self.assertEqual(json.loads(Path(self.panel.PANEL_RUNTIME_FILE).read_text())["node"],
                         {"boot_id": "boot-2", "expected_state": "online"})

    def test_noop_does_not_hide_new_missing_or_invalid_runtime_records(self):
        """Absent keys, invalid records and new devices still receive durable writes."""
        self.panel.save_json_file_atomic(self.panel.PANEL_RUNTIME_FILE, {"node": "invalid"})
        self.panel.update_device_runtime("node", boot_id="boot-1")
        self.panel.update_device_runtime("new", optional=None)
        self.assertEqual(self.panel.load_runtime_state_unlocked(),
                         {"node": {"boot_id": "boot-1"}, "new": {"optional": None}})

    def test_cache_configuration_rejects_invalid_limits(self):
        """Fail before startup for mistyped booleans, nonintegers or invalid budgets."""
        for options in ({"enabled": "false"}, {"max_files": 0}, {"max_files": True},
                        {"max_bytes": -1}, {"max_bytes": 1.5}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.panel.PanelJsonCache(**options)

    def test_server_options_validate_and_do_not_mutate_user_config(self):
        """All supported values pass through; unknown/invalid settings fail closed."""
        config = {"host": " 127.0.0.1 ", "port": 8081, "threads": 4,
                  "connection_limit": 16, "backlog": 20, "channel_timeout": 60, "cleanup_interval": 10}
        options = self.panel.server_options(config)
        self.assertEqual(options, {**config, "host": "127.0.0.1"})
        self.assertEqual(config["host"], " 127.0.0.1 ")
        for invalid in ([], {"host": ""}, {"host": None}, {"threads": 0},
                        {"threads": True}, {"threads": "2"}, {"port": 65536},
                        {"connection_limit": -1}, {"channel_timeout": 1.5}, {"threds": 4}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.panel.server_options(invalid)

    def test_direct_start_applies_config_and_imports_server_before_workers(self):
        """The normal app entry uses actual config values and starts each runtime once."""
        package = types.ModuleType("configs")
        package.__path__ = []
        fixtures = {"configs": package}
        for name, filename in (("configs.config", "config.example.py"), ("configs.devices", "devices.example.py")):
            module = types.ModuleType(name)
            exec((ROOT / "homelab-panel/configs" / filename).read_text(), module.__dict__)
            fixtures[name] = module
        fixtures["configs.config"].WEB_SERVER_CONFIG = {"host": "127.0.0.1", "port": 8081, "threads": 3}
        fixtures["configs.config"].STATE_CACHE_CONFIG = {"enabled": False, "max_files": 1, "max_bytes": 64}
        with patch.dict(sys.modules, fixtures), patch.object(sys, "argv", ["app.py"]), \
             patch("modules.panel_mqtt.PanelMqttRuntime.start") as start, patch("waitress.serve") as serve, \
             contextlib.redirect_stdout(io.StringIO()):
            state = runpy.run_path(str(ROOT / "homelab-panel/app.py"), run_name="__main__")
        start.assert_called_once()
        serve.assert_called_once_with(state["app"], host="127.0.0.1", port=8081, threads=3,
                                      connection_limit=32, backlog=64, channel_timeout=30, cleanup_interval=5)
        self.assertFalse(state["JSON_FILE_CACHE"].enabled)
        self.assertEqual(state["JSON_FILE_CACHE"].max_bytes, 64)


if __name__ == "__main__":
    unittest.main()
