# 第二完整验证宿主候选调研

> 用途：在 Wikipedia（首选宿主）、OpenCalc（calibration-only）之外，选定第二个
> 完整验证宿主，打破单一 host 证据边界。
> 数据来源：GitHub API（`gh api repos/...` / languages / contents / search/code）
> 实查，未做任何 clone、构建或设备动作。
> **查询时间：2026-09-28（UTC）**。星数、commit 时间、语言占比、代码搜索命中数
> 均为当日实测值。

## 0. 边界与既有档案的关系

- 本调研**不重新评估** `docs/host-app-selection.md`（2026-06）已结论的 11 个候选；
  Thunderbird 仍是该档案指定的第二宿主备选，本轮应要求只调研档案外新候选。
- OpenCalc 保持 calibration-only，不进入完整宿主比较。
- Catima 继续保留为未见 holdout：本轮未 clone、未构建、未暴露其源码给任何
  验证动作。
- 本调研产出的是**候选结论**，不是宿主能力声明。任何候选在 clone 冻结、
  可复现构建、部署启动、确定性 Journey 切片实测通过（参照
  `docs/runs/2026-08-23-opencalc-calibration/` 的校准流程）之前，不得作为
  Run Spec host 使用。

## 1. 硬指标（沿用 2026-06 选型档案）

| 编号 | 指标 |
|---|---|
| (a) | Kotlin 为主语言 |
| (b) | 活跃维护 |
| (c) | 典型架构（ViewModel、Compose 或 View 体系、协程） |
| (d) | 本地可构建（标准 Gradle，无特殊签名/私有依赖） |
| (e) | 可隔离注入点充足：单批互不相交（不同文件/模块）注入点 K≥8 可行 |
| (f) | 页面复杂度：多页面导航、列表、表单、后台任务，承载 lifecycle / config-change / process-death / navigation / coroutine 五类缺陷 |

## 2. 新候选对照表（8 个候选，实查于 2026-09-28）

| 仓库 | Stars | Kotlin 占比 | 最近 push | Gradle | 架构信号（code search 命中） | 模块/注入面 | 结论 |
|---|---|---|---|---|---|---|---|
| [tasks/tasks](https://github.com/tasks/tasks) | 5 609 | 96.8%（6.72M/6.94M 字节） | 2026-09-28 | Wrapper 9.7.1 | ViewModel=224、Composable=242 | 17 个 include；48 个顶层包 | **六项全过 → 首选推荐** |
| [ankidroid/Anki-Android](https://github.com/ankidroid/Anki-Android) | 11 869 | 97.5%（8.39M 字节，无 Java 进前三） | 2026-09-28 | Wrapper 9.7.1 | ViewModel=174、Composable=14（View 为主） | 多模块；49 个顶层包 | 六项全过 → 第二推荐 |
| [element-hq/element-x-android](https://github.com/element-hq/element-x-android) | 2 420 | ≈99%（14.97M 字节） | 2026-09-28 | Wrapper 9.7.1 | Composable=978、ViewModel=2（Presenter/Molecule 风格） | 29 个 include | (f) 受限：核心 Journey 需要 Matrix 账号与 homeserver，确定性差；工程体量为 Wikipedia 的 3 倍以上 |
| [breezy-weather/breezy-weather](https://github.com/breezy-weather/breezy-weather) | 11 498 | 100%（5.47M 字节） | 2026-09-19 | Wrapper 9.7.1 | ViewModel=16、Composable=65 | 7 个 include | (c)(f) 偏弱：ViewModel 信号少；核心价值依赖定位+网络，确定性 Journey 成本高 |
| [kiwix/kiwix-android](https://github.com/kiwix/kiwix-android) | 1 477 | ≈99%（3.99M 字节） | 2026-09-26 | Wrapper 9.5.0 | Composable=91（ViewModel 查询被 rate limit，未取到） | 单 app 模块 | (d)(f) 受限：release 签名配置进构建文件、疑带 libkiwix native 依赖；核心内容需下载 ZIM 包 |
| [ReadYouApp/ReadYou](https://github.com/ReadYouApp/ReadYou) | 7 551 | 97.8%（1.61M 字节） | 2026-08-11 | Wrapper 8.13 | ViewModel=49、Composable=142 | 单 app 模块 | (b)(f) 偏弱：近 7 周无 push；RSS 源需网络，确定性 Journey 需自建本地源 |
| [FossifyOrg/Calendar](https://github.com/FossifyOrg/Calendar) | 2 184 | 98.7%（0.93M 字节） | 2026-09-27 | Wrapper 9.7.1 | ViewModel=0、Composable=1（老式 Activity 架构） | 单 app 模块（依赖已发布的 FossifyCommons） | (c) 不满足：无 ViewModel/Compose，与 2026 年 AI 生成代码的典型形态偏差大 |
| [beemdevelopment/Aegis](https://github.com/beemdevelopment/Aegis) | 13 171 | **Java 为主**（1.13M 字节，前三无 Kotlin） | 2026-09-06 | — | — | — | **不满足 (a)**，淘汰 |

> 注：所有 settings 文件均未检出 `maven.pkg.github` / credentials / GITHUB_TOKEN
> 等私有依赖标记。Kiwix 的 ViewModel 命中数因 GitHub code search rate limit
> 未取到，不影响其 (d)(f) 项结论。

## 3. 首选推荐：tasks/tasks（Tasks.org）

### 3.1 六项硬指标逐项核验

- **(a) Kotlin**：96.8%（Kotlin 6 724 290 字节 / Java 125 262 / C 101 173）。
- **(b) 活跃**：调研当日有 push（2026-09-28），日级提交频率。
- **(c) 架构**：ViewModel 命中 224、Composable 命中 242——View 体系 + Compose
  混合、重 ViewModel，与 Wikipedia 的架构形态同构，也贴近 2026 年 AI 生成
  Android 代码的典型风格。Dagger/Hilt DI（`dagger.hilt.android.plugin`）。
- **(d) 可构建**：Gradle Wrapper 9.7.1，标准 `settings.gradle.kts`（17 个
  include）。`com.google.gms.google-services` 插件虽无条件应用，但
  `app/src/debug/google-services.json` 已随仓库提交（debug dummy），
  `generic` flavor（F-Droid 渠道）无需任何凭据。`.gitmodules` 为空文件，
  无 submodule 摩擦。无签名/私有 maven 依赖。
- **(e) 注入面**：`app/src/main/java/org/tasks/` 下实查 **48 个顶层包**：
  activities、api、appfunctions、audio、auth、backup、billing、caldav、
  calendars、compose、dashclock、data、db、dialogs、drive、etebase、
  extensions、files、filters、fragments、googleapis、gtasks、http、
  injection、intents、jobs、locale、location、logging、markdown、
  notifications、opentasks、preferences、provider、receivers、reminders、
  repeats、scheduling、sync、tags、tasklist、themes、ui、utility、viewmodel、
  voice、watch、wear、widget。互不相交注入点 K≥8 远超阈值。
- **(f) 页面复杂度**：任务列表/过滤器/标签（列表+导航）、任务编辑与提醒
  设置（表单）、caldav/gtasks/drive/etebase 多端同步（并发）、reminders/
  notifications/receivers/jobs/scheduling（后台任务）、backup（状态持久化与
  恢复）、widget（生命周期）——五类缺陷均有天然落点。

### 3.2 与 Wikipedia 的互补性

| 维度 | Wikipedia | tasks/tasks |
|---|---|---|
| 领域 | 内容浏览（网络+WebView 重） | CRUD 生产力（表单/列表/后台重） |
| 数据形态 | 远端内容为主，离线靠 saved pages | local-first，核心 Journey 零网络依赖 |
| 后台行为 | SavedPageSync、通知轮询 | 提醒/调度/多端同步/备份恢复，密度更高 |
| 模块形态 | 单 `:app`、60+ 功能包 | 17 模块、48 顶层包 |
| 架构形态 | View+Compose 混合 | View+Compose 混合（同构，控制变量） |

关键实际收益：**local-first 意味着确定性 Journey 不需要网络 fixture**——
建清单、加任务、设提醒、旋转、杀进程、恢复，全程离线可断言，直接降低
Run Spec 的环境敏感面；同时它把 Wikipedia 较薄的"后台任务/表单"缺陷面
补齐为一级注入面。

### 3.3 已知风险

- 仓库正在演进为 Kotlin Multiplatform（存在 `composeApp/`、`iosApp/`、`kmp/`
  目录与 fdroid/googleplay 双渠道 deps 清单），未来版本的构建矩阵可能复杂化；
  冻结 commit 可消除漂移，但选型时应固定在 Android `app` 模块仍为标准构建的
  修订上。
- FCM/Crashlytics 插件在 release 构建路径上仍需要真实凭据——只使用
  generic/debug 变体即可规避，Run Spec 必须显式锁定变体。
- 5.6k 星、社区体量小于 Wikipedia/Thunderbird，issue 响应与 LTS 预期较弱。

### 3.4 验证前置条件尽调（2026-09-28 实查）

结论：**无硬阻断条件**。不需要账号、不需要网络、不需要 API key、不需要安装
新 SDK。细项如下。

**构建侧（全部满足或有明确规避路径）：**

| 条件 | 实查结果 |
|---|---|
| JDK | AGP 9.4.0 + Gradle 9.7.1，JDK 17 可建；本机 Temurin 17.0.19（与 OpenCalc 校准同环境）✓ |
| Android SDK Platform | `compileSdk=37`（libs.versions.toml）；本机 platforms 已装 `android-37.0` ✓ |
| target/min SDK | targetSdk=36、minSdk=26；现有 API-35 模拟器直接可用 ✓ |
| google-services.json | `app/src/debug/` 已随仓库提交 dummy ✓ |
| mapbox/google/posthog key | `resValue(... ?: "")` 空默认可构建，仅 map/location 功能降级，不阻构建 ✓ |
| 私有 maven/签名/submodule | 均无（`.gitmodules` 为空文件）✓ |
| 构建变体 | `generic` / `googleplay`（isDefault）两 flavor——**必须显式锁定 `genericDebug`**，否则走错默认 flavor |
| Gradle 堆 | `gradle.properties` 配 `-Xmx8G`（高于 Wikipedia/OpenCalc），构建机需 8G 可用堆 |
| KMP 连带编译 | settings 含 composeApp/kmp 等 17 个 include，`:app` 构建会连带 KMP 模块，首构偏慢；冻结 commit 消除漂移 |

**运行侧（均可由 setup 机制承载）：**

| 条件 | 影响 | 处置 |
|---|---|---|
| `POST_NOTIFICATIONS`（targetSdk 36 → API 33+ 运行时权限） | 提醒类 Journey 会触发权限弹窗，打断确定性执行 | setup 阶段 `pm grant` 预授权（由 Attempt Setup Plan 承载） |
| `READ/WRITE_CALENDAR` | 仅日历集成 Journey 需要 | 首轮不覆盖，或按需 grant |
| 位置权限（含后台） | 仅 location/place 提醒需要；无 mapbox key 地图不可用 | 首轮不覆盖 location 包 |
| 首启流程 | manifest 无 intro/onboarding activity，activity-alias 直达主列表（与 Wikipedia 的 DefaultIcon alias 同型） | 校准时确认有无 changelog 一次性弹窗，纳入 setup |
| 账号/网络 | 核心 CRUD、提醒、备份 Journey 全部离线可用 | gtasks/caldav/drive 同步类注入点需测试账号，首轮不覆盖 |

净新增条件相对 Wikipedia 校准只有四项：8G 堆、变体锁定、通知权限预授权、
KMP 连带编译耗时。

## 4. 第二推荐：ankidroid/Anki-Android

- Kotlin 97.5%（Java 已跌出语言前三，迁移基本完成）、调研当日有 push、
  Gradle 9.7.1 多模块、`AnkiDroid/build.gradle.kts` 零 google-services/
  signingConfig 标记——构建摩擦比 tasks 更低。
- 49 个顶层包（deckpicker、reviewer、noteeditor、sync、multimedia、
  cardviewer、jsaddons、scheduling、workarounds……），注入面充足；复习/
  笔记/牌组管理全程离线可用。
- 偏弱项：核心复习界面是 WebView + JS 模板渲染，L2 无障碍树断言在卡片内容上
  的粒度受限（与 Wikipedia 文章页同类问题，不构成新增覆盖）；领域上同为
  "内容消费"，与 Wikipedia 的互补性弱于 tasks。

## 5. 否决项摘要

- **element-x-android**：纯 Compose 大工程，但无 homeserver 无法进入核心
  Journey，确定性验证需自建 Matrix 服务，运维负担不符合"快速反复构建运行"
  场景；可作未来第三宿主 revisit。
- **breezy-weather**：ViewModel 信号弱、核心依赖定位+网络。
- **kiwix-android**：构建疑带 native 依赖、内容需下载 ZIM 包。
- **ReadYou**：活跃度走弱（7 周无 push）、RSS 源需网络。
- **FossifyOrg/Calendar**：无 ViewModel/Compose，架构不典型。
- **beemdevelopment/Aegis**：实查为 Java 为主语言，不满足 (a)（与历史印象
  不符，以当日 languages API 为准）。

## 6. 结论与下一步

1. **推荐 tasks/tasks 为第二完整验证宿主**，ankidroid/Anki-Android 为顺位
   备选；Thunderbird 保留 2026-06 档案中的备选地位不变。
2. 下一步按 OpenCalc 校准流程做宿主校准 run：clone 并冻结 commit（记录
   commit/tree/archive SHA-256）→ `genericDebug` 变体可复现构建（独立
   GRADLE_USER_HOME 冷构建 + offline 重建字节一致）→ 模拟器部署启动 →
   3 次独立确定性 Journey 切片（建清单/加任务/设提醒 + 旋转或进程死亡）→
  上游测试基线分离 → run record 提交 `docs/runs/`。
3. 校准通过前，tasks/tasks 不得进入任何 Run Spec、注入对或正式分母；
   校准记录也必须显式声明其上游测试基线异常（若有）。

---
*调研方法备注：星数/pushed_at 经 `gh api repos/{repo}` 实查；语言占比经
`gh api repos/{repo}/languages`；Gradle 版本读各仓库默认分支
`gradle/wrapper/gradle-wrapper.properties`；模块数解析
`settings.gradle(.kts)` 的 include 行；私有依赖标记经 settings/build 文件
grep；架构信号经 `gh api search/code?q=ViewModel|Composable+repo:...`
（code search API，kiwix 的 ViewModel 查询被 rate limit 未取到）；注入面经
contents API 列顶层包目录。所有数据采集于 2026-09-28（UTC），未执行任何
clone、构建或设备动作。*
