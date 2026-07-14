# HANDOFF

当前项目范围已经重新对齐：MVP 先验证 **Codex CLI + Android CLI + Wikipedia host** 的行为层 smoke 链路，不再把旧计划里的 “100+ 自动注入缺陷基准” 当作当前完成标准。

## 当前真实状态

### 已完成

- GitHub PRD #1 已完成并关闭: <https://github.com/yangliang2/ai_verification/issues/1>
- GitHub Issues #1-#47（含原 M3 PRD #41）和 remediation #49 已完成并关闭；
  open PRs = 0。新的 remediation/re-baseline PRD #48 及 #50-#57 保持 open，
  均为 `ready-for-agent`。
- 原 M3 报告工作完成，但 milestone criterion 本身因 27/30 accountability
  未达到 29/30 而明确失败；该历史 evidence package 保持不可变。
- #49 已加固 ANR evidence capture。当前应先推进 #50 Journey action lineage；
  #51 仍被 #50 阻塞，#52-#56 依赖 #51，#57 依赖五个新 seed package。
- Run record: [`docs/runs/2026-06-15-afk-verification/README.md`](docs/runs/2026-06-15-afk-verification/README.md)
- Evidence artifacts: [`docs/runs/2026-06-15-afk-verification/artifacts/`](docs/runs/2026-06-15-afk-verification/artifacts/)
- M1 report: [`docs/M1-goldset-report.md`](docs/M1-goldset-report.md)
- M2 text-layout L3 summary: [`docs/M2-l3-text-layout-summary.md`](docs/M2-l3-text-layout-summary.md)
- M2 scoped milestone note: [`docs/M2-scoped-milestone-note.md`](docs/M2-scoped-milestone-note.md)
- M2 metric schema: [`docs/M2-metric-schema.md`](docs/M2-metric-schema.md)
- M2-beta audited report: [`docs/M2-beta-benchmark-slice-report.md`](docs/M2-beta-benchmark-slice-report.md)
- M2-beta evidence-derived aggregate: [`docs/M2-beta-aggregate-summary.md`](docs/M2-beta-aggregate-summary.md)
- Live-validation contract: [`docs/live-validation-gate.md`](docs/live-validation-gate.md)
- Retrospective #11 timing run record: [`docs/runs/2026-07-06-runner-timing-instrumentation/README.md`](docs/runs/2026-07-06-runner-timing-instrumentation/README.md)
- Latest L3 run record: [`docs/runs/2026-07-06-wikipedia-ui-rendering-01-nav-label-swap/README.md`](docs/runs/2026-07-06-wikipedia-ui-rendering-01-nav-label-swap/README.md)
- Latest M2 seed run record: [`docs/runs/2026-07-08-wikipedia-ui-rendering-02-search-card-copy-mismatch/README.md`](docs/runs/2026-07-08-wikipedia-ui-rendering-02-search-card-copy-mismatch/README.md)
- Latest L3 repeatability run record: [`docs/runs/2026-07-08-l3-repeatability-ui-rendering-02/README.md`](docs/runs/2026-07-08-l3-repeatability-ui-rendering-02/README.md)
- Latest live matched-pair run record: [`docs/runs/2026-07-09-wikipedia-process-death-03-oversized-saved-state-matched-pair-retry/`](docs/runs/2026-07-09-wikipedia-process-death-03-oversized-saved-state-matched-pair-retry/)
- Latest runner contract run record: [`docs/runs/2026-07-13-runner-enforced-live-validation-preflight/README.md`](docs/runs/2026-07-13-runner-enforced-live-validation-preflight/README.md)
- Latest accounting run record: [`docs/runs/2026-07-13-m2-beta-evidence-derived-accounting/README.md`](docs/runs/2026-07-13-m2-beta-evidence-derived-accounting/README.md)
- Latest M3 reliability tracer run record: [`docs/runs/2026-07-13-m3-search-card-l3-reliability/README.md`](docs/runs/2026-07-13-m3-search-card-l3-reliability/README.md)
- Final M3 audited baseline: [`docs/runs/2026-07-13-m3-final-reliability-baseline/README.md`](docs/runs/2026-07-13-m3-final-reliability-baseline/README.md)
- Latest M3 remediation record: [`docs/runs/2026-07-13-issue-49-anr-evidence-capture-remediation/README.md`](docs/runs/2026-07-13-issue-49-anr-evidence-capture-remediation/README.md)
- M2-beta current audited slice: 10 included injected-defect seeds, 10 caught,
  10 baseline controls passed; expected oracle split L1=4, L2=4, L3=2.
- Fixed-evidence L3 repeatability remains separate: 2 packages, 20 calls,
  baseline 10/10 pass, defect 10/10 fail, 0 errors.
- M3 ANR tracer result: 6 planned lanes, 4 first-attempt/eventually accountable,
  2 bounded retries, 3/3 accountable controls passed, and 1/1 accountable defect
  caught by L1 as `crash_stability`; two defect lanes exhausted non-accountable.
- M3 oversized saved-state increment: 6 planned lanes, 5 first-attempt and 6
  eventually accountable, 1 bounded retry, 3/3 controls passed, and 3/3 defects
  caught by L1 as `crash_stability` with `TransactionTooLargeException` evidence.
  M3 query-duplication increment: 6 planned lanes, 5 first-attempt and 6
  eventually accountable, 1 bounded retry, 3/3 controls passed, and 3/3 defects
  caught by L2 as `state_loss` with duplicated query evidence.
  M3 swallowed-Back increment: 6 planned lanes, 5 first-attempt and 6 eventually
  accountable, 1 bounded retry, 3/3 controls passed, and 3/3 defects caught by
  L2 as `state_loss` with SearchActivity-vs-Search-tab layout evidence.
  M3 Search-card L3 increment: 6 planned lanes, 5 first-attempt/eventually
  accountable, 1 bounded retry, 3/3 controls passed, and both accountable defects
  caught by L3 as `ui_rendering`; defect repetition 3 exhausted non-accountable
  after two Journey action-name mismatches.
  Final cross-seed aggregate: 30 planned, 24 first-attempt and 27 eventually
  accountable, 6 retries, 15/15 controls passed, and 12/12 accountable defects
  caught at the expected level/class. The audited M3 result is **FAILED** because
  27/30 misses the PRD's 29/30 eventual-accountability threshold.
- #49 ANR evidence-capture remediation now retains bounded best-effort screenshot,
  annotated screenshot, logcat, ordered phase errors, and partial checkpoint
  diagnostics without inventing layout evidence or weakening accountability. The
  historical 27/30 package and exhausted attempt lineage remain unchanged.
- Latest recorded full-suite status: `.venv/bin/pytest` -> `388 passed in 6.78s`.

### 已实测

Android CLI:
- Installed command: `/Users/peter/.local/bin/android`
- Version: `1.0.15498356`
- SDK path from `android info`: `/opt/homebrew/share/android-commandlinetools`
- Confirmed commands: `android update`, `android init`, `android info`, `android layout`, `android layout --diff`, `android screen capture`, `android screen capture --annotate`, `android screen resolve --screenshot`, `android docs`, `android skills`
- Caveat: `android screen resolve` uses `--screenshot`, not `--screen`
- Caveat: `android run` deploys/checks APKs; it does not build missing APKs

Codex CLI:
- Version: `codex-cli 0.144.1`
- Driver backend uses `codex exec --json --output-schema --output-last-message --skip-git-repo-check --cd ... --dangerously-bypass-approvals-and-sandbox` because it must operate Android CLI / adb outside the workspace.
- L3 judge backend uses `codex exec --json --output-last-message --skip-git-repo-check --sandbox read-only --cd ...` because it only reads evidence artifacts.

Wikipedia host:
- Current path: `/Users/peter/hosts/wikipedia` (clean git checkout at `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`)
- Build command: `./gradlew assembleDevDebug --no-daemon`
- Latest M3 build results: Search-card baseline `BUILD SUCCESSFUL in 6s`; defect
  `BUILD SUCCESSFUL in 37s`.
- Preserved APKs: `/Users/peter/hosts/wikipedia/aiverify-builds/m3-search-card-l3/`
- Baseline/defect APK SHA-256: `8e52dce057377b6f1bebb21128af4064c69f9717e5484d084724668bbe66d548` /
  `6711e911634b22e6ce6ccbed5b740b5f347589840c2741a565e028307c17ff8e`.
- Package: `org.wikipedia.dev`
- Launch component used by Android CLI: `org.wikipedia.DefaultIcon`
- Evidence confirms Wikipedia onboarding screen.

### Implemented runner contracts

- `src/aiverify/runner/run_spec.py`: `run-spec.yaml` parsing, validation, dry-run plan.
- `src/aiverify/runner/codex_backend.py`: Codex CLI Verification Agent Backend contract.
- `src/aiverify/runner/journey_result_schema.json`: structured Journey result schema.
- `src/aiverify/runner/evidence.py`: Android CLI layout/screenshot/checkpoint
  evidence capture, including checkpoint-local success/failure manifests and
  bounded retained diagnostics after layout exhaustion.
- `src/aiverify/runner/journey.py`: Journey segment boundary orchestration and
  propagation of partial failed checkpoints into interruption diagnostics.
- `src/aiverify/runner/system_events.py`: system-event injection at boundaries.
- `src/aiverify/runner/verdict.py`: Android CLI layout JSON to L2Oracle verdict;
  Run Specs can select a numeric `scenario.l2_boundary_index` for multi-boundary runs.
- `src/aiverify/runner/cli.py`: end-to-end Run Spec runner, mandatory live-validation
  preflight, execution-accountability envelope, timing, L1/L2/L3 gating, and
  non-zero exit on oracle fail.
- `src/aiverify/providers/codex_cli.py`: Codex CLI-backed `LLMProvider` for L3 semantic judging.
- `src/aiverify/agent/oracle/l1.py`, `l2.py`, `l3.py`: crash/ANR, state assertion, and semantic oracle paths now all exercised live.
- `src/aiverify/harness/device/controller.py`: includes public `press_home()` for backgrounding.
- `src/aiverify/bench/live_validation_gate.py`: generic Android environment gate
  plus explicit host-neutral app-smoke validation.
- `src/aiverify/bench/m2_beta_summary.py`: fail-closed, evidence-derived M2-beta
  outcome accounting over committed verdict and repeatability artifacts.
- `src/aiverify/bench/run_record_checksums.py`: deterministic run-record checksum
  inventory generation and verification, excluding the manifest itself.
- `src/aiverify/bench/m3_reliability.py`: versioned multi-seed M3 lane orchestration,
  bounded attempt lineage, authoritative evidence validation, fail-closed failure
  classification, and deterministic partial-summary generation.
- `src/aiverify/bench/m3_audit.py`: final evidence-derived audit model with
  criteria, oracle, lane, identity, package-integrity, and Markdown breakdowns.

## Current Boundary

Do not claim these are complete yet:

- Full defect-injected end-to-end benchmark.
- 100+ AI-generated source-level defects.
- Benchmark-wide detection rate, benchmark-wide false-positive rate,
  visual/multimodal L3 repeatability, or full-benchmark throughput beyond the
  bounded 10-seed M2-beta slice and text-layout L3 repeatability packages.
- Fully unattended Android Journey execution.
- ColorOS internal app/build migration.
- Multimodal/visual-only L3 judgment.

The current value is concrete but still bounded: the repo has a tested end-to-end
runner, real Android host build/deploy proof, M1 5/5 Goldset detection evidence,
an audited 10-seed M2-beta slice with 10/10 caught and 10/10 passed controls,
live L1/L2/L3 oracle coverage, runner-enforced preflight, fail-closed accounting,
and durable evidence discipline.

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

## Progress Update (2026-07-08) — #19 COMPLETE: M2 text-layout L3 evidence summarized

The two repeatability-gated text-layout semantic L3 seeds are consolidated in
`docs/M2-l3-text-layout-summary.md`:

- `ui-rendering-01`: #12 live matched pair, #14 repeatability.
- `ui-rendering-02`: #17 live matched pair, #18 repeatability.
- Aggregate fixed-evidence repeatability across the two seeds: 20 total calls,
  20 valid verdicts, 0 errors; baselines 10/10 pass; defects 10/10 fail /
  `ui_rendering`; confidence range 0.96-0.98.
- The summary records the judge boundary: `scenario.l3_spec` + observed evidence only,
  not `expected_behavior`, patches, issue text, or frozen verdict fixtures.
- Test coverage:
  `tests/bench/test_m2_l3_text_layout_summary.py` checks summary table values against
  the committed repeatability `summary.json` files and asserts the key limitations are
  present.

Interpretation: the current L3 claim can be stated narrowly as two Wikipedia
text-layout semantic L3 seeds passing fixed-evidence repeatability under Codex CLI
judging. It still does not support visual-only/multimodal L3 reliability or
benchmark-wide detection/false-positive rates.

## Progress Update (2026-07-08) — #20 COMPLETE: M2 scoped milestone note drafted

The current M2-alpha evidence package is now summarized in
`docs/M2-scoped-milestone-note.md`:

- Source issues/evidence are separated into M1 seed-count baseline (#9/#10), L3
  bring-up and repeatability (#12/#14/#17/#18/#19), and M2 seed expansion
  (#15/#16/#17).
- Proven claims are scoped to the audited runner/evidence chain, M1 5/5 seeded
  defect catches, three M2 seed-expansion issues, and two repeatability-gated
  text-layout semantic L3 seeds.
- Explicit non-claims remain benchmark-wide detection rate, false-positive rate,
  visual-only/multimodal L3 reliability, fully unattended Journey reliability,
  100+ AI-generated defects, cross-host/non-Wikipedia generality, ColorOS migration,
  and public throughput/cost metrics.
- Test coverage:
  `tests/bench/test_m2_scoped_milestone_note.py` guards the source evidence links,
  headline repeatability numbers, judge boundary, and recommended next decisions.

Interpretation: #20 is a scoped milestone note, not a new emulator/APK/L3-judge run.
It is the safe handoff artifact for deciding whether to add another seed, clean up
metric/schema language, or harden Journey automation next.

## Progress Update (2026-07-08) — #21 COMPLETE: M2 metric/schema cleanup added

M2 metric language is now separated from oracle verdict classes:

- `docs/M2-metric-schema.md` defines seed detection outcome, oracle outcome, oracle
  defect class, taxonomy category, and taxonomy pattern as separate concepts.
- Run specs now support optional `scenario.metric_context`, parsed into
  `MetricContextSpec` without breaking older specs.
- The runner writes top-level `verdict.json.metric_context` for new runs. This
  carries parsed seed metadata plus computed `seed_outcome`, `oracle_outcomes`,
  `oracle_defect_classes`, and `failed_oracles`.
- The existing L1/L2/L3 oracle verdict schema is unchanged. `defect_class_hypothesis`
  remains the oracle symptom class, not the seed taxonomy/root-cause category.
- M2 run specs with the current ambiguity now carry metric context:
  `wikipedia-config-change-02-query-duplication`, `wikipedia-navigation-02-back-button-swallowed`,
  and `wikipedia-ui-rendering-02-search-card-copy-mismatch`.

Interpretation: future M2 aggregation should use `metric_context.seed_outcome` for
per-seed caught/missed reporting, `metric_context.oracle_defect_classes` for oracle
symptom classes, and `metric_context.taxonomy_category` / `taxonomy_pattern_id` for
seed grouping.

## Progress Update (2026-07-08) — #22 COMPLETE: checkpoint evidence recovery hardened

`AndroidEvidenceCollector` now writes checkpoint-local capture metadata for both
successful and failed checkpoint attempts:

- successful captures write `capture-manifest.json` with checkpoint name, status,
  artifact paths, artifact existence, command count, and no error.
- failed captures still raise `EvidenceCaptureError`, but first persist
  `commands.json` and `capture-manifest.json`.
- failed command entries include phase, args, return code when available, stdout,
  stderr, timeout when applicable, status, and error text.
- layout retries now preserve per-attempt command status, including
  `invalid_output` for transient empty/non-JSON layout dumps.

Interpretation: this improves auditability of evidence-capture failures before more
M2 seed work. It does not make Journey execution fully unattended.

## Progress Update (2026-07-09) — #23-#34 COMPLETE: M2-beta and live-validation gate

The oversized saved-state seed and the first audited M2-beta slice are complete:

- #23 `process-death-03` changed its observation boundary from `dark_mode` to
  `app_to_background`, matching the source failure mode. The valid matched pair
  produced baseline L1 inconclusive / L2 pass and defect L1 fail /
  `crash_stability` with `TransactionTooLargeException`.
- #24-#29 defined M2-beta inclusion rules, backfilled metric context, resolved the
  temporary #23 quarantine, generated the aggregate summary, and published the
  audited benchmark-slice report.
- The resulting slice contains 10 included injected-defect seeds: 10 `caught`,
  10 `passed_control`; L1=4, L2=4, L3=2. Two fixed-evidence L3 repeatability
  packages remain outside the live seed denominator.
- #30-#34 added the generic Android environment gate, an explicit Wikipedia
  target-surface app smoke, a durable current-environment gate run, and the retry
  policy used to safely resume #23.

Durable sources:

- `docs/M2-beta-benchmark-slice-report.md`
- `docs/M2-beta-inclusion-rules.md`
- `docs/runs/2026-07-09-live-validation-gate-current-environment/`
- `docs/runs/2026-07-09-wikipedia-app-smoke-gate/`
- `docs/runs/2026-07-09-wikipedia-process-death-03-oversized-saved-state-matched-pair-retry/`

## Progress Update (2026-07-13) — #35-#40 COMPLETE: execution reliability and evidence accounting

#35 and all child issues are closed:

- #36 makes failed, skipped, incomplete, interrupted, duplicated, reordered, or
  mismatched Journey execution explicitly `non_accountable`; L1/L2/L3 and seed
  outcome accounting do not run for those executions.
- #37 makes live-validation preflight mandatory in the runner before logcat clear,
  host launch, Journey driving, or oracle evaluation. A failure persists gate
  evidence and returns `execution.reason=live_validation_preflight_failed` with
  `seed_outcome=not_accountable`.
- #38 adds deterministic numeric Journey Segment Boundary ordering and optional
  zero-based `scenario.l2_boundary_index`; ambiguous multi-boundary L2 evaluation
  returns explained `inconclusive`.
- #39 replaces manifest-declared M2-beta outcomes with fail-closed accounting from
  committed control/defect verdicts and repeatability summaries. Missing,
  contradictory, mismatched, or non-accountable evidence is rejected.
- #40 adds public run-record checksum generation and verification. The inventory
  covers every retained artifact except `checksums.sha256` itself.

Latest recorded verification after #39: `331 passed`, `0 failed`, with 2 existing
Element truth-value deprecation warnings from `src/aiverify/agent/oracle/l2.py:123`.

## Current Tracker And Next Milestone Decision

GitHub tracker state after the local #42 implementation (issue closure follows the
durable commit):

- #42 implementation and six live lanes are complete locally; run record is linked
  above and final verification is 360 passed with 2 pre-existing warnings;
- open pull requests: **0**;
- #43-#46 become the next independently executable seed tracers after #42 closes.

The next milestone direction is now fixed as **M3 Verification Agent execution
reliability and false-positive baseline**:

- #41 — parent PRD;
- #42 — ANR reliability tracer implemented; close after commit/evidence comment;
- #43 — oversized saved-state L1 reliability; next candidate;
- #44 — query-duplication L2 reliability; next candidate;
- #45 — swallowed-Back L2 reliability; next candidate;
- #46 — Search-card semantic L3 reliability; next candidate;
- #47 — publish the audited 30-lane baseline; blocked by #42-#46.

Execution order: close #42, then #43-#46 may proceed independently, then complete
#47. The planned slice is five seeds × baseline/defect × three
repetitions = 30 live lanes. Its completion thresholds are at least 29/30
eventually accountable lanes, zero false positives among accountable baselines,
and the expected oracle failure/class on every accountable defect lane.

For all M3 work:

- new live evidence must use runner-enforced live-validation preflight;
- interrupted or unhealthy runs remain non-accountable;
- M3 outcomes must be derived from committed evidence, not entered manually;
- new or updated run records should generate and verify `checksums.sha256`;
- preserve first-attempt results separately from eventual results after the
  single bounded retry;
- do not turn the M3 five-seed/30-lane slice into a benchmark-wide
  detection-rate or false-positive-rate claim.

## Next Implementation Issue Discipline

For any M3 implementation issue:

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
