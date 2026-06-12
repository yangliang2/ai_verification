# HANDOFF — 待接线清单

本次无人值守交付的边界：**不依赖真机、不依赖 LLM API key**。以下是你回来后把系统接到真实世界的步骤。每项附"如何自验已接通"。

## 诚实声明：未实测的验收项

以下计划验收项（`.omc/plans/ralplan-ai-behavior-verification.md`）在本次交付中**只有代码与单测，未经真实环境验证**，不存在任何"已验证"声明：

| 验收项 | 状态 |
|--------|------|
| AC1 注入管线产出 ≥100 缺陷 | ❌ 未开始（bench/injector 是 Phase 2 工作，依赖 LLM key） |
| AC2 缺陷可检测性验证 | ❌ 未开始（依赖真机 + 注入管线） |
| AC3 验证闭环 ≤12min/缺陷 | ⚠️ 组件齐备（planner/driver 原语/oracle），但未在真机上跑过一次端到端，无计时数据 |
| AC4/AC8 抓取率定标 | ❌ 未开始 |
| AC9 全基准吞吐 SLO | ⚠️ K≥8 的宿主已选定（Wikipedia，文件级隔离），但单批构建时间未实测 |
| M1 里程碑（金标准种子 5 抓 3） | ⚠️ 素材已挖好（18 条），未移植、未植入、未运行 |

已验证的部分：**145 个本地单测全绿**（adb 命令序列、patch/分批/缓存逻辑、taxonomy 不变量、planner/oracle 的 Mock 路径、异源约束校验）。

## 接线步骤

### 1. adb 真机连接
```bash
brew install android-platform-tools   # 若无 adb
adb devices                            # 连接 ColorOS 真机，开启 USB 调试
```
**自验**：`adb devices` 列出设备且状态为 `device`（非 unauthorized）。然后跑一次真实原语冒烟：
```bash
.venv/bin/python -c "
from aiverify.harness.device import DeviceController, SubprocessAdbRunner
dc = DeviceController(SubprocessAdbRunner())
print(dc.dump_ui()[:200])"
```
能打印出当前屏幕的 XML 即接通。

### 2. LLM provider 实现与 API key（异源约束）
当前只有 `MockProvider`。需按 `aiverify.providers.LLMProvider` 接口实现两个真实 provider（建议各 ~50 行，走各家 OpenAI 兼容端点可共用一套 HTTP 代码）：
- `AnthropicProvider`（env: `ANTHROPIC_API_KEY`）→ 建议角色：注入侧（Phase 2 injector）
- `OpenAIProvider`（env: `OPENAI_API_KEY`）→ 建议角色：验证侧（planner + L3 oracle）

**异源约束已在代码层强制**：定标跑组装角色时调用 `check_cross_source(assignments, calibration_run=True)`，注入侧与验证侧同 provider 会直接抛 `CrossSourceViolation`。
**自验**：`pytest tests/test_providers.py` 仍绿；用真实 key 跑一次 `PlanGenerator.generate()`（给一个小 diff），能产出通过 schema 校验的 `VerificationPlan`。

### 3. 宿主 App（选型报告：docs/host-app-selection.md）
首选 **wikimedia/apps-android-wikipedia**：
```bash
git clone https://github.com/wikimedia/apps-android-wikipedia ~/hosts/wikipedia
cd ~/hosts/wikipedia && ./gradlew assembleDevDebug   # 标准 gradle，无私有依赖
```
**自验**：构建出 APK 并 `adb install` 成功启动。**顺手记录构建耗时**——这是 AC9 预算账的"单批构建 ≤20min"第一份实测数据。

### 4. M1 里程碑：金标准种子缺陷植入
素材在 `bench/goldset/candidates.md`（18 条，全部带已核实的 issue/修复链接）。步骤：
1. 挑 5 条移植可行性"高"的（建议含 AntennaPod#1945 单行缺陷、TB#10288 旋转重复项）
2. 在 Wikipedia 宿主对应模块手工复现等价缺陷，每条写成一个 git patch 存入 `bench/goldset/patches/`
3. 用 `Patcher.apply()` 植入 → 构建 → 装机
4. 跑验证 Agent（步骤 5），目标：5 个抓住 ≥3

### 5. 首次端到端运行
组件已齐但**缺一个编排入口**（这是第一个要写的新代码，建议 `src/aiverify/runner.py`，~100 行）：
```
diff + 规格 → PlanGenerator.generate() → 按 scenario_clusters 驱动 DeviceController
（system_events 在指定 step 注入）→ logcat/UI dump 喂 L1/L2 oracle → 不足时 L3 → verdict 落盘
```
所有积木的接口签名见各模块 `__init__.py` 导出。
**自验**：对一个种子缺陷跑通全链路，产出通过 `validate_verdict()` 的 verdict JSON 文件。

### 6. ColorOS 构建探路（计划 Phase 0 并行项，未做）
计划要求尽早证伪"内部构建系统对接"可行性（签名、构建入口、产物安装权限）。这只能由你在内网做。最坏退化方案已写入计划：注入留开源宿主，仅迁移验证 Agent。

## 建议的接线顺序
1 → 3（并行：设备 + 宿主构建）→ 2（key）→ 5（端到端入口）→ 4（M1 冲刺）。预计 1-2 个工作日到 M1 可验。
