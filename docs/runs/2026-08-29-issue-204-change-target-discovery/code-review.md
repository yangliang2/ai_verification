# Issue #204 code review

Review fixed point: `1a72fd4fe8e3101f86dbb20698239f9d703e2073`.
Reviewed implementation commit: `8d4d6ff2897180826ff65c9d053f38840e7451e3`.
The review used separate Standards and Spec sub-agents over
`git diff 1a72fd4...HEAD`; the follow-up hardening below was then reviewed by
the local verification suite before the final commit.

## Standards

The Standards reviewer found no ADR-0003 or ADR-0005 conflict and no material
documented coding-standard breach. It flagged one conditional evidence issue:
the run record declared completion before the required GitHub issue comment
existed. The final handoff adds that comment with the exact commands, results,
artifact inventory, checksums, and gaps.

The reviewer also noted judgement-call smells: duplicated patch-template
construction across the candidate verifier and discovery module, and
compatibility aliases that may be speculative. The aliases are intentionally
kept as small entry-point compatibility names for the dependent ProjectTarget
work; the duplicate template is checked against the candidate patch bytes at
admission and does not alter the source of truth.

## Spec

The Spec reviewer identified these issues in the initial implementation:

- `ChangeTarget.diff_ref` named files that did not exist. This is fixed by the
  two checked-in auditor patch artifacts under
  `bench/runtime-calibration/opencalc-input-save-enabled-v1-diffs/`; admission
  verifies their UTF-8 bytes and SHA-256 against the candidate variants, and a
  regression test passes them through `verify_change_target_diff`.
- Projection IDs accepted arbitrary nonempty contract strings. This is fixed
  by requiring all six canonical neutral IDs and testing altered IDs.
- The explicit source-tree mismatch rejection branch was not covered. A test
  now supplies a clean checkout with a mismatched tree identity.
- The source-dependent tests are guarded by the documented external checkout
  path. The final local run had that checkout and executed all 19 new tests;
  an environment without it skips those tests rather than fabricating source
  evidence.

No scope-creep finding affected runtime behavior. The final full suite and
Ruff check passed after these changes.
