# Issue #209 — DIL-M1.11 one accountable preserved-state runtime attempt

Status: passed; evidence is committed with the implementation.

This run implements the production-shaped **Runtime Attempt** lane seam
(`runtime_attempt_v1`) and drives one prepared control lane end to end on a
**Recording Runtime Device**, concluding that its unfinished expression
survives recreation. It is the single-lane happy-path tracer that the failure
matrix and the four-lane family loop (#210–#218) build on.

Boundary: no Gradle build, no Android CLI, no adb, no emulator or physical
device, no model, and no agent backend ran in this issue. Every device-side
effect below is recorded simulation text admitted by the recording device, and
the attempt is labelled `recorded_simulation`. The production `AdbRuntimeDevice`
exists and is unit-tested against a stub command runner, but was not pointed at
a live serial.

## Scope and identities

- Issue: [#209](https://github.com/yangliang2/ai_verification/issues/209)
- Parent: [#199](https://github.com/yangliang2/ai_verification/issues/199)
- Branch: `main`
- Fixed point reviewed: `f87ae04` (`Record the reopened #209 as the DIL-M1 chain head in HANDOFF`)
- Implementation commits: the commit carrying this run record
- Seam: `runtime_attempt_v1`
- Claim boundary: `one_accountable_preserved_state_runtime_attempt`
- Evidence class: `recorded_simulation`
- Lane: `ocrc-v1-lane-01` (`ocrc-v1-lane-01:opencalc-preserve-expression`)
- Family: `opencalc-runtime-calibration-v1` / `v1`
- Target: `com.darkempire78.opencalculator.debug` /
  `com.darkempire78.opencalculator.activities.MainActivity`

Delivered surfaces:

| Path | Lines | SHA-256 |
|---|---:|---|
| `src/aiverify/bench/runtime_attempt.py` | 5061 | `686f3a19f7def7be5865c4b31ecb2d5e0c280980c798a37f13a601bc3f66eb58` |
| `src/aiverify/runtime_attempt.py` (compatibility shim) | 3 | `580e20b93686c04c7dbcdd9779f0fa42e70b43b8e9f62f40cf1c9a2c253bf739` |
| `tests/bench/test_runtime_attempt.py` | 1079 | `a2673970de163b5e4481a6989d47ad2bd073cdb0af23d2f426fd9234756ca4e4` |

## What the seam implements

The attempt runs the frozen fifteen-phase pipeline and fails closed on any
deviation:

```text
prepare-inputs → establish-execution-record → device-session → deploy-sealed-apk
→ attempt-setup → open-target-log-window → canonical-launch → journey
→ boundary-precondition → lifecycle-rotation → collect-post-event-observation
→ close-target-log-window → prove-lifecycle-transition → evaluate-oracles
→ finalize-receipt
```

- **ExecutionRecord first.** `ExecutionRecordStore.establish` runs before the
  first device mutation; the record is finalised exactly once, on both the
  accountable and the aborted path.
- **Runtime Attempt Device protocol.** `RecordingRuntimeDevice` (bounded
  recorded simulation) and `AdbRuntimeDevice` (production adb/Android CLI
  vectors) share one operation ledger. Each admitted operation is counted
  exactly once no matter how many command vectors it fans out into.
- **Session identity.** The device session binds serial, package, activity,
  boot id, Android CLI/adb/emulator versions, AVD name, AVD config digest,
  system image manifest digest, API level, fingerprint, ABI, model, hardware,
  display size/density, and the frozen settings set.
- **Sealed APK only.** The deployment vector is the Android CLI `run` vector for
  the preparation handoff path; the installed bytes are pulled back, hashed, and
  compared with the handoff digest. Handoff drift is rejected before any device
  side effect.
- **Attempt setup.** One `pm clear`, a proven absence of target processes, and
  the two admitted setting writes (`accelerometer_rotation`, `user_rotation`)
  forced to portrait, with the resulting rotation state re-read and verified.
  There is no poll, rewrite, retry, or compensation.
- **Marker-bounded log window.** The start marker is written before the
  canonical launch; the end marker and the all-buffer dump close the window
  after the post-event observation. Marker uniqueness, ordering, and the
  exactly-once foreground component check are proven from the captured text.
- **Lifecycle transition receipt.** One landscape dispatch, every bounded
  observation retained (budget 50, interval 0.1 s), and the provisional
  `opencalc-lifecycle-signature-v1` (`destroy` → `create` → `resume`) proven
  from the sliced window.
- **Oracles.** L1 is never `pass`: a complete window with no attributable
  crash/ANR concludes `inconclusive`; an attributed target crash concludes
  `fail`. A valid post-event input node with the exact `12+34` text yields L2
  `pass`, and its absence yields L2 `fail` with defect class `state_loss`.
- **Exactly-once budget, zero retries.** `expected_device_mutation_order` and
  the frozen read/mutation tables are enforced; the receipt carries
  `retries: 0`.
- **Independent verifier.** `verify_runtime_attempt` re-reads the sealed receipt
  and artifacts with no device and no trust in recorded verdicts: it recomputes
  the receipt identity, the constants, the evidence class from the bound device
  identity, the record binding, every artifact digest, the frozen artifact kind
  set (duplicate or unknown kinds are rejected), the device budget, the marker
  window, the lifecycle signature, the boundary precondition, the L1
  attribution, the L2 evaluation, and the reduced verdict.

## Acceptance evidence

| # | Criterion | Evidence |
|---:|---|---|
| 1 | ExecutionRecord established before the first external side effect, finalised exactly once | `test_execution_record_predates_the_first_device_mutation` samples the record around every mutation; `phase_errors == []`, `execution.status == "completed"` |
| 2 | Runtime Device Session receipt binds the device, boot, Android CLI, emulator, adb, system image, display profile, and settings | `test_device_session_receipt_binds_the_selected_device`; `SESSION_REQUIRED_FIELDS`, `SESSION_IDENTITY_SETTINGS`, AVD/system-image digests |
| 3 | Only the Sealed Runtime APK is deployed and installed bytes match the handoff | `test_sealed_apk_deployment_binds_installed_bytes_to_the_handoff`, `test_sealed_apk_drift_is_rejected_before_any_device_side_effect` |
| 4 | Attempt setup clears package data once, proves no target process, forces portrait via the two admitted setting writes, verifies the state | `test_attempt_setup_clears_package_data_and_forces_portrait_once` |
| 5 | Marker-bounded Target Log Window opens before the canonical launch; exact foreground component verified once | `test_marker_bounded_window_starts_before_the_canonical_launch` |
| 6 | Deterministic driver inputs `12+34`; runner proves the exact boundary precondition | `test_driver_enters_the_boundary_precondition_through_the_frozen_trajectory` |
| 7 | One orientation event dispatched, all bounded post-event observations kept, frozen lifecycle transition receipt proven | `test_landscape_event_and_lifecycle_transition_are_frozen` |
| 8 | Complete window → L1 `inconclusive` with no attributable crash/ANR; valid post-event node → L2 `pass` for the exact `12+34` | `test_recording_lane_concludes_one_accountable_preserved_state`; defect side: `test_state_loss_lane_concludes_accountable_with_a_failing_oracle`, `test_injected_target_crash_is_attributed_to_the_target_package` |
| 9 | Terminal `accountable_concluded` with complete references and zero retries | `REQUIRED_ACCOUNTABLE_COMPONENTS` (12 components), `retries == 0`, `test_frozen_device_budget_is_spent_exactly_once_in_order` |
| 10 | Recording-device integration test drives the public seam; runner behaviour stays green; the run record records the bounded result | `tests/bench/test_runtime_attempt.py` (22 test functions, 26 cases) drives `execute_runtime_attempt`/`verify_runtime_attempt` only; full-suite baseline comparison below; `verification/lane-01-attempt/` |

The predicate tests that need to read past the record binding re-sign both
sides (`_restamp_receipt`) so the verifier is pushed into its recomputation
paths: a tampered verdict reaches `attempt_oracle_invalid`, a tampered budget
reaches `attempt_device_budget_violated`/`invalid`, an appended duplicate or
unknown artifact kind reaches `attempt_artifact_inventory_invalid`, and a
relabelled `evidence_class` reaches `attempt_evidence_class_mismatch`.

## Verification commands and results

Tool versions: CPython `3.12.13`, pytest `9.1.1`, Ruff `0.16.9`, mypy `2.3.1`,
uv `0.10.7`, Git `2.50.1 (Apple Git-155)`.

```text
.venv/bin/python -m pytest tests/bench/test_runtime_attempt.py \
  tests/bench/test_runtime_calibration.py tests/test_runtime_preparation.py \
  tests/test_runtime_sealed_apk.py --junitxml=verification/focused-pytest.xml
```

Result: **119 passed, 0 failed, 0 skipped** in 56.366 s
(`verification/focused-pytest.xml`).

```text
.venv/bin/python -m pytest --junitxml=verification/full-pytest.xml
```

Result: **1468 tests, 18 failed, 52 skipped** in 434.243 s
(`verification/full-pytest.xml`).

Baseline comparison — the same command in a clean `git worktree` at the
reviewed fixed point `f87ae04` (`verification/baseline-pytest.xml`):

| Run | Tests | Failed | Skipped | Time |
|---|---:|---:|---:|---:|
| baseline (`f87ae04`) | 1442 | 18 | 52 | 448.294 s |
| with #209 | 1468 | 18 | 52 | 434.243 s |

`diff verification/full-pytest-failures-baseline.txt
verification/full-pytest-failures-current.txt` is empty: the failure sets are
identical line for line, so **no existing runner behaviour regressed**. The
`+26` tests are the new cases in `tests/bench/test_runtime_attempt.py`.
The 18 failures are pre-existing and have two independent causes, neither
related to this change and both present at `f87ae04`:
`test_runtime_family_preparation.py` (17) trips
`mapping_predecessor_input_mismatch` because the frozen issue-206
mapping-release fixture pins another workstation's absolute `candidate_root`
(`/Users/peter/...`); `test_m7_runtime_probe.py` (1) is not a path failure —
the Gradle wrapper cannot fetch `gradle-9.1.0-bin.zip` because the TLS
handshake to `services.gradle.org` is intercepted and the wrapper JVM refuses
the interception certificate (`PKIX path building failed`; the wrapper cache
holds only a zero-byte `.zip.part`). The 17 fixture-path failures were repaired
afterwards by pointing the gates at the locally reissued v2 stage:
[`docs/runs/2026-09-29-family-preparation-fixture-correction/`](../2026-09-29-family-preparation-fixture-correction/README.md).
The m7 failure remains open and environment-bound.

```text
uvx ruff check src/aiverify/bench/runtime_attempt.py src/aiverify/runtime_attempt.py \
  tests/bench/test_runtime_attempt.py
```

Result: `All checks passed!` (Ruff `format --check` is not a repository gate —
148 pre-existing files are not Ruff-formatted.)

```text
MYPYPATH=src uvx mypy --python-executable .venv/bin/python \
  src/aiverify/bench/runtime_attempt.py src/aiverify/runtime_attempt.py
```

Result: one environment-only error, `Library stubs not installed for "yaml"`
(the repository has no `types-PyYAML` and no mypy configuration). mypy over
`tests/` is not a repository gate: 572 pre-existing errors in 34 files.

`python -m compileall` over all three delivered files: passed.

### Bounded simulation result, re-verified from the committed bytes

`verification/lane-01-attempt/` is one real execution of the public seam
(`execute_runtime_attempt`) driving `ocrc-v1-lane-01` on the recording device
with a pinned clock; `verification/lane-01-attempt-repeat/` is a second run.

- Receipt: `attempt-receipt.json`, 30722 bytes, SHA-256
  `5e4c2a004e022db9edea2b3bc5b4e9e332f7fae02172247455094d1f64cc5f0c`,
  identity `cd9dcdef36aaaffa7ea58a02de26e8e51183dc48f7bff9b7958be0ea3d9fed07`
- Terminal state `accountable_concluded`, verdict `inconclusive`, `retries: 0`,
  evidence class `recorded_simulation`
- ExecutionRecord: `execution-record.json`, `lifecycle_state: completed`,
  `process_outcome: {"exit_code": 0}`,
  `execution.accounting_eligible: true`, provenance bound to the receipt digest
  above
- Device budget actually spent:
  `canonical_launch 1, clear_log_buffers 1, clear_package_data 1, deploy_apk 1,
  dispatch_orientation 1, dump_all_buffers_epoch 1, probe_session 1,
  read_foreground_state 3, read_installed_apk 1, read_layout 8,
  read_rotation_state 1, tap 5, target_process_ids 1, write_log_marker 4,
  write_rotation_setting 2`
- Artifacts: 7 frozen kinds (journey result/events/invocation, boundary layout,
  post-event layout, target log window 1832 B, lifecycle window 1182 B)
- `verification/lane-01-verification.json`: re-running
  `verify_runtime_attempt` on the committed directory returns
  `"verified": true` with 16 checks (7 artifact kinds + device-budget,
  mutation-order, mutation-vectors, log-window, lifecycle-signature, boundary,
  l2, l1, verdict)
- `verification/lane-01-conclusion-shape.json`: the second run reproduces the
  conclusion exactly (state, reason, verdict, retries, evidence class, budget
  counts, L1/L2 outcomes, boundary text, poll count). Only the per-run
  `attempt_id`, the per-verdict id, and the marker-bound window digest differ,
  and they differ by design

## Code review

See [`code-review.md`](code-review.md). Two blockers were raised; the
production-device operation accounting blocker was fixed before publication and
is now covered by a regression test. The layout-read budget tension is recorded
as an open gap for the failure-matrix issues.

## Known gaps

1. **Layout-read budget vs. bounded wait polling.** The frozen read contract
   charges `len(actions) + 2 = 8` layout reads, while the deterministic driver's
   first `wait` owns surface readiness through a bounded observation poll
   (`timeout_ms // interval_ms + 1` observations, one `read_layout` each). The
   recording device's surface is ready on the first observation, so this issue
   cannot exhibit the difference; on a real device a slow surface would exceed
   the budget and make the attempt non-accountable. The read-budget semantics
   must be decided before a real-device attempt is claimed, and that decision
   belongs to the failure-matrix/family issues (#210–#218).
2. **Orphan receipt on record-finalisation failure.** The receipt is written
   before the record is finalised; a crash in between leaves a receipt that
   binds no terminal record. The verifier then fails closed
   (`attempt_record_binding_mismatch`), so the residue cannot be mistaken for
   evidence, but a durable repair path is still missing.
3. **No live device exercise.** `AdbRuntimeDevice` is unit-tested through a stub
   runner only; no emulator or physical device was available to this issue, and
   no device session or runtime attempt record outside the recording device was
   created.
4. **Pre-existing environment-bound failures.** The 18 failures described above
   are inherited from `f87ae04`. Seventeen are the fixture-path failures
   (`mapping_predecessor_input_mismatch` against the committed issue-206 stage);
   they were repaired afterwards — see
   [`docs/runs/2026-09-29-family-preparation-fixture-correction/`](../2026-09-29-family-preparation-fixture-correction/README.md).
   One is the m7 Gradle distribution download blocked by TLS interception; it
   remains open in this environment.
