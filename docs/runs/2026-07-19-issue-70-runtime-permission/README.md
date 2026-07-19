# Issue #70 — Android runtime-permission fault injection

This run validates an Android app reliability fault-injection design. It does
not make a security-business, security-certification, or benchmark-metric claim.
The fixture is outside `bench/goldset/`, and both run specs leave
`metric_context` unspecified.

## Accountable result

The canonical matched pair uses Wikipedia Android commit
`6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`, package
`org.wikipedia.dev`, activity
`org.wikipedia.permission.PermissionFixtureActivity`, emulator
`emulator-5556`, and Android API 35.

- Baseline: `baseline/attempt-5/`, completed in 569.122 seconds. L1 was
  inconclusive because it found no crash/ANR, L2 passed, and L3 passed. After
  first denial it retained retry plus an explicit no-location fallback; after
  permanent denial it exposed fallback plus app Settings; after grant and
  harness revocation it rechecked permission, reported `REVOKED`, and stayed
  responsive.
- Candidate: `candidate/attempt-1/`, completed in 508.417 seconds. L1 failed as
  `crash_stability` on an AndroidRuntime `FATAL EXCEPTION` / uncaught
  `SecurityException`; L2 failed as `state_loss` because first denial returned
  `BLOCKED` instead of the required fallback. L3 was intentionally not run
  after deterministic L1/L2 failures.
- Each canonical attempt contains 13 screenshots, 13 layout dumps, 13 logcat
  captures, and 6 create-only system-event observation JSON files. The baseline
  has 117 files (14 MiB); the candidate has 112 files (15 MiB).

The system-event evidence establishes these actual device states:

1. Fine and coarse location permissions reset to denied without `USER_SET` or
   `USER_FIXED`.
2. First denial: fine location denied with `USER_SET` and without `USER_FIXED`.
3. Second denial: fine location denied with `USER_SET` and `USER_FIXED`.
4. Harness grant: fine location granted.
5. Harness revoke: fine location denied before the final UI access.

## Exact verification commands

```sh
WIKIPEDIA_SOURCE=/Users/peter/hosts/wikipedia-issue-70-baseline \
PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.runner \
  bench/runtime-permission/run-specs/wikipedia-location-permission-baseline.yaml \
  --device emulator-5556 \
  --artifact-dir docs/runs/2026-07-19-issue-70-runtime-permission/baseline/attempt-5/artifacts \
  --workdir /Users/peter/hosts/wikipedia-issue-70-baseline

WIKIPEDIA_SOURCE=/Users/peter/hosts/wikipedia-issue-70-fixture \
PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.runner \
  bench/runtime-permission/run-specs/wikipedia-location-permission-candidate.yaml \
  --device emulator-5556 \
  --artifact-dir docs/runs/2026-07-19-issue-70-runtime-permission/candidate/attempt-1/artifacts \
  --workdir /Users/peter/hosts/wikipedia-issue-70-fixture

PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/pytest -q

cd /Users/peter/hosts/wikipedia-issue-70-baseline
./gradlew :app:assembleDevDebug --console=plain
git apply --check -R \
  /Users/peter/projects/ai_verification-issue-70/bench/runtime-permission/patches/wikipedia-location-permission-baseline.patch

cd /Users/peter/hosts/wikipedia-issue-70-fixture
./gradlew :app:assembleDevDebug --console=plain
git apply --check -R \
  /Users/peter/projects/ai_verification-issue-70/bench/runtime-permission/patches/wikipedia-location-permission-candidate.patch

cd /Users/peter/projects/ai_verification-issue-70
git diff --check
```

Important results:

- Full Python suite: 544 passed in 16.50 seconds. An earlier full-suite run is
  retained in `pytest.log`; it had 543 passes and one stale exact-dictionary
  assertion failure. The corrected final run is `pytest-final.log`.
- Baseline APK build: `BUILD SUCCESSFUL in 8s`; 66 tasks, all up-to-date; total
  wall time 8.50 seconds. Log: `build-baseline.log`.
- Candidate APK build: `BUILD SUCCESSFUL in 1s`; 66 tasks, all up-to-date;
  total wall time 1.62 seconds. Log: `build-candidate.log`.
- Baseline APK SHA-256:
  `a2584a0fb0224bf89768296243c7da6b8ef2914da9ebdedff1b456461c914681`.
- Candidate APK SHA-256:
  `fb4402403d50367895cf4904c6c12046c4296649572c30f38731a7cbf21c5992`.
- Both reverse patch checks passed, proving each stored patch exactly describes
  its applied debug-only host fixture.
- Tool versions: Android CLI 1.0.15498356; adb 1.0.41 / 37.0.0-14910828;
  Gradle 9.5.1; Kotlin 2.3.20; JVM 17.0.19; Python 3.11.15; pytest 9.0.3.

## Artifact inventory

- `baseline/attempt-5/verdict.json`, `execution-record.json`, and
  `execution-provenance.json`: canonical baseline result and provenance.
- `candidate/attempt-1/verdict.json`, `execution-record.json`, and
  `execution-provenance.json`: canonical candidate result and provenance.
- Each canonical `artifacts/after-segment-*` and `artifacts/after-event-*`
  directory: layout, raw screenshot, logcat, capture command log, and capture
  manifest. Android CLI cannot choose a device for screenshots when two devices
  are online, so raw screenshots use device-scoped adb and manifests explicitly
  record annotated screenshots as unavailable.
- Each canonical `artifacts/system-event-*.json`: requested permission and
  observed granted/flags state.
- Each canonical `artifacts/*-segment-*/`: Journey backend events, invocation
  identity, action lineage, raw result, and normalized result.
- `baseline/attempt-5/artifacts/l3-judge/`: baseline L3 prompt/result evidence.
- `candidate/attempt-1/artifacts/after-segment-6/logcat.txt`: durable crash
  stack trace for the revoked-access fault.
- `build-baseline.log`, `build-candidate.log`, `pytest.log`, and
  `pytest-final.log`: build/test command outputs.
- `independent-verification.json`: the separate Verification Agent's single
  fail-closed conclusion (`pass`) with acceptance-criterion evidence and gaps.
- `checksums.sha256`: 507-entry final SHA-256 inventory, excluding itself.

## Superseded attempt lineage

- `baseline/attempt-1`: non-accountable `checkpoint_capture_error`; Android CLI
  screen capture could not select among two online emulators. This led to the
  honest device-scoped adb fallback and explicit absence of annotated images.
- `baseline/attempt-2`: non-accountable `journey_action_failed`; fine location
  was reset but the grouped coarse location permission retained `USER_FIXED`,
  suppressing the system dialog. Both group members are now reset.
- `baseline/attempt-3`: completed but detected a false L2 failure because the
  second reset creates an empty boundary segment and the L2 index still pointed
  at the pre-denial checkpoint. Both matched specs now use boundary index 2.
- `baseline/attempt-4`: L1 inconclusive, L2/L3 pass, but superseded because its
  final post-revoke action refreshed without invoking the location feature.
  Attempt 5 actually invokes the protected feature after revocation.

## Known gaps and scope

- This is one deterministic debug-only Wikipedia fixture on one API 35 emulator;
  it is not a device/API compatibility matrix.
- The runner intentionally records no goldset metric or taxonomy claim.
- L3 is fail-fast and therefore did not run for the candidate after L1/L2 had
  already supplied deterministic failure evidence.
- APK binaries remain in the independent host worktrees and are not committed to
  this repository; their hashes are recorded above. All runner evidence and
  source patches are stored under this committed run directory.
