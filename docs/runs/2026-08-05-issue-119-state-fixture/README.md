# Issue #119 — state-evolution fixture/context/oracle slice

This run record covers the bounded implementation delivered for issue #119.
It establishes a neutral, provenance-bound state-evolution contract and
discovery graph, an injectable local recovery adapter, and a fail-closed state
oracle. The adapter's event seam is bound to the existing
`SystemEventSpec`/`DeviceSystemEventInjector` path for the local smoke below.
It does not select a Risk Prior, compile a Campaign, or execute formal M8
lanes; those boundaries belong to #118, #120, #121, and #122.

## Implementation

- `src/aiverify/bench/state_evolution.py` contains the strict contract models,
  target-bound context loader, checksum verification, runtime phases/evidence
  checks, exactly-once migration receipt gate, and state outcome oracle.
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
  source/build members, deterministic recipe, independently checked protocol
  identity, variant identities, and a one-hunk localized ChangeTarget diff for
  audit admission only.
- `tests/bench/test_state_evolution.py` covers both target modes, schema and
  provenance round trips, known/unknown/contradictory context, adapter leakage
  checks, correct/stale/reset classifications, crash/evidence failures,
  migration/event identity validation, tamper rejection, and migration-boundary
  validation.

## Verification

Commands were run from the clean worktree `/Users/peter/projects/ai_verification-m8-119`
on branch `m8-119-state-fixture`, rebased onto `origin/main` commit
`fc0b0cdc199f9fa51ae4a3db73d4566f3e3d5587`:

```text
uv run --with ruff ruff check src/aiverify/bench/state_evolution.py tests/bench/test_state_evolution.py tests/bench/test_m6_cohort.py
→ All checks passed!

uv run --with pytest --with jsonschema --with pyyaml pytest -o addopts='' -q tests/bench/test_state_evolution.py
→ 19 passed in 0.22s

uv run --with pytest --with jsonschema --with pyyaml pytest -o addopts='' -q tests/discovery tests/bench/test_lifecycle_recovery.py tests/bench/test_m7_runtime_probe.py tests/bench/test_m6_cohort.py
→ 82 passed in 4.83s

uv run --with pytest --with jsonschema --with pyyaml pytest -o addopts='' -ra -q
→ 793 passed in 23.11s

/usr/bin/time -p uv build
→ Successfully built dist/aiverify-0.1.0.tar.gz
→ Successfully built dist/aiverify-0.1.0-py3-none-any.whl
→ real 0.80s, user 0.52s, sys 0.20s

uv run --with jsonschema --with pyyaml python - <<'PY'
from pathlib import Path
from jsonschema import Draft202012Validator
from aiverify.bench.state_evolution import (
    load_state_evolution_contract, load_state_evolution_schema,
    verify_state_evolution_matched_pair, verify_state_evolution_provenance,
)
root = Path("bench/discovery-fixtures/state-evolution")
schema = load_state_evolution_schema()
Draft202012Validator.check_schema(schema)
contract = load_state_evolution_contract(root / "contract.json")
assert not list(Draft202012Validator(schema).iter_errors(contract.to_dict()))
receipt = verify_state_evolution_provenance(root / "contract.json")
matched = verify_state_evolution_matched_pair(
    root / "auditor/matched-pair.json", repo_root=Path(".")
)
assert receipt.valid
assert matched.valid
print(
    f"schema_valid=True contract_valid=True provenance_valid=True "
    f"provenance_checks={len(receipt.checks)} matched_pair_valid=True "
    f"matched_pair_checks={len(matched.checks)}"
)
PY
→ schema_valid=True contract_valid=True provenance_valid=True provenance_checks=5 matched_pair_valid=True matched_pair_checks=15
→ real 0.13s, user 0.09s, sys 0.01s
```

### Local Android smoke (non-qualification)

The checked-in lifecycle fixture was built and exercised once on the controlled
`emulator-5554` (API 35). The adapter event binding drove rotation, a real
background process death/relaunch, and local-transport backup/clear/restore;
all three system-event receipts passed and the checkpoints showed v1 before
restore and v2/42 after restore. The public runner nevertheless finalized as
`non_accountable` (`execution_identity_error` / host identity drift), so this
run is retained as an adverse/inconclusive adapter smoke and creates no Finding
or qualification claim.

```text
bench/fixtures/lifecycle-recovery-app/gradlew -p bench/fixtures/lifecycle-recovery-app :app:assembleDebug --no-daemon
→ BUILD SUCCESSFUL; real 2.33s; APK SHA-256 07d72302bc192172dfc72eb8c18746aefe2aafdae6e6068b3ee8d3aeec21d94f

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m aiverify.runner bench/capability-slices/lifecycle-recovery/run-specs/baseline.yaml --device emulator-5554 --artifact-dir /tmp/aiverify-m8-119-baseline.7m9MEg/artifacts
→ 231.123s; rotate/process_death/backup_restore receipts passed; terminal execution non_accountable (execution_identity_error)
```

The durable inventory is under
`artifacts/android-smoke/runner/` (four state checkpoints, three system-event
receipts, screenshots/layouts/logcats, journey receipts, live-validation gate,
execution record, and verdict) plus `smoke-result.json`. Cleanup restored the
previous backup transport/enablement and cleared the fixture data. No
production data, external project state, or network policy was touched.

The adapter remains side-effect-free unless a runner is injected. Accountable
state classification additionally requires an explicit contract-bound
migration receipt (`count=1`, matching edge/schema/revision, `exactly_once=true`)
and explicit `process_death`/`backup_restore` event identities.

Toolchain for these runs: `uv 0.11.7`, `Python 3.11.15`, `pytest 9.1.1`,
`ruff 0.16.1`, `jsonschema 4.26.0`, and `PyYAML 6.0.3`.

Build artifact inventory: the durable run record stores
`artifacts/aiverify-0.1.0-py3-none-any.whl` (269,534 bytes, SHA-256
`fd49e0e3e5e96156223e2694569014c2bf458ef91220e8add38eed061c057031`). The
wheel contains `aiverify/bench/state_evolution.py` and
`aiverify/bench/state_evolution_schema.json`; the source distribution was
validated at build time but is not retained in the run record.

The durable checksum is generated and verified from the repository root:

```text
run_dir=docs/runs/2026-08-05-issue-119-state-fixture
(find "$run_dir" -type f ! -name checksums.sha256 -print0 | sort -z | xargs -0 shasum -a 256 > "$run_dir/checksums.sha256")
(shasum -a 256 -c "$run_dir/checksums.sha256")
→ all listed artifacts OK
```

## Claim boundary and known gaps

The result supports only the checked-in fixture's local durable-state
continuity contract, bounded recovery evidence shape, and the explicitly
non-accountable local smoke. It does not
claim persistence-framework coverage, production-data safety, cloud/multi-
device restore, downgrade/concurrent migration behavior, Android/OEM coverage,
or detection/false-positive rates. Runtime process/APK/transport identity is
explicitly unknown in the static context and must be bound before an accountable
Finding can be produced. The source pair, lane mapping, Risk Prior, and formal
qualification remain for the dependent M8 issues.

The oracle treats a missing/partial or unclassified state observation as
inconclusive unless a separate complete loss receipt explicitly confirms the
loss boundary; it does
not infer state loss from absent fields alone. A crash flag cannot override
missing or contradictory state. Package/activity, epoch, process identity,
backup transport, cleanup transport, and migration edge/count must match the
contract.

## Artifact checksums

The run record itself is checksum-bound by `checksums.sha256`; it covers every
durable file under this run directory except the checksum file itself. The
README and committed wheel are included anchors, and the complete artifact
inventory is machine-verifiable from the checksum list.

```text
7cfeb257d0e887429fad4c664f304ecbb8d97e903246f078a7848774823f463c  src/aiverify/bench/state_evolution.py
47812952d96b5914cfaf705186a861e850620f1914b84a3ec58b66e330ceaebe  src/aiverify/bench/state_evolution_schema.json
c49608614543e2c7136a7a5254e114c333a0971d7aedb51d68537add2589b7e2  bench/discovery-fixtures/state-evolution/contract.json
367b5b2710dab2ba08cc8cf263445c33a69b198ea46e9e87dc8e55f9f4e0c11c  bench/discovery-fixtures/state-evolution/context-manifest.json
4aaba044d909aff658523993e2b6b353df0468527c4e87f8ee03a963ffca6426  bench/discovery-fixtures/state-evolution/protocol.json
085e8df678f789b7ff22f8e742af96f46353f378ff1cad77c534df1d0b463649  bench/discovery-fixtures/state-evolution/auditor/build-recipe.json
7f8717629739acf0a6762af9bbed55f676ccaa5f2cb868257a83522cdecfa626  bench/discovery-fixtures/state-evolution/auditor/matched-pair.json
97ebb4155eb0f91e2bc6e55ce609f992eef013d5bf47de9a047341dc9982ee50  bench/capability-slices/state-evolution/adapter.json
74c3553d7b488f05fab19431755aaa8560d6ae884eeebc155b1564415a8d2988  tests/bench/test_state_evolution.py
fd49e0e3e5e96156223e2694569014c2bf458ef91220e8add38eed061c057031  docs/runs/2026-08-05-issue-119-state-fixture/artifacts/aiverify-0.1.0-py3-none-any.whl
```
