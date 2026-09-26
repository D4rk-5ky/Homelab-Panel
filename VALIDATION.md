# Homelab Panel 0.0.19 — validation

## Result and scope

Created **0.0.19** from the packaged **0.0.18** baseline. This release consolidates genuinely shared MQTT transport code into one root `shared_modules/mqtt.py` module without moving component-specific application logic across component boundaries.

The intended dependency direction is now:

- `homelab-panel` → `shared_modules.mqtt` for generic MQTT transport;
- `homelab-control` → `shared_modules.mqtt` for generic MQTT transport;
- neither component imports modules from the other component.

`shared_modules/` contains only MQTT in this release because no other cross-component category was large/duplicated enough to justify another shared module.

## Shared MQTT consolidation

`shared_modules/mqtt.py` now owns the common MQTT implementation:

- Paho MQTT v3.1.1 client construction and Callback API compatibility;
- optional reconnect delay policy;
- username/password authentication;
- Last Will configuration;
- caller-supplied connect/disconnect/message callbacks;
- blocking, threaded, asynchronous-threaded, and connect-only loop modes;
- direct publish return handling and optional publish wait;
- UTF-8 MQTT payload decoding;
- related status-topic derivation from `/last_message`;
- bounded disposable one-shot publication with no reconnect/retry;
- one-shot CLI argument/config/stdin handling.

The bounded worker launches `shared_modules/mqtt.py` itself, so there is one transport implementation. Root `homelab_mqtt.py` is now only a 10-line executable/backward-import adapter.

Component-specific code remains component-specific:

- `homelab-panel/modules/panel_mqtt.py` still owns panel receive cache, subscriptions, diagnostics, HA birth handling, panel-control dispatch and panel event callbacks;
- `homelab-control/homelab_control_command_listener.py` still owns command validation, queueing, scripts and jobs;
- `homelab-control/homelab_control_status_indicator.py` still owns local status/history/uptime/boot state publication;
- HA discovery, web routes, WoL/action safety and persistence were not moved into `shared_modules`.

## Independent execution/path checks

Temporary active configs copied from the tracked examples were used only during these checks and removed afterwards. Dependency stubs were used so no broker/device was contacted.

From `/tmp` rather than the project directory:

- `homelab-panel/app.py` successfully imported its component-local configs/modules and root `shared_modules.mqtt`;
- `homelab_control_command_listener.py` successfully imported its component-local config and root shared MQTT module;
- `homelab_control_status_indicator.py` successfully imported its component-local config and root shared MQTT module;
- the three programs do not import each other's component modules;
- `homelab_mqtt.py --help` ran from outside the project directory through the shared CLI implementation.

This means the programs remain independent processes as long as the project layout keeps the root `shared_modules/` directory available. A component may run without the other component running.

## Static/configuration checks

- All **15 Python files** parse successfully with Python AST compilation without requiring imports.
- All **6 shell scripts/modules** pass `bash -n`.
- All **4 embedded Python heredocs** in `homelab-control/modules/homelab_control_lib.sh` compile.
- `homelab-control/configs/config.example.json` parses as JSON.
- All **4 Jinja templates** parse successfully.
- All **3 systemd service examples** retain `[Unit]`, `[Service]`, and `ExecStart=`.
- Production Paho usage was searched: only `shared_modules/mqtt.py` imports `paho.mqtt.client` or constructs `mqtt.Client`; component production code no longer does so directly.
- `commented_code_map.md` covers all **201 production Python/shell function definitions** in this release, including nested functions.
- No configuration key/value was added or removed; the tracked config examples are unchanged from 0.0.18.

## MQTT regression checks

The real installed Flask/Paho test suite cannot run in this sandbox because both Flask and `paho-mqtt` are absent. The normal command was attempted:

```bash
python3 -B -m unittest discover -s tests -v
```

Discovery stops with `ModuleNotFoundError: No module named 'paho'` before the tests execute.

Using an isolated Paho compatibility stub, **10 focused publisher/CLI regression tests passed**:

- configured auth/port/payload/QoS/retain preservation;
- unauthenticated default non-retained command publication;
- broker rejection handling;
- connect and publish failures;
- timeout socket shutdown before disconnect with no retry;
- invalid topic/QoS/timeout rejection before connection;
- modern/legacy Paho constructor compatibility;
- parent process timeout and credentials kept off argv;
- CLI config/stdin handling;
- CLI help/config-error behavior.

The real shell bridge regression test also passed separately under the isolated interpreter shim. It verified exact stdin payload transfer, config path/QoS/retain arguments, success/failure exit propagation, and empty-topic no-op behavior.

A separate shared-MQTT stub check verified client ID/callback API/auth/Last Will/reconnect setup, async-thread connection mode, payload decoding, and related-topic derivation.

These isolated checks verify refactor wiring and behavior but do not replace a real broker/Paho integration test.

## Behavior/safety preservation

The refactor does not intentionally change:

- MQTT topics or payload formats;
- command QoS/retain configuration;
- Home Assistant discovery/entity IDs;
- remote/local command allow-lists;
- browser routes or button labels/confirmations;
- `$TITLE` expansion;
- Wake-on-LAN behavior;
- shutdown/reboot confirmation semantics;
- status/history/job persistence formats;
- component-local config locations;
- local script path-containment/executable checks;
- retained panel-control rejection;
- one-shot command no-reconnect/no-automatic-retry behavior.

## Baseline manifest comparison

The 0.0.18 baseline contains **33 files**. Before packaging, 0.0.19 contains **35 source files**.

Added:

- `shared_modules/__init__.py`
- `shared_modules/mqtt.py`

No baseline file path was removed.

Expected modified baseline paths:

- `README.md`
- `VALIDATION.md`
- `VERSION`
- `VERSIONING.md`
- `commented_code_map.md`
- `homelab-control/homelab_control_command_listener.py`
- `homelab-control/homelab_control_status_indicator.py`
- `homelab-panel/app.py`
- `homelab-panel/modules/panel_mqtt.py`
- `homelab_mqtt.py`
- `tests/test_mqtt_publish.py`

All three tracked configuration examples remain byte-for-byte unchanged from 0.0.18.

## Packaging requirements

Before packaging, generated `__pycache__`/`.pyc` files and temporary active configs are removed. The final ZIP must be checked for:

- exactly the expected **35** source files;
- no duplicate ZIP entries;
- successful archive integrity testing;
- extracted-file SHA-256 hashes matching the release tree;
- executable/non-executable permissions matching the release tree;
- no active local config files;
- no `__pycache__`, `.pyc`, `.pyo`, build cache, temporary files, runtime logs, or runtime state.

## Limits

- Full Flask/Paho unit tests and real MQTT wire tests require the missing runtime dependencies and were not available in this sandbox.
- No production MQTT broker, Home Assistant instance, remote homelab device, Wake-on-LAN target, shutdown/reboot operation, or privileged systemd action was contacted/executed.
