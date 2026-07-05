# M1 Goldset Report — behavior-layer defect detection

Tracks the M1 milestone: one Goldset seed per taxonomy category, each an injected
real-shaped behavior-layer defect run through the assembled end-to-end pipeline
(`python -m aiverify.runner`), proving the verifier detects it.

Source material for injection sites: `bench/goldset/candidates.md` (18 verified
real-world defects). Taxonomy: `src/aiverify/bench/taxonomy/taxonomy.yaml`.

## Coverage matrix

Two axes: **taxonomy category** (the defect's root cause) × **oracle path / symptom**
(how the verifier catches it). A healthy M1 exercises both a spread of categories and
both cheap oracle layers (L1 crash signal, L2 state assertion).

| # | Taxonomy category | Seed | Trigger | Oracle / symptom | Status |
|---|---|---|---|---|---|
| 1 | config-change | `config-change-01` search query loss | `dark_mode` | **L2 fail / state_loss** | ✅ done |
| 2 | lifecycle | `lifecycle-04` recreation crash | `dark_mode` | **L1 fail / crash_stability** | ✅ done |
| 3 | coroutine-concurrency | `coroutine-concurrency-03` main-thread ANR | typing (no event) | **L1 fail / crash_stability (ANR)** | ✅ done |
| 4 | navigation | `navigation-01` double-open crash | tap More tab (no event) | **L1 fail / crash_stability** | ✅ done |
| 5 | process-death | — | background + `kill_background` | L2 state_loss / L1 crash | ⏸ blocked (see finding) |

Oracle-path coverage so far: **L2 (state_loss) ✅**, **L1 (crash_stability, both crash
and ANR) ✅**, L3 (LLM semantic) not yet exercised. 4/5 categories done; only
process-death remains (blocked on host restore behavior).

## M1 target result

> **M1 target — catch at least 3 of 5 seeds: MET.**
> Of the 4 seeds attempted, **4 were caught** (0 missed, 0 build failures, 0 driver
> failures). The 5th seed (process-death) is **not yet attempted** — blocked on host
> restore behavior, tracked in issue #10. Detection rate on attempted seeds: **4/4**;
> against the full 5-seed target: **4/5 attempted, 4/5 caught**.

## Outcomes by category and timing

Per the M1 report contract, each seed's outcome is separated into
**caught / missed / build-failure / driver-failure / inconclusive**. "Caught" means an
oracle returned `fail` for the injected defect. L2 shows `inconclusive` for the
crash/ANR seeds because those scenarios have no state-assertion boundary — the **defect
was still caught by L1**, so the per-seed outcome is *caught*.

| Seed | Category | Per-seed outcome | L1 | L2 | Host build | End-to-end run |
|---|---|---|---|---|---|---|
| 1 config-change-01 | config-change | **caught** | inconclusive | **fail (state_loss)** | 9m48s cold / ~15s incr | ~2–3 min (Codex) |
| 2 lifecycle-04 | lifecycle | **caught** | **fail (crash)** | inconclusive | ~15s incr | ~2–3 min (Codex) |
| 3 coroutine-conc-03 | coroutine-concurrency | **caught** | **fail (ANR)** | n/a (no event) | ~15–30s incr | ~2–4 min (Codex, +6s ANR block) |
| 4 navigation-01 | navigation | **caught** | **fail (crash)** | n/a (no event) | ~15–30s incr | ~1–3 min (Codex) |
| 5 process-death | process-death | **not attempted (blocked → #10)** | — | — | — | — |

Also captured for seed 1: a **baseline (control) run** under the same event → **L2 pass**
(the negative control), confirming the harness does not false-positive when behavior is
correct.

Timing caveat (known gap): host build times are from Gradle output; end-to-end
**per-seed wall-clock is approximate — not precisely instrumented**. Adding start/end
timestamps to `verdict.json` is easy follow-up.

## Done seeds

### Seed 1 — config-change-01 (L2 / state_loss)
- Defect: `binding.searchCabView.isSaveFromParentEnabled = false` drops the search
  subtree's saved state across a config change → typed query lost.
- Matched pair under `dark_mode`: baseline **L2 pass**, defect **L2 fail / state_loss**.
- Patch `bench/goldset/patches/wikipedia-config-change-01-search-query-loss.patch`;
  run records `docs/runs/2026-07-05-wikipedia-config-change-smoke/` (baseline) and
  `docs/runs/2026-07-05-wikipedia-config-change-01-defect/` (defect);
  end-to-end CLI `docs/runs/2026-07-05-end-to-end-cli-codex/`.
- Test `tests/bench/test_goldset_config_change_01_defect.py`.

### Seed 2 — lifecycle-04 (L1 / crash_stability)
- Defect: a `lateinit configChangeToken` initialized only on first creation
  (`savedInstanceState == null`) but read on every `onCreateView`; after a
  config-change recreation it is never initialized → `UninitializedPropertyAccessException`
  (FATAL EXCEPTION).
- Under `dark_mode`: defect **L1 fail / crash_stability**; baseline no crash
  (**L1 inconclusive**).
- Patch `bench/goldset/patches/wikipedia-lifecycle-04-recreation-crash.patch`;
  run record `docs/runs/2026-07-05-wikipedia-lifecycle-04-recreation-crash/`;
  test `tests/bench/test_goldset_lifecycle_04_crash.py`.

### Seed 3 — coroutine-concurrency-03 (L1 / ANR)
- Defect: `onQueryTextChange` runs `Thread.sleep(6000)` on the main thread (heavy work
  that belongs on `Dispatchers.Default`); the first keystroke blocks the UI > 5s → ANR.
- Event-less scenario (typing triggers it) → **L1 fail / crash_stability**; baseline no
  block → **L1 inconclusive**.
- Exercised a runner change: L1 now scans **all** checkpoint logcats (not only
  post-event), and event-less scenarios are L2-not-applicable rather than an error.
- Patch `bench/goldset/patches/wikipedia-coroutine-concurrency-03-main-thread-anr.patch`;
  run record `docs/runs/2026-07-05-wikipedia-coroutine-concurrency-03-anr/`;
  test `tests/bench/test_goldset_coroutine_03_anr.py`.

### Seed 4 — navigation-01 (L1 / crash_stability)
- Defect: tapping the More nav tab bypasses `ExclusiveBottomSheetPresenter`'s
  dismiss-first guard and shows `MenuNavTabDialog` twice → `IllegalStateException:
  Fragment already added`. Deterministic single-tap double-show (real trigger: rapid
  double-tap without debounce).
- Event-less scenario → **L1 fail / crash_stability**; baseline (guarded) → inconclusive.
- Patch `bench/goldset/patches/wikipedia-navigation-01-double-open-crash.patch`;
  run record `docs/runs/2026-07-05-wikipedia-navigation-01-double-open-crash/`;
  test `tests/bench/test_goldset_navigation_01_crash.py`.

## Blocked / pending seeds

### 5. process-death — BLOCKED on host behavior (finding)
Attempted with the search-sentinel scenario. Confirmed on device:
- `am kill` on the **foreground** app is a no-op (process survives); the app must be
  **backgrounded first** (`press home`), then `am kill` truly kills it (pid → NONE).
- **But after a real process death + relaunch, Wikipedia cold-starts to the main feed,
  not back into `SearchActivity`** — the search screen does not restore across process
  death. So the search sentinel can't demonstrate process-death state loss (the baseline
  itself doesn't restore it).

To do a faithful process-death seed we need either (a) a host screen Wikipedia **does**
restore across process death (e.g. an article `PageActivity`, or reading lists) plus a
defect there, and/or (b) a multi-segment re-entry scenario where the crash fires on
re-navigation after death — which also needs the runner's L1 multi-checkpoint scan
(now added in seed 3) and a harness helper for the background→kill→restore choreography.
This is scoped follow-up, not a quick seed (see issue #10).

## Notes / findings carried forward

- `SearchActivity` declares `configChanges="orientation|screenSize"`, so **rotation
  does not recreate it**; use `dark_mode` (uiMode) to force recreation. See seed 1.
- The end-to-end CLI drives via the Codex CLI backend (agent navigates) while the
  runner deterministically injects the event and captures evidence.
