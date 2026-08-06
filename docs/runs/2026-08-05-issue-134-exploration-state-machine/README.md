# M9 #134 — Project Exploration State Machine

This run records the side-effect-free project exploration seam above the M9
Run Spec boundary. It initializes from the frozen top-three Hypothesis
Portfolio and provenance-bound Quality Context Graph, appends typed
hash-chained decisions and terminal outcomes, derives the Project Risk Map and
coverage frontier from recorded state, and replays the same event stream
deterministically. It preserves a supported Finding beside an explicit
non-accountable Residual Risk; it does not retry or replace either attempt.

The bounded receipt is a deterministic local fake-backend fixture. It is not a
production provider call, does not build or run an Android app, does not select
or reveal the M9 formal holdout, and does not claim qualification.

## Verification commands and results

Commands ran on 2026-08-05/06 in the dedicated clean worktree after syncing to
`origin/main` containing #135. Timings are `/usr/bin/time -p` values.

```text
uv run --with pytest pytest -q tests/discovery/test_exploration.py
→ 12 passed, 0 failed; real 1.10s, user 0.52s, sys 0.03s.

uv run --with pytest pytest --collect-only
→ 864 tests collected.

/usr/bin/time -p uv run --with pytest pytest -q
→ all 864 tests passed, 0 failed; real 63.13s, user 21.92s, sys 4.93s.

uv run --with pytest python -m compileall -q src tests
→ exit 0.

uv run --with pytest python -c 'from aiverify.discovery.schema import self_validate_schema; self_validate_schema(); print("schema self-validation passed")'
→ exit 0; schema self-validation passed.

git diff --check
→ exit 0.

/usr/bin/time -p uv build --quiet --out-dir docs/runs/2026-08-05-issue-134-exploration-state-machine/artifacts
→ package `aiverify 0.1.0`; wheel 370031 bytes, SHA-256
  `3ad429ef3c3044c52a564ad359daf5fc2dec63d92f3a94809e19d4163a9f06f4`;
  sdist 336425 bytes, SHA-256
  `31e503592d9f0083212a4d0ec04ccbbb770f8123a98ef4ad21d57f83ba86cd8d`;
  real 3.19s, user 0.59s, sys 0.22s.

PYTHONPATH=src uv run --with pytest python docs/runs/2026-08-05-issue-134-exploration-state-machine/validate_receipt.py
→ exit 0; status passed; source_contract_checks 4, event_chain_checks 10,
  state_replay_checks 2, package_artifact_checks 2, checksum_manifest_checks 7;
  formal_holdout_executed false; side_effects false. Output is committed in
  `validation-output.json`.

(cd docs/runs/2026-08-05-issue-134-exploration-state-machine && shasum -a 256 -c checksums.sha256)
→ all manifest entries OK; exit 0.
```

## Contract and bounded receipt

Implementation and tests are in:

- `src/aiverify/discovery/exploration.py`: immutable exploration campaign,
  typed events, hash-chain replay, ranked next probes, derived Project Risk
  Map, explicit stop reasons, and no-retry/no-replacement guards.
- `src/aiverify/discovery/discovery_schema.json` and
  `src/aiverify/discovery/schema.py`: checked-in event, stop, probe, and
  campaign contract definitions and contract map entries.
- `src/aiverify/discovery/__init__.py`: public discovery exports.
- `tests/discovery/test_exploration.py`: provenance binding, multi-hypothesis
  progression, deferred decisions, all stop reasons, budget boundaries,
  non-accountable residuals, falsification-review state, replay, and tamper
  rejection.

The receipt's single fake backend invocation is:

- backend: `fake-hypothesis-backend`;
- role: `verification-agent-hypothesis-generator-v1`;
- requested/effective model: `fixture-model-v1` / `fixture-model-v1`;
- invocation: `exploration-generator-1`;
- state: 10 hash-chained events, two terminal attempts (`supported` and
  `non_accountable`), one Finding, one Residual Risk, zero reviews, and six
  remaining budget units;
- evaluated stop: `terminal_finding` (the receipt intentionally leaves the
  state open, because stop evaluation is pure and no formal run is started);
- event-head digest:
  `7e719cbf89ac552d7062a342a13b3498789ad6155606281c5fb2d7455f17e92b`;
- state digest:
  `dff6775e1074dda244772f772b86329486489c1ffe804300c080fd49f42959e3`.

See `bounded-exploration-receipt.json` for the bounded scope and expected
state, and `validate_receipt.py` for deterministic reconstruction, schema
validation, replay, package inventory, and checksum checks.

## Artifact inventory and claim boundary

- `bounded-exploration-receipt.json`: fake-backend identity, side-effect flags,
  event sequence, state digests, outcome counts, and claim boundary.
- `validate_receipt.py`: deterministic fixture reconstruction and validator.
- `validation-output.json`: committed validator result.
- `tool-versions.txt`: host/tool/backend/model identity.
- `artifacts/aiverify-0.1.0-py3-none-any.whl`: 370031 bytes;
  SHA-256 `3ad429ef3c3044c52a564ad359daf5fc2dec63d92f3a94809e19d4163a9f06f4`.
- `artifacts/aiverify-0.1.0.tar.gz`: 336425 bytes;
  SHA-256 `31e503592d9f0083212a4d0ec04ccbbb770f8123a98ef4ad21d57f83ba86cd8d`.
- `checksums.sha256`: SHA-256 inventory for every committed run artifact.

No APK, screenshot, layout dump, logcat, emulator/device, production provider,
upstream project, formal M9 holdout, hidden mapping, ground truth, runtime
oracle, Falsification Review invocation, retry, replacement, or external side
effect was used. The result supports only this exact checked-in,
side-effect-free exploration contract and local fake receipt. It does not
support M9 qualification, provider/model diversity, discovery effectiveness,
project completeness, benchmark rates, Android/OEM/ColorOS coverage, or any
production behavior claim.
