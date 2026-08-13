# Issue #165 — risk-weighted white-box coverage audit

Status: baseline measurement and audit remediation complete on
`issue-165-risk-weighted-white-box-coverage-audit`. This record becomes durable
with the commits that contain this directory; the exact pushed and merged
evidence identities are recorded in the Issue #165 completion comment.

## Objective and source identity

- Issue: `#165` (`enhancement`, `ready-for-agent`).
- Base revision: `27e0c6449562659a2e62339d3ab27b25ca014855`.
- Base tree: `a7516116eef16ec7ffe31c23fe83ab4952b204c4`.
- Tested implementation revision:
  `4027291c96fe2b7c48d567a3d7e16b991a5083b5`.
- Tested implementation tree:
  `b654402cfdaff778fcf7e407f6a05b6cd5ac6813`.
- Tested evidence revision: recorded by the identity-binding follow-up commit.
- Claim boundary: this is a test-infrastructure measurement and audit. It does
  not establish Verification Agent behavior-layer capability, a production
  quality threshold, or a formal-run claim.

## Repeatable measurement contract

`pyproject.toml` adds the development dependency `coverage>=7.0` and fixes the
measurement scope to `aiverify` with branch measurement enabled. The ordinary,
hermetic audit command is:

```text
uv run --extra dev python -m coverage run -m pytest -rs
uv run --extra dev python -m coverage json -o coverage.json
uv run --extra dev python -m coverage report --sort=Cover
```

The default pytest configuration remains the external-fixture gate: the one
repository-external historical fixture is skipped unless it is explicitly
admitted. The durable invocation below sets a run-record-local data file rather
than writing `.coverage` at repository root.

## Verification and observed baseline

Tools:

- macOS 26.3 (25D125), Darwin 25.3.0, arm64
- Git 2.50.1 (Apple Git-155)
- uv 0.11.7 (`9d177269e`, 2026-04-15, aarch64-apple-darwin)
- Python 3.11.15, pytest 9.1.1, coverage.py 7.15.4 with C extension

Commands and results on the tested implementation revision:

```text
uv run --extra dev python -m pytest --collect-only -q
PASS: 1024 tests collected.

/usr/bin/time -p uv run --extra dev python -m coverage run \
  --data-file=docs/runs/2026-08-13-issue-165-risk-weighted-white-box-coverage-audit/artifacts/coverage.data \
  -m pytest -rs
PASS: 1023 passed, 1 skipped in 93.24s; real 93.52s, user 70.74s, sys 18.68s.
Skip: tests/bench/test_m9_recovery_formal.py:195 requires explicit admission
of a repository-external fixture.

uv run --extra dev python -m coverage json \
  --data-file=docs/runs/2026-08-13-issue-165-risk-weighted-white-box-coverage-audit/artifacts/coverage.data \
  -o docs/runs/2026-08-13-issue-165-risk-weighted-white-box-coverage-audit/artifacts/coverage.json
PASS: JSON report written.

uv run --extra dev python -m coverage report \
  --data-file=docs/runs/2026-08-13-issue-165-risk-weighted-white-box-coverage-audit/artifacts/coverage.data \
  --sort=Cover
PASS: 19,897 statements; 15,286 covered; 4,611 missing. 7,658 branch
opportunities; 4,857 covered; 2,801 missing; 2,075 partial branches. Total
coverage: 73% (77% statements; 63% branches).
```

The 73% total is an execution-measurement baseline only. A branch can be taken
without proving observable Android behavior, causal explanation, oracle
soundness, evidence integrity, or Verification Agent usefulness. Conversely, a
deliberately gated external or formal path can be important despite being
unmeasured here. Prioritize the Quality Contract, not the percentage.

## Named Quality Contract and canonical risk map

The primary **Quality Contract** is **fail-closed accountability**: the
Verification Agent rejects missing, unknown, stale, contradictory, or invalid
source, Effective Execution Identity, ExecutionRecord, or evidence before the
relevant external side effect. Such input cannot create an accountable
ExecutionRecord, Finding, or Local Conclusion.

[`risk-map.json`](risk-map.json) is the canonical, checked projection of
[`artifacts/coverage.json`](artifacts/coverage.json). It records the exact
per-surface branch counts and both unambiguous percentages:

- `covered_branch_percentage` is `covered_branches / num_branches`.
- `combined_coverage_percentage` is coverage.py's statement-and-branch value;
  it is not a branch percentage or a Verification Agent capability claim.

For every P0/P1 surface, the complete branch-to-action inventory is the join of
that surface's `source_paths` and action with
`coverage.json.files[source_path].missing_branches`. Each raw `[from_line,
to_line]` arc is explicitly governed by the surface's concrete `next_action`.
[`tests/bench/test_coverage_audit_contract.py`](../../../tests/bench/test_coverage_audit_contract.py)
asserts this complete disposition and exact metrics, so a future source-report
or hand-maintained-map drift fails locally.

| Priority | Quality Contract / trust boundary | Canonical surface | Existing hermetic evidence | Action |
| --- | --- | --- | --- | --- |
| P0 | fail-closed accountability / production-seam admission | `runner/admission.py` | `tests/runner/test_admission.py` | `WB-P0-01` |
| P0 | fail-closed accountability / Runner CLI external-side-effect ordering | `runner/cli.py` | `tests/runner/test_cli.py`, `tests/runner/test_admission.py` | `WB-P0-02` |
| P0 | fail-closed accountability / ExecutionRecord terminal accounting | `runner/execution_record.py` | `tests/runner/test_execution_record.py` | `WB-P0-03` |
| P0 | fail-closed accountability / Effective Execution Identity | `runner/execution_identity.py` | `tests/runner/test_execution_identity.py` | `WB-P0-04` |
| P0 | fail-closed accountability / package-reset destructive boundary | `runner/package_reset.py` | `tests/runner/test_package_reset.py` | `WB-P0-05` |
| P0 | fail-closed accountability / Context Acquisition | `discovery/acquisition.py` | `tests/discovery/test_acquisition.py` | `WB-P0-06` |
| P0 | fail-closed accountability / Discovery Campaign reduction | `discovery/campaign.py` | `tests/discovery/test_campaign.py` | `WB-P0-07` |
| P0 | fail-closed accountability / Attack Plan admission | `discovery/attack_planning.py` | `tests/discovery/test_attack_planning.py` | `WB-P0-08` |
| P0 | fail-closed accountability / M9 preclaim and namespace claim | `bench/m9_recovery_formal.py` | `tests/bench/test_m9_recovery_formal.py` | `WB-P0-09` |
| P0 | fail-closed accountability / M9 terminal absence and reconciliation | `bench/m9_recovery_qualification.py` | `tests/bench/test_m9_recovery_qualification.py` | `WB-P0-10` |
| P1 | fail-closed accountability / system-event evidence binding | `runner/system_events.py` | `tests/runner/test_system_events.py` | `WB-P1-01` |
| P1 | fail-closed accountability / evidence artifact binding | `runner/evidence.py` | `tests/runner/test_evidence.py` | `WB-P1-02` |
| P1 | fail-closed accountability / immutable M8 formal orchestration | `bench/m8_formal.py` | `tests/bench/test_m8_formal.py` | `WB-P1-03` |
| P1 | fail-closed accountability / immutable M9 formal orchestration | `bench/m9_formal.py` | `tests/bench/test_m9_formal.py` | `WB-P1-04` |
| P1 | fail-closed accountability / Hypothesis Portfolio selection | `discovery/hypothesis_portfolio.py` | `tests/discovery/test_hypothesis_portfolio.py` | `WB-P1-05` |
| P1 | fail-closed accountability / Discovery Campaign contract validation | `discovery/contracts.py` | `tests/discovery/test_contracts.py` | `WB-P1-06` |
| P2 | deferred wrapper coverage | providers and Android harness after P0/P1 admission | provider/harness suites | `WB-P2-01` |

The exact next action for every ID is intentionally defined once in
`risk-map.json`; no historical M8/M9 evidence is to be replayed merely to raise
coverage. The P0/P1 backlog is a triage input, not authorization to change
production semantics, start a formal run, create a population, or set a CI
threshold.

## Artifact inventory, side effects, and known gaps

- `artifacts/coverage.data` — raw coverage.py data for the measured suite,
  SHA-256 `19a5b38616e0f6e6aa1086f20439d25701831bad013cfda484d65b0676c06551`.
- `artifacts/coverage.json` — machine-readable line and branch report,
  SHA-256 `74caabe53ee6165173a83ae3c9b8cd97604ecd0660a2498de748a01893c27d17`.
- `risk-map.json` — checked Quality Contract/risk/action projection,
  SHA-256 `9b7d276b2ba078e96d1631ca4208382de77ff2c92399f7b77169078d6884673c`.
- `verification.json` — machine-readable source identity, commands, metrics,
  risk-map reference, and zero-side-effect declaration.
- `checksums.sha256` — ledger for every run-record artifact except itself.

No emulator, device, Android build/install, model or oracle call, formal
consumer, namespace claim, mapping release, external fixture admission, manual
step, historical evidence mutation, new cohort, or formal population was
performed. The known gap is intentional: this one local, default-suite baseline
does not measure the explicitly gated external historical fixture or establish
Verification Agent behavior-layer effectiveness. The P0/P1 backlog is the
deduplicated follow-up input; none is implemented by this issue.
