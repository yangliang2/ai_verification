# OpenCalc external-host calibration

Date: 2026-08-23 (America/New_York)

Status: **DURABLE REPOSITORY EVIDENCE**. This record and its artifacts were
committed in `0719a05` and published to the GitHub repository on 2026-08-24.
No standalone issue was opened for this exploratory calibration; publishing it
with the #197 branch does not authorize a formal population, a holdout release,
or a Verification Agent capability claim.

## Outcome

OpenCalc is suitable as a **calibration-only Android host**, with two explicit
constraints:

1. keypad actions need a fixed settle interval on this device profile; a
   zero-delay pilot dropped one input, while a 350 ms interval reproduced the
   same result in 3/3 isolated cycles;
2. upstream test suites are not fully green at the frozen commit, so their known
   baseline failures must be separated from Injection Lab/runtime outcomes.

This run proves only host build/install/launch and a deterministic local UI
slice. It did not materialize an Injection Lab pair, run Discovery Campaign,
consume a Run Spec, establish an ExecutionRecord, invoke Codex, or evaluate an
oracle.

## Frozen source and build identity

| Field | Value |
|---|---|
| Origin | `https://github.com/clementwzk/OpenCalc.git` |
| Commit | `0584d61189e916a62a3b402223b35e1d7a3093db` |
| Git tree | `8793c063c6a990ff3448fece38e62bc103952610` |
| `git archive` SHA-256 | `58d686b47f4a97f8b1127ab3de98bdf34a1c9310a221e5d5a7b4b5adcde54f3c` |
| Checkout | `/Users/peter/hosts/opencalc-calibration` (detached, clean) |
| Gradle home | `/Users/peter/hosts/.gradle-opencalc-calibration-0584d61` |
| Build variant | `debug` / `:app:assembleDebug` |
| Package | `com.darkempire78.opencalculator.debug` |
| Launcher | `com.darkempire78.opencalculator.activities.MainActivity` |
| Version | `3.2.1` (`versionCode=54`) |
| SDK | `min=21`, `compile=35`, `target=35` |
| APK | `/Users/peter/hosts/opencalc-calibration/app/build/outputs/apk/debug/app-debug.apk` |
| APK bytes | `7,378,262` |
| APK SHA-256 | `9557d4a14e3677c2db359ed683a9a064f0c624c5daa632d8bd85337de94615f7` |
| Signing certificate SHA-256 | `e5c1b7a4c96e7b68f2d5ea40a69d1158b89d94a2e4e45a4c3fc6bb914b47b83a` |

The independent-cache cold build and the subsequent offline clean rebuild
produced byte-identical APKs. After the instrumentation task uninstalled the
target app, the final reinstall's device-side `base.apk` SHA-256 matched the
local APK exactly.

## Environment

| Field | Value |
|---|---|
| macOS kernel | Darwin 25.3.0, arm64 |
| Java | OpenJDK 17.0.19 (Homebrew) |
| Gradle / AGP / Kotlin plugin | 8.10.2 / 8.8.0 / 2.0.0 |
| Android CLI | 1.0.15498356 |
| adb | 37.0.0-14910828 |
| APK inspection tools | build-tools 36.0.0 `aapt` and `apksigner` |
| Git | 2.50.1 (Apple Git-155) |
| AVD / serial | `aiverify_api35` / `emulator-5554` |
| Device | API 35, `sdk_gphone64_arm64`, `arm64-v8a` |
| Fingerprint | `google/sdk_gphone64_arm64/emu64a:15/AE3A.240806.043/12960925:userdebug/dev-keys` |
| Display | 1080x2400, density 420, auto-rotation enabled |

The cold AVD start completed in 18.20 seconds.

## Exact verification commands and results

### Source freeze

```sh
git clone --no-checkout https://github.com/clementwzk/OpenCalc.git /Users/peter/hosts/opencalc-calibration
git -C /Users/peter/hosts/opencalc-calibration checkout --detach 0584d61189e916a62a3b402223b35e1d7a3093db
git -C /Users/peter/hosts/opencalc-calibration rev-parse HEAD 'HEAD^{tree}'
git -C /Users/peter/hosts/opencalc-calibration archive --format=tar HEAD | shasum -a 256
git -C /Users/peter/hosts/opencalc-calibration status --porcelain=v1
```

Result: expected commit/tree/archive identities were observed and the checkout
was clean.

### Build and APK identity

```sh
./gradlew --version
/usr/bin/time -p ./gradlew clean :app:assembleDebug --no-daemon --console=plain
/usr/bin/time -p env GRADLE_USER_HOME=/Users/peter/hosts/.gradle-opencalc-calibration-0584d61 ./gradlew clean :app:assembleDebug --no-daemon --console=plain
/usr/bin/time -p env GRADLE_USER_HOME=/Users/peter/hosts/.gradle-opencalc-calibration-0584d61 ./gradlew --offline clean :app:assembleDebug --no-daemon --console=plain
shasum -a 256 app/build/outputs/apk/debug/app-debug.apk
/opt/homebrew/share/android-commandlinetools/build-tools/36.0.0/aapt dump badging app/build/outputs/apk/debug/app-debug.apk
/opt/homebrew/share/android-commandlinetools/build-tools/36.0.0/apksigner verify --print-certs app/build/outputs/apk/debug/app-debug.apk
```

Results:

- initial clean build: `BUILD SUCCESSFUL in 2m 49s`, 35 tasks, 34 executed;
- independent-cache cold build: `BUILD SUCCESSFUL in 4m 44s`, 35/35 executed;
- independent-cache offline clean rebuild: `BUILD SUCCESSFUL in 12s`, 35/35 executed;
- all observed APKs had the same byte count, SHA-256, package, launcher, SDK
  identity, and signing certificate shown above;
- non-fatal warnings covered deprecated Android/Kotlin surfaces, SDK XML v4
  versus an older parser, and six resource-merger `android:color` messages.

### Upstream tests

```sh
/usr/bin/time -p ./gradlew :app:testDebugUnitTest --no-daemon --console=plain
/usr/bin/time -p ./gradlew :app:connectedDebugAndroidTest --no-daemon --console=plain
/usr/bin/time -p ./gradlew :app:connectedDebugAndroidTest --no-daemon --console=plain -Pandroid.testInstrumentationRunnerArguments.class=com.darkempire78.opencalculator.MainActivityTests
```

Results:

- unit: 36 tests, 35 passed, 1 failed in an 11-second Gradle run. The failure
  asserted exact floating-point equality: expected `0.8660254037844387`, actual
  `0.8660254037844388`;
- full API-35 instrumentation: 4 tests, 3 passed, 1 failed in a 65-second Gradle
  run. `ExampleInstrumentedTest` expected the release package but observed the
  correct debug package suffix;
- filtered lifecycle tests: `MainActivityTests` passed 3/3 (landscape,
  portrait, and recreation) in an 11-second Gradle run (`real 12.18s`).

The XML and textproto receipts are copied into `artifacts/` before later Gradle
runs could overwrite them.

### Device deployment and deterministic replay

```sh
android emulator start --cold aiverify_api35
android run --apks=/Users/peter/hosts/opencalc-calibration/app/build/outputs/apk/debug/app-debug.apk --device=emulator-5554 --activity=com.darkempire78.opencalculator.activities.MainActivity
adb -s emulator-5554 shell pm clear com.darkempire78.opencalculator.debug
adb -s emulator-5554 shell am start -W -S -n com.darkempire78.opencalculator.debug/com.darkempire78.opencalculator.activities.MainActivity
android layout --device=emulator-5554 -p
adb -s emulator-5554 shell input tap 150 1888
sleep 0.35
adb -s emulator-5554 shell input tap 409 1888
sleep 0.35
adb -s emulator-5554 shell input tap 929 1888
sleep 0.35
adb -s emulator-5554 shell input tap 669 1888
sleep 0.35
adb -s emulator-5554 shell input tap 150 1590
sleep 0.35
adb -s emulator-5554 shell input tap 929 2187
sleep 1
android layout --device=emulator-5554 -p
```

The reset/start/layout/tap sequence was executed independently three times.
Each cycle asserted an empty initial `input` node and a final `input.text` of
`46` for `12+34=`. Cold activity `TotalTime` values were 531, 554, and 553 ms.
All three initial layout JSON files are byte-identical to each other, and all
three result layout JSON files are byte-identical to each other. Error-level
logcat filtered to the app PID was empty in every controlled cycle.

An earlier zero-delay pilot produced `15` because the final operand tap was not
accepted before `=`. Its two screenshots remain in the artifact set as
illustrative observations and are not counted in the 3/3 result. The screenshot
capture commands were not retained in this record and cannot be reconstructed
from the committed evidence. Because this run names `emulator-5554`, ADR-0001
requires serial-scoped `screencap`, `pull`, and remote `rm` commands for device
attribution. The five PNGs therefore are not accountable, device-attributed
evidence, and no conclusion relies on them. The 3/3 result is supported by the
device-selected layout JSON and serial-scoped reset/start/input observations.

Final local/device APK lineage was checked with:

```sh
adb -s emulator-5554 shell pm path com.darkempire78.opencalculator.debug
adb -s emulator-5554 shell sha256sum /data/app/<resolved-install>/base.apk
shasum -a 256 /Users/peter/hosts/opencalc-calibration/app/build/outputs/apk/debug/app-debug.apk
adb -s emulator-5554 shell cmd package resolve-activity --brief -n com.darkempire78.opencalculator.debug/com.darkempire78.opencalculator.activities.MainActivity
```

Both APK hashes were
`9557d4a14e3677c2db359ed683a9a064f0c624c5daa632d8bd85337de94615f7`,
and the expected launcher resolved.

## Artifact inventory

- `artifacts/controlled-cycle-{1,2,3}-initial.json`: post-reset layout trees;
- `artifacts/controlled-cycle-{1,2,3}-result.json`: result layout trees;
- `artifacts/controlled-cycle-{1,2,3}-result.png`: illustrative screenshot
  files excluded from accountable device-attributed evidence;
- `artifacts/cycle-1-initial.png` and `artifacts/cycle-1-result.png`: the
  zero-delay pilot's illustrative screenshot files, also excluded from
  accountable device-attributed evidence;
- `artifacts/unit-*.xml`: upstream unit-test receipts;
- `artifacts/instrumentation-full-suite.{xml,textproto}`: the 4-test failing
  upstream instrumentation receipt;
- `artifacts/instrumentation-main-activity.{xml,textproto}`: the filtered 3/3
  lifecycle receipt;
- `artifacts/SHA256SUMS`: checksums for every other artifact.

The two upstream instrumentation XML receipts are preserved byte-for-byte with
their generated CRLF or mixed line endings and remain bound by `SHA256SUMS`.
Consequently a branch-wide `git diff --check origin/main...HEAD` reports line-end
whitespace for exactly those two raw artifacts. They are an explicit raw-evidence
exception and must not be normalized without also changing their provenance and
checksums; the same check excluding those exact files covers the rest of the
branch.

The reproducible APK is intentionally not copied into this exploratory repo
record; its absolute local path, size, source recipe, and checksum are recorded
above. The external checkout and dedicated Gradle cache are also local-only.

## Observed DIL-to-runtime gap

The host is no longer the immediate blocker. The next blocker is an interface
gap in this repository:

- `aiverify.injection` has no production caller; its public modules are used
  only by Injection Lab tests;
- a sealed `InjectionReceipt` binds a deliberately patched, dirty, detached
  worktree, while current production-seam admission accepts only a clean Git
  worktree;
- `aiverify.runner` locates and deploys an already-built APK; it deliberately
  does not build the materialized source;
- the existing Run Spec should remain a single execution contract and should
  not absorb auditor-only injection labels or build orchestration.

The narrow next slice should introduce one deep preparation module before the
runner. Its interface consumes a sealed source authority, a declarative build
recipe, and an already-admitted Attack Plan/Run Spec template; its implementation
validates the exact worktree against the injection receipt, builds without
mutating source, verifies APK package/activity/hash, and returns either one
checksum-bound preparation receipt or one stable rejection. The existing clean
checkout path and the new sealed-injection path are the two real adapters at the
source-authority seam. Device side effects remain behind current production-seam
admission, and the runner remains responsible for deployment, evidence, oracle,
and ExecutionRecord lifecycle.

## Known gaps and claim boundary

- Locale, timezone, font scale, animation scales, and network state were observed
  only through the selected AVD's existing profile, not frozen in a Run Spec.
- No orientation/process-death defect-control pair or persistent-history oracle
  was created in this run.
- No source injection, discovery, blinded packet, Verification Agent invocation,
  or independent adjudication occurred.
- Upstream test failures require explicit baseline exceptions; they cannot be
  silently treated as injected detections.
- OpenCalc remains calibration-only and must not be promoted into the external
  holdout denominator. Catima was not cloned, built, or exposed to runtime
  debugging in this calibration.
- The five PNGs have no retained ADR-0001 serial-scoped capture-command receipt;
  they are illustrative artifacts rather than accountable screenshot evidence.
