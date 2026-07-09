# 2026-07-09 Live validation gate - current Android environment

Primary issue: [#32](https://github.com/yangliang2/ai_verification/issues/32)

Parent PRD: [#30](https://github.com/yangliang2/ai_verification/issues/30)

Related blocked seed: [#23](https://github.com/yangliang2/ai_verification/issues/23)

## Status

Generic Android environment gate: **passed**.

This run proves that the current device, boot state, Android CLI layout channel,
and direct UIAutomator dump channel are healthy enough to proceed to app-level
smoke validation. It is not a seed result and does not count #23 as caught,
missed, passed-control, or false-positive.

## Commands Run

Tool and environment capture:

```bash
android --version > android-version.txt 2>&1
adb version > adb-version.txt 2>&1
android info > android-info.txt 2>&1
adb devices -l > adb-devices-before.txt 2>&1
/Users/80268204/Library/Android/sdk/emulator/emulator -version > emulator-version.txt 2>&1
uname -a > host-uname.txt 2>&1
sw_vers > host-sw-vers.txt 2>&1
```

Gate execution:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.live_validation_gate \
  --device emulator-5554 \
  --timeout-seconds 20 \
  --output docs/runs/2026-07-09-live-validation-gate-current-environment/live-validation-gate.json \
  > docs/runs/2026-07-09-live-validation-gate-current-environment/live-validation-gate.stdout.json \
  2> docs/runs/2026-07-09-live-validation-gate-current-environment/live-validation-gate.stderr.txt
adb devices -l > adb-devices-after.txt 2>&1
```

Checksum generation:

```bash
(cd docs/runs/2026-07-09-live-validation-gate-current-environment && shasum -a 256 * > checksums.sha256)
```

## Gate Results

- CLI exit status: `0`
- Gate JSON status: `passed`
- Device: `emulator-5554`
- Failed checks: none

Per-check result:

| Check | Result | Important output |
|---|---|---|
| `adb-device-present` | passed | `emulator-5554 device product:sdk_gphone64_arm64 model:sdk_gphone64_arm64 device:emu64a` |
| `boot-completed` | passed | `sys.boot_completed=1` |
| `boot-animation-stopped` | passed | `init.svc.bootanim=stopped` |
| `android-layout-json` | passed | `android layout --pretty --device emulator-5554` returned a JSON list for the launcher UI. |
| `uiautomator-dump` | passed | `UI hierchary dumped to: /sdcard/window_dump.xml` |

## Environment

- Android CLI: `1.0.15498356`
- Android CLI launcher: `1.0.15498356`
- SDK path: `/Users/80268204/Library/Android/sdk`
- adb: Android Debug Bridge `1.0.41`, platform-tools `37.0.0-14910828`
- Emulator: `36.5.11.0` build `15261927`
- Device: `emulator-5554`, `sdk_gphone64_arm64`, `emu64a`
- Host OS: macOS `26.1` build `25B78`, Darwin `25.1.0`, arm64

## Artifact Inventory

- `README.md` - this run record.
- `run-metadata.txt` - run timestamp, issue, device, and run directory.
- `android-version.txt` - Android CLI version.
- `android-info.txt` - Android CLI SDK path and launcher version.
- `adb-version.txt` - adb/platform-tools version.
- `emulator-version.txt` - emulator version.
- `host-uname.txt` - host kernel details.
- `host-sw-vers.txt` - host macOS version.
- `adb-devices-before.txt` - device list before the gate.
- `adb-devices-after.txt` - device list after the gate.
- `live-validation-gate.json` - machine-readable gate result.
- `live-validation-gate.stdout.json` - stdout copy of the gate JSON.
- `live-validation-gate.stderr.txt` - gate stderr; empty for this run.
- `live-validation-gate-exit.txt` - gate process exit status.
- `checksums.sha256` - SHA-256 checksums for run artifacts.

## Known Gaps

- This is only the generic environment gate. Wikipedia target-surface smoke is
  tracked by #33 and has not been run here.
- #23 remains open/quarantined until a passing app-level smoke and a valid
  baseline/defect matched pair exist.
- No screenshots were captured by this generic gate. The required evidence for
  this slice is command output and layout/UIAutomator health.
