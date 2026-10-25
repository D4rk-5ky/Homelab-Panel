# Homelab Panel 0.0.27 — validation

Validated on 2026-10-25. The source baseline is the delivered `Homelab-Panel-0.0.26.zip`; preservation is also checked against the user's original `Homelab-Panel-0.0.25.zip`. Version advances exactly 0.0.26 → 0.0.27, with the 0.0.99 → 0.1.0 rollover policy retained.

## Implemented behavior

1. **One prepared dashboard snapshot.** The existing dashboard cache now shares prepared device/job views across browsers. MQTT revision/connectivity, ping measurements, provisional actions, WoL activity, device/settings changes and runtime/job file identities invalidate the view. MQTT freshness, stale-monitor and all active-job deadlines also invalidate it without new messages. Wall-clock sampling occurs under the preparation lock, so overlapping requests are not mistaken for clock rewinds. Actual backwards clock steps force reevaluation.
2. **Batched cached-state reads.** A rebuild loads runtime JSON once, jobs JSON once and MQTT receive metadata once for all devices. Unchanged requests check file identity but avoid repeated file-cache loads/deep copies, status construction, job evaluation and rendering. Existing helper functions receive optional batch inputs; direct monitor/HA callers retain their live defaults.
3. **Browser elapsed-time labels.** Stable receive/deadline epochs replace changing age/countdown text in shared sources. One visible-tab clock interval updates text using server time plus monotonic elapsed browser time. Server freshness and timeout classification remain authoritative; countdown zero never claims success or changes stored jobs.
4. **Older jobs loaded on demand.** Default initial batch is five per device. Button, wheel, scroll and keyboard demand expand a current newest-first prefix through authenticated GET `/api/jobs/<device_id>?limit=N`. A scroll-for-more sentinel makes an exactly fitting first batch scrollable. Expanded windows stay current on global polls. Requests are serialized, and a partial device response cannot advance the global cursor. Row HTML is cached once per current retained row, not once per browser/window. Full storage/history retention is preserved. `/?jobs=all` supplies the no-JavaScript path to every retained job.
5. **Optional payload logging.** `MQTT_CONFIG.log_payloads` defaults to False, suppressing full incoming panel telemetry printing. Connection, rejection/error and action-result logging remains. Routing, receive-state updates and control safety are unchanged.

`DASHBOARD_JOB_PAGE_SIZE` is optional in existing active configs, default 5, minimum 1, capped by `PANEL_JOB_MAX_ENTRIES`. Config examples and current-use README document both new options, routes, query values and clock behavior. Both supplied disclaimer bodies, full version history, all original files and permission metadata are preserved. No runtime dependency, additional service, new cache process or periodic rebuild worker is introduced.

## Python regressions

Environment: Python 3.14.4, Flask 3.1.3, Paho MQTT 2.1.0, Waitress 3.0.2.

```bash
python3 -B -m unittest discover -s tests -v
```

**56 tests pass, no skips.** Existing action/auth/HA/retained-control/path checks, dashboard isolation/escaping, CLI safety, Waitress startup and real Paho localhost wire exchanges remain covered. New checks exercise:

- exactly two cold source loads and zero warm loads/status builds/timeout evaluations/renders across two browser clients;
- no clock-only invalidation, exact job expiry, integer-second MQTT TTL boundary, stale-monitor expiry and backwards-clock reevaluation;
- runtime/MQTT/action/WoL/config changes and external file replacement/corruption/deletion;
- initial five of 100 jobs, lazy additional row rendering/reuse, independent expanded windows, bounded row cache, full no-JavaScript access and unchanged retained data;
- inserted/reordered jobs, expanded-window updates and deadlines of jobs outside the initial visible batch;
- protected read-only pagination, private response headers, input limits and HTML escaping;
- configurable initial batch independent of retention, and an active-config fixture omitting the new optional key;
- absent/False/True payload logging while receive-state and error/connection handling continue;
- six concurrent readers producing one preparation build.

Paho protocol checks contact a temporary localhost peer only, covering exact payload/auth/QoS/retain flags, rejected connections and missing acknowledgements. Power-script checks use stubs; no real device command runs.

## Chromium / Waitress end-to-end check

`tests/dashboard_browser.cjs` passes with Playwright, Chromium headless shell 151.0.7922.34 and a real Waitress localhost fixture. Device probes, MQTT connections and power actions are mocked.

Verified login/session expiry, independent private results, compact deltas, no full navigation on updates/actions, escaping, confirmation cancellation, focus/scroll preservation, connection failure/recovery, hidden-tab pause/resume, restart reset and a 390-pixel viewport without horizontal overflow.

Additional checks verify initial batching, older-job button loading, real wheel scrolling from an exactly fitting initial list, subsequent scrolling and keyboard expansion, failed-read retry, a queued older-job request behind a delayed global poll with at most one read in flight, age/countdown ticks without replacing their cached nodes, and server timeout classification. Test-only routes are confined to the browser fixture process. Browser dependencies/downloads are outside the release tree.

## Reproducible local workload comparison

Same isolated fixture for each version: three devices, 100 completed retained jobs per device, fixed clock, mocked device/network work. Sizes are uncompressed HTML/JSON bytes, not Pi timing measurements.

| Measurement | 0.0.26 | 0.0.27 |
|---|---:|---:|
| Initial dashboard HTML | 73,629 bytes | 15,782 bytes |
| Initially rendered job rows | 300 | 15 |
| Runtime cache loads per unchanged poll | 6 | 0 |
| Jobs cache loads per unchanged poll | 3 | 0 |
| Status fragments changed after 15 seconds, no source changes | 1 | 0 |
| Unchanged JSON response | 109 bytes | 143 bytes |

The initial fixture HTML is about **79% smaller**. The unchanged response gains server clock metadata; both versions send no card HTML when unchanged. Warm requests still perform two file-identity checks so external edits are detected; zero cache loads does not mean zero filesystem metadata checks. These results establish reduced work/payload, not a measured speedup or RAM saving on the Pi.

## Static, CLI, documentation and safety checks

- All **19 Python files** compile in memory, **6 shell files** pass `bash -n`, and **4 embedded Python blocks** compile.
- Both JavaScript files pass `node --check` with Node 24.22.1.
- **24 help/version checks**: all eight operator entry points × `-h`, `--help`, `--version`, invoked from `/tmp`; all succeed and version commands expose 0.0.27.
- JSON examples parse; every example option key/constant appears in README. The code map explains all **262 Python/shell function definitions** by name, plus browser functions/callbacks and embedded fixture commands.
- Existing full version history is preserved; README remains a current-use guide and includes both supplied disclaimer bodies with project-local links.
- Three systemd examples pass static section/directive checks. Root-agent code, shared MQTT transport/CLI helper, power scripts, action manager, HA integration, service units, requirements and unaffected config examples remain byte-identical to 0.0.26.
- Eight original/release configured-root power-script success/failure comparisons match event order, exact argv, output and return code using stubs. Authentication, non-retained panel control, action allow-lists, executable/path guards, one-minute power behavior and server deadline checks are preserved.

## Archive verification

The clean source ZIP contains **44 files** under `Homelab-Panel-0.0.27/`. It preserves all **44 paths from 0.0.26**, including all **42 original-upload paths**. No project file is removed or renamed. Original and previous-release file permissions are preserved. An external manifest records original, previous and final SHA-256 hashes/modes and change status for every path.

Packaging verifies CRC, unique safe paths, no symlinks/case collisions, exact archive/tree bytes and modes, all original/previous paths, fresh-extraction hashes/compilation and version commands. Exclusions include `__pycache__`, `.pyc`, `.pyo`, active private configs, runtime state/logs, virtual environments, build/cache artifacts, downloaded browsers/dependencies, diagnostics, test logs and temporary files. Root `.gitignore`, empty package markers, all tests, examples and necessary original support files remain included.

## Limits and deployment

Actual Pi Zero W CPU/RAM usage, SD-card behavior, production concurrency, real devices/ping/Wake-on-LAN, live Home Assistant/broker/ACL integration, physical power actions, sudo policy and systemd deployment were not exercised. Python 3.10–3.13 and real Paho 1.x were not run; the existing simulated Paho 1.x API checks pass.

Run one panel process. Install the complete source tree and keep active configs/state; the new options have defaults for existing configs. Restart the panel and reload open dashboard tabs once to load the updated script/templates. Existing import-started workers, command transport, sender-controlled retention on the direct agent topic and job/history retention remain unchanged. Background polling remains necessary for server state delivery; local clocks only update elapsed-time text.
