import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


class CliEntrypointTests(unittest.TestCase):
    def run_command(self, argv, *, env=None):
        return subprocess.run(
            argv,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def test_python_entrypoints_have_safe_help_and_version(self):
        entrypoints = [
            ROOT / "homelab-panel" / "app.py",
            ROOT / "homelab-control" / "homelab_control_command_listener.py",
            ROOT / "homelab-control" / "homelab_control_status_indicator.py",
            ROOT / "shared_modules" / "mqtt.py",
        ]
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        for entrypoint in entrypoints:
            with self.subTest(entrypoint=entrypoint.name, flag="--help"):
                result = self.run_command([sys.executable, str(entrypoint), "--help"], env=env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--version", result.stdout)
                self.assertIn("--help", result.stdout)
            with self.subTest(entrypoint=entrypoint.name, flag="--version"):
                result = self.run_command([sys.executable, str(entrypoint), "--version"], env=env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(VERSION, result.stdout)

    def test_long_running_python_entrypoints_reject_unknown_flags_before_dependencies(self):
        entrypoints = [
            ROOT / "homelab-panel" / "app.py",
            ROOT / "homelab-control" / "homelab_control_command_listener.py",
            ROOT / "homelab-control" / "homelab_control_status_indicator.py",
        ]
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        for entrypoint in entrypoints:
            with self.subTest(entrypoint=entrypoint.name):
                result = self.run_command([sys.executable, str(entrypoint), "--not-a-real-flag"], env=env)
                self.assertEqual(result.returncode, 2)
                self.assertIn("unrecognized arguments", result.stderr)

    def shell_test_env(self, tempdir: str):
        temp = Path(tempdir)
        marker = temp / "shutdown-called"
        (temp / "id").write_text("#!/bin/sh\n[ \"$1\" = \"-u\" ] && echo 0\n", encoding="utf-8")
        (temp / "shutdown").write_text(
            "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$SHUTDOWN_MARKER\"\n",
            encoding="utf-8",
        )
        (temp / "sudo").write_text(
            "#!/bin/sh\nexec \"$@\"\n",
            encoding="utf-8",
        )
        for name in ("id", "shutdown", "sudo"):
            (temp / name).chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = tempdir + os.pathsep + env.get("PATH", "")
        env["SHUTDOWN_MARKER"] = str(marker)
        return env, marker

    def test_power_scripts_help_version_and_unknown_args_do_not_execute_actions(self):
        scripts = [
            ROOT / "scripts" / "shutdown_delay.sh",
            ROOT / "scripts" / "shutdown_cancel.sh",
            ROOT / "scripts" / "reboot_delay.sh",
            ROOT / "scripts" / "reboot_cancel.sh",
        ]
        with tempfile.TemporaryDirectory() as tempdir:
            env, marker = self.shell_test_env(tempdir)
            for script in scripts:
                with self.subTest(script=script.name, flag="--help"):
                    result = self.run_command([str(script), "--help"], env=env)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("--version", result.stdout)
                    self.assertFalse(marker.exists())
                with self.subTest(script=script.name, flag="--version"):
                    result = self.run_command([str(script), "--version"], env=env)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(VERSION, result.stdout)
                    self.assertFalse(marker.exists())
                with self.subTest(script=script.name, flag="unknown"):
                    result = self.run_command([str(script), "--not-a-real-flag"], env=env)
                    self.assertEqual(result.returncode, 2)
                    self.assertFalse(marker.exists())

    def test_power_scripts_keep_no_argument_actions(self):
        expected = {
            "shutdown_delay.sh": '-h +1 Shutdown requested from Homelab Control Panel',
            "shutdown_cancel.sh": '-c',
            "reboot_delay.sh": '-r +1 Reboot requested from Homelab Control Panel',
            "reboot_cancel.sh": '-c',
        }
        with tempfile.TemporaryDirectory() as tempdir:
            env, marker = self.shell_test_env(tempdir)
            for name, expected_args in expected.items():
                marker.unlink(missing_ok=True)
                script = ROOT / "scripts" / name
                with self.subTest(script=name):
                    result = self.run_command([str(script)], env=env)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertTrue(marker.exists())
                    self.assertEqual(marker.read_text(encoding="utf-8").strip(), expected_args)

    def test_executable_shell_helpers_have_information_only_cli(self):
        helpers = [
            ROOT / "scripts" / "homelab_action_common.sh",
            ROOT / "homelab-control" / "modules" / "homelab_control_lib.sh",
        ]
        for helper in helpers:
            with self.subTest(helper=helper.name, flag="--help"):
                result = self.run_command([str(helper), "--help"])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--version", result.stdout)
            with self.subTest(helper=helper.name, flag="--version"):
                result = self.run_command([str(helper), "--version"])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(VERSION, result.stdout)
            with self.subTest(helper=helper.name, flag="no-args"):
                result = self.run_command([str(helper)])
                self.assertEqual(result.returncode, 2)
                self.assertIn("no standalone operational mode", result.stderr)


if __name__ == "__main__":
    unittest.main()
