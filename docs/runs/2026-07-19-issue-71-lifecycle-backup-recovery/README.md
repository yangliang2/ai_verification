# Issue #71 lifecycle and backup-recovery verification

Status: complete. The accountable matched pair supports the local capability:
the baseline is `locally_supported / correct_restoration`, the candidate is
`locally_rejected / stale_state`, and the separate read-only Verification Agent
concludes `locally_supported` with all 11 evidence checks passed.

This run record covers GitHub issue #71 only. It makes no detection-rate,
Goldset, compatibility-matrix, cloud-provider, or upstream-acceptance claim.

## Acceptance-criteria audit

- [x] The deterministic fixture keeps
  `AIVERIFY-ISSUE-71-SENTINEL / 1 / 41 / PENDING_V1_TO_V2` through rotation and
  a real background process death, with disjoint before/after PIDs.
- [x] Android local-transport backup, package-data clear, restore, and explicit
  relaunch produce `AIVERIFY-ISSUE-71-SENTINEL / 2 / 42 /
  MIGRATED_V1_TO_V2` in the baseline.
- [x] The machine oracle classifies crash, state loss, silent reset, stale
  state, correct restoration, and fail-closed non-accountable evidence.
- [x] Baseline and candidate retain system-event receipts, package/device/tool
  identity, APK and installed-APK hashes, logs, UI dumps, screenshots, Journey
  receipts, ExecutionRecords, verdicts, and complete checksum inventories.
- [x] A separate Codex CLI Verification Agent ran read-only and wrote one
  schema-valid authoritative `conclusion.json`.
- [x] Claims remain limited to the recorded local API-35 emulator and attempts.

## Implemented capability

- `src/aiverify/bench/lifecycle_recovery.py` supplies the fixture contract
  loader, run-evidence replay, fail-closed classifications, and CLI.
- `src/aiverify/harness/device/controller.py` and
  `src/aiverify/runner/system_events.py` add controlled `bmgr` backup/restore,
  exact success postconditions, package-data clear, relaunch, and restoration of
  the previous transport/enabled state.
- `src/aiverify/runner/journey.py`, `cli.py`, and `run_spec.py` make
  `backup_restore` a Journey boundary and bind create-only system-event receipts
  into the completed verdict and ExecutionRecord.
- `src/aiverify/runner/evidence.py` scopes screenshots to the selected serial in
  multi-device environments.
- `bench/fixtures/lifecycle-recovery-app/` is a minimal deterministic Android
  fixture. Only its version-1 SharedPreferences state is backed up; a no-backup
  data-epoch marker causes restored legacy state to migrate once to version 2.
- `bench/capability-slices/lifecycle-recovery/` contains the contract, matched
  Run Specs, Journey description, and one-line stale-migration candidate patch.
- `tests/bench/test_lifecycle_recovery.py` and the runner test modules cover the
  oracle, parsing, injection/cleanup, evidence binding, runner failure modes,
  and scoped screenshot capture.

## Accountable matched pair

Both lanes use package `dev.aiverify.lifecyclefixture`, activity
`dev.aiverify.lifecyclefixture.MainActivity`, device `emulator-5554`, AVD
`aiverify_api35`, API 35, and fingerprint
`google/sdk_gphone64_arm64/emu64a:15/AE3A.240806.043/12960925:userdebug/dev-keys`.
Their four user actions, three event/argument objects, four assertions, Codex
prompt hashes, package/activity/APK glob, and scenario ID match. Candidate Run
Spec bytes become identical to baseline after removing only its `diff:` field;
both hash to `3a23e226c11c68834a47dfae64941e9c5aec5ca896932a44caa98c4083c2c827`.

| Lane | Attempt | Runner | Dedicated oracle | Duration | Executed APK SHA-256 |
| --- | --- | --- | --- | ---: | --- |
| Baseline | `090153ac-43c7-4454-9812-e6bfcad871e0` | exit 0; L1 inconclusive; L2 pass | accountable `correct_restoration` | 282.686 s | `1a8cc170e310417f37447dd68bea1de853b1f8ed2d11d962a3662ba5cef85c0c` |
| Candidate | `8468060c-46c3-4e01-b56e-aa77bf82c96d` | exit 1; L1 inconclusive; L2 fail (`state_loss`) | accountable `stale_state` | 375.245 s | `535f04161fef62ac7bb89ebb873279224463b38db971691d5baa7b6a89e33fac` |

The runner's generic L2 defect class is `state_loss`; the dedicated contract
oracle refines the exact observed outcome to `stale_state` because the sentinel
survives while schema/revision/migration remain at the pre-migration values.

### Real event evidence

- Rotation: both receipts record requested/observed `user_rotation=1` and
  `accelerometer_rotation=0`; the v1 state remains exact.
- Background process death and return-to-foreground: baseline PID `25596`
  becomes `25913`; candidate PID `24543` becomes `24856`. Both sets are
  non-empty and disjoint, and all four v1 values remain exact after relaunch.
- Backup/restore: both runs select
  `com.android.localtransport/.LocalTransport`, record package-specific backup
  `Success`, restore token `1`, `restoreFinished: 0`, and restore success.
  Post-restore PIDs are `26243` and `25180`. The injector verifies `pm clear`
  returned exactly `Success`, then restores the prior GMS transport and disabled
  backup state before it emits a passed event receipt.
- State outcome: baseline changes to v2/revision 42/migrated; candidate keeps
  sentinel but remains v1/revision 41/pending. The final baseline and candidate
  screenshots were visually inspected and agree with their layout JSON. The
  independent agent inspected all fourteen checkpoint manifests/screenshots and
  found no target-package fatal-crash marker in retained logcats.

Each final lane contains 7 screenshots, 7 layout dumps, 7 logcats, 7 command
records/capture manifests, 3 event receipts, 4 Journey invocation receipts, the
archived executed APK, and the terminal runner/oracle/provenance records.

## Exact execution and verification commands

Fixture build:

```sh
bench/fixtures/lifecycle-recovery-app/gradlew \
  -p bench/fixtures/lifecycle-recovery-app \
  :app:assembleDebug --no-daemon
sha256sum \
  bench/fixtures/lifecycle-recovery-app/app/build/outputs/apk/debug/app-debug.apk
```

The initial clean build completed in 2m19s with 33 executed tasks. The final
cached build completed in 2s with 33 up-to-date tasks, reproduced SHA-256
`1a8cc170e310417f37447dd68bea1de853b1f8ed2d11d962a3662ba5cef85c0c`,
and was byte-identical to the archived final baseline APK.

Final runner invocations:

```sh
BASELINE_RUN=/tmp/aiverify-issue71-baseline-final.wK34Mo
PYTHONPATH=src /usr/bin/time -p \
  /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.runner \
  bench/capability-slices/lifecycle-recovery/run-specs/baseline.yaml \
  --device emulator-5554 \
  --artifact-dir "$BASELINE_RUN/artifacts"

git apply \
  bench/capability-slices/lifecycle-recovery/patches/stale-migration-guard.patch
bench/fixtures/lifecycle-recovery-app/gradlew \
  -p bench/fixtures/lifecycle-recovery-app \
  :app:assembleDebug --no-daemon
CANDIDATE_RUN=/tmp/aiverify-issue71-candidate.c2wnqt
PYTHONPATH=src /usr/bin/time -p \
  /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.runner \
  bench/capability-slices/lifecycle-recovery/run-specs/candidate.yaml \
  --device emulator-5554 \
  --artifact-dir "$CANDIDATE_RUN/artifacts"
git apply -R \
  bench/capability-slices/lifecycle-recovery/patches/stale-migration-guard.patch
```

The candidate's `applied-host.patch` and provenance `identity/host.patch` are
byte-identical. The committed minimal patch has different diff metadata/context
but the same `1 insertion, 1 deletion` in `StateStore.java`. Independent APK
bytecode inspection confirmed the corresponding baseline/candidate branch
opcode reversal.

Durable oracle replay:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.lifecycle_recovery \
  --run-dir docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/baseline/attempt-1 \
  --contract bench/capability-slices/lifecycle-recovery/contract.json \
  --output /tmp/issue-71-baseline-oracle-replay.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.lifecycle_recovery \
  --run-dir docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/candidate/attempt-1 \
  --contract bench/capability-slices/lifecycle-recovery/contract.json \
  --output /tmp/issue-71-candidate-oracle-replay.json
```

Result: baseline exit 0, accountable `correct_restoration`; candidate exit 1,
accountable `stale_state`. Exit 1 is the expected rejected-candidate result, not
an execution failure.

Focused and full Python regression:

```sh
PYTHONDONTWRITEBYTECODE=1 \
  /Users/peter/projects/ai_verfication/.venv/bin/pytest \
  -p no:cacheprovider -o addopts='' -q \
  tests/bench/test_lifecycle_recovery.py \
  tests/runner/test_run_spec.py \
  tests/runner/test_system_events.py \
  tests/runner/test_journey.py \
  tests/runner/test_cli.py \
  tests/runner/test_evidence.py

PYTHONDONTWRITEBYTECODE=1 \
  /Users/peter/projects/ai_verfication/.venv/bin/pytest \
  -p no:cacheprovider -o addopts='' -q
```

Result: `155 passed in 0.22s`; `542 passed in 17.86s`.

Lane inventory verification:

```sh
PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.run_record_checksums --verify \
  docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/baseline/attempt-1
PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.run_record_checksums --verify \
  docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/candidate/attempt-1
```

Result: both verified; baseline lists 70 artifacts and candidate lists 73.

## Independent Verification Agent

The separate read-only Codex CLI process ran for 808.92 seconds under thread
`019f7944-9b71-7bf1-ab39-f777b855f64a`. Its exact prompt, output schema,
invocation, raw JSONL transcript, schema validation, and one authoritative
conclusion are under `independent-verification/`.

`conclusion.json` reports `locally_supported`, `accountable=true`, with 11/11
checks passed. Validation confirms exactly one `conclusion` key, one completed
turn, and byte-for-JSON equality between the authoritative file and the final
agent message. The conclusion notes that attempts were untracked at audit time;
this run-record commit resolves that limitation without altering the audited
attempt bytes.

## Manual probe and retained diagnostics

Before the matched pair, the same public system-event injector was probed on
`emulator-5554`. Rotation preserved v1 state. A deliberately short first
process-death wait failed closed because PID `22062` survived; retrying changed
PID `22062` to `22323`. Backup/restore returned package `Success`, token `1`,
`restoreFinished: 0`, post-restore PID `22602`, restored the original backup
configuration, and produced exact migrated v2 state. Layouts, events, and
screenshots are under `artifacts/manual-probe/`.

`attempts/non-accountable-baseline-01/` retains the first full runner attempt.
It ended `non_accountable / checkpoint_capture_error` after 95.079 seconds when
Android CLI `screen capture` returned 0 but produced no PNG with two emulators
online. The diagnosed fix uses scoped `adb -s <serial> screencap/pull/cleanup`.
The real two-device reproduction under `artifacts/diagnosis/` then produced a
valid 1080x2400 PNG and passed manifest. Emulator `emulator-5556`, owned by the
concurrent issue #70 work, was not stopped or modified.

`attempts/accountable-baseline-superseded-no-apk/` is a successful early
baseline whose executed APK hash was
`173856bbbb16728278a440b76097f207d4dcc03ac1227257215dabcfe5c02b64`.
That exact APK was not frozen before the candidate rebuild, so the attempt is
excluded rather than misrepresented. A later baseline rebuild with hash
`1a8cc170...` was moved to `artifacts/unmatched-rebuild-after-candidate/` and is
explicitly not claimed as that superseded attempt's executed APK. The final
baseline was rerun with this latter APK and retains a matching archive.

The first independent-agent process stopped on an invalid output-schema draft
before producing a conclusion. Its error transcript is retained; the corrected
schema was then used by the single completed audit.

## Artifact inventory

- `baseline/attempt-1/`, `candidate/attempt-1/`: final accountable lanes with
  independent 70- and 73-entry manifests.
- `independent-verification/`: prompt, schema-bound conclusion, raw transcript,
  invocation identity, validation, and the pre-audit schema error.
- `artifacts/tdd/`: 37 red/green records covering oracle classes, system events,
  event/ExecutionRecord binding, provenance, matched assets, and screenshot
  diagnosis.
- `artifacts/build/`, `artifacts/manual-probe/`, `artifacts/diagnosis/`: Gradle,
  APK, installation, real-device layouts/screenshots/events, and diagnosis.
- `attempts/`: excluded attempts retained with explicit reasons.
- `issue-71.json`: fetched issue brief used by the independent audit.
- `issue-comment.md`, `parent-comment.md`: exact GitHub evidence updates.
- `checksums.sha256`: root inventory generated only after all final evidence and
  review records are frozen.

Tool versions are in `artifacts/tool-versions.txt`: Android CLI
`1.0.15498356`, adb `37.0.0`, OpenJDK `17.0.19`, Gradle `9.1.0`, Python
`3.11.15`, Codex CLI `0.144.5`, and Git `2.50.1`.

## Known gaps and claim boundary

- This is one local API-35 emulator and local backup transport, not an Android
  API/device/locale/RTL/form-factor matrix. That separate scope remains #72.
- Scoped multi-device screenshots retain plain PNGs and UI layouts but no
  Android-CLI annotated PNG, because this Android CLI version cannot select a
  device for annotation.
- The separate Verification Agent performed a read-only evidence audit and did
  not rerun the device Journey; its conclusion is bound to the two retained
  attempts and archived APKs.
- Absolute `/tmp` paths inside immutable runner receipts record where the live
  attempts occurred. Durable copies are replayed from this directory and are
  covered by the lane and root checksum inventories.
- No detection-rate, Goldset, compatibility-matrix, cloud-provider, or upstream
  acceptance is asserted.
