# 2026-07-12 Deterministic L2 boundary validation

Issue: #38

## Scope

This host-only validation covers deterministic L2 state-evidence selection for
multiple Journey Segment Boundaries. Run Specs may select a zero-based
`l2_boundary_index`, evaluated in `step_index` execution order. Multi-boundary
scenarios without a selection return L2 inconclusive; single-boundary and
event-less scenarios retain their existing semantics.

## Verification Commands And Results

```bash
git diff --check
```

Result: exit `0`.

```bash
.venv/bin/python -m compileall -q src
```

Result: exit `0`.

```bash
.venv/bin/pytest tests/runner/test_run_spec.py tests/runner/test_cli.py tests/runner/test_journey.py -q
```

Result: exit `0`; `41 passed`.

```bash
.venv/bin/pytest -q
```

Result: exit `0`; `311 passed`.

```bash
.venv/bin/pytest --collect-only
```

Result: exit `0`; `311 tests collected`.

## Environment

- Python: `3.11.15`
- pytest: `9.0.3`
- Android device/emulator: not used

## Implementation And Test Inventory

- Run Spec parsing normalizes system events by numeric `step_index` and validates
  the optional boundary selection.
- L2 compares only the selected before/after checkpoint pair.
- Missing selection in a multi-boundary scenario returns an explained L2
  inconclusive verdict instead of silently selecting a checkpoint.
- Tests cover explicit selection, reverse YAML order, boundary index 10,
  ambiguity, single-boundary compatibility, and event-less compatibility.

## Artifact Inventory

- `README.md` — this validation record.

No screenshots, layouts, APKs, logcat dumps, or generated external artifacts
were produced. Checksums are not applicable because this record contains no
external/binary evidence artifact.

## Known Gaps

- No Android device/emulator run was needed or performed; this issue changes the
  host-side Run Spec and L2 checkpoint-selection contract.
- Runner-enforced live-validation preflight is deferred to #37.
- Evidence-derived M2-beta aggregation is deferred to #39.
