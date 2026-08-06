# M9 #133 — Attack Plan synthesis and neutral compilation

Base: `origin/main` at `55ad2bdfa916a24a38387429f5a480ddfd24deba`
Worktree: `/Users/peter/projects/ai_verification-m9-133`
Branch: `m9-133-attack-plan`

This run records the bounded, side-effect-free Attack Planner contract. The
planner accepts only a ProjectTarget, provenance-bound context graph, frozen
source-grounded hypothesis, approved operator registry, validated build/
package/controllability receipts, budget, and frozen safety/claim boundaries.
It emits a strict proposal whose trigger, ordered actions, user intents,
system events, observations, evidence expectations, and oracle inputs retain
fact/operator lineage. Admission is fail-closed before build, device, agent,
or runtime effects. Only an admitted proposal compiles into a neutral
`ScenarioSpec`/`RunSpec`; outcome labels and expected behavior are omitted.

The bounded receipt is a local fake-backend invocation on a non-holdout fixture
target. It is not a production provider call and does not select, reveal, or
execute the M9 formal cohort.

## Verification commands and results

Commands ran on 2026-08-05. Timings are `/usr/bin/time -p` values.

```text
PYTHONPATH=src /usr/bin/time -p .venv/bin/pytest -q tests/discovery/test_attack_planning.py
→ 5 passed, 0 failed; real 0.31s, user 0.13s, sys 0.16s.

PYTHONPATH=src .venv/bin/pytest --collect-only -q | awk -F': ' '/: [0-9]+$/{s+=$2} END{print s+0}'
→ 845 collected tests.

PYTHONPATH=src /usr/bin/time -p .venv/bin/pytest -q
→ 845 passed, 0 failed; real 29.01s, user 20.62s, sys 4.84s.

PYTHONPATH=src .venv/bin/python -m compileall -q src tests
→ exit 0.

PYTHONPATH=src .venv/bin/python - <<'PY' ... self_validate_schema() ... PY
→ exit 0; discovery schema self-validation passed.

git diff --check
→ exit 0.

uv build --quiet --out-dir docs/runs/2026-08-05-issue-133-attack-plan/artifacts
→ package `aiverify 0.1.0`; wheel and sdist built successfully. Final sizes
  and SHA-256 values: wheel 349353 bytes, SHA-256
  `d6ed330bc61bbe9a1c382e5d8c57cf1830e58f42219689da14b9d3426a09fc49`;
  sdist 316872 bytes, SHA-256
  `2b72fec80709a30a601fe4af5f960481affff11d259bc4ebd3c172945b28fa17`.
  `/usr/bin/time -p`: real 0.76s, user 0.53s, sys 0.19s.

PYTHONPATH=src .venv/bin/python docs/runs/2026-08-05-issue-133-attack-plan/validate_receipt.py
→ exit 0; source/schema/receipt/package/checksum checks passed.

(cd docs/runs/2026-08-05-issue-133-attack-plan && shasum -a 256 -c checksums.sha256)
→ all manifest entries OK; exit 0.
```

## Bounded receipt and identities

See `bounded-synthesis-receipt.json`. The fake backend was invoked once with:

- backend: `fake-attack-planner`;
- role: `verification-agent-attack-planner-v1`;
- requested/effective model: `fixture-model-v1` / `fixture-model-v1`;
- invocation: `planner-invocation-1`;
- target: `project-attack` with no diff and no formal cohort information;
- result: admitted proposal, neutral compilation only, no external side effects.

The authoritative output digest, planner identity digest, and semantic
compilation digest are part of the committed receipt.

## Artifact inventory and claim boundary

- `bounded-synthesis-receipt.json`: fake planner identity, request/proposal
  lineage, output digest, admission, and side-effect receipt.
- `validate_receipt.py`: deterministic validator for source contracts, schema,
  receipt, package artifacts, and checksum inventory.
- `validation-output.json`: committed validator result.
- `tool-versions.txt`: host and tool identity.
- `artifacts/aiverify-0.1.0-py3-none-any.whl`: 349353 bytes;
  SHA-256 `d6ed330bc61bbe9a1c382e5d8c57cf1830e58f42219689da14b9d3426a09fc49`.
- `artifacts/aiverify-0.1.0.tar.gz`: 316872 bytes;
  SHA-256 `2b72fec80709a30a601fe4af5f960481affff11d259bc4ebd3c172945b28fa17`.
- `checksums.sha256`: SHA-256 inventory for the run record and package.

No APK, screenshot, layout dump, logcat, emulator/device, production provider,
upstream project, formal M9 holdout, hidden mapping, runtime verdict, retry, or
replacement was used. The result supports only the checked-in planner
contract, its deterministic admission/compiler seam, and this exact local
fake-backend receipt. It does not claim discovery effectiveness, project
completeness, benchmark rate, Android/OEM/ColorOS coverage, or production
behavior.
