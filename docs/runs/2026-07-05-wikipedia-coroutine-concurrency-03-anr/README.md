# 2026-07-05 Wikipedia coroutine-concurrency-03 main-thread ANR Run Record

Issue: [#9](https://github.com/yangliang2/ai_verification/issues/9) — M1 five-Goldset report (seed 3).
Third M1 category (coroutine-concurrency); proves L1 catches an **ANR**, and that the
runner's L1 scans every checkpoint (this seed has **no** system event).

## What this proves

The assembled end-to-end CLI catches a **main-thread-block → ANR** behavior-layer defect
via L1 — Codex drives, and the ANR is triggered by the typing itself (no boundary event):

```
python -m aiverify.runner \
  bench/goldset/run-specs/wikipedia-coroutine-concurrency-03-main-thread-anr.yaml \
  --device emulator-5554 --artifact-dir <run>/artifacts
```

```
scenario: wikipedia-coroutine-concurrency-03-main-thread-anr
Codex journey: [PASSED navigate+open search, PASSED type 'anrtest']
checkpoints: [after-segment-0]        <- no system event, single segment
L1: fail (crash_stability)            <- ANR caught from the segment logcat
L2: inconclusive                      <- no system event; state assertion N/A
```

## Defect (taxonomy coroutine-concurrency-03)

`bench/goldset/patches/wikipedia-coroutine-concurrency-03-main-thread-anr.patch`:
`SearchFragment.onQueryTextChange` runs `Thread.sleep(6000)` on the main thread
(heavy work that belongs on `Dispatchers.Default`), guarded to fire once. The first
keystroke blocks the UI thread while further input queues → ANR:

```
E ActivityManager: ANR in org.wikipedia.dev (org.wikipedia.dev/org.wikipedia.search.SearchActivity)
E ActivityManager: Reason: Input dispatching timed out (... Waited 5006ms for KeyEvent ...)
```

Happy path (no typing) never blocks. Baseline build: no ANR → L1 inconclusive.

## Runner change exercised

`src/aiverify/runner/cli.py`:
- L1 now judges the concatenation of **all** checkpoint logcats, so a crash/ANR during
  any segment is caught — not only the post-event checkpoint.
- Event-less scenarios (no `system_events`) are treated as L2-not-applicable
  (inconclusive) instead of raising.
- The CLI exits non-zero when **either** oracle reports fail.

## Environment

- Host @ `6ccb8d8`, defect APK (patch applied), package `org.wikipedia.dev`
- Emulator `emulator-5554` (AVD `aiverify_api35`)
- Codex CLI `0.139.0`, Android CLI `1.0.15498356`, adb `1.0.41`
- Patch SHA-256: `13d070c9a27c90ac1629c5fab3e11fa536ce5b74c6b0f0c0d62915a116a355ea`
- verdict.json SHA-256: `adcbd3c3b54f19535d643152b5eefbc9e5d993113bc079278a66865749c327e8`

## Implementation Mapping

- Injected patch: `bench/goldset/patches/wikipedia-coroutine-concurrency-03-main-thread-anr.patch`
- Run spec: `bench/goldset/run-specs/wikipedia-coroutine-concurrency-03-main-thread-anr.yaml`
- Seed spec: `bench/goldset/specs/wikipedia-coroutine-concurrency-03-main-thread-anr.md`
- ANR logcat fixture: `bench/goldset/fixtures/wikipedia-coroutine-concurrency-03-anr/anr-logcat.txt`
- Regression test: `tests/bench/test_goldset_coroutine_03_anr.py`

## Known Gaps

- The block is guarded to fire once so the app recovers after ~6s.
- ANR detection needs pending input during the block; the typed query supplies it.
- Host patch reverted after the run; defect preserved in the committed `.patch`.
