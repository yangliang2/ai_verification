# 2026-07-09 Wikipedia oversized saved-state live retry

Primary issue: [#23](https://github.com/yangliang2/ai_verification/issues/23)

This run continues the live-validation follow-up for
`wikipedia-process-death-03-oversized-saved-state`. It does **not** produce a
valid matched-pair result and should not be counted as an M2 caught/missed data
point.

## Status

Blocked by the Android execution environment before a valid baseline/control
lane could reach the target screen.

| lane | result | evidence |
|---|---|---|
| Baseline retry | blocked before `nav_tab_search` | `baseline/launch-not-focused-logcat.txt` |
| Defect retry | not run | `environment-refresh/no-live-continuation.txt` |
| Emulator refresh | unstable UI automation | `environment-refresh/layout-uiautomator-failure.txt` |
| Patch cleanliness | pass | host patch dry-run still applies cleanly |

## What Happened

The baseline APK built and installed successfully, but `org.wikipedia.dev`
failed during process startup before the UI reached the main navigation surface.
`am start -W` returned `Status: ok`, but the app task closed and the launcher
remained focused. Logcat shows `org.wikipedia.dev` failed to attach, then was
killed for start timeout / ANR.

After that, the old AVD was stopped and several emulator refresh paths were
tried:

- `android emulator stop/start medium_phone`
- SDK emulator cold start with `-no-snapshot-load -no-snapshot-save -no-audio`
- foreground SDK emulator cold start to keep the emulator process alive while
  waiting for boot completion

The foreground cold start eventually reached `boot_completed=1`, but Android
CLI layout / UIAutomator remained unusable: `android layout` could not retrieve
`/sdcard/window_dump.xml`, and direct `uiautomator dump` hung.

Because the baseline lane could not reach a valid UI state and the UI automation
channel remained unreliable, no defect lane was run.

## Commands Run

Baseline build/install/setup:

```bash
(cd /Users/80268204/hosts/wikipedia && ./gradlew assembleDevDebug --no-daemon)
adb -s emulator-5554 install -r /Users/80268204/hosts/wikipedia/app/build/outputs/apk/dev/debug/app-dev-debug.apk
adb -s emulator-5554 shell am force-stop org.wikipedia.dev
adb -s emulator-5554 shell pm clear org.wikipedia.dev
adb -s emulator-5554 shell cmd uimode night no
adb -s emulator-5554 push baseline/preseeded-prefs.xml /data/local/tmp/issue23-prefs.xml
adb -s emulator-5554 shell chmod 0644 /data/local/tmp/issue23-prefs.xml
adb -s emulator-5554 shell run-as org.wikipedia.dev mkdir -p shared_prefs
adb -s emulator-5554 shell run-as org.wikipedia.dev \
  cp /data/local/tmp/issue23-prefs.xml shared_prefs/org.wikipedia.dev_preferences.xml
adb -s emulator-5554 logcat -c
adb -s emulator-5554 shell am start -W -a android.intent.action.MAIN \
  -c android.intent.category.LAUNCHER -n org.wikipedia.dev/org.wikipedia.DefaultIcon
android layout --pretty --device emulator-5554
```

Baseline result:

- `baseline/build-exit.txt`: `exit_status=0`, `duration_seconds=33`
- Gradle: `BUILD SUCCESSFUL in 32s`, 77 actionable tasks:
  2 executed, 4 from cache, 71 up-to-date
- `baseline/install.txt`: `Success`
- `baseline/am-start-1.txt`: `Status: ok`, `Activity:
  org.wikipedia.dev/org.wikipedia.main.MainActivity`, `WaitTime: 23247`
- `baseline/abort.txt`: launcher remained focused; app task closed before
  `nav_tab_search`
- Baseline APK SHA-256:
  `396a3edda8634d0035c5d9794cb0fae51e8d1851f162195889d2c397663308d6`

Baseline logcat highlights:

- `Process ... org.wikipedia.dev ... failed to attach`
- `Killing ... org.wikipedia.dev ... start timeout`
- later retry: `ANR in org.wikipedia.dev`
- No valid before/after layout pair was captured.

Patch cleanliness check:

```bash
patch --dry-run -p1 -d /Users/80268204/hosts/wikipedia \
  < bench/goldset/patches/wikipedia-process-death-03-oversized-saved-state.patch
```

Result:

```text
patching file 'app/src/main/java/org/wikipedia/search/SearchActivity.kt'
```

Emulator refresh commands:

```bash
android emulator stop medium_phone
android emulator start medium_phone
adb devices -l
adb -s emulator-5554 shell getprop sys.boot_completed
adb -s emulator-5554 shell getprop init.svc.bootanim

/Users/80268204/Library/Android/sdk/emulator/emulator \
  @medium_phone -no-snapshot-load -no-snapshot-save -no-audio

android layout --pretty --device emulator-5554
adb -s emulator-5554 shell uiautomator dump /sdcard/window_dump.xml
```

Emulator refresh results:

- Original qemu process had been running since 2026-06-18.
- `android emulator stop medium_phone`: `duration_seconds=13`
- `android emulator start medium_phone`: `exit_status=0`,
  `duration_seconds=14`, but the emulator process later disappeared and
  `adb devices` became empty.
- SDK cold start reached `boot_completed=1` in
  `environment-refresh/sdk-emulator-cold-start-wait.txt`, but did not remain
  stable after the launcher shell exited.
- Foreground cold start #1 reached `boot_completed=1` at attempt 68, then was
  stopped manually.
- Foreground cold start #2 reached `boot_completed=1` at attempt 31
  (`duration_seconds=120`), but UI automation remained unusable.
- `environment-refresh/layout-uiautomator-failure.txt` records the exact
  Android CLI / UIAutomator failure.

## Environment

- Host project: `/Users/80268204/hosts/wikipedia`
- Package: `org.wikipedia.dev`
- Launcher alias: `org.wikipedia.DefaultIcon`
- Device/AVD: `emulator-5554`, `medium_phone`, `sdk_gphone64_arm64`
- Android CLI: `1.0.15498356`
- adb: platform-tools `37.0.0-14910828`
- Emulator: `36.5.11.0`

## Artifact Inventory

- `baseline/` - baseline build/install/setup logs, launch logs, launcher-only
  layouts, window/activity dumps, and startup ANR logcat.
- `environment-refresh/` - Android CLI emulator stop/start logs, SDK emulator
  cold-start logs, boot-wait transcripts, UIAutomator failure note, final device
  state files, and emulator log.
- `checksums.sha256` - SHA-256 manifest for this run record.

## Known Gaps

- No valid baseline verdict was produced on 2026-07-09.
- No defect lane was run on 2026-07-09.
- The seed remains implemented, but #23 must stay open until a future run can
  capture a valid baseline/defect matched pair on a stable emulator or device.
