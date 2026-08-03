# AI Verification

验证 AI coding 结果是否经得起 Android 行为层故障场景，而不是只看静态 diff、
单元测试或 happy path。

当前公共验证链为：

```text
Run Spec
→ Codex CLI Verification Agent Backend
→ Android CLI / adb
→ Journey Segment Boundary
→ L1 / L2 / L3 与 capability-specific oracle
→ fail-closed ExecutionRecord
→ Local Conclusion + durable run record
```

项目已有这条链路的可审计实现与多组有界证据，但不因此声称具备 Android 通用
覆盖、benchmark-wide 检测率或 upstream acceptance。当前声明的唯一入口是
[`docs/current-capability-claim-matrix.md`](docs/current-capability-claim-matrix.md)。

## 当前状态

截至 2026-08-02：

- #58 已由 fresh #80 M3.1 population 的有效证据收口。#80 在冻结的五 seed、
  30 lane 人口上得到 30/30 first-attempt 和 eventual accountability、
  15/15 controls passed、15/15 expected defects caught、0 retries，以及
  30/30 complete execution provenance。
- #59 已按 retrospective pilot 收口。M4 的原始结果保持为两个 accountable
  `locally_supported` case 和一个 `non_accountable` case；M4 早于后来有效的
  #80 gate，因此仍是 chronology exception，不能追认为 entry-gate 顺序合规。
- M5 parent #68 已收口。G-01～G-08 都有稳定 fixture、机器可检查 oracle 与
  committed run record；每项只支持该记录声明范围内的 bounded conclusion。
- 当前里程碑是 [M6 parent #82](https://github.com/yangliang2/ai_verification/issues/82)：
  以三个 exact historical pairs 和三个 blinded prospective AI changes 资格化
  Verification Agent，而不是继续增加与真实案例无关的孤立 tracer。

## 当前可支持的有界结论

| 层次 | 有界证据 |
|---|---|
| 公共执行链 | [MVP run](docs/runs/2026-06-15-afk-verification/README.md)、[end-to-end runner](docs/runs/2026-07-05-end-to-end-cli-codex/README.md) |
| fail-closed attempt accounting | [#60 ExecutionRecord/system-event run](docs/runs/2026-07-17-issue-60-execution-record-system-event/README.md) |
| 执行身份 | [#61 Effective Execution Identity run](docs/runs/2026-07-17-issue-61-effective-execution-identity/README.md) |
| 可移植 host identity | [#67 host-locator run](docs/runs/2026-07-18-issue-67-portable-host-locator/README.md) |
| 当前信任 gate | [#80 fresh M3.1 run](docs/runs/2026-07-21-issue-80-m3-fresh/README.md) |
| M4 prospective pilot | [M4 aggregate](docs/runs/2026-07-18-m4-aggregate/README.md) |
| M5 G-01～G-08 | [capability gap register](docs/research/2026-07-19-verification-gap-register.md) |

M1/M2/M3 的历史人口、M4 chronology、M5 各能力切片、未度量方向和明确不声明
事项都在 claim matrix 中逐行记录。不同人口不可合并成一个检测率 denominator。

## 当前不声明

- benchmark-wide detection rate、false-positive rate 或统计置信度；
- Android 通用、cross-host、physical/OEM/device-fleet 或 ColorOS 覆盖；
- fully unattended Journey reliability；
- visual-only/general multimodal L3 reliability；
- prospective task 是 Goldset，或本地结论等于 upstream acceptance；
- M4 满足“先过有效 entry gate、再执行”的时间顺序。

## 历史冻结结果

### M2-beta（截至 2026-07-09）

- [`docs/M2-beta-benchmark-slice-report.md`](docs/M2-beta-benchmark-slice-report.md)
- [`docs/M2-beta-aggregate-summary.md`](docs/M2-beta-aggregate-summary.md)
- 10 included injected-defect seeds, 0 blocked/candidate seeds，10 matched
  baseline controls passed；两个 L3 repeatability-only packages 单独记账。
- #23 oversized saved-state seed 已通过 matched pair 纳入 M2-beta denominator。

### M3/M3.1

- 原 M3 population：27/30 eventually accountable，milestone `FAILED`。
- M3 v2：独立人口 29/30 eventually accountable；保留自身身份边界。
- #62 M3.1 v3：6/30 eventually accountable，`FAILED`，记录保持不可变。
- #80 fresh M3.1：30/30 accountable、15/15 controls、15/15 defects、
  0 retries；这是当前 execution-trust baseline，不覆盖其他 host/backend/fleet。

## 目录结构

```text
src/aiverify/
  providers/          Verification Agent Backend、L3 judge 与异源约束
  harness/device/     Android CLI / adb 设备编排、系统事件与证据采集
  harness/build/      source patch、构建、APK 与缓存能力
  agent/planner/      driver-agnostic Journey 与验证计划
  agent/oracle/       L1/L2/L3 分层 oracle 与 verdict
  runner/             Run Spec、ExecutionRecord、identity、Journey 与 CLI
  bench/              evidence-derived aggregate、审计与 checksum 工具

bench/goldset/        版本化行为层 fixture、Run Spec 与历史素材
docs/adr/             架构决策
docs/agents/          tracker、triage 与 domain 约定
docs/research/        能力研究与 gap register
docs/runs/            committed run record 与 evidence artifact
tests/                contracts、fixtures、aggregates 与文档一致性检查
```

## 本地开发

```bash
uv venv .venv
uv pip install --python .venv/bin/python pytest pyyaml jsonschema
PYTHONPATH=src .venv/bin/python -m pytest
```

Android live run 还需要：

```bash
android update
android init
android info
adb devices
```

具体 Android CLI、Codex CLI、host commit、device 与 package 版本必须从目标 run
record 的 Effective Execution Identity 读取；不要把本机当前环境当成历史运行身份。

## 端到端运行

新 Run Spec 使用可移植 host locator，并绑定预期 origin 与 commit：

```yaml
host_project:
  root: ${WIKIPEDIA_SOURCE}
  origin: https://github.com/wikimedia/apps-android-wikipedia
  commit: 6ccb8d85a21a8e34b96e4813d3caee5c690ece9b
```

可以由 locator 环境变量或显式 override 解析本机路径：

```bash
WIKIPEDIA_SOURCE=/Users/me/hosts/wikipedia \
  PYTHONPATH=src python -m aiverify.runner run-spec.yaml \
  --device emulator-5554 \
  --artifact-dir docs/runs/<slug>/artifacts

PYTHONPATH=src python -m aiverify.runner run-spec.yaml \
  --host-project /Users/me/hosts/wikipedia \
  --device emulator-5554 \
  --artifact-dir docs/runs/<slug>/artifacts
```

runner 在外部副作用前建立持久 ExecutionRecord，并在执行前后校验 source、
worktree、APK、installed binary、device、tool 与 agent role identity。缺失、
漂移或矛盾身份 fail closed；任一 oracle fail 时 CLI 非零退出。

## 文档入口

- 当前声明边界：[`docs/current-capability-claim-matrix.md`](docs/current-capability-claim-matrix.md)
- 当前交接：[`HANDOFF.md`](HANDOFF.md)
- 项目术语：[`CONTEXT.md`](CONTEXT.md)
- Agent 与 Issue 规范：[`AGENTS.md`](AGENTS.md)
- Android CLI-first ADR：[`docs/adr/0001-android-cli-first-execution-base.md`](docs/adr/0001-android-cli-first-execution-base.md)
- Codex CLI backend ADR：[`docs/adr/0002-codex-cli-as-verification-agent-backend.md`](docs/adr/0002-codex-cli-as-verification-agent-backend.md)
- M5 gap register：[`docs/research/2026-07-19-verification-gap-register.md`](docs/research/2026-07-19-verification-gap-register.md)

历史初版计划保留为背景资料，但已经被当前 PRD、ADR、run record 和 GitHub
issue 状态 supersede；不要按旧 AC1-AC10 判断当前能力。

## 下一步：M6 qualification

依赖顺序为：

```text
#83 current claim matrix
  → #84 freeze six-case cohort (human-required)
  → #85 common Qualification Case Package
  → #86 historical track ┐
                         ├→ #88 aggregate, independent audit, M7 decision
  → #87 prospective track┘
```

正式执行前必须先完成 #84：冻结 admission、exclusion/replacement、repetition、
retry、identity、blinding 与 claim rules。M6 的 historical/prospective 两个
track 永远分开记账；没有新的明确授权，不进行任何 upstream comment、task claim
或 pull request。
