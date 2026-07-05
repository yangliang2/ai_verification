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

| # | Taxonomy category | Seed | Trigger event | Oracle / symptom | Status |
|---|---|---|---|---|---|
| 1 | config-change | `config-change-01` search query loss | `dark_mode` | **L2 fail / state_loss** | ✅ done |
| 2 | lifecycle | `lifecycle-04` recreation crash | `dark_mode` | **L1 fail / crash_stability** | ✅ done |
| 3 | process-death | — | `kill_background` (+ background) | L2 state_loss / L1 crash | ⬜ pending |
| 4 | navigation | — | double-open / deep link | L1 crash_stability | ⬜ pending |
| 5 | coroutine-concurrency | — | rotate / background race | L1 ANR/crash | ⬜ pending |

Oracle-path coverage so far: **L2 (state_loss) ✅**, **L1 (crash_stability) ✅**,
L3 (LLM semantic) not yet exercised.

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

## Pending seeds (next work)

3. **process-death** — `am kill` after backgrounding, then cold recovery. Candidate
   patterns: process-death-01 (state not in SavedStateHandle → loss) or process-death-03
   (deep page reads null upstream state → NPE). Note from experiments: reliable
   process-death restore of a deep activity needs backgrounding first (`am kill` is a
   no-op on the foreground app) and task-restore choreography — needs a harness helper.
4. **navigation** — double-open ("Fragment already added") crash, or deep-link entry
   that skips upstream init. Double-tap timing can be flaky; a deep-link trigger is
   more deterministic but needs a `deep_link` injector event.
5. **coroutine-concurrency** — main-thread block → ANR (L1), or GlobalScope updating a
   destroyed view on rotation → crash. Races often need load/repetition to surface.

## Notes / findings carried forward

- `SearchActivity` declares `configChanges="orientation|screenSize"`, so **rotation
  does not recreate it**; use `dark_mode` (uiMode) to force recreation. See seed 1.
- The end-to-end CLI drives via the Codex CLI backend (agent navigates) while the
  runner deterministically injects the event and captures evidence.
