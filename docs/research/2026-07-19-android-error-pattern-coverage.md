# Android 典型错误范式与当前验证覆盖

研究日期：2026-07-19  
范围：Android 官方文档所描述的运行时错误/质量风险，与本仓库 M3.1/M4 当前可审计能力的对照。

## 结论摘要

当前项目已经对一组重要的 **behavior-layer** 风险形成了可重复验证链：崩溃/ANR、配置变更后的状态丢失、进程死亡后的状态恢复、导航状态、并发/主线程阻塞，以及 UI 文本/渲染和真实 Intent 行为。M3.1 的 30 条执行审计证明的是执行可追责性和基线误报控制，不等于覆盖了 Android 的全部错误面；M4 的两个 `locally_supported` 案例证明真实上游变更可以走通链路，但不构成检测率或 Goldset 结论。

主要缺口是：真实网络/离线与重试、运行时权限拒绝/撤销、备份恢复和跨设备/多窗口、可访问性、性能帧时延/电池、组件/Intent 安全，以及更广泛的设备/API/语言/屏幕矩阵。现有代码中有部分驱动原语（例如旋转、进程死亡、权限 grant/revoke、网络开关），但没有对应的 M3.1 audited lane 或稳定的机器 oracle，故下表标为“原语存在，覆盖未证明”。

## 官方来源归纳的典型错误范式

| 错误范式 | Android 官方依据 | 常见可观察失败 | 当前覆盖判断 |
|---|---|---|---|
| UI 线程阻塞：磁盘/网络 I/O、长计算、同步 Binder、锁竞争、死锁 | [ANR patterns](https://developer.android.com/topic/performance/vitals/anr), [keep app responsive](https://developer.android.com/topic/performance/anrs/keep-your-app-responsive) | 输入无响应、ANR；前台输入默认约 5 秒超时，广播/服务也有超时 | **已覆盖（窄）**：M3 有主线程 ANR defect，L1/logcat oracle；未覆盖系统负载、Binder/广播/JobService 变体 |
| Activity/进程生命周期错误 | [Processes and app lifecycle](https://developer.android.com/guide/components/activities/process-lifecycle), [Save UI states](https://developer.android.com/topic/libraries/architecture/saving-states) | 旋转/配置变更崩溃，进程被杀后 UI 状态丢失；不能依赖 `onDestroy()` | **已覆盖（窄）**：M3 有 recreation crash、tab state-loss、oversized saved-state；未覆盖后台限制、更多组件生命周期 |
| 导航/返回栈和重复启动 | [Activity lifecycle](https://developer.android.com/guide/components/activities/activity-lifecycle) | back 被吞、重复打开、错误 back stack、重复 intent 导致崩溃 | **已覆盖（窄）**：navigation double-open crash、back-button swallowed；未覆盖 task/深链组合与多窗口 |
| 并发/协程异常与竞态 | [Keep app responsive / ANR](https://developer.android.com/topic/performance/anrs/keep-your-app-responsive) | 未处理异常、竞态更新、死锁、结果乱序或 UI 在销毁后更新 | **部分覆盖**：已有 coroutine main-thread ANR seed；没有系统化竞态/取消/生命周期作用域矩阵 |
| UI 渲染、布局、文本/本地化错误 | [UI tests and compatibility](https://developer.android.com/training/testing/ui-tests), [slow rendering](https://developer.android.com/topic/performance/vitals/render) | 标签/文案错误、布局错位、慢帧/冻结帧、不同设备或方向渲染差异 | **部分覆盖**：M3 L3 search-card/nav-label，M4 “Read more”页面类型；尚无截图 diff、帧时间、字体/RTL/大屏审计 |
| 配置与资源变化（方向、语言、夜间、屏幕尺寸） | [UI testing contexts](https://developer.android.com/training/testing/ui-tests) | 方向/locale/屏幕尺寸后错误资源、状态重置、布局溢出 | **部分覆盖**：旋转是既有驱动和 seed；夜间模式有执行前重置；没有稳定 locale/RTL/foldable/tablet lane |
| 网络不稳定、离线、超时、重复请求与缓存 | [Android architecture data layer](https://developer.android.com/topic/architecture), [App quality/vitals](https://developer.android.com/topic/performance/vitals/index.html) | 空白页、错误重试风暴、旧数据覆盖新数据、离线不可用、启动卡住 | **缺失（行为审计）**：有 `svc data/wifi` 设备原语，但 M3/M4 没有可审计 offline/timeout/cache consistency lane |
| 运行时权限拒绝、撤销与权限状态假设 | [Request runtime permissions](https://developer.android.com/training/permissions/requesting), [Permissions overview](https://developer.android.com/guide/topics/permissions/overview) | `SecurityException`、功能崩溃、拒绝后无法降级、权限被撤销后继续访问 | **缺失（行为审计）**：controller 有 grant/revoke 和 package dump 单测；没有真实 UI denial/permanent-denial/revocation journey |
| 存储、缓存、低空间、卸载与备份恢复 | [App-specific storage](https://developer.android.com/training/data-storage/app-specific), [Auto Backup](https://developer.android.com/identity/data/autobackup) | 缓存被系统清除后崩溃、低空间写入失败、卸载后错误期待数据仍在、恢复后状态不一致 | **部分/偏缺失**：有 oversized saved-state；没有低空间、cache eviction、Auto Backup restore 或 schema migration lane |
| Intent/组件边界与外部输入 | [Intents and intent filters](https://developer.android.com/guide/components/intents-filters), [Intent/component security](https://developer.android.com/agents/skills/security/android-intent-security/SKILL) | 未校验 URI/extras、错误 deep link、intent redirection、误导出组件、`onNewIntent` 状态不更新 | **部分覆盖**：M4 T426553 验证 encoded external URI，且有回归矩阵；仍缺 untrusted extras/redirection/exported component/security oracle |
| 可访问性语义 | [Accessibility testing](https://developer.android.com/guide/topics/ui/accessibility/testing) | 缺 contentDescription、不可聚焦/读屏顺序错误、小触控目标、低对比度 | **缺失**：uiautomator XML 被用于一般 UI oracle，但没有 Accessibility Test Framework/TalkBack/对比度断言 |
| 启动慢、慢帧、冻结帧、电量/唤醒 | [Startup time](https://developer.android.com/topic/performance/vitals/launch-time), [Slow rendering](https://developer.android.com/topic/performance/vitals/render), [Android vitals](https://developer.android.com/topic/performance/vitals/index.html) | 冷启动慢、16ms 以上 jank、700ms 冻结帧、ANR、过度 wake lock/电量消耗 | **缺失（指标审计）**：L1 可捕获崩溃/ANR；无 Perfetto/`gfxinfo`/battery/wakelock oracle |
| 设备/API/厂商差异 | [Automate UI tests](https://developer.android.com/training/testing/ui-tests) | 某 API、语言、方向、平板/折叠设备才出现崩溃或布局错误 | **缺失（矩阵）**：当前主要是单一 emulator/profile；没有 API/locale/form-factor 分层结果 |

## 证据到能力的边界

当前可直接核验的仓库证据：

- [M3.1 v20 audit](../runs/2026-07-18-m3-v20-audit/README.md)：30/30 accountable、baseline false positives 0、defect consistency 15/15、controls 15/15、provenance 30/30。
- `bench/goldset/patches/` 与 `bench/goldset/run-specs/`：包含 ANR、生命周期 recreation、进程死亡状态、导航、配置/查询状态、UI rendering 等 defect slices。
- [M4 aggregate](../runs/2026-07-18-m4-aggregate/README.md)：T426553 与 T426989 为 `locally_supported`；T409797 因无认证 fixture 为 `non_accountable`。这说明链路能对真实候选做 fail-closed 处理，但不是广泛 Android 缺陷覆盖证明。
- `src/aiverify/harness/device/controller.py`：已具备旋转、进程死亡、夜间模式、Wi‑Fi/数据开关、权限 grant/revoke 等事件原语；原语存在不代表已形成可审计能力。

## 建议的覆盖路线

按风险与可观测性，下一批应优先建立稳定 fixture 和 oracle：

1. **离线/超时/重试/缓存一致性**：网络切换前后、进程重启、请求取消和旧响应覆盖。
2. **权限状态矩阵**：首次拒绝、永久拒绝、设置中撤销、升级后权限变化，并要求 graceful degradation。
3. **生命周期扩展**：后台/前台、系统进程杀死、备份恢复、旋转 + 多窗口/折叠布局。
4. **可访问性与兼容性**：Accessibility Test Framework + TalkBack/语义树、RTL/locale、API 与大屏矩阵。
5. **性能与资源**：冷启动、`gfxinfo`/Perfetto 帧、低空间/cache eviction、wake lock/battery。
6. **Intent 安全**：恶意 extras、nested intent/redirection、exported component 和 `PendingIntent` 变体。

这些应作为新的 accountable lanes；在稳定 fixture、机器 oracle 和独立验证存在前，只登记为 capability gap，不把源码静态检查或构建成功计作运行时覆盖。

## 备注

官方页面会随 Android API/工具版本更新；本研究保留访问日期和直接链接。错误范式的“当前覆盖”是基于本仓库当前提交的运行记录与测试/benchmark manifest 的审计判断，不是对 Wikipedia 产品全部代码的安全审计。
