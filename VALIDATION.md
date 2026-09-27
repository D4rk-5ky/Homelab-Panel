# Homelab Panel 0.0.21 — validation

## Result and scope

Created **0.0.21** from the packaged **0.0.20** baseline after a function-by-function and current-path audit of the panel, Homelab Control agents, shared MQTT implementation, shell helpers, templates, examples, and tests.

The goal was to remove code that exists only for older layouts/protocols/callers and to remove dead delegation/duplicate paths without removing current functionality. Component independence remains a hard boundary:

- `homelab-panel` may use its own modules plus root `shared_modules.mqtt`;
- `homelab-control` may use its own files/modules plus root `shared_modules.mqtt`;
- neither component imports the other component;
- `shared_modules/mqtt.py` remains the only shared Python implementation between them.

No project path was added or removed in 0.0.21. The release keeps the same **34 tracked source files** as 0.0.20.

## Function/caller audit

The final source contains:

- **152 production Python functions/methods**;
- **13 production shell functions**;
- **165 production functions total**;
- **203 Python/shell functions including tests**.

Every remaining production function was checked against direct callers, callback registration, thread targets, Flask decorators, or executable entry-point use.

Only five production Python names occur only at their definition site:

- `require_web_login()` — Flask `@app.before_request` hook;
- `device_history()` — Flask route;
- `wol_cancel()` — Flask route;
- `mqtt_button()` — Flask route;
- `local_button()` — Flask route.

These are framework-registered entry points, not dead code. Every shell function has a current call site. `commented_code_map.md` contains every one of the **203** Python/shell function names present in the final release.

A normalized AST comparison found **zero exact duplicate production Python function bodies** after cleanup. A separate AST name-use pass found **zero unused top-level imports or simple top-level aliases/assignments** in executable production modules.

## Removed legacy/dead paths

The audit removed code that is not part of the current project behavior:

- app-level mirror/delegate functions around `PanelActionManager`, `PanelMqttRuntime`, and `HomeAssistantIntegration`;
- app-level duplicate MQTT cache/connectivity aliases;
- the old query-string `PANEL_TOKEN` web-access path;
- derived/sibling MQTT status-topic compatibility helpers;
- delayed-command `shutdown`/`reboot` aliases and implicit old power-category inference;
- implicit/default remote panel-control targeting;
- `json_jobs` and plain-text Homelab Control command handling;
- old string-valued command allow-list entries;
- generation of missing remote `job_id`/`source` fields;
- pre-current boot-history migration/archive helpers;
- duplicate Python `load_config()` wrappers;
- unused status-indicator log-directory ownership;
- shell `json_get_optional()` and invalid-history-limit fallback;
- Paho callback API v1 constructor support and public callback aliases;
- flexible string subscription formats;
- the unused shared MQTT `connect`-only lifecycle mode;
- no-op command aliases and other variables/helpers whose only purpose was compatibility with earlier internal layouts.

Searches of current source/docs/tests confirm that removed knobs/surfaces such as `PANEL_TOKEN`, `json_jobs`, `derive_related_topic`, `homelab_mqtt.py`, old MQTT callback compatibility names, and the connect-only mode are no longer referenced outside historical `VERSIONING.md` entries.

## Current behavior made explicit

0.0.21 supports only the current project formats:

- web access is either open when `WEB_AUTH_CONFIG.enabled` is false or uses the configured Flask session login;
- panel-control MQTT envelopes require explicit `target="remote"` or `target="local"`;
- direct remote-agent commands require JSON with non-empty `command`, `job_id`, and `source`;
- Homelab Control command allow-list entries are objects, not legacy strings;
- device status topics are explicit config fields rather than derived sibling-topic fallbacks;
- `LOCAL_SERVER["name"]` is required for the local Home Assistant device name;
- `shared_modules/mqtt.py` requires Paho callback API v2 / `paho-mqtt` 2.x+;
- the shared long-running MQTT client supports only current production modes: `forever`, `thread`, and `async_thread`.

Current robustness that is still useful—malformed runtime-state handling, allow-list validation, path containment, process timeouts, atomic writes, MQTT timeout/no-retry behavior, and safe display defaults—was retained. Those are current safety/recovery behaviors rather than historical compatibility.

## Codebase reduction

Production Python/shell source was counted with the same method on both releases, excluding tests:

- 0.0.20: **4,018 lines** across 18 production Python/shell files;
- 0.0.21: **3,523 lines** across the same 18 files;
- net reduction: **495 lines**.

The project therefore became smaller without creating additional modules or cross-component imports.

## Component boundary checks

Passed:

- no Python import from `homelab-panel` into `homelab-control`;
- no Python import from `homelab-control` into `homelab-panel`;
- only `shared_modules/mqtt.py` imports `paho.mqtt.client` or constructs `mqtt.Client` in production code;
- panel-specific MQTT cache/routing/HA behavior stays in `homelab-panel/modules/panel_mqtt.py`;
- control-specific job execution/status behavior stays in `homelab-control`;
- no additional root shared implementation module was created.

An independent smoke check from `/tmp` loaded the two Homelab Control Python entry points and panel module code using temporary current-format configs/stubs, verified current JSON command requirements, current object command specs, shared power-script resolution, and panel/control independence. Temporary active config files were removed after the check.

## Static and structure checks

Passed on the final source tree:

- all **14 Python files** compile in memory with bytecode writing disabled;
- all **6 shell files** pass `bash -n`;
- all **3 embedded Python heredocs** compile;
- all **4 Jinja templates** parse;
- `homelab-control/configs/config.example.json` parses as JSON;
- all **3 systemd unit examples** contain `[Unit]`, `[Service]`, `[Install]`, and `ExecStart=`;
- the shared MQTT CLI imports under an isolated current-Paho stub and `--help` exposes `--config`, `--topic`, `--qos`, `--retain`, `--timeout`, and `--request-stdin`;
- no current executable production module has an unused top-level import/simple alias reported by the AST audit;
- no exact normalized duplicate production Python function body remains;
- no `__pycache__`, `.pyc`, or `.pyo` remains after validation cleanup.

## Focused shared-MQTT regression tests

The offline current-Paho compatibility fixture is test-only and is not included in the release.

The focused MQTT publisher/client/CLI/shell regression set passed **12/12** after the cleanup. It covers:

- configured auth/port/payload/QoS/retain handling;
- unauthenticated default publication;
- refused connections and publish/connect failures;
- hard timeout close/disconnect behavior with no automatic command retry;
- invalid input rejection before network creation;
- current Paho callback API v2 client construction;
- shared long-running `MqttClient` authentication/LWT/subscriptions/normalized message callbacks/publish/disconnect behavior;
- bounded parent-worker handling with credentials kept off argv;
- CLI config/stdin handling and CLI errors/help;
- the real shell bridge calling the shared MQTT module.

Result:

```text
Ran 12 tests in 30.793s
OK
```

## Full test-suite limitation

The normal command was attempted on the final source without stubs:

```bash
python3 -B -m unittest discover -s tests -v
```

It cannot run in this sandbox because the real `paho-mqtt` package is not installed. Both test modules stop during import with `ModuleNotFoundError: No module named 'paho'`. Flask is also absent, so the real Flask-based panel tests cannot be rerun here.

The focused offline results above are therefore reported separately and are **not** represented as a full real-dependency suite pass.

## Not exercised against live infrastructure

No production MQTT broker, Home Assistant instance, remote Homelab Control host, Wake-on-LAN target, shutdown/reboot action, or live systemd service was contacted or changed during validation.

## Packaging checks

Passed on the final release archive:

- the **34-path** source manifest is identical to 0.0.20: no project path was added or removed;
- only intended source/docs/tests files differ from the baseline;
- no active private configs (`homelab-panel/configs/config.py`, `homelab-panel/configs/devices.py`, `homelab-control/configs/config.json`);
- no `__pycache__`, `.pyc`, `.pyo`, runtime state/logs, build cache, or temporary files;
- no duplicate ZIP member names;
- ZIP integrity passes;
- extracted-file SHA-256 values equal the release tree;
- extracted Unix permissions equal the release tree.

The final archive SHA-256 is recorded in the release response after packaging.
