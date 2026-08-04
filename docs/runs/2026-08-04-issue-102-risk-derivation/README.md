# M7-3 synchronous-critical-path risk derivation

Date: 2026-08-04

Issue: [#102](https://github.com/yangliang2/ai_verification/issues/102)

Base under test: `origin/main` at `e36ac08f757dfa45bfbc51ba1756b7fe9345f82c`
(M7-2 PR #107 merge)

Scope: one bounded, deterministic Risk Prior and Attack Operator for temporal
propagation across a synchronous critical path. The slice freezes hypotheses and
plans but never emits a Finding or executes an Android attack.

## Verification commands and results

Commands ran from `/Users/peter/projects/ai_verification-m7-102`:

```text
/Users/peter/projects/ai_verfication/.venv/bin/python -m pytest -o addopts='' -q \
  tests/discovery/test_risk_derivation.py \
  tests/discovery/test_contracts.py \
  tests/discovery/test_context_graph.py
32 passed in 0.30s

/Users/peter/projects/ai_verfication/.venv/bin/python -m pytest -o addopts='' -q
748 passed in 21.35s

PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python - <<'PY'
from aiverify.discovery import self_validate_schema
self_validate_schema()
print('schema self-validation: pass')
PY
schema self-validation: pass

PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python - <<'PY'
from aiverify.discovery import validate_contract
validate_contract({"schema_version": 1, "chain_id": "legacy", "steps": ["a"], "consequence": "b", "fact_ids": []}, "failure_chain")
print('legacy failure-chain schema: pass')
PY
legacy failure-chain schema: pass

git diff --check
pass
```

Relevant tool versions: `uv 0.11.7`, `git 2.50.1`, Python `3.11.15`, pytest
`9.0.3`, jsonschema `4.26.0`, and PyYAML `6.0.3`.

## Acceptance mapping

- `BehaviorDelta` keeps change-derived before/after inference separate from
  observed Context Facts; `ContractDrift` remains its own evidence-referenced
  relationship.
- `make_temporal_prior` matches bounded delay/latency/blocking/retry/I/O/lock/
  wait/availability signals without fixture identifiers.
- `derive_synchronous_risk` supports ChangeTarget and ProjectTarget. Project Mode
  starts from a critical synchronous dependency and needs no diff; Change Mode
  additionally binds BehaviorDelta and ContractDrift.
- `RiskHypothesis` is frozen, confidence/evidence bounded, and records required
  evidence, assumptions, causal mechanism, consequence, unknowns, and source
  facts. `FailureChain` records local behavior, propagation, caller constraint,
  and system-impact roles.
- `RiskPriority` exposes impact, propagation reach, context sensitivity,
  uncertainty, evidence gap, and estimated probe cost. Its deterministic score
  is explicitly an ordering aid, not a probability or conclusion.
- `AttackPlan` is frozen, binds the latency/availability perturbation,
  observations, oracle intent, abort boundary, local claim boundary, and target
  reference. Admission remains side-effect-free and no Finding is generated.
- Async paths, unknown caller context, contradictory facts, and irrelevant paths
  reject derivation rather than producing a high-confidence conclusion.

## Artifact inventory and checksums

The derivation consumes the neutral fixture committed by M7-2:

```text
a97585d1e7ba7ef620205b5c3ec6520a7dea05a35470aa6d045c371e172d1edf  synchronous-weather/README.md
0860238c85757352b9ce2347c37cab5310219234c50e35c92ef2ce561cc9da0d  synchronous-weather/SystemUiWeatherConsumer.kt
5cc6723879b6a3814c13a8aa6e176d55cd8e5e32f8d983dd925bb665ea277dc6  synchronous-weather/WeatherService.kt
b87b4f1a5b60c1a46d89becb483b66de26608c6f201f252b3117bdff1ce31395  synchronous-weather/build-metadata.json
135ba563187993afb40eb9afdf3e202f53ee59d495d7d24f23d50daa40d36c4b  synchronous-weather/context-manifest.json
```

## Known gaps and claim boundary

- No Kotlin compiler indexer, Android/Gradle build, device/emulator run, fault
  injection, LLM generation, or aggregate qualification was performed.
- The manifest's runtime thread/process observation is explicitly unknown; the
  resulting suggested probe is not promoted to evidence.
- The priority score is not a probability, detection rate, or Finding. Hypothesis
  and plan status are pre-execution `frozen`; only later evidence can produce a
  Finding.
- Claims are limited to this source/descriptor fixture and local contracts; no
  private SystemUI, weather-service, ColorOS, Android-wide, or upstream claim is
  made.
