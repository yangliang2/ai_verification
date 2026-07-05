# AI Verification

验证 AI coding 结果是否真的经得起 Android 行为层故障场景，而不是只看静态 diff、单元测试或 happy path。

当前 MVP 的重点不是重造一个裸 LLM provider，也不是立刻做 100+ 缺陷的大规模注入基准；重点是先打通一条可审计的验证链：

```text
run-spec.yaml
→ Codex CLI Verification Agent Backend
→ Android CLI / adb 执行与证据采集
→ Journey Segment Boundary 系统事件注入
→ L1/L2/L3 oracle
→ verdict + run record + issue evidence
```

## 当前范围

### MVP 已对齐的目标

- 使用 **Codex CLI** 作为第一种 Verification Agent Backend，保留真实生产形态的 agent 执行能力。
- 使用 Google **Android CLI** 作为 Android agent-first 操作入口，覆盖 APK 部署、layout/screenshot 采集、docs/skills 查询；adb 作为系统事件和 logcat fallback。
- 使用开源 Android 宿主 **wikimedia/apps-android-wikipedia** 先跑通 smoke/M1，而不是一开始接入 ColorOS 内部构建系统。
- 用 **Run Spec** 描述一次可复现验证运行。
- 在 **Journey Segment Boundary** 注入旋转、后台、权限、网络等行为层事件。
- 把每次非平凡验证写成 `docs/runs/<date>-<slug>/`，并在 GitHub issue 中留下可审计证据。

### 暂不声称完成

- 100+ AI 自动注入缺陷基准。
- M1 五个 Goldset 种子缺陷报告。
- ColorOS 一方应用迁移。
- 完全无人值守的 LLM UI driver。
- 对外可信的抓取率、误报率或全基准吞吐指标。

这些仍是后续方向，但不是当前已验证的 MVP 状态。

## 已验证状态

2026-06-15 AFK implementation pass:

- GitHub PRD: <https://github.com/yangliang2/ai_verification/issues/1>
- 已完成并关闭：#2-#7
- 保留人工语义工作：#8、#9
- Run record: [`docs/runs/2026-06-15-afk-verification/README.md`](docs/runs/2026-06-15-afk-verification/README.md)
- 本地测试：`.venv/bin/pytest` -> `170 passed`

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
  providers/          LLM provider 抽象与异源约束；保留给 planner/oracle/injector 等窄接口
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

**#8 已完整闭环（阴性对照 + 阳性注入，匹配对照）**：

- 阴性对照（baseline）：`run-spec → 段边界注入配置变更 → Android CLI layout → L1/L2 oracle → verdict`，
  查询保留 → **L2=pass**。
- 阳性注入（defect）：`isSaveFromParentEnabled=false` 破坏搜索子树 saved state，
  同一 `dark_mode` 事件下查询丢失 → **L2=fail / state_loss**。
- 关键发现：`SearchActivity` 声明了 `configChanges="orientation|screenSize"`，旋转不重建、
  无法暴露此缺陷；改用**深色模式（uiMode）**配置变更强制重建。为此新增了 `dark_mode` 系统事件
  （`DeviceController.set_night_mode` + injector + 白名单，均有单测）。
- Run records：
  [`.../2026-07-05-wikipedia-config-change-smoke/`](docs/runs/2026-07-05-wikipedia-config-change-smoke/README.md)（pass）、
  [`.../2026-07-05-wikipedia-config-change-01-defect/`](docs/runs/2026-07-05-wikipedia-config-change-01-defect/README.md)（fail）。

下一步是 **#9**：把 smoke slice 扩展到 M1 五个 Goldset 种子报告（`candidates.md` 已有 18 条素材）。
