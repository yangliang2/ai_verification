# 2026-07-09 Wikipedia app smoke gate

Primary issue: [#32](https://github.com/yangliang2/ai_verification/issues/32)

Parent PRD: [#30](https://github.com/yangliang2/ai_verification/issues/30)

Related blocked seed: [#23](https://github.com/yangliang2/ai_verification/issues/23)

## Status

Wikipedia app-level smoke gate: **passed**.

This run first executes the generic Android environment gate, then launches
`org.wikipedia.dev/org.wikipedia.DefaultIcon`, verifies that the app is in the
foreground window state, and verifies that Android CLI layout contains the target
main-feed search tab surface: `resource-id=nav_tab_search`,
`content-desc=Search`.

This is not a #23 seed result. It only proves that the current environment and
Wikipedia app entry surface are healthy enough to start seed-specific
baseline/defect matched-pair work.

## Commands Run

Tool, package, and environment capture:

```bash
android --version > android-version.txt 2>&1
adb version > adb-version.txt 2>&1
android info > android-info.txt 2>&1
/Users/80268204/Library/Android/sdk/emulator/emulator -version > emulator-version.txt 2>&1
sw_vers > host-sw-vers.txt 2>&1
uname -a > host-uname.txt 2>&1
adb -s emulator-5554 shell pm path org.wikipedia.dev > pm-path.txt 2>&1
adb -s emulator-5554 shell dumpsys package org.wikipedia.dev \
  | rg -n "versionName|versionCode" > package-version.txt
adb devices -l > adb-devices-before.txt 2>&1
adb -s emulator-5554 shell am force-stop org.wikipedia.dev > force-stop.txt 2>&1
adb -s emulator-5554 logcat -c > logcat-clear.txt 2>&1
```

Gate execution:

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.live_validation_gate \
  --device emulator-5554 \
  --timeout-seconds 30 \
  --app-settle-seconds 5 \
  --app-package org.wikipedia.dev \
  --app-activity org.wikipedia.DefaultIcon \
  --target-resource-id nav_tab_search \
  --target-content-desc Search \
  --output docs/runs/2026-07-09-wikipedia-app-smoke-gate/live-validation-gate.json \
  > docs/runs/2026-07-09-wikipedia-app-smoke-gate/live-validation-gate.stdout.json \
  2> docs/runs/2026-07-09-wikipedia-app-smoke-gate/live-validation-gate.stderr.txt
```

Post-gate evidence:

```bash
adb devices -l > adb-devices-after.txt 2>&1
android layout --pretty --device emulator-5554 > layout-after.json 2> layout-after.err
adb -s emulator-5554 shell dumpsys window \
  | rg -n "mCurrentFocus|mFocusedApp|org\\.wikipedia\\.dev" > window-focus.txt
adb -s emulator-5554 logcat -d \
  | rg -n "ActivityTaskManager: START|Displayed org\\.wikipedia\\.dev|MainActivity\\.HOME\\.show|org\\.wikipedia\\.dev" \
  | head -n 80 > logcat-launch-summary.txt
adb -s emulator-5554 logcat -d \
  | rg -n "ANR in org\\.wikipedia|FATAL EXCEPTION|AndroidRuntime: FATAL|failed to attach|start timeout|TransactionTooLarge" \
  > logcat-critical-scan.txt || printf 'no critical crash/startup lines matched\n' > logcat-critical-scan.txt
(cd docs/runs/2026-07-09-wikipedia-app-smoke-gate && shasum -a 256 * > checksums.sha256)
```

## Gate Results

- CLI exit status: `0`
- Gate JSON status: `passed`
- Failed checks: none
- Package: `org.wikipedia.dev`
- Launcher alias/activity: `org.wikipedia.DefaultIcon`
- Installed APK path: `/data/app/~~XUl1dstnv62Sug4uwDfhtw==/org.wikipedia.dev-MIJBLDYjnejHPphOyJgfWg==/base.apk`
- App version: `versionCode=50594`, `versionName=50594-dev-2026-07-07`

Per-check result:

| Check | Result | Important output |
|---|---|---|
| `adb-device-present` | passed | `emulator-5554 device product:sdk_gphone64_arm64 model:sdk_gphone64_arm64 device:emu64a` |
| `boot-completed` | passed | `sys.boot_completed=1` |
| `boot-animation-stopped` | passed | `init.svc.bootanim=stopped` |
| `android-layout-json` | passed | Android CLI returned a JSON list before app launch. |
| `uiautomator-dump` | passed | `UI hierchary dumped to: /sdcard/window_dump.xml` |
| `app-launch` | passed | `Status: ok`, `LaunchState: COLD`, `Activity: org.wikipedia.dev/org.wikipedia.main.MainActivity`, `TotalTime: 5308`, `WaitTime: 5320` |
| `app-foreground-package` | passed | `dumpsys window` contained `org.wikipedia.dev`; no WindowManager last-ANR since boot. |
| `app-target-surface` | passed | Layout contained `resource-id=nav_tab_search` and `content-desc=Search`. |

Post-gate log scan found no `ANR in org.wikipedia`, `FATAL EXCEPTION`,
`failed to attach`, `start timeout`, or `TransactionTooLarge` lines.

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
- `run-metadata.txt` - run timestamp, issue, device, package, activity, and target surface.
- `android-version.txt` - Android CLI version.
- `android-info.txt` - Android CLI SDK path and launcher version.
- `adb-version.txt` - adb/platform-tools version.
- `emulator-version.txt` - emulator version.
- `host-uname.txt` - host kernel details.
- `host-sw-vers.txt` - host macOS version.
- `pm-path.txt` - installed Wikipedia APK path.
- `package-version.txt` - filtered package version metadata.
- `adb-devices-before.txt` - device list before the gate.
- `adb-devices-after.txt` - device list after the gate.
- `force-stop.txt` - app force-stop output before launch.
- `logcat-clear.txt` - logcat clear output before launch.
- `live-validation-gate.json` - machine-readable gate result.
- `live-validation-gate.stdout.json` - stdout copy of the gate JSON.
- `live-validation-gate.stderr.txt` - gate stderr; empty for this run.
- `live-validation-gate-exit.txt` - gate process exit status.
- `window-focus.txt` - filtered post-gate window focus evidence.
- `layout-after.json` - post-gate Android CLI layout.
- `layout-after.err` - post-gate layout stderr; empty for this run.
- `logcat-launch-summary.txt` - filtered post-gate launch logcat evidence.
- `logcat-critical-scan.txt` - filtered post-gate crash/startup failure scan.
- `checksums.sha256` - SHA-256 checksums for run artifacts.

## Known Gaps

- This gate stops at the main feed search tab surface. It does not tap Search or
  enter `SearchActivity`.
- #23 still requires a valid baseline/defect matched pair after this gate.
- No screenshot was captured; this app smoke uses layout, window, and logcat
  evidence.
- Full `dumpsys package`, `dumpsys window`, and `logcat -d` outputs are not
  retained; this record keeps filtered excerpts plus the machine-readable gate
  result to limit unrelated environment noise.
