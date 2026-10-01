# Homelab Panel 0.0.26 — validation

## Result and scope

Created **0.0.26** from the packaged **0.0.25** release.

The complete 0.0.25 tree was inventoried before modification. It contained **36 files**. This release changes only the Home Assistant birth/discovery refresh path, its regression expectation, current-use documentation/config comments, and release metadata. No production file was removed and no configuration key was added or removed.

The reported symptom was that Home Assistant device buttons could appear freshly changed/pressed even when no command had intentionally been pressed. The project does not publish a button state topic: its discovered MQTT buttons contain a `command_topic`/`payload_press` and `retain=False`. The concrete project-side issue found was duplicate Home Assistant discovery publication on a panel MQTT connection: `_connected()` published one complete snapshot, then the broker could immediately replay the retained HA `online` status to the new status subscription, and 0.0.25 treated that retained replay as another birth event and published the same snapshot again.

## Versioning

Passed:

- baseline `VERSION`: `0.0.25`;
- final `VERSION`: `0.0.26`;
- increment is exactly `0.0.1`;
- rollover policy remains `0.0.99 -> 0.1.0`, not `0.0.100`.

## Home Assistant / MQTT behavior

Changed only `PanelMqttRuntime._message()` for the configured HA status topic:

- a matching **retained** status replay is cached for diagnostics but does **not** publish another HA snapshot;
- a matching **live** status message still calls `publish_home_assistant_snapshot()`;
- non-matching/offline status messages still do not publish a snapshot;
- `_connected()` still publishes one HA snapshot when the panel MQTT connection comes up;
- retained panel-control messages remain rejected and are not executed;
- button discovery topics, stable `unique_id` values, `command_topic`, `payload_press`, and non-retained button-command behavior are unchanged.

A focused dependency-free routing check directly exercised the production `PanelMqttRuntime`:

```text
connect -> 1 snapshot
retained online replay -> 0 additional snapshots
live online birth -> 1 additional snapshot
offline status -> 0 additional snapshots
```

Result: **passed**.

The existing `tests/test_home_assistant.py` regression was updated to require the same retained-vs-live behavior. It remains part of the normal full suite when Flask and Paho are installed.

## Compile and syntax checks

Passed:

- source compilation with Python's `compile()` for all **16 Python files**;
- `bash -n` for all **6 shell files**;
- parsing all **4 Jinja templates**;
- `systemd-analyze verify` for all **3 service units** (using the project's existing `homelab-controll.service` filename);
- executable-AST comparison confirms `homelab-panel/configs/config.example.py` changed in comments only, with no configuration semantics changed;
- `commented_code_map.md` references all **222** detected Python/shell function definitions;
- five `tests/test_cli_entrypoints.py` tests, including help/version safety and exact no-argument shutdown/reboot command preservation;
- `--version` continues to report `0.0.26` from the shared root `VERSION` file.

## Full-suite limitation

The normal command was attempted:

```bash
python3 -B -m unittest discover -s tests -v
```

The **5 CLI tests pass**, but collection of the older Home Assistant/MQTT suites cannot complete in this sandbox because the real runtime dependencies are absent:

```text
flask: No module named 'flask'
paho.mqtt.client: No module named 'paho'
```

The full dependency-backed Home Assistant integration suite therefore was **not claimed as passed**. The changed MQTT routing branch was instead tested directly with a temporary import stub outside the project tree; no stub or generated test artifact is included in the release.

## Documentation and configuration

Updated:

- `README.md` — current HA status/birth behavior and troubleshooting only; no release-history section was added;
- `commented_code_map.md` — documents why retained HA status replay is ignored and why live birth is still honored; updated regression-test responsibility;
- `VERSIONING.md` — added the 0.0.26 release record;
- `homelab-panel/configs/config.example.py` — comments now describe the retained/live rule. Available options are unchanged.

The user-supplied disclaimer/liability text remains in `README.md`.

## Packaging / manifest

The final archive is checked against the 0.0.25 manifest before delivery. Expected result:

- **36 files** in the final release;
- no baseline file removed;
- no new production/test file required for this change;
- changed files are limited to `VERSION`, `README.md`, `VERSIONING.md`, `VALIDATION.md`, `commented_code_map.md`, `homelab-panel/configs/config.example.py`, `homelab-panel/modules/panel_mqtt.py`, and `tests/test_home_assistant.py`;
- no `__pycache__`, `.pyc`, `.pyo`, build cache, temporary files, or runtime state/log files are included.

The final ZIP integrity/hash and exact manifest comparison are recorded during packaging.
