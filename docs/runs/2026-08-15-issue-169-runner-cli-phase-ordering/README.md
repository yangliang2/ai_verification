# Issue #169 — Runner CLI external-side-effect ordering

Status: the hermetic Runner CLI phase-ordering contracts and their measured
evidence are complete on `issue-169-runner-cli-phase-ordering`. The record
becomes durable with the commits containing this directory; a follow-up binding
commit records the first evidence revision and refreshes this ledger.

## Objective and source identity

- Issue: `#169` (`enhancement`, `ready-for-agent`).
- Base revision: `9d4defbbb8a4b6172c9cf7533929c35d74e21b07`.
- Base tree: `9c756ee59e6d28b4097587a6429dd5110d67050a`.
- Tested implementation revision: `2d4030311aea050a25c8372c6325d5d5420f3096`.
- Tested implementation tree: `1565e65734bf4930a5c5845e0db65d9035908573`.
- Tested evidence revision and tree: pending evidence binding.
- Claim boundary: this is hermetic test-contract evidence for the
  **fail-closed accountability Quality Contract** at the Runner CLI
  external-side-effect ordering boundary. It does not establish Verification
  Agent behavior-layer capability, a quality threshold, Android/OEM coverage,
  production outcome, or a formal-run result.

## Baseline disposition

Issue #165 measured `src/aiverify/runner/cli.py` with 80 branch opportunities,
62 covered, and 18 missing. This issue does not rewrite that historical audit.
Instead, [`branch-map.json`](branch-map.json) reads the committed #165 raw
coverage artifact and requires every historical missing arc to occur exactly
once in a named contract group. The integrity test also collects the mapped
test module and rejects a stale or nonexistent nodeid.

The contract suite injects its earliest failure at these Runner CLI boundaries:

- admission receipt/policy, before an ExecutionRecord exists;
- ExecutionRecord establishment, optional identity factory, and pre-run setup;
- static Effective Execution Identity capture, deployment, and readiness;
- live-validation preflight, device runner setup, and optional launch;
- Journey execution, oracle evaluation, identity finalization, and verdict
  output;
- public CLI admission exit routing and the module entrypoint.

For each established attempt, the suite asserts exactly one terminal,
non-accountable ExecutionRecord with an ordered failure reason and no
accountable execution provenance. Every later represented external action is
blocked. The test replacements fence `DeviceController`,
`AndroidEvidenceCollector`, `CodexCliBackend`, `DeviceSystemEventInjector`,
`JourneySegmentRunner`, and `L1Oracle`; they record local calls only and do not
invoke Android, a Verification Agent Backend, a model, or an oracle service.

The targeted execution below reaches all 80 Runner CLI branch opportunities,
including the historical 18 arcs. Its 398/411 statement observation and
80/80 branch observation are scoped execution facts, not a behavior-layer
coverage or capability claim.

## Verification

Tools:

- macOS 26.3 (25D125), Darwin arm64
- Git 2.50.1 (Apple Git-155)
- uv 0.11.7 (`9d177269e`, 2026-04-15, aarch64-apple-darwin)
- Python 3.11.15, pytest 9.1.1, coverage.py 7.15.4 with C extension

Commands and results on the tested implementation revision:

```text
uv run --extra dev python -m pytest -o addopts='' --collect-only -q
PASS: 1089 tests collected in 0.72s.

/usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q -rs
PASS: 1088 passed, 1 skipped in 50.39s; real 50.50s, user 31.44s,
sys 15.76s.
Skip: tests/bench/test_m9_recovery_formal.py:195 requires explicit admission
of a repository-external fixture.

/usr/bin/time -p uv run --extra dev python -m coverage run --branch \
  --source=aiverify.runner.cli \
  --data-file=docs/runs/2026-08-15-issue-169-runner-cli-phase-ordering/artifacts/runner-cli-coverage.data \
  -m pytest -o addopts='' -q -rs \
  tests/runner/test_cli.py \
  tests/runner/test_cli_phase_ordering.py \
  tests/bench/test_runner_cli_phase_ordering_matrix.py
PASS: 68 passed in 0.33s; real 0.56s, user 0.42s, sys 0.14s.

uv run --extra dev python -m coverage json \
  --data-file=docs/runs/2026-08-15-issue-169-runner-cli-phase-ordering/artifacts/runner-cli-coverage.data \
  -o docs/runs/2026-08-15-issue-169-runner-cli-phase-ordering/artifacts/runner-cli-coverage.json
PASS: JSON report written.

uv run --extra dev python -m coverage report \
  --data-file=docs/runs/2026-08-15-issue-169-runner-cli-phase-ordering/artifacts/runner-cli-coverage.data \
  --sort=Cover
PASS: cli.py has 398/411 statements, 80/80 branches, 0 missing branches,
and 0 partial branches in this targeted execution.

/usr/bin/time -p uv run --extra dev python -m pytest -o addopts='' -q -rs \
  tests/runner/test_cli.py \
  tests/runner/test_cli_phase_ordering.py \
  tests/bench/test_runner_cli_phase_ordering_matrix.py \
  tests/bench/test_coverage_audit_contract.py \
  tests/test_external_fixture_gate.py \
  tests/bench/test_run_record_checksums.py \
  tests/bench/test_current_claim_matrix.py
PASS: 87 passed in 1.95s; real 2.03s, user 0.70s, sys 1.30s.

uv run --extra dev python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-08-15-issue-169-runner-cli-phase-ordering --verify
PASS: checksum inventory verified for 5 artifacts.

git diff --check
PASS: exit 0.
```

The first evidence commit and binding follow-up record exact identities in
[`verification.json`](verification.json).

## Artifact inventory, side effects, and known gaps

- `branch-map.json` — canonical checked disposition of the 18 Issue #165
  Runner CLI missing branch arcs, SHA-256
  `9eaf89fb482fe60ec46e2b9e9746e4a61af5abbbb8ccbef290a772b958de3db8`.
- `artifacts/runner-cli-coverage.data` — raw targeted coverage.py data,
  SHA-256
  `0bfb0b74033d5b4fd787a350eb1428c0ba23bf38eb22deea7b425f353e14cd1b`.
- `artifacts/runner-cli-coverage.json` — machine-readable targeted line and
  branch report, SHA-256
  `28e41d6b0e0223678a2a4ab45ba3f1cc786ee9992a520b735145a4b53b494f36`.
- `verification.json` — machine-readable source identity, commands, results,
  scope, and claim boundary; it is listed in `checksums.sha256`.

No device or emulator, Android build/install, model, remote oracle,
Verification Agent Backend, formal consumer, external fixture admission,
external snapshot mutation, cohort/population action, or manual step occurred.
The tests write only isolated pytest temporary files and local run artifacts.

Known gaps:

- The suite proves ordering at hermetic seams; it does not prove a real Android
  execution, outcome detection rate, causal explanation, oracle soundness, or
  broader Verification Agent utility.
- It preserves existing Runner CLI production semantics and does not establish
  an aggregate coverage gate or numeric quality threshold.
- The repository-external historical fixture remains skipped by default; frozen
  M8, M9, and M9-R evidence was neither replayed nor changed.
