# Deep Interview Spec: AI 行为层验证 Agent + AI 缺陷注入评测系统（Android / ColorOS）

## Metadata
- Interview ID: di-ai-code-verification-20260611
- Rounds: 13（+ Round 0 拓扑确认）
- Final Ambiguity Score: 8.5%
- Type: greenfield
- Generated: 2026-06-11
- Threshold: 0.2
- Threshold Source: default
- Initial Context Summarized: no
- Status: PASSED

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.90 | 0.40 | 0.360 |
| Constraint Clarity | 0.92 | 0.30 | 0.276 |
| Success Criteria | 0.93 | 0.30 | 0.279 |
| **Total Clarity** | | | **0.915** |
| **Ambiguity** | | | **0.085** |

## Topology
| Component | Status | Description | Coverage / Deferral Note |
|-----------|--------|-------------|--------------------------|
| 行为层验证 Agent | active | 接收一次 AI 代码改动，自动生成验证计划，在模拟器上以复杂用户行为+多样设备状态驱动真实 App，猎杀行为层边界缺陷，产出风险报告 | 验收标准 1、3 覆盖 |
| AI 验证方法体系 | active | 支撑 Agent 的多信号验证方法：用户意图（可被澄清/补全）、运行时真实行为、项目既有约定、多模型共识的分层组合 | 已收敛为多信号体系 + 分层承诺模型 |
| AI 缺陷注入评测系统 | active | AI 自动化、大规模地向宿主 App 注入行为层缺陷，构建评测基准，度量验证 Agent 的能力水位 | 验收标准 2、4、5 覆盖（Round 9 由用户主动升级为顶层组件） |
| 差距诊断 | deferred | "编码能力强、验证能力没跟上"的论证 | 用户确认仅为背景动机（Round 0，2026-06-11） |
| 接入形态 | deferred | IDE 插件 / CI 门禁 / 独立 Agent 服务等封装 | 用户确认"核心是验证能力本身，形态是后续问题"（Round 2） |

## Goal
构建一套**用 AI 验证 AI 生成代码**的能力。MVP 聚焦 Android（Kotlin，ColorOS 一方系统应用）的**行为层边界缺陷**：主流程看似正确，但生命周期、页面导航、旋转/配置变更、后台杀进程、协程并发、非理想设备状态下埋雷的那类问题。

能力闭环为双轮驱动：
1. **验证 Agent**：改动 → 自动验证计划 → 模拟器驱动真实 App 探索 → 风险透明化报告，全程零人工脚本。
2. **缺陷注入评测系统**：AI 大规模注入行为层缺陷构建基准，持续度量验证 Agent 的抓取能力——评测系统是验证 Agent 的"陪练"。

## Constraints
- **定位**：自用优先，第一用户是作者本人，解决自己 AI 编码工作流中的验证痛点
- **环境**：Android 原生，Kotlin；最终落地宿主为 ColorOS 一方系统应用
- **工作流**：SDD（规格驱动开发）——验证 Agent 的输入契约为「需求规格 + 代码改动 diff + 可构建源码」（白盒全上下文）；但需求规格被明确定性为**不充分的信号**，可能漏场景，不能当 ground truth
- **执行底座**：本地真机为主（1-2 台 ColorOS 真机 + adb 驱动），规模化并发推迟；评测吞吐量受此约束
- **验证对象**：App 行为层（非纯 JVM 逻辑层）→ 必须在真机/模拟器上驱动真实 App
- **设备状态多样性**：不能假设"刚开机的理想态"——需覆盖后台压力、权限状态、网络条件、存储状态等真实状态空间
- **用户行为复杂性**：注入与验证都需覆盖复杂的多步用户行为路径，而非单页面单操作
- **缺陷注入必须 AI 自动化且规模化**：手工构造缺陷不可接受
- **注入宿主路径**：开源 Android 项目做注入管线的练兵与验证 → 最终迁移到 ColorOS 真实应用
- （推断，待确认）系统应用涉及内部代码，基准可能无法完全公开

## Non-Goals
- MVP 不做接入形态（IDE 插件 / CI 门禁 / 编码 agent 集成均为后续封装问题）
- 不以纯逻辑层单元测试为核心路线（行为层雷为主，Round 8 确认）
- 不承诺"证明代码正确"——承诺是分层的：验证计划契约 + 风险透明化报告，长期以缺陷发现率和对标资深工程师自证能力
- 差距诊断不作为独立交付物

## Acceptance Criteria
- [ ] AI 缺陷注入系统能向宿主 App **自动**注入行为层缺陷，类型覆盖：生命周期、旋转/配置变更、后台杀进程、页面导航状态、协程并发，**规模 ≥100 个**（Round 13 用户定标）
- [ ] 注入的缺陷触发条件覆盖复杂用户行为路径与多样化设备状态（非刚开机理想态）
- [ ] 验证 Agent 对一次代码改动可全自动闭环：生成验证计划（基于 SDD 规格 + diff）→ 真机执行 → 输出风险报告（含规格盲区发现），零人工脚本
- [ ] **第一里程碑（用户钦定）**：在 AI 注入缺陷基准上**抓取率 ≥80%**（Round 13 用户定标）
- ⚠️ 已知张力（规划阶段须解决）：100+ 缺陷规模 × 本地 1-2 台真机吞吐 → 注入管线必须高度自动化、单缺陷验证周期必须很短，或基准分批执行
- [ ] 注入管线先在开源 Android 项目上跑通，再在 ColorOS 真实应用上完成迁移验证
- 长期（非 MVP 验收）：在自己项目的真实 AI 改动上抓住未被人工发现的真实缺陷；连续两周敢凭报告直接合入；对标资深工程师 review + QA 水准

## Assumptions Exposed & Resolved
| Assumption | Challenge | Resolution |
|------------|-----------|------------|
| 想法是探讨方法论 | Round 0 拓扑确认 | 核心是做具体的工具/产品，方法论为其服务 |
| 产品需要先选介入形态（IDE/CI/独立 agent） | Round 1-2："都需要"→ 追问共享核心 | 核心是验证能力本身，形态推迟 |
| 验证需要单一裁决基准（oracle） | Round 3：冲突时听谁的 | 多信号体系；用户意图本身可能模糊不全，澄清意图也是验证的一部分 |
| "充分验证"可达 | Round 4 反方模式：测试只能证伪 | 分层承诺模型：验证计划契约 + 风险透明化 + 缺陷发现率/对标资深工程师自证 |
| 愿景产品（大而全） | Round 5 定位约束 | 自用优先，长在自己的真实工作流上 |
| 验证 = 通用代码测试 | Round 6 简化模式 + Round 8 本体论模式 | 靶心是"看似对但边界错"，且以**行为层雷为主**（生命周期/导航/系统事件），非逻辑层单测 |
| 评测基准可以手工构造 | Round 9 验收标准 | 缺陷注入本身必须 AI 化、规模化，覆盖复杂行为与真实设备状态 |
| 注入宿主用样板/开源即可 | Round 10 | 开源练兵，最终必须落到 ColorOS 一方系统应用 |
| 需求规格可作为验证的 ground truth | Round 11：SDD 工作流确认 | 规格稳定存在但不充分——发现规格盲区本身是验证交付物 |
| 需要云平台/模拟器集群才能起步 | Round 12：执行底座 | 本地真机为主起步，规模化推迟 |
| 小基准起步更稳妥 | Round 13：数字定标 | 用户选高标准：100+ 注入缺陷 / 抓取率 ≥80%，张力转化为注入管线的自动化要求 |

## Technical Context
- Greenfield：当前目录 `/Users/peter/projects/ai_verfication` 为空项目（仅 `.omc/`）
- 技术域提示（访谈推断，供规划参考）：模拟器/真机驱动（adb、UI 自动化）、行为层探索 agent、AI 测试生成、变异测试/缺陷注入（mutation testing 的行为层扩展）、设备状态编排（网络/权限/后台压力/进程杀）

## Ontology (Key Entities)
| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| 验证 Agent | core domain | 验证计划、执行循环、风险报告 | 验证 AI 生成代码改动；被评测系统度量 |
| AI 缺陷注入评测系统 | core domain | 缺陷库、注入管线、抓取率 | 向宿主 App 注入缺陷；度量验证 Agent |
| AI 代码改动 | core domain | diff、任务上下文 | 验证 Agent 的输入 |
| 行为层边界缺陷 | core domain | 生命周期/导航/配置变更/后台杀/并发 | 验证 Agent 的猎杀目标；注入系统的产物 |
| 用户意图 | supporting | 可能模糊/不全 | 验证信号之一；可被澄清补全 |
| 验证信号层 | supporting | 意图/运行时行为/既有约定/多模型共识 | 组成验证方法体系 |
| 验证计划 | supporting | 验什么/怎么验/验到什么程度 | Agent 产出，契约式承诺 |
| 风险报告 | supporting | 验了什么/没验什么/剩余风险 | Agent 最终交付物 |
| 宿主 App | supporting | 开源项目（练兵）、ColorOS 系统应用（落地） | 注入与验证的载体 |
| 设备状态空间 | supporting | 后台压力/权限/网络/存储 | 注入与验证的环境维度 |
| 用户行为路径 | supporting | 多步复杂操作序列 | 缺陷触发与探索的载体 |
| 作者（第一用户） | supporting | ColorOS 一方应用开发，Kotlin | 自用优先 |
| 模拟器/真机环境 | external system | adb、UI 驱动 | 行为层验证的执行底座 |
| 接入形态 | deferred | IDE/CI/独立服务 | 后续封装 |

## Ontology Convergence
| Round | Entity Count | New | Changed | Stable | Stability Ratio |
|-------|-------------|-----|---------|--------|----------------|
| 1 | 4 | 4 | - | - | N/A |
| 2 | 4 | 0 | 1 | 3 | 100% |
| 3 | 6 | 2 | 0 | 4 | 67% |
| 4 | 9 | 3 | 0 | 6 | 67% |
| 5 | 9 | 0 | 1 | 8 | 100% |
| 6 | 10 | 1 | 0 | 9 | 90% |
| 7 | 11 | 1 | 0 | 10 | 91% |
| 8 | 12 | 1 | 1 | 10 | 92% |
| 9 | 14 | 2 | 0 | 12 | 86% |
| 10 | 15 | 1 | 0 | 14 | 93% |

核心实体（验证 Agent、AI 代码改动、行为层缺陷、验证报告）自 Round 4 起保持稳定；后期新增均为对核心的具体化（宿主、设备状态、注入系统），属收敛性扩展。

## Interview Transcript
<details>
<summary>Full Q&A（10 rounds + Round 0）</summary>

### Round 0（拓扑确认）
**Q:** 拆解为差距诊断 / AI 验证方法体系 / 落地载体三部分，对吗？
**A:** 核心是落地载体——想做一个具体的工具/产品，方法论为它服务。

### Round 1
**Q:** 产品在哪个时刻、以什么形态介入？（IDE 实时 / PR 门禁 / 独立验证 Agent）
**A:** 感觉都需要。
**Ambiguity:** 80.5%（Goal 0.30 / Constraints 0.15 / Criteria 0.10）

### Round 2
**Q:** 只能先做一个形态先做哪个？还是核心根本不是形态？
**A:** 核心是验证能力本身，形态是后续问题。
**Ambiguity:** 71.5%（Goal 0.45 / Constraints 0.20 / Criteria 0.15）

### Round 3
**Q:** 信号冲突时，最终裁决基准是什么？（意图/运行时/既有约定/多模型共识）
**A:** 都需要，要体系化思考；用户意图可能模糊或考虑不全。
**Ambiguity:** 68.6%（Goal 0.50 / Constraints 0.20 / Criteria 0.18）

### Round 4（反方模式）
**Q:** 若"充分验证"理论上不可达，产品实际承诺的交付物是什么？
**A:** 风险透明化报告、对标资深工程师、验证计划契约、可度量缺陷发现率——都要（组合成分层承诺模型）。
**Ambiguity:** 61.5%（Goal 0.55 / Constraints 0.20 / Criteria 0.35）

### Round 5
**Q:** 第一个真实用户是谁，以什么身份和投入做？
**A:** 自用优先。
**Ambiguity:** 51.1%（Goal 0.60 / Constraints 0.45 / Criteria 0.38）

### Round 6（简化模式）
**Q:** 最简版本只能消灭一种痛，选哪种？
**A:** 看似对但边界错。
**Ambiguity:** 41.3%（Goal 0.68 / Constraints 0.50 / Criteria 0.55）

### Round 7
**Q:** 你日常 AI 编码的主要环境？
**A:** Android Native App 开发，主要语言 Kotlin。
**Ambiguity:** 34.2%（Goal 0.70 / Constraints 0.68 / Criteria 0.58）

### Round 8（本体论模式）
**Q:** 验证的核心对象是 Kotlin 代码单元逻辑，还是 App 在设备上的行为？
**A:** 行为层雷为主。
**Ambiguity:** 27.6%（Goal 0.82 / Constraints 0.70 / Criteria 0.62）

### Round 9
**Q:** 三个月后验收 MVP，必须达成的第一里程碑是哪条？
**A:** 注入缺陷达标——但缺陷注入也要 AI 来做，需要大量构建；用户行为非常复杂，手机状态也不会永远是刚开机状态。
**Ambiguity:** 20.4%（Goal 0.85 / Constraints 0.72 / Criteria 0.80）

### Round 10
**Q:** AI 大规模注入行为层缺陷时，宿主 App 用什么？
**A:** ColorOS 一方系统应用；开源项目可做注入验证，但最终要落实到真实应用。
**Ambiguity:** 15.3%（Goal 0.88 / Constraints 0.80 / Criteria 0.85）✅ PASSED（用户选择继续访谈）

### Round 11
**Q:** 真实工作流里，验证 Agent 能稳定拿到的输入包是什么？
**A:** 用 SDD 方式开发，会有需求规格；但规格很可能没考虑清楚所有场景，未必充分完整。
**Ambiguity:** 12.7%（Goal 0.90 / Constraints 0.86 / Criteria 0.85）

### Round 12
**Q:** 验证 Agent 驱动 App 的执行底座是什么？
**A:** 本地真机为主。
**Ambiguity:** 10.9%（Goal 0.90 / Constraints 0.92 / Criteria 0.85）

### Round 13
**Q:** 第一里程碑的数字定标？
**A:** 100+ 个注入缺陷 / 抓取率 ≥80%。
**Ambiguity:** 8.5%（Goal 0.90 / Constraints 0.92 / Criteria 0.93）✅ 所有维度 ≥0.90

</details>
