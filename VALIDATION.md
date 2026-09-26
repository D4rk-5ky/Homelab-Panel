# Homelab Panel 0.0.14 — validation

## Result and scope

Created **0.0.14** from the preceding **0.0.13** release. All **26 baseline project paths** remain; **2 files added**, **9 updated**, and **17 unchanged**. The same 26 paths from the original uploaded **0.0.12** archive are also preserved. The final ZIP contains **28 files** under `Homelab-Panel-0.0.14/`.

Baseline 0.0.13 ZIP SHA-256: `c196c972a8d7e47b0206ccd152211f36257fd1f7fb6499022b92ea32f0a0a637`.

Original uploaded 0.0.12 ZIP SHA-256: `a47f923f10850a02b09a5b01e3ee451d44f3a14a8357e02cf65fff26525e426f`.

## What changed

- The panel and Bash agent status library now share `homelab_mqtt.py` for Paho publishing. No runtime source invokes `mosquitto_pub` or `mosquitto_sub`; all subscriptions already used Paho.
- Panel publications keep configured host/port/authentication, topic/payload, QoS/retention, `(ok, message)` results, and the 20-second process timeout.
- Shell telemetry keeps QoS 1, retained messages, exact stdin payloads, empty-topic no-op, quiet success, and failure propagation. Its MQTT credentials are read by Python directly from the existing config. Telemetry now also has a 20-second timeout.
- Each publication uses a disposable Python process and Paho client. Credentials are sent on stdin rather than argv. The parent kills and waits for a timed-out child, including during DNS/connect stalls. Clients never reconnect, and failure after sending reports that delivery may be unknown.
- Persistent status/subscription clients remain unchanged. One-shot publication uses MQTT 3.1.1 and a fixed 60-second keepalive. No new configuration fields are required.
- README documents installation without Mosquitto client tools, the publishing CLI and every flag, exit codes, timeout/completion semantics, and remaining broker requirements. Updated code map, configuration comments, version history, tests, and this report; retained the supplied disclaimer.

## Verification

Environment: Darwin 24.6.0, Python 3.13.15, Flask 3.1.3, Paho MQTT 2.1.0, Jinja 3.1.6.

### Regression and protocol checks

**27 tests passed** with no skipped tests:

- The 12 existing panel/HA tests still pass, covering discovery, local naming, shared routing, access gates, retained panel-command rejection, path containment, and rendering all four pages.
- Publisher unit tests cover exact config/payload/QoS/retention forwarding, unauthenticated defaults, rejected connections, socket/Paho errors, invalid inputs, timeout cleanup, callback API compatibility, and private stdin requests with bounded subprocesses.
- Panel delegation and helper CLI tests cover return values, JSON config, verbatim stdin, flags, safe help, and nonzero failures.
- The real Bash library runs against a transport shim to verify its Python command arguments, payload bytes, empty-topic behavior, suppressed success output, preserved error output, and propagated exit status. This never invokes a power script.
- Actual Paho network code and the production child-process path are exercised against a minimal MQTT peer bound only to `127.0.0.1` on an ephemeral port. Tests check authentication and clean-session flags, topic/UTF-8 payload bytes, retained flags, QoS 0 send, QoS 1 PUBACK, and QoS 2 PUBREC/PUBREL/PUBCOMP. Refused CONNACK sends no command; withheld PUBACK causes failure and transport closure without retry.
- Localhost socket tests required execution outside the default sandbox because it blocks listener sockets. They then passed; no external broker or homelab host was contacted.

### Static and CLI checks

- All **8 Python source/config/test files** compile in memory.
- All **6 shell files** pass `bash -n`; all **4 embedded Python heredocs** compile.
- The remote JSON example and all **4 Jinja templates** parse.
- All **3 systemd examples** pass structural section/directive checks; full systemd validation is unavailable on this macOS host.
- All **209 Python/shell function definitions** have code-map entries, including nested/test helpers; existing browser callbacks remain documented.
- Configuration examples cover existing options; README covers all example option names and every new publisher flag. Panel config imports match the example. Config values/parsed code are unchanged; edits to the panel config example are comments only.
- Actual `homelab_mqtt.py --help` succeeds without network activity. Invalid QoS exits with argument-error status 2.
- AST comparison shows `mqtt_publish()` is the only changed existing panel function. The app also imports the shared module from the project root. Remote listener/status Python files, service files, templates, device configuration, and all power action scripts are byte-identical to 0.0.13.
- Existing version history and both disclaimer sections are preserved.

### ZIP checks

- Compared final relative paths against both the original uploaded archive and 0.0.13: no original files removed or renamed; both new source/test files included.
- Verified ZIP integrity, unique names, per-file content hashes, and permissions against the final tree; original executable flags are preserved.
- Excluded Python caches/bytecode, build caches, temporary files, runtime data/logs, active configs, and dependency environments. No forbidden files are present.
- The accompanying manifest includes original-upload, baseline, and release SHA-256 values per file; the checksum file identifies the ZIP.

## Reproduce

From the extracted project root, using Python 3.10+ with Flask and Paho installed:

```bash
python3 -B -m unittest discover -s tests -v
python3 homelab_mqtt.py --help
```

The full test suite requires permission to bind temporary localhost sockets. It does not use the configured production broker. `-B` disables import-time bytecode, `-m unittest` runs the test runner, `discover` locates tests, `-s tests` selects their directory, and `-v` prints individual results.

## Limits

- No production MQTT broker, ACL policy, Home Assistant registry, or real device integration was exercised. The localhost peer covers specific MQTT exchanges rather than a complete broker implementation.
- No real Wake-on-LAN, shutdown/reboot/cancellation, privileged sudo/root operation, or user-provided job was executed.
- Linux `/proc` boot/uptime behavior and service startup/restart remain untested; `systemd-analyze` is unavailable.
- Browser layout/keyboard scrolling was not tested interactively; templates render in the existing Flask tests and their source is unchanged.
- The older Paho constructor/callback path is checked with a test double; real wire tests used the installed Paho 2.1.0.
- Existing remote-agent retained-command behavior and power-confirmation semantics are unchanged. Transport completion still does not prove that a remote action ran; a missing acknowledgement can leave delivery uncertain.

## Changes against 0.0.13

| Project-relative path | Content status |
|---|---|
| `.gitignore` | Unchanged |
| `README.md` | Updated |
| `VALIDATION.md` | Updated |
| `VERSION` | Updated |
| `VERSIONING.md` | Updated |
| `commented_code_map.md` | Updated |
| `homelab-control/config.example.json` | Unchanged |
| `homelab-control/homelab-control-command-listener.service` | Unchanged |
| `homelab-control/homelab-control-status-indicator.service` | Unchanged |
| `homelab-control/homelab_control_command_listener.py` | Unchanged |
| `homelab-control/homelab_control_lib.sh` | Updated |
| `homelab-control/homelab_control_status_indicator.py` | Unchanged |
| `homelab-panel/app.py` | Updated |
| `homelab-panel/config.example.py` | Updated |
| `homelab-panel/devices.example.py` | Unchanged |
| `homelab-panel/homelab-controll.service` | Unchanged |
| `homelab-panel/templates/history.html` | Unchanged |
| `homelab-panel/templates/index.html` | Unchanged |
| `homelab-panel/templates/login.html` | Unchanged |
| `homelab-panel/templates/mqtt_diagnostics.html` | Unchanged |
| `homelab_mqtt.py` | Added |
| `scripts/homelab_action_common.sh` | Unchanged |
| `scripts/reboot_cancel.sh` | Unchanged |
| `scripts/reboot_delay.sh` | Unchanged |
| `scripts/shutdown_cancel.sh` | Unchanged |
| `scripts/shutdown_delay.sh` | Unchanged |
| `tests/test_home_assistant.py` | Updated |
| `tests/test_mqtt_publish.py` | Added |
