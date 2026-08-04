# AI Verification 当前能力与声明矩阵

更新时间：2026-08-04

本矩阵是当前里程碑声明的入口。它把“仓库中存在实现”与“已有可审计证据
支持某个声明”分开，并使用以下状态：

- **有界证据支持**：存在稳定 fixture、机器可检查 oracle、匹配运行、身份与
  checksum 证据；结论只适用于该记录声明的 host、设备、配置和行为。
- **non_accountable**：存在候选或运行记录，但缺少形成行为结论所需的可信证据。
- **尚未度量**：方向与能力可能存在，尚无合格人口支持项目级声明。
- **当前不声明**：证据范围明确不支持该泛化。

## 公共验证链与信任基础

| 能力 | 状态 | 当前证据 | 声明边界 |
|---|---|---|---|
| Run Spec → Codex CLI Verification Agent Backend → Android CLI/adb → Journey Segment Boundary → L1/L2/L3 | 有界证据支持 | [MVP run](runs/2026-06-15-afk-verification/README.md)、[end-to-end runner](runs/2026-07-05-end-to-end-cli-codex/README.md) | Wikipedia 与已提交 fixture；不是通用 Android 或完全无人值守证明 |
| fail-closed ExecutionRecord 与 system-event accounting | 有界证据支持 | [#60 run](runs/2026-07-17-issue-60-execution-record-system-event/README.md) | 公共 Run Spec runner；历史 evidence 不回填 |
| Effective Execution Identity | 有界证据支持 | [#61 run](runs/2026-07-17-issue-61-effective-execution-identity/README.md) | 绑定实际 Run Spec、source、APK/安装态、device、tool、backend/model |
| portable、identity-bound host locator | 有界证据支持 | [#67 run](runs/2026-07-18-issue-67-portable-host-locator/README.md) | 声明的 source origin/commit 与解析后的本机路径 |
| attempt-complete 可靠性 gate | 有界证据支持 | [#80 fresh M3.1 run](runs/2026-07-21-issue-80-m3-fresh/README.md) | Wikipedia、Codex CLI、单台 API 35 emulator、五 seed/30 lane 人口 |

#80 的冻结人口结果为 30/30 first-attempt 和 eventual accountability、15/15
baseline controls passed、15/15 defect lanes 在预注册 oracle/class 被捕获、0
retry、30/30 complete execution provenance。五个 package checksum inventory
共 743/743 entries，run-root inventory 769/769 entries；唯一独立 Verification
Agent 的结论为 `locally_supported`。

## 基准与里程碑人口

| 人口 | 状态 | 原始结果 | 可以声明 | 不可以声明 |
|---|---|---|---|---|
| M1 five-seed report | 有界证据支持 | 五个 Goldset-derived Behavior-Layer Defect 均有对应 L1/L2 行为证据 | 五个已记录 seed 的端到端可执行性 | 完整 Goldset 或基准检测率 |
| M2-beta injected slice | 有界证据支持 | 10 included candidates caught；10 matched controls passed；另有两个 L3 repeatability-only packages | 版本化十 seed slice 的 evidence-derived accounting | benchmark-wide rate、视觉/多模态 L3 |
| 原 M3 population | 有界失败证据 | 27/30 eventually accountable；milestone FAILED | 失败结果与已问责 lane 的原始观察 | 用后续人口覆盖或重写失败 |
| M3 v2 population | 有界证据支持但身份受限 | 29/30 eventually accountable；旧标准 PASSED | 独立的 v2 人口结果 | 与其他 30-lane 人口合并；完整 execution identity |
| #62 M3.1 v3 population | 有界失败证据 | 6/30 eventually accountable；FAILED | stale identity/环境失败的不可变记录 | M4 entry gate PASS |
| #80 fresh M3.1 population | 有界证据支持 | 30/30 accountable；15 controls passed；15 defects caught | 当前执行信任 gate 在声明范围内通过 | 跨 host、跨 backend、设备 fleet 或 benchmark-wide reliability |
| M4 prospective pilot | 2 个有界支持 + 1 个 non_accountable | T426553、T426989 `locally_supported`；T409797 `non_accountable`；T337177 excluded | 三个 admitted case 的原始本地结论与操作事实 | detection/false-positive rate、Goldset、upstream acceptance、原 entry gate 顺序合规 |
| M6 blinded AI-change qualification | aggregate integrity PASS；M7 scale gate 未通过 | 6 个 frozen packages、36/36 lanes accountable、0 retries、6/6 adjudication agreement；historical 18 lanes 保持独立；prospective P-01/P-02 `locally_supported`，P-03 `inconclusive` | 六个 package、各自 track denominator、P-03 contradiction 与单一路线的本地事实 | M7 scale pass、benchmark-wide detection/false-positive rate、P-03 修复或重跑、upstream acceptance |

M4 的实现和 aggregate 已提交，但执行时间早于后来有效的 #80 gate。#59 以
retrospective pilot 加明确 chronology exception 关闭；该历史事实不能被后来的
PASS 追认为顺序合规。

## M5 Android 能力切片

所有条目都只表示对应 fixture、Journey、oracle 和设备记录上的
`locally_supported`/匹配候选拒绝能力，不表示 Android 通用覆盖。

| Gap | 能力切片 | 状态 | 证据与已观察结果 | 主要未覆盖范围 |
|---|---|---|---|---|
| G-01 | offline、timeout、bounded retry、cache/response ordering | 有界证据支持 | [#69](runs/2026-07-19-issue-69-network-reliability/README.md)：baseline pass；candidate 检出 `retry_storm` 与 `stale_response_overwrite` | 真实 Wikipedia 网络、任意 timing、production networking |
| G-02 | permission denial、permanent denial、Settings revocation | 有界证据支持 | [#70](runs/2026-07-19-issue-70-runtime-permission/README.md)：baseline graceful fallback；candidate crash/state failure | 单一 debug fixture/API 35；不是安全认证或兼容矩阵 |
| G-03 | rotation、background/process death、backup/restore migration | 有界证据支持 | [#71](runs/2026-07-19-issue-71-lifecycle-backup-recovery/README.md)：baseline correct restoration；candidate stale migration rejected | cloud transport、设备/API matrix、普遍备份正确性 |
| G-04 | locale/RTL/orientation/form-factor matrix | 有界证据支持 | [#72](runs/2026-07-20-issue-72-compatibility-matrix/README.md)：4/4 baseline cells supported；forced-LTR candidate 在 3 个 Arabic cells 被拒绝 | 其他 API、foldable posture、font scale、night mode、OEM/physical device |
| G-05 | accessibility semantics、order、touch targets、contrast | 有界证据支持 | [#73](runs/2026-07-20-issue-73-accessibility/README.md)：3/3 baseline checkpoints；missing-name candidate rejected | WCAG certification、完整 ATF/TalkBack/辅助技术、physical/OEM fleet |
| G-06 | cold start、frozen frame、storage/battery pressure | 有界证据支持 | [#74](runs/2026-07-20-issue-74-performance-intent/README.md)：baseline thresholds supported；frozen-frame candidate rejected | fleet performance、耗电归因、长期 pressure/thermal |
| G-07 | nested Intent、exported boundary、immutable one-shot token | 有界证据支持 | [#74](runs/2026-07-20-issue-74-performance-intent/README.md)：unsafe nested-Intent candidate rejected；组件边界与 token receipts retained | 一般 Android 安全、渗透测试、认证结论 |
| G-08 | deterministic ordering、cancellation、destroy lifecycle race | 有界证据支持 | [#78](runs/2026-07-21-issue-78-deterministic-concurrency/README.md)：baseline supported；stale/destroy candidates rejected | stress/fuzz、真实网络并发、一般并发正确性 |

## M6 收口与 M7 forward boundary

M6 已通过 PR #97 完成，parent [#82](https://github.com/yangliang2/ai_verification/issues/82)
与 cohort freeze [#84](https://github.com/yangliang2/ai_verification/issues/84) 已关闭。
完整输入、逐 lane 观察、独立审计和 checksum 见
[M6 aggregate](runs/2026-08-03-issue-88-aggregate/README.md)。

P-03 的 `inconclusive` 原因是冻结 fixture/oracle contract 内部矛盾；它保持冻结，
不被替换、修复或重跑。唯一 forward route 是
`remediate_fixture_execution_oracle_adjudication_gaps`：任何未来 formal discovery
experiment 在 hypothesis、fixture、expected evidence、oracle 或 claim boundary
缺失或矛盾时，必须在外部副作用前 fail closed。这条路线不构成 M7 scale pass。

## 尚未度量与当前不声明

| 项目 | 状态 | 进入声明所需条件 |
|---|---|---|
| M7 project/change risk-discovery qualification | 有界证据支持（discovery/admission/evidence seam） | [#104 run](runs/2026-08-04-issue-104-m7-qualification/README.md)：冻结 4-cell/12-lane；12/12 accountable、0 retries、12/12 admitted attacks、12/12 independent adjudication；contradictory preflight 在 formal denominator 外 fail-closed | 仅 local fixture 与离线 seam；下一步 bounded runtime probe；不声明 Android runtime、benchmark-wide rate、项目完整覆盖或 upstream acceptance |
| benchmark-wide detection/false-positive rate | 当前不声明 | 合格且足够规模的独立 ground-truth population 与预注册统计契约 |
| physical/OEM/device-fleet 与 ColorOS | 当前不声明 | 独立的设备/host admission、身份、矩阵与 durable evidence |
| fully unattended Journey reliability | 当前不声明 | 无 agent-in-the-loop 的版本化执行人口和 accountability 测量 |
| visual-only/general multimodal L3 | 当前不声明 | 视觉 ground truth、repeatability、false-positive controls 与独立审计 |
| upstream acceptance | 当前不声明 | 本仓库本地结论不等于 maintainer review 或 merge |

## M7 qualification boundary and next route

M7 #104 的冻结离线 qualification 已完成。它证明 change 与 complete-project
两种入口都能经过 Context Expansion、Risk Hypothesis freeze、Attack Plan
admission、accountable Attempt Evidence、Finding/Residual Risk reduction 和
独立 adjudication；四个 cell 各 3 次，合计 12/12 accountable，0 retries。输入
packet 的 variant、expected evidence、verdict 和 outcome 均保持盲化；P-03-class
contradictory context 在正式 invocation 前被排除且不进入 denominator。

这个结果只支持 `proceed_to_bounded_runtime_probe`。它不提供 Android runtime
执行结果、缺陷检测率、误报率、项目完整性或 upstream acceptance 声明。

## 当前下一步

M7 parent [#98](https://github.com/yangliang2/ai_verification/issues/98) 验证
“AI 能力能否围绕软件工程质量契约，针对 change/project target 发现可复核、可攻击
的风险假设”。已完成的执行顺序为：

`#99 → (#101 与 #102) → #103 → #104`

#100 定义了 Discovery Campaign 与 Run Spec 的边界；#101/#102 并行完成，#103
负责编排，#104 完成 qualification。下一步应另行冻结并 admission 一个有界 runtime
probe；M7 继续保持 local-only claim boundary，不把任何 discovery finding 写成
upstream acceptance 或 benchmark-wide rate。
