# Homelab Panel 0.0.25 — validation

Validated on 2026-10-24, based on repository commit `fb9a0b21e3607b49419ce9e72ce10689d8b26277` (version 0.0.24).

## Delivered behavior

- Direct panel startup uses Waitress: one process, four request threads, port 5000. The systemd entry still launches app.py. Existing configurations require no new keys.
- The dashboard shell loads on navigation. Polling requests `/api/dashboard` with a per-tab revision and process-instance token. Only changed shared status/job fragments are returned; unchanged polls contain metadata and an empty `devices` object.
- Web requests use background-monitor ping measurements, never run network probes, and mark missing/expired measurements unknown. Cache expiry allows the normal sequential scan duration (two monitor intervals plus three seconds per configured device). Current MQTT connection/TTL state is evaluated independently to avoid false online status after broker loss.
- Shared HTML fragments are escaped and cached by input content. Runtime JSON is parsed once per file version; atomic replacements, external edits, deletion and corruption are detected. Merged jobs are decoded/sorted only when sources change. Lifecycle timeouts and countdowns remain time-dependent.
- Command results are returned only to the initiating browser; ordinary forms preserve redirect/flash fallback. Session identities, flash messages and cookies stay outside shared caches. Dynamic responses are private/no-store and vary by Cookie.
- Browser polling does not overlap, times out and retries on failure, pauses in hidden tabs and resumes when visible. It marks displayed data as unrefreshed after a connection failure. Commands are never retried automatically.

## Python regressions

Executed with Python 3.12, Flask 3.1.3, Paho MQTT 2.1.0 and Waitress 3.0.2 installed in an isolated temporary dependency directory:

```text
python3 -B -m unittest discover -s tests -v
Ran 40 tests
OK
```

The suite covers existing HA discovery/dispatch, command safety, real Paho wire exchanges over localhost, and nine new dashboard/server cases:

1. startup/expired-cache views without request-time pings;
2. unchanged-card reuse without template rendering and an unchanged JSON payload under 200 bytes;
3. per-device deltas, independent tab cursors and restart resets;
4. broker loss and MQTT TTL expiry;
5. source invalidation and job timeout progression without new MQTT data;
6. JSON parse reuse and file replace/delete/corruption handling;
7. two-session identity/message isolation and authenticated JSON actions;
8. HTML escaping of device/job payloads;
9. direct entry uses Waitress instead of the development server.

The existing test loader required a fixture-only correction: production callback-owner modules are loaded before the temporary `sys.modules` overlay, so patching their callbacks remains possible after fixture cleanup. Production MQTT/agent behavior was not changed.

## Browser end-to-end check

`tests/dashboard_browser.cjs` passed with Chromium 153.0.8010.0 / Playwright and a real Waitress 3.0.2 localhost server. It verified:

- real login and authenticated polling;
- compact unchanged responses and changed-card delivery;
- persistent shell/no navigation during polls and commands;
- escaped job messages with no script execution;
- preserved job-list element, focus and scroll position;
- cancelled confirmations send zero commands; accepted confirmation sends one;
- command result appears only in the initiating tab;
- connection failure indicator and automatic recovery;
- hidden-tab polling pause and visible-tab resume;
- fresh fragments after process-cache reset;
- no horizontal overflow at a 390-pixel mobile viewport;
- expired session returns to login;
- no JavaScript page errors.

All power actions, device probes and MQTT connections in the browser fixture are mocked. Test-only fixture routes are defined inside the browser test subprocess, never in production app.py.

## Static checks and packaging

- All 17 Python files parse successfully.
- All six shell files pass `bash -n`; agent JSON example parses.
- Both browser JavaScript files pass `node --check`.
- `git diff --check` passes.
- Release includes source, configuration examples, new templates/static assets, requirements, tests, current README/code map/versioning/validation.
- Release excludes `.git`, active configs, runtime state/logs, virtualenvs, bytecode, browser/dependency downloads and temporary test files.

## Practical limits

The actual Raspberry Pi/homelab host and real device actions were not exercised. CPU/RAM savings on that host have not been measured. Shared fragments are populated lazily and caches reset on process restart. Keep one panel process. Python 3.10+ remains the minimum; older Paho compatibility remains covered by the existing simulated-API checks, while real wire tests here used Paho 2.1.0.

Upgrade steps and optional browser-test setup are in README.md.
