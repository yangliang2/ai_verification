# M8 / #120 state-evolution derivation

Date: 2026-08-05<br>
Baseline: `origin/main` at `8b80e6e07a51d72783cac410e813b3b144d1e4f1`<br>
Working branch: `m8-120-state-derivation`<br>
Implementation revision: `8d8c201` (implementation plus hardening; evidence artifacts rebuilt)

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
  path, transition, and binding rejection coverage.

Commands were run from the clean worktree
`/Users/peter/projects/ai_verification-m8-120`.

| Check | Exact command | Result |
| --- | --- | --- |
| Targeted | `/usr/bin/time -p uv run --with pytest pytest tests/discovery/test_state_evolution_risk.py -q` | 10 passed; real 0.49 s |
| Scoped | `uv run --with pytest pytest tests/discovery tests/bench/test_state_evolution.py tests/bench/test_lifecycle_recovery.py tests/bench/test_m7_runtime_probe.py tests/bench/test_m6_cohort.py -rA` | 111 passed in 4.67 s |
| Full suite | `/usr/bin/time -p uv run --with pytest pytest -rA` | 803 passed in 23.53 s; wall real 24.12 s |
| Lint (changed surface) | `uv run --with ruff ruff check src/aiverify/discovery/state_evolution_risk.py src/aiverify/discovery/__init__.py tests/discovery/test_state_evolution_risk.py` | All checks passed |
| Bytecode | `/usr/bin/time -p uv run python -m compileall -q src tests` | Exit 0; real 0.10 s |
| Contract/schema/replay seam | `uv run python - <<'PY' ...` (loads the state context, derives both modes through `derive_with_strategy`, validates all four contracts, round-trips them, checks 4 leakage terms, and asserts no Finding) | `schema_valid=true`, project/change accepted, deterministic IDs, `finding_count=0`, `leakage_checks=4`; real 0.35 s |
| Package | `/usr/bin/time -p uv build --out-dir /tmp/aiverify-m8-120-dist.Dj1Tgh` | Source and wheel built successfully; real 2.72 s |

The package identity was `aiverify` version `0.1.0`. The wheel is 275,880
bytes and the source archive is 247,043 bytes. Durable artifacts and SHA-256
digests are in [`artifacts/checksums.sha256`](artifacts/checksums.sha256).

## Artifact inventory

- [`artifacts/aiverify-0.1.0-py3-none-any.whl`](artifacts/aiverify-0.1.0-py3-none-any.whl)
- [`artifacts/aiverify-0.1.0.tar.gz`](artifacts/aiverify-0.1.0.tar.gz)
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
