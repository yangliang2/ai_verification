# Issue #86 — Historical Admission Preflight

Date: 2026-08-03
Project branch: `issue-86-historical`
Project base: `c938376944058bd1b441cb5911dfe8383773597d` (merged #92)
Source checkout: local clone of `https://github.com/wikimedia/apps-android-wikipedia`

## Gate result

The three frozen exact historical pairs reproduce their preregistered
pre-fix/fixed behavior on the API-35 emulator in a local, temporary upstream
checkout:

| Slot | Pre-fix revision | Pre-fix result | Fixed revision | Fixed result |
|---|---|---|---|---|
| H-01 / T425894 | `b88c6a672e18167727fcc9d913c9ed57e50e03ce` | 1 test, 1 expected failure | `996ad8592fbd41e59ea195da72a3e9a728181006` | 1 test, pass |
| H-02 / T379777 | `675b930624c80498b3d3881592ac1c3f179a2709` | 3 tests, 3 expected failures | `c7250ce14feaa24e52d3a2468fb86b15fa56cfff` | 3 tests, pass |
| H-03 / T382892 | `d67ec44adc1d8c4d8dc7dcb736c0faa9f1b6934c` | 1 test, 1 expected failure | `fdc4ffb9ef3be93a96500bf630057c1e66ac7b8f` | 1 test, pass |

All six clean/build/deploy/test-install/instrumentation commands exited 0;
the Android instrumentation process reports assertion failures in its output
while retaining process exit 0. The raw outputs are preserved per revision.

This is admission preflight only. No formal 18-lane execution, Qualification
Case Package, Verification Agent session, or independent audit was started.
The explicit formal-execution gate for #86 remains outstanding.

## Exact command forms

For each row, the temporary upstream checkout was detached at the listed
revision, the project fixture was copied to
`app/src/androidTest/java/org/wikipedia/m6/`, and the fixture copy was removed
after the run. Commands were:

```text
JAVA_HOME=/opt/homebrew/opt/openjdk@17 /usr/bin/time -p \
  ./gradlew clean :app:assembleDevDebug :app:assembleDevDebugAndroidTest \
  --offline --no-daemon

adb -s emulator-5554 shell pm clear org.wikipedia.dev
adb -s emulator-5554 install -r -d app/build/outputs/apk/dev/debug/app-dev-debug.apk
adb -s emulator-5554 install -r -d \
  app/build/outputs/apk/androidTest/dev/debug/app-dev-debug-androidTest.apk

/usr/bin/time -p adb -s emulator-5554 shell am instrument -w \
  -e class org.wikipedia.m6.M6H0X...Test \
  org.wikipedia.test/androidx.test.runner.AndroidJUnitRunner
```

Build wall times were 10.33s / 7.57s (H-01 pre/fixed), 10.93s / 9.77s
(H-02 pre/fixed), and 10.58s / 10.03s (H-03 pre/fixed). Instrumentation wall
times were 2.10s / 2.19s, 1.09s / 1.09s, and 1.12s / 1.11s respectively.

## Fixture and source identity

- H-01 fixture SHA-256:
  `d7d4b7412554020f82bf2a362c02d9bcc69eaa568ac50d8f1db8ad988a02b327`
- H-02 fixture SHA-256:
  `8a0f41f25f8fe44810826780b9cc8ce519d57b78c2078515504a161c224eda92`
- H-03 fixture SHA-256:
  `2c1c552745faabcf3c4e3c0c7322fb264a4b21f12394f33caa27bb9aaf37088d`
- Historical pair selection and prior committed admission evidence:
  `docs/runs/2026-08-03-issue-84-cohort-admission/`.

The temporary source clone was left detached at H-03 fixed only while the
commands ran and was cleaned back to a zero-status worktree. No source commit,
branch, task comment, pull request, or other upstream state was created.

## Device and tools

`environment.txt` records the exact project commit, source remote, final
checkout, Android CLI/ADB/Gradle versions, API level, emulator fingerprint and
model, and clone status. The device was `emulator-5554`, API 35,
`sdk_gphone64_arm64`.

## Artifact inventory

- `h01-pre/`, `h01-fixed/`, `h02-pre/`, `h02-fixed/`, `h03-pre/`,
  `h03-fixed/`: checkout, Gradle build, APK deployment, test-APK install, and
  instrumentation output.
- `environment.txt`: tool/device/source identity.
- `checksums.sha256`: SHA-256 inventory for this run record and the three
  fixture inputs.

## Known gaps and next authorization boundary

- This preflight does not create formal lanes, attempt ledgers, ExecutionRecord
  artifacts, case packages, or independent audit evidence.
- APK files were generated in the temporary source checkout and intentionally
  not copied into the project run record; the build logs and source/fixture
  identities are retained.
- Formal #86 work must use separate candidate lane directories and the common
  package/ledger contract, then run 18 lanes without post-accountable retry.
- No upstream interaction was performed. A separate approval is required
  before formal M6 execution begins.

