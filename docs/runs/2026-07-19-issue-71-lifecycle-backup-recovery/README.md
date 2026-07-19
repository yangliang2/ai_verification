# Issue #71 lifecycle and backup-recovery verification

Status: implementation and deterministic fixture validated; matched baseline and
candidate runner attempts are recorded below once complete.

## Scope and contract

This run record covers GitHub issue #71 only. The fixture contract and matched
Journey live under `bench/capability-slices/lifecycle-recovery/`. The observable
state must remain `AIVERIFY-ISSUE-71-SENTINEL / 1 / 41 /
PENDING_V1_TO_V2` through rotation and a real background process death, then
become `AIVERIFY-ISSUE-71-SENTINEL / 2 / 42 / MIGRATED_V1_TO_V2` after a
successful local-transport backup, app-data clear, restore, and relaunch.

The candidate patch changes only the legacy migration guard. Its accountable
expected outcome is `stale_state`; the baseline expected outcome is
`correct_restoration`. Missing layout, changed/missing process identity, failed
backup/restore markers, missing provenance, or an incomplete runner attempt must
produce `non_accountable`.

This is a local capability result. It is not a detection-rate, Goldset, or
upstream acceptance claim.

## Commands and results so far

Python focused tests:

```sh
/Users/peter/projects/ai_verfication/.venv/bin/pytest -q \
  tests/bench/test_lifecycle_recovery.py \
  tests/runner/test_run_spec.py \
  tests/runner/test_system_events.py \
  tests/runner/test_journey.py \
  tests/runner/test_cli.py
```

Result: passed (see `artifacts/test-focused-pre-run.txt`).

Full repository regression:

```sh
PYTHONDONTWRITEBYTECODE=1 \
  /Users/peter/projects/ai_verfication/.venv/bin/pytest \
  -p no:cacheprovider -o addopts='' -q
```

Result: `541 passed in 15.92s` (see `artifacts/test-full-pre-run.txt`).

Android fixture build and candidate patch check:

```sh
bench/fixtures/lifecycle-recovery-app/gradlew \
  -p bench/fixtures/lifecycle-recovery-app \
  :app:assembleDebug --no-daemon
git apply --check \
  bench/capability-slices/lifecycle-recovery/patches/stale-migration-guard.patch
shasum -a 256 \
  bench/fixtures/lifecycle-recovery-app/app/build/outputs/apk/debug/app-debug.apk
```

First clean build: `BUILD SUCCESSFUL in 2m 19s`, 33 executed tasks. Cached
rebuild: `BUILD SUCCESSFUL in 4s`, 33 up-to-date tasks. Baseline APK SHA-256:
`173856bbbb16728278a440b76097f207d4dcc03ac1227257215dabcfe5c02b64`.

## Manual real-emulator probe

Device: `emulator-5554`, API 35, AVD `aiverify_api35`.

The fixture APK was installed with `android run`, package data was cleared, and
the explicit activity `dev.aiverify.lifecyclefixture.MainActivity` was launched.
The initial layout showed `UNINITIALIZED / 0 / 0 / NOT_CREATED`. A coordinate tap
on the visible `create_fixture` button produced the exact v1 state.

The same public `DeviceSystemEventInjector` used by the runner was then invoked
against the real device for each boundary:

- rotation to `user_rotation=1` preserved all four v1 values;
- the first intentionally short process-death probe failed closed because PID
  `22062` survived; its evidence is retained and not counted;
- retrying with 2-second background and kill waits changed PID `22062` to
  `22323` and preserved all four v1 values;
- local-transport backup/restore returned package `Success`, restore token `1`,
  `restoreFinished: 0`, and post-restore PID `22602`; it restored the original
  GMS transport and disabled backup afterward;
- the post-restore layout showed the exact v2/revision-42 migrated state.

Screenshots and layouts are under `artifacts/build/` and
`artifacts/manual-probe/`. The captured screenshots were visually inspected;
the visible labels and values agreed with the corresponding layout JSON.

## Toolchain

See `artifacts/tool-versions.txt`: Android CLI `1.0.15498356`, adb `37.0.0`,
OpenJDK `17.0.19`, Gradle `9.1.0`, Python `3.11.15`, Codex CLI `0.144.5`, and
Git `2.50.1`.

## Preliminary artifact inventory

- `artifacts/tdd/`: red/green history for oracle classifications, backup event,
  event evidence binding, matched specs, and fail-closed provenance handling.
- `artifacts/build/`: build logs, APK checksum, installation/launch output, and
  initial UI evidence.
- `artifacts/manual-probe/`: real-device event JSON, layouts, and screenshot.
- `artifacts/test-focused-pre-run.txt`: focused Python regression output.
- `artifacts/test-full-pre-run.txt`: full Python regression output.
- `artifacts/tool-versions.txt`: exact local tool versions.

Checksums, matched runner attempts, independent Verification Agent conclusion,
and the final requirement audit are added after the full executions.

## Retained non-accountable attempt and diagnosis

`attempts/non-accountable-baseline-01/` is the first full baseline invocation.
Its preflight and first Journey segment passed, but the attempt correctly ended
`non_accountable / checkpoint_capture_error` after 95.079 seconds. Android CLI
`screen capture` has no device selector in version `1.0.15498356`; with both
`emulator-5554` and `emulator-5556` online it printed a multiple-device error,
returned exit code 0, and wrote no PNG. Layout and logcat capture remained valid.

The collector regression now uses `adb -s <serial> shell screencap`, a scoped
`adb pull`, and scoped cleanup when a device is supplied. Unit feedback is in
`artifacts/tdd/36-multi-device-screenshot-red.txt` and
`37-multi-device-screenshot-green.txt` (`8 passed`). The original two-device
reproduction then produced a real 1080×2400 PNG and a passed capture manifest;
the replay is retained under `artifacts/diagnosis/multi-device-repro/` and was
visually inspected. No emulator belonging to the concurrent issue #70 run was
stopped or modified.

The post-fix focused regression reports `10 passed in 0.11s`; the full repository
regression reports `542 passed in 19.46s`. See
`artifacts/test-screenshot-fix-focused-green.txt` and
`artifacts/test-full-screenshot-fix-green.txt`.
