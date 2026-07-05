# HANDOFF

当前项目范围已经重新对齐：MVP 先验证 **Codex CLI + Android CLI + Wikipedia host** 的行为层 smoke 链路，不再把旧计划里的 “100+ 自动注入缺陷基准” 当作当前完成标准。

## 当前真实状态

### 已完成

- GitHub PRD: <https://github.com/yangliang2/ai_verification/issues/1>
- 已关闭 agent-ready issues: #2, #3, #4, #5, #6, #7
- 已保留 human-required issues: #8, #9
- Run record: [`docs/runs/2026-06-15-afk-verification/README.md`](docs/runs/2026-06-15-afk-verification/README.md)
- Evidence artifacts: [`docs/runs/2026-06-15-afk-verification/artifacts/`](docs/runs/2026-06-15-afk-verification/artifacts/)
- Test status: `.venv/bin/pytest` -> `170 passed`

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
- Confirmed flags: `codex exec --json --output-schema --output-last-message --sandbox --ask-for-approval --cd`

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
- `src/aiverify/harness/device/controller.py`: includes public `press_home()` for backgrounding.

## Current Boundary

Do not claim these are complete yet:

- First Wikipedia config-change Goldset seed (#8).
- M1 five-Goldset report (#9).
- Full defect-injected end-to-end benchmark.
- 100+ AI-generated source-level defects.
- Detection rate, false-positive rate, or full-benchmark throughput.
- Fully unattended Android Journey execution.
- ColorOS internal app/build migration.

The current value is narrower but concrete: the repo now has a tested runner contract, a real Android host build/deploy proof, and durable evidence discipline.

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

Both cheap oracle paths (L1 crash, L2 state) now proven live. Remaining M1 seeds:
process-death, navigation, coroutine-concurrency (see the report for candidate
patterns + the process-death reliability note).

## Next Issue

Continue **#9**: seeds 3-5 (process-death, navigation, coroutine-concurrency).

Recommended seed shape:

```text
Open a page with editable/search state
→ enter sentinel text
→ inject config-change/rotation at a Journey Segment Boundary
→ capture Android CLI layout/screenshot before and after
→ use L2Oracle to assert the sentinel state is retained or not duplicated
→ write verdict and run record
```

Keep it deliberately simple. Avoid coroutine race, background process death, or deep navigation for the first seed; those add trigger instability before the evidence loop is proven.

## Expected #8 Deliverables

- Goldset patch under `bench/goldset/patches/`.
- Goldset spec under `bench/goldset/specs/`.
- A `run-spec.yaml` example or fixture for the smoke run.
- A durable run record under `docs/runs/<date>-wikipedia-config-change-smoke/`.
- GitHub issue comments with commands, outputs, artifacts, checksums, and known gaps.
- A commit containing the implementation, run record, and evidence artifacts, unless there is a clear reason not to commit.

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
  --sandbox danger-full-access \
  --ask-for-approval never \
  --cd /Users/peter/projects/ai_verfication \
  "<Journey instructions + checkpoint/evidence contract>"
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
