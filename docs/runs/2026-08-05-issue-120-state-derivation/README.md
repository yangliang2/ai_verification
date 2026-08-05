# M8 / #120 state-evolution derivation

Date: 2026-08-05<br>
Baseline: `origin/main` at `8b80e6e07a51d72783cac410e813b3b144d1e4f1`<br>
Working branch: `m8-120-state-derivation`<br>
Implementation revision: `db535e6` (implementation plus hardening; evidence artifacts rebuilt)

## Scope and result

This run records the static, fixture-neutral state-evolution discovery slice
for #120. It adds one versioned Risk Prior, one bounded historical-state replay
Attack Operator, and one derivation strategy shared by `ChangeTarget` and
`ProjectTarget`.

The strategy accepts only a provenance-bound, known, synchronous path through
writer, durable storage, legacy schema, schema transition, current reader,
recovery boundary, and a known Quality Contract. Change Mode binds a matching
`BehaviorDelta` and `ContractDrift`; Project Mode rejects both and invents no
diff. Missing, unknown, contradictory, stale, malformed, disconnected, or
mismatched history rejects deterministically. A static runtime-identity
unknown remains explicit uncertainty in an accepted hypothesis. No Finding or
runtime qualification is produced by this slice.

## Implementation and tests

- `src/aiverify/discovery/state_evolution_risk.py` — prior, operator, strategy,
  graph/path admission, deterministic contracts, and fail-closed reasons.
- `src/aiverify/discovery/__init__.py` — public exports.
- `src/aiverify/discovery/campaign.py` — state continuity quality-contract
  extraction when a campaign is seeded from the state graph.
- `tests/discovery/test_state_evolution_risk.py` — Change/Project parity,
  strategy seam, deterministic identity, round-trip/tamper, leakage, status,
  path, transition monotonicity, and binding rejection coverage.

Commands were run from the clean worktree
`/Users/peter/projects/ai_verification-m8-120`.

| Check | Exact command | Result |
| --- | --- | --- |
| Targeted | `/usr/bin/time -p uv run --with pytest pytest tests/discovery/test_state_evolution_risk.py -q` | 10 passed; real 1.45 s |
| Scoped | `uv run --with pytest pytest tests/discovery tests/bench/test_state_evolution.py tests/bench/test_lifecycle_recovery.py tests/bench/test_m7_runtime_probe.py tests/bench/test_m6_cohort.py -rA` | 111 passed in 4.71 s |
| Full suite | `/usr/bin/time -p uv run --with pytest pytest -rA` | 803 passed in 22.65 s; real 25.53 s (user 18.49 s, sys 3.70 s) |
| Lint (changed surface) | `uv run --with ruff ruff check src/aiverify/discovery/state_evolution_risk.py src/aiverify/discovery/__init__.py tests/discovery/test_state_evolution_risk.py` | All checks passed |
| Bytecode | `/usr/bin/time -p uv run python -m compileall -q src tests` | Exit 0; real 0.04 s |
| Contract/schema/replay seam | `/usr/bin/time -p uv run python docs/runs/2026-08-05-issue-120-state-derivation/artifacts/contract_seam_check.py` | `schema_valid=true`, project/change accepted, deterministic IDs, `finding_count=0`, `leakage_checks=4`; real 0.35 s |
| Package | `/usr/bin/time -p uv build --out-dir /tmp/aiverify-m8-120-dist.TekLaT` | Source and wheel built successfully; real 0.79 s |

The package identity was `aiverify` version `0.1.0`. The wheel is 275,939
bytes and the source archive is 247,160 bytes. Durable artifacts and SHA-256
digests are in [`artifacts/checksums.sha256`](artifacts/checksums.sha256).

## Artifact inventory

- [`artifacts/aiverify-0.1.0-py3-none-any.whl`](artifacts/aiverify-0.1.0-py3-none-any.whl)
- [`artifacts/aiverify-0.1.0.tar.gz`](artifacts/aiverify-0.1.0.tar.gz)
- [`artifacts/contract_seam_check.py`](artifacts/contract_seam_check.py)
- [`artifacts/checksums.sha256`](artifacts/checksums.sha256)

No Android package, emulator, screenshot, layout dump, logcat, or device
receipt was generated for #120: runtime execution is explicitly out of scope.

## Claim boundary and known gaps

This is a local, static, provenance-bound derivation claim for the checked-out
context graph and source revision only. It is not a production-project claim,
an execution result, a Finding, or a qualification result. Runtime process/APK
identity is intentionally unknown until a later admitted runtime slice; the
hypothesis preserves that uncertainty. No fixture variant, prescribed Journey,
expected outcome, or verdict is consumed by the prior, operator, hypothesis, or
attack plan.

The original dirty `issue-73-accessibility-slice` worktree and its experiment
files were not read, modified, cleaned, reset, or committed by this run.
