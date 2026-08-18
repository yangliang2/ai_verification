# Issue #171 — ExecutionRecord terminal-accounting contracts

Status: the hermetic ExecutionRecord terminal-accounting contracts and their
measured evidence have been reconciled with merged #173 on
`issue-171-execution-record-terminal-accounting`. This record refreshes the
issue-local measurement from the current `main` base; its corrected evidence
commit is bound in a follow-up checksum commit.

## Objective and source identity

- Issue: `#171` (`enhancement`, `ready-for-agent`).
- Base revision: `a59e0e50b63ae8df1dc67df15ccaefacd95721d9`.
- Base tree: `536dc46b9952dfd89f936f338c0ea19508a1d25d`.
- Tested implementation revision: `26a2d35166fbe25cf8fa70392991e764401e378b`.
- Tested implementation tree: `a0a540e9a3d8d33000904b7e50b994dc0db04804`.
- Tested evidence revision: `67bf1a4ecad06f40bca1212973df6ee6a6a34b45`.
- Tested evidence tree: `bd12fe0c27e8a3084b63198872a0e729eb53f2f1`.
- The tested evidence revision is the first commit containing the reconciled
  implementation evidence. This checksum-binding follow-up records that
  identity; the Issue #171 implementation-evidence comment records the pushed
  head, and a final completion comment will add the merged SHA.
- Reconciliation: the prior issue-local measurement used `d12ae23` before
  #173 changed the same boundary. It is superseded for this PR by the exact
  current-base measurement below; the historical #165 audit remains immutable.
- Claim boundary: this is hermetic test-contract evidence for the
  **fail-closed accountability Quality Contract** at the ExecutionRecord
  terminal-accounting boundary. It does not establish Verification Agent
  behavior-layer capability, a production quality threshold, Android/OEM
  coverage, a production outcome, or a formal-run result.

## Baseline disposition and contract

The Issue #165 risk map made ExecutionRecord terminal accounting the next P0
boundary after merged WB-P0-01 (#167) and WB-P0-02 (#169). On the current base,
which includes #173's post-publication repair, the ordinary hermetic suite
measured `src/aiverify/runner/execution_record.py` at 172/206 statements and
56/82 branches, with 26 missing branch arcs and 26 partial branches. The #165
audit remains historical context; this separate, current-base artifact does not
rewrite it.

[`branch-map.json`](branch-map.json) is a checked, one-to-one disposition of
all 26 fresh baseline arcs. It names the exact collected hermetic case for each
arc and rejects a duplicate, omitted, or stale nodeid. The targeted execution
then observes 206/206 statements and 82/82 branches with no missing or partial
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
- exclusive establishment and artifact-write failures, including pre- and
  post-publication temporary-file cleanup and preservation of prior evidence;
  and
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
# Fresh baseline on base a59e0e5, before this contract reconciliation.
# Executed from detached worktree /tmp/ai-verification-issue-171-base-a59e0e5.
/usr/bin/time -p uv run --extra dev python -m coverage run --branch \
  --source=aiverify.runner.execution_record \
  --data-file=/Users/peter/projects/ai_verification-issue-171/docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-baseline.data \
  -m pytest -o addopts='' -q -rs
PASS: 1097 passed, 1 skipped in 122.08s; real 143.58s, user 66.70s,
sys 17.10s.
Skip: tests/bench/test_m9_recovery_formal.py:195 requires explicit admission
of a repository-external fixture.

uv run --extra dev python -m coverage json \
  --data-file=/Users/peter/projects/ai_verification-issue-171/docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-baseline.data \
  -o /Users/peter/projects/ai_verification-issue-171/docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-baseline.json
PASS: JSON report written.

uv run --extra dev python -m coverage report \
  --data-file=/Users/peter/projects/ai_verification-issue-171/docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-baseline.data \
  --sort=Cover
PASS: execution_record.py has 172/206 statements, 56/82 branches,
26 missing branches, and 26 partial branches.

uv run --extra dev python -m pytest -o addopts='' --collect-only -q
PASS: 1146 tests collected in 0.18s.

/usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q -rs
PASS: 1145 passed, 1 skipped in 85.70s; real 85.99s, user 31.80s,
sys 15.80s.
Skip: tests/bench/test_m9_recovery_formal.py:195 requires explicit admission
of a repository-external fixture.

/usr/bin/time -p uv run --extra dev python -m coverage run --branch \
  --source=aiverify.runner.execution_record \
  --data-file=docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-contracts.data \
  -m pytest -o addopts='' -q -rs \
  tests/runner/test_execution_record.py \
  tests/runner/test_execution_record_terminal_accounting.py \
  tests/bench/test_execution_record_terminal_accounting_matrix.py
PASS: 60 passed in 0.22s; real 0.47s, user 0.36s, sys 0.07s.

uv run --extra dev python -m coverage json \
  --data-file=docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-contracts.data \
  -o docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-contracts.json
PASS: JSON report written.

uv run --extra dev python -m coverage report \
  --data-file=docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-contracts.data \
  --sort=Cover
PASS: execution_record.py has 206/206 statements, 82/82 branches,
0 missing branches, and 0 partial branches in this targeted execution.

/usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q -rs \
  tests/runner/test_execution_record.py \
  tests/runner/test_execution_record_terminal_accounting.py \
  tests/bench/test_execution_record_terminal_accounting_matrix.py \
  tests/bench/test_coverage_audit_contract.py \
  tests/test_external_fixture_gate.py \
  tests/bench/test_run_record_checksums.py \
  tests/bench/test_current_claim_matrix.py
PASS: 79 passed in 0.75s; real 0.85s, user 0.66s, sys 0.16s.

uv run --extra dev python -m compileall -q src
PASS: exit 0.

uv run --extra dev python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting --verify
PASS: checksum inventory verified for 7 artifacts.

git diff --check origin/main...HEAD
PASS: exit 0.
```

The first evidence commit and binding follow-up record exact identities in
[`verification.json`](verification.json).

## Artifact inventory, side effects, and known gaps

- `branch-map.json` — checked one-to-one map of 26 fresh baseline arcs,
  SHA-256 `0282e6c0f732583594d2c849e865ed30a15a2977da43fc160c941abd4d1c5431`.
- `artifacts/execution-record-baseline.data` — raw base measurement,
  SHA-256 `9a2344e31877a64141d7aeae7ac3e93dab959181c133e1fd4781f5f7ec37ab98`.
- `artifacts/execution-record-baseline.json` — machine-readable base report,
  SHA-256 `af688c9a12a5ec11f12a5145ce8f36caed011213c3d6473e1bff73ce5cdab442`.
- `artifacts/execution-record-contracts.data` — raw targeted contract
  measurement, SHA-256 `c042c912a256fc1b8f3ad71ef713a972712c96cf1fd2039caef5f2681a2a44fa`.
- `artifacts/execution-record-contracts.json` — machine-readable targeted
  report, SHA-256 `2ccf8f8a28fa53178491ba999ca1fd05a55f1b698fcfdeafc60b13cbe33248f9`.
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
