# M2-beta Oversized Saved-State Quarantine

Primary seed issue: #23
M2-beta accounting issue: #27
Parent PRD: #24

## Status

`wikipedia-process-death-03-oversized-saved-state` is quarantined from the
M2-beta benchmark slice.

This does not close #23. The seed remains implemented and can still become
M2-beta evidence later, but only after a valid baseline/defect matched pair is
captured on a stable emulator or real device.

As of 2026-07-09, the live validation gates have been added and both required
pre-seed gates pass on `emulator-5554`:

- generic Android environment gate:
  `docs/runs/2026-07-09-live-validation-gate-current-environment/README.md`;
- Wikipedia app-level smoke gate:
  `docs/runs/2026-07-09-wikipedia-app-smoke-gate/README.md`.

These gates unblock a future #23 matched-pair retry, but they are not seed
outcomes and do not change M2-beta accounting by themselves.

For the current M2-beta aggregate:

- accounting state: `candidate` and `blocked`;
- injected-defect denominator impact: `0`;
- caught/missed outcome: none;
- baseline-control outcome: none;
- false-positive outcome: none.

## Evidence Used

Committed seed artifacts already exist:

- run specification;
- human-readable seed specification;
- injected patch;
- L1 crash fixture;
- regression test.

The latest live retry evidence is:

- `docs/runs/2026-07-09-wikipedia-process-death-03-oversized-saved-state-live-retry/README.md`
- #23 progress comment linking the same committed run record.

That retry did not produce valid benchmark evidence:

- baseline build and install succeeded;
- `am start -W` returned `Status: ok`;
- the app task closed before `nav_tab_search`;
- logcat included failed attach / start timeout / ANR signals;
- Android CLI layout / UIAutomator remained unstable after emulator refresh;
- no defect lane was run.

The later live validation gate evidence is:

- `docs/runs/2026-07-09-live-validation-gate-current-environment/README.md`
  - generic gate passed: adb device, boot completion, boot animation,
    Android CLI layout JSON, and direct UIAutomator dump;
- `docs/runs/2026-07-09-wikipedia-app-smoke-gate/README.md`
  - app-level smoke passed: explicit Wikipedia launch, foreground package, and
    `nav_tab_search` / `Search` target surface.

This changes the next-action state from "environment not proven" to "ready for
seed-specific matched-pair retry." It does not backfill a baseline verdict,
defect verdict, or matched pair for #23.

## Inclusion-Rule Application

The M2-beta inclusion rules require a valid baseline/defect matched pair before
an injected-defect seed can count as `caught` or `missed`.

#23 does not currently satisfy that rule because:

1. the baseline/control lane did not reach the target UI surface;
2. there is no valid baseline verdict;
3. there is no defect lane;
4. there is no matched pair under the same scenario and boundary.

Therefore the seed is excluded from M2-beta numerator and denominator counts.
It should appear in aggregate reporting only as a quarantined candidate/blocked
seed.

## Criteria To Reconsider Inclusion

Future work may move #23 from quarantined candidate to included seed only if it
produces durable evidence with all of the following:

1. a passing generic live validation gate is linked from the issue evidence;
2. a passing Wikipedia app-level smoke gate is linked from the issue evidence;
3. baseline/control build installs and reaches the target SearchActivity
   surface;
4. baseline/control run captures an interpretable oracle result;
5. defect build runs the same scenario and boundary;
6. defect run captures an interpretable L1/L2/L3 oracle result;
7. both halves are linked from a durable run record and GitHub issue evidence;
8. the matched pair satisfies `docs/M2-beta-inclusion-rules.md`.

Until then, #23 must remain outside M2-beta caught/missed accounting.

## Known Gap

This quarantine decision is an accounting decision, not a defect-design
rejection. It preserves #23 for future execution work while keeping M2-beta
aggregate reporting auditable.
