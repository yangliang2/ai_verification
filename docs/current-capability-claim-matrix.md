# AI Verification 当前能力与声明矩阵

更新时间：2026-08-05

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
| M8 state-evolution formal qualification | 有界失败证据；`inconclusive` | exact #121 manifest 进入 #122；12/12 ordered terminal attempts、0/12 accountable、change/project 分母 0/6 各自成立；共同原因是 execution-identity capture 的 fixture `host_project` 与 runner root policy mismatch | 冻结人口的 admission/accountability 失败事实与不可重跑边界 | state-evolution runtime detection、migration correctness、M7 合并、Android/OEM/production 或 benchmark-wide claim |
| M9 unseen-project adversarial discovery | 有界失败证据；`Not Supported`；不形成 runtime claim | exact #136 merge 进入 #137；contradiction packet pre-side-effect rejected；Context Acquisition partial (64 facts)；top-3 portfolio、Attack Plan、leakage audit passed；6/6 ordered terminal lanes，0/6 accountable，0/3 defect support，0/3 control rejection，6/6 independent reviews，0 retries/replacements；共同原因是 fresh emulator 上 package-clear 在 install 前返回 `Failed` | 冻结 M9 population 的 gate、admission、accountability、non-accountable lane 和 independent-review facts | M9 runtime detection/rejection、project completeness、benchmark rate、Android/OEM/ColorOS、production/upstream acceptance |

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

## M6 收口、M7 forward boundary 与 M8 结果

M6 已通过 PR #97 完成，parent [#82](https://github.com/yangliang2/ai_verification/issues/82)
与 cohort freeze [#84](https://github.com/yangliang2/ai_verification/issues/84) 已关闭。
完整输入、逐 lane 观察、独立审计和 checksum 见
[M6 aggregate](runs/2026-08-03-issue-88-aggregate/README.md)。

P-03 的 `inconclusive` 原因是冻结 fixture/oracle contract 内部矛盾；它保持冻结，
不被替换、修复或重跑。唯一 forward route 是
`remediate_fixture_execution_oracle_adjudication_gaps`：任何未来 formal discovery
experiment 在 hypothesis、fixture、expected evidence、oracle 或 claim boundary
缺失或矛盾时，必须在外部副作用前 fail closed。这条路线不构成 M7 scale pass。

M7 parent [#98](https://github.com/yangliang2/ai_verification/issues/98) 的 source-of-truth
由 #99 收口，#100 定义 Discovery Campaign 与 Run Spec 的边界；#101/#102、#103、#104
以及 #112/#115 的历史结果见下方。保留这些入口用于追溯，不把它们与 M8/M9 denominator
合并。

M8 parent #117 与 children #118–#122 已通过 PR #123–#127 合入；最终 PR #127 的
merge 是 `957f108`。#122 的 12 条 lane 各执行一次并在
`execution-identity-capture` 终止为 `non-accountable`，没有 install、launch、agent、
Journey、system-event 或 observed-state evidence。因此 M8 的真实 aggregate 是
`0/12 accountable`、`inconclusive`，不能被写成 runtime supported/rejected。修复
提交 `22af9b2` 未用于重跑、替换、修改 fixture、修改 oracle 或重写该 frozen
population；未来若重新度量必须新建并冻结 cohort/contract。

## 尚未度量与当前不声明

| 项目 | 状态 | 进入声明所需条件 |
|---|---|---|
| M7 project/change risk-discovery qualification | 有界证据支持（discovery/admission/evidence seam） | [#104 run](runs/2026-08-04-issue-104-m7-qualification/README.md)：冻结 4-cell/12-lane；12/12 accountable、0 retries、12/12 admitted attacks、12/12 independent adjudication；contradictory preflight 在 formal denominator 外 fail-closed | 仅 local fixture 与离线 seam；不声明 benchmark-wide rate、项目完整覆盖或 upstream acceptance |
| M7-R1 synchronous-critical-path runtime probe | 有界证据支持（单一 API-35 emulator、Change Mode） | [#112 run](runs/2026-08-04-issue-112-runtime-admission/README.md)：defect/control 各 3 次，6/6 accountable、0 retries；defect 3/3 `locally_supported`（250 ms main-thread delay），control 3/3 `locally_rejected`；APK、ExecutionRecord、effective identity、截图/layout/logcat 与 oracle 均 checksum-bound | 仅该 fixture、TemporalActivity、API-35 AVD 与 200 ms temporal contract；不声明 ANR rate、OEM/SystemUI、physical fleet、Project Mode 或通用 Android 能力 |
| M7-R2 synchronous-critical-path runtime probe | 有界证据支持（单一 API-35 emulator、Project Mode） | [#115 run](runs/2026-08-05-issue-115-project-runtime/README.md)：ProjectTarget 无 diff；defect/control 各 3 次，6/6 accountable、0 retries；defect 3/3 `locally_supported`（250 ms main-thread delay），control 3/3 `locally_rejected`；campaign admission、leakage audit、APK、ExecutionRecord、effective identity、截图/layout/logcat 与 oracle 均 checksum-bound | 仅该 ProjectTarget packet、fixture adapter、API-35 AVD 与 200 ms temporal contract；不声明项目完整性、ANR rate、OEM/SystemUI、physical fleet、Change/Project 合并率或通用 Android 能力 |
| M8 state-evolution formal qualification | 有界失败证据；不形成 runtime claim | [#122 run](runs/2026-08-05-issue-122-formal-execution/README.md)：exact #121 manifest/admission、12/12 ordered terminal attempts、0 retries/replacements；共同原因是 runner 在 execution-identity capture 阶段拒绝 fixture 子目录 `host_project`，因此 0/12 install/launch/agent/state evidence；修复见 `22af9b2`，821 tests 全通过；post-run audit 对未观测 migration receipt fail-closed | 不声明 state-evolution detection、Change/Project qualification、migration correctness、Android/OEM/production 或 benchmark-wide rate；冻结一尝试人口不重跑，未来需新 cohort/contract |
| M9 unseen-project adversarial discovery | 有界失败证据；`Not Supported`；不形成 runtime claim | [#137 run](runs/2026-08-06-issue-137-formal-execution/README.md)：exact #136 contract；contradiction packet 在副作用前 reject；Context Acquisition partial (64 facts)；top-3/Attack Plan/leakage gates pass；6/6 ordered terminal lanes，0/6 accountable，0/3 defect support，0/3 control rejection，6/6 independent reviews，0 retries/replacements；fresh emulator package-clear setup failure，未到 install/launch/agent/runtime | 仅声明冻结 population 的 gate、admission、terminal non-accountable evidence 与独立 review；不将 `Not Supported` 解释为应用 runtime verdict | 不声明 M9 runtime detection/rejection、project completeness、benchmark rate、Android/OEM/ColorOS、production 或 upstream acceptance；未来重测需新 cohort/contract |
| benchmark-wide detection/false-positive rate | 当前不声明 | 合格且足够规模的独立 ground-truth population 与预注册统计契约 |
| physical/OEM/device-fleet 与 ColorOS | 当前不声明 | 独立的设备/host admission、身份、矩阵与 durable evidence |
| fully unattended Journey reliability | 当前不声明 | 无 agent-in-the-loop 的版本化执行人口和 accountability 测量 |
| visual-only/general multimodal L3 | 当前不声明 | 视觉 ground truth、repeatability、false-positive controls 与独立审计 |
| upstream acceptance | 当前不声明 | 本仓库本地结论不等于 maintainer review 或 merge |

## M7/M8 qualification boundary and M9 result

M7 #104 的冻结离线 qualification 已完成。它证明 change 与 complete-project
两种入口都能经过 Context Expansion、Risk Hypothesis freeze、Attack Plan
admission、accountable Attempt Evidence、Finding/Residual Risk reduction 和
独立 adjudication；四个 cell 各 3 次，合计 12/12 accountable，0 retries。输入
packet 的 variant、expected evidence、verdict 和 outcome 均保持盲化；P-03-class
contradictory context 在正式 invocation 前被排除且不进入 denominator。

这个结果先支持 `proceed_to_bounded_runtime_probe`；随后 [#112](https://github.com/yangliang2/ai_verification/issues/112)
完成了独立冻结的 Change Mode runtime slice，[#115](https://github.com/yangliang2/ai_verification/issues/115)
完成了无 diff 的 Project Mode runtime slice。三者都只支持 local-only 的有界
事实，不提供缺陷检测率、误报率、项目完整性或 upstream acceptance 声明。M8
#122 的 12 条 lane 均在 runtime 之前 non-accountable；该失败证据保持不可变，不能
与 M7 结果合并或用修复后的 runner 重写。

M9 的 formal scope 是 `ProjectTarget` only：Verification Agent 只接收完整 source
provenance、scope 和 bounded budget，不接收 diff、手写 Context Graph、Risk Hypothesis、
Attack Plan、Scenario、Journey、expected evidence 或 verdict。`ChangeTarget` 只做
regression coverage。三 priors 在一个 Hypothesis Portfolio 中竞争；formal cohort 是
`project-defect × 3` 与 `project-control × 3` 六条 lane，按
`m9-lane-01`–`m9-lane-06` 顺序执行；一个 incomplete/contradictory
context packet 在任何 build/device/agent/runtime side effect 前 fail closed，留在
denominator 外。每条 lane one attempt、zero retry、zero replacement；Falsification
Review 必须使用 clean context、separate invocation identity，并披露 same-family
limitation。所有 M9 结果都只能是 exact local evidence 范围内的 local-only claim。

#137 的真实 aggregate 是 `Not Supported`，原因是六条 lane 在 fresh emulator
package-clear setup 阶段 non-accountable；没有安装、启动、agent、L1/L2/L3 或
runtime oracle evidence。这个结果保持 one-attempt/zero-retry/zero-replacement
边界；未来-only 的 package-clear 幂等修复不回填或重写该 population。

## M9 收口记录

M9 parent [#128](https://github.com/yangliang2/ai_verification/issues/128) 的实现顺序为：

`#129 → (#130 || #131) → #132 → (#133 || #135) → #134 → #136 → #137`

#136 是唯一人工冻结门，现已获得批准并由 #137 消费。#137 已按冻结顺序拒绝
contradiction packet、完成 Context Acquisition、三-prior Hypothesis Portfolio、
Attack Plan admission、六条 lane 与 Falsification Review，并诚实收口
non-accountable 结果。不得重跑或改写 M8，也不得把 M9 结果扩展成 benchmark-wide
rate、completeness、OEM/ColorOS、production 或 upstream claim。
