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

## 目录结构

```
src/aiverify/
  providers/         LLM provider 抽象 + 异源约束校验（check_cross_source）
  harness/device/    adb 设备编排：DeviceController 系统事件原语、LogcatAnalyzer
  harness/build/     批量构建管线：Patcher（无残留回滚）、Batcher（K 批文件不相交）、Builder（APK 缓存）
  agent/planner/     验证计划生成器：PlanGenerator + plan_schema.json
  agent/oracle/      分层判定：L1 crash/ANR、L2 状态断言、L3 LLM 语义 + verdict_schema.json（冻结）
  bench/taxonomy/    行为层缺陷分类法：5 类 27 模式（taxonomy.yaml + 校验 loader）
bench/goldset/       金标准缺陷素材：18 条已核实的真实开源 issue（candidates.md）
docs/                taxonomy.md、host-app-selection.md（首选 Wikipedia App，备选 Thunderbird）
tests/               145 个单测（全部不依赖真机与 API key）
```

## 本地开发

```bash
uv venv .venv && uv pip install --python .venv/bin/python pytest pyyaml jsonschema
.venv/bin/python -m pytest          # 全量测试
```

## 文档

- 需求规格（13 轮深度访谈产物）：[`.omc/specs/deep-interview-ai-code-verification.md`](.omc/specs/deep-interview-ai-code-verification.md)
- 实施计划（Planner/Architect/Critic 共识产物）：[`.omc/plans/ralplan-ai-behavior-verification.md`](.omc/plans/ralplan-ai-behavior-verification.md)
- 缺陷分类法说明：[`docs/taxonomy.md`](docs/taxonomy.md)
- 宿主 App 选型报告：[`docs/host-app-selection.md`](docs/host-app-selection.md)
- **接线清单（真机/API key 依赖项）：[`HANDOFF.md`](HANDOFF.md)**

## 状态

Phase 0+1 无人值守边界内的部分已交付：全部基础组件 + 单测、缺陷分类法、金标准素材、宿主选型。
真机执行、LLM 真实调用、注入管线（Phase 2）见 `HANDOFF.md` 的诚实声明与接线步骤——未实测的验收项不声称已验证。
