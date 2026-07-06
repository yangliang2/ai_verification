# 2026-07-06 Wikipedia process-death tab-state-loss Run Record

Issue: [#9](https://github.com/yangliang2/ai_verification/issues/9) — M1 five-Goldset report (seed 5, final category);
unblocks and resolves [#10](https://github.com/yangliang2/ai_verification/issues/10) (process-death seed).

## What this proves

The assembled end-to-end CLI catches a **silent state loss across real process death**
via the L2 state oracle — the defect class that config-change recreation can never
expose (the process, and any in-memory "storage", survives a recreation). Codex drives
the UI, the runner injects a true process death (HOME → `am kill` → explicit
launcher-intent relaunch) and captures evidence, L2 judges.

```
# baseline (control) — unmodified host
adb -s emulator-5554 shell pm clear org.wikipedia.dev
PYTHONPATH=src .venv/bin/python -m aiverify.runner \
  bench/goldset/run-specs/wikipedia-process-death-02-tab-state-loss.yaml \
  --device emulator-5554 --artifact-dir <run>/baseline/artifacts

# defect — patch applied
adb -s emulator-5554 shell pm clear org.wikipedia.dev
PYTHONPATH=src .venv/bin/python -m aiverify.runner \
  bench/goldset/run-specs/wikipedia-process-death-02-tab-state-loss.yaml \
  --device emulator-5554 --artifact-dir <run>/defect/artifacts
```

Matched pair, same scenario, same `process_death` event; the only difference is the
injected persistence rewire:

| half | L1 | L2 | tabsCountText before → after | exit | wall clock |
|---|---|---|---|---|---|
| baseline (control) | inconclusive | **pass** | "2" → "2" | 0 | 12:44:54 → 12:49:31 (4m37s) |
| defect | inconclusive | **fail / state_loss** | "2" → node gone (feed) | 1 | 12:50:14 → 12:54:07 (3m53s) |

L2 evidence (defect): `resource-id='tabsCountText'：操作后节点消失。操作前 text='<absent>'，
期望保留 text='2'` — the restored app landed on the **main feed**: with an empty tab
list, PageActivity's restore path bails out of the article UI entirely, so the whole
article toolbar (and `tabsCountText` with it) disappeared. Both Codex journey segments
PASSED in both halves; zero `am start` commands were used by the driver.

## Defect (taxonomy process-death-02: in-memory singleton as storage)

`bench/goldset/patches/wikipedia-process-death-02-tab-state-loss.patch` rewires
`WikipediaApp` tab persistence: `commitTabState()` writes the tab list to a
process-local `InMemoryTabStateCache` singleton instead of `Prefs.tabs`, and
`initTabs()` restores only from that cache. Config changes and navigation work
perfectly (process alive); a real process death starts a new process with an empty
cache — every tab and its article backstack silently gone, no crash.

Real-world shape: K-9 Mail #3970 (candidates.md P1) — state kept only in memory is
silently absent from the process-death restore path while everything else restores.

## Scenario

1. Walk onboarding → search "Cat" → open article.
2. Tab switcher → new tab → search "Dog" → open article. Toolbar `tabsCountText` = "2".
3. Boundary: inject `process_death` (2s → HOME → 2s → `am kill` → verify-by-design →
   explicit launcher intent → 8s restore wait).
4. L2 asserts `tabsCountText` text stays "2".

## Host-behavior findings (what unblocked issue #10)

Verified on-device before the seed was built (probe transcript in session; key facts
re-verified by the runs themselves):

1. **`am kill` is a no-op on a foreground process.** The app must be backgrounded
   (HOME) first; then the pid truly goes to NONE and relaunch gets a fresh pid.
2. **The current article survives process death without app persistence**: the system
   restores the PageActivity task, and the visible page is rebuilt from
   Activity/Fragment saved state + intent redelivery — not from `Prefs.tabs`.
   "The article is still there" is therefore NOT a valid discriminator (the earlier
   #9 finding that "Wikipedia cold-starts to the feed" applied only to
   `SearchActivity`, which the system does not restore).
3. What `Prefs.tabs` actually carries across process death is the **tab list** (other
   tabs + per-tab backstacks) — observable as `tabsCountText`: the baseline restores
   "2". The defect has two loss shapes, both failing the same "2" assertion: when the
   current article is re-derivable from intent redelivery (probe: article opened via
   VIEW deep link) it comes back alone as "1"; when it is not (this run: article
   opened by in-app navigation), PageActivity restores into an empty tab list and
   bails to the main feed, removing the node entirely.
4. **`monkey -p <pkg>` relaunch is nondeterministic on debug builds**: Wikipedia dev
   exposes LeakCanary's `LeakLauncherActivity` as a second LAUNCHER activity, and
   monkey sometimes picks it (observed live). The `process_death` event therefore
   relaunches with `am start -a android.intent.action.MAIN -c
   android.intent.category.LAUNCHER -n <pkg>/<activity>` (the run spec's `activity`),
   which brings the existing task back to front unchanged — same as a real icon tap.

## Driver-contract fix surfaced by this run

The first baseline attempt (12:31–12:43, discarded) had **L2 pass but an L1 false
fail**: Codex shortcut navigation with
`am start -n ...SearchActivity -a android.intent.action.SEARCH --es query Cat`, an
intent the host rejects with a real `FATAL EXCEPTION: Unknown intent when launching
SearchActivity` (plus a follow-on ANR) — an agent-induced crash, not a host defect.
Fix: the driver preamble in `src/aiverify/runner/cli.py` now forbids intent-based
navigation (`am start`/`am broadcast`/`monkey`) and requires tap/type-only driving.
The rerun used zero `am start` commands and produced a clean L1.

## Environment

- Host `/Users/peter/hosts/wikipedia` @ `6ccb8d8`, package `org.wikipedia.dev`,
  launcher alias `org.wikipedia.DefaultIcon`
- Baseline APK SHA-256: `450f97a73b37f419610fbf2677137e93bf78265030fdc07cbf26c7967a435fad`
- Defect APK SHA-256: `2e9f1d637689ca1d8dcfd86f3ac38f478422c3ce1450e436b72ee5f9c2ea6446`
- Patch SHA-256: `4b274312e148df8e6ce1fb76afb9fe2b2779be75f8c5632892a5ec93313686fc`
- Emulator `emulator-5554` (AVD `aiverify_api35`, API 35)
- Codex CLI `0.139.0`, Android CLI `1.0.15498356`, adb `1.0.41`
- baseline/verdict.json SHA-256: `1dadcd82b3d6ce9d63f7695f2ccb1057885262d5d76edcf759c6d2170a2db898`
- defect/verdict.json SHA-256: `f12a77fc2d1ef25f1375f21c41a0d59eafc7cf9c0c473144e637fdf7c0ac2469`

## Implementation Mapping

- Harness event: `DeviceController.process_death` (`src/aiverify/harness/device/controller.py`),
  injector branch + `activity` field (`src/aiverify/runner/system_events.py`),
  whitelist entry (`src/aiverify/runner/run_spec.py`), wired in `src/aiverify/runner/cli.py`
- Injected patch: `bench/goldset/patches/wikipedia-process-death-02-tab-state-loss.patch`
- Run spec: `bench/goldset/run-specs/wikipedia-process-death-02-tab-state-loss.yaml`
- Seed spec: `bench/goldset/specs/wikipedia-process-death-02-tab-state-loss.md`
- Layout fixtures (frozen from these runs):
  `bench/goldset/fixtures/wikipedia-process-death-02-tab-state-loss/{control,defect}-{before,after}-layout.json`
- Regression test: `tests/bench/test_goldset_process_death_02_state_loss.py`
- Unit tests: `tests/harness/test_device_controller.py` (TestProcessDeath),
  `tests/runner/test_system_events.py` (process_death cases)

## Artifact inventory

- `baseline/verdict.json`, `defect/verdict.json` — full L1/L2 verdicts + journey results
- `{baseline,defect}/artifacts/after-segment-0/` — pre-event checkpoint (layout.json,
  screen.png, screen-annotated.png, logcat.txt, commands.json)
- `{baseline,defect}/artifacts/after-event-0/` — post-process-death checkpoint (same shape)
- `{baseline,defect}/artifacts/wikipedia-process-death-02-tab-state-loss-segment-0/` —
  Codex events (`codex-events.jsonl`) + structured journey result (`codex-journey-result.json`)

## Known gaps

- Wall-clock timing is from shell `date` around the CLI invocation; per-phase timing
  inside the run is still not instrumented (M1 report known gap, unchanged).
- The discarded first baseline attempt is kept out of the artifacts; its lesson is
  encoded in the driver-preamble fix and this record.
