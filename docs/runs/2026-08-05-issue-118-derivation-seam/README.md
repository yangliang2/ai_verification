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
uv run --with pytest --with jsonschema --with pyyaml pytest tests/discovery -q
........................................                                 [100%]
```

The discovery test suite passed, including deterministic custom-strategy
Change/Project lifecycle, prior/operator rejection, campaign round trips,
ledger tamper checks, and the existing temporal derivation tests.

```text
uv run --with pytest --with jsonschema --with pyyaml pytest -o addopts='' -ra -q
770 passed in 24.47s

uv build
Successfully built dist/aiverify-0.1.0.tar.gz
Successfully built dist/aiverify-0.1.0-py3-none-any.whl
```

The implementation also preserves the repository's full test contract; the
root agent should rerun the full suite after dependent M8 changes are merged.

## Evidence boundary

The strategy callable receives only target, `QualityContextGraph`, target mode,
and optional Change Mode `BehaviorDelta`/`ContractDrift`. Selection rejects
unsupported prior IDs, operator IDs, target modes, mismatched output identity,
and incomplete accepted results before campaign admission or Run Spec
compilation. Strategy identity/version and selected prior ID are retained in
the campaign and selection ledger. No Finding or runtime capability claim is
made by this issue.
