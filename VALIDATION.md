# Homelab Panel 0.0.28 — validation

Prepared 2026-10-26 from the user's replacement archive `Homelab-Panel-main.zip`,
version 0.0.27, SHA-256
`dada65152861f608f74f284771a4327a1423fa690ef267ca203d4bbef86b25ac`.
The earlier `Homelab-Panel-Homelab-Panel-Next.zip` is not the release baseline.
Version advances once, **0.0.27 → 0.0.28**, following 0.0.99 → 0.1.0 rollover.

## Inspection and preservation

The archive was inventoried before editing. Runtime Python, shared MQTT/CLI,
configuration examples, Bash power/status helpers, service units, templates,
dashboard JavaScript, tests, README, existing code map, validation and version
history were reviewed. Existing Waitress and prepared/dashboard/JSON/job caches
were reused. No original file is removed or renamed. All supplied Unix permission
bits and the complete prior version history are preserved. The archive specifies
0755 for ten executable files and no Unix mode for 34 other files; those regular
files are packaged as 0644.

Action manager, Home Assistant and MQTT integrations, dashboard preparation,
shared MQTT transport/CLI, both remote-agent programs, remote shell library,
all power scripts, device and remote-agent config examples remain byte-identical
to the uploaded baseline. Only the panel unit's thread comment changes; its
ExecStart, user, group and deployment paths remain intact. Live power probes,
command allow-lists, script containment/executable guards, browser confirmations,
MQTT retention behavior, session/private-response behavior, job deadlines and
history/job retention are preserved.

## Changes verified

- Optional WEB_SERVER_CONFIG defaults: host 0.0.0.0, port 5000, two threads,
  32 active channels, backlog 64, 30-second inactivity timeout, 5-second cleanup
  checks. Config is validated before workers start. Existing configs can omit it.
  Port/thread/channel settings are configuration keys, not app CLI flags.
- PanelJsonCache now has LRU eviction, a three-file limit and a combined 2 MiB
  source-file budget by default. Oversized files remain readable but uncached.
  Disabled/unstable reads are not retained; corrupt/deleted sources release old
  entries and accounting. Cache copies remain isolated across request threads.
  Source bytes are not decoded Python heap size or a total process memory cap.
- Repeated identical runtime field updates skip atomic writes and unnecessary
  dashboard invalidation. Real/new values still persist immediately through
  existing atomic writers. There is no deferred flush; history/job writes retain
  their existing behavior.
- Current-use README, config example and code map cover every new option/function.
  Both supplied disclaimer bodies remain as written, with Homelab Panel links.
  VERSIONING.md records all release changes. An identical lowercase versioning.md
  is included in the archive to satisfy both requested filename spellings.

## Python regression results

Environment: macOS, Python **3.12.14**, Flask **3.1.3**, Paho MQTT **2.1.0**,
Waitress **3.0.2**, with dependencies isolated outside the release tree.

```bash
python3 -B -m unittest discover -s tests -v
```

**66 tests pass, no skips.** The original 56 tests remain, plus 10 Pi runtime
checks. New tests verify LRU count/source-byte budgets, oversized/disabled bypass,
corruption/deletion/growth, one cold parse across concurrent readers, independent
returned objects, skipped identical updates, durable real updates, invalid settings,
configured direct startup and older configs missing optional dictionaries.

Existing regressions cover auth/session/flash isolation, escaping, retained panel
control rejection, local/remote dispatch and path guards, state/job deadlines,
MQTT TTL and broker loss, cache invalidation, demand-loaded jobs, concurrent
preparation, CLI inspection, root/sudo action argv, and no automatic command retry.
Paho wire tests exercise actual QoS 0/1/2, auth/payload/retain bytes, rejected
connections and missing acknowledgements against a temporary 127.0.0.1 peer.
Power operations are stubbed; no real shutdown/reboot/WoL is performed.

Baseline comparison: the untouched uploaded project runs 56 tests with one failure
on this macOS host. Its local-action test expects `/var/...` while production
correctly resolves `/private/var/...`. The release test fixture now resolves its
expected path; production guards are unchanged. A first sandboxed run also denied
localhost socket binding; the comparable baseline and passing release run used
approved localhost access. These are recorded environmental/test-fixture findings,
not changes to remote command safety.

## Browser and Waitress

The existing Playwright browser regression passes with installed Google Chrome
and a real localhost Waitress fixture. It first passed using the original fixture's
four threads. The fixture was then updated to apply WEB_SERVER_OPTIONS with only
localhost/ephemeral-port overrides, and is verified with the release's two-thread
server settings. An initial configured run failed the original fixed 1.2-second
countdown wait. The fixture now brings the tested page forward, waits up to seven
seconds for an observed clock tick, and uses a 10-second test-only job deadline.
The rerun passes; production JavaScript and job deadlines are unchanged. Device,
broker and power I/O remain mocked.

The scenario checks login/session expiry, independent private results, compact
deltas without navigation, XSS escaping, cancelled confirmations, focus/scroll
preservation, network failure/recovery, hidden-tab pause/resume, instance resets,
mobile layout, older-job button/wheel/keyboard loading, failed-read retry,
serialized reads, local clocks and authoritative job timeout.

## Static, CLI and documentation checks

- 21 Python files compile in memory; no bytecode is written into the project.
- Six Bash files pass `bash -n`; three quoted shell-embedded Python blocks and
  the browser's embedded Python fixture compile.
- Both JavaScript files pass `node --check`; all six Jinja templates parse.
- JSON examples parse. All panel config constants and dictionary options appear
  in README; device/agent examples are preserved unchanged.
- All 278 Python/shell function definitions are represented by name in the code
  map, including nested functions; JavaScript functions and external commands
  remain explained in its existing browser/command sections.
- 24 information-only invocations pass: eight operator entry points each with
  `-h`, `--help` and `--version`, from an unrelated temporary directory. All version
  output reports 0.0.28. Service inspection also passes with Python site packages
  disabled. Existing regressions verify unsupported-argument rejection and power
  inspection before privileged/config/state work.
- Three systemd files were statically inspected. They were not installed or run.

## Packaging verification

The release ZIP contains the full project beneath Homelab-Panel-0.0.28/.
Original/final SHA-256 and Unix modes, additions/changes/omissions and the original
archive checksum are recorded in the supplied external release manifest. All 44
original file paths are retained; the two new code/test files and documentation
mirror are included. The archive therefore has 47 files.

Checks include CRC, unique safe paths, no symlinks, original-path preservation,
archive/tree byte and mode identity, deliberate identical VERSIONING.md/versioning.md
contents, clean extraction, compilation and version reporting. The two versioning
spellings are intentional; they refer to one file on case-insensitive filesystems.
No bytecode, __pycache__, .pyo, virtualenvs, build/test caches, temporary files,
runtime logs/state, active private configs, dependencies or browser downloads
are included. The original archives remain untouched.

## Limits

No actual Pi Zero W CPU/RAM, SD-card lifetime, response-time or production-load
measurements were made. Two threads and these limits are starting defaults, not
benchmark-proven optima. Increase threads if blocking commands delay dashboard
requests, and size caches/history for your own workload.

Real devices/ping/WoL, production MQTT broker/ACLs, Home Assistant discovery,
physical shutdown/reboot confirmation, sudo policy, systemd deployment, Alpine
OpenRC deployment, TLS/reverse-proxy setup and ARMv6 execution were not tested.
Python 3.10/3.11/3.13+ and actual Paho 1.x were not run; simulated 1.x API checks
pass. The JSON budget is not a whole-process memory ceiling. Existing import-started
workers require one panel process; no multiprocess coordination was added.

Upgrade using README: retain active configs and state, install the complete source
and existing dependencies, restart the panel, and reload the dashboard once.
Do not overwrite your active configuration files with examples.
