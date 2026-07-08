# 2026-07-08 Wikipedia oversized saved-state Seed Progress Record

Primary issue: [#23](https://github.com/yangliang2/ai_verification/issues/23)
- M2 process-death/save-state oversized Bundle seed.

Parent context: [#13](https://github.com/yangliang2/ai_verification/issues/13)
is closed as the M2-alpha scoping issue. This record is post-#13 seed expansion
work and is **not** a benchmark-wide metric claim.

## Status

This record captures a seed implementation and a blocked live validation attempt.
It does **not** establish a valid live matched-pair result yet.

Implemented locally:

| item | path |
|---|---|
| Run spec | `bench/goldset/run-specs/wikipedia-process-death-03-oversized-saved-state.yaml` |
| Seed spec | `bench/goldset/specs/wikipedia-process-death-03-oversized-saved-state.md` |
| Injected patch | `bench/goldset/patches/wikipedia-process-death-03-oversized-saved-state.patch` |
| L1 crash fixture | `bench/goldset/fixtures/wikipedia-process-death-03-oversized-saved-state/crash-logcat.txt` |
| Regression tests | `tests/bench/test_goldset_process_death_03_oversized_saved_state.py` |

## Source Pattern

The seed targets `bench/goldset/candidates.md` P2:
Tusky issue #419, where `onSaveInstanceState` saved a full Bitmap-like payload
and crashed with `TransactionTooLargeException` when Android saved Activity
state.

The Wikipedia injection writes a 2 MiB byte array from
`SearchActivity.onSaveInstanceState()`. The expected detector is L1
`crash_stability` from `FATAL EXCEPTION` / `TransactionTooLargeException`
logcat evidence.

## Discarded C4 Probe

The issue originally targeted a C4 dialog-state seed. A local probe against
Wikipedia `MenuNavTabDialog` showed the control surface is invalid: the baseline
sheet itself does not remain visible across the `dark_mode` / `uiMode` boundary.
That would make the baseline fail before any defect injection, so the C4 host
surface was discarded.

## Commands Run

Focused local regression:

```bash
.venv/bin/pytest tests/bench/test_goldset_process_death_03_oversized_saved_state.py -q
```

Result:

```text
4 passed
```

Full local regression:

```bash
.venv/bin/pytest -q
```

Result:

```text
251 passed, 2 warnings
```

Patch applicability check:

```bash
patch --dry-run -p1 -d /Users/80268204/hosts/wikipedia \
  < bench/goldset/patches/wikipedia-process-death-03-oversized-saved-state.patch
```

Result:

```text
patching file 'app/src/main/java/org/wikipedia/search/SearchActivity.kt'
```

Baseline live setup attempt:

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

Setup result:

- `baseline/build-exit.txt`: `exit_status=0`, `duration_seconds=28`
- Gradle: `BUILD SUCCESSFUL in 27s`, 77 actionable tasks up-to-date
- `baseline/install.txt`: `Success`
- `baseline/am-start-1.txt`: `Status: ok`, `WaitTime: 20149`
- `baseline/prelaunch-layout-1-1.err`: `ERROR: null root node returned by UiTestAutomationBridge`
- The prelaunch layout command later timed out after 90 seconds before a runner
  invocation was started.

## Environment

- Host: `/Users/80268204/hosts/wikipedia`, tarball checkout of Wikimedia Android
  app used by prior M2 seeds.
- Package: `org.wikipedia.dev`
- Launcher alias: `org.wikipedia.DefaultIcon`
- Device: `emulator-5554`, AVD `medium_phone`, `sdk_gphone64_arm64`,
  Android 16 / API 36
- Android CLI: `1.0.15498356`
- adb: `1.0.41`, platform-tools `37.0.0-14910828`
- Python: `3.12.13`
- pytest: `9.1.1`
- Baseline APK SHA-256:
  `feddcf5e29f5182bfc5c58ec42472358332d6a4e72b362ff397c51c56a445d3b`

## Artifact Inventory

- `baseline/build.stdout.txt`, `baseline/build.stderr.txt`,
  `baseline/build-exit.txt`
- `baseline/apk.sha256`
- `baseline/install.txt`, `baseline/force-stop.txt`, `baseline/pm-clear.txt`,
  `baseline/night-no.txt`
- `baseline/preseeded-prefs.xml` and prefs push/copy logs
- `baseline/am-start-1.txt`
- `baseline/prelaunch-layout-1-1.json` and
  `baseline/prelaunch-layout-1-1.err`
- `baseline/prelaunch-timeout.txt`
- `checksums.sha256` - SHA-256 manifest for this progress record

## Known Gaps

- No valid live baseline or defect runner invocation was produced in this record.
- The emulator showed cold-start and UI-automation instability: `am start -W`
  reported success, but Android CLI layout capture returned a null root and then
  timed out before the app could be confirmed ready.
- This seed should not be counted as an audited M2 caught/missed data point until
  a future run captures a valid baseline/defect matched pair.
