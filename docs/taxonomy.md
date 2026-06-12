# 行为层缺陷分类法（bench/taxonomy）

本文件说明 `src/aiverify/bench/taxonomy/taxonomy.yaml` 的设计依据与内容速览。
该分类法是缺陷注入系统的知识核心：AI 注入器（`bench/injector`）按此对宿主 Kotlin
源码定点生成变异 patch，配套触发场景与预期表现构成评测基准的 ground truth。

## 为什么是"行为层"缺陷

我们刻意只收录一类错误：**主流程正常、特定行为条件下才出错**的缺陷。

- 不是编译错（静态检查即可拦下，无验证价值）。
- 不是纯逻辑错（单元测试覆盖，与"AI 生成代码在真机行为层失效"的命题错位）。
- 而是生命周期、配置变更、进程死亡、导航、并发这五类——只有把设备/系统事件
  编排进特定时序，才能暴露的缺陷。这正是 AI 写 Android 代码时真实会犯、
  code review 容易漏掉、却在真机使用中反复咬人的错误形态。

每个 `kotlin_example_after` 都遵循同一标准：看似合理、能编译、review 易漏。
否则它无法代表"AI 生成的隐蔽缺陷"。

## 来源依据（诚实声明）

本分类法为**基于领域知识整理的初版**，五大类与各模式的依据如下：

| 类别 | 主要依据 |
| --- | --- |
| lifecycle | Android 官方 Activity/Fragment 生命周期文档中反复强调的回调对称性与时序陷阱；`viewLifecycleOwner` vs Fragment lifecycle 是官方明确警示的高频错误。 |
| config-change | 官方"Handle configuration changes / Save UI states"指南；ViewModel + SavedStateHandle + `rememberSaveable` 三层状态保存模型的常见误用。 |
| process-death | 官方"Processes and app lifecycle / Save UI state"；进程被杀与配置变更的区别是社区长期混淆点，"单例当持久化"是高频反模式。 |
| navigation | Jetpack Navigation 文档中的返回栈、`popUpTo/inclusive`、deep link、一次性事件重放等已知坑；Fragment 事务时序问题在 issue 跟踪器中长期存在。 |
| coroutine-concurrency | 官方协程指南与 lifecycle-aware 收集（`repeatOnLifecycle`）文档；`GlobalScope` 滥用、主线程阻塞、`StateFlow.update` 原子性、`CancellationException` 重抛是社区公认的协程踩坑清单。 |

**重要**：上述为领域知识初版，尚未经真实开源 issue 逐条溯源校准。项目计划用两个
机制回填校准这份分类法（见 `.omc/plans` 与 PRD）：

1. `bench/goldset/` —— 将 Phase 0 收集的真实缺陷素材移植到宿主 App，人工验证可触发性，
   作为金标准 holdout 集，用其与注入分布的差距反向修正本分类法。
2. `bench/validator/` + `bench/flaky_pool/` —— 对每个注入缺陷按 ground truth 复现，
   剔除等价变异、记录复现率分布；不稳定缺陷留痕分析。

因此本文件的模式集合是**可演进的工作基线**，不宣称是穷尽或经验证的权威清单。
模式总数、分类边界会随真实缺陷回填迭代。

## 模式速览

加载与校验入口：`from aiverify.bench.taxonomy import load_taxonomy`。
校验不变量（见 `loader.py`）：五类齐全、每类 ≥5 模式、id 全局唯一、必填字段非空。

当前共 **27 个模式**（lifecycle 6 / config-change 5 / process-death 5 / navigation 5 /
coroutine-concurrency 6）。

### lifecycle —— 生命周期回调对称性与时序

| id | 模式 | 预期失败 |
| --- | --- | --- |
| lifecycle-01 | onStop 未注销已注册的监听 | 内存泄漏 / 后台回调更新已 detach 视图 |
| lifecycle-02 | onResume 重复注册导致回调叠加 | 单次事件触发多次副作用 |
| lifecycle-03 | 依赖 onDestroy 必被调用来释放资源 | 后台被杀时数据丢失 |
| lifecycle-04 | lateinit 在异步回调先于初始化时访问 | crash（Uninitialized） |
| lifecycle-05 | onSaveInstanceState 后仍提交 Fragment 事务 | crash（IllegalStateException） |
| lifecycle-06 | 用 Fragment 而非 viewLifecycleOwner 观察 LiveData | crash / 内存泄漏 |

### config-change —— 配置变更（旋转 / 字体 / 多窗口 / 深色模式）

| id | 模式 | 预期失败 |
| --- | --- | --- |
| config-change-01 | 旋转后 UI 状态丢失（未持久化） | 状态丢失 |
| config-change-02 | 重建昂贵对象而非交给 ViewModel | 重复网络请求 / UI 闪烁 |
| config-change-03 | 重建后持有失效的视图/Context 引用 | crash / 内存泄漏 |
| config-change-04 | 声明 configChanges 却未实现 onConfigurationChanged | UI 错乱 |
| config-change-05 | Compose 用 remember 而非 rememberSaveable | 状态丢失 |

### process-death —— 后台进程被杀与冷恢复

| id | 模式 | 预期失败 |
| --- | --- | --- |
| process-death-01 | ViewModel 状态未经 SavedStateHandle 持久化 | 状态丢失 |
| process-death-02 | 用内存单例缓存当持久化存储 | 数据丢失 |
| process-death-03 | 深层页面冷恢复依赖未初始化的上游数据 | crash（NPE） |
| process-death-04 | onSaveInstanceState 保存过大/不可序列化数据 | crash（TransactionTooLarge）/ 静默丢状态 |
| process-death-05 | 恢复后未重新校验权限/登录态 | crash（SecurityException）/ 越权 |

### navigation —— 页面导航与返回栈

| id | 模式 | 预期失败 |
| --- | --- | --- |
| navigation-01 | 重复点击导致同一目标页多开 | UI 错乱（返回栈多页） |
| navigation-02 | deep link 进入时状态未初始化 | crash / 空白页 |
| navigation-03 | popUpTo/inclusive 返回栈清理错误 | UI 错乱（返回回到登录页） |
| navigation-04 | Fragment 事务时序——视图就绪前导航 | crash / 导航丢失 |
| navigation-05 | 旋转后重复触发一次性导航事件 | UI 错乱（重复导航） |

### coroutine-concurrency —— 协程作用域、并发与线程

| id | 模式 | 预期失败 |
| --- | --- | --- |
| coroutine-concurrency-01 | 用 GlobalScope 启动界面相关协程 | 内存泄漏 / crash |
| coroutine-concurrency-02 | 用 launch 而非 repeatOnLifecycle 收集 Flow | 资源浪费 / crash |
| coroutine-concurrency-03 | 主线程阻塞——主调度器执行重活 | UI 卡顿 / ANR |
| coroutine-concurrency-04 | 并发更新 UI 状态的竞态（非原子读改写） | 数据错误（丢更新） |
| coroutine-concurrency-05 | 未取消旧 job 导致竞态与泄漏 | 数据错误 / 内存泄漏 |
| coroutine-concurrency-06 | 异常处理吞掉 CancellationException | 状态错乱 / 残留副作用 |

## 字段约定

每个模式含以下字段（`loader.py` 强校验）：

- `id` —— 类前缀-序号，全局唯一。
- `name` —— 模式简称。
- `description` —— 缺陷机理（中文）。
- `kotlin_example_before` —— 正确代码（地道 Jetpack/Compose/协程惯用法）。
- `kotlin_example_after` —— 注入缺陷后的片段（看似合理、能编译、review 易漏）。
- `trigger_scenario` —— 触发该缺陷的用户行为 + 系统事件序列（自然语言步骤）。
- `expected_failure` —— 可观察失败：crash / 状态丢失 / UI 错乱 / 数据错误。
- `device_state_dimensions` —— 相关设备状态维度，驱动 `harness/device` 编排，
  取值如 `orientation-change`、`low-memory`、`permission-revoked`、`no-network`、
  `background-pressure`。纯导航类缺陷可为空列表。
