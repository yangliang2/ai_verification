# AI Verification

用 AI 验证 AI 生成的代码——Android 行为层验证 Agent + AI 缺陷注入评测系统。

## 背景

AI 时代编码能力越来越强，但验证能力没有跟上。本项目聚焦 Android（Kotlin）开发中最隐蔽的一类问题：**主流程看似正确，但生命周期、页面导航、旋转/配置变更、后台杀进程、协程并发等行为层边界埋雷**。

## 核心设计：双轮驱动

1. **行为层验证 Agent**：接收一次 AI 代码改动（SDD 规格 + diff + 源码）→ 自动生成验证计划 → 真机执行（LLM 驱动 UI 操作 + adb 确定性编排系统事件）→ 分层判定（crash/状态断言/LLM 语义）→ 输出风险透明化报告（含规格盲区发现），全程零人工脚本。
2. **AI 缺陷注入评测系统**：AI 向宿主 App 源码级注入 100+ 行为层缺陷构建评测基准，持续度量验证 Agent 的抓取能力——评测系统是验证 Agent 的"陪练"。

### 基准可信度三重锚（防"AI 测 AI"的同源共谋）

- **强制异源**：缺陷注入方与验证判定方使用不同 provider 的模型
- **金标准对照集**：非 AI 生成的真实历史缺陷作 holdout，抓取率分别报告
- **flaky_pool**：难复现真实缺陷留痕不丢弃，防基准被提纯成"只剩好抓的"

## 第一里程碑

AI 自动注入 ≥100 个行为层缺陷（五类各 ≥15），验证 Agent 抓取率 ≥80%（各类 ≥60%），误报率 ≤20%，全基准一轮墙钟 ≤24h（本地双真机）。

## 文档

- 需求规格（13 轮深度访谈产物）：[`.omc/specs/deep-interview-ai-code-verification.md`](.omc/specs/deep-interview-ai-code-verification.md)
- 实施计划（Planner/Architect/Critic 共识产物）：[`.omc/plans/ralplan-ai-behavior-verification.md`](.omc/plans/ralplan-ai-behavior-verification.md)

## 状态

规划阶段完成（pending approval），实现未开始。
