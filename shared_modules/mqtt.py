#!/usr/bin/env python3
"""Generic MQTT transport shared by Homelab Panel and Homelab Control."""

import argparse
import json
import math
from pathlib import Path
import socket
import subprocess
import sys
import time

import paho.mqtt.client as mqtt


class MqttClient:
    """Common long-running MQTT client; components only supply callbacks/topics."""

    def __init__(self, settings: dict, *, client_id: str = "", will: dict | None = None,
                 subscriptions=None, on_connect=None, on_disconnect=None, on_message=None,
                 reconnect_min: int | None = None, reconnect_max: int | None = None):
        self.settings, self.client_id, self.will = settings, client_id, will
        self.subscriptions = subscriptions
        self.on_connect, self.on_disconnect, self.on_message = on_connect, on_disconnect, on_message
        self.reconnect_min, self.reconnect_max = reconnect_min, reconnect_max
        self.client = None
        self.connected = False
        self.loop_mode = ""

    def _build_client(self):
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
            clean_session=True,
            protocol=mqtt.MQTTv311,
        )
        if self.reconnect_min is not None or self.reconnect_max is not None:
            client.reconnect_delay_set(min_delay=1 if self.reconnect_min is None else int(self.reconnect_min),
                                       max_delay=30 if self.reconnect_max is None else int(self.reconnect_max))
        user = str(self.settings.get("user", ""))
        if user:
            client.username_pw_set(user, str(self.settings.get("pass", "")))
        if self.will and str(self.will.get("topic", "")).strip():
            client.will_set(str(self.will["topic"]).strip(), payload=self.will.get("payload", "offline"),
                            qos=int(self.will.get("qos", 1)), retain=bool(self.will.get("retain", True)))
        client.on_connect, client.on_disconnect = self._handle_connect, self._handle_disconnect
        if self.on_message is not None:
            client.on_message = self._handle_message
        return client

    def _subscription_items(self) -> list[tuple[str, int]]:
        values = self.subscriptions() if callable(self.subscriptions) else self.subscriptions
        topics = {}
        for topic, qos in values or ():
            topic = str(topic).strip()
            if topic:
                topics[topic] = int(qos)
        return sorted(topics.items())

    def _handle_connect(self, client, userdata, flags, reason_code, properties):
        self.client = client
        self.connected = reason_code == 0
        if not self.connected:
            if self.on_disconnect:
                self.on_disconnect(str(reason_code))
            return
        for topic, qos in self._subscription_items():
            client.subscribe(topic, qos=qos)
        if self.on_connect:
            self.on_connect()

    def _handle_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        self.connected = False
        if self.on_disconnect:
            self.on_disconnect(str(reason_code))

    def _handle_message(self, client, userdata, message):
        if self.on_message:
            self.on_message(str(message.topic), message.payload.decode("utf-8", errors="replace").strip(),
                            bool(getattr(message, "retain", False)), int(getattr(message, "qos", 0)))

    def start(self, *, mode: str):
        if self.client is None:
            self.client = self._build_client()
        self.loop_mode = mode
        host, port = str(self.settings["host"]), int(self.settings.get("port", 1883))
        keepalive = int(self.settings.get("keepalive", 60))
        if mode == "async_thread":
            self.client.connect_async(host, port, keepalive=keepalive)
            self.client.loop_start()
        else:
            self.client.connect(host, port, keepalive=keepalive)
            if mode == "forever":
                self.client.loop_forever()
            elif mode == "thread":
                self.client.loop_start()
            else:
                raise ValueError(f"Unsupported MQTT connection mode: {mode}")
        return self

    def publish(self, topic: str, payload: str, *, qos: int, retain: bool,
                wait_timeout: float | None = None) -> bool:
        if self.client is None or not self.connected or not topic:
            return False
        info = self.client.publish(topic, payload=payload, qos=qos, retain=retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            return False
        if wait_timeout is not None:
            try:
                info.wait_for_publish(timeout=wait_timeout)
            except Exception:
                return False
        return True

    def stop(self) -> None:
        if self.client is None:
            return
        if self.loop_mode in {"thread", "async_thread"}:
            try:
                self.client.loop_stop()
            except Exception:
                pass
        try:
            self.client.disconnect()
        except (OSError, RuntimeError):
            pass


def _publish_once(settings: dict, topic: str, payload: str, *, qos: int,
                  retain: bool, timeout: float) -> tuple[bool, str]:
    """Publish once with no reconnect/retry; close hard on uncertain failure."""
    client = None
    published = publish_started = False
    connection_result = None

    def on_connect(client, userdata, flags, reason_code, properties):
        nonlocal connection_result
        connection_result = reason_code

    try:
        timeout = float(timeout)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("MQTT timeout must be a positive finite number")
        if qos not in (0, 1, 2):
            raise ValueError("MQTT QoS must be 0, 1, or 2")
        if not topic or "+" in topic or "#" in topic:
            raise ValueError("MQTT publication requires a nonempty topic without wildcards")
        deadline = time.monotonic() + timeout
        client = MqttClient(settings)._build_client()
        client.on_connect = on_connect
        client.connect_timeout = min(5.0, timeout)
        rc = client.connect(settings["host"], int(settings.get("port", 1883)), keepalive=60)
        if rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT connection failed: {mqtt.error_string(rc)}")

        def network_step():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("MQTT operation timed out")
            rc = client.loop(timeout=min(0.2, remaining))
            if rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"MQTT connection failed: {mqtt.error_string(rc)}")

        while connection_result is None:
            network_step()
        if connection_result != 0:
            raise RuntimeError(f"MQTT broker rejected connection: {connection_result}")
        if time.monotonic() >= deadline:
            raise TimeoutError("MQTT operation timed out before publication")
        publish_started = True
        info = client.publish(topic, payload=payload, qos=qos, retain=retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT publication failed: {mqtt.error_string(info.rc)}")
        while not info.is_published():
            network_step()
        published = True
        return True, "MQTT message published"
    except Exception as exc:
        detail = f"MQTT publication failed: {exc}"
        if publish_started:
            detail += "; delivery may be unknown; no automatic retry"
        return False, detail
    finally:
        if client is not None:
            if not published and (sock := client.socket()) is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()
            try:
                client.disconnect()
            except (OSError, RuntimeError):
                pass


def publish_message(settings: dict, topic: str, payload: str, *, qos: int,
                    retain: bool, timeout: float = 20) -> tuple[bool, str]:
    """Run the disposable publisher worker under a hard parent-process timeout."""
    try:
        timeout = float(timeout)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("MQTT timeout must be a positive finite number")
        request = {"settings": settings, "topic": topic, "payload": payload,
                   "qos": qos, "retain": retain, "timeout": timeout}
        result = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--request-stdin"],
                                input=json.dumps(request, ensure_ascii=False), capture_output=True,
                                text=True, timeout=timeout, check=False)
        if result.returncode:
            return False, f"MQTT publisher exited with status {result.returncode}"
        response = json.loads(result.stdout)
        if (not isinstance(response, list) or len(response) != 2
                or not isinstance(response[0], bool) or not isinstance(response[1], str)):
            raise ValueError("Invalid response from MQTT publisher")
        return response[0], response[1]
    except subprocess.TimeoutExpired:
        return False, "MQTT publication timed out; delivery may be unknown; no automatic retry"
    except Exception as exc:
        return False, f"MQTT publication failed: {exc}"


def cli_main() -> int:
    """Run the standalone one-shot MQTT CLI used by shell/service callers."""
    parser = argparse.ArgumentParser(description="One-shot MQTT publisher")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--config", help="Path to agent JSON config; reads its mqtt section")
    source.add_argument("--request-stdin", action="store_true",
                        help="Internal worker mode: read a JSON request from stdin and return JSON")
    parser.add_argument("--topic", help="Destination topic (required with --config); payload is read verbatim from stdin")
    parser.add_argument("--qos", type=int, choices=(0, 1, 2), default=1, help="MQTT delivery QoS (default: 1)")
    parser.add_argument("--retain", action="store_true", help="Retain telemetry at the broker; never use for commands")
    parser.add_argument("--timeout", type=float, default=20,
                        help="Total publication timeout in seconds (default: 20; must be positive)")
    args = parser.parse_args()
    if args.request_stdin:
        try:
            response = _publish_once(**json.load(sys.stdin))
        except (ValueError, TypeError) as exc:
            response = (False, f"Invalid MQTT worker request: {exc}")
        print(json.dumps(response, ensure_ascii=False))
        return 0
    if not args.topic:
        parser.error("--topic is required with --config")
    try:
        with open(args.config, encoding="utf-8") as handle:
            settings = json.load(handle)["mqtt"]
        if not isinstance(settings, dict):
            raise ValueError("Config mqtt section must be an object")
        ok, message = publish_message(settings, args.topic, sys.stdin.read(), qos=args.qos,
                                      retain=args.retain, timeout=args.timeout)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"MQTT configuration/input error: {exc}", file=sys.stderr)
        return 1
    print(message, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(cli_main())
