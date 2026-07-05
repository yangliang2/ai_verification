# Goldset Seed — Wikipedia navigation-01 double-open crash (M1 seed 4)

> Issue: [#9](https://github.com/yangliang2/ai_verification/issues/9) — M1 five-Goldset report.
> Oracle path: **L1 / crash_stability**, event-less scenario (crash on a tap).
> Run record: [`docs/runs/2026-07-05-wikipedia-navigation-01-double-open-crash/`](../../../docs/runs/2026-07-05-wikipedia-navigation-01-double-open-crash/README.md)

## Goal

Prove the verifier catches a **duplicate-open ("Fragment already added")** navigation
defect through L1. Fourth M1 category (navigation).

## Defect

`bench/goldset/patches/wikipedia-navigation-01-double-open-crash.patch`: in
`MainFragment`, tapping the **More** nav tab normally shows `MenuNavTabDialog` via
`ExclusiveBottomSheetPresenter.show(...)`, which **dismisses any existing sheet first**
(the app's own double-open guard). The patch bypasses that guard and calls `.show()`
twice on the same dialog instance:

```
IllegalStateException: Fragment already added: MenuNavTabDialog{...} (tag=menu_nav_tab)
```

This is the deterministic form of the missing-debounce double-open bug (the real-world
version is a rapid double-tap). Happy path (single guarded open) is fine.

| dimension | value |
|---|---|
| taxonomy pattern | `navigation-01` (repeated click opens the same destination twice) |
| verdict symptom axis | `crash_stability` |
| trigger | tapping the More nav tab (user action) — no system event |
| detector | **L1** (FATAL EXCEPTION / IllegalStateException) |
| real-world analogues | `candidates.md` N1 (Element #7087), N4 (AntennaPod #5548) |

## Expected verdict

- defect build: L1 = fail, defect_class_hypothesis = crash_stability.
- L2 = inconclusive (no system event).
- baseline build (guarded single open): no crash → L1 inconclusive.

## Known boundary

- Compressed to a deterministic single-tap double-show for reliability; the authentic
  trigger is a rapid double-tap with no debounce. Observable behavior (the exact
  "Fragment already added" crash) matches the real bug.
