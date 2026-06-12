# 开源 Android 宿主 App 选型调研

> 用途：为「AI 缺陷注入评测系统」选定 1–2 个开源 Kotlin Android App 作为缺陷注入宿主。
> 数据来源：GitHub API（`gh repo view` / `gh api repos/...` / languages / commits / contents API）实查 + 源码树抽查。
> **查询时间：2026-06（2026-06-11，美东时间）**。星数、commit 时间、语言占比均为当日实测值。

## 1. 硬指标回顾

| 编号 | 指标 |
|---|---|
| (a) | Kotlin 为主语言 |
| (b) | 活跃维护 |
| (c) | 典型架构（ViewModel、Compose 或 View 体系、协程） |
| (d) | 本地可构建（标准 Gradle，无特殊签名/私有依赖） |
| (e) | 可隔离注入点充足：单批互不相交（不同文件/模块）注入点 K≥8 可行 |
| (f) | 页面复杂度：多页面导航、列表、表单、后台任务，承载 lifecycle / config-change / process-death / navigation / coroutine 五类缺陷 |

## 2. 候选对照表（11 个候选，数据实查于 2026-06-11）

| 仓库 | Stars | 主语言占比 | 最近 commit | Gradle | 架构特征 | 模块/注入面 | 硬指标结论 |
|---|---|---|---|---|---|---|---|
| [wikimedia/apps-android-wikipedia](https://github.com/wikimedia/apps-android-wikipedia) | ≈2.9k | Kotlin 98.8% | 2026-06-11 | Wrapper 9.5.1，标准构建 | View(Fragment)+Compose 混合、ViewModel 大量使用（代码搜索 ViewModel 命中 185 处）、协程/Room/WorkManager/Paging | 单 `:app` 模块，但含 60+ 个按功能划分的顶层包 | **全部满足 → 首选** |
| [thunderbird/thunderbird-android](https://github.com/thunderbird/thunderbird-android) | ≈13.6k | Kotlin 81.5% / Java 17.9% | 2026-06-11 | Wrapper 9.5.1，标准构建 | Compose（`@Composable` 命中 694 处）+ 遗留 View（K-9 部分）、ViewModel/协程/Koin | settings.gradle.kts 共 **148 个模块**（feature:/core: 分层） | **全部满足 → 备选** |
| [bitwarden/android](https://github.com/bitwarden/android) | ≈9.0k | Kotlin 99.4% | 2026-06-10 | Wrapper 9.5.1 | 纯 Compose + MVVM + 协程 | 10 个模块（app/authenticator/core/data/network/ui 等） | (d) 受限：依赖 `maven.pkg.github.com/bitwarden/sdk`，**需 GITHUB_TOKEN 凭据**才能解析 SDK 依赖 |
| [duckduckgo/Android](https://github.com/duckduckgo/Android) | ≈4.7k | Kotlin 98.7% | 2026-06-11 | Wrapper 8.14.4 | View+Compose 混合、ViewModel/协程、Dagger/Anvil | 超大规模多模块（按 feature 拆分数百模块） | (d) 偏重：构建挂接 Develocity/refreshVersions 插件，工程体量与构建链复杂度高 |
| [element-hq/element-android](https://github.com/element-hq/element-android) | ≈3.7k | Kotlin 99.0% | 2026-06-08 | Wrapper 8.14.3 | MvRx(Mavericks)+Epoxy，架构风格偏非典型 | ~20+ 模块（vector、matrix-sdk-android 等） | (b)(c) 受限：已进入维护模式（被 Element X 取代），近期提交以发布说明为主；MvRx/Epoxy 非主流"典型架构" |
| [android/nowinandroid](https://github.com/android/nowinandroid) | ≈21.3k | Kotlin 99.1% | 2026-04-30 | Wrapper 9.4.0 | 纯 Compose + MVVM + 协程（官方教科书式） | ~35 个模块（core:/feature: api+impl 分层） | 满足 (a)(c)(d)(e)，**但属 Google 官方样板 App，真实业务度低**，且模型训练语料中曝光率极高，作评测宿主有"被背诵"风险 |
| [nextcloud/android](https://github.com/nextcloud/android) | ≈5.4k | Kotlin 57.6% / Java 40.9% | 2026-06-11 | Wrapper 9.5.0 | View 为主，Java/Kotlin 混杂 | 少量模块 | (a) 弱：Kotlin 仅 57.6%，Java 遗留多 |
| [wordpress-mobile/WordPress-Android](https://github.com/wordpress-mobile/WordPress-Android) | ≈3.1k | Kotlin 76.9% / Java 22.6% | 2026-06-12 | — | View+Compose 混合 | 多模块、体量大 | (a) 中等、(d) 偏重：历史包袱重、构建慢、Java 比例不低 |
| [TeamNewPipe/NewPipe](https://github.com/TeamNewPipe/NewPipe) | ≈38.6k | **Java 77.3%** / Kotlin 22.6% | 2026-06-10 | — | View 体系，RxJava 为主 | 单模块为主 | **不满足 (a)**：Java 为主 |
| [AntennaPod/AntennaPod](https://github.com/AntennaPod/AntennaPod) | ≈7.9k | **Java 98.0%** | 2026-06-10 | — | View 体系 | 多模块 | **不满足 (a)**：几乎纯 Java |
| [tuskyapp/Tusky](https://github.com/tuskyapp/Tusky) | ≈2.6k | Kotlin 93.0% | **2025-05-23（仓库已归档）** | — | View+ViewModel | 单模块 | **不满足 (b)**：GitHub 仓库已 archived，开发迁往 Codeberg |

> 注：星数取数量级（实测值：Wikipedia 2 950、Thunderbird 13 590、Bitwarden 8 967、DuckDuckGo 4 707、Element 3 699、NiA 21 343、Nextcloud 5 394、WordPress 3 138、NewPipe 38 641、AntennaPod 7 927、Tusky 2 570）。

## 3. 各候选评估

### 3.1 wikimedia/apps-android-wikipedia —— 首选

- **语言/活跃度**：Kotlin 98.8%（languages API），最近 commit 2026-06-11，提交频率为日级。Apache-2.0 许可。
- **构建**：Gradle Wrapper 9.5.1，标准 `settings.gradle.kts`，依赖仅 google()/mavenCentral()/jitpack，无私有 maven、无强制签名、无 google-services 强依赖（默认 dev flavor 可直接构建）。是社区公认"开箱即建"的大型真实 App。
- **架构**：经典 Activity/Fragment + ViewModel + 协程（代码搜索 ViewModel 命中 185 处），Room 数据库、WorkManager、Paging-Compose；新功能（search/feed/games 等）已用 Compose，旧页面为 View 体系——**View 与 Compose 双形态都可注入**。
- **注入面**：虽为单 `:app` 模块，但 `app/src/main/java/org/wikipedia/` 下有 60+ 个按功能划分的顶层包（feed、page、search、readinglist、notifications、edit、gallery、talk、places、watchlist、suggestededits、history、games、login、savedpages……），各功能包之间文件互不相交，**单批 K≥8 个不同文件/不同包的注入点轻松可行**（详见第 5 节盘点，列出 16 处）。
- **页面复杂度**：底部 NavTab 多页导航 + 深层页面栈（搜索→文章→图库→编辑）、大量 RecyclerView/Paging 列表、编辑/登录/回复等表单、SavedPageSyncService 与通知轮询等后台任务——五类缺陷均有天然落点。
- **风险**：单模块意味着"模块级隔离"退化为"包/文件级隔离"，但对缺陷注入互不相交的要求而言等价；工程约 40 万行，构建一次约数分钟，可接受。

### 3.2 thunderbird/thunderbird-android —— 备选

- **语言/活跃度**：Kotlin 81.5%（Java 17.9% 为 K-9 遗留邮件核心），最近 commit 2026-06-11，Mozilla 团队全职维护。
- **构建**：Gradle Wrapper 9.5.1，标准多模块构建，无私有依赖。
- **架构**：新代码全 Compose（`@Composable` 命中 694 处）+ ViewModel + 协程 + Koin DI；旧消息列表/阅读器仍有 View 与 Java。
- **注入面**：settings.gradle.kts 实测 **148 个模块**，`feature:account:*`、`feature:onboarding:*`、`feature:mail:message:*`、`feature:navigation:drawer:*`、`feature:widget:*`、`core:*` 等，模块级隔离极佳，K≥8 远超阈值。
- **风险**：模块粒度过细导致单模块逻辑量小，部分缺陷类别（process-death、深层导航）集中在 `app-common`/legacy 部分的 Java 代码中；双品牌（K-9/Thunderbird）flavor 使构建矩阵略复杂。
- **定位**：作为备选/第二宿主，与 Wikipedia 形成"单模块大包 vs 细粒度多模块"、"View+Compose 混合 vs Compose 为主"的互补覆盖。

### 3.3 bitwarden/android —— 否决（构建凭据）

Kotlin 99.4%、活跃（2026-06-10）、纯 Compose+MVVM，本是优质候选；但 `settings.gradle.kts` 实查包含 `maven.pkg.github.com/bitwarden/sdk` 仓库且要求 `GITHUB_TOKEN`/`gitHubToken` 凭据解析其 Rust SDK 产物，违反硬指标 (d)"无私有依赖"。若评测流水线可注入 token 可作第三备选，但不推荐增加此运维负担。

### 3.4 duckduckgo/Android —— 否决（构建链复杂度）

Kotlin 98.7%、日级活跃。但工程为数百个细粒度模块，构建挂接 Develocity 构建扫描与 refreshVersions 插件，依赖 Dagger/Anvil 编译器链，全量构建成本高、对评测系统的"快速反复构建"场景不友好。

### 3.5 element-hq/element-android —— 否决（维护模式 + 非典型架构）

Kotlin 99.0%，但项目已进入维护模式（官方主力转向 Element X / Compose 重写版），2026-06 的提交以版本说明合并为主；架构采用 MvRx(Mavericks)+Epoxy，与"典型 ViewModel/Compose 架构"指标不符，注入的缺陷形态会偏离主流 Android 代码风格。

### 3.6 android/nowinandroid —— 可用但不建议作主宿主

完全满足 (a)(c)(d)(e)：Kotlin 99.1%、教科书式 Compose+MVVM、35 模块。但它是 **Google 官方样板/演示 App**：业务逻辑薄、代码风格过度规范、且在公开语料中曝光率极高——被测模型很可能"背过"其代码，注入缺陷后的检测难度失真，**真实度低，评测效度存疑**。最近 commit 2026-04-30，活跃度也低于真实产品。可作为校准用对照组，不作正式宿主。

### 3.7 其余淘汰项

- **TeamNewPipe/NewPipe**：38.6k 星但 Java 77.3%，不满足 (a)。
- **AntennaPod/AntennaPod**：Java 98.0%，不满足 (a)。
- **tuskyapp/Tusky**：GitHub 仓库已于 2025-05 归档（迁往 Codeberg），不满足 (b)；GitHub 侧最近 commit 停在 2025-05-23。
- **nextcloud/android**：Kotlin 仅 57.6%，Java 遗留重，架构混杂。
- **wordpress-mobile/WordPress-Android**：活跃但 Java 22.6%、工程历史包袱重、构建偏慢，性价比低于前两名。

## 4. 推荐结论

- **首选：wikimedia/apps-android-wikipedia** —— 唯一在六项硬指标上全部高分的真实产品级 App：近纯 Kotlin、日级维护、ViewModel+协程+View/Compose 双形态、零门槛标准 Gradle 构建、60+ 互不相交的功能包、页面与后台任务复杂度充足。
- **备选：thunderbird/thunderbird-android** —— 148 模块的细粒度多模块工程，Compose 为主，与首选形成架构形态互补；Kotlin 占比（81.5%）与构建矩阵复杂度略逊于首选。

## 5. 首选注入点盘点初稿（Wikipedia）

基准路径：`app/src/main/java/org/wikipedia/`（以下目录与代表文件均经 GitHub contents API 实查确认存在，2026-06-11）。

五类缺陷代号：**L**=lifecycle，**C**=config-change，**P**=process-death，**N**=navigation，**X**=coroutine-concurrency。

| # | 包/页面（真实路径） | 代表文件（实查存在） | 功能 | 适合注入类别 |
|---|---|---|---|---|
| 1 | `page/` | `PageFragment.kt`（66KB）、`LinkHandler.kt` | 文章阅读页（WebView+BottomSheet） | L, C, N |
| 2 | `main/` + `navtab/` | `MainActivity.kt`、`MainFragment.kt` | 主界面与底部 Tab 导航 | N, P, L |
| 3 | `search/` | `SearchActivity.kt`、`RecentSearchesFragment.kt`、`HybridSearchResultsScreen.kt`(Compose) | 搜索（输入防抖+结果列表） | X, C, N |
| 4 | `feed/` | `HomeFragment.kt`、`HomeScreen.kt`(Compose)、`ForYouModulePager.kt` | 探索信息流（多卡片异步聚合） | X, L, C |
| 5 | `readinglist/` | `ReadingListFragment.kt`、`ReadingListFragmentViewModel.kt` | 阅读列表（Room CRUD+列表） | P, X, L |
| 6 | `notifications/` | `NotificationActivity.kt`、`NotificationPollBroadcastReceiver.kt` | 通知中心+后台轮询 | X, L |
| 7 | `edit/` | `EditSectionActivity.kt`、`EditSectionViewModel.kt` | 条目编辑表单（草稿/预览/提交） | P, C, X |
| 8 | `gallery/` | `GalleryActivity.kt`、`GalleryItemFragment.kt`、`GalleryItemViewModel.kt` | 图片画廊（ViewPager+横竖屏） | C, L |
| 9 | `talk/` | `TalkReplyActivity.kt`、`TalkReplyViewModel.kt`、`TalkTopicActivity.kt` | 讨论页与回复表单 | N, P, X |
| 10 | `places/` | `PlacesFragment.kt`、`PlacesFragmentViewModel.kt` | 地图找条目（定位+地图生命周期） | L, C |
| 11 | `watchlist/` | `WatchlistFragment.kt`、`WatchlistFilterActivity.kt` | 监视列表（过滤器+分页） | X, N |
| 12 | `suggestededits/` | `SuggestedEditsCardsFragment.kt`、`SuggestedEditsCardsViewModel.kt` | 建议编辑任务流（多步导航） | N, X |
| 13 | `history/` | `HistoryFragment.kt`、`HistoryViewModel.kt`、`history/db/` | 浏览历史（Room+列表） | L, X |
| 14 | `login/` + `createaccount/` | `LoginActivity.kt`、`LoginClient.kt` | 登录/注册表单（多步认证） | P, C |
| 15 | `savedpages/` | `SavedPageSyncService.kt`、`SavedPageSyncNotification.kt` | 离线文章后台同步 | X, P |
| 16 | `games/` | `GamesHubFragment.kt`、`GamesHubScreen.kt`(Compose)、`GamesHubViewModel.kt` | 游戏中心（Compose 新功能区） | L, X |

**互斥性与覆盖度检查**：16 个注入点分属 16 个互不相交的顶层包，单批任取 8 个即满足 K≥8 且文件零交集；五类缺陷覆盖数 L×9、C×7、P×6、N×6、X×11，每类至少 6 个候选落点，支持按类别分层抽样。另有 `concurrency/FlowEventBus.kt`（全局事件总线）可作 coroutine 类高难度注入点补充。

---
*调研方法备注：星数/语言/commit 经 `gh repo view --json`、`gh api repos/{repo}/languages`、`gh api repos/{repo}/commits` 实查；Gradle 版本读取各仓库默认分支 `gradle/wrapper/gradle-wrapper.properties`；模块数解析各仓库 `settings.gradle(.kts)`；架构特征经 GitHub code search（ViewModel/@Composable 命中数）与 contents API 源码树抽查。所有数据采集于 2026-06-11（UTC-4）。*
