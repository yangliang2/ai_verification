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
- `bench/discovery-fixtures/state-evolution/auditor/` records the matched
  source/build members, deterministic recipe, byte-equivalent protocol hash,
  variant identities, and ChangeTarget diff hash for audit admission only.
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
→ 9 passed in 0.10s

uv run --with pytest --with jsonschema --with pyyaml pytest -o addopts='' -q tests/discovery tests/bench/test_lifecycle_recovery.py tests/bench/test_m7_runtime_probe.py tests/bench/test_m6_cohort.py
→ 76 passed in 4.35s

uv run --with pytest --with jsonschema --with pyyaml pytest -o addopts='' -ra -q
→ 777 passed (duration recorded by the final full-suite run below)

uv build
→ Successfully built dist/aiverify-0.1.0-py3-none-any.whl

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

The durable checksum is generated and verified from the repository root:

```text
run_dir=docs/runs/2026-08-05-issue-119-state-fixture
(find "$run_dir" -type f ! -name checksums.sha256 -print0 | sort -z | xargs -0 shasum -a 256 > "$run_dir/checksums.sha256")
(shasum -a 256 -c "$run_dir/checksums.sha256")
→ all listed artifacts OK
```

## Claim boundary and known gaps

The result supports only the checked-in fixture's local durable-state
continuity contract and its bounded recovery evidence shape. It does not
claim persistence-framework coverage, production-data safety, cloud/multi-
device restore, downgrade/concurrent migration behavior, Android/OEM coverage,
or detection/false-positive rates. Runtime process/APK/transport identity is
explicitly unknown in the static context and must be bound before an accountable
Finding can be produced. The source pair, lane mapping, Risk Prior, and formal
qualification remain for the dependent M8 issues.

The oracle treats a missing/partial state observation as inconclusive unless a
separate complete loss receipt explicitly confirms the loss boundary; it does
not infer state loss from absent fields alone. Package/activity, epoch, process
identity, backup transport, and cleanup transport must match the contract.

## Artifact checksums

The run record itself is checksum-bound by `checksums.sha256` (one README
artifact, verified `OK`).

```text
7267d01ec88d431078f442c0c2b09dcc6f24e8800bf8147967cdc005044eb32e  src/aiverify/bench/state_evolution.py
910af073e8f6f4ffc6c671678c39e7ce0bd885ae7634c3a23ef965379ea18213  src/aiverify/bench/state_evolution_schema.json
c49608614543e2c7136a7a5254e114c333a0971d7aedb51d68537add2589b7e2  bench/discovery-fixtures/state-evolution/contract.json
367b5b2710dab2ba08cc8cf263445c33a69b198ea46e9e87dc8e55f9f4e0c11c  bench/discovery-fixtures/state-evolution/context-manifest.json
4aaba044d909aff658523993e2b6b353df0468527c4e87f8ee03a963ffca6426  bench/discovery-fixtures/state-evolution/protocol.json
085e8df678f789b7ff22f8e742af96f46353f378ff1cad77c534df1d0b463649  bench/discovery-fixtures/state-evolution/auditor/build-recipe.json
341497ecd02506ab1149d7f76ed02779c4464d70a154964d31861040ce87df71  bench/discovery-fixtures/state-evolution/auditor/matched-pair.json
97ebb4155eb0f91e2bc6e55ce609f992eef013d5bf47de9a047341dc9982ee50  bench/capability-slices/state-evolution/adapter.json
6aaca93294c00ec978034a976238ee69a59aa156964736c70cb5c3bfa0e6b9ea  tests/bench/test_state_evolution.py
277d70736222283fb3a309c82de5146ed6311bad6c61d4e558107d05c3b59c38  docs/runs/2026-08-05-issue-119-state-fixture/artifacts/aiverify-0.1.0-py3-none-any.whl
```
