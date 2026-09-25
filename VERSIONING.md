# VERSIONING.md

## Version policy

This project uses three-part numeric versions and increments every created release by exactly `0.0.1`.

Examples:

- `0.0.1` → `0.0.2`
- `0.0.98` → `0.0.99`
- `0.0.99` → `0.1.0`

The rollover is **not** `0.0.100`.

Every created release must update:

- `VERSION`
- `VERSIONING.md`
- `README.md` when current behavior/usage/configuration changes
- `commented_code_map.md` when functions, routes, scripts, commands, or architecture change
- all affected configuration example files

Release ZIPs must exclude generated Python bytecode/cache files and temporary/build artifacts. Runtime logs/state should not be shipped as historical machine data unless there is a specific reason to preserve them.

---

## 0.0.1 — 2026-09-25

Initial tracked release created from the uploaded, previously unversioned `Homelab-Panel-main` baseline.

### Runtime code

- Preserved the existing Python, shell, HTML, systemd, and active configuration behavior unchanged.
- Normalized the command-listener systemd unit file mode from executable (`0755`) to normal unit-file permissions (`0644`); unit contents were not changed.
- Did not refactor, rename, or alter shutdown/reboot, MQTT, Wake-on-LAN, ping, token, or status logic in this release.

### Documentation and release structure

- Rewrote `README.md` so it documents current application behavior and usage only, rather than acting as historical release notes.
- Added the requested liability/disclaimer language and adapted `script` wording to the Homelab Panel project where appropriate.
- Documented every current configuration option in `homelab-panel/config.py`, `homelab-panel/devices.py`, and `homelab-control/config.json`.
- Documented the complete current command surface: Python entry points, shell scripts, MQTT command payloads, Flask routes, and systemd usage.
- Explicitly documented that version 0.0.1 has no supported CLI flags or argument parser.
- Added `commented_code_map.md` with function/command/file purpose and rationale.
- Added explicit configuration examples:
  - `homelab-control/config.example.json`
  - `homelab-panel/config.example.py`
  - `homelab-panel/devices.example.py`
- Added `VERSION` containing `0.0.1`.

### Clean-package changes

- Removed the uploaded `homelab-panel/__pycache__/` directory and its `.pyc` files from the release package.
- Removed historical machine runtime data from `homelab-control/logs/commands.log` and `homelab-control/state/*` in the release package.
- Preserved the empty `logs/` and `state/` directories because the runtime uses those locations and creates their contents as needed.

### Validation performed for this release

- Full source/config/template/service inventory reviewed before modification.
- Python source compile checks performed without writing bytecode into the project tree.
- Shell scripts checked with `bash -n`.
- JSON configuration/example files parsed as JSON.
- Python config/example files syntax-checked.
- Release ZIP checked for forbidden cache/bytecode files.
- Final release manifest compared with the uploaded baseline so removals and additions are accounted for.

Any environment-dependent checks that could not be safely executed are reported with the delivered release rather than being represented as tested.
