# tasks/tasks 第二宿主验证测试计划

> 状态：**提案，未授权执行**。按仓库纪律，任何 formal population 需要人工冻结
> 与授权；本计划在 Part 1 环境准备提交 durable run record 之前不产生任何
> Run Spec 或注入动作。
> 依据文档：`docs/research/2026-09-28-second-host-candidate-research.md`
> （候选与前置条件尽调）、`docs/host-app-selection.md`（硬指标）、
> `docs/taxonomy.md`（五类缺陷）、`docs/runs/2026-08-23-opencalc-calibration/`
> （校准流程模板）、`docs/M2-beta-benchmark-slice-report.md`（matched pair 模式）。

## 0. 验证目标与边界

**目标**：在第二个宿主 tasks/tasks 上验证 AIVerify 的行为层验证能力，回答三个
问题：

1. **可移植性**：公共验证链（Run Spec → Codex CLI backend → Android CLI/adb →
   Journey Segment Boundary → L1/L2/L3 oracle → fail-closed ExecutionRecord）
   能否在新宿主上原样运行；
2. **无误报**：干净构建上 baseline control 全部通过（不产生 false positive）；
3. **有检出**：预注册的行为层注入缺陷全部被对应 oracle 层级捕获（true
   positive），且 control/defect matched pair 记账。

**明确不声明**：跨 host 检测率/误报率、benchmark-wide 结论、OEM/物理设备
覆盖、全无人值守可靠性。所有结论都是 frozen commit + 单台 API-35 模拟器 +
声明 oracle 范围内的 local-only 证据。

## 1. 两部分划分与生命周期

```text
Part 1  环境准备（Environment Preparation）
        一次性 host 入驻：源码冻结 → 可复现构建 → 部署 → 确定性回放 → 基线分离
        性质：可重做；不产生 Run Spec、ExecutionRecord lane 或任何验证语义
        产出：frozen 环境 + 校准 run record（docs/runs/<date>-tasks-calibration/）
            │
            ▼  退出 gate 通过才放行
Part 2  验证任务（Verification Tasks）
        正式 lane：T1 基线控制 → T2 缺陷注入 matched pair → T3 信任合同抽查
        性质：冻结后不可变；每条 lane one attempt、0 retry、0 replacement
        产出：逐 lane run record + 有界结论
```

生命周期规则：

- Part 1 的环境身份（commit、APK 哈希、工具版本、设备 profile）一旦漂移，
  必须重做 Part 1 并重发环境身份；
- Part 2 的冻结 population 永久绑定其执行时的环境身份，环境重做后**不得**
  用新环境重跑旧 population，只能新建冻结批次；
- Part 1 失败是准备问题，不进入任何分母；Part 2 的 non-accountable lane 是
  不可变证据。

---

# Part 1：环境准备

## P1.1 源码冻结

| 项 | 值 |
|---|---|
| Origin | `https://github.com/tasks/tasks.git` |
| 冻结动作 | `git clone --no-checkout` + `checkout --detach <commit>`；记录 commit / tree / `git archive` SHA-256 三件套；确认 worktree 干净 |
| 选 commit 原则 | Android `app` 模块仍为标准构建的近期修订（规避 KMP 演进中的构建矩阵漂移），人工批准后冻结 |

## P1.2 构建配方与可复现性

| 项 | 值 |
|---|---|
| 构建命令 | `./gradlew :app:assembleGenericDebug --no-daemon`（**显式锁定 genericDebug，禁止走 isDefault 的 googleplay**） |
| 可复现性 | 独立 `GRADLE_USER_HOME` 冷构建 + offline 重建，两 APK 字节一致（字节数 + SHA-256 相同） |
| 检查 | `aapt dump badging`（package/launcher/SDK）+ `apksigner verify --print-certs` |
| 工具链 | JDK 17（Temurin 17.0.19）、本机已有 `android-37.0` platform（compileSdk=37）、Gradle 堆 `-Xmx8G`、KMP 连带模块首构时长记录 |

## P1.3 设备与部署

- 模拟器 `aiverify_api35`（API 35）冷启动，记录启动耗时与设备 fingerprint；
- 部署 APK、经 activity-alias 启动主界面；
- 校验 device-side `base.apk` SHA-256 与本地 APK 一致（安装态身份绑定）。

## P1.4 运行时前置 setup

- `pm grant org.tasks android.permission.POST_NOTIFICATIONS`（消除提醒类
  Journey 的运行时弹窗）；
- 确认并消除首启一次性弹窗（若有 changelog 对话框），把消除动作固化为
  setup 步骤；
- 不预授权日历/位置权限（首轮不覆盖对应功能）。

## P1.5 确定性回放证明

切片：建清单 → 加任务"买牛奶" → 设提醒 → 旋转 → 断言列表项/提醒状态。

- 独立重复 3 次（每次 `pm clear` + 冷启动）；
- 3 组初始 layout JSON 字节一致、3 组结果 layout JSON 字节一致；
- app PID 的 error 级 logcat 为空；记录冷启动 `TotalTime`。

## P1.6 上游测试基线分离

- 单元测试全量 + 主要 instrumented 套件各跑一次，receipts 归档；
- 已知失败显式列为例外清单——后续任何检出不得与上游基线失败混淆（OpenCalc 先例）。

## P1.7 环境身份输出与退出 gate

输出环境身份清单：source 三件套、APK/证书哈希、Gradle/AGP/Kotlin/JDK/
build-tools/Android CLI/adb 版本、设备 profile、setup 步骤、上游例外清单。

**退出 gate（全部满足才放行 Part 2）**：字节一致构建 ✓、安装态哈希一致 ✓、
3/3 确定性回放 ✓、上游基线例外已列 ✓、环境身份清单已提交
`docs/runs/<date>-tasks-calibration/` ✓。

---

# Part 2：验证任务

## T1 基线控制运行（干净构建，5 条 Journey）

每条 Journey 一个 Run Spec，oracle 组合 L1（logcat crash/ANR）+ L2（无障碍树
状态断言）；L3 仅在 J2/J5 启用做语义复核。边界事件用仓库白名单系统事件。

| # | Journey | 覆盖缺陷类 | 边界事件 | L2 断言（示例） |
|---|---|---|---|---|
| J1 | 建清单 → 加任务 → 编辑标题 | C（config-change） | 旋转 ×2 | 旋转后标题文本与列表项保持 |
| J2 | 编辑任务详情（备注/截止日期） | P（process-death） | `am kill` 后冷恢复 | 恢复后表单内容/任务字段保持 |
| J3 | 列表 → 详情 → 返回 → 第二项 | N（navigation） | 无（纯路径） | 返回后列表滚动位置/选中项正确，无双开 |
| J4 | 设提醒 → 切后台 → 回前台 | L（lifecycle） | Home/Recent 切换 | 提醒时间 chip 保持，无重复弹窗 |
| J5 | 快速连续添加 5 个任务 | X（concurrency） | 无（快打输入） | 恰好 5 项、无丢失/重复 |

通过标准：5/5 `locally_supported`（baseline control），0 retry，每条 lane 有
完整 ExecutionRecord。任一失败：定性为 Run Spec/Journey/setup 问题或真实
上游缺陷——若是后者，记录为 Finding 并冻结，不静默重跑；T1 未全过不得
进入 T2。

## T2 缺陷注入 matched pair

### T2.1 注入点（48 个顶层包中抽 5 个互不相交包）

| # | 包 | 缺陷类 | 注入缺陷（预注册） | 预期 oracle |
|---|---|---|---|---|
| D1 | `tasklist` 或 `fragments` | C | 移除旋转时的列表状态保存/恢复 | L2 fail（旋转后状态丢失） |
| D2 | `data` 或 `viewmodel` | P | 任务编辑草稿不进 SavedStateHandle/持久化 | L2 fail（杀进程后草稿丢失） |
| D3 | `activities` / `intents` | N | 详情页启动 flags 错误导致返回栈异常（双开或吞返回） | L1/L2 fail |
| D4 | `reminders` 或 `scheduling` | L | 观察者注册到错误 lifecycle owner，恢复后重复触发 | L1（异常）或 L2（重复 chip/弹窗） |
| D5 | `ui` 或 `compose`（快速添加入口） | X | 去掉输入防抖/落库去重，快速连击产生重复任务 | L2 fail（恰好 5 项 → 实际 6+） |

### T2.2 执行纪律（沿用 M2-beta / #80）

- 每个缺陷一份独立 patch 文件，应用于**同一冻结 commit**，与 T1 同一构建
  recipe；defect 变体与 baseline 构成 matched pair，共享 Run Spec。
- oracle 层级与断言在运行前预注册进 Run Spec（`expected_oracle_level` /
  `expected_oracle_defect_class`），运行后不得修改。
- 单批 5 条 defect lane + 5 条 matched control lane，one attempt、0 retry、
  0 replacement；non-accountable lane 保持为不可变证据。
- 注入 patch、构建、APK 哈希全部进入 Effective Execution Identity。

通过标准：5/5 defect 在预注册 oracle 层级被捕获 + 5/5 control 通过。

## T3 信任合同抽查

- 抽查 2 条 lane 的 ExecutionRecord：外部副作用前建立、原子终结、canonical
  failure reason 完整；
- 抽查 Effective Execution Identity：`org.tasks` 包名、genericDebug APK 全哈希、
  installed binary 哈希、新 host commit/tree、tool/backend identity 全部绑定；
- 全切片 0 retry、append-only attempt inventory 完整。

---

# 验收汇总

| 部分 | 通过标准 | 证明什么 |
|---|---|---|
| Part 1 | 字节一致构建 + 3/3 回放 + 基线分离 + 环境身份提交 | host 可作为验证载体 |
| T1 | 5/5 baseline passed | 新宿主上无误报 |
| T2 | 5/5 defect caught + 5/5 control passed | 新宿主上有检出（五类缺陷各一） |
| T3 | 2/2 抽查 identity 完整 + 0 retry | 信任合同随 host 移植 |

全部通过后的**有界声明**：在 tasks/tasks 冻结 commit + genericDebug + 单台
API-35 模拟器 + 声明 oracle 范围内，AIVerify 验证链对五类行为层缺陷各检出
一次、基线零误报。**不构成**跨 host 检测率——两个 host 的单独有界结论
并存，不合并分母。

# 风险与对策

| 风险 | 归属 | 对策 |
|---|---|---|
| 首启一次性弹窗（changelog）打断确定性 | P1.4 | 校准时确认并纳入 setup 步骤 |
| 通知权限弹窗时机 | P1.4 | setup 统一 `pm grant`，Journey 内不再出现 |
| KMP 连带编译使注入-构建循环变慢 | P1.2 / T2 | 注入迭代用小命令集；正式 lane 才走完整 recipe |
| `am kill` 后 Hilt/WorkManager 恢复时序抖动 | T1/T2 | J2/D2 的 L2 断言聚焦持久化状态而非瞬态 UI；必要时用 Observation Poll（只读、保留全部观察、不补偿副作用） |
| 上游测试基线非绿 | P1.6 | 已知失败显式列为例外，不计入检出 |
| Widget / 穿戴 / 语音等出进程交互 | Part 2 | 第一轮全部不覆盖，列入明确不声明 |
| 环境身份漂移（工具升级/换 commit） | 两部分之间 | 重做 Part 1 重发身份；旧 population 保持不可变不重跑 |

# 执行前置（授权清单）

**Part 1 放行：**

- [ ] 人工批准本计划
- [ ] 人工批准冻结 commit（P1.1 clone 时确定并记录）

**Part 2 放行：**

- [ ] 人工审阅 Part 1 校准 run record 与退出 gate
- [ ] T2 开始前人工冻结 5 个 defect patch 与全部 Run Spec，之后不可修改
