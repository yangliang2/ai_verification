# 2026-07-05 Wikipedia config-change INJECTED DEFECT Run Record

Issue: [#8](https://github.com/yangliang2/ai_verification/issues/8) — Wikipedia config-change Goldset seed (positive / injected-defect half).
Parent PRD: [#1](https://github.com/yangliang2/ai_verification/issues/1).
Baseline (negative control) half: [`docs/runs/2026-07-05-wikipedia-config-change-smoke/`](../2026-07-05-wikipedia-config-change-smoke/README.md).

## Scope

Prove the verification chain **detects** a real-shaped config-change behavior-layer
defect: injects the defect into the host, drives the same scenario, and confirms
the repo code reports **L2 fail / state_loss** — while the unmodified baseline
reports **L2 pass** under the *same* configuration-change event (matched pair).

- Injected line (`SearchFragment.initSearchView()`):
  `binding.searchCabView.isSaveFromParentEnabled = false`
  — drops the whole search subtree's saved state (SearchView `mUserQuery` **and**
  the `search_src_text` EditText) across configuration-change recreation.
- taxonomy pattern: `config-change-01` (配置变更后 UI 状态丢失，未持久化)
- verdict symptom axis: `state_loss`
- real-world analogues: `bench/goldset/candidates.md` C1 (Tusky #45), C3 (Thunderbird #10288)

## Key finding — rotation cannot expose this defect on SearchActivity

`SearchActivity` declares in the manifest:
```xml
android:configChanges="orientation|screenSize"
```
So **rotation does not recreate the activity** — Android delivers
`onConfigurationChanged` and the view tree (including the EditText text) persists
in memory. The save/restore path is never exercised on rotation. Consequences:

- The earlier baseline smoke "pass" (under rotation) was **trivial** — the view was
  never destroyed, so nothing was saved/restored.
- Disabling saved state has **no observable effect under rotation**. Verified
  empirically: with the defect built in, a portrait→landscape rotation still
  retained `zzsentinelqx`.

`uiMode` (dark mode) is **not** in that `configChanges` list, so toggling dark mode
**does** force activity recreation and exercises the real save/restore path. Dark
mode is an explicit member of the taxonomy `config-change` category (旋转 / 字体 /
多窗口 / 深色模式). The seed therefore uses a **dark-mode** config-change event.

To support this, the harness gained a first-class `dark_mode` system event:
`DeviceController.set_night_mode()` (`cmd uimode night yes|no`), the
`DeviceSystemEventInjector` branch, and the `SUPPORTED_SYSTEM_EVENTS` whitelist
entry — all unit-tested.

## Matched-pair result (same scenario, same dark-mode event)

| Build | `search_src_text` after dark-mode | L2 verdict |
| --- | --- | --- |
| Baseline (unmodified) | `zzsentinelqx` (retained) | **pass** |
| Defect (`isSaveFromParentEnabled=false`) | `Search Wikipedia` (placeholder — lost) | **fail / state_loss** |

The only variable is the one injected line, so the fail is attributable to it.

## Environment

- Host app: `/Users/peter/hosts/wikipedia` @ `6ccb8d8`, package `org.wikipedia.dev`
- Emulator: AVD `aiverify_api35`, `emulator-5554`
- Android CLI `1.0.15498356` · adb `1.0.41` · Gradle build `assembleDevDebug`
- Defect APK SHA-256: `6b5ba9f51cc9bc5fe27251f68b9978b5c27b74157b19272b2beeb21c7e73c513`
- Baseline APK SHA-256: `ac1003091da4d11381a1fb652a4d2ae1ae56c4eaee603afc67851418051cec85`
- Injected patch: `bench/goldset/patches/wikipedia-config-change-01-search-query-loss.patch`
  (SHA-256 `56b542d7db95fef9457d8f1b72c5708380a0e43752b281c5535c9cf34d3a294c`; `git apply --check` clean against host `6ccb8d8`)

## Commands And Results

Inject + build (incremental):
```bash
# apply patch to host, then:
cd /Users/peter/hosts/wikipedia && ./gradlew assembleDevDebug --no-daemon
# BUILD SUCCESSFUL in 15s
```

Deploy + navigate (agent-in-the-loop; onboarding walked, then nav_tab_search ->
search_card -> search_src_text), type sentinel, capture BEFORE (light), inject
dark mode at the boundary, capture AFTER (dark):
```bash
android run --apks=.../app-dev-debug.apk --device=emulator-5554 --activity=org.wikipedia.DefaultIcon
adb -s emulator-5554 shell input text "zzsentinelqx"
android layout --device=emulator-5554 --pretty -o=<before>/layout.json
adb -s emulator-5554 shell "cmd uimode night yes"     # <- dark_mode config change
android layout --device=emulator-5554 --pretty -o=<after>/layout.json
```
```text
DEFECT   BEFORE search_src_text: 'zzsentinelqx'   AFTER: 'Search Wikipedia'   -> lost
CONTROL  BEFORE search_src_text: 'zzsentinelqx'   AFTER: 'zzsentinelqx'       -> retained
```

Verdict (repo code `judge_l2_from_android_layout` + `L1Oracle`), written to `verdict.json`:
```text
DEFECT   L1: inconclusive   L2: fail   defect_class_hypothesis: state_loss
  evidence: resource-id='search_src_text' attr='text' 期望='zzsentinelqx' 实际='Search Wikipedia'
CONTROL  L2: pass
```

Test verification:
```bash
PYTHONPATH=src .venv/bin/pytest      # 181 passed
```
(was 173; +8: 4 in `tests/bench/test_goldset_config_change_01_defect.py`,
2 dark_mode injector tests, 2 `set_night_mode` DeviceController tests.)

## Implementation Mapping

- Injected patch: `bench/goldset/patches/wikipedia-config-change-01-search-query-loss.patch`
- Run Spec: `bench/goldset/run-specs/wikipedia-config-change-01-defect.yaml`
- Frozen fixtures (matched pair): `bench/goldset/fixtures/wikipedia-config-change-01-defect/{defect,control}-{before,after}-layout.json`
- Regression test: `tests/bench/test_goldset_config_change_01_defect.py`
- Harness `dark_mode` event: `src/aiverify/harness/device/controller.py` (`set_night_mode`),
  `src/aiverify/runner/system_events.py`, `src/aiverify/runner/run_spec.py`
- Verdict: `docs/runs/2026-07-05-wikipedia-config-change-01-defect/verdict.json`

## Artifact Inventory

| Artifact | SHA-256 |
| --- | --- |
| `artifacts/after-segment-0-before-darkmode/layout.json` | `c833afd37e96bb7c353b53486dd7fab262c7407763cccdf16909c6f64b67f8ef` |
| `artifacts/after-segment-0-before-darkmode/screen.png` | `6a9617642b770124f4b327e68dc29ba2c1fc8d812ef6b844515f9186c31f1c61` |
| `artifacts/after-event-0-darkmode/layout.json` | `702ab19b4a9078efb7218ab19fcc9e93813c8ea98fdbb456e20264e8e094d115` |
| `artifacts/after-event-0-darkmode/screen.png` | `6932aabf28c4ac75346b95eb4d23a9290d8ba83c694d4bb6ef4d64d4f2ca6097` |
| `artifacts/after-event-0-darkmode/screen-annotated.png` | `a3648d06a8c6fe64738b0910e6dc4ed7ee45a8b450f3ab84abfb641234269ba3` |
| `artifacts/baseline-control-under-darkmode/before-layout.json` | `c833afd37e96bb7c353b53486dd7fab262c7407763cccdf16909c6f64b67f8ef` |
| `artifacts/baseline-control-under-darkmode/after-layout.json` | `c833afd37e96bb7c353b53486dd7fab262c7407763cccdf16909c6f64b67f8ef` |
| `verdict.json` | `af4ff50e27057c21ea21d412bf6029d23f7122aeeba373e51fd9317e208a619c` |

(Control before==after==the defect-before hash: the search screen with the sentinel
retained renders to a byte-identical layout JSON; only the defect-after differs.)

## Known Gaps

- **Agent-in-the-loop**, not Codex CLI backend: navigation/injection driven via
  Android CLI layout + adb. Driving through `CodexCliBackend` remains pending.
- Dark mode injected via `cmd uimode night` (the new MVP injector path); no
  higher-level Android CLI Journey.
- The host patch was reverted after the run; the durable defect definition lives
  in the committed `.patch` artifact (verified `git apply --check` clean).
- One seed, one defect class. Broadening to the M1 five-Goldset set is #9.
