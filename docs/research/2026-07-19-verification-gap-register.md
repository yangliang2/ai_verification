# Android 验证能力 Gap Register

更新时间：2026-07-19  
依据：[Android 错误范式与当前覆盖研究](./2026-07-19-android-error-pattern-coverage.md)、M3.1 v20 audit、M4 aggregate。

## 目的

本登记册把“已知但尚未形成可审计能力”的差距变成后续任务输入。Gap 只有在具备稳定 fixture、机器可检查 oracle、匹配的 baseline/candidate Journey、独立验证和持久化证据后，才可标记为消解；静态代码检查、单次手工观察或构建成功不等于覆盖。

## 优先级与状态

| ID | Gap | 风险面 | 当前状态 | 消解完成条件 | 优先级 |
|---|---|---|---|---|---|
| G-01 | 网络离线、超时、重试、缓存一致性 | 空白页、旧响应覆盖新响应、重试风暴 | 缺失行为审计 | 固定 fixture + offline/timeout/retry/restore Journey + response-order oracle | P0 |
| G-02 | 运行时权限拒绝、永久拒绝、撤销 | `SecurityException`、无法降级 | 仅有 adb 原语 | denial/permanent-denial/revocation 三态 Journey + graceful-degradation oracle | P0 |
| G-03 | 进程/后台/备份恢复扩展 | 状态丢失、恢复后不一致 | 有窄生命周期覆盖 | background kill + Auto Backup/restore + migration oracle | P1 |
| G-04 | 配置与设备矩阵 | RTL、locale、横竖屏、平板/折叠差异 | 仅有部分旋转/夜间覆盖 | API × locale/RTL × form factor 矩阵 + layout/semantic oracle | P1 |
| G-05 | 可访问性 | TalkBack 顺序、contentDescription、触控目标、对比度 | 缺失 | Accessibility Test Framework + 语义树/对比度/触控目标 oracle | P1 |
| G-06 | 性能与资源 | 冷启动、jank、冻结帧、耗电、低空间 | 缺失 | startup/gfxinfo/Perfetto/battery/storage fixtures + threshold oracle | P1 |
| G-07 | Intent 与组件安全 | untrusted extras、redirection、exported 边界 | 仅覆盖 URI 语义 | malicious input + exported/PendingIntent oracle + no-redirection assertion | P1 |
| G-08 | 并发/取消/生命周期竞态 | 乱序响应、销毁后更新、死锁 | 仅有窄 coroutine/ANR 覆盖 | deterministic scheduler/test fixture + cancellation/order oracle | P2 |

## 推进规则

1. 每个 Gap 先建立最小可重复 fixture，再写 oracle；无法稳定复现的候选进入 `non_accountable`，不能反向制造失败。
2. 每个 Gap 使用一个独立 issue 和一个 durable run record；完成后将本表状态改为 `covered`，并链接验证命令、结果和 artifacts。
3. 新能力必须保持 M3.1 的 provenance、baseline false-positive、retry/quarantine 和 fail-closed 纪律。
4. M5 先处理 P0，再处理 P1；在 G-01/G-02 尚未形成 accountable lane 前，不宣称 Android 通用检测能力。

## 当前基线

- 已覆盖基线：M3.1 v20，30/30 accountable、baseline false positives 0、defect consistency 15/15、provenance 30/30。
- M4：T426553、T426989 为 `locally_supported`；T409797 为 `non_accountable`；T337177 被排除。
- 本登记册不是 Goldset，不计算 detection rate、false-positive rate 或 upstream acceptance rate。
