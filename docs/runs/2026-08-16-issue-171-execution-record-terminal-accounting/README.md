# Issue #171 — ExecutionRecord terminal-accounting contracts

Status: reconciled after merged #173 and #175 on
issue-171-execution-record-terminal-accounting. This is a fresh, scoped
measurement from current main. The initial evidence commit is followed by a
checksum-binding commit that records its exact identity.

## Objective and source identity

- Issue: #171 (enhancement, ready-for-agent).
- Base revision: 5b19bdde0b42bf7497334b5f9039c1fc076d769d.
- Base tree: 26f4493c9d7c215a569775c6c844d6d9a05cb2e5.
- Tested implementation revision: e766da3151a0c7ae5246933e2666c22a85bd0eb7.
- Tested implementation tree: c00d72e8cc0360813ebe3f5fd2cace068acea864.
- Tested evidence revision and tree: pending the immediately following
  checksum-binding commit.
- Reconciliation: the earlier d12 measurement predates #173, and the later
  a59e0e5 measurement predates #175's temporary-file authority repair. Both
  are superseded for this PR by the exact current-main measurement below. The
  historical #165 audit remains immutable.
- Claim boundary: hermetic fail-closed accountability Quality Contract evidence
  at the ExecutionRecord terminal-accounting boundary only. It does not
  establish Verification Agent behavior-layer capability, a production quality
  threshold, Android/OEM coverage, a production outcome, or a formal-run
  result.

## Baseline disposition and contract

The Issue #165 risk map identifies ExecutionRecord terminal accounting as the
next P0 boundary after merged WB-P0-01 (#167) and WB-P0-02 (#169). On base
5b19bdd, the ordinary hermetic suite measured
src/aiverify/runner/execution_record.py at 182/215 statements and 59/84
branches, with 25 missing branch arcs and 25 partial branches. This separate
current-base artifact does not rewrite the historical #165 audit.

branch-map.json is a checked one-to-one disposition of all 25 fresh baseline
arcs. It names the exact collected hermetic case for every arc and rejects a
duplicate, omitted, or stale nodeid. The targeted execution observes 215/215
statements and 84/84 branches with no missing or partial branches. These are
scoped execution facts, not a numeric quality gate or a Verification Agent
capability claim.

The contracts use temporary local files and controlled persistence seams only.
They cover:

- malformed lifecycle, execution, timing, evidence-reference, phase-error, and
  final-reason inputs;
- mismatched attempt identity, repeat finalization, corrupt persisted bytes,
  missing terminal timing, and failed atomic replacement;
- valid preflight_rejected, interrupted, and failed terminal states, each with
  exactly one non-accountable ExecutionRecord, exit code 2, and an ordered
  final phase error matching the canonical reason;
- exclusive establishment and artifact-write failures; pre-publication replace
  and cleanup failures preserve the prior canonical record; a temporary file
  retained when cleanup itself fails before deletion remains in the unpublished
  namespace and is rejected by the public loader; and
- schema-v1 compatibility and schema-v2 execution-provenance requirements.

The merged #175 policy remains intact: an initial in_progress ExecutionRecord
is the canonical durable but non-accountable attempt envelope, while a terminal
replacement becomes authoritative only after os.replace. This PR changes no
production Runner CLI, ExecutionRecord, or Effective Execution Identity
semantics. A failed contract would be a separate fail-closed accountability
persistence-defect triage input, not authorization to reinterpret an existing
ExecutionRecord.

## Verification

Tools:

- macOS 26.3 (25D125), Darwin arm64
- Git 2.50.1 (Apple Git-155)
- uv 0.11.7 (9d177269e, 2026-04-15, aarch64-apple-darwin)
- Python 3.11.15, pytest 9.1.1, coverage.py 7.15.4 with C extension

Commands and results:

    # Fresh baseline from detached current main, before this PR's test change.
    # Executed from /tmp/ai-verification-issue-171-main-kaSlME.
    /usr/bin/time -p uv run --extra dev python -m coverage run --branch \
      --source=aiverify.runner.execution_record \
      --data-file=/Users/peter/projects/ai_verification-issue-171/docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-baseline.data \
      -m pytest -o addopts='' -q -rs
    PASS: 1098 passed, 1 skipped in 116.17s; real 128.97s, user 66.01s,
    sys 16.39s.
    Skip: tests/bench/test_m9_recovery_formal.py:195 requires explicit
    admission of a repository-external fixture.

    uv run --extra dev python -m coverage json \
      --data-file=/Users/peter/projects/ai_verification-issue-171/docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-baseline.data \
      -o /Users/peter/projects/ai_verification-issue-171/docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-baseline.json
    PASS: JSON report written.

    uv run --extra dev python -m coverage report \
      --data-file=/Users/peter/projects/ai_verification-issue-171/docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-baseline.data \
      --sort=Cover
    PASS: execution_record.py has 182/215 statements, 59/84 branches,
    25 missing branches, and 25 partial branches.

    uv run --extra dev python -m pytest -o addopts='' --collect-only -q
    PASS: 1147 tests collected in 0.38s.

    /usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q -rs
    PASS: 1146 passed, 1 skipped in 152.44s; real 152.70s, user 56.17s,
    sys 32.25s.
    Skip: tests/bench/test_m9_recovery_formal.py:195 requires explicit
    admission of a repository-external fixture.

    /usr/bin/time -p uv run --extra dev python -m coverage run --branch \
      --source=aiverify.runner.execution_record \
      --data-file=docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-contracts.data \
      -m pytest -o addopts='' -q -rs \
      tests/runner/test_execution_record.py \
      tests/runner/test_execution_record_terminal_accounting.py \
      tests/bench/test_execution_record_terminal_accounting_matrix.py
    PASS: 61 passed in 0.47s; real 1.01s, user 0.68s, sys 0.16s.

    uv run --extra dev python -m coverage json \
      --data-file=docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-contracts.data \
      -o docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-contracts.json
    PASS: JSON report written.

    uv run --extra dev python -m coverage report \
      --data-file=docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting/artifacts/execution-record-contracts.data \
      --sort=Cover
    PASS: execution_record.py has 215/215 statements, 84/84 branches,
    0 missing branches, and 0 partial branches in this targeted execution.

    /usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q -rs \
      tests/runner/test_execution_record.py \
      tests/runner/test_execution_record_terminal_accounting.py \
      tests/bench/test_execution_record_terminal_accounting_matrix.py \
      tests/bench/test_coverage_audit_contract.py \
      tests/test_external_fixture_gate.py \
      tests/bench/test_run_record_checksums.py \
      tests/bench/test_current_claim_matrix.py
    PASS: 80 passed in 3.95s; real 4.18s, user 1.39s, sys 1.92s.

    uv run --extra dev python -m compileall -q src
    PASS: exit 0.

The final binding commit records exact source identity in verification.json,
regenerates checksums.sha256, verifies its 7-artifact inventory, and runs
git diff --check origin/main...HEAD.

## Artifact inventory, side effects, and known gaps

- branch-map.json — checked one-to-one map of 25 fresh baseline arcs,
  SHA-256 fded41504cc1c1ba68a9325509947c38e6f24c69008323e1ff99c46558e94d8b.
- artifacts/execution-record-baseline.data — raw base measurement,
  SHA-256 c641aa37f4c12eedeb7b935cf88a9a1aebccc8f8c88106aa04619295786f4846.
- artifacts/execution-record-baseline.json — machine-readable base report,
  SHA-256 a67da15cf4d4159708084a676709e65bdc434d7cd7f3e914876879a2591e4aa6.
- artifacts/execution-record-contracts.data — raw targeted contract
  measurement, SHA-256
  f378c2ab103a4ecf6a24f32fe8b125d1a2164d1eab1f1ff773f6128c2ea4b55a.
- artifacts/execution-record-contracts.json — machine-readable targeted
  report, SHA-256
  3f8083fdd14b66ccc99348212b54de89375175b4e68d09ac746233cb3161c760.
- verification.json — machine-readable source identity, commands, results,
  scope, and claim boundary; it is listed in checksums.sha256.

No device or emulator, Android build/install, package launch, model, remote
oracle, Verification Agent Backend, formal consumer, external fixture
admission, external snapshot mutation, cohort/population action, or manual
step occurred. The detached baseline worktree used only local repository files
and is removed after the measurement. The contracts write only isolated pytest
temporary files and local run artifacts.

Known gaps:

- The suite proves fail-closed terminal-accounting behavior at hermetic local
  seams; it does not prove a real Android execution, detection rate, causal
  explanation, oracle soundness, or broader Verification Agent utility.
- The public loader rejects a retained unpublished temporary path; direct raw
  JSON access or external path tampering is outside this loader-authority
  contract.
- It preserves existing production semantics and does not establish a numeric
  coverage threshold or CI gate.
- The repository-external historical fixture remains skipped by default; frozen
  M8, M9, and M9-R evidence was neither replayed nor changed.
