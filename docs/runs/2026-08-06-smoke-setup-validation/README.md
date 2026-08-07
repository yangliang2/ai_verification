# M9 non-holdout smoke validation

Status: complete as a local-only setup and runtime smoke. This run is not a new M9 qualification, is excluded from the formal denominator, does not consume the M9 holdout, and does not change the formal M9 conclusion (`Not Supported`).

The purpose was to validate the recommended next step after the formal result: prove that the APK/build/install/launch/process-death/evidence path is usable on the disposable API-35 emulator, using two immutable local fixture inputs with neutral labels. The run also checks one positive persistence path and one bounded negative persistence path; it is not a general capability claim.

## Run identity and boundary

- Run ID: `2026-08-06-smoke-setup-validation`
- Repository branch: `m9-smoke-setup-validation`
- Repository base: exact `origin/main` at `716ce60020916127176b24c71e3829f603468a5e`
- Backend: none; no remote service or agent runtime was invoked by the app
- Requested/effective model identity: not applicable
- Device: disposable `emulator-5554`, AVD `aiverify_api35`, `sdk_gphone64_arm64`, API 35
- App package: `com.example.android.architecture.blueprints.main`
- Activity: `com.example.android.architecture.blueprints.todoapp.TodoActivity`
- Network policy: not changed
- Formal M9 holdout: not run
- Formal M9 denominator: unchanged

The original `issue-73-accessibility-slice` worktree was not used or modified. The two source inputs were clean, immutable local worktrees:

| Neutral input | Local source commit | Source tree | APK SHA-256 |
| --- | --- | --- | --- |
| `fixture-a` | `ee66e1526b84c026615df032c705842b7d2a521f` | `19455e693ec8c96c37a56aec55059a220826c5a3` | `d38b30f17010da114b5585dadec8326eb76b04dfbae4a175f7cb2840a0093c66` |
| `fixture-b` | `208575f78d59716669d0733b5ed3e08797b08787` | `34998af23aed59aa17eaf915d848ab1b916a63e2` | `61063a0fd247eb03d1bd251b0d9359c3c2a5ea07cb8abe4b38d3daae57c153ac` |

The exact package identity for both APKs was checked with `apkanalyzer`: version code `1`, version name `1.0`, min SDK `21`, target SDK `35`, and the activity above.

## Exact commands and results

### Build and package identity

Commands run in each fixture worktree:

```text
./gradlew --offline --no-daemon assembleDebug
./gradlew --no-daemon assembleDebug
apkanalyzer apk summary app/build/outputs/apk/debug/app-debug.apk
apkanalyzer manifest min-sdk app/build/outputs/apk/debug/app-debug.apk
apkanalyzer manifest target-sdk app/build/outputs/apk/debug/app-debug.apk
apkanalyzer manifest print app/build/outputs/apk/debug/app-debug.apk
shasum -a 256 app/build/outputs/apk/debug/app-debug.apk
```

The initial offline attempt failed because the local cache did not contain `kotlinx-coroutines-test`, AndroidX Test core/JUnit/rules, and `hilt-android-testing`. This was an environment/cache limitation; it was not used as a source result. The online builds then passed:

| Input | Build result | Duration | Gradle actionable/executed/up-to-date | APK size |
| --- | --- | ---: | --- | ---: |
| `fixture-a` | pass | 1m12s | 71 / 28 / 43 | 24,681,606 bytes |
| `fixture-b` | pass | 11s | 71 / 28 / 43 | 24,681,461 bytes |

The Android tool reported the known SDK XML warning (“version 4 encountered by tool understanding up to 3”); both online builds still completed successfully.

### Repository test check

Command run from this clean `origin/main` worktree:

```text
/usr/bin/time -p uv run --extra dev pytest -q -rA tests/bench/test_m9_formal.py
```

Result: 3 passed, 0 failed, 0 skipped; real time `0.19s` (user `0.15s`, sys `0.03s`). The passing checks covered terminal/fail-closed oracle behavior, six-row accountability reconciliation, and treating an uninstalled package as clean.

Tooling versions are recorded in [`tool-versions.json`](tool-versions.json).

### Device setup and launch

The package was intentionally absent before each install. The exact pre-install command was:

```text
adb -s emulator-5554 shell pm clear com.example.android.architecture.blueprints.main
```

It returned exit code `1` and `Failed` for the absent package in both setup attempts. This is the setup condition covered by the future-only package-clear handling; it was not treated as an app failure.

Install and launch commands were:

```text
adb -s emulator-5554 install -r -d <fixture>/app/build/outputs/apk/debug/app-debug.apk
adb -s emulator-5554 shell am start -W -n com.example.android.architecture.blueprints.main/com.example.android.architecture.blueprints.todoapp.TodoActivity
adb -s emulator-5554 shell am force-stop com.example.android.architecture.blueprints.main
```

Both installs returned `Success`; both cold launches returned `Status: ok` for the expected activity. Launch timings were `991ms` total / `993ms` wait for `fixture-a`, and `909ms` total for `fixture-b`.

Layout and log evidence was captured with:

```text
android layout --pretty --device=emulator-5554 -o <artifact>.json
android layout --diff --device=emulator-5554 -o <artifact>.json
```

Initial screenshots (`initial.png`) were captured and visually inspected immediately. Both showed the expected empty Todo screen. The initial layout contained 11 elements for both inputs; after force-stop/relaunch, the layout diff was empty (`added=[]`, `modified=[]`). A and B logcats contained no `FATAL EXCEPTION` or `AndroidRuntime: FATAL` marker.

### Bounded task flows

The interaction sequence was scripted with `adb shell input` and checked at each meaningful state with `android layout`: create a task, commit title/description input, save, open the task, edit the title, save, force-stop/relaunch, and reopen the task. The IME required an explicit Enter key event to commit text before saving; the first uncommitted-input attempt on `fixture-b` produced the app's ordinary `Tasks cannot be empty` validation message, after which the correctly committed sequence was completed. This operator-input correction is not a formal retry or lane replacement.

Observed results:

| Input | Create | Edit/save UI | After force-stop/reopen | Smoke interpretation |
| --- | --- | --- | --- | --- |
| `fixture-a` | pass; `SmokeControlA` | `SmokeControlB` visible; `Task saved` | `SmokeControlB` and `SmokeDescriptionControl` visible | positive persistence path passed |
| `fixture-b` | pass; `SmokeTitleA` | `Task saved`, but list still showed `SmokeTitleA` | `SmokeTitleA` and `SmokeDescriptionA` visible | bounded negative persistence behavior observed |

The `fixture-b` observation is deliberately recorded as observed behavior, not converted into a formal M9 finding or aggregate result.

## Artifact inventory

- `apk-a/initial.png`, `layout-initial.json`, `layout-after-process-death.json`, task-flow layout checkpoints, and `logcat.txt`/`control-task-logcat.txt`.
- `apk-b/initial.png`, `layout-initial.json`, `layout-after-process-death.json`, task-flow layout checkpoints, and `logcat.txt`.
- `smoke-summary.json`: machine-readable run result and claim boundary.
- `tool-versions.json`: Android/ADB/Gradle/JVM/uv/device identity.
- `checksums.sha256`: SHA-256 ledger for every committed raw evidence file and metadata file except the ledger itself.

Key artifact checksums:

| Artifact | SHA-256 |
| --- | --- |
| `apk-a/initial.png` | `89e550ad01bc833edee7d59bd2a0ba3dc3d81e6806c71ff56b1907b5690e98c2` |
| `apk-b/initial.png` | `49c29ebeb759d003de707d4ea02c2dd54d99b497194e28f4865f0be554c3a3d2` |
| `apk-a/layout-after-process-death.json` | `cd4d51be3ffd2b56d7c65534983af09c4b5f985949d7e25ed47bd1bea6252c76` |
| `apk-b/layout-after-process-death.json` | `cd4d51be3ffd2b56d7c65534983af09c4b5f985949d7e25ed47bd1bea6252c76` |
| `apk-a/control-reopened-detail.json` | `e98128a2c504c115a51f0df8801325cbb24e4dc43b7e411e42113ddff9f0a682` |
| `apk-b/reopened-detail.json` | `15951caaad1d57af8190a26b53ed93085a64807b04de84f5d65e47c0ec51edd3` |
| `apk-a/logcat.txt` | `a82563c3d8f16e91bec51fba6bf550e3b14bf3a512af2e95ae2b37eab922654d` |
| `apk-b/logcat.txt` | `fadfdd2bf0a75e5cf21e981f25441b7a6272fce7d80a9df06d76b90576a636ca` |

## Manual steps, known gaps, and claim boundary

No user manual action was required; the operator input was scripted. The screenshots were visually inspected by the agent immediately after capture, as required by the Android validation workflow.

This smoke does not provide an independent falsification review, hidden-mapping release, formal cohort execution, model/backend comparison, oracle adjudication, OEM/ColorOS claim, success/recall/integrity rate, benchmark result, or production/upstream validation. It uses one disposable emulator and two local public-project fixture worktrees. It must not be used to claim M9 support, rewrite M8, or alter the frozen #136 contract.

The emulator was cleaned after evidence capture with:

```text
adb -s emulator-5554 uninstall com.example.android.architecture.blueprints.main
adb -s emulator-5554 shell pm path com.example.android.architecture.blueprints.main
```

The uninstall returned `Success`; the final `pm path` returned exit code `1`, confirming the package was absent.
