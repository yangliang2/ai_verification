# Issue #167 — production-seam admission rejection contracts

Status: the hermetic contract suite and its measured evidence are complete on
`issue-167-production-seam-admission-contracts`. This refresh incorporates the
independent-review isolation fixes. The record becomes durable with the commits
containing this directory; the evidence-identity binding is completed in the
final follow-up commit and recorded on Issue #167.

## Objective and source identity

- Issue: `#167` (`enhancement`, `ready-for-agent`).
- Base revision: `850144c75ac65aa8cf67117e9090bd471b78232c`.
- Base tree: `c86b3ec594c6944003d1744e8e8f50c4e3af88aa`.
- Tested implementation revision: `caacbdf5b33daab3d01718792569569644b7e693`.
- Tested implementation tree: `9d40ca60950b4c8121fbed42a3306bc0b9beccbe`.
- Tested evidence revision: `a1365fae0246bf0e89c8b0055c479637cb78a4a6`.
- Tested evidence tree: `2ac022c341203e383d4445a1565b6056c830ccde`.
- The tested evidence revision is the first commit containing the repaired
  implementation and refreshed run record. This binding follow-up refreshes its
  ledger; the exact pushed and merged identities are recorded in the Issue #167
  completion comment.
- Claim boundary: this is hermetic test-contract evidence for the
  **fail-closed accountability Quality Contract**. It does not establish
  Verification Agent behavior-layer capability, Android/OEM coverage, a
  quality threshold, production outcome, or formal-run result.

## Independent-review remediation

- The hermetic command runner now allows exactly the four read-only Git identity
  queries used by admission. It fails before subprocess execution for every
  other Git subcommand, including destructive `clean`, `reset`, and `push`
  forms; the failure and response-override variants use the same guard.
- The public-runner receipt-drift test places its fixture `codex` executable
  first on `PATH`, rather than depending on a host-installed Codex CLI. The
  focused negative-PATH command below confirms that the test remains green when
  the host `codex` location is unavailable.

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
PASS: 1065 tests collected in 0.17s.

/usr/bin/time -p uv run --extra dev python -m pytest -rs
PASS: 1064 passed, 1 skipped in 49.05s; real 49.15s, user 32.07s, sys 15.05s.
Skip: tests/bench/test_m9_recovery_formal.py:195 requires explicit admission
of a repository-external fixture.

/usr/bin/time -p uv run --extra dev python -m coverage run \
  --source=aiverify.runner.admission \
  --data-file=docs/runs/2026-08-15-issue-167-admission-rejection-contracts/artifacts/admission-coverage.data \
  -m pytest -o addopts='' -q -rs \
  tests/runner/test_admission.py \
  tests/bench/test_admission_contract_matrix.py
PASS: 51 passed in 5.69s; real 5.90s, user 2.74s, sys 2.70s.

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
PASS: 70 passed in 6.39s; real 6.48s, user 3.07s, sys 2.86s.

env PATH=/usr/bin:/bin /Users/peter/.local/bin/uv run --extra dev python -m pytest \
  -o addopts='' -q \
  tests/runner/test_admission.py::test_serialized_receipt_drift_blocks_public_runner_before_execution_record \
  tests/runner/test_admission.py::test_git_identity_runners_reject_non_identity_commands
PASS: 2 passed in 1.56s with no host Codex CLI on PATH.

/usr/bin/time -p uv run --extra dev python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-08-15-issue-167-admission-rejection-contracts --verify
PASS: checksum inventory verified for 5 artifacts; real 0.02s, user 0.01s,
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
  `ffed044b2a449a98769f894af8b375b2310a7cbed100ebad94da5eda60aeac98`.
- `verification.json` — machine-readable source identity, commands, results,
  scope, and claim boundary; checksum recorded in `checksums.sha256`.

No device or emulator, Android build/install, model, oracle, Verification Agent
Backend, formal consumer, namespace claim, mapping release, external-fixture
admission, external snapshot mutation, cohort/population action, or manual step
occurred. The temporary Git repositories used by the tests are test fixtures;
the injected command runners permit only the four read-only Git identity
queries required by admission.

Known gaps:

- This verifies explicit admission and receipt rejection behavior at a local
  hermetic boundary. It does not prove a real Android execution, detection rate,
  causal explanation, oracle soundness, or broader Verification Agent utility.
- Runner CLI phase ordering, ExecutionRecord terminal accounting, and Effective
  Execution Identity remain separate P0 backlog items; no formal or historical
  M8/M9/M9-R evidence was replayed or changed.
