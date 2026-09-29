# Issue #209 code review

Review fixed point: `f87ae04`

Reviewed surfaces: `src/aiverify/bench/runtime_attempt.py`,
`src/aiverify/runtime_attempt.py`, `tests/bench/test_runtime_attempt.py`.
Sources were the issue body and its ten acceptance criteria, `AGENTS.md`,
`CONTEXT.md`, `docs/agents/domain.md`, and the frozen
`docs/opencalc-runtime-calibration-v1.md` (§10 attempt setup and phase order,
canonical launch, L1/L2 oracles).

The review was run as a dedicated review pass over the uncommitted new files.
Findings are listed with their disposition; everything marked fixed is covered
by a regression test or by the committed lane-01 evidence.

## Standards

### Findings and dispositions

1. **[blocker, fixed] `AdbRuntimeDevice` counted command vectors, not admitted
   operations.** `_run` opened a ledger entry per command vector, so
   `probe_session` (22 vectors), `read_installed_apk` (2 + pull),
   `read_rotation_state` (3), and `read_foreground_state` (3) were charged 22/3/3/3
   against a frozen budget that admits exactly one of each. Every real-device
   attempt would have failed the exactly-once budget. Fixed: each admitted
   operation now opens its own ledger entry once (`patch_adb_budget`, 17 edits);
   the recording device and the production device now use the same accounting
   unit. Regression: `test_adb_device_counts_admitted_operations_not_command_vectors`.
2. **[blocker, recorded gap] Read budget vs. bounded wait polling.** The frozen
   read contract charges `len(actions) + 2` layout reads, but the deterministic
   driver's first `wait` owns surface readiness via a bounded observation poll
   that reads a layout per observation (frozen spec §10). The recording device
   settles on the first observation, so the difference is invisible here; a
   real device with a slow surface would exceed the budget. Not resolved: the
   read-budget semantics must be decided deliberately, and that decision belongs
   with the failure-matrix/family issues (#210–#218), not with this recording-device
   tracer. Recorded in `README.md` "Known gaps" 1.
3. **[major, fixed] Artifact inventory admitted duplicate and unknown kinds.**
   A last-write-wins index let a second entry shadow a frozen kind (for example
   re-declaring `post_event_layout` over `boundary_layout`) and wash a
   `state_loss` failure into a `pass`. Fixed: `_FROZEN_ARTIFACT_KINDS` is
   enforced unconditionally; duplicates and unknown kinds are rejected, and the
   frozen completeness requirement applies to accountable attempts only so
   non-accountable partial inventories stay admissible. Regression:
   `test_verification_rejects_a_duplicated_or_unknown_artifact_kind` plus the
   five non-accountable parameterisations.
4. **[major, fixed] The verifier trusted recorded values.** `evidence_class` was
   only checked for being a non-empty string; the L1 attribution counts/events,
   the L2 input node count/text, and the boundary precondition text were never
   recomputed. Fixed: `_verify_evidence_class` recomputes the class from the
   bound device kind and the preparation's test-substitute flag; the L1
   attributed event count and event list, the L2 input node count and text, and
   the boundary text are recomputed and compared against the frozen
   `BOUNDARY_PRECONDITION_TEXT`. Regression:
   `test_verification_rejects_a_relabelled_evidence_class` and the hardened
   budget/log-window tamper test.
5. **[minor, fixed] Verifier exception-code consistency.** `int(counts.get(...))`
   and `list(observed_order or [])` could raise bare `ValueError`/`TypeError`
   instead of a canonical violation. Fixed: counts must be `int` (not `bool`),
   `observed_order` must be a list, and the lifecycle event line must be an
   `int`; anything else fails closed with a stable code.
6. **[minor, recorded gap] Orphan receipt.** The receipt is written before the
   record is finalised, so a crash in between leaves a receipt with no terminal
   record. Verification fails closed on that residue, but no repair path
   exists. Recorded in `README.md` "Known gaps" 2.
7. **[minor, addressed] Acceptance criterion 10 evidence gap.** Addressed by
   this run record: the committed `verification/lane-01-attempt/` bytes are a
   real bounded simulation, and `verify_runtime_attempt` re-verifies them from
   the committed copy.
8. **[nit, fixed] Tautological read-budget assertion.** The test re-implemented
   `expected_device_read_counts` from its own constant and compared it with
   itself. Now the frozen read contract is asserted against explicit literal
   values.
9. **[nit, fixed] Window digest compared against the wrong text.** The test
   hashed the whole capture file while `window_sha256` covers the
   marker-bounded slice. Now the test recomputes the slice with
   `_window_slice`.

### Checks supporting this review

- Ruff `0.16.9`: `All checks passed!` for all three delivered files.
- mypy `2.3.1` for the two source files: only the repository-wide missing
  `yaml` stubs (no mypy configuration exists in the repository).
- `compileall`: passed for all three files.
- Focused suite: 119 passed, 0 failed (`verification/focused-pytest.xml`).
- Full suite vs. baseline at `f87ae04`: identical 18-failure sets, +26 new
  passing tests (`verification/full-pytest.xml`, `verification/baseline-pytest.xml`).

## Specification

### Criterion disposition

| # | Criterion | Disposition and evidence |
|---:|---|---|
| 1 | ExecutionRecord before the first external side effect, finalised once | Satisfied by `_establish_record` and the single `_finalize_record` call on both terminal paths; regression `test_execution_record_predates_the_first_device_mutation`. |
| 2 | Runtime Device Session binds device/boot/Android CLI/emulator/adb/system image/display/settings | Satisfied by `_session_fields`, `SESSION_REQUIRED_FIELDS`, `SESSION_IDENTITY_SETTINGS`, and the AVD/system-image digest binding; regression `test_device_session_receipt_binds_the_selected_device`; committed receipt carries all 18 session fields. |
| 3 | Sealed Runtime APK deployment with installed-byte equality | Satisfied by `_sealed_apk_binding` and `read_installed_apk`; regressions `test_sealed_apk_deployment_binds_installed_bytes_to_the_handoff`, `test_sealed_apk_drift_is_rejected_before_any_device_side_effect`. |
| 4 | Attempt setup: one clear, proven absence, two admitted writes, verified portrait | Satisfied by `ATTEMPT_SETUP_OPERATIONS` and the attempt-setup phase; regression `test_attempt_setup_clears_package_data_and_forces_portrait_once`; `test_attempt_setup_plan_rejects_a_drifted_frozen_operation_set` binds the operation set. |
| 5 | Marker-bounded window opens before the canonical launch; one exact foreground component | Satisfied by the open/close window phases and the launch foreground check; regression `test_marker_bounded_window_starts_before_the_canonical_launch`. |
| 6 | Deterministic driver `12+34` and exact boundary precondition | Satisfied by the frozen driver plan and the boundary read; regression `test_driver_enters_the_boundary_precondition_through_the_frozen_trajectory`. |
| 7 | One orientation dispatch with bounded post-event observations and a frozen lifecycle receipt | Satisfied by the rotation phase, poll budget/interval, and the provisional signature; regression `test_landscape_event_and_lifecycle_transition_are_frozen`. |
| 8 | L1 inconclusive without attributable crash/ANR; L2 pass for the exact `12+34` | Satisfied by both oracles and their recomputation in the verifier; regressions `test_recording_lane_concludes_one_accountable_preserved_state`, plus the state-loss and injected-crash lanes. |
| 9 | `accountable_concluded` with complete references and zero retries | Satisfied by `REQUIRED_ACCOUNTABLE_COMPONENTS`, `retries: 0`, and the mutation-order/read budget checks; regression `test_frozen_device_budget_is_spent_exactly_once_in_order`; committed receipt carries all 12 components and 7 artifacts. |
| 10 | Public-seam recording-device integration test; runner behaviour stays green; run record records the bounded result | Satisfied by `tests/bench/test_runtime_attempt.py` (22 functions / 26 cases), the baseline-equality comparison, and this run record's `verification/lane-01-attempt/`. |

### Residual risk

The residual risk is concentrated in the two recorded gaps: the layout-read
budget tension affects only a future real-device attempt (this issue claims no
device evidence), and the orphan receipt is a fail-closed residue, not a
false-positive evidence path. Both are flagged for the downstream issues that
own the real-device and failure-matrix work.
