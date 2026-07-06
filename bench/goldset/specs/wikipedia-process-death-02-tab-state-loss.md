# Goldset Seed — Wikipedia process-death tab-state loss (M1 seed 5)

> Issue: [#9](https://github.com/yangliang2/ai_verification/issues/9) — M1 five-Goldset report;
> unblocks [#10](https://github.com/yangliang2/ai_verification/issues/10) (process-death seed).
> Oracle path proven: **L2 / state_loss** under a real process death.
> Run record: [`docs/runs/2026-07-06-wikipedia-process-death-02-tab-state-loss/`](../../../docs/runs/2026-07-06-wikipedia-process-death-02-tab-state-loss/README.md)

## Goal

Prove the verifier catches a **silent state loss across real process death** — the
defect class that config-change recreation can never expose, because the process (and
any in-memory "storage") survives a recreation. This is the fifth and final M1
taxonomy category.

## Defect (taxonomy process-death-02: in-memory singleton as storage)

`bench/goldset/patches/wikipedia-process-death-02-tab-state-loss.patch` rewires
`WikipediaApp` tab persistence:

- `commitTabState()` writes the tab list to a process-local `InMemoryTabStateCache`
  singleton instead of `Prefs.tabs` (persistent storage);
- `initTabs()` restores only from that cache.

Happy path is indistinguishable from correct code: navigation, tab management, and
**config-change recreation all work** (the process stays alive, so the cache holds).
Only a real process death (system reclaiming the backgrounded app) starts a new
process with an empty cache — every tab and its article backstack is silently gone.

Real-world shape: K-9 Mail [#3970](https://github.com/thunderbird/thunderbird-android/issues/3970)
(candidates.md P1) — state kept only in memory is silently absent from the
process-death restore path while everything else restores fine.

| dimension | value |
|---|---|
| taxonomy pattern | `process-death-02` (in-memory singleton used as storage) |
| verdict symptom axis | `state_loss` |
| trigger | `process_death` (HOME → `am kill` → explicit launcher-intent relaunch) |
| detector | **L2** (`tabsCountText` text "2" → "1" after the event) |

## Host-behavior findings (unblocked issue #10)

Verified on `emulator-5554` (AVD `aiverify_api35`, API 35):

1. `am kill` is a **no-op on a foreground process**; the app must be backgrounded
   (HOME) first — then the pid truly goes to NONE.
2. After process death + launcher relaunch, the system **restores the PageActivity
   task**, and the **current article restores via Activity/Fragment saved state and
   intent redelivery — not via `Prefs.tabs`**. "The article is still there" is
   therefore NOT a valid discriminator; a probe asserting on it produces a
   false-negative on the defect and a trivially-passing baseline.
3. What `Prefs.tabs` actually carries across process death is the **tab list** (other
   tabs + per-tab backstacks). The observable discriminator is the toolbar tab count:
   baseline restores "2", the defect build comes back with "1".
4. Debug builds expose **multiple LAUNCHER activities** (LeakCanary's
   `LeakLauncherActivity`); `monkey -p <pkg>` picks one nondeterministically and can
   relaunch the wrong UI. The `process_death` harness event therefore relaunches with
   an explicit launcher intent (`am start -a MAIN -c LAUNCHER -n <pkg>/<activity>`),
   which brings the existing task back to front unchanged — same as a real icon tap.

## Scenario

1. Open the app, walk onboarding, search "Cat", open the article.
2. Open a **second tab** via the tab switcher, search "Dog", open the article —
   toolbar `tabsCountText` now shows "2".
3. Boundary: inject `process_death`.
4. L2 asserts `tabsCountText` text stays "2".

## Expected verdict

- **defect build**: L2 = fail, defect_class_hypothesis = state_loss (count "2" → "1").
- **baseline build**: same event, count stays "2" → L2 = pass. No crash either way,
  so L1 = inconclusive.

## Known boundary

- The current-article restore path (saved state + intent redelivery) is system-owned
  and stays intact under this defect; only app-persisted state is lost. That is what
  makes the seed faithful: partial restore, silent loss — no crash to catch on L1.
- `restore_wait` (default 8s) must cover PageActivity recreation + article reload
  before the after-event checkpoint; slower hosts can raise it via event args.
