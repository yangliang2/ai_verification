# Goldset Seed — Wikipedia coroutine-concurrency-03 main-thread ANR

> Issue: [#9](https://github.com/yangliang2/ai_verification/issues/9) — M1 five-Goldset report.
> Oracle path: **L1 / crash_stability** (ANR), via an event-less scenario.
> Run record: [`docs/runs/2026-07-05-wikipedia-coroutine-concurrency-03-anr/`](../../../docs/runs/2026-07-05-wikipedia-coroutine-concurrency-03-anr/README.md)

## Goal

Prove the verifier catches a **main-thread block → ANR** behavior-layer defect through
L1, and prove the runner's L1 scans **every** checkpoint (not just the post-event one) —
here the ANR is triggered by a user action (typing), with no system event.

## Defect

`bench/goldset/patches/wikipedia-coroutine-concurrency-03-main-thread-anr.patch`:
`SearchFragment.onQueryTextChange` runs heavy work on the main thread
(`Thread.sleep(6000)`, guarded to fire once) instead of `withContext(Dispatchers.Default)`.
The first keystroke blocks the UI thread > 5s while further input queues → ANR.

| dimension | value |
|---|---|
| taxonomy pattern | `coroutine-concurrency-03` (main-thread block / heavy work on main dispatcher) |
| verdict symptom axis | `crash_stability` (ANR) |
| trigger | typing (user action) — **no system event** |
| detector | **L1** (`ANR in` in logcat) |

## Observed ANR

```
E ActivityManager: ANR in org.wikipedia.dev (org.wikipedia.dev/org.wikipedia.search.SearchActivity)
E ActivityManager: Reason: Input dispatching timed out (... Waited 5002ms for KeyEvent ...)
```

## Expected verdict

- defect build: L1 = fail, defect_class_hypothesis = crash_stability.
- L2 = inconclusive (no system event → state assertion not applicable).
- baseline build: no block, no ANR → L1 inconclusive.

## Runner change this seed exercises

`cli.py` now (a) runs L1 over the concatenation of **all** checkpoint logcats — so a
crash/ANR in any segment is caught, not only after a boundary event — and (b) treats
event-less scenarios as L2-not-applicable rather than an error. The CLI exits non-zero
when **either** oracle reports fail.

## Known boundary

- The block is guarded to fire once (`mainThreadBlockDone`) so the app recovers after
  ~6s rather than blocking on every keystroke.
- ANR detection needs pending input during the block; the typed query supplies it.
