# Issue #71 lifecycle and backup-recovery verification

Status: implementation, real-device evidence, and independent post-review audit
complete; durable commit and GitHub publication are being finalized.

This record supports a deliberately narrow local claim. On the recorded API-35
emulator, the baseline preserves deterministic version-1 state through rotation
and background process death, then restores and migrates that state after local
backup, app-data clear, and restore. The one-line stale-migration candidate is
rejected. No detection-rate, device-matrix, cloud-provider, or upstream
acceptance claim is made.

## Acceptance-criteria audit

- [x] A deterministic Android fixture creates
  AIVERIFY-ISSUE-71-SENTINEL / schema 1 / revision 41 /
  PENDING_V1_TO_V2.
- [x] Rotation and a real background process death retain exact state. Event
  receipts prove HOME/background state, target-process absence after kill,
  launcher relaunch, target foreground state, and disjoint process IDs.
- [x] Local-transport backup records backup success, app-data clear result,
  restore token/result, post-restore PID, and cleanup back to the original
  transport and enabled state.
- [x] The baseline restores schema 2 / revision 42 / MIGRATED_V1_TO_V2.
- [x] The candidate retains the sentinel but remains stale at schema 1 /
  revision 41 / PENDING_V1_TO_V2.
- [x] The fail-closed oracle classifies crash, state loss, silent reset, stale
  state, correct restoration, and missing/non-accountable evidence.
- [x] Both final lanes retain run-relative ExecutionRecord and system-event
  references, provenance, archived executed APKs, Journey receipts, layouts,
  screenshots, logcats, verdicts, and independent lane checksums.
- [x] A separate read-only post-review Verification Agent produced exactly one
  fail-closed schema-valid conclusion: locally_supported, accountable, with
  13/13 evidence checks passed.
- [ ] The run record, issue comment, parent progress comment, and closure are
  pending commit/push.

## Implemented capability

- src/aiverify/bench/lifecycle_recovery.py: contract loading, evidence replay,
  fail-closed classifications, and CLI.
- src/aiverify/harness/device/controller.py and
  src/aiverify/runner/system_events.py: controlled rotation, HOME/background
  transition, process death, launcher relaunch, local backup/clear/restore, and
  backup-configuration cleanup with explicit retained postconditions.
- src/aiverify/runner/journey.py, cli.py, and run_spec.py: Journey boundaries,
  centralized interruption handling, durable run-relative event references,
  and ExecutionRecord binding.
- src/aiverify/runner/evidence.py: serial-scoped raw screenshot capture whenever
  a run names a device. ADR 0001 documents the selector-less Android CLI
  1.0.15498356 limitation and the recorded adb shell-screencap/pull/cleanup
  fallback; Android CLI remains the no-selector path.
- bench/fixtures/lifecycle-recovery-app/: deterministic Android fixture. Only
  version-1 SharedPreferences state is backed up; a no-backup data-epoch marker
  causes restored legacy state to migrate once.
- bench/capability-slices/lifecycle-recovery/: contract, matched Run Specs,
  Journey, one-line candidate patch, and independent-conclusion schema.
- tests/bench/test_lifecycle_recovery.py and runner test modules: oracle,
  parsing, event injection/cleanup, interruption evidence, provenance,
  run-relative references, and screenshot regression coverage.

## Final accountable lanes

Both lanes ran from host commit
8cab543d120bce430f97642c30e023f2f742ed57 on emulator-5554, AVD
aiverify_api35, API 35, fingerprint
google/sdk_gphone64_arm64/emu64a:15/AE3A.240806.043/12960925:userdebug/dev-keys.
They used package dev.aiverify.lifecyclefixture and activity
dev.aiverify.lifecyclefixture.MainActivity.

| Lane | Attempt ID | Runner | Dedicated oracle | Time | Executed APK SHA-256 |
| --- | --- | --- | --- | ---: | --- |
| Baseline | bfd50b91-4489-467b-9b21-ac69f835058c | exit 0; L1 inconclusive; L2 pass | accountable, locally_supported / correct_restoration | 280.052 s (real 280.15 s) | 1a8cc170e310417f37447dd68bea1de853b1f8ed2d11d962a3662ba5cef85c0c |
| Candidate | f71c8c40-884a-4a38-a29d-300140f4b602 | exit 1; L1 inconclusive; L2 fail (state_loss) | accountable, locally_rejected / stale_state | 289.997 s (real 290.08 s) | 82cb4a481c4572ba883adca2fb9fafce4c1e40b4fbb785b1acfc00051410958b |

Candidate exit 1 is the expected product rejection, not a harness failure. The
generic L2 class is state_loss; the dedicated contract oracle refines the
observation to stale_state because the sentinel survived while
schema/revision/migration did not advance.

Each lane contains seven screenshots, seven layout dumps, seven logcats, seven
command/capture-manifest pairs, three system-event receipts, four Journey
invocation receipts, the archived executed APK, and terminal runner,
provenance, oracle, and ExecutionRecord files. The baseline manifest contains
71 entries and the candidate manifest 72.

### Real event receipts

- Rotation: both receipts record requested and observed user_rotation=1 and
  accelerometer_rotation=0; exact version-1 state remains visible.
- Process death: baseline PID 26923 becomes 27249; candidate PID 27884 becomes
  28238. Both record the launcher package after HOME, target absence after
  kill, target foreground state after relaunch, and disjoint non-empty PID
  sets.
- Backup/restore: both select
  com.android.localtransport/.LocalTransport, record package backup Success,
  app-data clear Success, restore token 1, restoreFinished: 0, and post-restore
  process IDs 27584 and 28573. Both restore the original GMS transport and
  disabled backup state before a passed receipt is emitted.
- Visual/log review: baseline after-event-2 shows sentinel / 2 / 42 / MIGRATED;
  candidate shows sentinel / 1 / 41 / PENDING. A scan of all fourteen retained
  logcats found no target-package FATAL EXCEPTION, ANR, Process, or Fatal signal
  marker.

## Matched-input audit and qualification

The executable inputs match apart from the intended one-line candidate defect:

- normalized Run Spec SHA-256:
  3a23e226c11c68834a47dfae64941e9c5aec5ca896932a44caa98c4083c2c827;
- all four Journey prompt hashes match byte-for-byte;
- host commit, device, tool identities, package/activity, driver model, event
  sequence/arguments, assertions, and scenario match;
- each archived APK hash equals its installed APK hash;
- filtering identity/host.patch to paths outside docs/runs yields no baseline
  path and exactly one candidate path: a 1-insertion/1-deletion change in
  StateStore.java, patch SHA-256
  7109a3a3e7d1e0416ffe4c0a06de10982c8fdc99f1cfc888c266acc328674a42.

The strict entire-worktree patches are not byte-identical because evidence
documents under this run directory changed between executions. This
documentation-only drift is disclosed in artifacts/matched-input-audit.json;
the audit's matched_executable_inputs value is true and
strict_entire_worktree_match is false. The Journey prompts prohibited file
inspection and retained commands contain only device UI operations.

The candidate runner footer says the lane was “superseded” because it was
written when a clean-host replacement was still planned. The lane was later
selected as the qualified final candidate without altering its bytes after the
clean retry failed before its first Journey action. That retry is retained at
attempts/non-accountable-baseline-clean-codex-usage-limit/ and is not product
evidence: Codex CLI reported the account usage limit before any action or
system event.

## Exact live commands

Fixture build and hash:

~~~sh
bench/fixtures/lifecycle-recovery-app/gradlew -p bench/fixtures/lifecycle-recovery-app :app:assembleDebug --no-daemon
sha256sum bench/fixtures/lifecycle-recovery-app/app/build/outputs/apk/debug/app-debug.apk
~~~

The post-review baseline build completed in 2 seconds with 33 tasks up to date.
The candidate build completed in 2 seconds with 1 executed, 3 from cache, and
29 up-to-date tasks.

Baseline Journey:

~~~sh
BASELINE_RUN=/tmp/aiverify-issue71-baseline-review.vWWaiL
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /usr/bin/time -p .venv/bin/python -m aiverify.runner bench/capability-slices/lifecycle-recovery/run-specs/baseline.yaml --device emulator-5554 --artifact-dir $BASELINE_RUN/artifacts
~~~

Candidate Journey:

~~~sh
git apply bench/capability-slices/lifecycle-recovery/patches/stale-migration-guard.patch
bench/fixtures/lifecycle-recovery-app/gradlew -p bench/fixtures/lifecycle-recovery-app :app:assembleDebug --no-daemon
CANDIDATE_RUN=/tmp/aiverify-issue71-candidate-review.jugCbv
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /usr/bin/time -p .venv/bin/python -m aiverify.runner bench/capability-slices/lifecycle-recovery/run-specs/candidate.yaml --device emulator-5554 --artifact-dir $CANDIDATE_RUN/artifacts
git apply -R bench/capability-slices/lifecycle-recovery/patches/stale-migration-guard.patch
~~~

The source currently matches HEAD; the candidate patch is not left applied.

## Final verification commands

~~~sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -o addopts='' -q --tb=short

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums --verify docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/baseline/attempt-2
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m aiverify.bench.run_record_checksums --verify docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/candidate/attempt-2

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m aiverify.bench.lifecycle_recovery --run-dir docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/baseline/attempt-2 --contract bench/capability-slices/lifecycle-recovery/contract.json --output /tmp/issue-71-baseline-oracle-final.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m aiverify.bench.lifecycle_recovery --run-dir docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/candidate/attempt-2 --contract bench/capability-slices/lifecycle-recovery/contract.json --output /tmp/issue-71-candidate-oracle-final.json
~~~

Results on 2026-07-19:

- full suite: 545 passed in 16.48 seconds;
- both lane checksum inventories verified;
- baseline oracle: exit 0, accountable correct_restoration;
- candidate oracle: exit 1, accountable stale_state (expected rejection);
- git diff --check and compileall were also run against the authored
  post-review code changes; see
  artifacts/tdd/40-post-review-full-suite-green.txt. A later whole staged-tree
  check reports trailing spaces inside immutable captured identity/host.patch
  log lines. Those raw evidence bytes are intentionally preserved; authored
  source/document paths pass the scoped check.

## Independent verification

The original Codex CLI audit of the pre-review lanes is preserved under
independent-verification-pre-review/. A fresh collaboration Verification Agent
audited attempt-2 read-only and returned exactly one JSON object. Local Draft
2020-12 validation passed against
bench/capability-slices/lifecycle-recovery/independent-conclusion-schema.json.

The authoritative independent-verification/conclusion.json is
locally_supported and accountable, with 13/13 checks passed and SHA-256
c60b774f2c0e8b24ebf708952826ced4b8864e46e411e9febaf9e65ca8e7213b.
It independently verified lane inventories, provenance and run-relative
bindings, APK/device/tool identity, normalized Run Specs and prompts, the
candidate bytecode difference, all lifecycle/backup receipts, UI/logcat
evidence, oracle discrimination, and exclusion of the clean usage-limit retry.
It explicitly concluded that the docs-only host.patch drift does not
contaminate matched executable or Journey inputs.

The collaboration API exposes the final message but not a raw transcript or CLI
thread. invocation.md and prompt.md record that limitation without inventing
provenance; validation.txt records the successful local schema check.

## Artifact inventory

- baseline/attempt-2/ and candidate/attempt-2/: qualified final real-device
  lanes with independent 71- and 72-entry manifests.
- artifacts/matched-input-audit.{json,txt}: executable-input equality audit and
  explicit entire-worktree qualification.
- artifacts/tdd/: 40 red/green/regression records, including post-review
  evidence-reference and event-receipt tests.
- artifacts/build/, artifacts/manual-probe/, artifacts/diagnosis/: fixture
  builds, installation, manual device probes, and multi-device screenshot
  diagnosis.
- independent-verification-pre-review/: superseded pre-review independent
  audit.
- independent-verification/: authoritative post-review read-only conclusion,
  task/invocation record, and schema validation.
- attempts/: excluded and superseded attempts, including provenance
  self-drift and the clean Codex-usage-limit retry.
- issue-71.json: issue brief captured for audit.
- issue-comment.md and parent-comment.md: to be added as the exact GitHub
  publication bodies.
- checksums.sha256: to be generated after all final artifacts are frozen.

Tool versions: Android CLI 1.0.15498356, adb 37.0.0, OpenJDK 17.0.19,
Gradle 9.1.0, Python 3.11.15, Codex CLI 0.144.5, Git 2.50.1.

## Known gaps and claim boundary

- One local API-35 emulator and local backup transport were tested. The broader
  API/device/locale/RTL/form-factor matrix remains issue #72.
- Device-scoped screenshots retain plain PNG and UI-layout evidence but no
  Android-CLI annotation because Android CLI 1.0.15498356 has no screenshot
  device selector.
- The final Verification Agent audits retained evidence read-only; it does not
  rerun the device Journey.
- ExecutionRecord and system-event references are run-relative. Some immutable
  live-run provenance/verdict fields retain absolute execution-origin paths;
  their durable copies are inventoried here and replay uses this directory.
- The entire-worktree match is qualified by disclosed docs/runs-only drift.
  A clean retry was attempted but became non-accountable at the external Codex
  usage limit before the first Journey action.
- No rates, Goldset, compatibility matrix, cloud-provider result, or upstream
  acceptance is asserted.
