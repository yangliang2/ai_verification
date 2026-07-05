# Goldset Seed — Wikipedia lifecycle-04 recreation crash (M1 seed 2)

> Issue: [#9](https://github.com/yangliang2/ai_verification/issues/9) — M1 five-Goldset report.
> Oracle path proven: **L1 / crash_stability** (complements seed 1's L2 / state_loss).
> Run record: [`docs/runs/2026-07-05-wikipedia-lifecycle-04-recreation-crash/`](../../../docs/runs/2026-07-05-wikipedia-lifecycle-04-recreation-crash/README.md)

## Goal

Prove the verifier catches a **crash-on-recreation** behavior-layer defect through
the cheap L1 logcat oracle, end-to-end via the assembled CLI. This is the crash
counterpart to seed 1 (state loss): same trigger (`dark_mode` config change), a
different defect, a different oracle layer.

## Defect

`bench/goldset/patches/wikipedia-lifecycle-04-recreation-crash.patch` adds a
`lateinit var configChangeToken` to `SearchFragment`:

- initialized only in `onCreate` when `savedInstanceState == null` (first creation);
- read on every `onCreateView` (`binding.searchCabView.contentDescription = configChangeToken`).

Happy path (no config change): initialized once, read fine. After a config-change
recreation (`savedInstanceState != null`): never initialized → the read throws
`kotlin.UninitializedPropertyAccessException` → FATAL EXCEPTION.

| dimension | value |
|---|---|
| taxonomy pattern | `lifecycle-04` (lateinit accessed before initialization) |
| verdict symptom axis | `crash_stability` |
| trigger | `dark_mode` (uiMode config change; recreates SearchActivity) |
| detector | **L1** (FATAL EXCEPTION in logcat) |

## Observed crash

```
E AndroidRuntime: FATAL EXCEPTION: main
E AndroidRuntime: kotlin.UninitializedPropertyAccessException: lateinit property configChangeToken has not been initialized
E AndroidRuntime:     at org.wikipedia.search.SearchFragment.onCreateView(SearchFragment.kt:148)
```

## Expected verdict

- **defect build**: L1 = fail, defect_class_hypothesis = crash_stability.
- **baseline build**: no crash under the same event → L1 = inconclusive.

## Known boundary

- Deterministic because it keys off `savedInstanceState != null`, which any config
  change that recreates the activity sets. Reuses seed 1's finding that `dark_mode`
  (not rotation) recreates `SearchActivity`.
- L1's crash pattern requires the `AndroidRuntime` tag (see the L1 false-positive fix
  in `docs/runs/2026-07-05-end-to-end-cli-codex/`); this crash carries it.
