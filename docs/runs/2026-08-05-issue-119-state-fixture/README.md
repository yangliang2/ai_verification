# Issue #119 — state-evolution fixture/context/oracle slice

This run record covers the bounded implementation delivered for issue #119.
It establishes a neutral, provenance-bound state-evolution contract and
discovery graph, a side-effect-free local recovery adapter, and a fail-closed
state oracle. It does not select a Risk Prior, compile a Campaign, or execute
formal M8 lanes; those boundaries belong to #118, #120, #121, and #122.

## Implementation

- `src/aiverify/bench/state_evolution.py` contains the strict contract models,
  target-bound context loader, checksum verification, runtime phases/evidence
  checks, and state outcome oracle.
- `src/aiverify/bench/state_evolution_schema.json` is the checked-in strict
  Draft 2020-12 contract schema and is included in the wheel package data.
- `bench/discovery-fixtures/state-evolution/` contains the writer/storage/
  schema/migration/reader/recovery descriptors, neutral context graph, and
  invariant contract. Every source reference in the contract has a SHA-256
  receipt; the static graph keeps runtime identity explicitly unknown.
- `bench/capability-slices/state-evolution/adapter.json` binds package,
  activity, resource IDs, bounded event names, and local reversible safety
  policy without a variant, Journey, expected outcome, or verdict.
- `tests/bench/test_state_evolution.py` covers both target modes, schema and
  provenance round trips, known/unknown/contradictory context, adapter leakage
  checks, correct/stale/reset classifications, crash/evidence failures, and
  migration-boundary validation.

## Verification

Commands were run from the clean worktree `/Users/peter/projects/ai_verification-m8-119`
on branch `m8-119-state-fixture`, based on `origin/main` commit `ddea496`:

```text
uv run --with ruff ruff check src/aiverify/bench/state_evolution.py tests/bench/test_state_evolution.py tests/bench/test_m6_cohort.py
→ All checks passed!

uv run --with pytest --with jsonschema --with pyyaml pytest -o addopts='' -q tests/bench/test_state_evolution.py
→ 8 passed in 0.09s

uv run --with pytest --with jsonschema --with pyyaml pytest -o addopts='' -q tests/discovery tests/bench/test_lifecycle_recovery.py tests/bench/test_m7_runtime_probe.py tests/bench/test_m6_cohort.py
→ 76 passed in 4.35s

uv run --with pytest --with jsonschema --with pyyaml pytest -o addopts='' -ra -q
→ 776 passed in 23.25s

uv run --with jsonschema --with pyyaml python - <<'PY'
from pathlib import Path
from jsonschema import Draft202012Validator
from aiverify.bench.state_evolution import (
    load_state_evolution_contract, load_state_evolution_schema,
    verify_state_evolution_provenance,
)
root = Path("bench/discovery-fixtures/state-evolution")
schema = load_state_evolution_schema()
Draft202012Validator.check_schema(schema)
contract = load_state_evolution_contract(root / "contract.json")
assert not list(Draft202012Validator(schema).iter_errors(contract.to_dict()))
receipt = verify_state_evolution_provenance(root / "contract.json")
assert receipt.valid
print(f"schema_valid=True provenance_valid=True checks={len(receipt.checks)}")
PY
→ schema_valid=True provenance_valid=True checks=5
```

No emulator, APK install, backup/restore, process-death, network, or external
project state was touched in this issue. Those side effects require the later
admission and formal execution contracts.

## Claim boundary and known gaps

The result supports only the checked-in fixture's local durable-state
continuity contract and its bounded recovery evidence shape. It does not
claim persistence-framework coverage, production-data safety, cloud/multi-
device restore, downgrade/concurrent migration behavior, Android/OEM coverage,
or detection/false-positive rates. Runtime process/APK/transport identity is
explicitly unknown in the static context and must be bound before an accountable
Finding can be produced. The source pair, lane mapping, Risk Prior, and formal
qualification remain for the dependent M8 issues.

## Artifact checksums

The run record itself is checksum-bound by `checksums.sha256` (one README
artifact, verified `OK`).

```text
9f5283ca30e753d20a7f62c8ad895e8fda27939e65dd218cd3326f2021e876e8  src/aiverify/bench/state_evolution.py
8d6f8b2b24147e45bf4e125bae4f7a3ba233b6c8aedeaa38aa09b0baefcc0e90  src/aiverify/bench/state_evolution_schema.json
e9d9fbdf145656b8c44b914b1f3c468afcb018ec2d7ce6406bafa0fae990854d  bench/discovery-fixtures/state-evolution/contract.json
367b5b2710dab2ba08cc8cf263445c33a69b198ea46e9e87dc8e55f9f4e0c11c  bench/discovery-fixtures/state-evolution/context-manifest.json
04980c07e8ecc5b693261e0dac1ddec7cb6a10a69a3e940f16a55ba299243f0f  bench/capability-slices/state-evolution/adapter.json
0986fe7c2961a6b0204b31ff76f16f00790522b46662d50c33441f4dfb378cdb  tests/bench/test_state_evolution.py
```
