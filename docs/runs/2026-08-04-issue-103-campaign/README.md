# M7-4 Discovery Campaign orchestration

Date: 2026-08-04

Issue: [#103](https://github.com/yangliang2/ai_verification/issues/103)

Base under test: `origin/main` at `e50576f923603e1507bf1920c7500011b3731dbf`
(M7-3 PR #108 merge)

Scope: one bounded, side-effect-free campaign loop shared by ChangeTarget and
ProjectTarget. The loop binds context expansion, freezes one temporal
hypothesis, admits one attack plan, compiles a validated Run Spec, and reduces
immutable attempt evidence into a Finding or Residual Risk.

## Verification commands and results

Commands ran from `/Users/peter/projects/ai_verification-m7-103`:

```text
/Users/peter/projects/ai_verfication/.venv/bin/python -m pytest -o addopts='' -q \
  tests/discovery/test_campaign.py \
  tests/discovery/test_risk_derivation.py \
  tests/discovery/test_contracts.py \
  tests/discovery/test_context_graph.py
38 passed in 0.45s

/Users/peter/projects/ai_verfication/.venv/bin/python -m pytest -o addopts='' -q
754 passed in 20.89s

PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python - <<'PY'
from aiverify.discovery import self_validate_schema
self_validate_schema()
print('schema self-validation: pass')
PY
schema self-validation: pass

/Users/peter/projects/ai_verfication/.venv/bin/python -m compileall -q src tests
compileall: pass

git diff --check
pass
```

Relevant tool versions: `uv 0.11.7`, `git 2.50.1`, Python `3.11.15`, pytest
`9.0.3`, `jsonschema 4.26.0`, and PyYAML `6.0.3`.

## Acceptance mapping

- `seed_change_campaign` and `seed_project_campaign` use the same bounded risk
  derivation, admission, Run Spec compiler, and evidence reducer. Project Mode
  has no diff input; Change Mode preserves `BehaviorDelta` and `ContractDrift`
  separately.
- `ContextExpansionRequest`/`ContextExpansionResult` record required facts,
  probes, budget, resolved facts, and unresolved questions. Target, graph, and
  budget mismatches fail closed.
- `HypothesisSelectionLedger` records considered/selected/deferred/rejected
  decisions as a deterministic hash chain. Resume verifies every entry and the
  head digest.
- `admit_campaign_plan` is side-effect-free and requires a frozen hypothesis,
  complete plan, known supporting facts, oracle, evidence expectations, abort
  boundary, and claim boundary. `compile_attack_plan_to_run_spec` calls the
  existing Run Spec parser only after admission, strips benchmark outcome labels
  from the emitted scenario, and performs no build/device action.
- `AttemptEvidence.from_execution` delegates to the existing
  `validate_execution_record` and `validate_verdict` contracts. An accountable
  terminal receipt requires evidence references and an execution-identity
  digest; a non-accountable receipt can only become Residual Risk.
- `reduce_attempt_evidence` appends immutable findings/residuals to a matching
  `ProjectRiskMap`; campaign/map relationship and target checks reject tamper.

## Artifact inventory and checksums

The campaign consumes the neutral M7-2 fixture committed in prior slices:

```text
9c7971f873b1539da60afa84d0bc477fe630bcfaf21e3c766323076041a8e05b  synchronous-weather/README.md
ebc51ee8363f2d4c23b924f0f6a6cde80459d529b726af0c413458a9cff27e91  synchronous-weather/SystemUiWeatherConsumer.kt
1f7d39c4deeb955476c93ec4045200abbaf0ed5dfe8b0b9dca2e9fd185c8f1a1  synchronous-weather/WeatherService.kt
b87b4f1a5b60c1a46d89becb483b66de26608c6f201f252b3117bdff1ce31395  synchronous-weather/build-metadata.json
135ba563187993afb40eb9afdf3e202f53ee59d495d7d24f23d50daa40d36c4b  synchronous-weather/context-manifest.json
```

The fixture is unchanged; the exact inventory is also preserved in the M7-3 record:
[`docs/runs/2026-08-04-issue-102-risk-derivation/README.md`](../2026-08-04-issue-102-risk-derivation/README.md).
No fixture contents were changed by this slice.

## Known gaps and claim boundary

- No Android/Kotlin/Gradle build, emulator/device run, fault injection, or
  external project action was performed. The compiled Run Spec is validated
  input only; execution remains the existing runner's responsibility.
- No aggregate qualification was performed; M7-5/#104 owns the frozen
  12-lane campaign and independent adjudication.
- Findings are permitted only from an accountable terminal ExecutionRecord and
  validated oracle evidence. All claims remain local to the committed source,
  context, Run Spec, execution identity, and evidence references; no upstream,
  OEM, Android-wide, or capability-rate claim is made.
