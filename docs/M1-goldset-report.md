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
| 5 | process-death | `process-death-02` tab-state loss | `process_death` | **L2 fail / state_loss** | ✅ done |

Oracle-path coverage: **L2 (state_loss) ✅**, **L1 (crash_stability, both crash
and ANR) ✅**, **L3 (LLM semantic, ui_rendering) ✅** (post-M1 seed 6, issue #12 —
see "Beyond M1" below). **All 5 categories done.**

## M1 target result

> **M1 target — catch at least 3 of 5 seeds: MET, 5/5.**
> All five seeds attempted, **all five caught** (0 missed, 0 build failures, 0 driver
> failures). The process-death blocker (#10) was resolved by moving the sentinel to a
> restore-capable surface (the tab list) and adding a `process_death` harness event.
> Detection rate: **5/5**, with a passing baseline control for both L2 seeds.

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
| 5 process-death-02 | process-death | **caught** | inconclusive | **fail (state_loss)** | ~15–30s incr | 3m53s (Codex, measured) |

Also captured for seeds 1 and 5: a **baseline (control) run** under the same event →
**L2 pass** (the negative control), confirming the harness does not false-positive
when behavior is correct. Seed 5's control ran end-to-end through the same CLI
(4m37s, measured).

Timing caveat: host build times are from Gradle output. Seeds 1–4 end-to-end
wall-clock was approximate (shell `date` around the CLI). Since #11 the runner
instruments timing itself: `verdict.json` now carries a `timing` block with run
`started_at`/`finished_at`/`total_seconds` and per-phase durations (journey segment,
checkpoint capture, system-event injection). Seed 5's table rows are measured.

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

### Seed 5 — process-death-02 (L2 / state_loss)
- Defect: `WikipediaApp` tab persistence rewired to a process-local
  `InMemoryTabStateCache` singleton instead of `Prefs.tabs` (in-memory singleton as
  storage; real-world shape K-9 Mail #3970, candidates.md P1). Config changes and
  navigation are unaffected (process alive); a real process death restarts with an
  empty cache — the tab list and per-tab article backstacks are silently gone, no crash.
- Scenario: two article tabs (Cat, Dog) → `process_death` boundary event (HOME →
  `am kill` → explicit launcher-intent relaunch) → assert toolbar `tabsCountText`
  stays "2".
- Matched pair, both halves end-to-end Codex-driven with clean L1: baseline **L2 pass**
  ("2" → "2"), defect **L2 fail / state_loss** ("2" → node gone: PageActivity restores
  into an empty tab list and bails to the feed).
- This resolved #10's blocker. Key host findings: the **current article restores via
  system saved-state / intent redelivery, not app persistence** — so "the article is
  still there" is not a valid sentinel (the earlier "cold-starts to the feed" finding
  applied only to `SearchActivity`, which the system does not restore); and **`monkey`
  relaunch is nondeterministic on debug builds** (LeakCanary adds a second LAUNCHER
  activity), so the `process_death` event relaunches via an explicit MAIN+LAUNCHER
  intent with the run spec's `activity`.
- Also hardened the driver contract: the first baseline attempt was discarded because
  Codex navigated via `am start -a SEARCH`, crashing the host with an unsupported
  intent (an agent-induced L1 false fail). The driver preamble now forbids intent-based
  navigation (tap/type only); the reruns used zero `am start`.
- Patch `bench/goldset/patches/wikipedia-process-death-02-tab-state-loss.patch`;
  run record `docs/runs/2026-07-06-wikipedia-process-death-02-tab-state-loss/`;
  test `tests/bench/test_goldset_process_death_02_state_loss.py`.

## Beyond M1 — Seed 6, ui-rendering-01 (L3 / ui_rendering, issue #12)

The last unexercised oracle path. A sixth category beyond the M1 five, designed to be
**invisible to L1 and L2 by construction** so only semantic judgment can catch it:

- Defect: `NavTab.kt` swaps the `READING_LISTS`/`SEARCH` `text` string resources
  (copy-paste wrong-resource-id shape) — the Saved tab renders "Search" and vice
  versa. No crash, no missing node, app fully functional.
- Judge: **Codex CLI** as `CodexCliProvider` (`provider_id="openai"`, read-only
  sandbox) behind the existing `L3Oracle` contract; gated to run only when `l3_spec`
  is set and L1/L2 both come back non-fail. Cross-source holds (Claude-authored patch
  vs openai judge).
- Matched pair, both halves end-to-end via the CLI: baseline **L3 pass** (exit 0),
  defect **L3 fail / ui_rendering**, confidence 0.97 (exit 1). One judge call per
  half (~21 s, ≈20% of wall clock).
- The judge sees only `scenario.l3_spec` (correct-behavior product spec) + observed
  evidence — never `expected_behavior` or the patch.
- Patch `bench/goldset/patches/wikipedia-ui-rendering-01-nav-label-swap.patch`;
  run record `docs/runs/2026-07-06-wikipedia-ui-rendering-01-nav-label-swap/`;
  test `tests/bench/test_goldset_ui_rendering_01_nav_label_swap.py` (replays the
  frozen live judge responses via `MockProvider` — no emulator or LLM needed).
- M2 repeatability follow-up (#14): the same fixed baseline/defect evidence was judged
  5 times per half. Baseline was **5/5 L3 pass**, defect was **5/5 L3 fail /
  ui_rendering**, with 0 judge errors and confidence 0.97-0.98. Run record:
  `docs/runs/2026-07-07-l3-repeatability-ui-rendering-01/`. This supports using L3
  for M2 **text-layout semantic** seeds under repeatability discipline; it still does
  not prove visual-only or multimodal L3 reliability.

## Beyond M1 — Seed 7, config-change-02 (L2 / duplicated state, issue #15)

First M2 seed expansion beyond the original five-category M1 matrix. This keeps the
trigger and oracle path deliberately simple, but changes the symptom from state loss to
duplicated restored state:

- Defect: `SearchFragment.initSearchView()` re-applies the restored query after
  recreation and appends it to itself (`zzsentinelqx` → `zzsentinelqxzzsentinelqx`).
  The shape mirrors real duplicated editable-state regressions such as duplicated
  Thunderbird/K-9 recipients after configuration changes.
- Scenario: open Wikipedia SearchActivity, enter sentinel query `zzsentinelqx`, hide
  the keyboard with Back, inject `dark_mode`, and assert `search_src_text.text` still
  equals the original sentinel.
- Matched pair, both halves end-to-end via the CLI on Android API 36:
  baseline **L2 pass** (`zzsentinelqx` → `zzsentinelqx`), defect **L2 fail**
  (`zzsentinelqx` → `zzsentinelqxzzsentinelqx`). Current L2 verdict schema reports the
  mismatch as `state_loss`; the run/spec preserve that this is a duplicated-state seed.
- Patch `bench/goldset/patches/wikipedia-config-change-02-query-duplication.patch`;
  run record `docs/runs/2026-07-07-wikipedia-config-change-02-query-duplication/`;
  test `tests/bench/test_goldset_config_change_02_query_duplication.py`.
- Runner hardening from this live run: Android CLI layout capture now retries transient
  empty/non-JSON dumps, and screenshot/logcat capture has bounded timeouts so evidence
  collection fails with an explicit harness error instead of hanging indefinitely.

## Beyond M1 — Seed 8, navigation-02 (L2 / swallowed Back, issue #16)

Second M2 seed expansion beyond the original M1 matrix. This complements the M1
navigation seed, which was an L1 crash, with a non-crashing navigation-state defect:

- Defect: `SearchActivity`'s `OnBackPressedCallback` consumes the first
  Activity-level Back callback without delegating to `onBackPressedDispatcher`.
  The keyboard Back path still works; the user must press Back again to leave the
  search screen. This mirrors Tusky #3570, where the first hardware/system Back
  press after search had no visible effect.
- Scenario: open the Wikipedia Search tab, enter SearchActivity via `search_card`,
  type sentinel `zznavbackqx`, press Back once to hide the keyboard, press Back a
  second time to navigate out, inject `dark_mode` as the L2 observation boundary,
  and assert `search_card.resource-id == "search_card"`.
- Matched pair, both halves end-to-end via the CLI on Android API 36:
  baseline **L2 pass** (second Back returns to Search tab; `search_card` remains
  visible), defect **L2 fail** (still in SearchActivity; `search_src_text` remains
  visible and `search_card` is absent). Current L2 verdict schema reports the
  mismatch as `state_loss`; the run/spec preserve that this is a navigation
  swallowed-Back seed.
- Patch `bench/goldset/patches/wikipedia-navigation-02-back-button-swallowed.patch`;
  run record `docs/runs/2026-07-07-wikipedia-navigation-02-back-button-swallowed/`;
  test `tests/bench/test_goldset_navigation_02_back_button_swallowed.py`.
- Device note: the first defect setup after `pm clear` hit a startup ANR before
  the runner began; that attempt is retained in the run record and was not used as
  evidence. The valid defect run relaunched the same installed defect APK, confirmed
  `nav_tab_search`, cleared logcat, and then ran the assembled runner.

## Notes / findings carried forward

- `SearchActivity` declares `configChanges="orientation|screenSize"`, so **rotation
  does not recreate it**; use `dark_mode` (uiMode) to force recreation. See seed 1.
- The end-to-end CLI drives via the Codex CLI backend (agent navigates) while the
  runner deterministically injects the event and captures evidence.
- The Verification Agent Backend must not navigate via intents (`am start` etc.);
  unsupported intents can crash the host and contaminate L1. Enforced in the driver
  preamble since seed 5.
