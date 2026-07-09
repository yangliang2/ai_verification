# M2-beta Oversized Saved-State Quarantine Resolution

Primary seed issue: #23
M2-beta accounting issue: #27
Parent PRD: #24

## Status

`wikipedia-process-death-03-oversized-saved-state` was previously quarantined
from the M2-beta benchmark slice because the first live retry did not produce a
valid baseline/defect matched pair.

As of 2026-07-09, that quarantine is resolved. The seed is now included in
M2-beta accounting:

- accounting state: `included`;
- injected-defect denominator impact: `1`;
- defect outcome: `caught`;
- baseline-control outcome: `passed_control`;
- expected oracle: `L1`;
- defect class: `crash_stability`.

## Historical Blocking Evidence

The earlier blocked retry remains useful historical evidence:

- `docs/runs/2026-07-09-wikipedia-process-death-03-oversized-saved-state-live-retry/README.md`
- #23 progress comment linking the same committed run record.

That retry did not produce valid benchmark evidence:

- baseline build and install succeeded;
- `am start -W` returned `Status: ok`;
- the app task closed before `nav_tab_search`;
- logcat included failed attach / start timeout / ANR signals;
- Android CLI layout / UIAutomator remained unstable after emulator refresh;
- no defect lane was run.

## Gate Evidence

The later live validation gate evidence proved the environment before the
successful matched-pair retry:

- `docs/runs/2026-07-09-live-validation-gate-current-environment/README.md`
  - generic gate passed: adb device, boot completion, boot animation,
    Android CLI layout JSON, and direct UIAutomator dump;
- `docs/runs/2026-07-09-wikipedia-app-smoke-gate/README.md`
  - app-level smoke passed: explicit Wikipedia launch, foreground package, and
    `nav_tab_search` / `Search` target surface.

## Successful Matched Pair

Durable run record:

- `docs/runs/2026-07-09-wikipedia-process-death-03-oversized-saved-state-matched-pair-retry/`

The final valid run changed the seed boundary from `dark_mode` to
`app_to_background`. A manual probe in the same run record showed why:

- `dark_mode` recreated `SearchActivity` but did not emit a
  `TransactionTooLargeException`;
- pressing Home from `SearchActivity` sent the Activity through the background
  save-state path and produced `FAILED BINDER TRANSACTION`,
  `FATAL EXCEPTION`, and `TransactionTooLargeException`.

Matched-pair outcome:

- baseline/control lane: runner exit `0`, L1 `inconclusive`, L2 `pass`;
- defect lane: runner exit `1`, L1 `fail`, `crash_stability`;
- defect logcat evidence includes
  `java.lang.RuntimeException: android.os.TransactionTooLargeException:
  data parcel size 2110592 bytes`.

## Inclusion-Rule Application

The M2-beta inclusion rules require a valid baseline/defect matched pair before
an injected-defect seed can count as `caught` or `missed`.

#23 now satisfies that rule because:

1. the baseline/control lane reached `SearchActivity`;
2. the baseline/control run captured an interpretable oracle result;
3. the defect lane ran the same user journey and `app_to_background` boundary;
4. the defect run captured an interpretable L1 `crash_stability` oracle result;
5. both halves are linked from a durable run record and GitHub issue evidence.

Therefore the seed is included in the M2-beta numerator and denominator as one
`caught` injected-defect seed with a `passed_control` baseline.

## Known Gap

The file name remains a quarantine note for historical continuity. Its current
contents are the resolution record, not an active exclusion.
