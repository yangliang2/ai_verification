# Issue #205 — OpenCalc ProjectTarget discovery admission

Date: 2026-08-29 (America/New_York)

Status: **durable repository evidence when committed with the implementation**.
This record covers the model-free ProjectTarget discovery seam requested by
[issue #205](https://github.com/yangliang2/ai_verification/issues/205), on
branch `issue-197-runtime-source-preparation`, from fixed point `343cf27`.

## Outcome and claim boundary

The OpenCalc control/defect matched pair is admitted as two complete,
immutable `ProjectTarget` campaigns. Each target is materialized in a fresh
clone from the pinned pristine baseline, receives exactly one anchored source
injection, and gets a deterministic synthetic commit with a receipt binding
the parent, trees, source-tree digests, patch digest, result diff digest,
author/committer metadata, timestamp, message, and receipt identity.

The ProjectTarget package retains source meaning for auditors while carrying
no `BehaviorDelta`, `ContractDrift`, or invented diff. Its driver-visible
projection has the same generic shape as its paired control/defect projection,
with only opaque checksum-bound identities varying. The projection contains
`diff: null`, no catalog/variant/target meaning, no source-rich path, and
`model_calls: false`.

This run proves source materialization, bounded Context Acquisition, campaign
admission, projection leakage review, deterministic identity, and the
side-effect-free boundary only. It does not build an APK, access Android CLI,
adb, a device/emulator, a runtime oracle, a network/provider, or a model, and
it makes no product-quality, defect-detection, or runtime claim.

## Acceptance evidence

| Issue criterion | Evidence |
| --- | --- |
| Separate deterministic synthetic commits | `SyntheticProjectCommit` in `src/aiverify/bench/opencalc_discovery.py` creates one clean clone and one deterministic `commit-tree` result per variant. `verification/project-admission.json` records both complete receipts and Git parent/tree/diff checks. |
| Pinned pristine baseline and no runtime-build reuse | Admission validates the external checkout before every materialization, clones with `--no-local --no-hardlinks`, never invokes a build/device/model command, marks discovery materialization as `runtime_build_worktree: false`, and revalidates both clean materializations before projection. |
| Complete ProjectTarget provenance, scope, budget, and no diff | `SourceRichDiscoveryPackage` binds each `ProjectTarget` to its synthetic commit/worktree, nine required paths, budget nine, source injection bytes/digest, and `behavior_delta=None`/`contract_drift=None`. |
| Shared discovery inputs and neutral campaign semantics | Project campaigns use the same nine-path scope, six adapters, quality contract, risk prior, attack operator, neutral hypothesis/failure-chain/attack-plan semantics, and exploration policy as ChangeTarget campaigns. The focused symmetry test compares these fields without merging target/source identities. |
| Auditor package preserves source meaning | Packages retain catalog identity, target kind, baseline and synthetic provenance, source injection reference/bytes/digest, synthetic commit receipt, and round-trip serialization. |
| Blind projection and Run Spec boundary | The four checked-in lane commitments are rebound through candidate verification. Project projections expose only opaque lane/commitment identities, bounded context, neutral IDs, `diff: null`, and `model_calls: false`; leakage auditing passes. |
| Symmetric control/defect projection shape | Project lanes `ocrc-v1-lane-03` and `ocrc-v1-lane-04` have equal serialization key shapes; their opaque identities and projection IDs remain distinct and receipt-bound. |
| Fail-closed drift behavior | Tests cover dirty pristine source, non-empty materialization roots, invented ProjectTarget diffs, forged exploration policy, candidate identity drift, and post-context synthetic-worktree drift. Candidate/source/materialization/projection disclosure checks occur before any build/device/model operation. |
| Semantic symmetry without identity merging | `test_project_packages_preserve_source_meaning_and_share_neutral_contracts` compares the full neutral hypothesis semantics and shared acquisition/contract inputs while asserting distinct synthetic source commits and target kind. |
| Durable validation record | This README, `verification.json`, `project-admission.json`, both JUnit reports, `code-review.md`, and `checksums.sha256` are committed with the implementation. |

## Implementation surface

- `src/aiverify/bench/opencalc_discovery.py`: ProjectTarget admission API,
  receipt model, deterministic Git materialization, anchored injection,
  context/campaign binding, strict package serialization, materialization
  revalidation, blind projections, leakage audit, and compatibility aliases.
- `tests/bench/test_opencalc_discovery.py`: matched-pair admission, deterministic
  receipt and clean-worktree checks, semantic ChangeTarget/ProjectTarget
  symmetry, source/build/device/model side-effect boundary, materialization and
  serialization drift rejection.
- `verification/project-admission.json`: compact final manual admission receipt
  with source, candidate, package, receipt, projection, leakage, and
  subprocess-boundary identities.

## Exact verification commands and results

All commands ran from `/Users/peter/projects/ai_verfication`.

```text
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest tests/bench/test_opencalc_discovery.py --junitxml=docs/runs/2026-08-29-issue-205-project-target-discovery/verification/focused-pytest.xml
```

Result: 27 passed, 0 failed, 0 errors, 0 skipped; pytest time 25.47s; shell
wall time 25.55s. The JUnit report records 27 tests in 25.469s.

```text
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest --junitxml=docs/runs/2026-08-29-issue-205-project-target-discovery/verification/full-pytest.xml
```

Result: 1,388 passed, 0 failed, 0 errors, 1 skipped out of 1,389 tests;
pytest time 181.97s; shell wall time 182.08s. The one skip is the pre-existing
`tests.bench.test_m9_recovery_formal.test_frozen_target_specific_mismatch_is_side_effect_free`
external-fixture gate, which requires explicit admission.

```text
uv run --with ruff ruff check src/aiverify/bench/opencalc_discovery.py tests/bench/test_opencalc_discovery.py
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m compileall -q src tests
```

All three checks passed. Tool versions: CPython 3.14.4, pytest 9.1.1, Ruff
0.16.5, uv 0.11.7, and Git 2.50.1 (Apple Git-155).

The candidate source-of-truth check also accepted all 28 candidate artifacts
with artifact inventory digest
`393a19ce2ca16b60510ed21f80ba637df1bf3236da3b565fbc7a7856ad1eab14`.

The final manual admission receipt recorded 123 Git-only subprocesses, clean
control/defect materializations, unchanged pristine source bytes/status, and
zero build/device/model calls. The temporary materialization root was outside
the repository; its deterministic identities and clean-worktree checks are
captured in `verification/project-admission.json`.

## Review

The two-axis review used fixed point `343cf27`; findings and remediation are
recorded in [`code-review.md`](code-review.md). The standards review identified
candidate-identity omission from normalized result identity, exception-alias
compatibility, clone-cleanup ownership, parser error normalization, and stale
docstrings. The spec review identified incomplete semantic-symmetry assertions,
missing post-context materialization revalidation, and permissive serialized
policy drift. All were corrected and covered by the final focused/full runs.

## Artifact inventory

- `verification/project-admission.json` — final manual ProjectTarget admission
  receipt and deterministic identity inventory.
- `verification/verification.json` — machine-readable commands, results,
  versions, claim boundary, source/candidate identities, and known gaps.
- `verification/focused-pytest.xml` — focused JUnit report, 27 tests.
- `verification/full-pytest.xml` — repository-wide JUnit report, 1,389 tests / 1
  skip.
- `code-review.md` — standards/spec review and disposition.
- `checksums.sha256` — checksums for every committed run-record artifact except the
  manifest itself.

No screenshots, layout dumps, Android artifacts, device/emulator logs, runtime
JSON, model traces, or oracle outcomes were produced.

## Known gaps

- Temporary synthetic source clones are not committed because they are
  materialized run outputs; commit/tree/diff/receipt identities and clean-state
  checks are committed in the admission receipt.
- This is a discovery-admission seam. Runtime build preparation, device
  execution, oracle evaluation, and any model role remain intentionally out of
  scope.
- The external pristine checkout is an environment prerequisite; the focused
  source-dependent tests skip when `/Users/peter/hosts/opencalc-calibration` is
  unavailable.
