# 2026-07-08 Wikipedia oversized saved-state Seed Progress Record

Primary issue: [#23](https://github.com/yangliang2/ai_verification/issues/23)
- M2 process-death/save-state oversized Bundle seed.

Parent context: [#13](https://github.com/yangliang2/ai_verification/issues/13)
is closed as the M2-alpha scoping issue. This record is post-#13 seed expansion
work and is **not** a benchmark-wide metric claim.

## Status

This record captures a seed implementation plus additional live validation
progress. It still does **not** establish a valid live matched-pair result.

Current evidence state:

| lane | result | evidence |
|---|---|---|
| Local seed regression | pass | `tests/bench/test_goldset_process_death_03_oversized_saved_state.py` |
| Patch applicability | pass | `manual-defect/patch-dry-run-after-restore.txt` |
| Manual baseline UI path | L1 inconclusive, L2 pass | `manual-baseline/verdict.json` |
| Manual defect UI path | blocked before boundary | `manual-defect/startup-anr-logcat.txt` |
| Direct defect probe after reboot | blocked by emulator boot state | `manual-defect-direct-probe/boot-wait.txt` |

Implemented in this repo:

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

Patch applicability check after restoring the host checkout:

```bash
patch --dry-run -p1 -d /Users/80268204/hosts/wikipedia \
  < bench/goldset/patches/wikipedia-process-death-03-oversized-saved-state.patch
```

Result:

```text
patching file 'app/src/main/java/org/wikipedia/search/SearchActivity.kt'
```

Manual baseline setup and UI traversal:

```bash
(cd /Users/80268204/hosts/wikipedia && ./gradlew assembleDevDebug --no-daemon)
adb -s emulator-5554 install -r /Users/80268204/hosts/wikipedia/app/build/outputs/apk/dev/debug/app-dev-debug.apk
adb -s emulator-5554 shell am force-stop org.wikipedia.dev
adb -s emulator-5554 shell pm clear org.wikipedia.dev
adb -s emulator-5554 shell cmd uimode night no
adb -s emulator-5554 push manual-baseline/preseeded-prefs.xml /data/local/tmp/issue23-prefs.xml
adb -s emulator-5554 shell chmod 0644 /data/local/tmp/issue23-prefs.xml
adb -s emulator-5554 shell run-as org.wikipedia.dev mkdir -p shared_prefs
adb -s emulator-5554 shell run-as org.wikipedia.dev \
  cp /data/local/tmp/issue23-prefs.xml shared_prefs/org.wikipedia.dev_preferences.xml
adb -s emulator-5554 logcat -c
adb -s emulator-5554 shell am start -W -a android.intent.action.MAIN \
  -c android.intent.category.LAUNCHER -n org.wikipedia.dev/org.wikipedia.DefaultIcon
android layout --pretty --device emulator-5554
adb -s emulator-5554 shell input tap <nav_tab_search center>
adb -s emulator-5554 shell input tap <search_card center>
adb -s emulator-5554 shell input tap <search_src_text center>
adb -s emulator-5554 shell input text zzoversize
adb -s emulator-5554 shell input keyevent BACK
android screen capture -o manual-baseline/before-event-screen.png
adb -s emulator-5554 shell cmd uimode night yes
android layout --pretty --device emulator-5554
android screen capture -o manual-baseline/after-event-screen.png
adb -s emulator-5554 logcat -d
```

Manual baseline result:

- `manual-baseline/build-exit.txt`: `exit_status=0`, `duration_seconds=7`
- Gradle: `BUILD SUCCESSFUL in 7s`, 77 actionable tasks up-to-date
- `manual-baseline/install.txt`: `Success`
- `manual-baseline/am-start-1.txt`: `Status: ok`, `LaunchState: COLD`,
  `Activity: org.wikipedia.dev/org.wikipedia.main.MainActivity`,
  `WaitTime: 30798`
- `manual-baseline/launch-ready.txt`: attempt 1 reached `nav_tab_search`
- `manual-baseline/search-tab-ready.txt`: attempt 1 reached `search_card`
- `manual-baseline/search-page-ready.txt`: attempt 2 reached `search_src_text`
- `manual-baseline/before-event-ready.txt`: attempt 1 reached
  `search_src_text`
- `manual-baseline/after-event-ready.txt`: attempt 1 reached
  `search_src_text`
- `manual-baseline/verdict.json`: L1 `inconclusive`, L2 `pass`
- Baseline APK SHA-256:
  `feddcf5e29f5182bfc5c58ec42472358332d6a4e72b362ff397c51c56a445d3b`

The first baseline attempt used sentinel `zzoversizeqx`; Android input
stabilized the field value as `zzoversize`. The run spec and regression test
now use `zzoversize`, matching the observed stable UI value.

Manual defect setup and UI attempt:

```bash
patch --dry-run -p1 -d /Users/80268204/hosts/wikipedia \
  < bench/goldset/patches/wikipedia-process-death-03-oversized-saved-state.patch
patch -p1 -d /Users/80268204/hosts/wikipedia \
  < bench/goldset/patches/wikipedia-process-death-03-oversized-saved-state.patch
(cd /Users/80268204/hosts/wikipedia && ./gradlew assembleDevDebug --no-daemon)
adb -s emulator-5554 install -r /Users/80268204/hosts/wikipedia/app/build/outputs/apk/dev/debug/app-dev-debug.apk
adb -s emulator-5554 shell am force-stop org.wikipedia.dev
adb -s emulator-5554 shell pm clear org.wikipedia.dev
adb -s emulator-5554 shell cmd uimode night no
adb -s emulator-5554 push manual-defect/preseeded-prefs.xml /data/local/tmp/issue23-prefs.xml
adb -s emulator-5554 shell chmod 0644 /data/local/tmp/issue23-prefs.xml
adb -s emulator-5554 shell run-as org.wikipedia.dev mkdir -p shared_prefs
adb -s emulator-5554 shell run-as org.wikipedia.dev \
  cp /data/local/tmp/issue23-prefs.xml shared_prefs/org.wikipedia.dev_preferences.xml
adb -s emulator-5554 logcat -c
adb -s emulator-5554 shell am start -W -a android.intent.action.MAIN \
  -c android.intent.category.LAUNCHER -n org.wikipedia.dev/org.wikipedia.DefaultIcon
android layout --pretty --device emulator-5554
```

Manual defect result:

- `manual-defect/build-exit.txt`: `exit_status=0`, `duration_seconds=100`
- Gradle: `BUILD SUCCESSFUL in 1m 39s`, 77 actionable tasks:
  5 executed, 72 up-to-date
- `manual-defect/install.txt`: `Success`
- `manual-defect/am-start-1.txt`: `Status: ok`, `WaitTime: 28844`
- `manual-defect/am-start-2.txt`: `Status: timeout`, `WaitTime: 21991`
- `manual-defect/launch-layout-1.json`: 0 bytes
- `manual-defect/launch-layout-2.json`: 0 bytes
- `manual-defect/startup-anr-logcat.txt` includes startup ANRs before the
  SearchActivity/save-state boundary:
  - `Process ... org.wikipedia.dev ... failed to attach`
  - `Killing ... org.wikipedia.dev ... start timeout`
  - `ANR in org.wikipedia.dev`
  - `Reason: Process ... org.wikipedia.dev ... failed to complete startup`
- No `TransactionTooLargeException` or target save-state L1 was captured.
- Defect APK SHA-256:
  `f876af648d5de85e6b08a0de294df17fa45079eac787d5d8470f55f3cca5e68b`

Host checkout restoration:

```bash
patch -R -p1 -d /Users/80268204/hosts/wikipedia \
  < bench/goldset/patches/wikipedia-process-death-03-oversized-saved-state.patch
patch --dry-run -p1 -d /Users/80268204/hosts/wikipedia \
  < bench/goldset/patches/wikipedia-process-death-03-oversized-saved-state.patch
```

Result:

```text
patching file 'app/src/main/java/org/wikipedia/search/SearchActivity.kt'
```

Direct defect probe reboot attempt:

```bash
adb -s emulator-5554 reboot
adb -s emulator-5554 wait-for-device
adb -s emulator-5554 shell getprop sys.boot_completed
```

Result:

- `manual-defect-direct-probe/reboot-duration.txt`:
  `duration_seconds=225`
- `manual-defect-direct-probe/boot-wait.txt`: attempts 1 through 60 all had an
  empty `boot_completed` value
- `manual-defect-direct-probe/boot-completed.txt`: empty
- No direct `SearchActivity` probe was run after reboot because the emulator did
  not report boot completion.

## Environment

- Host: `/Users/80268204/hosts/wikipedia`, tarball checkout of Wikimedia Android
  app used by prior M2 seeds.
- Package: `org.wikipedia.dev`
- Launcher alias: `org.wikipedia.DefaultIcon`
- Target Activity: `org.wikipedia.search.SearchActivity`
- Device: `emulator-5554`, AVD `medium_phone`, `sdk_gphone64_arm64`,
  Android 16 / API 36
- Android CLI: `1.0.15498356`
- adb: `1.0.41`, platform-tools `37.0.0-14910828`
- Python: `3.12.13`
- pytest: `9.1.1`

## Artifact Inventory

- `baseline/` - initial blocked baseline setup attempt retained for audit.
- `manual-baseline/` - successful manual baseline traversal, screenshots,
  layouts, logcat, APK checksum, build/install/setup logs, and verdict JSON.
- `manual-defect/` - defect patch apply/build/install logs, startup ANR logcat,
  empty layout captures, abort marker, patch reversal logs, and defect APK
  checksum.
- `manual-defect-direct-probe/` - emulator reboot and boot-completion evidence
  for the skipped direct probe.
- `checksums.sha256` - SHA-256 manifest for this progress record.

## Known Gaps

- No valid live defect runner invocation was produced in this record.
- The valid baseline is a manual UI traversal, not a full runner matched-pair
  invocation.
- The manual defect attempt did not reach `SearchActivity`; it blocked in app
  startup ANR before the intended save-state boundary.
- The direct defect probe was not run because the emulator failed to report
  `sys.boot_completed=1` after reboot.
- This seed should not be counted as an audited M2 caught/missed data point
  until a future run captures a valid baseline/defect matched pair.
