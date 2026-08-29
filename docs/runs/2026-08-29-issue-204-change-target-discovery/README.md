# Issue #204 — OpenCalc ChangeTarget discovery admission

Status: passed, local evidence committed with the implementation.

This run admits the two pinned OpenCalc ChangeTarget campaigns from the
candidate source of truth and the pristine external checkout. It covers issue
#204 only. It intentionally does not apply either patch, build an Android
artifact, access a device or emulator, invoke a model, or execute a runtime
oracle; those are later calibration-family stages.

## Inputs and identities

- Candidate: `bench/runtime-calibration/opencalc-input-save-enabled-v1`
- Pristine source checkout: `/Users/peter/hosts/opencalc-calibration`
- Origin: `https://github.com/clementwzk/OpenCalc.git`
- Commit: `0584d61189e916a62a3b402223b35e1d7a3093db`
- Git tree: `8793c063c6a990ff3448fece38e62bc103952610`
- Declared archive SHA-256: `58d686b47f4a97f8b1127ab3de98bdf34a1c9310a221e5d5a7b4b5adcde54f3c`
- Anchored source file SHA-256: `409e08157ce741bf77f7f00817a28eabee11cd1f6a5355bff7d1dd5a977eaac7`
- Anchor context occurrence: exactly `1`
- Candidate identity: `1e247a243e2d9fcfc9704a641c5f1174b1f4cbceee7f2af28ad494d32c68bfd5`
- Candidate artifact inventory: `393a19ce2ca16b60510ed21f80ba637df1bf3236da3b565fbc7a7856ad1eab14`
- Matched-pair identity: `2a1f1cebbe29202c73524e77bad9258da99ecfb58e639d3fa7e3f01b8fa31848`
- Admission result identity: `1109552d6f23c3b34161784159599c50702d42e1f4fa36cfd8944f1a44e04dba`

The source checkout was clean before and after admission. The only source
change in this implementation is a checked-in identity correction: the
previous target-file digest was 63 characters, so it was replaced with the
actual 64-character SHA-256 and the dependent candidate/schema identities were
regenerated. The upstream commit, tree, path, and bytes did not change.

## Acceptance evidence

- One shared Upstream Source Anchor binds origin, commit, repository-relative
  path, complete target-file digest, exact context bytes/digest, insertion
  point, and required occurrence count.
- The `control` and `defect` entries share the baseline, anchor, taxonomy,
  operator, target, insertion point, and context. Their only declared source
  difference is `binding.input.isSaveEnabled = true` versus `false`.
- Anchor drift, ambiguity, missing context, source identity drift, pair
  taxonomy/operator drift, extra source hunk, required-context absence or
  unreadability, and budget exhaustion are covered by rejection tests.
- Both campaigns read the pristine `ProjectTarget` context with budget `9`,
  inspect all nine required paths, retain five sourced unknown facts, and
  finish `plan-admitted`. The real `BehaviorDelta` remains in each
  auditor-only package.
- Both projections share the neutral contract/prior/operator/hypothesis/plan
  and exploration-policy IDs. They expose only opaque lane identity,
  commitments, bounded context, neutral IDs, `diff: null`, and
  `model_calls: false`.
- Leakage auditing passed for both driver-visible serializations. Hidden
  variant/source meaning, expected symptom, and oracle material are rejected
  without mutating the auditor package.
- Build calls: `0`; device calls: `0`; model calls: `0`.
- The auditor-only patch references are real checked-in files under
  `bench/runtime-calibration/opencalc-input-save-enabled-v1-diffs/` and are
  byte-bound to the two candidate patch digests.

Detailed admission fields and projection receipts are in
[`verification/discovery-admission.json`](verification/discovery-admission.json).

## Verification commands and results

Tool versions: Python `3.11.15`, pytest `9.1.1`, Ruff `0.16.5`, uv `0.11.7`, Git `2.50.1`.

```text
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/pytest -q tests/bench/test_opencalc_discovery.py tests/bench/test_runtime_calibration.py tests/discovery tests/injection --junitxml=docs/runs/2026-08-29-issue-204-change-target-discovery/verification/focused-pytest.xml
217 passed; 0 failed; 0 errors; 0 skipped; pytest time 87.130s; wall time 88.32s (user 40.36s, sys 40.72s).
```

```text
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/pytest -q --junitxml=docs/runs/2026-08-29-issue-204-change-target-discovery/verification/full-pytest.xml
1380 passed, 1 skipped, 0 failed, 0 errors; pytest time 163.479s; wall time 166.45s (user 80.67s, sys 71.74s).
```

The one full-suite skip is the pre-existing repository-external fixture test
`tests.bench.test_m9_recovery_formal.test_frozen_target_specific_mismatch_is_side_effect_free`,
which requires explicit admission.

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m aiverify.bench.runtime_calibration verify-candidate --candidate-root bench/runtime-calibration/opencalc-input-save-enabled-v1 --output-root docs/runs/2026-08-29-issue-204-change-target-discovery/verification/candidate-stage
status: accepted; artifact_count: 28; artifact_inventory_sha256: 393a19ce2ca16b60510ed21f80ba637df1bf3236da3b565fbc7a7856ad1eab14
```

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m compileall -q src tests
git diff --check
both commands passed with no output.
```

```text
uv run --with ruff ruff check src/aiverify/bench/opencalc_discovery.py tests/bench/test_opencalc_discovery.py
All checks passed with Ruff 0.16.5.
```

The discovery test module has 19 tests, the prerequisite runtime-calibration
module has 21 tests, and the focused command also covers the existing
discovery and injection suites. No Gradle, Android CLI, adb, device, emulator,
or model command was run.

## Evidence inventory

- `verification/discovery-admission.json` — compact admission, matched-pair,
  package, projection, leakage, and side-effect receipt.
- `verification/verification.json` — machine-readable command/result summary.
- `verification/focused-pytest.xml` — focused JUnit report.
- `verification/full-pytest.xml` — repository-wide JUnit report.
- `verification/candidate-stage/stage-start.json` — candidate verification
  start receipt.
- `verification/candidate-stage/stage-terminal.json` — accepted candidate
  verification receipt.
- `code-review.md` — two-axis Standards/Spec review and follow-up disposition.
- `SHA256SUMS` — checksums for this run's committed evidence artifacts.

The atomic four-lane runtime mapping release is intentionally not produced by
#204; ProjectTarget admission and family mapping belong to the dependent
follow-up work. No manual or real-device verification was performed or
claimed. When the documented external checkout is absent, the new
source-dependent test module skips its 19 tests; this local run had the pinned
checkout available and executed them.
