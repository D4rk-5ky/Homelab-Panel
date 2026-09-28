# Homelab Panel 0.0.24 — validation

## Result and scope

Created **0.0.24** from the uploaded **0.0.23** package.

The complete baseline project was inspected before the requested behavior was changed. The source tree contains **34 relative project paths** covering the panel app/modules/templates, Homelab Control daemons/helper, shared MQTT transport, power-action scripts, service units, configuration examples, tests, and release documentation.

This release implements two requested changes only:

1. optional lifecycle expiry for unresolved jobs, including 60-second shutdown/reboot examples and a distinct `timed_out` state; and
2. support for the older Paho MQTT 1.x callback API alongside current Paho 2.x callback API v2.

## Versioning

Passed:

- baseline `VERSION`: `0.0.23`;
- final `VERSION`: `0.0.24`;
- increment is exactly `0.0.1`;
- rollover policy remains `0.0.99 -> 0.1.0`, not `0.0.100`.

## Job lifecycle timeout

The new button option is:

```python
"job_timeout_seconds": 60,
```

Behavior verified from the implementation and isolated logic tests:

- the setting is optional and must resolve to a positive integer;
- omitting it leaves the panel lifecycle without this expiry;
- only `queued`, `running`, `waiting`, and `confirming` are active lifecycle states;
- configured active jobs expose `timeout_remaining_seconds`;
- when the deadline expires, the derived job state is `timed_out`;
- `timed_out` is not treated as active;
- the generated job message explicitly says the job timed out and is no longer considered active;
- the timeout view is non-mutating, so a later real remote `success` or `failure` can replace a display-time timeout;
- already-terminal jobs such as `success` are not rewritten by lifecycle expiry;
- shutdown/reboot example buttons use 60 seconds as requested;
- shutdown/reboot physical-confirmation fallback values in the tracked device example are also 60 seconds;
- a button-level `job_timeout_seconds` is reused by the shutdown/reboot confirmation worker rather than parsed separately;
- confirmation deadline expiry records `timed_out` with warning severity rather than `failure`;
- cancelling the shutdown/reboot confirmation worker still stops that worker; if the original job remains unresolved, its configured lifecycle deadline makes the displayed/HA job non-active after expiry.

`job_timeout_seconds` is deliberately separate from Homelab Control's command `timeout`: the panel lifecycle timeout does **not** kill the remote script. The command-listener `timeout` is still the subprocess execution limit.

An isolated `PanelActionManager` confirmation test exercised a one-second deadline with no confirmation signal and verified the final persisted callback state was `timed_out`, warning severity, and contained the explicit non-active timeout note.

An isolated Homelab Control listener timeout test forced `subprocess.TimeoutExpired` and verified the resulting job record became `timed_out` with the message `Command timed out after ... seconds; job is no longer considered active`.

## Timeout UI/status presentation

The dashboard/template implementation now uses:

- green for `success`;
- red for `failure`;
- yellow/orange for active/waiting work;
- purple for `timed_out`.

The Jobs section includes a legend explaining those meanings. Configured active jobs show the remaining timeout seconds. Timed-out jobs show the configured timeout, timeout timestamp when available, and the explicit timeout message.

Warning history entries use the same purple border so confirmation/subprocess timeout events are visibly distinct from red failures. `result_to_danish()` maps `timed_out` to `Timeout` for history/current-result display.

All four Jinja templates parse successfully. The new Flask rendering regression is present in `tests/test_home_assistant.py`, but the real Flask-based suite could not be executed in this sandbox because its dependencies are unavailable; see the limitation section below.

## Paho MQTT 1.x + 2.x compatibility

`shared_modules/mqtt.py` now uses one version-adaptive transport path:

- when `mqtt.CallbackAPIVersion` exists, client construction requests `VERSION2` explicitly;
- when it is absent, the Paho-2-only `callback_api_version` constructor keyword is omitted, allowing Paho 1.x construction;
- long-running connect handling accepts the Paho 1.x four-argument and Paho 2.x VERSION2 five-argument callback shapes;
- disconnect handling normalizes Paho 1.x `(rc)` and Paho 2.x `(disconnect_flags, reason_code, properties)` callback tails;
- the one-shot publisher's connect callback also accepts both version families;
- optional publish completion waiting uses bounded `is_published()` polling, avoiding dependence on a version-specific completion-call signature.

Five focused MQTT regression tests passed under an import-only Paho stub, including explicit simulated-Paho-1 coverage:

```text
test_shared_long_running_client_api ... ok
test_paho_v1_constructor_and_callback_shapes_are_supported ... ok
test_paho_v1_one_shot_connect_callback_is_supported ... ok
test_settings_payload_qos_and_retention_are_preserved ... ok
test_invalid_inputs_fail_before_connecting ... ok

Ran 5 tests in 0.002s
OK
```

The MQTT CLI `--help` also executes under the stub and still exposes the complete current flag contract: `--config PATH`, internal `--request-stdin`, `--topic TOPIC`, `--qos {0,1,2}`, `--retain`, and `--timeout SECONDS`, including the retained-command safety warning.

## Full-suite limitation

The normal release test command was attempted:

```bash
python3 -B -m unittest discover -s tests -v
```

The sandbox does not contain the real `paho-mqtt` package, so collection stops with `ModuleNotFoundError: No module named 'paho'` before the Flask-dependent suite can run. Flask is also not available in this execution environment.

A temporary non-project `pip --target` dependency installation was attempted without changing the project or system Python. Package retrieval failed because the execution environment could not resolve the package index hostname. The temporary test dependency/stub directories are outside the project and are not included in the release.

Consequently, this release was **not** exercised against an installed real Paho 1.x package, an installed real Paho 2.x package, or a real Flask test client in this sandbox. The version compatibility is covered by simulated callback/constructor tests and static inspection, but should still be exercised on the target hosts after deployment.

## Static and structure checks

Passed on the final source tree before packaging:

- all **14 Python files** compile in memory without writing bytecode;
- all **6 shell files** pass `bash -n`;
- all **3 embedded Python heredocs** in the shell helper compile;
- all **4 Jinja templates** parse;
- `homelab-control/configs/config.example.json` parses as JSON;
- all **3 systemd unit examples** contain `[Unit]`, `[Service]`, `[Install]`, and `ExecStart=`;
- repository-wide argparse search still finds only `shared_modules/mqtt.py`;
- `commented_code_map.md` contains every current Python/shell function name: **152 production Python functions/methods + 13 production shell functions + 42 test functions = 207 total**;
- no source/config/template/service path was added or removed;
- no `__pycache__`, `.pyc`, or `.pyo` exists in the release tree.

Production Python/shell source is **3,651 lines**. Test source is **716 lines**.

## Configuration and documentation audit

The three tracked configuration examples were checked:

- `homelab-panel/configs/config.example.py` — no new global panel option was required;
- `homelab-panel/configs/devices.example.py` — documents the new optional per-button `job_timeout_seconds` and uses 60 seconds for shutdown/reboot plus their fallback confirmation values;
- `homelab-control/configs/config.example.json` — its existing per-command `timeout` remains the remote subprocess limit and requires no new key.

README.md documents the distinction between panel lifecycle timeout and agent execution timeout, all current status colors, countdown/timeout behavior, and Paho 1.x/2.x support. The existing CLI flag documentation remains complete.

The existing README disclaimer body was preserved. The request referred to a disclaimer "as written below", but no replacement disclaimer text was supplied in the request, so no disclaimer wording was invented.

## Files changed from 0.0.23

The intended release changes are limited to:

- `README.md`;
- `VALIDATION.md`;
- `VERSION`;
- `VERSIONING.md`;
- `commented_code_map.md`;
- `homelab-control/homelab_control_command_listener.py`;
- `homelab-panel/app.py`;
- `homelab-panel/configs/devices.example.py`;
- `homelab-panel/modules/panel_actions.py`;
- `homelab-panel/templates/history.html`;
- `homelab-panel/templates/index.html`;
- `shared_modules/mqtt.py`;
- `tests/test_home_assistant.py`;
- `tests/test_mqtt_publish.py`.

No project path is intended to be added or removed. All other baseline files must remain byte-identical.

## Not exercised against live infrastructure

No production MQTT broker, Home Assistant instance, remote Homelab Control host, Wake-on-LAN target, real shutdown/reboot action, or live systemd service was contacted or changed.

## Packaging requirements

The final ZIP is verified after creation for:

- the same **34 relative project paths** as 0.0.23;
- no unexpected changed/added/removed file;
- no duplicate or traversal-unsafe ZIP member;
- archive integrity;
- byte-for-byte equality between archive members and the final release tree;
- preserved Unix permission bits;
- no active private config, runtime state/log, test stub, dependency download, cache, bytecode, build output, or temporary file.
