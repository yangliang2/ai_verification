# Android 行为层缺陷金标准对照集 — 候选素材（candidates）

> 用途：作为"用 AI 验证 AI 生成代码"评测基准的金标准集（计划 AC8）。本集合中全部条目均为
> **非 AI 生成的真实历史缺陷**，来自知名开源 Android 项目的已关闭 issue / 已合并修复 PR，
> 用于对照 AI 注入缺陷库、度量验证 Agent 的盲区。

## 筛选标准

1. **行为层缺陷**：主流程（happy path）正常，仅在特定行为条件（旋转、进程被杀、快速双击、
   并发时序等）下出错；排除纯 UI 样式 / 文案 / 功能请求类问题。
2. **可复现路径清晰**：issue 中有明确的触发步骤或崩溃堆栈，可在宿主 App 中构造等价场景。
3. **真实性可验证**：每条均附真实 issue 链接，且已通过 `gh api` 实际拉取 issue 正文、
   关闭原因（state_reason）与时间线交叉引用确认内容相符；修复 PR 均确认已合并
   （或注明无法定位到单一修复提交）。被 stale-bot 关闭、未实际修复的 issue 已剔除
   （如 signalapp/Signal-Android#9220、nextcloud/android#4037）。

## 后续固化流程（概述）

本文件只负责"挖掘 + 核实"。后续接线工作：从每条素材中提取**缺陷模式**（错误的状态保存方式、
缺失的生命周期解注册、错误的线程切换等），移植到宿主 App 的对应模块中复现为可注入的金标准
缺陷用例，并编写触发脚本 / 断言；移植时保留本文件中的原始链接作为溯源。

---

## 1. lifecycle（生命周期回调：监听泄漏、重复注册、回调时序）

### L1. Signal-Android — 列表项 Recipient 监听器导致 Context 泄漏
- 项目：signalapp/Signal-Android
- Issue：https://github.com/signalapp/Signal-Android/issues/3224
- 类别：lifecycle（监听器泄漏）
- 描述：RecyclerView/ListView 列表项注册了 Recipient 变更监听器，但 Activity
  pause/stop/destroy 时列表项无法收到回收通知，监听器持有 Context 强引用造成内存泄漏。
- 触发条件：打开含联系人列表的页面后退出 Activity；监听器未解注册，Context 被持有。
- 修复 commit：https://github.com/signalapp/Signal-Android/commit/ed0e1c07b92b6da63bc5b7e082e9914c8c8a6927
  （"Fix some memory leaks. Fixes #3224"）；相关 PR：https://github.com/signalapp/Signal-Android/pull/3214
- 移植可行性：**高** — "列表项注册监听器 + 生命周期结束未解注册"是通用模式，任何带列表的宿主页面均可复刻。

### L2. Element Android — 离开 DM 时 loading 对话框泄漏 Window
- 项目：element-hq/element-android
- Issue：https://github.com/element-hq/element-android/issues/4713
- 类别：lifecycle（对话框未随宿主销毁，WindowLeaked）
- 描述：在房间资料页执行"离开房间"，弹出 loading Dialog 后 Activity finish，Dialog 未在
  生命周期结束前 dismiss，日志报 `android.view.WindowLeaked: ... has leaked window DecorView`。
- 触发条件：触发一个会 finish 当前 Activity 的异步操作，期间显示非 DialogFragment 的 Dialog。
- 修复 PR：https://github.com/element-hq/element-android/pull/4729 （已合并 2021-12-16，
  "Avoid leaking Activity Window when showing loading dialog"）
- 移植可行性：**高** — 异步操作 + loading 弹窗 + Activity 提前 finish 即可复现，无外部依赖。

### L3. WordPress-Android — onSaveInstanceState 之后执行 FragmentManager 事务崩溃
- 项目：wordpress-mobile/WordPress-Android
- Issue：https://github.com/wordpress-mobile/WordPress-Android/issues/2910
- 类别：lifecycle（回调时序：状态保存后提交事务）
- 描述：MediaBrowserActivity 在异步回调（onSavedEdit）中调用 `popBackStack()`，若此时
  Activity 已执行过 onSaveInstanceState（如被切到后台），抛出
  `IllegalStateException: Can not perform this action after onSaveInstanceState`。
- 触发条件：发起编辑保存的异步操作后立即将 App 切到后台 / 锁屏，回调返回时执行 Fragment 事务。
- 修复 PR：https://github.com/wordpress-mobile/WordPress-Android/pull/2972 （已合并 2015-07-15）
- 移植可行性：**高** — 经典缺陷模式（异步回调中无状态检查地提交 Fragment 事务），极易在宿主 App 注入与复现。

---

## 2. config-change（旋转 / 配置变更状态丢失）

### C1. Tusky — 回复时旋转屏幕，已输入正文丢失
- 项目：tuskyapp/Tusky
- Issue：https://github.com/tuskyapp/Tusky/issues/45
- 类别：config-change（输入状态未正确保存/恢复）
- 描述：点"回复"并在 @用户名 后输入文字，竖屏转横屏后输入的正文消失、仅剩用户名——回复
  场景的文本恢复逻辑有缺陷（新发帖场景恢复正常）。
- 触发条件：回复模式下输入文字 → 旋转屏幕（Activity 重建）。
- 修复：无单一修复 commit；据维护者在 issue 中说明，后续通过"撰写页不再随旋转重建"
  （configChanges 处理）使该缺陷不再出现。
- 移植可行性：**高** — "EditText 状态在特定入口路径下未纳入 savedInstanceState"模式清晰，宿主表单页即可复刻。

### C2. Thunderbird for Android — 撰写邮件时旋转屏幕崩溃（回归缺陷）
- 项目：thunderbird/thunderbird-android
- Issue：https://github.com/thunderbird/thunderbird-android/issues/8606
- 类别：config-change（重建路径崩溃）
- 描述：在统一收件箱开始撰写邮件并填入有效收件人后，旋转设备 90° 再转回，App 崩溃；
  为 8.x 引入的回归。
- 触发条件：撰写界面含收件人 → 连续旋转屏幕两次。
- 修复：维护者确认在 11.0b5 的一批崩溃修复中被解决，未定位到单一修复 commit。
- 移植可行性：**中** — 崩溃模式真实且触发路径清晰，但因无修复 diff，注入时需自行设计等价的重建期空指针/状态错乱。

### C3. K-9 Mail / Thunderbird — 旋转屏幕后收件人地址重复
- 项目：thunderbird/thunderbird-android
- Issue：https://github.com/thunderbird/thunderbird-android/issues/10288
  （同类重复报告：https://github.com/thunderbird/thunderbird-android/issues/10595 ）
- 类别：config-change（状态恢复与已有状态叠加）
- 描述：撰写界面启用 Cc/Bcc 字段后旋转屏幕，收件人 token 文本被重复添加（恢复逻辑把
  savedInstanceState 中的地址再次 append 而非替换）。
- 触发条件：撰写邮件填入地址 → 屏幕方向变化 → 地址成倍增加。
- 修复 PR：https://github.com/thunderbird/thunderbird-android/pull/10353 （已合并 2026-01-14，
  "fix(tokenautocomplete): prevent duplicated recipient text on configuration change"）
- 移植可行性：**高** — "恢复时叠加而非覆盖"是非常典型的可注入行为缺陷，断言（元素数量翻倍）容易自动化。

### C4. AntennaPod — 旋转屏幕后确认对话框消失
- 项目：AntennaPod/AntennaPod
- Issue：https://github.com/AntennaPod/AntennaPod/issues/6289
- 类别：config-change（Dialog 未随配置变更恢复）
- 描述："全部标记为已播放"的确认对话框在屏幕旋转后直接消失（使用普通 AlertDialog 而非
  DialogFragment，Activity 重建后对话框不会恢复），用户操作意图丢失。
- 触发条件：弹出确认对话框 → 旋转屏幕 → 对话框消失。
- 修复：随 3.0 版本对话框重构解决（消失问题不再出现）；残余的对话框高度问题另行跟踪于
  https://github.com/AntennaPod/AntennaPod/issues/6470 。
- 移植可行性：**高** — AlertDialog vs DialogFragment 的恢复差异是教科书级行为缺陷，注入与验证都很直接。

---

## 3. process-death（后台杀进程后恢复崩溃 / 状态错乱）

### P1. K-9 Mail — 进程被杀后草稿正文丢失
- 项目：thunderbird/thunderbird-android
- Issue：https://github.com/thunderbird/thunderbird-android/issues/3970
- 类别：process-death（状态错乱：部分状态恢复、部分丢失）
- 描述：撰写邮件期间切换到其他应用（进程被系统回收），返回后附件与签名修改仍在，
  但邮件正文文本丢失——正文未纳入进程死亡恢复路径。
- 触发条件：撰写界面输入正文 + 添加多个附件 → 切到其他 App 触发后台杀进程 → 返回。
- 修复：issue 被关闭时未定位到单一修复 commit（撰写界面后续整体重写）。
- 移植可行性：**高** — "部分字段持久化、部分字段只在内存"造成恢复后状态不一致，模式清晰，可用 `am kill` 脚本化复现。

### P2. Tusky — onSaveInstanceState 写入整张位图导致 TransactionTooLargeException
- 项目：tuskyapp/Tusky
- Issue：https://github.com/tuskyapp/Tusky/issues/419
- 类别：process-death（保存状态体积超限，保存阶段即崩溃）
- 描述：ComposeActivity 的 onSaveInstanceState 把媒体预览的完整 Bitmap 写进 Bundle，
  超过 Binder 事务上限抛 `android.os.TransactionTooLargeException`，进入后台即崩溃。
- 触发条件：撰写界面附加图片 → 切后台（系统保存实例状态）。
- 修复 commit：https://github.com/tuskyapp/Tusky/commit/bc59d4d938ff5565831e052a3461cf94e0bf2bcf
  （"Fix issues with media uploads restoring. Fixes #419. Fixes #308."）
- 移植可行性：**高** — 向 savedInstanceState 塞大对象即可稳定复现，崩溃信号明确，适合自动断言。

### P3. NewPipe — 状态恢复时 StateSaver 返回空数组导致启动崩溃
- 项目：TeamNewPipe/NewPipe
- Issue：https://github.com/TeamNewPipe/NewPipe/issues/5996
- 类别：process-death（恢复路径空值崩溃）
- 描述：MainActivity 重建恢复时，自研 StateSaver 从缓存文件目录读取状态，目录列表为
  null 时未判空，抛 `NullPointerException: Attempt to get length of null array`，
  应用无法启动（Unable to start activity）。
- 触发条件：进程死亡 / Activity 重建后从持久化状态恢复，且状态缓存目录异常（被清理）。
- 修复 PR：https://github.com/TeamNewPipe/NewPipe/pull/5999 （已合并 2021-04-06，
  改动 `util/StateSaver.java`）
- 移植可行性：**中** — 需要宿主 App 有类似的自定义状态持久化层；可简化为"恢复路径读取缓存未判空"。

---

## 4. navigation（返回栈 / 导航状态错乱、重复打开）

### N1. Element Android — 快速双击空间按钮必现 "Fragment already added" 崩溃
- 项目：element-hq/element-android
- Issue：https://github.com/element-hq/element-android/issues/7087
- 类别：navigation（重复打开同一目的地）
- 描述：快速双击 space FAB，同一个 SpaceListBottomSheet 被 show 两次，主线程抛
  `IllegalStateException: Fragment already added: SpaceListBottomSheet`，应用崩溃。
- 触发条件：对打开 BottomSheet/DialogFragment 的按钮快速连点两次（无防抖、show 前不检查是否已添加）。
- 修复 PR：https://github.com/element-hq/element-android/pull/7102 （已合并 2022-09-14，
  "Fixes Crash On Double Click Of Space FABs"）
- 移植可行性：**高** — 去掉防抖即可注入，UI 自动化双击即可稳定触发。

### N2. Nextcloud Android — 第三方 App 经 SSO 添加账号后返回栈错误
- 项目：nextcloud/android
- Issue：https://github.com/nextcloud/android/issues/6971
- 类别：navigation（跨应用流程的返回栈错乱）
- 描述：第三方 App 通过 SSO 添加新账号，授权完成显示文件列表后按返回键，没有回到
  第三方 App，而是逐层回退到 Web 登录页等中间页面——登录流程的中间 Activity 未清出返回栈。
- 触发条件：外部入口（deep link / 跨 App intent）进入多步流程，完成后按返回。
- 修复 PR：https://github.com/nextcloud/android/pull/6983 （已合并 2020-09-23，
  "directly go back to app if SSO is used"）
- 移植可行性：**中** — 需要宿主 App 有跨入口的多步流程；可简化为 deep link 进入流程后中间页未 finish。

### N3. Tusky — 搜索页按返回键第一次无效
- 项目：tuskyapp/Tusky
- Issue：https://github.com/tuskyapp/Tusky/issues/3570
- 类别：navigation（返回事件被吞、返回行为不一致）
- 描述：在搜索视图中执行过搜索后按系统返回键，第一次按压无任何反应，需按第二次才能返回
  （SearchView 焦点/折叠状态拦截了返回事件）。
- 触发条件：搜索页输入并执行搜索 → 按硬件/手势返回。
- 修复 PR：https://github.com/tuskyapp/Tusky/pull/3571 （已合并 2023-09-27，
  "Also provide a 'direct' back with the hardware button"）
- 移植可行性：**高** — onBackPressed 分发逻辑缺陷，注入点单一，断言（一次返回应退出页面）简单。

### N4. AntennaPod — 双击章节按钮崩溃（重复打开 Fragment）
- 项目：AntennaPod/AntennaPod
- Issue：https://github.com/AntennaPod/AntennaPod/issues/5548
- 类别：navigation（重复打开）
- 描述：播放界面双击"章节"按钮，章节对话框被打开两次导致崩溃。
- 触发条件：对打开对话框的入口快速双击。
- 修复 PR：https://github.com/AntennaPod/AntennaPod/pull/5555 （已合并 2021-11-21，
  "Do not crash when opening chapter dialog twice"）
- 移植可行性：**高** — 与 N1 同模式、不同项目印证，可作为同型缺陷的第二个金标准样本。

---

## 5. coroutine-concurrency（并发竞态、泄漏、线程约束违例）

### X1. AntennaPod — ExoPlayer 方法被多线程调用导致竞态崩溃
- 项目：AntennaPod/AntennaPod
- Issue：https://github.com/AntennaPod/AntennaPod/issues/3025
- 类别：coroutine-concurrency（违反单线程约束的播放器调用）
- 描述：ExoPlayer 实例的方法从多个线程被调用，违反其单线程访问约束，在播放中返回桌面等
  时机随机崩溃（播放仍继续但进程报错）。
- 触发条件：播放器控制调用分散在工作线程与主线程，时序竞争下崩溃（偶发）。
- 修复 PR：https://github.com/AntennaPod/AntennaPod/pull/3097 （已合并 2019-04-11，
  "Executing all ExoPlayer methods on main thread"；前置方案 https://github.com/AntennaPod/AntennaPod/pull/3087 ）
- 移植可行性：**高** — "对线程受限对象的跨线程调用"可在宿主 App 任何持线程约束组件上注入；偶发性需用压测脚本放大。

### X2. AntennaPod — 单例错误导致并发下重新打开已关闭的 SQLiteDatabase
- 项目：AntennaPod/AntennaPod
- Issue：https://github.com/AntennaPod/AntennaPod/issues/1945
- 类别：coroutine-concurrency（单例/资源生命周期竞态）
- 描述：DownloadService 运行期间抛
  `IllegalStateException: attempt to re-open an already-closed object: SQLiteDatabase`——
  getInstance 实现有缺陷，未正确返回缓存实例，多个调用方持有不同实例，一方 close 后另一方继续用。
- 触发条件：后台服务与前台逻辑并发访问数据库单例，其中一方关闭连接。
- 修复 PR：https://github.com/AntennaPod/AntennaPod/pull/2627 （已合并 2018-04-07，
  "Actually return instance in getInstance"）
- 移植可行性：**高** — 修复 diff 极小（单例返回错误），是理想的"一行行为缺陷"注入样本。

### X3. Element Android — 二维码登录竞态导致交叉签名建立失败
- 项目：element-hq/element-android
- Issue：https://github.com/element-hq/element-android/issues/7676
- 类别：coroutine-concurrency（异步步骤间缺少同步/等待）
- 描述：扫码登录流程中，验证检查在本设备 device keys 尚未上传/下载完成前就执行，
  在慢网络/慢服务器下竞态触发，导致交叉签名无法建立并报错；快环境下不可见。
- 触发条件：弱网或慢 homeserver 下执行 QR 登录（步骤 A 未完成即执行依赖它的步骤 B）。
- 修复 PR：https://github.com/element-hq/element-android/pull/7699 （已合并 2022-12-09，
  "Download device keys for self prior to verification checks"；补充修复 https://github.com/element-hq/element-android/pull/7737 ）
- 移植可行性：**中** — 模式（缺失 await 的依赖步骤）通用，但需在宿主 App 构造可注入延迟的双步异步流程。
 
### X4. NewPipe — 列表更新时序竞态导致 "ViewHolder views not attached" 崩溃
- 项目：TeamNewPipe/NewPipe
- Issue：https://github.com/TeamNewPipe/NewPipe/issues/4475
- 类别：coroutine-concurrency（异步加载与 UI 更新时序竞态）
- 描述：列表分页异步加载与 RecyclerView 更新/动画时序竞争，出现 ViewHolder 视图未附着
  状态下的更新，导致列表页崩溃；初始加载条数不足时更易触发。
- 触发条件：列表页快速滚动/触发分页加载，异步结果到达时机与布局阶段冲突（偶发）。
- 修复 PR：https://github.com/TeamNewPipe/NewPipe/pull/7659 （已合并 2022-02-19，
  "Load enough initial items and fix crash in lists"）
- 移植可行性：**中** — 偶发竞态，注入容易（在错误时机 notify）但稳定复现需要脚本化滚动压测。

---

## 统计

| 类别 | 条数 |
|---|---|
| lifecycle | 3 |
| config-change | 4 |
| process-death | 3 |
| navigation | 4 |
| coroutine-concurrency | 4 |
| **总计** | **18** |

### 核实记录
- 全部 18 条 issue 均已于 2026-06-11 通过 `gh api repos/<repo>/issues/<n>` 拉取正文与
  `state/state_reason` 确认：均为 closed（其中 17 条 completed；TB#8455 等 not_planned /
  stale 关闭的候选已剔除）。
- 12 条修复 PR 通过 `gh api repos/<repo>/pulls/<n>` 确认 `merged_at` 非空；2 条修复
  commit（Signal ed0e1c07、Tusky bc59d4d9）通过 commits API 确认提交信息含 "Fixes #issue"。
- 无修复链接的条目（C1、C2、C4、P1）已在正文注明关闭方式，移植时按"等价缺陷模式"处理。
