# 2026-07-12 Journey non-accountable execution validation

Issue: #36

## Scope

This host-only validation covers the Verification Agent runner's execution
accounting contract. A failed, skipped, incomplete, or interrupted Journey now
creates a durable non-accountable result with diagnostic artifact references;
it does not invoke L1/L2/L3 or create a caught/missed/control outcome.

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
.venv/bin/pytest tests/runner/test_journey.py tests/runner/test_cli.py tests/runner/test_codex_backend.py -q
```

Result: exit `0`; `29 passed`.

```bash
.venv/bin/pytest -q
```

Result: exit `0`; progress completed at `100%`.
The collection check below recorded `302` tests; all `302` passed.

```bash
.venv/bin/pytest --collect-only
```

Result: exit `0`; `302 tests collected`.

## Environment

- Python: `3.11.15`
- pytest: `9.0.3`
- Android device/emulator: not used

## Implementation And Test Inventory

- Journey orchestration now stops before a later boundary when an action is
  failed, skipped, incomplete, duplicated, reordered, or mismatched.
- Interrupted backend, checkpoint, and system-event execution retain completed
  flow state and failed phase timing.
- Codex backend errors retain references to emitted result/event artifacts.
- Runner verdicts include an outer `execution` result, explicit accounting
  eligibility, and diagnostic artifact references for non-accountable runs.
- Tests cover passed, failed, skipped, incomplete, mismatched, multi-segment,
  backend, checkpoint, and system-event paths using fake seams only.

## Artifact Inventory

- `README.md` — this validation record.

No screenshots, Android layouts, APKs, logcat dumps, or generated external
artifacts were produced. Checksums are not applicable because this run record
contains no external/binary evidence artifact.

## Known Gaps

- No real-device/emulator run was needed or performed; this issue changes the
  runner's host-side accounting and diagnostic contract.
- Runner-enforced live-validation preflight is intentionally deferred to #37.
- Evidence-derived M2-beta aggregation is intentionally deferred to #39.
