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
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from shared_modules import mqtt as shared_mqtt
publisher = shared_mqtt
from test_home_assistant import load_panel


class PublisherTests(unittest.TestCase):
    """Check shared MQTT transport, one-shot publishing, and production callers."""

    def client(self, reason=0, acknowledged=True):
        """Create a client whose first loop delivers a controlled CONNACK."""
        client = Mock()
        client.connect.return_value = shared_mqtt.mqtt.MQTT_ERR_SUCCESS
        def connect_once(**kwargs):
            client.on_connect(client, None, {}, reason, None)
            return shared_mqtt.mqtt.MQTT_ERR_SUCCESS
        client.loop.side_effect = connect_once
        client.publish.return_value.rc = shared_mqtt.mqtt.MQTT_ERR_SUCCESS
        client.publish.return_value.is_published.return_value = acknowledged
        return client

    def test_settings_payload_qos_and_retention_are_preserved(self):
        """Each publish uses configured auth/port and exact payload."""
        for qos in (0, 1, 2):
            with self.subTest(qos=qos):
                client = self.client()
                with patch.object(shared_mqtt.mqtt, 'Client', return_value=client):
                    ok, _ = publisher._publish_once(
                        {'host': 'broker', 'port': 1884, 'user': 'alice', 'pass': 'secret'},
                        'device/state', 'æ\n "value" ', qos=qos, retain=True, timeout=20)
                self.assertTrue(ok)
                client.username_pw_set.assert_called_once_with('alice', 'secret')
                client.connect.assert_called_once_with('broker', 1884, keepalive=60)
                client.publish.assert_called_once_with('device/state', payload='æ\n "value" ', qos=qos, retain=True)
                client.disconnect.assert_called_once()
                client.reconnect.assert_not_called()
                client.loop_start.assert_not_called()
                client.socket.assert_not_called()

    def test_unauthenticated_publish_uses_explicit_nonretained_command_settings(self):
        """Empty credentials remain optional while callers supply command QoS/retention explicitly."""
        client = self.client()
        with patch.object(shared_mqtt.mqtt, 'Client', return_value=client):
            self.assertTrue(publisher._publish_once({'host': 'broker'}, 'command', 'wake', qos=0, retain=False, timeout=20)[0])
        client.username_pw_set.assert_not_called()
        client.publish.assert_called_once_with('command', payload='wake', qos=0, retain=False)
        client.connect.assert_called_once_with('broker', 1883, keepalive=60)

    def test_refused_connection_never_publishes(self):
        """A broker rejecting login cannot be reported as a successful send."""
        client = self.client(reason=5)
        with patch.object(shared_mqtt.mqtt, 'Client', return_value=client):
            ok, message = publisher._publish_once({'host': 'broker'}, 'command', 'wake', qos=0, retain=False, timeout=20)
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
                    client.publish.return_value.rc = shared_mqtt.mqtt.MQTT_ERR_NO_CONN
                with patch.object(shared_mqtt.mqtt, 'Client', return_value=client):
                    self.assertFalse(publisher._publish_once({'host': 'broker'}, 'command', 'wake', qos=0, retain=False, timeout=20)[0])
                client.disconnect.assert_called_once()
                client.reconnect.assert_not_called()

    def test_timeout_closes_socket_before_disconnect_without_retry(self):
        """Unacknowledged commands cannot be flushed later by cleanup/reconnect."""
        client = self.client(acknowledged=False)
        events = []
        client.socket.return_value.shutdown.side_effect = lambda how: events.append('shutdown')
        client.socket.return_value.close.side_effect = lambda: events.append('close')
        client.disconnect.side_effect = lambda: events.append('disconnect')
        with patch.object(shared_mqtt.mqtt, 'Client', return_value=client), patch.object(shared_mqtt.time, 'monotonic', side_effect=[0, 0, 0, 2]):
            ok, message = publisher._publish_once({'host': 'broker'}, 'command', 'wake', qos=1, retain=False, timeout=1)
        self.assertFalse(ok)
        self.assertIn('delivery may be unknown', message)
        self.assertEqual(events, ['shutdown', 'close', 'disconnect'])
        client.publish.assert_called_once()
        client.reconnect.assert_not_called()

    def test_invalid_inputs_fail_before_connecting(self):
        """Invalid topics, QoS, and deadlines do not create a network client."""
        cases = [('', {}), ('a/+', {}), ('a/#', {}), ('valid', {'qos': 3}),
                 ('valid', {'timeout': 0}), ('valid', {'timeout': float('nan')})]
        with patch.object(shared_mqtt.mqtt, 'Client') as build:
            for topic, overrides in cases:
                options = {'qos': 0, 'retain': False, 'timeout': 20, **overrides}
                self.assertFalse(publisher._publish_once({'host': 'broker'}, topic, 'data', **options)[0])
            build.assert_not_called()

    def test_shared_long_running_client_api(self):
        """Both components can use one shared lifecycle/subscription/message/publish API."""
        client = Mock()
        client.connect.return_value = shared_mqtt.mqtt.MQTT_ERR_SUCCESS
        client.publish.return_value.rc = shared_mqtt.mqtt.MQTT_ERR_SUCCESS
        events = []
        with patch.object(shared_mqtt.mqtt, 'Client', return_value=client) as build:
            transport = shared_mqtt.MqttClient(
                {'host': 'broker', 'port': 1884, 'keepalive': 45, 'user': 'alice', 'pass': 'secret'},
                client_id='shared-test',
                will={'topic': 'status', 'payload': 'offline', 'qos': 1, 'retain': True},
                subscriptions=lambda: [('one/topic', 1), ('two/topic', 0)],
                on_connect=lambda: events.append(('connect',)),
                on_disconnect=lambda reason: events.append(('disconnect', reason)),
                on_message=lambda topic, payload, retain, qos: events.append(('message', topic, payload, retain, qos)),
            ).start(mode='thread')
        self.assertTrue(build.call_args.kwargs['clean_session'])
        if getattr(shared_mqtt.mqtt, 'CallbackAPIVersion', None) is not None:
            self.assertEqual(build.call_args.kwargs['callback_api_version'], shared_mqtt.mqtt.CallbackAPIVersion.VERSION2)
        else:
            self.assertNotIn('callback_api_version', build.call_args.kwargs)
        self.assertEqual(build.call_args.kwargs['protocol'], shared_mqtt.mqtt.MQTTv311)
        client.connect.assert_called_once_with('broker', 1884, keepalive=45)
        client.username_pw_set.assert_called_once_with('alice', 'secret')
        client.will_set.assert_called_once_with('status', payload='offline', qos=1, retain=True)
        client.on_connect(client, None, {}, 0, None)
        self.assertTrue(transport.connected)
        self.assertEqual(client.subscribe.call_count, 2)
        client.on_message(client, None, types.SimpleNamespace(topic='one/topic', payload=' æ '.encode(), retain=True, qos=1))
        self.assertEqual(events[-1], ('message', 'one/topic', 'æ', True, 1))
        self.assertTrue(transport.publish('state', 'online', qos=1, retain=True))
        client.on_disconnect(client, None, None, 4, None)
        self.assertFalse(transport.connected)
        self.assertEqual(events[0], ('connect',))
        self.assertEqual(events[-1][0], 'disconnect')

    def test_paho_v1_constructor_and_callback_shapes_are_supported(self):
        """Paho 1.x lacks CallbackAPIVersion and uses shorter callback signatures."""
        client = Mock()
        client.publish.return_value.rc = shared_mqtt.mqtt.MQTT_ERR_SUCCESS
        events = []
        with patch.object(shared_mqtt.mqtt, 'CallbackAPIVersion', None, create=True), \
             patch.object(shared_mqtt.mqtt, 'Client', return_value=client) as build:
            transport = shared_mqtt.MqttClient(
                {'host': 'broker'},
                subscriptions=[('legacy/topic', 1)],
                on_connect=lambda: events.append(('connect',)),
                on_disconnect=lambda reason: events.append(('disconnect', reason)),
            )
            built = transport._build_client()
        self.assertIs(built, client)
        self.assertNotIn('callback_api_version', build.call_args.kwargs)
        client.on_connect(client, None, {}, 0)
        self.assertTrue(transport.connected)
        client.subscribe.assert_called_once_with('legacy/topic', qos=1)
        client.on_disconnect(client, None, 7)
        self.assertFalse(transport.connected)
        self.assertEqual(events, [('connect',), ('disconnect', '7')])

    def test_paho_v1_one_shot_connect_callback_is_supported(self):
        """The disposable publisher also accepts Paho 1.x's four-argument connect callback."""
        client = Mock()
        client.connect.return_value = shared_mqtt.mqtt.MQTT_ERR_SUCCESS
        client.publish.return_value.rc = shared_mqtt.mqtt.MQTT_ERR_SUCCESS
        client.publish.return_value.is_published.return_value = True

        def connect_once(**kwargs):
            client.on_connect(client, None, {}, 0)
            return shared_mqtt.mqtt.MQTT_ERR_SUCCESS

        client.loop.side_effect = connect_once
        with patch.object(shared_mqtt.mqtt, 'CallbackAPIVersion', None, create=True), \
             patch.object(shared_mqtt.mqtt, 'Client', return_value=client) as build:
            ok, message = publisher._publish_once(
                {'host': 'broker'}, 'legacy/topic', 'payload', qos=0, retain=False, timeout=20
            )
        self.assertTrue(ok, message)
        self.assertNotIn('callback_api_version', build.call_args.kwargs)

    def test_parent_bounds_worker_and_keeps_credentials_off_argv(self):
        """The Paho child receives private input and retains the hard time limit."""
        result = Mock(returncode=0, stdout='[true, "published"]')
        with patch.object(shared_mqtt.subprocess, 'run', return_value=result) as run:
            self.assertEqual(publisher.publish_message({'host': 'broker', 'pass': 'secret'}, 'topic', 'payload', qos=0, retain=False), (True, 'published'))
        args, options = run.call_args
        self.assertEqual(args[0][0], sys.executable)
        self.assertNotIn('secret', ' '.join(args[0]))
        self.assertEqual(json.loads(options['input'])['settings']['pass'], 'secret')
        self.assertEqual(options['timeout'], 20)
        self.assertEqual(args[0][-1], '--request-stdin')
        with patch.object(shared_mqtt.subprocess, 'run', side_effect=subprocess.TimeoutExpired('publisher', 20)):
            ok, message = publisher.publish_message({'host': 'broker'}, 'topic', 'payload', qos=0, retain=False)
        self.assertFalse(ok)
        self.assertIn('timed out', message)

    def test_panel_actions_reuse_shared_publisher_and_current_json_envelope(self):
        """Panel remote actions use the shared publisher with the current JSON job envelope."""
        panel = load_panel()
        panel.MQTT_CONFIG.update(qos=2, retain=False)
        action_module = sys.modules[panel.ACTION_MANAGER.__class__.__module__]
        with patch.object(action_module, 'publish_message', return_value=(False, 'failed')) as publish:
            self.assertEqual(
                panel.ACTION_MANAGER.execute_remote_action(
                    'aoostar_wtr', 'run_watchtower', job_id='job-1', source='test-suite'
                ),
                (False, 'failed'),
            )
        payload = json.loads(publish.call_args.args[2])
        self.assertEqual(payload, {'command': 'run_watchtower', 'job_id': 'job-1', 'source': 'test-suite'})
        publish.assert_called_once_with(
            panel.MQTT_CONFIG, 'aoostar/control/power', publish.call_args.args[2], qos=2, retain=False
        )

    def test_cli_reads_credentials_from_config_and_payload_from_stdin(self):
        """The shell bridge preserves whitespace and never needs password flags."""
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.json'
            settings = {'host': 'broker', 'user': 'alice', 'pass': 'secret'}
            config.write_text(json.dumps({'mqtt': settings}))
            argv = ['mqtt.py', '--config', str(config), '--topic', 'state', '--qos', '2', '--retain', '--timeout', '3']
            with patch.object(shared_mqtt, 'publish_message', return_value=(True, 'sent')) as publish, patch.object(sys, 'argv', argv), patch.object(sys, 'stdin', io.StringIO('æ\n trailing ')), contextlib.redirect_stdout(io.StringIO()):
                rc = publisher.cli_main()
            self.assertEqual(rc, 0)
            publish.assert_called_once_with(settings, 'state', 'æ\n trailing ', qos=2, retain=True, timeout=3)
            argv = ['mqtt.py', '--config', str(config), '--topic', 'state']
            with patch.object(shared_mqtt, 'publish_message', return_value=(False, 'rejected')), patch.object(sys, 'argv', argv), patch.object(sys, 'stdin', io.StringIO('data')), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(publisher.cli_main(), 1)

    def test_cli_help_and_config_errors(self):
        """Help documents every flag and exits before input/network work."""
        help_output = io.StringIO()
        with patch.object(shared_mqtt, 'publish_message') as publish, contextlib.redirect_stdout(help_output), contextlib.redirect_stderr(io.StringIO()):
            with patch.object(sys, 'argv', ['mqtt.py', '--help']), self.assertRaises(SystemExit) as result:
                publisher.cli_main()
            self.assertEqual(result.exception.code, 0)
            help_text = help_output.getvalue()
            for expected in (
                '--config PATH', '--request-stdin', '--topic TOPIC', '--qos {0,1,2}',
                '--retain', '--timeout SECONDS', '--version', 'payload verbatim from stdin',
                'omit --retain for command/control messages',
            ):
                self.assertIn(expected, help_text)
            with patch.object(sys, 'argv', ['mqtt.py', '--config', '/nonexistent/homelab-config.json', '--topic', 'state']):
                self.assertEqual(publisher.cli_main(), 1)
            publish.assert_not_called()

    def test_shell_bridge_payload_and_failure_exit(self):
        """The real shell helper passes exact stdin and propagates Python failure."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control = root / 'homelab-control'
            modules = control / 'modules'
            configs = control / 'configs'
            modules.mkdir(parents=True)
            configs.mkdir()
            lib = modules / 'homelab_control_lib.sh'
            config = configs / 'config.json'
            shutil.copyfile(ROOT / 'homelab-control/modules/homelab_control_lib.sh', lib)
            shutil.copyfile(ROOT / 'homelab-control/configs/config.example.json', config)
            shim = root / 'python3'
            shim.write_text(f'''#!{sys.executable}
import json,os,sys
from pathlib import Path
if len(sys.argv)>1 and sys.argv[1].endswith('/shared_modules/mqtt.py'):
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
                result = subprocess.run(['bash', '-c', 'source "$1"; mqtt_pub "device/state" "$2"', 'check', str(lib), 'æ\n trailing '], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, rc, result.stderr)
                self.assertEqual(result.stdout, '')
                if rc:
                    self.assertIn('publish failed', result.stderr)
                record = json.loads(capture.read_text())
                self.assertEqual(record['payload'], 'æ\n trailing ')
                self.assertEqual(record['args'][1:], ['--config', str(config), '--topic', 'device/state', '--qos', '1', '--retain'])
            capture.unlink()
            result = subprocess.run(['bash', '-c', 'source "$1"; mqtt_pub "" "unused"', 'check', str(lib)], env=env, capture_output=True, text=True)
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
