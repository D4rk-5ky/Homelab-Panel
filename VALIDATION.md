# Homelab Panel 0.0.20 — validation

## Result and scope

Created **0.0.20** from the packaged **0.0.19** baseline after auditing every production MQTT call path in the panel, Homelab Control agents, shell bridge, and shared publisher.

The objective was not merely to move MQTT code. Generic MQTT transport now has one implementation/API in root `shared_modules/mqtt.py`, while each component keeps only behavior that belongs to that component.

Dependency direction is deliberately one-way:

- `homelab-panel` → `shared_modules.mqtt`;
- `homelab-control` → `shared_modules.mqtt`;
- `homelab-panel` does not import Homelab Control modules;
- `homelab-control` does not import panel modules.

## MQTT consolidation

`shared_modules/mqtt.py` is now the only generic MQTT implementation and the only production file importing Paho. Its shared API owns:

- Paho MQTT 3.1.1 client construction;
- Paho callback-API compatibility;
- username/password authentication;
- optional Last Will configuration;
- reconnect-delay policy;
- static or callable subscription lists;
- connect and network-loop modes;
- normalized decoded message callbacks as `(topic, payload, retain, qos)`;
- long-running publication return handling;
- clean stop/disconnect behavior;
- related sibling-topic derivation;
- bounded one-shot publication with no automatic reconnect/retry;
- one-shot CLI config/stdin/flag handling.

Both long-running Homelab Control programs and the panel use the same `MqttClient(...).start()` / `.publish()` interface.

`homelab-panel/modules/panel_mqtt.py` remains because it contains panel-specific behavior rather than a second transport implementation. It owns the panel receive cache, panel topic selection, diagnostics, retained panel-control rejection, HA birth handling, status/job/boot routing, and panel connect/disconnect event hooks. It does not construct a Paho client.

The root `homelab_mqtt.py` compatibility wrapper from 0.0.19 was removed. Shell and standalone one-shot callers now execute `shared_modules/mqtt.py` directly, so there is no second MQTT executable implementation surface.

## Codebase reduction

Production Python/shell source was counted with the same method on both releases, excluding tests:

- 0.0.19: **4,084 lines**;
- 0.0.20: **4,018 lines**;
- net reduction: **66 lines**.

The 0.0.19 project had 35 tracked release files. 0.0.20 has 34; the only intentionally removed path is `homelab_mqtt.py`. No replacement wrapper was added.

## Behavior and safety preserved

The refactor does not intentionally change:

- MQTT broker configuration keys;
- MQTT topic names or payload formats;
- configured QoS/retain behavior;
- bounded one-shot command timeout/no-retry semantics;
- command allow-lists;
- local script path/executable guards;
- Home Assistant discovery IDs/topics;
- web routes;
- `$TITLE` confirmation behavior;
- power/WoL behavior;
- job/state/history formats;
- component-local config paths.

All three tracked config examples are byte-identical to 0.0.19:

- `homelab-panel/configs/config.example.py`;
- `homelab-panel/configs/devices.example.py`;
- `homelab-control/configs/config.example.json`.

## Static and structure checks

Passed:

- all **14 Python files** parse successfully with Python AST compilation;
- all **6 shell files** pass `bash -n`;
- all **4 embedded Python heredocs** in the Homelab Control shell module compile;
- the Homelab Control JSON example parses successfully;
- all **4 Jinja templates** parse successfully;
- all **3 systemd unit examples** retain `[Unit]`, `[Service]`, and `ExecStart=` structure;
- production Paho search finds only `shared_modules/mqtt.py` importing `paho.mqtt.client` / constructing `mqtt.Client`;
- all **210 production Python/shell function definitions** are represented in `commented_code_map.md`;
- all **249 Python/shell function definitions including tests** are represented in `commented_code_map.md`.

## Shared MQTT regression tests

The isolated Paho compatibility fixture was used only for offline tests; it is not part of the release.

The focused shared publisher/client/CLI/shell suite passed **12/12**:

- configured auth/port/payload/QoS/retain preservation;
- unauthenticated default non-retained publication;
- refused-connection handling without publish;
- connect and publish failure propagation;
- timeout socket close/disconnect behavior with no retry;
- invalid input rejection before network creation;
- modern and legacy Paho constructor compatibility;
- shared long-running `MqttClient` auth/LWT/subscription/message/publish/disconnect API;
- bounded parent worker and credentials kept off argv;
- CLI config and exact stdin payload handling;
- CLI help/config error handling;
- real shell bridge exact-payload/failure propagation.

Result:

```text
Ran 12 tests in 30.817s
OK
```

The shared CLI `--help` was also executed from `/tmp` rather than the repository working directory using the isolated Paho compatibility fixture.

## Independent component import/path checks

Temporary active configs copied from the tracked examples were created only for this check and removed immediately afterwards. Dependency stubs prevented broker/device access.

From `/tmp`, these imported successfully:

- `homelab-control/homelab_control_command_listener.py`;
- `homelab-control/homelab_control_status_indicator.py`;
- `homelab-panel/modules/panel_mqtt.py`.

This verifies that the shared root package can be resolved independently of the shell working directory and that neither component needs to import the other component's application modules.

## Full test-suite limitation

The normal command was attempted without stubs:

```bash
python3 -B -m unittest discover -s tests -v
```

It cannot execute in this sandbox because the real `paho-mqtt` package is not installed; discovery stops while importing both test modules with `ModuleNotFoundError: No module named 'paho'`. Flask is also not installed in this environment, so the real Flask-based panel tests cannot be rerun here either.

Therefore the isolated 12-test MQTT regression result is reported separately and is **not** represented as a full real-dependency suite pass.

## Not exercised against live infrastructure

No production MQTT broker, Home Assistant instance, remote Homelab Control host, Wake-on-LAN target, shutdown/reboot action, or live systemd service was contacted or changed during validation.

## Packaging checks

The final archive was checked for:

- expected 0.0.19 → 0.0.20 manifest changes;
- no unexpected baseline file removal;
- no active private config files;
- no `__pycache__`, `.pyc`, `.pyo`, runtime state/logs, build cache, or temporary files;
- no duplicate ZIP member names;
- ZIP integrity;
- extracted-file SHA-256 equality with the release tree;
- Unix permission equality with the release tree.

The final archive SHA-256 is recorded in the release response after packaging.
