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

截至 2026-08-12：

- #58 已由 fresh #80 M3.1 population 的有效证据收口。#80 在冻结的五 seed、
  30 lane 人口上得到 30/30 first-attempt 和 eventual accountability、
  15/15 controls passed、15/15 expected defects caught、0 retries，以及
  30/30 complete execution provenance。
- #59 已按 retrospective pilot 收口。M4 的原始结果保持为两个 accountable
  `locally_supported` case 和一个 `non_accountable` case；M4 早于后来有效的
  #80 gate，因此仍是 chronology exception，不能追认为 entry-gate 顺序合规。
- M5 parent #68 已收口。G-01～G-08 都有稳定 fixture、机器可检查 oracle 与
  committed run record；每项只支持该记录声明范围内的 bounded conclusion。
- M6 已通过 PR #97 完成并关闭 [parent #82](https://github.com/yangliang2/ai_verification/issues/82)。
  已提交的 [M6 aggregate](docs/runs/2026-08-03-issue-88-aggregate/README.md) 固定了
  六个 Qualification Case Packages、36/36 accountable lanes、0 retries 和 6/6
  adjudication agreement；historical 与 prospective populations 仍分开记账。
- M6 的 prospective P-01/P-02 为 `locally_supported`，P-03 因冻结的
  fixture/oracle 内部矛盾保持 `inconclusive`。这不是 M7 scale pass；唯一前进路线是
  `remediate_fixture_execution_oracle_adjudication_gaps`，只适用于未来 admission，
  不改写、不重跑冻结的 P-03。
- M7 parent [#98](https://github.com/yangliang2/ai_verification/issues/98) 已完成
  bounded discovery/admission/runtime slices；#104、#112、#115 的结果都只支持各自
  local fixture、source、device、oracle 和 evidence boundary。
- M8 parent [#117](https://github.com/yangliang2/ai_verification/issues/117) 与
  children #118–#122 已关闭，PR #123–#127 已合入；最终 [PR #127 merge
  `957f108`](https://github.com/yangliang2/ai_verification/commit/957f108d88afd74a8787b42be568ab558c5fb9b1)
  记录了 exact #121 manifest 的正式结果：12/12 lanes 一次性终止于
  `execution-identity-capture`，0/12 accountable，qualification
  `inconclusive`。这不是 runtime PASS/FAIL 结果，且不可重跑、替换或重写。
- M9 parent [#128](https://github.com/yangliang2/ai_verification/issues/128) 的原始
  #136/#137 人口保持不可变：#137 是 install 前 0/6 accountable 的
  `Not Supported`，不形成 runtime claim。
- M9-R recovery 已按 #148 → #150 → #152 → #154 → #157 收口。R2 只证明两条
  historical canary 能走完整链；R3 冻结了全新 3+3 packet；R4 的唯一正式调用在
  `PORTFOLIO_FROZEN` 因 Attack Plan evidence contract 不满足而 fail closed。R5
  机械归约为 pre-runtime `Not Supported`：0/6 accountable、0/6 evidence-valid、
  0/3 defect support、0/3 control rejection、0/6 review，且零 retry/replacement/
  rerun。future-only hardening 已由 [#158](https://github.com/yangliang2/ai_verification/issues/158)
  完成，并通过 PR #160 在 `9dfb19e` 合入；它不授权重跑该 packet，也不建立新的
  formal population 或 runtime claim。

## M8 结果与 M9 边界

M8 的 durable evidence 见
[`docs/runs/2026-08-05-issue-122-formal-execution/README.md`](docs/runs/2026-08-05-issue-122-formal-execution/README.md)。冻结的 #121 manifest
被完整消费：change/project 各 6 条 lane，全部只有一个 terminal attempt；每条 lane
在 execution-identity capture 阶段因 fixture `host_project` 与 runner root policy
不兼容而 `non-accountable`。没有 APK install、launch、agent invocation、Journey、
system event 或 observed state evidence，因此真实 aggregate 是 `0/12 accountable`
与 `inconclusive`。修复提交 `22af9b2` 只说明后续 admission 可修正该 seam，不得用于
重跑这套冻结人口；原始 static migration receipts 也不转化为 Finding。

M9 的正式链为：

```text
ProjectTarget
→ Context Acquisition
→ Hypothesis Portfolio
→ Attack Plan
→ production-seam admission
→ accountable runtime execution
→ Falsification Review
→ Project Risk Map
```

正式模式只接收无 diff 的完整 `ProjectTarget`、immutable source provenance、scope
和 bounded budget；`ChangeTarget` 只做 regression coverage。三项竞争的 Risk Priors
是 synchronous critical-path temporal propagation、state-evolution compatibility
drift、lifetime/ownership drift。正式 cohort 是 `project-defect × 3` 与
`project-control × 3` 的六 lane；一个 incomplete/contradictory context packet
先 fail closed、留在 denominator 外。M9 未形成任何 benchmark-rate、project-
completeness、Android/OEM/ColorOS、production 或 upstream claim。

M9-R 的 durable evidence 分三层：
[R3 fresh freeze](docs/runs/2026-08-07-issue-152-m9-r3-fresh-qualification-freeze/README.md)、
[R4 terminal formal attempt](docs/runs/2026-08-07-m9-r4-formal-attempt-01/formal-execution-summary.json)
与 [R5 reconciliation](docs/runs/2026-08-08-issue-157-m9-r5-reconciliation/README.md)。
R4 先正确拒绝 denominator-external contradiction packet，再完成 Context Acquisition
和三-prior portfolio；它在 mapping release、fresh fixture、device、model 和 runtime
之前终止。六个 terminal rows 是 checksum-bound typed absence，不是六条 runtime
观察。R5 的 `Not Supported` 只说明冻结的 all-or-nothing gate 未通过。

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
- Discovery Campaign boundary ADR：[`docs/adr/0003-discovery-campaign-above-run-spec.md`](docs/adr/0003-discovery-campaign-above-run-spec.md)
- M5 gap register：[`docs/research/2026-07-19-verification-gap-register.md`](docs/research/2026-07-19-verification-gap-register.md)

历史初版计划保留为背景资料，但已经被当前 PRD、ADR、run record 和 GitHub
issue 状态 supersede；不要按旧 AC1-AC10 判断当前能力。

## 历史 M6 资格化收口与 M7 入口

M6 的已完成依赖顺序为：

```text
#83 current claim matrix
  → #84 freeze six-case cohort (human-required)
  → #85 common Qualification Case Package
  → #86 historical track ┐
                         ├→ #88 aggregate, independent audit, M7 decision
  → #87 prospective track┘
```

`#82` parent 与 `#84` cohort freeze 已在 M6 aggregate 合并后完成关闭；冻结的
admission、exclusion/replacement、repetition、retry、identity、blinding 与 claim
rules 仍是历史测量合同。M6 的 historical/prospective 两个 track 永远分开记账，
P-03 的矛盾只进入未来 admission 规则。

M7 的历史依赖为：

```text
#99 ────────────────────────────────┐
                                    ├→ #104 blinded qualification
#100 → (#101 || #102) → #103 ───────┘
```

M7 已按上述依赖完成；没有新的明确授权，不进行任何 upstream comment、task claim、
外部仓库写入或超出本地声明边界的 scale claim。

## M9 source-of-truth contract

M9 的四个 canonical domain terms 是 `Context Acquisition`、`Hypothesis Portfolio`、
`Exploration Stop Rule` 和 `Falsification Review`，定义与既有 `Context Fact`、
`Quality Context Graph`、`Risk Hypothesis`、`Attack Plan`、`Finding`、`Residual Risk`
和 `Project Risk Map` 的关系见 [`CONTEXT.md`](CONTEXT.md)。这些 domain contracts
已被 #129–#157 的实现与证据消费，但 R4/R5 的 pre-runtime `Not Supported` 不证明
该链具备正式 runtime discovery 能力。

M9 只对 ProjectTarget 进行 formal qualification；ChangeTarget 仅用于 regression
coverage。三 priors 必须在一个 Hypothesis Portfolio 中竞争：synchronous critical-
path temporal propagation、state-evolution compatibility drift、以及
lifetime/ownership drift。冻结 population 为六条 `project-defect × 3`、
`project-control × 3` formal lanes，加一个 pre-side-effect rejected、denominator-
external contradiction packet。每条 lane one attempt、zero retry、zero replacement；
Falsification Review 使用 clean context 与 separate invocation identity，并公开
same-family limitation。

M8 的 `0/12 accountable`、`inconclusive` 结果是不可变 evidence；不得以
`22af9b2` 或任何后续代码重跑/替换/改写。所有 M9 结论只能是 exact source/build/
device/operator/backend-model/oracle/review/evidence 范围内的 local-only claim。

M9-R 的 fresh recovery packet 只调用一次。R5 读取 exact R4 merge、验证 R3/R4
账本与 committed auditor mapping，并调用冻结 reducer；10 个 gate 中只有
contradiction pre-side-effect rejection 与 attempt-inventory checksum binding 通过。
原始 R4 summary 的 `formal_holdout_executed=false` 是 runtime 权威事实；R5 reducer
输出中的同名 `true` 只表示它归约了一个 formal attempt，不能解释成 runtime 已开始。
这项字段语义与 pre-runtime inventory reverse-binding gap 已由 #158 future-only
修复并通过 PR #160 在 `9dfb19e` 合入。未来 packet 使用 target-specific preclaim，
pre-runtime row 以 `terminal_absence_receipt` 绑定 canonical ExecutionRecord；归约结果
分别报告 `formal_attempt_reconciled` 与 `runtime_holdout_executed`。这些合同绝不回填
或重跑 #154。

本 issue 复核了 ADR-0001、0002、0003。#129 只补齐 domain vocabulary 与 bounded
qualification boundary，没有新增 hard-to-reverse architecture、provider、data
ownership 或 production-operation decision，因此当前不新增 ADR；若后续实现把
same-family review limitation 变成不可逆系统政策，必须重新评估 ADR 门槛。
