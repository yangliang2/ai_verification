## Completion evidence

Issue #71 is implemented and verified for the recorded local environment. The
bounded conclusion is accountable locally_supported: the baseline restores and
migrates exact state, while the matched one-line stale-migration candidate is
rejected as stale_state.

Durable run record:
[2026-07-19 issue #71 lifecycle/backup recovery](https://github.com/yangliang2/ai_verification/tree/issue-71-lifecycle-recovery/docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery)

### Accountable lane results

| Lane | Attempt | Runner result | Dedicated oracle | Total | APK SHA-256 |
| --- | --- | --- | --- | ---: | --- |
| Baseline | bfd50b91-4489-467b-9b21-ac69f835058c | exit 0; completed; L1 inconclusive; L2 pass | locally_supported / correct_restoration | 280.052 s | 1a8cc170e310417f37447dd68bea1de853b1f8ed2d11d962a3662ba5cef85c0c |
| Candidate | f71c8c40-884a-4a38-a29d-300140f4b602 | exit 1; completed; L1 inconclusive; L2 fail (state_loss) | locally_rejected / stale_state | 289.997 s | 82cb4a481c4572ba883adca2fb9fafce4c1e40b4fbb785b1acfc00051410958b |

Candidate exit 1 is the expected product rejection, not an execution failure.
Both source/installed/archived APK identities match. Device identity:
emulator-5554, AVD aiverify_api35, API 35,
google/sdk_gphone64_arm64/emu64a:15/AE3A.240806.043/12960925:userdebug/dev-keys.
Package/activity:
dev.aiverify.lifecyclefixture/dev.aiverify.lifecyclefixture.MainActivity.

The separate read-only Verification Agent returned exactly one schema-valid
conclusion: locally_supported, accountable=true, with 13/13 evidence checks
passed. Conclusion SHA-256:
c60b774f2c0e8b24ebf708952826ced4b8864e46e411e9febaf9e65ca8e7213b.

### Acceptance-criteria implementation

- bench/fixtures/lifecycle-recovery-app/: deterministic sentinel fixture,
  versioned SharedPreferences state, backup rules, and no-backup epoch marker.
- src/aiverify/harness/device/controller.py and
  src/aiverify/runner/system_events.py: rotation, explicit HOME/background
  state, kill and process-absence proof, launcher relaunch, local backup,
  app-data clear, restore, post-restore PID, and cleanup to prior backup state.
- src/aiverify/bench/lifecycle_recovery.py: fail-closed evidence replay and
  crash/state_loss/silent_reset/stale_state/correct_restoration
  classification.
- src/aiverify/runner/{journey,cli,run_spec,evidence}.py: backup_restore Journey
  boundary, run-relative evidence bindings, interruption receipt preservation,
  and serial-scoped screenshots.
- bench/capability-slices/lifecycle-recovery/: matched Run Specs/Journey,
  contract, one-line candidate patch, and independent output schema.
- tests/bench/test_lifecycle_recovery.py plus runner tests implement regression
  coverage. artifacts/tdd/ contains 40 red/green/full-suite records.

### Exact verification commands

~~~sh
bench/fixtures/lifecycle-recovery-app/gradlew -p bench/fixtures/lifecycle-recovery-app :app:assembleDebug --no-daemon
sha256sum bench/fixtures/lifecycle-recovery-app/app/build/outputs/apk/debug/app-debug.apk

BASELINE_RUN=/tmp/aiverify-issue71-baseline-review.vWWaiL
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /usr/bin/time -p .venv/bin/python -m aiverify.runner bench/capability-slices/lifecycle-recovery/run-specs/baseline.yaml --device emulator-5554 --artifact-dir "$BASELINE_RUN/artifacts"

git apply bench/capability-slices/lifecycle-recovery/patches/stale-migration-guard.patch
bench/fixtures/lifecycle-recovery-app/gradlew -p bench/fixtures/lifecycle-recovery-app :app:assembleDebug --no-daemon
CANDIDATE_RUN=/tmp/aiverify-issue71-candidate-review.jugCbv
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /usr/bin/time -p .venv/bin/python -m aiverify.runner bench/capability-slices/lifecycle-recovery/run-specs/candidate.yaml --device emulator-5554 --artifact-dir "$CANDIDATE_RUN/artifacts"
git apply -R bench/capability-slices/lifecycle-recovery/patches/stale-migration-guard.patch

PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -o addopts='' -q --tb=short
.venv/bin/python -m compileall -q src tests
git diff --check

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums --verify docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/baseline/attempt-2
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums --verify docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/candidate/attempt-2

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m aiverify.bench.lifecycle_recovery --run-dir docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/baseline/attempt-2 --contract bench/capability-slices/lifecycle-recovery/contract.json --output /tmp/issue-71-baseline-oracle-final.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m aiverify.bench.lifecycle_recovery --run-dir docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/candidate/attempt-2 --contract bench/capability-slices/lifecycle-recovery/contract.json --output /tmp/issue-71-candidate-oracle-final.json

.venv/bin/python -c 'import json; from pathlib import Path; from jsonschema import validate; validate(json.loads(Path("docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/independent-verification/conclusion.json").read_text()), json.loads(Path("bench/capability-slices/lifecycle-recovery/independent-conclusion-schema.json").read_text())); print("independent conclusion schema verified")'

(cd docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery && shasum -a 256 -c checksums.sha256)
~~~

Important results:

- post-review full regression: 545 passed in 17.63 s; final repeat:
  545 passed in 16.48 s;
- compileall: exit 0; git diff --check passed on the authored post-review code
  state. A whole staged-evidence check later reports trailing spaces embedded
  in immutable captured identity/host.patch log lines; those raw bytes were
  preserved, while authored source/document paths pass a scoped check;
- baseline build: BUILD SUCCESSFUL in 2 s, 33 up-to-date;
- candidate build: BUILD SUCCESSFUL in 2 s, 1 executed / 3 from cache /
  29 up-to-date;
- both lane inventories verify: 71 baseline entries and 72 candidate entries;
- dedicated replay: baseline exit 0 correct_restoration; candidate exit 1
  stale_state as expected;
- independent schema validation and the final root checksum inventory verify.

### Real-device/manual evidence and artifact inventory

Both process-death receipts show the Nexus Launcher resumed after HOME,
target_resumed_after_home=false, successful kill, process absence, target
foreground resumption, and disjoint PIDs (26923→27249 and 27884→28238).
Both backup receipts show local-transport package Success, app-data clear exact
Success, token 1, restoreFinished: 0, post-restore PIDs 27584/28573, and cleanup
back to the original GMS transport and disabled backup state.

Each final lane retains seven screenshots, seven layouts, seven logcats, seven
command/capture manifests, three event receipts, four Journey receipts, an APK,
verdict, ExecutionRecord, provenance, oracle, and checksum manifest. Final
screenshots were visually inspected: baseline is sentinel / 2 / 42 / MIGRATED;
candidate is sentinel / 1 / 41 / PENDING. All fourteen logcats were scanned;
no target-package FATAL EXCEPTION, ANR, Process, or Fatal signal marker was
found.

Code review ran independent Spec and Standards passes, their findings were
fixed, attempt-2 was rerun, and both final re-reviews report no blocker. The
review record is under artifacts/code-review.md.

### Matched-input qualification and known gaps

Normalized Run Specs, four prompt hashes, scenario/actions/events/assertions,
device/tool/package identity, and other executable inputs match. Outside
docs/runs, baseline host.patch has no change and candidate has exactly the
intended 1-insertion/1-deletion StateStore.java patch (SHA-256
7109a3a3e7d1e0416ffe4c0a06de10982c8fdc99f1cfc888c266acc328674a42).
The entire worktrees are not byte-identical because run-record documents
changed between executions; this is disclosed, independently adjudicated
non-contaminating, and not hidden.

A clean-host rerun was attempted. It became non-accountable before the first
Journey action because Codex CLI hit an external usage limit; it has no Journey
result, checkpoint, or injected event and is excluded from product evidence.

Scope remains one local API-35 emulator and local backup transport. Android CLI
1.0.15498356 cannot select a screenshot device, so explicit-serial raw captures
use recorded adb shell-screencap/pull/cleanup and have no annotated PNG. No
detection-rate, Goldset, compatibility-matrix, cloud-provider, or upstream
acceptance claim is made. Compatibility-matrix work remains #72.
