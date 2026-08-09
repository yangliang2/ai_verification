# Issue #158 — pre-runtime formal hardening

Status: implementation and regression verification complete in the isolated
`issue-158-pre-runtime-reconciliation` worktree.  This change is future-only;
it does not retry, repair, reinterpret, or rewrite the exhausted M9-R4 #154
packet or the #137 result.

## Implementation

- `src/aiverify/bench/m9_recovery_formal.py`
  - Adds a side-effect-free target-specific Context Acquisition → Hypothesis
    Portfolio → Attack Plan admission preclaim before the formal namespace is
    claimed.
  - Persists and verifies a checksum-bound preclaim receipt through formal
    start, then consumes the exact in-memory products without a second
    discovery/planning pass.
  - Gives terminal pre-runtime rows minimal absence evidence that binds the
    canonical `ExecutionRecord` path and SHA-256, while keeping them
    non-accountable.  The receipt is named `terminal_absence_receipt`; it is
    deliberately separate from glossary-defined `Attempt Evidence`.
  - Separates runtime reach from formal-attempt reconciliation in execution
    summaries.
- `src/aiverify/bench/m9_recovery_qualification.py`
  - Makes reconciliation expose `formal_attempt_reconciled` and
    `runtime_holdout_executed`; the compatibility `formal_holdout_executed`
    field now reflects runtime reach.
  - Computes the inventory-to-row binding from the terminal row's canonical
    record reference.
- Regression coverage includes exact plan mismatch ordering, preclaim receipt
  tampering, six pre-runtime terminal rows, exhaustive inventory binding, zero
  retry/replacement/rerun, honest runtime flags, and historical R5 checksum
  protection.

## Verification

Base revision: `3ef1f7d5125aae672b430e0d14ff945ddfb00b56` (tree
`8e3b4503b7960e7d7bf848f7061c8dad5d6b322f`).

Tool: `uv 0.11.7 (9d177269e 2026-04-15 aarch64-apple-darwin)`.

Commands and results:

```text
uv run --extra dev python -m compileall -q src tests
PASS (exit 0)

git diff --check
PASS (exit 0)

/usr/bin/time -p uv run --extra dev python -m pytest tests/bench/test_m9_recovery_formal.py tests/bench/test_m9_recovery_qualification.py
98 passed in 18.22s; real 18.38s; user 7.71s; sys 10.40s

/usr/bin/time -p uv run --extra dev python -m pytest
1017 passed in 52.30s; real 52.51s; user 31.97s; sys 17.01s

/usr/bin/time -p uv run --extra dev python -m pytest -q
1017 passed; exit 0; real 63.27s; user 38.72s; sys 20.32s

/usr/bin/time -p uv run --extra dev python -m pytest -q
1017 passed; exit 0; real 73.53s; user 39.90s; sys 22.04s
```

The final-HEAD smoke runs reached 100%; a separate collection check reported
1017 tests.  The latest run includes the post-review receipt terminology fix.

The frozen-target regression confirms the exact #154 target-specific Attack
Plan mismatch is rejected before a formal root is created.  The full suite
also verifies the historical #157 reconciliation and interpretation artifacts
remain checksum-bound.

## Manual and external verification

No manual UI, emulator, physical-device, Android build/install, model, runtime,
oracle, or review invocation was performed.  Those effects are explicitly out
of scope for #158 and the preclaim contract reports zero counters for them.

No R3/R4 evidence files were changed.  The original dirty user worktree was
left untouched; this record was produced in the isolated implementation
worktree.

## Artifact inventory and gaps

- `README.md` — this durable run record.
- `verification.json` — machine-readable command/result inventory and scope
  boundaries.
- `checksums.sha256` — checksum ledger for this run record.
- Screenshots, layouts, logcat, APKs, device logs, model receipts, and runtime
  reports: none (not applicable; no external execution was authorized).

A successful preclaim against a future admitted Attack Plan is covered by pure
unit fixtures; the frozen #154 target intentionally remains a rejection case.
No merge, release, or issue close is implied by this local run record.
