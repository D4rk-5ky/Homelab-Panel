"""Paho publishing checks with fake clients and an isolated loopback MQTT peer."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import homelab_mqtt as publisher
from test_home_assistant import load_panel


class PublisherTests(unittest.TestCase):
    """Check error handling, compatibility, and both production call sites."""

    def client(self, reason=0, acknowledged=True):
        """Create a client whose first loop delivers a controlled CONNACK."""
        client = Mock()
        client.connect.return_value = publisher.mqtt.MQTT_ERR_SUCCESS
        client.loop.side_effect = lambda **kwargs: self.connect_callback(client, reason)
        client.publish.return_value.rc = publisher.mqtt.MQTT_ERR_SUCCESS
        client.publish.return_value.is_published.return_value = acknowledged
        return client

    def connect_callback(self, client, reason):
        """Deliver the callback without contacting a real broker."""
        client.on_connect(client, None, {}, reason, None)
        return publisher.mqtt.MQTT_ERR_SUCCESS

    def test_settings_payload_qos_and_retention_are_preserved(self):
        """Each publish uses configured auth/port and exact payload."""
        for qos in (0, 1, 2):
            with self.subTest(qos=qos):
                client = self.client()
                with patch.object(publisher, 'build_client', return_value=client):
                    ok, _ = publisher._publish_once(
                        {'host': 'broker', 'port': 1884, 'user': 'alice', 'pass': 'secret'},
                        'device/state', 'æ\n "value" ', qos=qos, retain=True)
                self.assertTrue(ok)
                client.username_pw_set.assert_called_once_with('alice', 'secret')
                client.connect.assert_called_once_with('broker', 1884, keepalive=60)
                client.publish.assert_called_once_with('device/state', payload='æ\n "value" ', qos=qos, retain=True)
                client.disconnect.assert_called_once()
                client.reconnect.assert_not_called()
                client.loop_start.assert_not_called()
                client.socket.assert_not_called()

    def test_default_command_is_nonretained_and_unauthenticated(self):
        """Empty credentials remain optional; default command retention is off."""
        client = self.client()
        with patch.object(publisher, 'build_client', return_value=client):
            self.assertTrue(publisher._publish_once({'host': 'broker'}, 'command', 'wake')[0])
        client.username_pw_set.assert_not_called()
        client.publish.assert_called_once_with('command', payload='wake', qos=0, retain=False)
        client.connect.assert_called_once_with('broker', 1883, keepalive=60)

    def test_refused_connection_never_publishes(self):
        """A broker rejecting login cannot be reported as a successful send."""
        client = self.client(reason=5)
        with patch.object(publisher, 'build_client', return_value=client):
            ok, message = publisher._publish_once({'host': 'broker'}, 'command', 'wake')
        self.assertFalse(ok)
        self.assertIn('rejected', message)
        client.publish.assert_not_called()
        client.socket.return_value.close.assert_called_once()

    def test_connect_exception_and_publish_error_fail(self):
        """Socket failures and Paho return-code failures reach callers."""
        for at_connect in (True, False):
            with self.subTest(at_connect=at_connect):
                client = self.client()
                if at_connect:
                    client.connect.side_effect = OSError('connection refused')
                else:
                    client.publish.return_value.rc = publisher.mqtt.MQTT_ERR_NO_CONN
                with patch.object(publisher, 'build_client', return_value=client):
                    self.assertFalse(publisher._publish_once({'host': 'broker'}, 'command', 'wake')[0])
                client.disconnect.assert_called_once()
                client.reconnect.assert_not_called()

    def test_timeout_closes_socket_before_disconnect_without_retry(self):
        """Unacknowledged commands cannot be flushed later by cleanup/reconnect."""
        client = self.client(acknowledged=False)
        events = []
        client.socket.return_value.shutdown.side_effect = lambda how: events.append('shutdown')
        client.socket.return_value.close.side_effect = lambda: events.append('close')
        client.disconnect.side_effect = lambda: events.append('disconnect')
        with patch.object(publisher, 'build_client', return_value=client), patch.object(publisher.time, 'monotonic', side_effect=[0, 0, 0, 2]):
            ok, message = publisher._publish_once({'host': 'broker'}, 'command', 'wake', qos=1, timeout=1)
        self.assertFalse(ok)
        self.assertIn('delivery may be unknown', message)
        self.assertEqual(events, ['shutdown', 'close', 'disconnect'])
        client.publish.assert_called_once()
        client.reconnect.assert_not_called()

    def test_invalid_inputs_fail_before_connecting(self):
        """Invalid topics, QoS, and deadlines do not create a network client."""
        cases = [('', {}), ('a/+', {}), ('a/#', {}), ('valid', {'qos': 3}),
                 ('valid', {'timeout': 0}), ('valid', {'timeout': float('nan')})]
        with patch.object(publisher, 'build_client') as build:
            for topic, options in cases:
                self.assertFalse(publisher._publish_once({'host': 'broker'}, topic, 'data', **options)[0])
            build.assert_not_called()

    def test_client_construction_supports_paho_callback_versions(self):
        """New clients use API v2; older Paho keeps its original constructor."""
        with patch.object(publisher.mqtt, 'Client') as client:
            publisher.build_client()
            self.assertTrue(client.call_args.kwargs['clean_session'])
            self.assertEqual(client.call_args.kwargs['callback_api_version'], publisher.mqtt.CallbackAPIVersion.VERSION2)
        legacy = Mock(spec=['Client', 'MQTTv311'])
        legacy.MQTTv311 = 4
        with patch.object(publisher, 'mqtt', legacy):
            publisher.build_client()
        legacy.Client.assert_called_once_with(clean_session=True, protocol=4)

    def test_parent_bounds_worker_and_keeps_credentials_off_argv(self):
        """The Paho child receives private input and retains the hard time limit."""
        result = Mock(returncode=0, stdout='[true, "published"]')
        with patch.object(publisher.subprocess, 'run', return_value=result) as run:
            self.assertEqual(publisher.publish_message({'host': 'broker', 'pass': 'secret'}, 'topic', 'payload'), (True, 'published'))
        args, options = run.call_args
        self.assertEqual(args[0][0], sys.executable)
        self.assertNotIn('secret', ' '.join(args[0]))
        self.assertEqual(json.loads(options['input'])['settings']['pass'], 'secret')
        self.assertEqual(options['timeout'], 20)
        self.assertEqual(args[0][-1], '--request-stdin')
        with patch.object(publisher.subprocess, 'run', side_effect=subprocess.TimeoutExpired('publisher', 20)):
            ok, message = publisher.publish_message({'host': 'broker'}, 'topic', 'payload')
        self.assertFalse(ok)
        self.assertIn('timed out', message)

    def test_panel_reuses_shared_publisher_and_config(self):
        """Panel commands preserve their own QoS/retain settings and errors."""
        panel = load_panel()
        panel.MQTT_CONFIG.update(qos=2, retain=False)
        with patch.object(panel, 'publish_message', return_value=(False, 'failed')) as publish, patch.object(panel, 'run_command') as run:
            self.assertEqual(panel.mqtt_publish('device/control', 'wake'), (False, 'failed'))
            publish.assert_called_once_with(panel.MQTT_CONFIG, 'device/control', 'wake', qos=2, retain=False)
            run.assert_not_called()

    def test_cli_reads_credentials_from_config_and_payload_from_stdin(self):
        """The shell bridge preserves whitespace and never needs password flags."""
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.json'
            settings = {'host': 'broker', 'user': 'alice', 'pass': 'secret'}
            config.write_text(json.dumps({'mqtt': settings}))
            with patch.object(publisher, 'publish_message', return_value=(True, 'sent')) as publish, patch.object(sys, 'stdin', io.StringIO('æ\n trailing ')), contextlib.redirect_stdout(io.StringIO()):
                rc = publisher.main(['--config', str(config), '--topic', 'state', '--qos', '2', '--retain', '--timeout', '3'])
            self.assertEqual(rc, 0)
            publish.assert_called_once_with(settings, 'state', 'æ\n trailing ', qos=2, retain=True, timeout=3)
            with patch.object(publisher, 'publish_message', return_value=(False, 'rejected')), patch.object(sys, 'stdin', io.StringIO('data')), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(publisher.main(['--config', str(config), '--topic', 'state']), 1)

    def test_cli_help_and_config_errors(self):
        """Help exits before input/network work; missing config exits nonzero."""
        with patch.object(publisher, 'publish_message') as publish, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                publisher.main(['--help'])
            self.assertEqual(result.exception.code, 0)
            self.assertEqual(publisher.main(['--config', '/nonexistent/homelab-config.json', '--topic', 'state']), 1)
            publish.assert_not_called()

    def test_shell_bridge_payload_and_failure_exit(self):
        """The real shell helper passes exact stdin and propagates Python failure."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control = root / 'homelab-control'
            control.mkdir()
            shutil.copyfile(ROOT / 'homelab-control/homelab_control_lib.sh', control / 'lib.sh')
            shutil.copyfile(ROOT / 'homelab-control/config.example.json', control / 'config.json')
            shim = root / 'python3'
            shim.write_text(f'''#!{sys.executable}
import json,os,sys
from pathlib import Path
if len(sys.argv)>1 and sys.argv[1].endswith('/homelab_mqtt.py'):
 Path(os.environ['CAPTURE']).write_text(json.dumps({{'args':sys.argv[1:],'payload':sys.stdin.read()}}))
 print('published')
 if int(os.environ['PUBLISH_RC']): print('publish failed',file=sys.stderr)
 sys.exit(int(os.environ['PUBLISH_RC']))
os.execv(sys.executable,[sys.executable,*sys.argv[1:]])
''')
            shim.chmod(0o755)
            capture = root / 'captured.json'
            env = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'], 'CAPTURE': str(capture)}
            for rc in (0, 7):
                env['PUBLISH_RC'] = str(rc)
                result = subprocess.run(['bash', '-c', 'source "$1"; mqtt_pub "device/state" "$2"', 'check', str(control / 'lib.sh'), 'æ\n trailing '], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, rc, result.stderr)
                self.assertEqual(result.stdout, '')
                if rc:
                    self.assertIn('publish failed', result.stderr)
                record = json.loads(capture.read_text())
                self.assertEqual(record['payload'], 'æ\n trailing ')
                self.assertEqual(record['args'][1:], ['--config', str(control / 'config.json'), '--topic', 'device/state', '--qos', '1', '--retain'])
            capture.unlink()
            result = subprocess.run(['bash', '-c', 'source "$1"; mqtt_pub "" "unused"', 'check', str(control / 'lib.sh')], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(capture.exists())


class WireTests(unittest.TestCase):
    """Exercise the real installed Paho against a tiny localhost protocol peer."""

    @staticmethod
    def read_packet(conn):
        """Read one MQTT fixed header and body for protocol assertions."""
        header = conn.recv(1)
        if not header:
            raise EOFError('peer closed')
        length = 0
        multiplier = 1
        while True:
            byte = conn.recv(1)
            if not byte:
                raise EOFError('truncated length')
            value = byte[0]
            length += (value & 127) * multiplier
            if value < 128:
                break
            multiplier *= 128
        body = bytearray()
        while len(body) < length:
            chunk = conn.recv(length - len(body))
            if not chunk:
                raise EOFError('truncated packet')
            body.extend(chunk)
        return header[0], bytes(body)

    @staticmethod
    def read_string(body, offset):
        """Decode one length-prefixed MQTT byte string and advance its offset."""
        size = int.from_bytes(body[offset:offset+2], 'big')
        end = offset + 2 + size
        return body[offset+2:end], end

    def exchange(self, qos=1, retain=False, reject=False, acknowledge=True):
        """Run one bounded localhost exchange and return captured wire data."""
        listener = socket.socket()
        self.addCleanup(listener.close)
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(3)
        captured = {}
        errors = []

        def serve():
            """Accept CONNECT, optionally acknowledge PUBLISH, and observe close."""
            try:
                conn, _ = listener.accept()
                with conn:
                    conn.settimeout(3)
                    header, body = self.read_packet(conn)
                    self.assertEqual(header, 0x10)
                    captured['connect'] = body
                    conn.sendall(b'\x20\x02\x00' + (b'\x05' if reject else b'\x00'))
                    if reject:
                        captured['after_reject'] = conn.recv(1)
                        return
                    header, body = self.read_packet(conn)
                    captured['publish'] = (header, body)
                    size = int.from_bytes(body[:2], 'big')
                    if qos:
                        mid = body[2+size:4+size]
                        if acknowledge:
                            conn.sendall((b'\x40\x02' if qos == 1 else b'\x50\x02') + mid)
                            if qos == 2:
                                self.assertEqual(self.read_packet(conn), (0x62, mid))
                                conn.sendall(b'\x70\x02' + mid)
                    captured['ending'] = conn.recv(8)
            except BaseException as exc:
                errors.append(exc)

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        result = publisher.publish_message(
            {'host': '127.0.0.1', 'port': listener.getsockname()[1], 'user': 'alice', 'pass': 'secret'},
            'test/isolated', 'æ\n payload ', qos=qos, retain=retain, timeout=1.5)
        worker.join(4)
        self.assertFalse(worker.is_alive(), 'protocol peer did not stop')
        if errors:
            raise errors[0]
        return result, captured

    def test_real_paho_qos_zero_one_two_and_retention(self):
        """CONNECT auth and PUBLISH flags/UTF-8 bytes survive the migration."""
        for qos, retain in ((0, False), (1, True), (2, False)):
            with self.subTest(qos=qos, retain=retain):
                (ok, message), captured = self.exchange(qos=qos, retain=retain)
                self.assertTrue(ok, message)
                connect = captured['connect']
                self.assertEqual(connect[7] & 0xC2, 0xC2)  # username, password, clean session
                _, offset = self.read_string(connect, 10)  # generated client ID
                username, offset = self.read_string(connect, offset)
                password, _ = self.read_string(connect, offset)
                self.assertEqual((username, password), (b'alice', b'secret'))
                header, body = captured['publish']
                self.assertEqual(header, 0x30 | (qos << 1) | int(retain))
                topic, offset = self.read_string(body, 0)
                self.assertEqual(topic, b'test/isolated')
                self.assertEqual(body[offset + (2 if qos else 0):], 'æ\n payload '.encode())

    def test_real_paho_rejected_connection_sends_no_command(self):
        """A refused CONNACK closes the disposable client without a PUBLISH."""
        (ok, _), captured = self.exchange(reject=True)
        self.assertFalse(ok)
        self.assertEqual(captured['after_reject'], b'')
        self.assertNotIn('publish', captured)

    def test_real_paho_missing_ack_times_out_and_closes(self):
        """Lost PUBACK reports uncertain delivery and does not retry."""
        (ok, message), captured = self.exchange(acknowledge=False)
        self.assertFalse(ok)
        self.assertIn('delivery may be unknown', message)
        self.assertEqual(captured['ending'], b'')


if __name__ == '__main__':
    unittest.main()
