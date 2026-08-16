# Issue #171 — ExecutionRecord terminal-accounting contracts

Status: the hermetic ExecutionRecord terminal-accounting contracts and their
measured evidence are complete on
`issue-171-execution-record-terminal-accounting`. This record's first evidence
commit is bound in a follow-up commit that refreshes its checksum ledger.

## Objective and source identity

- Issue: `#171` (`enhancement`, `ready-for-agent`).
- Base revision: `d12ae239ded2450aae3ae7d4b0dc9d26bd851fae`.
- Base tree: `ddd920c5c1a40824520d698355d6a4f4c8452e53`.
- Tested implementation revision: `ce10b832cc8492279976bc7a13743936e16dd2ba`.
- Tested implementation tree: `750e16779b0d5e46d2fb3f27dfffb55f84d83d85`.
- Tested evidence revision: `7debf4e6f510e4487d94b7bb326b9cca98a57c9b`.
- Tested evidence tree: `e904d342f10842c21363c41e7fff6898f72aa18d`.
- The tested evidence revision is the first commit containing the tested
  implementation and complete run record. The binding follow-up refreshes its
  ledger. The Issue #171 implementation-evidence comment records the pushed
  head; the final completion comment will add the merged SHA.
- Claim boundary: this is hermetic test-contract evidence for the
  **fail-closed accountability Quality Contract** at the ExecutionRecord
  terminal-accounting boundary. It does not establish Verification Agent
  behavior-layer capability, a production quality threshold, Android/OEM
  coverage, a production outcome, or a formal-run result.

## Baseline disposition and contract

The Issue #165 risk map made ExecutionRecord terminal accounting the next P0
boundary after merged WB-P0-01 (#167) and WB-P0-02 (#169). Before this
implementation, the ordinary hermetic suite measured
`src/aiverify/runner/execution_record.py` at 161/194 statements and 55/80
branches, with 25 missing branch arcs and 25 partial branches. That measured
base artifact is retained rather than rewriting the historical #165 audit.

[`branch-map.json`](branch-map.json) is a checked, one-to-one disposition of
all 25 fresh baseline arcs. It names the exact collected hermetic case for each
arc and rejects a duplicate, omitted, or stale nodeid. The targeted execution
then observes 194/194 statements and 80/80 branches with no missing or partial
branches. Those are scoped execution facts, not a numeric quality gate or a
Verification Agent capability claim.

The contracts use temporary local files and controlled persistence seams only.
They cover:

- malformed lifecycle, execution, timing, evidence-reference, phase-error, and
  final-reason inputs;
- mismatched attempt identity, repeat finalization, corrupt persisted bytes,
  missing terminal timing, and atomic-replacement failure;
- valid `preflight_rejected`, `interrupted`, and `failed` terminal states, each
  with exactly one non-accountable ExecutionRecord, exit code 2, and an ordered
  final phase error matching the canonical reason;
- exclusive establishment and artifact-write failures, including temporary-file
  cleanup and preservation of prior evidence; and
- schema-v1 compatibility and schema-v2 execution-provenance requirements.

No production Runner CLI, ExecutionRecord terminal-accounting, or Effective
Execution Identity semantics changed. A contract failure would be a separate
Behavior-Layer Defect triage input, not authorization to reinterpret a past
ExecutionRecord.

## Verification

Tools:

- macOS 26.3 (25D125), Darwin arm64
- Git 2.50.1 (Apple Git-155)
- uv 0.11.7 (`9d177269e`, 2026-04-15, aarch64-apple-darwin)
- Python 3.11.15, pytest 9.1.1, coverage.py 7.15.4 with C extension

Commands and results:

```text
# Fresh baseline on base d12ae23, before the contract implementation
/usr/bin/time -p uv run --extra dev python -m coverage run --branch \
  --source=aiverify.runner.execution_record \
  --data-file=docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-baseline.data \
  -m pytest -o addopts='' -q -rs
PASS: 1092 passed, 1 skipped in 124.98s; real 135.96s, user 67.05s,
sys 17.31s.
Skip: tests/bench/test_m9_recovery_formal.py:195 requires explicit admission
of a repository-external fixture.

uv run --extra dev python -m coverage json \
  --data-file=docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-baseline.data \
  -o docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-baseline.json
PASS: JSON report written.

uv run --extra dev python -m coverage report \
  --data-file=docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-baseline.data \
  --sort=Cover
PASS: execution_record.py has 161/194 statements, 55/80 branches,
25 missing branches, and 25 partial branches.

uv run --extra dev python -m pytest -o addopts='' --collect-only -q
PASS: 1140 tests collected in 0.17s.

/usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q -rs
PASS: 1139 passed, 1 skipped in 50.13s; real 50.24s, user 31.00s,
sys 15.25s.
Skip: tests/bench/test_m9_recovery_formal.py:195 requires explicit admission
of a repository-external fixture.

/usr/bin/time -p uv run --extra dev python -m coverage run --branch \
  --source=aiverify.runner.execution_record \
  --data-file=docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-contracts.data \
  -m pytest -o addopts='' -q -rs \
  tests/runner/test_execution_record.py \
  tests/runner/test_execution_record_terminal_accounting.py \
  tests/bench/test_execution_record_terminal_accounting_matrix.py
PASS: 54 passed in 0.20s; real 0.41s, user 0.34s, sys 0.07s.

uv run --extra dev python -m coverage json \
  --data-file=docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-contracts.data \
  -o docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-contracts.json
PASS: JSON report written.

uv run --extra dev python -m coverage report \
  --data-file=docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-contracts.data \
  --sort=Cover
PASS: execution_record.py has 194/194 statements, 80/80 branches,
0 missing branches, and 0 partial branches in this targeted execution.

/usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q -rs \
  tests/runner/test_execution_record.py \
  tests/runner/test_execution_record_terminal_accounting.py \
  tests/bench/test_execution_record_terminal_accounting_matrix.py \
  tests/bench/test_coverage_audit_contract.py \
  tests/test_external_fixture_gate.py \
  tests/bench/test_run_record_checksums.py \
  tests/bench/test_current_claim_matrix.py
PASS: 73 passed in 0.70s; real 0.82s, user 0.62s, sys 0.14s.

uv run --extra dev python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting --verify
PASS: checksum inventory verified for 7 artifacts.

git diff --check origin/main...HEAD
PASS: exit 0.
```

The first evidence commit and binding follow-up record exact identities in
[`verification.json`](verification.json).

## Artifact inventory, side effects, and known gaps

- `branch-map.json` — checked one-to-one map of 25 fresh baseline arcs,
  SHA-256 `29757091ef5a4e77ecf9a2493c3702da8b41c29b9a2cb10a41639da0af5f9b5e`.
- `artifacts/execution-record-baseline.data` — raw base measurement,
  SHA-256 `aa6312cb9045825fc1f78213f58a603135d8eefceb24f0606a93e6dbc607a1fa`.
- `artifacts/execution-record-baseline.json` — machine-readable base report,
  SHA-256 `ec262e0aa191f3cb5c938bc97b8faea315f8905d69ed0b2304702faf0d9b4078`.
- `artifacts/execution-record-contracts.data` — raw targeted contract
  measurement, SHA-256 `cb73214f02205341f2d59b994547646bf7f5e6da879040de2a14871a7e99c781`.
- `artifacts/execution-record-contracts.json` — machine-readable targeted
  report, SHA-256 `3dd108ae729701eedf98985c2016216df82dfea836a65a4b15b4293166113935`.
- `verification.json` — machine-readable source identity, commands, results,
  scope, and claim boundary; it is listed in `checksums.sha256`.

No device or emulator, Android build/install, package launch, model, remote
oracle, Verification Agent Backend, formal consumer, external fixture
admission, external snapshot mutation, cohort/population action, or manual
step occurred. The contracts write only isolated pytest temporary files and
local run artifacts.

Known gaps:

- The suite proves fail-closed terminal-accounting behavior at hermetic local
  seams; it does not prove a real Android execution, detection rate, causal
  explanation, oracle soundness, or broader Verification Agent utility.
- It preserves existing production semantics and does not establish a numeric
  coverage threshold or CI gate.
- The repository-external historical fixture remains skipped by default; frozen
  M8, M9, and M9-R evidence was neither replayed nor changed.
