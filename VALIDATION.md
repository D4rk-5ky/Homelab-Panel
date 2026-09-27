# Homelab Panel 0.0.22 — validation

## Result and scope

Created **0.0.22** from the packaged **0.0.21** baseline after a second caller audit focused specifically on code that might exist only because tests reference it.

The cleanup rule was stricter than the previous release:

- production callers were analysed separately from `tests/`;
- indirect runtime entry points (Flask decorators, callbacks, thread targets, injected callbacks and executable entry points) were checked before classifying anything as dead;
- tests were not allowed to justify an otherwise unused production function, argument mode or default call form;
- component independence remains unchanged: `homelab-panel` and `homelab-control` do not import one another, and `shared_modules/mqtt.py` remains the only shared Python implementation.

The release keeps the same **34 project paths** as 0.0.21.

## Test-only dependency audit

No complete production function was found whose only live reference came from the test suite.

The audit did find **test-only or otherwise unused callable surface inside live functions**. Those paths were removed rather than preserved for test convenience:

- `shared_modules.mqtt.cli_main(argv=...)` no longer accepts an injected argv list; it now always parses the real process `sys.argv`, matching shell/service execution;
- `MqttClient.start()` no longer has an unused implicit `forever` mode; every current runtime caller supplies `forever`, `thread` or `async_thread` explicitly;
- `MqttClient.publish()` requires explicit `qos` and `retain`, because every production caller supplies both;
- `publish_message()` requires explicit `qos` and `retain`; its 20-second timeout default remains because the panel's current remote-action path intentionally uses it;
- private `_publish_once()` requires the full worker request (`qos`, `retain`, `timeout`) supplied by `publish_message()`;
- `PanelMqttRuntime.set_state()` and `publish_direct()` require the retain/QoS values their only current callers already provide;
- the Homelab Control status indicator's `read_text_file()` requires an explicit fallback, and its `publish()` helper requires explicit retain/QoS; all current call sites already supplied them;
- `PanelActionManager.execute_remote_action()` now requires explicit `source`; all current app call sites already provided it. Its empty `job_id` default remains because current Wake-on-LAN/cancel paths use it without a normal remote job ID.

A repeated default-argument audit reports only `app.py:run_command(timeout=20)` as syntactically always supplied. That is a static-analysis false positive: `run_command` is injected into `PanelActionManager`, which calls it without a timeout for current WoL/local-script execution. The default is therefore active runtime behavior and was retained.

## Shared MQTT simplification

The project requires Paho callback API v2 / `paho-mqtt` 2.x+. Paho's current API allows `ReasonCode` to be compared directly with zero for success. The shared MQTT layer therefore no longer carries separate `_reason_value()` and `_reason_text()` normalization helpers.

Current behavior is now:

- connect success: `reason_code == 0`;
- connect/disconnect error text: `str(reason_code)`;
- Paho construction remains centralized exclusively in `shared_modules/mqtt.py`;
- no panel/control component imports Paho directly.

This removes a compatibility-shaped abstraction without changing the current Paho-v2 contract.

## Test-suite cleanup

The tests were updated so they do not preserve the removed production API surface:

- CLI tests patch `sys.argv` and call `cli_main()` exactly as the real entry point does;
- one-shot publisher tests pass explicit QoS/retain/timeout values instead of relying on private defaults;
- `publish_message()` tests pass explicit QoS/retain like production callers;
- the separate fake connect-callback helper was folded into the fake client builder;
- the separate Paho-client-construction test was merged into `test_shared_long_running_client_api()`, which already constructs the same transport and now also verifies callback API v2, MQTT 3.1.1 and clean-session configuration.

Test source is **591 lines**, down from **596** in 0.0.21.

## Function/caller audit

The final source contains:

- **150 production Python functions/methods**;
- **13 production shell functions**;
- **163 production functions total**;
- **200 Python/shell functions including tests**.

No whole production function has a tests-only reference pattern. The remaining definition-only names are framework/injected entry points already verified in the previous full audit, not dead test-supported code.

`commented_code_map.md` contains every one of the **200** Python/shell function names in the final release. Stale entries for removed `_reason_value()`, `_reason_text()`, the old standalone test connect callback, and the merged MQTT construction test were removed.

A normalized AST comparison again found **zero exact duplicate production Python function bodies**. A separate import-use pass found **zero unused top-level imports** in executable production modules.

## Codebase reduction

Production Python/shell source was counted with the same method on both releases, excluding tests:

- 0.0.21: **3,523 lines**;
- 0.0.22: **3,501 lines**;
- net reduction: **22 production lines**.

Together with the test cleanup:

- test source: **596 → 591 lines**;
- project paths: **34 → 34**;
- no new module or compatibility wrapper was added.

## Component boundary checks

Passed:

- no Python import from `homelab-panel` into `homelab-control`;
- no Python import from `homelab-control` into `homelab-panel`;
- only `shared_modules/mqtt.py` imports `paho.mqtt.client` or constructs `mqtt.Client` in production;
- panel-specific MQTT cache/routing/HA behavior stays in `homelab-panel/modules/panel_mqtt.py`;
- control-specific job/status behavior stays in `homelab-control`;
- no additional root shared implementation module was created.

## Static and structure checks

Passed on the final source tree:

- all **14 Python files** parse/compile in memory;
- all **6 shell files** pass `bash -n`;
- all **3 embedded Python heredocs** compile;
- all **4 Jinja templates** parse;
- `homelab-control/configs/config.example.json` parses as JSON;
- all **3 systemd unit examples** contain `[Unit]`, `[Service]`, `[Install]`, and `ExecStart=`;
- the shared MQTT CLI imports under an isolated current-Paho stub and `--help` exposes `--config`, `--topic`, `--qos`, `--retain`, `--timeout`, and `--request-stdin`;
- all three config examples are byte-identical to 0.0.21;
- no current production function has a tests-only whole-function reference pattern;
- no exact normalized duplicate production Python function body remains;
- no unused top-level production import was found;
- no removed test-only signatures/helpers remain referenced in current code or code-map documentation.

## Focused shared-MQTT regression tests

The isolated Paho compatibility fixture is test-only and is not included in the release.

**11/11 focused tests passed** after the cleanup. These cover:

- configured authentication, port, exact payload, QoS 0/1/2 and retain handling;
- unauthenticated publication using explicit non-retained command settings;
- broker rejection and connect/publish failure handling;
- hard timeout close/disconnect behavior with no automatic retry;
- invalid input rejection before client creation;
- the shared long-running `MqttClient`, including callback API v2/MQTT 3.1.1 construction, authentication, LWT, subscriptions, normalized message callback, publish and disconnect state;
- bounded parent-worker execution with credentials kept off argv;
- CLI config/stdin handling using patched real `sys.argv` semantics;
- CLI help/config errors;
- the real Homelab Control shell bridge calling `shared_modules/mqtt.py`.

Result:

```text
Ran 11 tests in 33.817s
OK
```

The panel-action integration test requires Flask and was not included in this isolated subset.

## Full test-suite limitation

The normal final-source command was attempted without stubs:

```bash
python3 -B -m unittest discover -s tests -v
```

It stops during module import because the sandbox does not have the real `paho-mqtt` package installed:

```text
ModuleNotFoundError: No module named 'paho'
```

Flask is also absent from the sandbox, so the real Flask-based panel tests cannot be rerun here either. The focused 11-test result is therefore reported separately and is **not** represented as a complete real-dependency suite pass.

## Not exercised against live infrastructure

No production MQTT broker, Home Assistant instance, remote Homelab Control host, Wake-on-LAN target, shutdown/reboot action, or live systemd service was contacted or changed during validation.

## Packaging checks

Passed on the final release package:

- the **34-path** source manifest is identical to 0.0.21: no project path was added or removed;
- exactly the intended ten files differ from the baseline (`README.md`, `VALIDATION.md`, `VERSION`, `VERSIONING.md`, `commented_code_map.md`, the four cleaned production Python files, and `tests/test_mqtt_publish.py`);
- all three config examples are byte-identical to 0.0.21;
- no active private configs (`homelab-panel/configs/config.py`, `homelab-panel/configs/devices.py`, `homelab-control/configs/config.json`);
- no `__pycache__`, `.pyc`, `.pyo`, runtime state/logs, build cache, or temporary files;
- no duplicate ZIP member names;
- ZIP integrity passes;
- extracted-file SHA-256 values equal the release tree;
- extracted Unix permissions equal the release tree.

The final archive SHA-256 is reported with the downloadable release.
