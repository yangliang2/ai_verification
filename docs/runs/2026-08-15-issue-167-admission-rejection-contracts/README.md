# Issue #167 — production-seam admission rejection contracts

Status: the hermetic contract suite and its measured evidence are complete on
`issue-167-production-seam-admission-contracts`. This record becomes durable
with the commits containing this directory; the evidence-identity binding is
completed in the final follow-up commit and recorded on Issue #167.

## Objective and source identity

- Issue: `#167` (`enhancement`, `ready-for-agent`).
- Base revision: `850144c75ac65aa8cf67117e9090bd471b78232c`.
- Base tree: `c86b3ec594c6944003d1744e8e8f50c4e3af88aa`.
- Tested implementation revision: `d315251e6592d4536530def72102e29b2cc881f2`.
- Tested implementation tree: `50ebd6947ff2f80eca0ded13fba595dcf51d7422`.
- Tested evidence revision and tree: pending final evidence binding.
- Claim boundary: this is hermetic test-contract evidence for the
  **fail-closed accountability Quality Contract**. It does not establish
  Verification Agent behavior-layer capability, Android/OEM coverage, a
  quality threshold, production outcome, or formal-run result.

## Baseline disposition

Issue #165 measured `src/aiverify/runner/admission.py` with 76 branch
opportunities, 44 covered, and 32 missing. This issue does not rewrite that
historical audit. Instead, [`branch-map.json`](branch-map.json) reads the
committed #165 raw coverage artifact and requires each of those 32 missing arcs
to occur once in one concrete, named test group:

- exact Run Spec source and serialized-byte identity;
- serialized receipt revalidation;
- host origin, commit, worktree, and locator identity;
- target declaration and deployment identity;
- Verification Agent Backend policy and executable resolution;
- artifact namespace and read-only Git command failure.

`tests/bench/test_admission_contract_matrix.py` fails if an arc is omitted,
duplicated, or no longer matches the #165 raw artifact. The targeted execution
below exercised all 235 statements and all 76 branch opportunities in the
admission module. That observation is a narrow execution fact, not a percentage
claim about the Verification Agent.

## Verification

Tools:

- macOS 26.3 (25D125), Darwin 25.3.0, arm64
- Git 2.50.1 (Apple Git-155)
- uv 0.11.7 (`9d177269e`, 2026-04-15, aarch64-apple-darwin)
- Python 3.11.15, pytest 9.1.1, coverage.py 7.15.4 with C extension

Commands and results on the tested implementation revision:

```text
uv run --extra dev python -m pytest -o addopts='' --collect-only -q
PASS: 1064 tests collected in 0.14s.

/usr/bin/time -p uv run --extra dev python -m pytest -rs
PASS: 1063 passed, 1 skipped in 48.44s; real 48.54s, user 31.64s, sys 14.64s.
Skip: tests/bench/test_m9_recovery_formal.py:195 requires explicit admission
of a repository-external fixture.

/usr/bin/time -p uv run --extra dev python -m coverage run \
  --source=aiverify.runner.admission \
  --data-file=docs/runs/2026-08-15-issue-167-admission-rejection-contracts/artifacts/admission-coverage.data \
  -m pytest -o addopts='' -q -rs \
  tests/runner/test_admission.py \
  tests/bench/test_admission_contract_matrix.py
PASS: 50 passed in 5.69s; real 5.90s, user 2.82s, sys 2.59s.

uv run --extra dev python -m coverage json \
  --data-file=docs/runs/2026-08-15-issue-167-admission-rejection-contracts/artifacts/admission-coverage.data \
  -o docs/runs/2026-08-15-issue-167-admission-rejection-contracts/artifacts/admission-coverage.json
PASS: JSON report written.

uv run --extra dev python -m coverage report \
  --data-file=docs/runs/2026-08-15-issue-167-admission-rejection-contracts/artifacts/admission-coverage.data \
  --sort=Cover
PASS: admission.py has 235/235 statements, 76/76 branches, 0 missing branches,
and 0 partial branches in this targeted execution.

/usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q -rs \
  tests/runner/test_admission.py \
  tests/bench/test_admission_contract_matrix.py \
  tests/bench/test_coverage_audit_contract.py \
  tests/test_external_fixture_gate.py \
  tests/bench/test_run_record_checksums.py \
  tests/bench/test_current_claim_matrix.py
PASS: 69 passed in 6.10s; real 6.18s, user 3.02s, sys 2.63s.

/usr/bin/time -p uv run --extra dev python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-08-15-issue-167-admission-rejection-contracts --verify
PASS: checksum inventory verified for 5 artifacts; real 0.03s, user 0.02s,
sys 0.00s.

/usr/bin/time -p git diff --check
PASS: exit 0; real 0.01s, user 0.00s, sys 0.05s.
```

## Artifact inventory, side effects, and known gaps

- `branch-map.json` — canonical mapping of the 32 Issue #165 baseline arcs to
  named #167 contract-test groups, SHA-256
  `0855f04af605c9a804a4e742fb5468fd7ae21ca4e5ebb281ea1681b377ab403a`.
- `artifacts/admission-coverage.data` — raw coverage.py data for the targeted
  execution, SHA-256
  `1e9252e3e91a0dbb2de054bb52b2a19c480a1fd56727c667d4b81335f1a0c279`.
- `artifacts/admission-coverage.json` — machine-readable targeted line and
  branch report, SHA-256
  `7277f4a0afcb45412e1d6d997beb421a3b3f9c5bdbe7448a4b7949dc791139b5`.
- `verification.json` — machine-readable source identity, commands, results,
  scope, and claim boundary; checksum recorded in `checksums.sha256`.

No device or emulator, Android build/install, model, oracle, Verification Agent
Backend, formal consumer, namespace claim, mapping release, external-fixture
admission, external snapshot mutation, cohort/population action, or manual step
occurred. The temporary Git repositories used by the tests are test fixtures;
the injected command runners permit only read-only Git identity queries.

Known gaps:

- This verifies explicit admission and receipt rejection behavior at a local
  hermetic boundary. It does not prove a real Android execution, detection rate,
  causal explanation, oracle soundness, or broader Verification Agent utility.
- Runner CLI phase ordering, ExecutionRecord terminal accounting, and Effective
  Execution Identity remain separate P0 backlog items; no formal or historical
  M8/M9/M9-R evidence was replayed or changed.
