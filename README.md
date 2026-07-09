# AI Verification

验证 AI coding 结果是否真的经得起 Android 行为层故障场景，而不是只看静态 diff、单元测试或 happy path。

当前 MVP 已经打通一条可审计的验证链；下一阶段不是重造一个裸 LLM provider，也不是直接跳到 100+ 缺陷的大规模注入基准，而是先把已验证链路扩展成可度量的 M2 基准范围：

```text
run-spec.yaml
→ Codex CLI Verification Agent Backend
→ Android CLI / adb 执行与证据采集
→ Journey Segment Boundary 系统事件注入
→ L1/L2/L3 oracle
→ verdict + run record + issue evidence
```

## 当前范围

### MVP 已验证能力

- 使用 **Codex CLI** 作为第一种 Verification Agent Backend，保留真实生产形态的 agent 执行能力。
- 使用 Google **Android CLI** 作为 Android agent-first 操作入口，覆盖 APK 部署、layout/screenshot 采集、docs/skills 查询；adb 作为系统事件和 logcat fallback。
- 使用开源 Android 宿主 **wikimedia/apps-android-wikipedia** 跑通 smoke/M1，而不是一开始接入 ColorOS 内部构建系统。
- 用 **Run Spec** 描述一次可复现验证运行，并通过 `python -m aiverify.runner` 产出 verdict。
- 在 **Journey Segment Boundary** 注入配置变更、进程死亡等行为层事件。
- 用 M1 五个 Goldset-derived Behavior-Layer Defect 证明 L1/L2 oracle 能抓住 crash、ANR、state loss。
- 用第六个 ui-rendering seed 证明 L3 semantic oracle 能抓住 L1/L2 不可见的语义 UI 错误。
- 把每次非平凡验证写成 `docs/runs/<date>-<slug>/`，并在 GitHub issue 中留下可审计证据。

### 暂不声称完成

- 100+ AI 自动注入缺陷基准。
- M2/M3 级别的多种子检测率基准。
- ColorOS 一方应用迁移。
- 完全无人值守的 LLM UI driver。
- 对外可信的抓取率、误报率或全基准吞吐指标。
- 视觉/多模态 L3 稳定性或全基准吞吐指标。

这些仍是后续方向，但不是当前已验证的 MVP 状态。

## 已验证状态

截至 2026-07-09：

- GitHub PRD #1 已完成并关闭：<https://github.com/yangliang2/ai_verification/issues/1>
- M2-beta PRD #24 已完成子 issue #25-#29，并产出 audited benchmark slice report。
- Run record: [`docs/runs/2026-06-15-afk-verification/README.md`](docs/runs/2026-06-15-afk-verification/README.md)
- M1 report: [`docs/M1-goldset-report.md`](docs/M1-goldset-report.md)
- M2-beta report: [`docs/M2-beta-benchmark-slice-report.md`](docs/M2-beta-benchmark-slice-report.md)
- M2-beta aggregate summary: [`docs/M2-beta-aggregate-summary.md`](docs/M2-beta-aggregate-summary.md)
- M2-beta inclusion rules: [`docs/M2-beta-inclusion-rules.md`](docs/M2-beta-inclusion-rules.md)
- M2-beta #23 quarantine note: [`docs/M2-beta-oversized-saved-state-quarantine.md`](docs/M2-beta-oversized-saved-state-quarantine.md)
- M2 text-layout L3 summary: [`docs/M2-l3-text-layout-summary.md`](docs/M2-l3-text-layout-summary.md)
- M2 scoped milestone note: [`docs/M2-scoped-milestone-note.md`](docs/M2-scoped-milestone-note.md)
- M2 metric schema: [`docs/M2-metric-schema.md`](docs/M2-metric-schema.md)
- L3 run record: [`docs/runs/2026-07-06-wikipedia-ui-rendering-01-nav-label-swap/`](docs/runs/2026-07-06-wikipedia-ui-rendering-01-nav-label-swap/README.md)
- Latest M2 seed run record: [`docs/runs/2026-07-08-wikipedia-ui-rendering-02-search-card-copy-mismatch/`](docs/runs/2026-07-08-wikipedia-ui-rendering-02-search-card-copy-mismatch/README.md)
- Latest L3 repeatability run record: [`docs/runs/2026-07-08-l3-repeatability-ui-rendering-02/`](docs/runs/2026-07-08-l3-repeatability-ui-rendering-02/README.md)
- 当前 M2-beta aggregate：9 included injected-defect seeds, 1 blocked/candidate seed, 2 repeatability-only packages。
- 本地测试：`.venv/bin/pytest` -> `281 collected, exit 0, 2 warnings`

Wikipedia host 实测：

- Host path: `/Users/peter/hosts/wikipedia`
- Host commit: `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`
- Build: `./gradlew assembleDevDebug --no-daemon` -> `BUILD SUCCESSFUL in 9m 48s`
- APK: `/Users/peter/hosts/wikipedia/app/build/outputs/apk/dev/debug/app-dev-debug.apk`
- Package: `org.wikipedia.dev`
- Android CLI deploy: `android run --apks=... --device=emulator-5554 --activity=org.wikipedia.DefaultIcon`
- Evidence artifacts: [`docs/runs/2026-06-15-afk-verification/artifacts/`](docs/runs/2026-06-15-afk-verification/artifacts/)

## 目录结构

```text
src/aiverify/
  providers/          LLM provider 抽象、Codex CLI L3 judge、异源约束
  harness/device/     adb 设备编排、系统事件原语、logcat/UI dump
  harness/build/      patch、批量构建、APK 缓存等后续基准能力
  agent/planner/      driver-agnostic 验证计划 schema 与 generator
  agent/oracle/       L1/L2/L3 分层判定与 verdict schema
  runner/             当前 MVP runner contracts
    run_spec.py       单次验证运行输入契约
    codex_backend.py  Codex CLI backend contract
    evidence.py       Android CLI evidence checkpoints
    journey.py        Journey segment boundary 编排
    system_events.py  runner 到 DeviceController 的系统事件注入
    cli.py            Run Spec 到 Codex driver、evidence、L1/L2/L3 verdict 的端到端入口
    verdict.py        Android CLI layout JSON 到 L2Oracle verdict

bench/goldset/        真实历史行为层缺陷候选素材
docs/adr/             当前架构决策
docs/agents/          agent/issue tracker/triage 约定
docs/runs/            可审计运行记录与 evidence artifacts
```

## 本地开发

```bash
uv venv .venv
uv pip install --python .venv/bin/python pytest pyyaml jsonschema
.venv/bin/pytest
```

Android smoke 需要额外环境：

```bash
android update
android init
android info
adb devices
```

当前实测 Android CLI 版本为 `1.0.15498356`，Codex CLI 版本为 `codex-cli 0.139.0`。

## 端到端运行（Codex CLI backend）

把一份 run-spec 从头跑到 verdict，无需手动驱动：Codex CLI 作为 Verification Agent
Backend 驱动应用，runner 注入行为层事件并采证据，oracle 判定：

```bash
PYTHONPATH=src python -m aiverify.runner \
  bench/goldset/run-specs/wikipedia-config-change-01-defect.yaml \
  --device emulator-5554 \
  --artifact-dir docs/runs/<slug>/artifacts
```

任一 oracle（L1/L2/L3）返回 `fail` 时进程以非零码退出（便于 CI gate）。实测见
[`docs/runs/2026-07-05-end-to-end-cli-codex/`](docs/runs/2026-07-05-end-to-end-cli-codex/README.md)
和 [`docs/runs/2026-07-06-wikipedia-ui-rendering-01-nav-label-swap/`](docs/runs/2026-07-06-wikipedia-ui-rendering-01-nav-label-swap/README.md)。

## 文档入口

- 项目语言与术语：[`CONTEXT.md`](CONTEXT.md)
- 当前交接和下一步：[`HANDOFF.md`](HANDOFF.md)
- Agent 工作规范：[`AGENTS.md`](AGENTS.md)
- Android CLI execution ADR：[`docs/adr/0001-android-cli-first-execution-base.md`](docs/adr/0001-android-cli-first-execution-base.md)
- Codex CLI backend ADR：[`docs/adr/0002-codex-cli-as-verification-agent-backend.md`](docs/adr/0002-codex-cli-as-verification-agent-backend.md)
- Host app 选型：[`docs/host-app-selection.md`](docs/host-app-selection.md)
- 历史初版计划：[`.omc/plans/ralplan-ai-behavior-verification.md`](.omc/plans/ralplan-ai-behavior-verification.md)

历史初版计划保留为背景资料，但已经被当前 PRD #1、ADR、run record 和 GitHub issue 状态 supersede；不要按旧 AC1-AC10 直接判断当前 MVP 是否完成。

## 下一步

当前 M2-beta 入口：

- #24：M2-beta audited aggregate benchmark slice PRD。
- #25：M2-beta inclusion rules 已完成；定义 included/control/repeatability-only/candidate/blocked/excluded accounting。
- #26：M2-beta metric context backfill 已完成；M1/M2 seed run specs 可被 aggregate 读取。
- #27：#23 oversized saved-state seed 已 quarantine 出 M2-beta denominator；#23 本身保持 open，等待稳定设备 matched pair。
- #28：M2-beta aggregate summary path 已完成；`python -m aiverify.bench.m2_beta_summary` 可生成汇总。
- #29：M2-beta final benchmark-slice report 已完成。

此前 M2-alpha / M2-follow-up 的入口：

- #14：`ui-rendering-01` 的 L3 repeatability 已完成；fixed evidence 下 baseline 5/5 pass、defect 5/5 fail/ui_rendering。
- #15：config-change duplicated-state Goldset seed 已完成；baseline L2 pass、defect L2 fail，覆盖“恢复时叠加/重复”模式。
- #13：M2 scoping 已给出第一轮范围，作为 M2-alpha 的决策记录。
- #9：M1 five-Goldset report 已完成并关闭。
- #1：父 PRD 已完成并关闭。
- #16：navigation back-button Goldset seed 已完成；baseline L2 pass、defect L2 fail，覆盖“Back 被吞掉 / 需要额外返回一次”的非崩溃导航状态缺陷。
- #17：第二个 L3 text-layout semantic seed 已完成；Search tab `search_card` baseline L3 pass、defect L3 fail/ui_rendering。
- #18：`ui-rendering-02` 的 L3 repeatability 已完成；fixed evidence 下 baseline 5/5 pass、defect 5/5 fail/ui_rendering。
- #19：M2 text-layout L3 小结已完成；记录两个 repeatability-gated seed 的可用范围和限制。
- #20：M2 scoped milestone note 已完成；把 M1 seed-count、M2 seed expansion、text-layout L3 repeatability 和剩余 benchmark gap 分开记录。
- #21：M2 metric/schema cleanup 已完成；新增 `scenario.metric_context` 和顶层 `verdict.json.metric_context`，把 seed outcome、oracle symptom class、taxonomy category 分开。
- #22：checkpoint evidence recovery hardening 已完成；成功/失败的 evidence capture 都会写 `capture-manifest.json`，失败时也保留 `commands.json`。

推荐下一步继续扩展新的 M2 seed，或用 `metric_context` 做一个 aggregate M2 report。
