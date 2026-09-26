# Homelab Panel 0.0.18 — validation

## Result and scope

Created **0.0.18** from the packaged **0.0.17** baseline. This release reorganizes component-local configuration and implementation modules without changing configured MQTT topics/payloads, Home Assistant entity IDs, command allow-lists, button labels/confirmations, runtime state locations, or power-action semantics.

## Structure changes

- Panel configuration moved to `homelab-panel/configs/`:
  - tracked `config.example.py` and `devices.example.py`;
  - active `config.py` and `devices.py` are expected there and remain excluded from clean releases;
  - `configs/__init__.py` makes the directory an explicit Python package.
- Panel implementation modules moved unchanged to `homelab-panel/modules/`:
  - `panel_actions.py`;
  - `panel_home_assistant.py`;
  - `panel_mqtt.py`;
  - `modules/__init__.py` makes the directory an explicit package.
- Remote-agent configuration moved to `homelab-control/configs/`; both Python entry points load `configs/config.json` relative to their own location.
- `homelab_control_lib.sh` moved to `homelab-control/modules/` and now derives the agent root from its parent directory before resolving `state/`, `logs/`, and `configs/config.json`.
- `scripts/homelab_action_common.sh` now locates the remote module and config under those new directories.
- Project-root `homelab_mqtt.py` intentionally remains at the root because it is both an independently executable CLI and a shared one-shot publisher used by multiple components.

## Independent execution/path-resolution checks

Temporary active configs were copied from the examples only for these checks and removed afterwards. No production broker/device was contacted.

From `/tmp` rather than the project directory, isolated dependency stubs were used to import/start the path-resolution portions of the applications:

- `homelab-panel/app.py` successfully resolved:
  - `homelab-panel/configs/config.py`;
  - `homelab-panel/configs/devices.py`;
  - `modules.panel_actions`, `modules.panel_home_assistant`, and `modules.panel_mqtt`.
- `homelab_control_command_listener.py` resolved `homelab-control/configs/config.json`.
- `homelab_control_status_indicator.py` resolved `homelab-control/configs/config.json`.
- Sourcing `homelab-control/modules/homelab_control_lib.sh` from `/tmp` resolved its agent root and new config path correctly.
- Sourcing `scripts/homelab_action_common.sh` from `/tmp` resolved the new remote module/config paths correctly.

These checks verify that the entry points do not depend on the current shell working directory and remain independently runnable. They do not replace real Flask/Paho integration tests.

## Configuration/module preservation checks

- The three moved panel implementation modules are byte-for-byte identical to their 0.0.17 versions; only their paths changed.
- `homelab-control/configs/config.example.json` is byte-for-byte identical to the 0.0.17 remote JSON example.
- The two moved Python configuration examples have identical Python ASTs to 0.0.17; only path comments were updated. No configuration key/value behavior changed.
- `.gitignore` now excludes only the active files at the new config paths while retaining examples/package markers.

## Static/configuration checks

- All **13 Python files** compile in memory without generating bytecode.
- All **6 shell scripts/modules** pass `bash -n`.
- All **4 embedded Python heredocs** in `homelab-control/modules/homelab_control_lib.sh` compile.
- `homelab-control/configs/config.example.json` parses as JSON.
- All **4 Jinja templates** parse successfully with the available Jinja runtime.
- All **3 systemd service examples** retain `[Unit]`, `[Service]`, and `ExecStart=`.
- `commented_code_map.md` covers all **240 Python/shell function definitions** in the release.
- `homelab_mqtt.py --help` was executed successfully with an isolated Paho import stub. It still exposes `--config`, `--request-stdin`, `--topic`, `--qos`, `--retain`, `--timeout`, and standard `-h/--help` without contacting a broker.

## Regression-test scope

The normal command was attempted:

```bash
python3 -B -m unittest discover -s tests -v
```

Test discovery cannot import either test module because `paho-mqtt` is not installed in this sandbox (`ModuleNotFoundError: No module named 'paho'`). Flask is also not installed. Therefore the full real-dependency regression/wire suite could not be rerun here.

The test source was updated for the new layout:

- `load_panel()` loads the examples as `configs.config` and `configs.devices` from `homelab-panel/configs/`;
- the shell bridge fixture mirrors `homelab-control/configs/` and `homelab-control/modules/`.

All test files compile successfully. No production MQTT broker, Home Assistant instance, Wake-on-LAN target, shutdown/reboot operation, or privileged systemd action was used.

## Baseline manifest comparison

The 0.0.17 baseline contains **31 files**. The 0.0.18 source tree contains **33 files**.

Seven old paths were intentionally removed because those files were relocated:

- `homelab-control/config.example.json`
- `homelab-control/homelab_control_lib.sh`
- `homelab-panel/config.example.py`
- `homelab-panel/devices.example.py`
- `homelab-panel/panel_actions.py`
- `homelab-panel/panel_home_assistant.py`
- `homelab-panel/panel_mqtt.py`

Nine paths were intentionally added:

- `homelab-control/configs/config.example.json`
- `homelab-control/modules/homelab_control_lib.sh`
- `homelab-panel/configs/__init__.py`
- `homelab-panel/configs/config.example.py`
- `homelab-panel/configs/devices.example.py`
- `homelab-panel/modules/__init__.py`
- `homelab-panel/modules/panel_actions.py`
- `homelab-panel/modules/panel_home_assistant.py`
- `homelab-panel/modules/panel_mqtt.py`

Eleven existing paths changed in place:

- `.gitignore`
- `README.md`
- `VERSION`
- `VERSIONING.md`
- `commented_code_map.md`
- `homelab-control/homelab_control_command_listener.py`
- `homelab-control/homelab_control_status_indicator.py`
- `homelab-panel/app.py`
- `scripts/homelab_action_common.sh`
- `tests/test_home_assistant.py`
- `tests/test_mqtt_publish.py`

No other baseline path changed.

## Packaging requirements

Before packaging, temporary active configs and generated `__pycache__`/`.pyc` files from path-resolution testing were removed. The final ZIP is checked for:

- exactly the expected **33** source files;
- no duplicate ZIP entries;
- successful archive integrity testing;
- extracted-file hashes matching the release tree;
- executable/non-executable permissions matching the release tree;
- no active local config files;
- no `__pycache__`, `.pyc`, `.pyo`, build cache, temporary files, runtime logs, or runtime state.

## Limits

- Full Flask/Paho unit and real-wire tests require those installed dependencies and were not available in this sandbox.
- No production broker, Home Assistant instance, remote homelab device, or actual power action was contacted/executed.
