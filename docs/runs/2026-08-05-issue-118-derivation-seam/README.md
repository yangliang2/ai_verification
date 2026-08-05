# Issue #118 — Risk derivation seam

This run records the side-effect-free verification of the generalized campaign
risk-derivation seam. It does not execute an Android build, emulator, device,
or external project.

## Source

- Branch: `m8-118-derivation-seam`
- Base: `origin/main` at `ddea496`
- Scope: explicit, versioned `RiskDerivationStrategy` selection while keeping
  the M7 temporal strategy as the compatibility default.

## Verification

```text
/usr/bin/time -p uv run --with pytest --with jsonschema --with pyyaml pytest tests/discovery -q
42 passed; real 2.87s, user 0.57s, sys 0.16s
```

The discovery test suite passed, including deterministic custom-strategy
Change/Project lifecycle, prior/operator rejection, campaign round trips,
ledger tamper checks, and the existing temporal derivation tests.

```text
/usr/bin/time -p uv run --with pytest --with jsonschema --with pyyaml pytest -o addopts='' -ra -q
772 passed in 22.18s; real 22.75s, user 18.00s, sys 3.89s

/usr/bin/time -p uv build
Successfully built dist/aiverify-0.1.0.tar.gz
Successfully built dist/aiverify-0.1.0-py3-none-any.whl
real 0.73s, user 0.51s, sys 0.20s
```

Tool versions: `uv 0.11.7`, CPython `3.11.15`, pytest `9.1.1`, jsonschema
`4.26.0`, and PyYAML `6.0.3`. `uv run python -m compileall -q src tests`,
`git diff --check`, and
`uv run --with ruff ruff check src/aiverify/discovery/risk.py
src/aiverify/discovery/campaign.py src/aiverify/discovery/contracts.py
src/aiverify/discovery/schema.py src/aiverify/discovery/__init__.py
tests/discovery/test_campaign.py --select F,E9` all passed.

## Artifact inventory and checksums

The committed source, schema, tests, ADR, and this run record are the durable
implementation artifacts. Package artifacts produced by the build were:

| Artifact | SHA-256 |
| --- | --- |
| `dist/aiverify-0.1.0.tar.gz` | `594371db7d839cf1fcae948735e7245e097d27f393604c4daca382b6307b3d7a` |
| `dist/aiverify-0.1.0-py3-none-any.whl` | `e4d91fe7d7444eb122150139b8e27524f453c2bcccb370ba00f37b6092c16de2` |

The `dist/` directory is a local build output and is not claimed as a
committed evidence artifact; the checksums above identify exactly what the
reported package build produced.

## Manual checks and known gaps

Manual/device steps: none. No APK was built or installed, no emulator or adb
was touched, and no external project or production data was accessed.

Known gap: this issue verifies the pure derivation and campaign seam only. It
does not qualify the M8 state-evolution strategy, prove runtime behavior, or
provide detection/completeness/general Android claims. The full suite must be
rerun after dependent #119–#122 changes are merged.

## Evidence boundary

The strategy callable receives only target, `QualityContextGraph`, target mode,
and optional Change Mode `BehaviorDelta`/`ContractDrift`. Selection rejects
unsupported prior IDs, operator IDs, target modes, mismatched output identity,
and incomplete accepted results before campaign admission or Run Spec
compilation. Strategy identity/version and selected prior ID are retained in
the campaign and selection ledger. No Finding or runtime capability claim is
made by this issue.
