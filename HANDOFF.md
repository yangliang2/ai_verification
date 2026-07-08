# HANDOFF

当前项目范围已经重新对齐：MVP 先验证 **Codex CLI + Android CLI + Wikipedia host** 的行为层 smoke 链路，不再把旧计划里的 “100+ 自动注入缺陷基准” 当作当前完成标准。

## 当前真实状态

### 已完成

- GitHub PRD #1 已完成并关闭: <https://github.com/yangliang2/ai_verification/issues/1>
- 已关闭 agent-ready issues: #2, #3, #4, #5, #6, #7
- 已关闭 implementation/follow-up issues: #8, #9, #10, #11, #12, #14, #15, #16, #17, #18
- Run record: [`docs/runs/2026-06-15-afk-verification/README.md`](docs/runs/2026-06-15-afk-verification/README.md)
- Evidence artifacts: [`docs/runs/2026-06-15-afk-verification/artifacts/`](docs/runs/2026-06-15-afk-verification/artifacts/)
- M1 report: [`docs/M1-goldset-report.md`](docs/M1-goldset-report.md)
- Retrospective #11 timing run record: [`docs/runs/2026-07-06-runner-timing-instrumentation/README.md`](docs/runs/2026-07-06-runner-timing-instrumentation/README.md)
- Latest L3 run record: [`docs/runs/2026-07-06-wikipedia-ui-rendering-01-nav-label-swap/README.md`](docs/runs/2026-07-06-wikipedia-ui-rendering-01-nav-label-swap/README.md)
- Latest M2 seed run record: [`docs/runs/2026-07-08-wikipedia-ui-rendering-02-search-card-copy-mismatch/README.md`](docs/runs/2026-07-08-wikipedia-ui-rendering-02-search-card-copy-mismatch/README.md)
- Latest L3 repeatability run record: [`docs/runs/2026-07-08-l3-repeatability-ui-rendering-02/README.md`](docs/runs/2026-07-08-l3-repeatability-ui-rendering-02/README.md)
- Test status: `.venv/bin/pytest` -> `239 passed, 2 warnings`

### 已实测

Android CLI:
- Installed command: `/Users/peter/.local/bin/android`
- Version: `1.0.15498356`
- SDK path from `android info`: `/opt/homebrew/share/android-commandlinetools`
- Confirmed commands: `android update`, `android init`, `android info`, `android layout`, `android layout --diff`, `android screen capture`, `android screen capture --annotate`, `android screen resolve --screenshot`, `android docs`, `android skills`
- Caveat: `android screen resolve` uses `--screenshot`, not `--screen`
- Caveat: `android run` deploys/checks APKs; it does not build missing APKs

Codex CLI:
- Version: `codex-cli 0.139.0`
- Driver backend uses `codex exec --json --output-schema --output-last-message --skip-git-repo-check --cd ... --dangerously-bypass-approvals-and-sandbox` because it must operate Android CLI / adb outside the workspace.
- L3 judge backend uses `codex exec --json --output-last-message --skip-git-repo-check --sandbox read-only --cd ...` because it only reads evidence artifacts.

Wikipedia host:
- Path: `/Users/peter/hosts/wikipedia`
- Commit: `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`
- Build command: `./gradlew assembleDevDebug --no-daemon`
- Build result: `BUILD SUCCESSFUL in 9m 48s`
- APK: `/Users/peter/hosts/wikipedia/app/build/outputs/apk/dev/debug/app-dev-debug.apk`
- APK SHA-256: `cf882666ecab7b4ad3362e5580ef3e692062d3958045b103e0c43a6014ee32e9`
- Package: `org.wikipedia.dev`
- Launch component used by Android CLI: `org.wikipedia.DefaultIcon`
- Evidence confirms Wikipedia onboarding screen.

### Implemented runner contracts

- `src/aiverify/runner/run_spec.py`: `run-spec.yaml` parsing, validation, dry-run plan.
- `src/aiverify/runner/codex_backend.py`: Codex CLI Verification Agent Backend contract.
- `src/aiverify/runner/journey_result_schema.json`: structured Journey result schema.
- `src/aiverify/runner/evidence.py`: Android CLI layout/screenshot/checkpoint evidence capture.
- `src/aiverify/runner/journey.py`: Journey segment boundary orchestration.
- `src/aiverify/runner/system_events.py`: system-event injection at boundaries.
- `src/aiverify/runner/verdict.py`: Android CLI layout JSON to L2Oracle verdict.
- `src/aiverify/runner/cli.py`: end-to-end Run Spec runner, timing, L1/L2/L3 gating, non-zero exit on oracle fail.
- `src/aiverify/providers/codex_cli.py`: Codex CLI-backed `LLMProvider` for L3 semantic judging.
- `src/aiverify/agent/oracle/l1.py`, `l2.py`, `l3.py`: crash/ANR, state assertion, and semantic oracle paths now all exercised live.
- `src/aiverify/harness/device/controller.py`: includes public `press_home()` for backgrounding.

## Current Boundary

Do not claim these are complete yet:

- Full defect-injected end-to-end benchmark.
- 100+ AI-generated source-level defects.
- Detection rate, false-positive rate, L3 repeatability, or full-benchmark throughput beyond the M1 seed-count demonstration.
- Fully unattended Android Journey execution.
- ColorOS internal app/build migration.
- Multimodal/visual-only L3 judgment.

The current value is concrete but still bounded: the repo has a tested end-to-end runner, real Android host build/deploy proof, M1 5/5 Goldset detection evidence, live L1/L2/L3 oracle coverage, and durable evidence discipline.

## Progress Update (2026-07-05) — #8 COMPLETE (both halves)

Both the negative control and the injected-defect halves of #8 are done, as a
matched pair on `emulator-5554` / AVD `aiverify_api35`, computed by the repo code:

- Baseline: sentinel retained across the config change → **L2=pass**.
- Defect (`isSaveFromParentEnabled=false`): sentinel lost → **L2=fail / state_loss**.
- Run records: `docs/runs/2026-07-05-wikipedia-config-change-smoke/` (pass) and
  `docs/runs/2026-07-05-wikipedia-config-change-01-defect/` (fail).

Key finding: `SearchActivity` declares `configChanges="orientation|screenSize"`, so
**rotation does not recreate it** and cannot expose config-change state loss (the
baseline rotation-pass was trivial). The seed uses a **dark-mode (uiMode)** config
change, which is not swallowed and forces recreation. New first-class `dark_mode`
system event added: `DeviceController.set_night_mode`, injector branch, whitelist —
all unit-tested. Suite now **181 passed** (was 170).

Durable assets: `bench/goldset/{run-specs,specs,fixtures,patches}/wikipedia-config-change*`,
`tests/bench/test_goldset_config_change_smoke.py`, `tests/bench/test_goldset_config_change_01_defect.py`.

Still not exercised: Codex CLI backend (both runs were agent-in-the-loop).

## Progress Update (2026-07-05) — backend wired + end-to-end CLI

The two gaps from the #8 run records are closed:

- **Codex CLI backend now runs live.** Fixed two blocking bugs: `CodexCliBackend`
  used `--ask-for-approval` (rejected by codex 0.139.0 → now
  `--dangerously-bypass-approvals-and-sandbox`), and `journey_result_schema.json`
  was not OpenAI-strict (→ made `additionalProperties:false` + all-required).
- **Assembled end-to-end CLI**: `python -m aiverify.runner RUN_SPEC --device ... --artifact-dir ...`
  wires RunSpec → JourneySegmentRunner(CodexCliBackend, AndroidEvidenceCollector,
  DeviceSystemEventInjector) → oracle → verdict. Added `instruction_prefix` seam to
  `JourneySegmentRunner` (driver preamble) and `runner/cli.py` + `__main__.py`.
- Live end-to-end on the defect build: **L1 inconclusive, L2 fail / state_loss**,
  Codex-driven, no manual steps. Run record:
  `docs/runs/2026-07-05-end-to-end-cli-codex/`.
- The end-to-end run surfaced and fixed an **L1 false positive**: real-device logcat
  noise (`E gclu: ...RuntimeException: ManagedChannel...`, caught binder NPE) matched
  L1's loose pattern. Fixed by requiring the `AndroidRuntime` tag + clearing logcat
  at run start. Suite now **183 passed**.

## Progress Update (2026-07-05) — #9 started, 2/5 seeds

M1 Goldset report scaffolded: `docs/M1-goldset-report.md` (coverage matrix by
taxonomy category × oracle path).

- Seed 1 — config-change-01 → **L2 fail / state_loss** (done earlier).
- Seed 2 — lifecycle-04 recreation crash → **L1 fail / crash_stability**, proven
  end-to-end via the CLI (Codex-driven). `UninitializedPropertyAccessException` on a
  `dark_mode` recreation. Run record `docs/runs/2026-07-05-wikipedia-lifecycle-04-recreation-crash/`,
  test `tests/bench/test_goldset_lifecycle_04_crash.py`. Suite 183 -> 187.

Both cheap oracle paths (L1 crash, L2 state) now proven live.

Seed 3 — coroutine-concurrency-03 main-thread ANR → **L1 fail / crash_stability**,
event-less scenario (ANR triggered by typing). Exercised a CLI change: L1 now scans
**all** checkpoint logcats, and event-less scenarios are L2-not-applicable. Run record
`docs/runs/2026-07-05-wikipedia-coroutine-concurrency-03-anr/`. Suite now 190.

**process-death is BLOCKED** (finding, see `docs/M1-goldset-report.md`): Wikipedia
cold-starts to the feed after real process death, not back into SearchActivity, so the
search scenario can't show process-death state loss. Needs a restore-capable screen
(article PageActivity) or a multi-segment re-entry scenario + a background→kill→restore
harness helper.

Seed 4 — navigation-01 double-open crash → **L1 fail / crash_stability**. Tapping the
More nav tab bypasses `ExclusiveBottomSheetPresenter`'s guard and shows the dialog twice
→ `IllegalStateException: Fragment already added`. Event-less. Run record
`docs/runs/2026-07-05-wikipedia-navigation-01-double-open-crash/`. Suite now 193.

**4/5 M1 categories done** (config-change, lifecycle, coroutine-concurrency, navigation).
Only **process-death** remains — BLOCKED on host restore behavior (see
`docs/M1-goldset-report.md`).

## Progress Update (2026-07-06) — #9 COMPLETE: 5/5 seeds, M1 met

Seed 5 — **process-death-02 tab-state loss → L2 fail / state_loss**, matched pair
end-to-end via the CLI (Codex-driven): baseline L2 pass ("2"→"2" tabs), defect L2 fail
("2"→node gone). Run record
`docs/runs/2026-07-06-wikipedia-process-death-02-tab-state-loss/`. Suite now **202
passed** (was 193). **All five M1 categories caught (5/5); the M1 target (≥3/5) is met.**

What unblocked #10 (all verified on device):
- `am kill` needs prior backgrounding (HOME), then pid truly dies.
- The **current article** restores via system saved-state/intent redelivery, NOT
  `Prefs.tabs` — so the valid sentinel is the **tab list** (`tabsCountText` "2"), not
  "the article is still there". The old "cold-starts to feed" finding was
  SearchActivity-specific.
- Defect: `WikipediaApp` tab persistence → in-memory singleton (`commitTabState`/
  `initTabs` no longer touch `Prefs.tabs`); invisible to config changes, fatal to
  process death. Real-world shape K-9 Mail #3970.
- New first-class `process_death` system event: `DeviceController.process_death`
  (HOME → `am kill` → **explicit MAIN+LAUNCHER intent relaunch** — `monkey` is
  nondeterministic on debug builds because LeakCanary adds a second LAUNCHER activity),
  injector `activity` field, whitelist — all unit-tested.
- Driver contract hardened: Codex once crashed the host via `am start -a SEARCH`
  (unsupported intent → real FATAL → L1 false fail on the control). The driver
  preamble now forbids intent-based navigation; reruns were clean.

## Progress Update (2026-07-06) — #12 COMPLETE: L3 semantic oracle exercised

Scoping (owner-confirmed): seed = **ui-rendering semantic error**, judge = **Codex
CLI**. Seed 6 — **ui-rendering-01 nav label swap → L3 fail / ui_rendering**, matched
pair end-to-end via the CLI: baseline **L3 pass** (exit 0), defect **L3 fail**
(confidence 0.97, exit 1); L1/L2 inconclusive by construction (no crash, no boundary
event, no missing node). Run record
`docs/runs/2026-07-06-wikipedia-ui-rendering-01-nav-label-swap/`. Suite now **219
passed** (was 202). All three oracle paths (L1/L2/L3) are now proven live.

What was built:
- `src/aiverify/providers/codex_cli.py`: `CodexCliProvider` implements `LLMProvider`
  via `codex exec` (`provider_id="openai"`, judge sandbox **read-only**, answer +
  event stream persisted under `artifacts/l3-judge/`). Cross-source constraint holds:
  Claude-authored patches (injector) vs openai judge.
- Run-spec: new optional `scenario.l3_spec` — the correct-behavior product spec fed to
  the judge. Deliberately separate from `expected_behavior`, which describes the
  defect run and would leak the answer; the judge never sees it.
- `runner/cli.py`: L3 gating (runs only if `l3_spec` set AND L1/L2 both non-fail),
  `l3` block in verdict.json, `l3-judge` timing phase, `--l3-model` flag, exit-code
  gate includes L3. Judge errors degrade to `L3 inconclusive` (`L3-error`), not a
  crashed run.
- Defect: `NavTab.kt` READING_LISTS/SEARCH string resources swapped — Saved tab shows
  "Search", Search tab shows "Saved" (copy-paste wrong-resource-id shape).
- Regression: `tests/bench/test_goldset_ui_rendering_01_nav_label_swap.py` replays the
  frozen live judge responses through `L3Oracle` + `MockProvider` — hardware- and
  LLM-independent.

## Progress Update (2026-07-07) — #14 COMPLETE: L3 repeatability measured

M2-alpha L3 repeatability on `ui-rendering-01` is measured using fixed evidence from
the #12 matched pair and live Codex CLI judge calls:

- Baseline: **5/5 L3 pass**, `defect_class_hypothesis=null`.
- Defect: **5/5 L3 fail / ui_rendering**.
- Errors/retries/inconclusive verdicts: **0**.
- Confidence range: baseline 0.97-0.98; defect 0.97-0.98.
- Run record: `docs/runs/2026-07-07-l3-repeatability-ui-rendering-01/`.
- Test seam: `tests/bench/test_l3_repeatability.py` covers aggregation/reporting with
  `MockProvider`; live runner is `python -m aiverify.bench.l3_repeatability`.

Interpretation: L3 can contribute to M2 **text-layout semantic** seed metrics when
the fixed-evidence repeatability gate is satisfied. Do not generalize this to
visual-only/multimodal defects or benchmark-wide false-positive/detection rates yet.

## Progress Update (2026-07-07) — #15 COMPLETE: M2 duplicated-state seed added

Seed 7 — **config-change-02 query duplication → L2 fail**, matched pair end-to-end via
the CLI on `emulator-5554` / Android API 36:

- Baseline: `search_src_text` retains `zzsentinelqx` across `dark_mode` → **L2 pass**.
- Defect: restored query is appended to itself (`zzsentinelqxzzsentinelqx`) after
  recreation → **L2 fail**. Current verdict schema reports this as `state_loss`; the
  spec/run record preserve the intended duplicated-state classification.
- Run record: `docs/runs/2026-07-07-wikipedia-config-change-02-query-duplication/`.
- Durable assets: `bench/goldset/{run-specs,specs,fixtures,patches}/wikipedia-config-change-02-query-duplication*`,
  `tests/bench/test_goldset_config_change_02_query_duplication.py`.
- Runner evidence hardening added during the live run: retry transient empty/non-JSON
  Android CLI layout dumps and bound screenshot/logcat capture with explicit timeouts.

Device finding: SearchActivity + soft keyboard/focus can produce noisy recreation
behavior on API 36; the stable scenario presses system Back after typing so the
config-change boundary starts from a focused SearchActivity with the keyboard hidden.

## Progress Update (2026-07-08) — #16 COMPLETE: navigation Back-button seed added

Seed 8 — **navigation-02 Back swallowed → L2 fail**, matched pair end-to-end via
the CLI on `emulator-5554` / Android API 36:

- Baseline: first Back hides the keyboard, second Back returns from SearchActivity
  to the Search tab, and `search_card` remains visible across the `dark_mode`
  observation boundary → **L2 pass**.
- Defect: first Activity-level Back callback is consumed, so after the second Back
  the app remains in SearchActivity with `search_src_text=zznavbackqx`; `search_card`
  is absent across the `dark_mode` observation boundary → **L2 fail**. Current
  verdict schema reports this as `state_loss`; the spec/run record preserve the
  navigation swallowed-Back classification.
- Run record:
  `docs/runs/2026-07-07-wikipedia-navigation-02-back-button-swallowed/`.
- Durable assets:
  `bench/goldset/{run-specs,specs,fixtures,patches}/wikipedia-navigation-02-back-button-swallowed*`,
  `tests/bench/test_goldset_navigation_02_back_button_swallowed.py`.

Device finding: the first defect prelaunch after `pm clear` hit a startup ANR
before the runner began; that attempt is retained in the run record and not used
as evidence. The valid defect run relaunched the same installed APK, confirmed
`nav_tab_search`, cleared logcat, and then ran the assembled runner.

## Progress Update (2026-07-08) — #17 COMPLETE: second L3 search-card seed added

Seed 9 — **ui-rendering-02 Search card copy mismatch → L3 fail / ui_rendering**,
matched pair end-to-end via the CLI on `emulator-5554` / Android API 36:

- Baseline: Search tab `search_card` is visible, `search_text_view=Search Wikipedia`,
  `search_icon` content description is `Search Wikipedia` → **L3 pass**.
- Defect: same `search_card`, `search_text_view`, and `search_icon` nodes remain
  visible, but both visible/accessibility copy say `Track what you've been reading
  here.` → **L3 fail / ui_rendering**.
- L1 and L2 are inconclusive by construction: no crash, no boundary event, no missing
  node.
- Run record:
  `docs/runs/2026-07-08-wikipedia-ui-rendering-02-search-card-copy-mismatch/`.
- Durable assets:
  `bench/goldset/{run-specs,specs,fixtures,patches}/wikipedia-ui-rendering-02-search-card-copy-mismatch*`,
  `tests/bench/test_goldset_ui_rendering_02_search_card_copy_mismatch.py`.

Device finding: the first attempted #17 surface was SearchActivity's empty-state
`search_empty_message`, but that node was not visible in the final accessibility
layout after opening SearchActivity, so L3 correctly returned inconclusive. That
attempt is retained under the run record's discarded probing directory and was not
used as matched-pair evidence.

## Progress Update (2026-07-08) — #18 COMPLETE: L3 repeatability measured for ui-rendering-02

M2 L3 repeatability on `ui-rendering-02` is measured using fixed evidence from the
#17 matched pair and live Codex CLI judge calls:

- Baseline: **5/5 L3 pass**, `defect_class_hypothesis=null`.
- Defect: **5/5 L3 fail / ui_rendering**.
- Errors/retries/inconclusive verdicts: **0**.
- Confidence range: baseline 0.96-0.98; defect 0.96-0.98.
- Run record: `docs/runs/2026-07-08-l3-repeatability-ui-rendering-02/`.
- Runner improvement: `src/aiverify/bench/l3_repeatability.py` now derives the
  fixed-evidence Journey result path from the loaded run spec `scenario.id` instead
  of hard-coding `ui-rendering-01`.

Interpretation: both current text-layout semantic L3 seeds (`ui-rendering-01` and
`ui-rendering-02`) have passed the fixed-evidence repeatability gate. This still does
not support visual-only/multimodal L3 claims or benchmark-wide detection/false-positive
rates.

## Next Issue

Open tracker state:

- **#1 parent PRD is complete/closed** — smoke/M1/L3 progress is recorded with durable evidence.
- **#9 is complete/closed** — M1 report complete, 5/5 caught.
- **#13 M2 scoping** produced the M2-alpha scope and is closed.
- **#14 is complete** — L3 repeatability on the existing `ui-rendering-01` seed is stable 5x/5x per half.
- **#15 is complete/closed** — config-change duplicated-state seed has matched baseline/defect L2 evidence.
- **#16 is complete/closed** — navigation Back-button seed has matched baseline/defect L2 evidence.
- **#17 is complete/closed** — second L3 text-layout semantic seed has matched baseline/defect L3 evidence.
- **#18 is complete/closed** — `ui-rendering-02` L3 repeatability is stable 5x/5x per half.

Recommended execution order:

1. Pick the next M2 seed deliberately: another L2 state/navigation seed, another
   text-layout L3 semantic seed, or a small M2 text-layout L3 summary that records the
   two repeatability-gated seeds and their limits.
2. Do not start broader seed expansion, fully unattended Journey execution, or public
   detection-rate reporting until the #17/#18 evidence is reviewed.

## Next Implementation Issue Discipline

For any new M2 implementation issue:

- create or triage the GitHub issue before starting;
- keep one category role and one state role from `docs/agents/triage-labels.md`;
- add a durable run record under `docs/runs/<date>-<slug>/` for non-trivial verification;
- post issue evidence with exact commands, important results, files/tests, manual or device steps, artifact inventory, checksums where practical, and known gaps;
- commit the code/doc/evidence changes that support the issue comment.

## Execution Notes

Use Android CLI first:

```bash
android run --apks=/Users/peter/hosts/wikipedia/app/build/outputs/apk/dev/debug/app-dev-debug.apk \
  --device=emulator-5554 \
  --activity=org.wikipedia.DefaultIcon

android layout --device=emulator-5554 --pretty -o=<run-dir>/artifacts/layout.json
android screen capture -o=<run-dir>/artifacts/screen.png
android screen capture --annotate -o=<run-dir>/artifacts/screen-annotated.png
```

Use adb where Android CLI lacks precise primitives:

```bash
adb -s emulator-5554 shell settings put system accelerometer_rotation 0
adb -s emulator-5554 shell settings put system user_rotation 1
adb -s emulator-5554 logcat -d -t 200 > <run-dir>/artifacts/logcat-tail.txt
```

Use Codex CLI as the verification backend shape:

```bash
codex exec --json \
  --output-schema src/aiverify/runner/journey_result_schema.json \
  --output-last-message <run-dir>/codex-result.json \
  --skip-git-repo-check \
  --cd /Users/peter/projects/ai_verification \
  --dangerously-bypass-approvals-and-sandbox \
  "<Journey instructions + checkpoint/evidence contract>"
```

Use Codex CLI as the L3 judge shape:

```bash
codex exec --json \
  --output-last-message <run-dir>/artifacts/l3-judge/l3-judge-call-1.md \
  --skip-git-repo-check \
  --sandbox read-only \
  --cd /Users/peter/projects/ai_verification \
  "<L3 spec + observed evidence>"
```

## Evidence Discipline

Follow `AGENTS.md` strictly:

- Non-trivial validation gets a `docs/runs/<date>-<slug>/README.md`.
- Artifacts live under that run directory.
- Issue comments link to the run record and include exact commands/results.
- Important artifacts get SHA-256 checksums.
- Run records and artifacts are committed with the change they justify.
- If something remains local-only or uncommitted, say that explicitly.

## Historical Documents

`.omc/plans/ralplan-ai-behavior-verification.md` is retained as historical context. It describes the broader long-term benchmark vision and old AC1-AC10 acceptance framing, but the current MVP source of truth is:

- GitHub PRD #1 and child issues.
- `CONTEXT.md`.
- ADRs under `docs/adr/`.
- This `HANDOFF.md`.
- Run records under `docs/runs/`.
