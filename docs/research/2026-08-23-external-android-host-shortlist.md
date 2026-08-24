# 独立外部 Android host 候选筛选

日期：2026-08-23（America/New_York）
状态：auditor-side 桌面筛选，附 OpenCalc branch-local calibration 更新；**不是**
Qualification Manifest、host freeze 或 Verification Agent 能力证据

## 结论

下一阶段应先用 **OpenCalc 做 calibration**，确认 Injection Lab → Discovery
Campaign → Run Spec → Android runtime 的接缝；接缝稳定后，优先对 **Catima**
做全新 auditor-side preflight 并冻结为 unseen holdout。若 Catima 的 Java/Gradle
工具链或 API 35 实机接缝不稳定，则依次降级到 **Markor**、**Birday**；Fossify
Gallery 只作为权限和 MediaStore 成本更高的储备。

| 排名 | 项目 | 建议角色 | 桌面分 | 当前判断 |
|---:|---|---|---:|---|
| 1 | Catima | 首选 unseen holdout | 92 | fully offline、API 35 官方 instrumentation、确定性本地数据；先解决 Java 21/25 工具链差异 |
| 2 | Markor | holdout 备选 | 90 | 离线文本编辑和文件 oracle 很强；已在本机完成 debug build，首次启动/存储权限需预检 |
| 3 | Birday | holdout 备选 | 87 | 单模块、Room、本地事件流；日期、通知和可选联系人/日历权限需钉死 |
| 4 | Fossify Gallery | 高成本 holdout 储备 | 84 | 本地媒体行为面真实；MediaStore、权限、缩略图异步会提高 flakiness 风险 |
| 5 | OpenCalc | calibration only | 81 | 最容易形成精确机器 oracle，但体量和状态空间不足以承载正式外部泛化声明 |

分数只用于排序，不是 qualification 结果。正式 holdout 必须通过下述全部硬门槛；
总分不能补偿硬门槛失败。

## Rubric

### 硬门槛

1. **来源与许可**：官方公开仓库、OSI 许可、未归档，并能冻结 immutable commit。
2. **独立构建**：fresh clone 可生成可安装 debug APK；不需要私钥、私有 Maven、
   付费 SDK 或发布凭据。
3. **自包含运行路径**：核心 Journey 不要求登录、真实后端、云账号、SIM、传感器
   或物理设备；数据可由 auditor 确定性 seed 和 reset。
4. **API 35 可执行性**：`minSdk <= 35`，有明确 application ID、launcher activity、
   build variant 和 APK 输出；最终仍须在项目指定 API 35 AVD 上实证。
5. **可度量行为缺陷**：能在 happy path 不变的前提下构造 behavior-layer defect 与
   matched control，并由独立于注入实现的机器 oracle 判定。
6. **盲化纪律**：候选调研不公开最终 source locator、补丁、hidden mapping、预期
   evidence 或 oracle 阈值；正式选择、pair 和 mapping 在 auditor-only 空间冻结。

### 加权项（100）

| 维度 | 权重 |
|---|---:|
| 确定性 seed、reset 和 machine oracle | 25 |
| 无密钥 build/install/launch | 20 |
| lifecycle/navigation/process-death/concurrency 等行为接缝 | 20 |
| 非玩具业务与代表性复杂度 | 15 |
| 维护状态、许可和 provenance | 10 |
| 构建时长、权限、异步和设备运维成本 | 10 |

桌面分的逐项构成为：

| 项目 | seed/oracle 25 | build 20 | behavior 20 | 代表性 15 | provenance 10 | 运维 10 | 合计 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Catima | 24 | 16 | 19 | 15 | 10 | 8 | 92 |
| Markor | 24 | 19 | 17 | 14 | 9 | 7 | 90 |
| Birday | 22 | 19 | 17 | 12 | 9 | 8 | 87 |
| Fossify Gallery | 18 | 18 | 19 | 14 | 9 | 6 | 84 |
| OpenCalc | 25 | 20 | 13 | 8 | 8 | 7 | 81 |

正式 holdout 还要求代表性项至少 10/15。OpenCalc 即使总分超过 80，也因此只能
用于 calibration。

## 方法与声明边界

- 对官方 GitHub 默认分支做了 2026-08-23 的 shallow clone，并冻结到下列 commit。
- “规模”是该 commit 中 tracked `*.kt`、`*.java`、`*.xml`、`*.gradle` 和
  `*.gradle.kts` 的总行数；它包含资源/翻译，只表示相对操作成本，不表示业务代码量。
- 模块数来自官方 `settings.gradle(.kts)`。
- 桌面筛选阶段只有 Markor 做过本机 build spot-check。筛选完成后，OpenCalc 又完成了
  branch-local build/install/runtime calibration；详见其候选条目与 run record。其余
  候选仍只是 source/CI static audit，**没有**被表述为本机 build、install、launch
  或 runtime 成功。
- 这份 repo-visible 文档只给出缺陷族级边界。后续 formal Verification Agent 不应
  获得本轮聊天、auditor preflight、具体注入点或 hidden mapping；使用同一线程继续
  调试任一候选会消耗其 holdout 身份。
- 本文的 `unseen` 只表示 formal invocation 未接触 auditor-side 调试、候选 pair 和
  hidden mapping。候选均是公开 GitHub 项目，本文不声称所用模型从未在预训练或其他
  外部上下文中见过其公开源码；任何 same-family limitation 必须继续披露。

## 五个候选

### 1. Catima — 首选 unseen holdout

- 冻结审计点为 [`d1d8eaa`](https://github.com/CatimaLoyalty/Android/commit/d1d8eaacae12fe241e9e3cd8a1298bac624ece56)，
  2026-08-23 位于官方 `main`；GPL-3.0，约 42,924 行，`:app`、`:wear`、`:shared`
  三个模块。
- 官方说明它在 Android 6+ 上 **fully offline**，卡片保存在设备上；相机、NFC、
  蓝牙都不是核心手工录入路径的硬依赖。[官方 README](https://github.com/CatimaLoyalty/Android/blob/d1d8eaacae12fe241e9e3cd8a1298bac624ece56/docs/README.md#L1-L74)
- `app` 为 `compile/targetSdk 36`、`minSdk 23`；默认 `foss` flavor，debug suffix
  为 `.debug`，因此预期命令/包为 `./gradlew :app:assembleFossDebug` 和
  `me.hackerchick.catima.debug`。release signing 不是 debug build 前提。
  [app build](https://github.com/CatimaLoyalty/Android/blob/d1d8eaacae12fe241e9e3cd8a1298bac624ece56/app/build.gradle.kts#L8-L78)
- 官方 CI 对 `foss`、`fdroidLegacy`、`gplay` 均 build、lint、unit test，并分别在
  API 23 与 API 35 跑 instrumentation；这是本轮唯一已有官方 API 35 device-test
  信号的候选。[Android CI](https://github.com/CatimaLoyalty/Android/blob/d1d8eaacae12fe241e9e3cd8a1298bac624ece56/.github/workflows/android.yml#L1-L75)
- 可行边界（非正式 mapping）：本地卡片的 create/edit/list/detail、前后台切换、
  configuration change 和 process recreation。auditor 可 seed 固定文本型条码，
  用 layout/card 字段与本地持久化状态形成双重 oracle；不需要相机或网络。
- 主要风险：Gradle wrapper 是 9.7、Kotlin/JVM toolchain 声明 21，但当前 `build.sh`
  与 CI 实际默认/安装 Java 25；本机只有 Java 17。本地工具链必须先按单一版本重放，
  不能把官方 CI 通过替代为本机 build 证据。

### 2. Markor — holdout 备选

- 冻结审计点为 [`e05521f`](https://github.com/gsantner/markor/commit/e05521f798dfc8a4a8a2721d7eeeedc0d8a3197c)，
  2026-07-23 位于官方 `master`；Apache-2.0，约 68,492 行，单 `:app` 模块。
- 官方明确说明应用可完全离线，文件保存在本地；README 也给出 `make all install run`
  的开发入口。[README](https://github.com/gsantner/markor/blob/e05521f798dfc8a4a8a2721d7eeeedc0d8a3197c/README.md#L130-L174)
- `compile/targetSdk 35`、`minSdk 18`，三个 flavors；稳定入口是
  `./gradlew :app:assembleFlavorDefaultDebug`，包为 `net.gsantner.markor`。
  [app build](https://github.com/gsantner/markor/blob/e05521f798dfc8a4a8a2721d7eeeedc0d8a3197c/app/build.gradle#L23-L86)
- 官方 CI 使用 Java 21 执行 `make clean all`。[CI](https://github.com/gsantner/markor/blob/e05521f798dfc8a4a8a2721d7eeeedc0d8a3197c/.github/workflows/build-android-project.yml#L31-L54)
  本轮在 macOS/Java 17/已安装 Android SDK 上执行上述 debug 命令，结果为
  `BUILD SUCCESSFUL in 8m 31s`；这是临时桌面 spot-check，不是 committed run evidence。
- 可行边界：固定纯文本文件的 edit/autosave/preview 与 lifecycle/process recreation；
  oracle 可同时检查 UI 文本与落盘字节 checksum。避免远程图片、WebView 网络内容和
  加密文件，以保持自包含。
- 主要风险：首次启动和 Android 新版存储授权路径较宽，manifest/intent surface 大；
  preflight 必须证明固定 AppData 或 SAF 路径可重复 seed，而不是依赖人工选择目录。

### 3. Birday — holdout 备选

- 冻结审计点为 [`daf6ad2`](https://github.com/m-i-n-a-r/birday/commit/daf6ad20836eb53f4ca0fb170567f5471ce897ff)，
  2026-03-26 位于官方 `master`；GPL-3.0，约 35,196 行，单 `:app` 模块。
- 应用以本地生日/事件为核心；联系人和 Calendar import 是可选路径。
  [README](https://github.com/m-i-n-a-r/birday/blob/daf6ad20836eb53f4ca0fb170567f5471ce897ff/README.md#L1-L70)
- `compile/targetSdk 36`、`minSdk 26`，`assembleDebug` 产生
  `com.minar.birday.debug`；build 无 signing 或 API-key 前置，并直接依赖 Room 与
  WorkManager。[app build](https://github.com/m-i-n-a-r/birday/blob/daf6ad20836eb53f4ca0fb170567f5471ce897ff/app/build.gradle.kts#L1-L90)
- main manifest 未声明 `INTERNET`，launcher 是 `MainActivity`，但声明了可拒绝的
  contacts/calendar/notification 权限；官方 CI 运行 `./gradlew build`。
  [manifest](https://github.com/m-i-n-a-r/birday/blob/daf6ad20836eb53f4ca0fb170567f5471ce897ff/app/src/main/AndroidManifest.xml#L1-L100)
  [CI](https://github.com/m-i-n-a-r/birday/blob/daf6ad20836eb53f4ca0fb170567f5471ce897ff/.github/workflows/build.yaml#L1-L22)
- 可行边界：固定日期的本地 event CRUD、Room persistence、进程重建后的列表/详情。
  oracle 可绑定固定时区/系统日期后检查 layout 与 debug database；第一 pair 不使用
  定时通知，避免把 scheduler timing 当作缺陷信号。
- 主要风险：主 Activity 自行处理 configuration changes，rotation 不天然触发
  recreation；日期、locale、时区、欢迎页和可选权限必须在 Run Spec 中冻结。

### 4. Fossify Gallery — 高成本 holdout 储备

- 冻结审计点为 [`1933e40`](https://github.com/FossifyOrg/Gallery/commit/1933e40ac69787104b3b91343b643666a49fd601)，
  2026-08-01 位于官方 `main`；GPL-3.0，约 50,932 行，单 `:app` 模块。
- `compile/targetSdk 36`、`minSdk 26`；有 `foss`/`gplay` flavors，debug suffix
  `.debug`。release signing 仅在 keystore/env 存在时启用，因此 auditor 入口应固定为
  `./gradlew :app:assembleFossDebug`、包 `org.fossify.gallery.debug`。
  [app build](https://github.com/FossifyOrg/Gallery/blob/1933e40ac69787104b3b91343b643666a49fd601/app/build.gradle.kts#L1-L120)
- 官方 README 将其定义为本地私密 gallery；main manifest 声明 Android 13+
  media permissions、selected-photo、notification 和可选 camera 等权限。
  [README](https://github.com/FossifyOrg/Gallery/blob/1933e40ac69787104b3b91343b643666a49fd601/README.md#L1-L45)
  [manifest](https://github.com/FossifyOrg/Gallery/blob/1933e40ac69787104b3b91343b643666a49fd601/app/src/main/AndroidManifest.xml#L1-L50)
- 官方 PR workflow 明确跑 `:app:testFossDebugUnitTest`，testing-build workflow 生成
  foss debug APK；正式 release secrets 与 debug path 分离。
  [workflows](https://github.com/FossifyOrg/Gallery/tree/1933e40ac69787104b3b91343b643666a49fd601/.github/workflows)
- 可行边界：auditor 预置固定小图集后，检查相册列表/选择/查看器在 rotation、后台与
  process recreation 后的状态；oracle 结合 MediaStore/file inventory 与 layout。
- 主要风险：权限对话框、MediaStore 扫描、缩略图生成和图像解码均可能引入等待与
  flakiness；只有在三次 clean reset 的 seed-to-visible 时延稳定后才可冻结。

### 5. OpenCalc — calibration only

- 冻结审计点为 [`0584d61`](https://github.com/clementwzk/OpenCalc/commit/0584d61189e916a62a3b402223b35e1d7a3093db)，
  2026-07-10 位于官方 `main`；GPL-3.0，约 11,803 行，单 `:app` 模块。
- `compile/targetSdk 35`、`minSdk 21`，`assembleDebug` 生成
  `com.darkempire78.opencalculator.debug`；无外部服务、signing secret 或 flavor
  选择。[app build](https://github.com/clementwzk/OpenCalc/blob/0584d61189e916a62a3b402223b35e1d7a3093db/app/build.gradle.kts#L1-L58)
- 官方功能包括 portrait/landscape 与 history；main manifest 无 `INTERNET`，只有
  vibration、overlay/full-screen 相关权限和一个 launcher activity。
  [README](https://github.com/clementwzk/OpenCalc/blob/0584d61189e916a62a3b402223b35e1d7a3093db/README.md#L35-L75)
  [manifest](https://github.com/clementwzk/OpenCalc/blob/0584d61189e916a62a3b402223b35e1d7a3093db/app/src/main/AndroidManifest.xml#L1-L55)
- 可行边界：固定按键序列、结果和 history 在 orientation/process recreation 后的
  一致性；layout text 与 preferences/history 可形成简单机器 oracle。
- 淘汰正式 holdout 的理由：源码与状态空间明显小于其他候选，核心行为集中度高，
  很容易退化为“验证计算器”；仓库也没有 checked-in GitHub Actions build workflow。
  它适合先烧通接缝，不适合支撑外部真实项目泛化声明。
- 后续 local-only calibration 已在固定 commit 上完成：独立 Gradle home 冷构建
  `4m44s`，同一缓存的 `--offline clean assembleDebug` 为 `12s`，APK byte-for-byte
  一致；API 35 AVD 的三轮 `pm clear → cold start → 12+34=` 均得到 `46`，初始/结果
  layout JSON 各自三轮完全一致。零间隔 pilot 会漏掉一次 tap，350 ms action settle
  才稳定；上游 unit suite 为 35/36，通过 debug suffix 修正语义后的 lifecycle
  instrumentation slice 为 3/3。证据当前位于
  [`docs/runs/2026-08-23-opencalc-calibration/`](../runs/2026-08-23-opencalc-calibration/README.md)，
  已在 `0719a05` 提交并发布到 GitHub；它仍只构成有界校准证据，不改变 OpenCalc 的
  calibration-only 角色。

## 淘汰或延期摘要

| 项目 | 结论 | 主要理由与一手来源 |
|---|---|---|
| Thunderbird Android | 延期 | 旧文档把它当第二宿主，但邮件的代表性行为通常需要账号和服务器，且工程构建矩阵很大；在证明无登录、自包含、可机器判定的 Journey 前，不满足本轮门槛。[官方仓库](https://github.com/thunderbird/thunderbird-android) |
| Tasks.org | 延期 | `genericDebug` 的 map/google key 可为空，因此不能武断称其 debug 需要 secret；但官方 release workflow 使用 keystore/API secrets，工程约 206k 行、8 模块并含多种同步/地图服务，首个 holdout 成本过高。[app build](https://github.com/tasks/tasks/blob/ef45d290e28838dab6567dba08c019eb058f7b7f/app/build.gradle.kts#L61-L120) [bundle workflow](https://github.com/tasks/tasks/blob/ef45d290e28838dab6567dba08c019eb058f7b7f/.github/workflows/bundle.yml#L80-L170) |
| Auxio | 延期 | 本地离线行为很好，但官方构建要求 recursive submodules、CMake、Ninja、NDK 28.2 和 Java 21；不适合作为第一条纵向切片。[官方 build 文档](https://github.com/OxygenCobalt/Auxio#building) |
| Etar | 延期 | 自身不含 CalDAV client，但依赖 Android CalendarProvider、calendar permissions 和系统日期；provider seed/reset 与时间 oracle 成本高于前三名。[README](https://github.com/Etar-Group/Etar-Calendar#how-to-use-etar) [manifest](https://github.com/Etar-Group/Etar-Calendar/blob/60b20da5eeb4418d55133f05affbbe75621aa9c9/app/src/main/AndroidManifest.xml#L20-L60) |
| Unitto | 淘汰 | 技术上确定性强，但官方 contribution guidance 明确写明禁止任何 AI 使用。虽然这不是对 GPL fork 权利的法律判断，为尊重上游贡献政策，本项目不把它选作 AI Verification host。[CONTRIBUTING](https://github.com/sadellie/unitto/blob/02791d63a0ad0d9866322889ae980a923e53fd82/CONTRIBUTING.md#L1-L10) |
| Material Files | 延期 | 本地文件 oracle 可行，但 build 启用 CMake/NDK，运行权限与文件系统 surface 很宽；当前没有胜过 Catima/Markor 的收益。[app build](https://github.com/zhanghai/MaterialFiles/blob/fc1250038496ebf4d4c139f62d16f0071f2c995a/app/build.gradle#L1-L90) |
| Wikipedia / repo fixtures | 排除 | 已被本项目大量 calibration/formal 工作消费，不再是独立 unseen host；本轮按任务边界不重新评估。 |

## 正式冻结前 auditor-side preflight

以下全部通过后，才允许创建 Qualification Manifest；失败就降级到下一候选，不在
formal population 中边跑边修。

1. **隔离与 provenance**
   - 由 human/auditor 在 verifier clean context 之外选择 host；冻结 origin、完整 commit、
     license、submodule/依赖状态与 source archive checksum。
   - 审计 verifier 可见输入，确认没有本轮聊天、preflight log、具体 defect/control
     locator、hidden mapping、expected evidence 或 oracle threshold。
   - OpenCalc 只做接缝 calibration；禁止对最终 holdout 做 agent-assisted 调参。

2. **无密钥 clean build**
   - fresh clone、clean Gradle user home；记录 OS、JDK、Gradle、AGP、Android SDK/
     build-tools/NDK 版本和精确命令。
   - 在未注入 signing/API secrets 的环境构建指定 debug variant；保存 dependency
     resolution、build duration、APK path 与 SHA-256。
   - 再用 `--offline` 重建或明确记录不能离线的依赖；检查 merged manifest，而不是只
     看 source manifest。
   - Catima 特别比较 Java 21 与官方 Java 25 路径，并选择唯一冻结工具链。

3. **APK 与 API 35 smoke**
   - `aapt dump badging`/APK analyzer 核对 package、launcher、min/target SDK；确认
     debug signing、application ID suffix 和本地/安装后 APK hash lineage。
   - 在 cold-boot API 35 AVD 上 install/launch；固定 locale、timezone、font scale、
     animation、orientation、网络状态和所有 permission decisions。
   - 清空 app data 后以同一方法 seed 三次，记录 seed-to-visible 时间、layout、截图、
     logcat 与持久化状态；3/3 不一致即淘汰。

4. **pair 与 oracle qualification（auditor-only）**
   - 在写补丁前冻结 trigger、前置状态、expected evidence、abort boundary、oracle 和
     local claim boundary。
   - defect/control 必须作用于相同文件/相同构建面并保持可观察 happy path 等价；
     control 不能只是“未修改 upstream”。
   - 独立 oracle 不调用 production adjudication 路径；baseline/control 3/3 通过、
     defect 3/3 复现，且 clean reset 后顺序交换不改变结果。
   - 分别生成 ChangeTarget 与 ProjectTarget verifier packet，泄漏扫描通过后才释放；
     mapping 只在 Risk Hypothesis freeze 和 Attack Plan admission 后由 auditor 应用。

5. **durable evidence**
   - 保存 exact commands、versions、build durations、APK/package/device identity、
     checksums、layout/screenshots/logs 和 artifact inventory。
   - formal 结束并允许 release 后写入 `docs/runs/<date>-<slug>/`，随实现一起 commit；
     在此之前 private auditor artifact 不得被描述成 repo-durable evidence。

## 决策规则

- Catima 的无密钥 `fossDebug` build、API 35 deny-permission offline Journey 和三次 seed
  稳定性全部通过：冻结 Catima。
- Catima 任一项失败：冻结 Markor 前先证明无需人工 SAF 操作的固定本地文档路径。
- Markor 失败：评估 Birday 的固定时区/日期与 process-recreation slice。
- Gallery 只在前三项均失败且 MediaStore seed 3/3 稳定时启用。
- OpenCalc 永不升级为本轮 formal holdout；它的职责是让执行接缝先失败、先修复、再
  将全新 host 交给 clean-context Verification Agent。
