# Issue #210 — DIL-M1.12 fail closed across runtime pre-observation phases

Status: passed; evidence is committed with the implementation.

This run hardens the Runtime Attempt lane seam (`runtime_attempt_v1`) shipped by
#209: every material failure before the product observation boundary now
terminates at the phase that produced it, with one canonical non-accountable
reason, one externally derived failure scope, and exactly one finalization of
the existing ExecutionRecord. No forbidden setup action — pre-deployment smoke
launch, package-reset retry, settings rewrite, compensation, emulator restart,
fallback deployment — is reachable, and no pre-observation failure fabricates a
log-window receipt or an authoritative oracle.

Boundary: no Gradle build, no Android CLI, no adb, no emulator or physical
device, no model, and no agent backend ran in this issue. Every device-side
effect below is recorded simulation text admitted by `RecordingRuntimeDevice`,
and the attempt is labelled `recorded_simulation`. The production
`AdbRuntimeDevice` was not pointed at a live serial.

## Scope and identities

- Issue: [#210](https://github.com/yangliang2/ai_verification/issues/210)
- Parent: [#199](https://github.com/yangliang2/ai_verification/issues/199)
- Branch: `main`
- Fixed point reviewed: `e2aee56` (`Implement one accountable preserved-state runtime attempt (#209)`)
- Implementation commits: the commit carrying this run record
- Seam: `runtime_attempt_v1`
- Claim boundary: `one_accountable_preserved_state_runtime_attempt`
- Evidence class: `recorded_simulation`
- Lane: `ocrc-v1-lane-01` (`ocrc-v1-lane-01:opencalc-preserve-expression`)
- Target: `com.darkempire78.opencalculator.debug` /
  `com.darkempire78.opencalculator.activities.MainActivity`

Delivered surfaces:

| Path | Lines | SHA-256 |
|---|---:|---|
| `src/aiverify/bench/runtime_attempt.py` | 5415 | `8eefe3800777443100340576728ba7da60a3b7251d160773d026533b7a4eaa81` |
| `src/aiverify/runtime_attempt.py` (compatibility shim, unchanged) | 3 | `580e20b93686c04c7dbcdd9779f0fa42e70b43b8e9f62f40cf1c9a2c253bf739` |
| `tests/bench/test_runtime_attempt.py` | 1852 | `f1f3fb9dc50eb2d2566727923d3bfd35ffd2acc0a6dfa349522bf681234f427d` |

## What the change implements

The fifteen frozen phases and the accountable happy path are unchanged. The
change makes every non-accountable exit a first-class, verifier-checked object:

- **Failure scope vocabulary.** `FAILURE_SCOPE_LANE_LOCAL` / `_SHARED` /
  `_UNKNOWN` reuse the exact vocabulary that `runtime_family_preparation.py`
  already binds for family orchestration. `FAILURE_SCOPES` is the one frozen
  table mapping all 22 canonical reasons to a scope, and `failure_scope(reason)`
  derives the scope from the reason alone — never from a recorded label — so a
  lane and the independent verifier cannot disagree. Unlisted reasons fall back
  to `unknown` (abort).
- **Frozen phase ledger.** Every attempt records one ledger entry per phase in
  `FROZEN_PHASES` order. An accountable attempt owes all fifteen phases `ok`; a
  non-accountable attempt owes a strict ordered prefix whose final entry is its
  one failed phase. `_verify_phase_ledger` recomputes this from receipt bytes.
- **Fail closed at the declared boundary.** `run_pipeline` attributes every
  untyped error raised after the record exists to the running phase
  (`self.phases[-1]["phase"]`), maps it to a canonical reason when one exists
  and to `device_io_failed` otherwise, and terminalises it as one abort. A
  rejection before the record exists propagates untouched, so no fabricated
  record is created. Device-session drift (serial, required fields, frozen
  settings) fails at `device-session`; post-admission handoff APK drift and
  deployment/installed-read failures fail at `deploy-sealed-apk`; package-clear
  failure or contradiction, a residual target process, setting-write failure,
  and portrait read-back contradiction fail at `attempt-setup`; log-buffer clear
  and start-marker failures fail at `open-target-log-window`, before the
  canonical launch; launch and pre-Journey foreground failures fail at
  `canonical-launch`.
- **Marker window, exactly once.** A failure before the start-marker exists
  fabricates no `target_log_window` receipt. Once the window is open, the abort
  path closes it through terminal finalization: `window_end_dispatched` makes
  the end marker at-most-once across the whole attempt, the capture is recorded
  as `partial` (or `unavailable_after_abort`), and a second marker is never
  written.
- **Exactly-once finalization, no authoritative oracle.**
  `conclude_non_accountable` drops any partially computed `oracles` component
  before sealing the receipt; `_conclude_receipt_failure` finalizes the existing
  record when not even a receipt can be sealed (exit code 2, one
  `finalize-receipt` phase error, no receipt path, no provenance).
- **Independent verifier.** `_verify_non_accountable_evidence` refuses a
  non-accountable receipt that carries an authoritative oracle
  (`attempt_non_accountable_oracle_invalid`), requires the five-key failure
  object, binds its reason to the terminal reason, recomputes
  `scope == failure_scope(reason)` (`attempt_failure_scope_invalid`), and
  requires the failure phase to be the terminal ledger phase. Verification
  reports `phase-ledger`, `failure-scope`, and `no-authoritative-oracle` checks
  next to the existing deterministic recomputations.

## Acceptance evidence

| # | Criterion | Evidence |
|---:|---|---|
| 1 | Static verifier, source, preparation, tool, device-session, and APK identity checked at their declared boundaries; drift produces a canonical non-accountable reason | Matrix `session-probe-refused`, `session-serial-drift`, `session-required-field-missing`, `session-settings-missing` (`device_session_unavailable`, phase `device-session`); `sealed-apk-drifted-after-admission` (`sealed_apk_bytes_drifted`, phase `deploy-sealed-apk`). `_check_frozen_inputs`/`_check_run_spec_binding` still reject non-frozen inputs in `prepare-inputs` before any device side effect (`test_pre_side_effect_rejections_leave_the_recording_device_untouched`) |
| 2 | Deployment failure, installed-byte mismatch, package-reset failure/contradiction, residual target process, setting-write failure, portrait verification failure stop before canonical observation | Matrix `deployment-refused`/`installed-read-refused` (`sealed_apk_deployment_failed`), `installed-bytes-drifted` (`sealed_apk_bytes_drifted`), then `package-clear-refused`, `package-clear-contradicted`, `target-process-residual`, `setting-write-refused`, `rotation-read-refused`, `portrait-contradicted` (all `attempt_setup_failed`). Each case asserts the exact frozen phase prefix and that no later phase dispatched a command |
| 3 | Only package clear and the two declared rotation-setting writes are reachable device mutations; every permitted write at most once | `_assert_admitted_mutation_vectors` runs on every matrix case: each admitted vector appears at most once, marker vectors bind the lane/attempt/marker kind, and every other mutation must be in the admitted set. `EXPECTED_DEVICE_MUTATION_COUNTS` and `test_frozen_device_budget_is_spent_exactly_once_in_order` keep the accountable path at `clear_package_data 1`, `write_rotation_setting 2` |
| 4 | No pre-deployment smoke launch, package-reset retry, settings rewrite, compensation, emulator restart, or fallback deployment | The uniqueness assertion above, plus per-case equality between dispatched operations and the expected frozen sequence, plus `_RetryTapDevice` (a forbidden second tap) and `_OccupiedReceiptDevice` proving the attempt aborts instead of retrying. `canonical_launch` is never dispatched before `deploy-sealed-apk` completed, and `deploy_apk` never appears twice |
| 5 | Log-start failure stops before canonical launch; launch failure and foreground mismatch stop before Journey dispatch | Matrix `log-clear-refused`/`start-marker-refused` (phase `open-target-log-window`, no `canonical_launch` in dispatched mutations); `canonical-launch-refused`/`foreground-read-refused`/`foreground-component-contradicted` (phase `canonical-launch`, no `tap` in dispatched mutations) |
| 6 | A failure before the target-window start marker fabricates no log-window receipt; a failure after it still closes the marker window through terminal finalization | Matrix not-opened branch: no `target_log_window` component and no markers. Opened branch (`canonical-launch-refused`, `foreground-*`): `write_log_marker` count equals expected + 1 terminal end marker. `test_terminal_finalization_closes_the_marker_window_exactly_once` and `test_a_failed_window_capture_never_dispatches_a_second_end_marker` (partial capture keeps 4 markers, never 5) |
| 7 | Every handled path finalizes the existing ExecutionRecord once with ordered phase errors and no authoritative oracle | `test_a_receipt_write_failure_finalizes_the_record_exactly_once` (exit 2, no receipt path/provenance, one ordered `finalize-receipt` error, record state `failed`); `test_a_post_oracle_failure_seals_a_receipt_without_an_authoritative_oracle`; every matrix case asserts one record update with `exit_code 2` and a `phase_errors` ledger matching the frozen prefix |
| 8 | Failure scope classified as lane-local, shared, or unknown using externally visible evidence suitable for later family orchestration | `FAILURE_SCOPES` (22 reasons) and `failure_scope()` in `src/aiverify/bench/runtime_attempt.py`; `test_frozen_phase_and_scope_tables_are_the_frozen_contract` pins the tables; `test_verification_rejects_a_drifted_failure_scope_and_ledger` shows the verifier recomputes the scope from the reason and rejects a tampered one |
| 9 | Recording-device tests assert exact phase ordering and forbidden-command unreachability for every material pre-observation failure | `test_pre_observation_failures_fail_closed_at_the_canonical_phase` (19 labelled cases, 4 device-session + 4 deploy + 6 attempt-setup + 2 log-window + 3 canonical-launch) asserting reason, scope, phase, ordered ledger, exact dispatched operations, and admissible mutation vectors |
| 10 | Focused/full regressions and a committed run record document counts, artifacts, checksums, and remaining simulated-device limitations | This document; `verification/focused-pytest.xml` (145 passed), `verification/full-pytest.xml`, `verification/baseline-pytest.xml`, `verification/checksums.sha256`, `verification/pre-observation-matrix.json`, `verification/attempts/*`, `verification/handoffs/*` |

## Verification commands and results

Tool versions: CPython `3.12.13`, pytest `9.1.1`, Ruff `0.16.9`, mypy `2.3.1`,
uv `0.10.7`, Git `2.50.1 (Apple Git-155)`.

```text
.venv/bin/python -m pytest tests/bench/test_runtime_attempt.py \
  tests/bench/test_runtime_calibration.py tests/test_runtime_preparation.py \
  tests/test_runtime_sealed_apk.py \
  --junitxml=verification/focused-pytest.xml
```

Result: **145 passed, 0 failed, 0 skipped** in 63.198 s
(`verification/focused-pytest.xml`); `tests/bench/test_runtime_attempt.py`
alone is 30 test functions / 52 cases.

```text
.venv/bin/python -m pytest --junitxml=verification/full-pytest.xml
```

Result: **1494 tests, 18 failed, 52 skipped** in 680.391 s
(`verification/full-pytest.xml`).

Baseline comparison — the same command in a clean `git worktree` at the
reviewed fixed point `e2aee56` (`verification/baseline-pytest.xml`):

| Run | Tests | Failed | Skipped | Time |
|---|---:|---:|---:|---:|
| baseline (`e2aee56`) | 1468 | 18 | 52 | 672.370 |
| with #210 | 1494 | 18 | 52 | 680.391 |

`diff verification/full-pytest-failures-baseline.txt
verification/full-pytest-failures-current.txt` is empty: the failure sets are
identical line for line, so **no existing runner behaviour regressed**. The
`+26` tests are the new cases in `tests/bench/test_runtime_attempt.py`.
The 18 failures are pre-existing and environment-bound: the frozen
issue-206 mapping-release fixtures pin another workstation's absolute
`candidate_root` (`/Users/peter/...`), so `test_runtime_family_preparation.py`
(17) and `test_m7_runtime_probe.py` (1) fail on any other machine at `e2aee56`
too. They are unrelated to this change and are not repaired here.

```text
uvx ruff check src/aiverify/bench/runtime_attempt.py src/aiverify/runtime_attempt.py \
  tests/bench/test_runtime_attempt.py
```

Result: `All checks passed!`

```text
MYPYPATH=src uvx mypy --python-executable .venv/bin/python \
  src/aiverify/bench/runtime_attempt.py src/aiverify/runtime_attempt.py
```

Result: one environment-only error, `Library stubs not installed for "yaml"`
(the repository has no `types-PyYAML` and no mypy configuration), identical to
the #209 baseline.

`python -m compileall` over all three delivered files: passed.

### Pre-observation failure matrix, re-verified from the committed bytes

`verification/generate_evidence.py` drives the public seam
(`execute_runtime_attempt` + `verify_runtime_attempt`) through 19 labelled
failures and asserts, for each case, the canonical reason, the derived scope,
the terminal phase, the ordered phase ledger, the absence of an authoritative
oracle, one finalization with exit code 2, and `"verified": true`. The matrix
is written to `verification/pre-observation-matrix.json` with the raw bytes of
every attempt under `verification/attempts/<label>/` and every handoff APK
under `verification/handoffs/<label>/`.

| Label | Reason | Scope | Terminal phase | Phases | Mutations | Artifacts | Checks |
|---|---|---|---:|---:|---:|---:|---:|
| `session-probe-refused` | `device_session_unavailable` | shared | `device-session` | 3 | 0 | 1 | 3 |
| `session-serial-drift` | `device_session_unavailable` | shared | `device-session` | 3 | 0 | 1 | 3 |
| `session-required-field-missing` | `device_session_unavailable` | shared | `device-session` | 3 | 0 | 1 | 3 |
| `session-settings-missing` | `device_session_unavailable` | shared | `device-session` | 3 | 0 | 1 | 3 |
| `sealed-apk-drifted-after-admission` | `sealed_apk_bytes_drifted` | shared | `deploy-sealed-apk` | 4 | 0 | 2 | 3 |
| `deployment-refused` | `sealed_apk_deployment_failed` | shared | `deploy-sealed-apk` | 4 | 0 | 2 | 3 |
| `installed-read-refused` | `sealed_apk_deployment_failed` | shared | `deploy-sealed-apk` | 4 | 1 | 2 | 3 |
| `installed-bytes-drifted` | `sealed_apk_bytes_drifted` | shared | `deploy-sealed-apk` | 4 | 1 | 2 | 3 |
| `package-clear-refused` | `attempt_setup_failed` | lane_local | `attempt-setup` | 5 | 1 | 3 | 3 |
| `package-clear-contradicted` | `attempt_setup_failed` | lane_local | `attempt-setup` | 5 | 2 | 3 | 3 |
| `target-process-residual` | `attempt_setup_failed` | lane_local | `attempt-setup` | 5 | 2 | 3 | 3 |
| `setting-write-refused` | `attempt_setup_failed` | lane_local | `attempt-setup` | 5 | 2 | 3 | 3 |
| `rotation-read-refused` | `attempt_setup_failed` | lane_local | `attempt-setup` | 5 | 4 | 3 | 3 |
| `portrait-contradicted` | `attempt_setup_failed` | lane_local | `attempt-setup` | 5 | 4 | 3 | 3 |
| `log-clear-refused` | `target_log_window_unavailable` | shared | `open-target-log-window` | 6 | 4 | 4 | 3 |
| `start-marker-refused` | `target_log_window_unavailable` | shared | `open-target-log-window` | 6 | 5 | 4 | 3 |
| `canonical-launch-refused` | `canonical_launch_failed` | lane_local | `canonical-launch` | 7 | 7 | 5 | 4 |
| `foreground-read-refused` | `canonical_launch_failed` | lane_local | `canonical-launch` | 7 | 8 | 5 | 4 |
| `foreground-component-contradicted` | `canonical_launch_failed` | lane_local | `canonical-launch` | 7 | 8 | 5 | 4 |

"Mutations" counts dispatched device mutations: the four device-session cases
mutate nothing; the deploy cases mutate at most the admitted `deploy_apk`; the
attempt-setup cases stop at or before the two rotation-setting writes; the
log-window cases stop at or before the start marker; the canonical-launch cases
stop at or before the launch, and the three window-opened cases dispatch
exactly one extra terminal end marker (`write_log_marker` = expected + 1).
No case ever dispatches a forbidden operation, and no case reports any
`phases` ledger that is not a strict frozen prefix.

## Artifact inventory

70 files, 1.1 MB under this run record: this document, its checksum, and
68 evidence artifacts.

- `verification/pre-observation-matrix.json` — the 19-case matrix with the
  frozen phase/scope tables and, per case, the expected and recorded failure,
  phase ledger, components, dispatched mutations/vectors, markers, operation
  counts, record summary, verification summary, and receipt bytes/digest.
- `verification/attempts/<label>/attempt-receipt.json` (19) and
  `execution-record.json` (19) — the raw sealed bytes of every case.
- `verification/attempts/<label>/target-log-window.log` (3) — the terminal
  finalization capture for the three window-opened cases
  (`canonical-launch-refused`, `foreground-read-refused`,
  `foreground-component-contradicted`).
- `verification/handoffs/<label>/sealed-runtime.apk` (19) — the handoff bytes
  the recorded deployment vector points at, kept in-repo so the vectors stay
  re-verifiable.
- `verification/generate_evidence.py` — the self-checking matrix driver.
- `verification/focused-pytest.xml`, `full-pytest.xml`, `baseline-pytest.xml`,
  `full-pytest-failures-{baseline,current}.txt` — the regression reports.
- `verification/extract_failures.py` — the failure-set extractor used for the
  baseline diff.
- `verification/checksums.sha256` — SHA-256 for `README.md` and every artifact
  under `verification/`; the delivered source files are checksummed in the
  table above.

## Known gaps

1. **No live device exercise.** As in #209, `AdbRuntimeDevice` is unit-tested
   through a stub command runner only; no emulator or physical device was
   available, and every matrix byte above is recorded simulation text. The
   real-device shape of these failures (adb error text, slow surfaces, HAL
   quirks) remains unproven.
2. **Recording-device determinism.** The matrix fails the device through
   explicit policy knobs (`fail_operations`, `reported_serial`,
   `installed_digest_override`, `residual_target_process`, `reported_rotation`,
   `reported_foreground_component`, `_SealedApkDriftDevice`, `_RetryTapDevice`,
   `_OccupiedReceiptDevice`), so it proves the seam's own contract, not a
   device's behaviour.
3. **Layout-read budget vs. bounded wait polling.** Inherited from #209: the
   frozen read contract charges `len(actions) + 2 = 8` layout reads while the
   driver's first `wait` owns surface readiness through a bounded poll. The
   recording device's surface is ready on the first observation, so this issue
   cannot exhibit the difference; the decision still belongs to the
   family-orchestration issues.
4. **Orphan receipt on record-finalisation failure.** Inherited from #209: a
   crash between receipt sealing and record finalization leaves a receipt that
   binds no terminal record; the verifier fails closed on it
   (`attempt_record_binding_mismatch`), but no durable repair path exists.
5. **Pre-existing environment-bound failures.** The 18 failures described above
   are inherited from `e2aee56` and are not repaired in this issue.

## Follow-ups

- #211 (family orchestration) consumes `failure_scope` to decide whether the
  remaining lanes continue after a lane-local non-accountability; the scope
  table is frozen here for that consumer.

## Checksums

`verification/checksums.sha256` lists the SHA-256 of `README.md` and of every
artifact under `verification/` (70 files, 1.1 MB in this directory tree). Run
`shasum -a 256 -c verification/checksums.sha256` from this directory to
re-verify.
