"""Inspection and argv safety checks; power commands always use isolated stubs."""
import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / 'VERSION').read_text().strip()
sys.path.insert(0, str(ROOT))
from shared_modules import mqtt


class CliTests(unittest.TestCase):
    def test_service_inspection_precedes_dependencies_and_private_configs(self):
        """-S hides installed packages; inspection must still work from any cwd."""
        paths = ['homelab-panel/app.py',
                 'homelab-control/homelab_control_command_listener.py',
                 'homelab-control/homelab_control_status_indicator.py']
        with tempfile.TemporaryDirectory() as directory:
            for path in paths:
                for flag in ('-h', '--help', '--version', '--unsupported', 'unexpected'):
                    with self.subTest(path=path, flag=flag):
                        result = subprocess.run([sys.executable, '-S', '-B', str(ROOT / path), flag],
                                                cwd=directory, capture_output=True, text=True, timeout=5)
                        self.assertEqual(result.returncode, 2 if flag in ('--unsupported', 'unexpected') else 0, result.stderr)
                        self.assertNotIn('Traceback', result.stderr)
                        if flag == '--version':
                            self.assertIn(VERSION, result.stdout)
                        elif flag in ('-h', '--help'):
                            self.assertIn('--version', result.stdout)
                            self.assertIn('no arguments', result.stdout)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_publisher_version_precedes_input_and_publication(self):
        """Version does not require normal-mode --config/--topic or stdin."""
        with patch.object(sys, 'argv', ['mqtt.py', '--version']), \
             patch.object(mqtt, 'publish_message') as publish, \
             patch('builtins.open', side_effect=AssertionError('Private config read')), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as result:
                mqtt.cli_main()
        self.assertEqual(result.exception.code, 0)
        self.assertTrue(output.getvalue().endswith(' ' + VERSION + '\n'))
        publish.assert_not_called()

    def prepare_scripts(self, directory):
        """Copy just source scripts and VERSION into a disposable fake install."""
        root = Path(directory)
        shutil.copytree(ROOT / 'scripts', root / 'scripts')
        shutil.copyfile(ROOT / 'VERSION', root / 'VERSION')
        commands = root / 'bin'
        commands.mkdir()
        return root, commands

    def test_power_inspection_and_errors_never_enter_privileged_setup(self):
        """Trap identity, config, Python, sudo and shutdown on inspection paths."""
        with tempfile.TemporaryDirectory() as directory:
            root, commands = self.prepare_scripts(directory)
            capture = root / 'unexpected'
            for name in ('id', 'shutdown', 'sudo', 'python3'):
                script = commands / name
                script.write_text('#!/bin/sh\nprintf invoked >> "$CAPTURE"\nexit 98\n')
                script.chmod(0o755)
            control = root / 'homelab-control'
            (control / 'configs').mkdir(parents=True)
            (control / 'modules').mkdir()
            (control / 'configs/config.json').write_text('invalid private configuration')
            (control / 'modules/homelab_control_lib.sh').write_text('printf sourced >> "$CAPTURE"; exit 99\n')
            env = {**os.environ, 'PATH': str(commands) + os.pathsep + os.environ['PATH'], 'CAPTURE': str(capture)}
            for path in sorted((root / 'scripts').glob('*.sh')):
                if path.name == 'homelab_action_common.sh':
                    continue
                for args in (['-h'], ['--help'], ['--version'], ['--unsupported'], ['unexpected'], ['--help', 'unexpected']):
                    with self.subTest(path=path.name, args=args):
                        result = subprocess.run(['bash', str(path), *args], cwd='/tmp', env=env,
                                                capture_output=True, text=True, timeout=5)
                        self.assertEqual(result.returncode, 0 if len(args) == 1 and args[0] in ('-h', '--help', '--version') else 2, result.stderr)
                        self.assertFalse(capture.exists(), 'Inspection entered setup or power operation')
                        if args == ['--version']:
                            self.assertIn(VERSION, result.stdout)
            self.assertFalse((control / 'state').exists())
            self.assertFalse((control / 'logs').exists())

    def test_power_actions_preserve_root_sudo_argv_and_failure_status(self):
        """No-argument invocation retains each action; stubs capture actual argv."""
        expected = {'shutdown_delay.sh': ['-h', '+1', 'Shutdown requested from Homelab Control Panel'],
                    'reboot_delay.sh': ['-r', '+1', 'Reboot requested from Homelab Control Panel'],
                    'shutdown_cancel.sh': ['-c'], 'reboot_cancel.sh': ['-c']}
        with tempfile.TemporaryDirectory() as directory:
            root, commands = self.prepare_scripts(directory)
            capture = root / 'captured'
            (commands / 'id').write_text('#!/bin/sh\nprintf "%s\\n" "$FAKE_UID"\n')
            for name in ('sudo', 'shutdown'):
                (commands / name).write_text('#!/bin/sh\nprintf "%s\\n" "$0" "$@" > "$CAPTURE"\nexit "$POWER_RC"\n')
            for script in commands.iterdir():
                script.chmod(0o755)
            env = {**os.environ, 'PATH': str(commands) + os.pathsep + os.environ['PATH'], 'CAPTURE': str(capture)}
            for name, args in expected.items():
                for uid in ('0', '1000'):
                    for rc in ('0', '7'):
                        with self.subTest(script=name, uid=uid, rc=rc):
                            result = subprocess.run(['bash', str(root / 'scripts' / name)], cwd='/tmp',
                                                    env={**env, 'FAKE_UID': uid, 'POWER_RC': rc},
                                                    capture_output=True, text=True, timeout=5)
                            self.assertEqual(result.returncode, 0 if rc == '0' else 1, result.stderr)
                            lines = capture.read_text().splitlines()
                            self.assertEqual(Path(lines[0]).name, 'shutdown' if uid == '0' else 'sudo')
                            self.assertEqual(lines[1:], args if uid == '0' else ['shutdown', *args])


if __name__ == '__main__':
    unittest.main()
