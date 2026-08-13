# Issue #165 — risk-weighted white-box coverage audit

Status: baseline measurement and audit complete on
`issue-165-risk-weighted-white-box-coverage-audit`. This record becomes durable
with the commits that contain this directory; the exact pushed and merged
evidence identities are recorded in the Issue #165 completion comment.

## Objective and source identity

- Issue: `#165` (`enhancement`, `ready-for-agent`).
- Base revision: `27e0c6449562659a2e62339d3ab27b25ca014855`.
- Base tree: `a7516116eef16ec7ffe31c23fe83ab4952b204c4`.
- Tested implementation revision:
  `60bbc8f6ca20312755f3726cfbfa3dd61f68cca3`.
- Tested implementation tree:
  `643caad2c8fb572d2043f1eae669328868ce6e14`.
- Tested evidence revision: recorded by the identity-binding follow-up commit.
- Claim boundary: this is a test-infrastructure measurement and audit. It does
  not establish Agent behavior coverage, a production quality threshold, or a
  formal-run claim.

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
PASS: 1022 tests collected.

uv run --extra dev python -m coverage run \
  --data-file=docs/runs/2026-08-13-issue-165-risk-weighted-white-box-coverage-audit/artifacts/coverage.data \
  -m pytest -rs
PASS: 1021 passed, 1 skipped in 121.10s.
Skip: tests/bench/test_m9_recovery_formal.py:195 requires explicit admission
of a repository-external fixture.

uv run --extra dev python -m coverage json \
  --data-file=docs/runs/2026-08-13-issue-165-risk-weighted-white-box-coverage-audit/artifacts/coverage.data \
  -o docs/runs/2026-08-13-issue-165-risk-weighted-white-box-coverage-audit/artifacts/coverage.json
PASS: JSON report written.

uv run --extra dev python -m coverage report \
  --data-file=docs/runs/2026-08-13-issue-165-risk-weighted-white-box-coverage-audit/artifacts/coverage.data \
  --sort=Cover
PASS: 19,897 statements; 15,291 covered; 4,606 missing. 7,658 branch
opportunities; 4,858 covered; 2,800 missing; 2,074 partial branches. Total
coverage: 73% (77% statements; 63% branches).
```

The 73% total is an execution-measurement baseline only. A branch can be taken
without proving the observable Android behavior, causal explanation, oracle
soundness, evidence integrity, or production usefulness that a behavior-layer
claim requires. Conversely, a deliberately gated external or formal path can be
important despite being unmeasured here. Prioritize the accountability contract,
not the percentage.

## Risk-weighted coverage map

`covered branches / branch opportunities` is from `coverage.json`; a partial
rating means that the default hermetic suite executed some, not all, paths. The
listed tests are evidence of the exercised contract, not a claim that every
business behavior was established.

| Priority | trust boundary and implementation surface | Baseline | Existing hermetic evidence | Audit result and exact next action |
| --- | --- | ---: | --- | --- |
| P0 | Production seam admission: `runner/admission.py` | 44 / 76 (76%) | `tests/runner/test_admission.py` rejects host/spec/options/receipt drift before device or formal work. | Partial. **WB-P0-01:** add a table-driven child covering every failing admission check (host, exact bytes, target, policy, namespace) and assert no record, device, model, or formal-root callback. |
| P0 | Terminal attempt accounting: `runner/execution_record.py` | 55 / 80 (79%) | `tests/runner/test_execution_record.py` covers nonterminal abandonment, contradictory terminal records, and atomic write rules. | Partial. **WB-P0-02:** enumerate each terminal reason and persistence failure with a fault-injected store; assert exactly one terminal, non-accountable record on every pre-run rejection. |
| P0 | Effective Execution Identity: `runner/execution_identity.py` | 227 / 388 (68%) | `tests/runner/test_execution_identity.py` binds provenance and rejects an unapproved fixture subdirectory. | Partial and the largest runner branch gap. **WB-P0-03:** inject tool/device/APK/role-receipt drift one field at a time; assert `verify_ready_for_agent` never succeeds and no accountable evidence is emitted. |
| P0 | Destructive package-reset boundary: `runner/package_reset.py` | 24 / 28 (92%) | `tests/runner/test_package_reset.py` rejects query and clear contradictions. | Partial. **WB-P0-04:** add command-result permutations for malformed package paths and terminal command failures; assert no false `already_clean` or successful reset receipt. |
| P0 | Source identity and Context Acquisition: `discovery/acquisition.py` | 172 / 246 (82%) | `tests/discovery/test_acquisition.py` rejects dirty/mismatched identity before reads and preserves stale/contradictory evidence as non-known. | Partial. **WB-P0-05:** exercise final identity re-check and every adapter failure/unknown result using a generated Git fixture; assert no trusted graph or claimable context is returned. |
| P0 | Campaign reduction: `discovery/campaign.py` | 173 / 290 (71%) | `tests/discovery/test_campaign.py` excludes non-accountable attempts and rejects unsupported/contradictory strategy inputs. | Partial. **WB-P0-06:** mutation-test the evidence reducer inputs (terminal record, identity digest, claim boundary, ledger order) and assert no Finding/Local Conclusion survives invalid evidence. |
| P0 | Attack Plan admission: `discovery/attack_planning.py` | 141 / 238 (71%) | `tests/discovery/test_attack_planning.py` rejects fabricated, leaky, and incomplete plans before compilation. | Partial. **WB-P0-07:** table-drive malformed planner payloads, each required preflight reference, and leakage term; assert backend/compilation side effects remain zero. |
| P0 | M9 target-specific preclaim and irreversible namespace: `bench/m9_recovery_formal.py` | 76 / 226 (46%) | `tests/bench/test_m9_recovery_formal.py` covers preclaim rejection, root create-only behavior, and typed terminal absence. | Materially partial. **WB-P0-08:** first introduce an isolated namespace/command seam, then cover remaining claim, lane-exception, and reconciliation branches against a disposable fixture; do not invoke or mutate the frozen M9 records. |
| P0 | M9 terminal absence and reconciliation: `bench/m9_recovery_qualification.py` | 326 / 474 (80%) | `tests/bench/test_m9_recovery_qualification.py` rejects missing/tampered admissions, identities, receipts, ledgers, and reviews. | Partial. **WB-P0-09:** create synthetic six-lane packets for each terminal-absence/reconciliation failure and assert the qualifier remains unsupported with no new population or formal measurement. |
| P1 | System-event and evidence binding: `runner/system_events.py`, `runner/evidence.py` | 132 / 176 (85%); 32 / 34 (98%) | `tests/runner/test_system_events.py`, `tests/runner/test_evidence.py`. | `system_events` remains partial. **WB-P1-01:** inject missing, reordered, and conflicting raw events; verify reducer inputs are rejected before evidence promotion. |
| P1 | Historical M8/M9 formal orchestrators: `bench/m8_formal.py`, `bench/m9_formal.py` | 27 / 194 (24%); 10 / 160 (18%) | Static and contract-level tests only; no historical formal replay was admitted. | Intentionally unmeasured in large part. **WB-P1-02:** specify an immutable, disposable packet seam before adding tests; never use coverage pressure to replay frozen historical populations. |
| P1 | Discovery plan expansion: `discovery/hypothesis_portfolio.py`, `discovery/contracts.py` | 173 / 278 (72%); 163 / 234 (81%) | Portfolio and contracts suites exercise current validation boundaries. | Partial. **WB-P1-03:** cover unsupported prior/operator combinations and serialization contradictions that would otherwise reach selection or compilation. |
| P2 | CLI, providers, Android harness, and oracle wrappers | CLI 64 / 80 (89%); most small wrappers at 90%+ | Existing runner/provider/harness/oracle tests. | Defer. **WB-P2-01:** only add a focused test when a concrete defect or a P0/P1 boundary trace identifies an untested wrapper branch. |

The categories are deliberately independent of the aggregate percentage. In
particular, M8/M9 historical orchestration has low execution coverage because
the default suite preserves the external-fixture gate and immutable evidence;
this is a risk to manage with an isolated seam, not permission to rerun history.

## Artifact inventory, side effects, and known gaps

- `artifacts/coverage.data` — raw coverage.py data for the measured suite,
  SHA-256 `18a5acb46486107fdc790222462dee5cad5913652c9cc6b9af6fc07178438f23`.
- `artifacts/coverage.json` — pretty-printed machine-readable line and branch
  details, SHA-256 `7f4c86de8fe360a8597f04e566d0deb2d8594b973f94e3d18cc2b035ec83a9c3`.
- `verification.json` — machine-readable run identity, commands, metrics, map,
  and zero-side-effect declaration.
- `checksums.sha256` — ledger for every run-record artifact except itself.

No emulator, device, Android build/install, model or oracle call, formal
consumer, namespace claim, mapping release, external fixture admission, manual
step, historical evidence mutation, new cohort, or formal population was
performed. The known gap is intentional: this one local, default-suite baseline
does not measure the explicitly gated external historical fixture or establish
behavior-layer effectiveness. The nine P0 and three P1 entries above are the
deduplicated follow-up backlog; none is implemented by this issue.
