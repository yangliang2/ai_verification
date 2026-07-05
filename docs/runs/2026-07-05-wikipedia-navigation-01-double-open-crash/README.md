# 2026-07-05 Wikipedia navigation-01 double-open crash Run Record

Issue: [#9](https://github.com/yangliang2/ai_verification/issues/9) — M1 five-Goldset report (seed 4).
Fourth M1 category (navigation); L1 / crash_stability, event-less scenario.

## What this proves

The assembled end-to-end CLI catches a **duplicate-open ("Fragment already added")**
navigation defect via L1 — Codex drives, the crash is triggered by tapping the More
nav tab (no boundary event):

```
python -m aiverify.runner \
  bench/goldset/run-specs/wikipedia-navigation-01-double-open-crash.yaml \
  --device emulator-5554 --artifact-dir <run>/artifacts
```

```
scenario: wikipedia-navigation-01-double-open-crash
Codex journey: [FAILED navigate to feed + tap More]   <- Codex observed the crash
L1: fail (crash_stability)                             <- crash caught
L2: inconclusive                                       <- no system event
```

## Defect (taxonomy navigation-01)

`bench/goldset/patches/wikipedia-navigation-01-double-open-crash.patch`: in
`MainFragment`, tapping the More nav tab normally shows `MenuNavTabDialog` via
`ExclusiveBottomSheetPresenter.show(...)`, which dismisses any existing sheet first
(the app's own double-open guard). The patch bypasses that guard and shows the same
dialog instance twice:

```
E AndroidRuntime: FATAL EXCEPTION: main
E AndroidRuntime: java.lang.IllegalStateException: Fragment already added: MenuNavTabDialog{...} (tag=menu_nav_tab)
```

Compressed to a deterministic single-tap double-show; the real-world trigger is a rapid
double-tap with no debounce (candidates N1 Element #7087, N4 AntennaPod #5548).
Happy path (single guarded open) is fine.

## Environment

- Host @ `6ccb8d8`, defect APK (patch applied), package `org.wikipedia.dev`
- Emulator `emulator-5554` (AVD `aiverify_api35`)
- Codex CLI `0.139.0`, Android CLI `1.0.15498356`, adb `1.0.41`
- Patch SHA-256: `8d6a6e03a2f77a70a9b9c97bd496ae1c12863ec8e88762f85723c62a38b16631`
- verdict.json SHA-256: `8db566275458de757d1611fc0fe66e14ec0e140ee0f3755a2c6ec42a03c0d329`

## Implementation Mapping

- Injected patch: `bench/goldset/patches/wikipedia-navigation-01-double-open-crash.patch`
- Run spec: `bench/goldset/run-specs/wikipedia-navigation-01-double-open-crash.yaml`
- Seed spec: `bench/goldset/specs/wikipedia-navigation-01-double-open-crash.md`
- Crash logcat fixture: `bench/goldset/fixtures/wikipedia-navigation-01-double-open-crash/crash-logcat.txt`
- Regression test: `tests/bench/test_goldset_navigation_01_crash.py`

## Known Gaps

- Deterministic single-tap double-show stands in for a rapid double-tap; the observed
  crash (`Fragment already added: MenuNavTabDialog`) matches the real bug exactly.
- Host patch reverted after the run; defect preserved in the committed `.patch`.
