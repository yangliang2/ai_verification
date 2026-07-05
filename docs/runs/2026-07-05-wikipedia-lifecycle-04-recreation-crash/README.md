# 2026-07-05 Wikipedia lifecycle-04 recreation-crash Run Record

Issue: [#9](https://github.com/yangliang2/ai_verification/issues/9) — M1 five-Goldset report (seed 2).
Complements seed 1 (config-change-01, L2/state_loss) by proving the **L1 / crash_stability** path.

## What this proves

The assembled end-to-end CLI catches a **crash-on-recreation** behavior-layer defect
via the cheap L1 logcat oracle — Codex drives, the runner injects the config change and
captures evidence, L1 judges:

```
python -m aiverify.runner \
  bench/goldset/run-specs/wikipedia-lifecycle-04-recreation-crash.yaml \
  --device emulator-5554 --artifact-dir <run>/artifacts
```

```
scenario: wikipedia-lifecycle-04-recreation-crash
Codex journey: [PASSED navigate+open search, PASSED type sentinel]
L1: fail  (defect_class=crash_stability)   <- the crash was caught
L2: inconclusive                            <- app crashed; no clean post-event state
```

## Defect (taxonomy lifecycle-04)

`bench/goldset/patches/wikipedia-lifecycle-04-recreation-crash.patch` adds a
`lateinit var configChangeToken` to `SearchFragment`, initialized only on first
creation (`savedInstanceState == null`) but read on every `onCreateView`. After a
config-change recreation it is never initialized:

```
E AndroidRuntime: FATAL EXCEPTION: main
E AndroidRuntime: kotlin.UninitializedPropertyAccessException: lateinit property configChangeToken has not been initialized
E AndroidRuntime:     at org.wikipedia.search.SearchFragment.onCreateView(SearchFragment.kt:148)
```

Happy path (no config change) initializes and reads it fine.

- trigger: `dark_mode` (uiMode config change — recreates SearchActivity; rotation would
  not, per seed 1's finding)
- detector: **L1** (FATAL EXCEPTION carries the `AndroidRuntime` tag the fixed L1
  pattern requires)
- baseline build under the same event: no crash → **L1 inconclusive**

## Environment

- Host @ `6ccb8d8`, defect APK (patch applied), package `org.wikipedia.dev`
- Emulator `emulator-5554` (AVD `aiverify_api35`)
- Codex CLI `0.139.0`, Android CLI `1.0.15498356`, adb `1.0.41`
- Patch SHA-256: `52dd65498be3f6b1378a0abbbf5bd276810d3aac1b5a1192fefb04d9de17ef70`
- verdict.json SHA-256: `7b8b57fa31afa0250c4d4b312245b547685a24e9955a6a41f9aa93f392b491ba`

## Implementation Mapping

- Injected patch: `bench/goldset/patches/wikipedia-lifecycle-04-recreation-crash.patch`
- Run spec: `bench/goldset/run-specs/wikipedia-lifecycle-04-recreation-crash.yaml`
- Seed spec: `bench/goldset/specs/wikipedia-lifecycle-04-recreation-crash.md`
- Crash logcat fixture: `bench/goldset/fixtures/wikipedia-lifecycle-04-recreation-crash/crash-logcat.txt`
- Regression test: `tests/bench/test_goldset_lifecycle_04_crash.py`
- Verdict + evidence checkpoints under `artifacts/`

## Known Gaps

- L2 is inconclusive because the app crashed during the event (no clean post-event
  layout to assert); L1 is the correct detector for a crash defect.
- Single seed. Remaining M1 categories (process-death, navigation,
  coroutine-concurrency) are tracked in `docs/M1-goldset-report.md`.
- Host patch reverted after the run; the defect lives in the committed `.patch`.
