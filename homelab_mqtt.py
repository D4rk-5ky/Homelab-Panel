#!/usr/bin/env python3
"""One-shot Paho MQTT publishing shared by the panel and shell status helpers."""
import argparse
import json
import math
import socket
import subprocess
from pathlib import Path
import sys
import time

import paho.mqtt.client as mqtt


def build_client():
    """Use a fresh clean session so failed commands cannot replay on reconnect."""
    options = {"clean_session": True, "protocol": mqtt.MQTTv311}
    if hasattr(mqtt, "CallbackAPIVersion"):
        options["callback_api_version"] = mqtt.CallbackAPIVersion.VERSION2
    return mqtt.Client(**options)


def _publish_once(settings: dict, topic: str, payload: str, *, qos: int = 0,
                    retain: bool = False, timeout: float = 20) -> tuple[bool, str]:
    """Publish once, await local send/QoS acknowledgement, then close the client.

    The manual network loop never reconnects or runs a background thread. The
    deadline covers connect/CONNACK/publication processing. The parent process
    also enforces a hard timeout, including DNS. Delivery may be uncertain after
    publication begins.
    """
    client = None
    published = False
    publish_started = False
    connection_result = None

    def on_connect(client, userdata, flags, reason_code, properties=None):
        """Capture broker acceptance for both Paho callback API versions."""
        nonlocal connection_result
        connection_result = reason_code

    try:
        timeout = float(timeout)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("MQTT timeout must be a positive finite number")
        if qos not in (0, 1, 2):
            raise ValueError("MQTT QoS must be 0, 1, or 2")
        if not topic or '+' in topic or '#' in topic:
            raise ValueError("MQTT publication requires a nonempty topic without wildcards")
        deadline = time.monotonic() + timeout
        client = build_client()
        # Paho 2 exposes this public setting; older Paho uses its socket default.
        if hasattr(client, "connect_timeout"):
            client.connect_timeout = min(5.0, timeout)
        if settings.get("user"):
            client.username_pw_set(settings["user"], settings.get("pass", ""))
        client.on_connect = on_connect
        rc = client.connect(settings["host"], int(settings.get("port", 1883)),
                            keepalive=60)
        if rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT connection failed: {mqtt.error_string(rc)}")

        def network_step():
            """Advance the current connection within the remaining deadline."""
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
            # On failure close the transport before disconnect can flush any
            # pending packet. This client is discarded and never reconnected.
            if not published:
                sock = client.socket()
                if sock is not None:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    sock.close()
            try:
                client.disconnect()
            except (OSError, RuntimeError):
                pass


def publish_message(settings: dict, topic: str, payload: str, *, qos: int = 0,
                    retain: bool = False, timeout: float = 20) -> tuple[bool, str]:
    """Run Paho in a disposable process to bound DNS/connect/send by 20s default.

    This preserves the panel's former process timeout. Credentials and payload
    travel through stdin rather than process arguments; the child cannot keep
    sending after subprocess.run kills and waits for a timed-out operation.
    """
    try:
        timeout = float(timeout)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("MQTT timeout must be a positive finite number")
        request = {"settings": settings, "topic": topic, "payload": payload,
                   "qos": qos, "retain": retain, "timeout": timeout}
        result = subprocess.run(
            [sys.executable, "-B", str(Path(__file__).resolve()), "--request-stdin"],
            input=json.dumps(request, ensure_ascii=False), capture_output=True,
            text=True, timeout=timeout, check=False,
        )
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


def main(argv=None) -> int:
    """Publish stdin using an agent config without exposing credentials in argv."""
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--config", help="Path to the agent JSON config; reads its mqtt section")
    source.add_argument("--request-stdin", action="store_true", help="Internal worker mode: read a JSON request from stdin and return JSON")
    parser.add_argument("--topic", help="Destination topic (required with --config); payload is read verbatim from stdin")
    parser.add_argument("--qos", type=int, choices=(0, 1, 2), default=1, help="MQTT delivery QoS (default: 1)")
    parser.add_argument("--retain", action="store_true", help="Retain telemetry at the broker; never use for commands")
    parser.add_argument("--timeout", type=float, default=20, help="Total publication timeout in seconds (default: 20; must be positive)")
    args = parser.parse_args(argv)
    if args.request_stdin:
        # Only the bounded parent invokes this mode in normal operation.
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
        ok, message = publish_message(settings, args.topic, sys.stdin.read(),
                                      qos=args.qos, retain=args.retain, timeout=args.timeout)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"MQTT configuration/input error: {exc}", file=sys.stderr)
        return 1
    print(message, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
