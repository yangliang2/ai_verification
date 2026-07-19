# Issue #71 code review record

Date: 2026-07-19

The code-review skill ran two independent read-only reviews: one against the
issue specification and one against repository standards.

## Initial specification findings

1. Backup receipts validated app-data clear and cleanup transiently but did not
   retain those observations.
2. Process-death receipts proved PID replacement but did not explicitly retain
   the HOME/background and post-relaunch foreground states.

Resolution:

- system-event-2 now retains clear_data_status, clear_data_output,
  cleanup_status, cleanup_transport, and cleanup_backup_enabled;
- system-event-1 now retains background/relaunch status, resumed package,
  target foreground/background booleans, process absence, and before/after
  PIDs;
- the dedicated oracle requires these fields and fails closed when they are
  absent or inconsistent;
- attempt-2 was rerun on the emulator after these changes.

## Initial standards findings

1. GitHub issue/parent evidence and a committed root inventory were still
   pending.
2. ExecutionRecord system-event references were absolute temporary paths.
3. Interrupted Journey paths could discard already-created event receipts and
   duplicated interruption construction.
4. Device-scoped screenshot behavior contradicted ADR 0001.

Resolution:

- GitHub publication remains an explicit finalization step and the run record
  is not declared complete before it;
- all run-local ExecutionRecord references and top-level system-event receipt
  references are relative;
- interruption construction is centralized and preserves/serializes retained
  event evidence;
- ADR 0001 now explicitly describes the implemented fallback for Android CLI
  1.0.15498356: an explicit serial always uses recorded adb shell-screencap,
  pull, and cleanup commands; no serial uses Android CLI capture;
- regression tests cover these corrections.

## Verification of corrections

TDD records:

- tdd/38-review-evidence-gaps-red.txt: 6 expected failures before fixes;
- tdd/39-review-evidence-gaps-green.txt: the same 6 tests passed;
- tdd/40-post-review-full-suite-green.txt: 545 tests passed, compileall passed,
  and git diff --check passed.

## Final re-review

Specification re-review initially observed that the new attempt-2 independent
conclusion had not yet been archived. After conclusion.json, invocation.md,
prompt.md, and validation.txt were added, the same reviewer returned:

> No spec blocker remains.

The reviewer cited the two exact attempt IDs, one locally_supported and
accountable conclusion, successful schema validation, and 13 passed evidence
checks.

Standards re-review found one further documentation mismatch: ADR 0001 said the
adb fallback was multi-device-only and used exec-out, while the code and
attempt-2 manifests showed explicit-serial shell-screencap/pull/cleanup. After
the ADR and run README were corrected, the same reviewer returned:

> No non-publication Standards blocker remains.

The only remaining steps at that point were the deliberately sequenced root
checksum, durable commit/push, issue/parent comments, label update, and closure.
