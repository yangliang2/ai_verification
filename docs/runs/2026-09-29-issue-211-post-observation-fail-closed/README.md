# Issue #211 — DIL-M1.13 fail closed across boundary, lifecycle, log, and oracle evidence

Status: passed; evidence is committed with the implementation.

This run extends the Runtime Attempt lane seam (`runtime_attempt_v1`) shipped by
#209 and hardened before the observation boundary by #210: every material
failure at or after the boundary precondition now terminates at the phase that
produced it, keeps the evidence it already took, and closes the terminal
artifacts — while an attempt whose evidence does hold still concludes
accountable with a real L1/L2 oracle. Non-accountability and a product verdict
are now disjoint outcomes of the same seam: a capture, parse, checksum, identity,
or lifecycle-proof failure can never be reported as an L1/L2 result, and a
complete attributable capture without a target crash/ANR is never reported as an
observation failure.

Boundary: no Gradle build, no Android CLI, no adb, no emulator or physical
device, no model, and no agent backend ran in this issue. Every device-side
effect below is recorded simulation text admitted by `RecordingRuntimeDevice`,
and the attempt is labelled `recorded_simulation`. The production
`AdbRuntimeDevice` was not pointed at a live serial.

## Scope and identities

- Issue: [#211](https://github.com/yangliang2/ai_verification/issues/211)
- Parent: [#199](https://github.com/yangliang2/ai_verification/issues/199)
- Branch: `main`
- Fixed point reviewed: `2a5d16b` (`Fail closed across runtime pre-observation phases (#210)`)
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
| `src/aiverify/bench/runtime_attempt.py` | 5902 | `17177d7c6ffb89de1c4d260084ebe55fc2185a42dd7c9afd57f5ba058da011a0` |
| `src/aiverify/runtime_attempt.py` (compatibility shim, unchanged) | 3 | `580e20b93686c04c7dbcdd9779f0fa42e70b43b8e9f62f40cf1c9a2c253bf739` |
| `tests/bench/test_runtime_attempt.py` | 2809 | `fa8968b0fef99644d9891df8691cd0af0be74c561bf3b64de2cb79ae9a7db4fe` |

## What the change implements

The pre-boundary behaviour of #210 is unchanged: the same 22 canonical reasons,
the same scope vocabulary, the same ordered phase ledger, and the same
marker-window finalization. The change adds the post-boundary half of the seam:

- **A sixteenth phase closes the post-cell identity.** `close-post-cell-identity`
  sits between `close-target-log-window` and `prove-lifecycle-transition` in
  `FROZEN_PHASES`, and `post_cell_identity` joins
  `REQUIRED_ACCOUNTABLE_COMPONENTS`. The phase re-probes the session once after
  the cell, records the probe as `operation: "probe_session"` with its
  commands/return codes, and compares 14 required session fields, `serial`, and
  10 frozen settings against the pre-cell receipt via
  `session_identity_drift(reference, observed) -> list[str]`. Rotation and
  display size are deliberately excluded: the cell rotates the device on
  purpose. The close is written *before* the probe is dispatched, so a refused
  re-probe stays visible as `closed: false` instead of being retried.
- **A twenty-third reason.** `device_session_identity_drifted` joins
  `FAILURE_SCOPES` as a shared reason, keeping the frozen
  `set(FAILURE_SCOPES) == set(SHARED_FAILURE_REASONS)` contract, and phase
  `close-post-cell-identity` maps to `device_session_unavailable` so host-level
  session loss on the re-probe keeps its existing classification.
- **The read budget grows to two probes.**
  `EXPECTED_DEVICE_READ_COUNTS["probe_session"]` is `2`: the pre-cell session
  probe and the post-cell identity close. The independent verifier recomputes
  this from the recorded shape, so an attempt that probes once — or three times
  — is rejected as `attempt_device_budget_violated`.
- **Aborts close the identity exactly once.**
  `_best_effort_close_post_cell_identity` runs on the abort path: it does nothing
  when the phase already closed the identity, and it does nothing when no
  session was ever established, because re-probing a refusal the abort already
  owns would be a retry. Otherwise it closes once and marks the component
  `partial: true`.
- **The unsettled poll keeps its evidence.** `_dispatch_orientation` now records
  the full `lifecycle_transition` component — poll budget, poll count, every
  ordered observation, before/after foreground state, dispatch vector — *before*
  the settled check, and only then fails `orientation_not_observed`. A rejected
  poll is never shortened, replayed, or compensated, and the abort never takes a
  second product observation.
- **One capture answers both evidence families.** The lifecycle proof reads the
  lifecycle slice out of the same recorded dump that bound the L1 window; the
  window and the slice are two windows of one `dump_all_buffers_epoch` capture
  (`verification/...` matrix `dump_all_buffers_epoch == 1` in every case).
- **An independent verifier check.** `_verify_post_cell_identity` recomputes the
  drift from the recorded fields, refuses a missing or non-`probe_session` close,
  a closed-but-contradicted reference, a non-zero probe return code, and a
  recorded `drifted_fields` that disagrees with the recomputation — all as
  `attempt_post_cell_identity_mismatch` — and a receipt/record whose
  `post_cell_identity` component is absent is `attempt_component_invalid`. It
  reports the `post-cell-identity` check next to the existing deterministic
  recomputations.
- **Closed fault vocabularies for the recording device.** `LAYOUT_FAULTS` (6),
  `LOG_DUMP_FAULTS` (9), `LIFECYCLE_FAULTS` (7), and `SESSION_DRIFT_FAULTS` (5)
  are the only names `RecordingDevicePolicy` admits; an unadmitted name raises
  `RuntimeAttemptError("recording_device_fault_invalid")`. Layout faults bind to
  frozen ordinals (`RECORDED_JOURNEY_LAYOUT_READS = 6`,
  `RECORDED_BOUNDARY_LAYOUT_READ = 7`, `RECORDED_POST_EVENT_LAYOUT_READ = 8`), so
  a drift in the mirror cannot silently move a fault onto the Journey's own
  reads.

## Acceptance evidence

| # | Criterion | Evidence |
|---:|---|---|
| 1 | Boundary Precondition requires one structurally valid input node with exact text 12+34; missing, duplicate, invalid, or different pre-event state is non-accountable before rotation | Matrix `boundary-input-missing`, `boundary-input-duplicated`, `boundary-input-geometry-invalid`, `boundary-text-drifted`, `boundary-text-omitted`, `boundary-layout-malformed`: all `boundary_layout_unreadable`, scope lane-local, phase `boundary-precondition`, mutation prefix stops at the terminal end marker with **no lifecycle-start marker and no `dispatch_orientation`**, window closed partial. `test_driver_enters_the_boundary_precondition_through_the_frozen_trajectory` pins the frozen tap trajectory that reaches it |
| 2 | Lifecycle event marked and dispatched exactly once with no retry, reverse rotation, relaunch, or compensating action | Matrix `rotation-dispatch-refused` (3 markers, no dispatch, no second attempt) and `rotation-not-observed` (one `dispatch_orientation`, 50 polls, then terminal); `_assert_admitted_mutation_vectors` proves each dispatched vector appears at most once per case; `test_post_observation_failures_fail_closed_at_the_canonical_phase` asserts `dispatch_orientation <= 1` on every case and `not in counts` for boundary cases; the accountable path pins `dispatch_orientation 1` in `test_frozen_device_budget_is_spent_exactly_once_in_order` |
| 3 | Lifecycle evidence proves the frozen ordered destruction, creation, and resume signature with the same task and process and no target restart | Matrix `lifecycle-events-reordered`, `lifecycle-event-duplicated`, `lifecycle-event-missing`, `lifecycle-relaunch-missing`, `lifecycle-task-changed`, `lifecycle-pid-changed` (all `lifecycle_transition_unproven`, phase `prove-lifecycle-transition`) and `lifecycle-target-restarted` (`target_process_restarted`). `test_landscape_event_and_lifecycle_transition_are_frozen` pins `signature_events` order, `signature.id`/`status`, `restart_evidence == []`, and `before.component == after.component` |
| 4 | Target Log Window contains one ordered attempt-bound marker pair and one complete attributable dump used by both L1 and lifecycle evaluation | `test_the_single_capture_serves_the_l1_window_and_the_lifecycle_slice`: `dump_all_buffers_epoch == 1`; `oracles.window_sha256 == window.window_sha256`; each of the four markers occurs exactly once in the capture; `_marker_indexes` equals `start_line`/`end_line`; the lifecycle `slice_lines` are derived from that same capture and lie strictly inside the window; `lifecycle-window.log` is byte-equal to `_window_slice(capture, *slice_lines)` and matches `slice_sha256` |
| 5 | Missing, reversed, duplicate, incomplete, capture-failed, or ambiguously attributable log evidence makes the attempt non-accountable | Matrix `log-dump-refused` (`target_log_window_capture_failed`, window refused, no capture file), `log-dump-empty`/`log-end-marker-missing`/`log-markers-reversed`/`log-markers-duplicated`/`log-window-truncated` (`target_log_window_marker_error`), `log-window-incomplete` (`target_log_window_capture_failed`), `log-lifecycle-marker-missing`/`-duplicated` (`lifecycle_transition_unproven`), `log-foreign-crash-unattributable` (`log_attribution_ambiguous`, scope **unknown**, phase `evaluate-oracles`) |
| 6 | Observation Poll retains every read-only probe and never repeats or compensates for the lifecycle side effect | `test_the_unsettled_poll_retains_every_probe_without_compensating`: `poll_count == LIFECYCLE_POLL_BUDGET == 50`, observations numbered 1..50 with every `fields.landscape is False`, `read_foreground_state == 51 == 1 + poll_budget`, `dispatch_orientation == 1`, no second layout read (`post_event_observation` absent), window closed partial, identity closed, verifier true. Matrix `rotation-not-observed` records the same shape |
| 7 | Valid exact post-event text yields L2 pass; changed or omitted-empty text yields L2 fail with state_loss; valid structural ambiguity yields accountable L2 inconclusive | `POST_EVENT_OBSERVATIONS` (7 cases) + `test_post_event_observation_yields_the_frozen_l2_result`: exact text `12+34` → `pass`/`preserved_state`; `wrong_text`, `omitted_text`, and `save_enabled=False` → `fail`/`state_loss` with `defect_class == "state_loss"` and exit 1; `missing_input`, `duplicate_input`, `invalid_geometry` → `inconclusive`/`post_event_input_{missing,duplicated,unusable}`. All seven stay `accountable_concluded`, and the verifier recomputes both the verdict and the L2 outcome |
| 8 | Capture, parse, checksum, identity, or lifecycle-proof failure cannot become an L1/L2 result; complete logs without crash/ANR remain L1 inconclusive | Every one of the 31 fail-closed matrix cases asserts `"oracles" not in outcome.components`, `verdict == inconclusive`, and `verified["recomputed"] is None`; the seven accountable observation cases keep `oracles.l1.outcome == inconclusive` while L2 carries the product verdict. `log-foreign-crash-unattributable` shows an attribution failure terminating at `evaluate-oracles` with no authoritative oracle |
| 9 | Post-cell identity and terminal artifacts are closed even when evidence fails, and no handled path retries or replaces the attempt | Every matrix case records a `post_cell_identity` component and `probe_session == 2`; `post-cell-probe-refused` records `closed: false` with `capture: unavailable_after_abort` instead of retrying. On the accountable path `_verify_post_cell_identity` recomputes the drift from the recorded fields (`test_verification_rejects_a_tampered_post_cell_identity` restamps the receipt identity and still rejects a false `closed`, a rewritten reference, a fabricated drift list, and a real injected drift); on the non-accountable path the component is bound by the receipt identity digest, which covers the whole document. `test_a_refused_session_identity_is_never_re_probed_on_the_abort_path` proves exactly one probe call on the abort path, `probe_session` absent from the counted operations (no compensation), `retries == 0`, exactly one receipt and one record, exit 2, `verified: true`. `test_terminal_finalization_closes_the_marker_window_exactly_once` and `test_a_failed_window_capture_never_dispatches_a_second_end_marker` pin the at-most-once end marker |
| 10 | Table-driven and recording-device tests cover every result/rejection class through the public lane seam, with a committed run record | `POST_OBSERVATION_FAILURES` (31 cases) and `POST_EVENT_OBSERVATIONS` (7 cases) drive `execute_runtime_attempt` + `verify_runtime_attempt` and assert reason, derived scope, terminal phase, ordered ledger, exact dispatched prefix, admissible mutation vectors, window/identity closure, one receipt/record, and `verified: true`. `test_frozen_phase_and_scope_tables_are_the_frozen_contract` proves the matrix mirrors the four fault vocabularies exactly (27 names). Focused suite +42 cases (145 → 187); full suite +42 (1494 → 1536). This document and `verification/` are the run record |

## Verification commands and results

Tool versions: CPython `3.12.13`, pytest `9.1.1`, Ruff `0.16.9`, mypy `2.3.1`,
uv `0.10.7`, Git `2.50.1 (Apple Git-155)`.

```text
.venv/bin/python -m pytest tests/bench/test_runtime_attempt.py \
  tests/bench/test_runtime_calibration.py tests/test_runtime_preparation.py \
  tests/test_runtime_sealed_apk.py \
  --junitxml=docs/runs/2026-09-29-issue-211-post-observation-fail-closed/verification/focused-pytest.xml
```

Result: **187 passed, 0 failed, 0 skipped** in 60.434 s
(`verification/focused-pytest.xml`); `tests/bench/test_runtime_attempt.py`
alone is 36 test functions / 94 cases (was 30 / 52 at `2a5d16b`).

```text
.venv/bin/python -m pytest \
  --junitxml=docs/runs/2026-09-29-issue-211-post-observation-fail-closed/verification/full-pytest.xml
```

Result: **1536 tests, 18 failed, 52 skipped** in 646.669 s
(`verification/full-pytest.xml`).

Baseline comparison — the same command in a clean `git worktree` at the
reviewed fixed point `2a5d16b` (`verification/baseline-pytest.xml`):

| Run | Tests | Failed | Skipped | Time |
|---|---:|---:|---:|---:|
| baseline (`2a5d16b`) | 1494 | 18 | 52 | 635.415 |
| with #211 | 1536 | 18 | 52 | 646.669 |

`diff verification/full-pytest-failures-baseline.txt
verification/full-pytest-failures-current.txt` is empty: the failure sets are
identical line for line, so **no existing runner behaviour regressed**. The
`+42` tests are the new cases in `tests/bench/test_runtime_attempt.py`.
The 18 failures are pre-existing and environment-bound: the frozen
issue-206 mapping-release fixtures pin another workstation's absolute
`candidate_root` (`/Users/peter/...`), so `test_runtime_family_preparation.py`
(17) and `test_m7_runtime_probe.py` (1) fail on any other machine at `2a5d16b`
too. They are unrelated to this change and are not repaired here.

```text
uvx ruff check src/aiverify/bench/runtime_attempt.py src/aiverify/runtime_attempt.py \
  tests/bench/test_runtime_attempt.py \
  docs/runs/2026-09-29-issue-211-post-observation-fail-closed/verification/
```

Result: `All checks passed!`

```text
MYPYPATH=src uvx mypy --python-executable .venv/bin/python \
  src/aiverify/bench/runtime_attempt.py
```

Result: one environment-only error, `Library stubs not installed for "yaml"`
(the repository has no `types-PyYAML` and no mypy configuration), identical to
the #210 baseline.

`python -m compileall` over the delivered source tree and the test module:
passed.

### Post-observation failure matrix, re-verified from the committed bytes

```text
PYTHONPATH=src .venv/bin/python \
  docs/runs/2026-09-29-issue-211-post-observation-fail-closed/verification/generate_evidence.py
```

Result: `wrote .../post-observation-matrix.json with 31 failures and 7
observations`. The script drives the public seam (`execute_runtime_attempt` +
`verify_runtime_attempt`) through 31 labelled failures and 7 accountable
observations on a pinned clock, asserts for each case the canonical reason, the
derived scope, the terminal phase, the ordered phase ledger, the exact
dispatched-mutation prefix and admissible vectors, one receipt/record with
exactly one phase error, the window closure state, and the post-cell identity
state. Two consecutive runs produce byte-identical JSON apart from the ephemeral
per-attempt UUID (and the digests derived from it), which the seam generates.

| Label | Reason | Scope | Terminal phase | Dispatched | Window | Identity |
|---|---|---|---:|---:|---|---|
| `boundary-input-missing` | `boundary_layout_unreadable` | lane_local | `boundary-precondition` | 13 | abort | closed |
| `boundary-input-duplicated` | `boundary_layout_unreadable` | lane_local | `boundary-precondition` | 13 | abort | closed |
| `boundary-input-geometry-invalid` | `boundary_layout_unreadable` | lane_local | `boundary-precondition` | 13 | abort | closed |
| `boundary-text-drifted` | `boundary_layout_unreadable` | lane_local | `boundary-precondition` | 13 | abort | closed |
| `boundary-text-omitted` | `boundary_layout_unreadable` | lane_local | `boundary-precondition` | 13 | abort | closed |
| `boundary-layout-malformed` | `boundary_layout_unreadable` | lane_local | `boundary-precondition` | 13 | abort | closed |
| `rotation-dispatch-refused` | `orientation_dispatch_failed` | lane_local | `lifecycle-rotation` | 14 | abort | closed |
| `rotation-not-observed` | `orientation_not_observed` | lane_local | `lifecycle-rotation` | 16 | abort | closed |
| `post-event-layout-malformed` | `post_event_layout_unreadable` | lane_local | `collect-post-event-observation` | 16 | abort | closed |
| `log-dump-refused` | `target_log_window_capture_failed` | shared | `close-target-log-window` | 16 | refused | closed |
| `log-dump-empty` | `target_log_window_marker_error` | shared | `close-target-log-window` | 16 | unproven | closed |
| `log-end-marker-missing` | `target_log_window_marker_error` | shared | `close-target-log-window` | 16 | unproven | closed |
| `log-markers-reversed` | `target_log_window_marker_error` | shared | `close-target-log-window` | 16 | unproven | closed |
| `log-markers-duplicated` | `target_log_window_marker_error` | shared | `close-target-log-window` | 16 | unproven | closed |
| `log-window-truncated` | `target_log_window_marker_error` | shared | `close-target-log-window` | 16 | unproven | closed |
| `log-window-incomplete` | `target_log_window_capture_failed` | shared | `close-target-log-window` | 16 | unproven | closed |
| `log-lifecycle-marker-missing` | `lifecycle_transition_unproven` | lane_local | `prove-lifecycle-transition` | 16 | phase | closed |
| `log-lifecycle-marker-duplicated` | `lifecycle_transition_unproven` | lane_local | `prove-lifecycle-transition` | 16 | phase | closed |
| `lifecycle-events-reordered` | `lifecycle_transition_unproven` | lane_local | `prove-lifecycle-transition` | 16 | phase | closed |
| `lifecycle-event-duplicated` | `lifecycle_transition_unproven` | lane_local | `prove-lifecycle-transition` | 16 | phase | closed |
| `lifecycle-event-missing` | `lifecycle_transition_unproven` | lane_local | `prove-lifecycle-transition` | 16 | phase | closed |
| `lifecycle-relaunch-missing` | `lifecycle_transition_unproven` | lane_local | `prove-lifecycle-transition` | 16 | phase | closed |
| `lifecycle-task-changed` | `lifecycle_transition_unproven` | lane_local | `prove-lifecycle-transition` | 16 | phase | closed |
| `lifecycle-pid-changed` | `lifecycle_transition_unproven` | lane_local | `prove-lifecycle-transition` | 16 | phase | closed |
| `lifecycle-target-restarted` | `target_process_restarted` | lane_local | `prove-lifecycle-transition` | 16 | phase | closed |
| `log-foreign-crash-unattributable` | `log_attribution_ambiguous` | unknown | `evaluate-oracles` | 16 | phase | closed |
| `post-cell-probe-refused` | `device_session_unavailable` | shared | `close-post-cell-identity` | 16 | phase | refused |
| `post-cell-serial-drifted` | `device_session_identity_drifted` | shared | `close-post-cell-identity` | 16 | phase | drifted |
| `post-cell-field-missing` | `device_session_identity_drifted` | shared | `close-post-cell-identity` | 16 | phase | drifted |
| `post-cell-setting-missing` | `device_session_identity_drifted` | shared | `close-post-cell-identity` | 16 | phase | drifted |
| `post-cell-setting-drifted` | `device_session_identity_drifted` | shared | `close-post-cell-identity` | 16 | phase | drifted |

"Dispatched" counts the frozen device mutations in the admitted prefix: 13 for
the six boundary cases (the terminal end marker is the last one, and no
lifecycle-start marker or rotation follows), 14 for the refused rotation, 16 —
the complete prefix — for everything at or after the post-event observation.
`Window` is the recorded `target_log_window` state: `abort` (closed, `partial`,
capture kept), `refused` (not closed, `capture: unavailable_after_abort`, no
file — the capture itself was refused), `unproven` (not closed, no capture
key — the dump could not be parsed into a window), or `phase` (closed normally
by the phase that ran). `Identity` is the recorded `post_cell_identity` state:
`closed`, `refused` (closed `false` after exactly one refused probe), or
`drifted` with the recomputed field list. No case records an `oracles`
component, no case reports a phase ledger that is not a strict frozen prefix,
and every case is accepted by the independent verifier.

### Accountable L2 result matrix

| Label | L2 outcome | L2 detail | L1 verdict | Exit | Terminal state |
|---|---|---|---|---:|---|
| `post-event-text-exact` | pass | `preserved_state` | inconclusive | 0 | accountable_concluded |
| `post-event-text-drifted` | fail | `state_loss` | fail | 1 | accountable_concluded |
| `post-event-text-omitted` | fail | `state_loss` | fail | 1 | accountable_concluded |
| `post-event-save-disabled` | fail | `state_loss` | fail | 1 | accountable_concluded |
| `post-event-input-missing` | inconclusive | `post_event_input_missing` | inconclusive | 0 | accountable_concluded |
| `post-event-input-duplicated` | inconclusive | `post_event_input_duplicated` | inconclusive | 0 | accountable_concluded |
| `post-event-input-unusable` | inconclusive | `post_event_input_unusable` | inconclusive | 0 | accountable_concluded |

All seven cases record every required accountable component including
`post_cell_identity`, dispatch `probe_session` exactly twice, and are re-verified
by `verify_runtime_attempt` with the recomputed verdict and L2 outcome.

## Artifact inventory

338 files, 5.2 MB under this run record: this document, its checksum, and 336
evidence artifacts. The attempt roots are larger than in #210 because
post-boundary failures genuinely run the Journey, so each case keeps the
`artifacts/journey/*` observation dumps its receipt binds by digest.

- `verification/post-observation-matrix.json` — the 31-failure + 7-observation
  matrix with the frozen phase table, the 23-reason scope table, the four fault
  vocabularies, the frozen layout ordinals, the read budget, and, per case, the
  expected and recorded failure, phase ledger, components, dispatched
  mutations/vectors, markers, operation counts, window/identity closure, record
  summary, verification summary, and receipt digest.
- `verification/attempts/<label>/attempt-receipt.json` (38) and
  `execution-record.json` (38) — the raw sealed bytes of every case.
- `verification/attempts/<label>/artifacts/target-log-window.log` (31) — the
  single marker-bounded capture for every case that could be captured; absent
  for the seven cases whose dump was refused or could not be parsed into a
  window (`log-dump-refused` plus the six `unproven` cases), where the recorded
  component says so instead of pointing at a file that does not exist.
- `verification/attempts/<label>/artifacts/lifecycle-window.log` (8) — the
  lifecycle slice cut from that same capture: the seven accountable observation
  cases plus `log-foreign-crash-unattributable`. The other fail-closed cases
  never reached a readable lifecycle slice, so no slice artifact is claimed.
- `verification/attempts/<label>/artifacts/journey/*.json` (38 × 3),
  `boundary-layout.json` (32), `post-event-layout.json` (29) — the recorded
  journey, boundary, and post-event surfaces the receipts bind.
- `verification/handoffs/<label>/sealed-runtime.apk` (38) — the handoff bytes the
  recorded deployment vector points at, kept in-repo so the vectors stay
  re-verifiable.
- `verification/generate_evidence.py` (850 lines) — the self-checking matrix
  driver.
- `verification/focused-pytest.xml`, `full-pytest.xml`, `baseline-pytest.xml`,
  `full-pytest-failures-{baseline,current}.txt` — the regression reports.
- `verification/extract_failures.py` — the failure-set extractor used for the
  baseline diff.
- `verification/checksums.sha256` — SHA-256 for `README.md` and every artifact
  under `verification/`; the delivered source files are checksummed in the table
  above.

## Known gaps

1. **No live device exercise.** As in #209 and #210, `AdbRuntimeDevice` is
   unit-tested through a stub command runner only; no emulator or physical
   device was available, and every matrix byte above is recorded simulation text.
   Whether a real device ever rotates without settling, refuses a mid-cell
   `getprop`, or reports a process death the way the recording device does remains
   unproven.
2. **Recording-device determinism.** The matrix fails the device through explicit
   policy knobs (`boundary_layout_fault`, `post_event_layout_fault`,
   `log_dump_fault`, `lifecycle_fault`, `session_drift_fault`, `save_enabled`,
   `fail_operations`, plus `_CountingSessionDevice`), so it proves the seam's own
   contract, not a device's behaviour.
3. **Session identity comparison is a fixed field set.** `session_identity_drift`
   compares 14 required fields, `serial`, and 10 frozen settings. A device whose
   identity is observable only through an unlisted property is not covered, and
   the settings list is a frozen snapshot rather than a discovered set.
4. **The window cannot be closed when the dump is refused.** `log-dump-refused`
   records `closed: false` with `capture: unavailable_after_abort` and no capture
   file: the attempt reports the truth rather than fabricating a closure. The
   verifier accepts that shape, so the only evidence that the window was owed and
   lost is the abort receipt and the recorded `capture_error`.
5. **The post-cell identity recomputation runs on the accountable path only.**
   `_verify_post_cell_identity` is reached only when the terminal state is
   `accountable_concluded`; a non-accountable receipt keeps its
   `post_cell_identity` component under the receipt identity digest, which
   detects any edit but does not recompute the drift. A non-accountable receipt
   that claimed `closed: true` over a drifted identity would therefore have to be
   caught by re-running the attempt, not by the verifier.
6. **Layout-read budget vs. bounded wait polling.** Inherited from #209/#210: the
   frozen read contract charges `len(actions) + 2 = 8` layout reads while the
   driver's first `wait` owns surface readiness through a bounded poll. The
   recording device's surface is ready on the first observation, so this issue
   cannot exhibit the difference; the decision still belongs to the
   family-orchestration issues.
7. **Orphan receipt on record-finalisation failure.** Inherited from #209: a crash
   between receipt sealing and record finalization leaves a receipt that binds no
   terminal record; the verifier fails closed on it
   (`attempt_record_binding_mismatch`), but no durable repair path exists.
8. **Ephemeral attempt identity.** `attempt_id` is a fresh UUID per execution, so
   the committed matrix is not byte-reproducible across runs; it is reproducible
   modulo that identity (verified by two consecutive runs). Any future
   cross-machine comparison must normalise it.
9. **Pre-existing environment-bound failures.** The 18 failures described above
   are inherited from `2a5d16b` and are not repaired in this issue.

## Follow-ups

- The family-orchestration work still owes the consumer of `failure_scope`
  (`#210` froze the table for it) and now also the consumer of the post-cell
  identity close: a shared `device_session_identity_drifted` abort is the signal
  that the device, not the lane, is suspect.

## Checksums

`verification/checksums.sha256` lists the SHA-256 of `README.md` and of every
artifact under `verification/` (337 files, 5.2 MB in this directory tree). Run
`shasum -a 256 -c verification/checksums.sha256` from this directory to
re-verify.
