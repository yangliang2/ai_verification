# Android 验证能力 Gap Register

更新时间：2026-08-04
依据：[Android 错误范式与当前覆盖研究](./2026-07-19-android-error-pattern-coverage.md)、
[#80 fresh M3.1 trust gate](../runs/2026-07-21-issue-80-m3-fresh/README.md)、
[M4 aggregate](../runs/2026-07-18-m4-aggregate/README.md) 和 M5 child run records。

## 目的与状态语义

本登记册记录“已形成可审计的最小能力切片”，不是 Android 通用能力清单。Gap
只有在具备稳定 fixture、机器可检查 oracle、匹配 baseline/candidate Journey、
独立验证和 durable evidence 后，才标记为 `covered (bounded)`。

`covered (bounded)` 只适用于链接的 host/fixture、设备、配置、Journey 和 oracle；
它不等于 benchmark-wide detection、Goldset、device-fleet、production 或 upstream
acceptance。

## M5 Gap 状态

| ID | Gap | 当前状态与证据 | 有界观察 | 仍未覆盖 |
|---|---|---|---|---|
| G-01 | 网络离线、超时、重试、缓存一致性 | covered (bounded)：[#69](https://github.com/yangliang2/ai_verification/issues/69)，[run](../runs/2026-07-19-issue-69-network-reliability/README.md) | baseline 完成 online/offline/cache/timeout/retry/order/recovery；candidate 检出 `retry_storm`、`stale_response_overwrite` | 真实 Wikipedia networking、任意 timing、production network |
| G-02 | 运行时权限拒绝、永久拒绝、撤销 | covered (bounded)：[#70](https://github.com/yangliang2/ai_verification/issues/70)，[run](../runs/2026-07-19-issue-70-runtime-permission/README.md) | baseline 在 denial/permanent denial/Settings revocation 下 graceful fallback；candidate crash/state failure | 其他 permission group、device/API matrix、安全认证 |
| G-03 | 生命周期、后台、process death、backup/restore | covered (bounded)：[#71](https://github.com/yangliang2/ai_verification/issues/71)，[run](../runs/2026-07-19-issue-71-lifecycle-backup-recovery/README.md) | baseline correct restoration；stale-migration candidate rejected | cloud transport、OEM/API matrix、一般备份正确性 |
| G-04 | locale、RTL、orientation、form factor | covered (bounded)：[#72](https://github.com/yangliang2/ai_verification/issues/72)，[run](../runs/2026-07-20-issue-72-compatibility-matrix/README.md) | 4/4 API-35 baseline cells supported；forced-LTR candidate 在 3 个 Arabic cells rejected | 其他 API、foldable posture、font scale、night mode、OEM/physical device |
| G-05 | accessibility semantics、order、touch target、contrast | covered (bounded)：[#73](https://github.com/yangliang2/ai_verification/issues/73)，[run](../runs/2026-07-20-issue-73-accessibility/README.md) | 3/3 baseline checkpoints supported；missing accessible name candidate rejected | WCAG、完整 ATF/TalkBack/辅助技术、physical/OEM fleet |
| G-06 | cold start、frozen frame、resource pressure | covered (bounded)：[#74](https://github.com/yangliang2/ai_verification/issues/74)，[run](../runs/2026-07-20-issue-74-performance-intent/README.md) | baseline thresholds supported；frozen-frame candidate rejected；storage/battery receipts retained | fleet performance、energy attribution、长期 pressure/thermal |
| G-07 | nested Intent、exported boundary、token mutability | covered (bounded)：[#74](https://github.com/yangliang2/ai_verification/issues/74)，[run](../runs/2026-07-20-issue-74-performance-intent/README.md) | unsafe nested-Intent candidate rejected；component boundary 与 one-shot token checked | 一般 Android security、渗透测试、认证结论 |
| G-08 | deterministic concurrency、cancellation、lifecycle races | covered (bounded)：[#78](https://github.com/yangliang2/ai_verification/issues/78)，[run](../runs/2026-07-21-issue-78-deterministic-concurrency/README.md) | baseline ordering/cancellation supported；stale/destroy candidates rejected | stress/fuzz、真实网络并发、一般并发正确性 |

## M5 收口与 M6 结果

- #68 的 gap milestone 已关闭；G-01～G-08 均有各自的 bounded fixture/run
  record，但不能合并成 Android 通用检测率。
- #80 是当前执行信任基线：30/30 accountable、15/15 controls passed、
  15/15 expected defects caught、0 retries、30/30 provenance。
- M4 retained facts：T426553、T426989 `locally_supported`；T409797
  `non_accountable`；T337177 excluded。M4 早于后来有效的 #80 gate，#59 以
  retrospective chronology exception 关闭。
- [当前能力与声明矩阵](../current-capability-claim-matrix.md) 是声明边界入口。

M6 已通过 PR #97 和 [aggregate](../runs/2026-08-03-issue-88-aggregate/README.md)
完成：六个 frozen packages、36/36 accountable lanes、0 retries、6/6 adjudication
agreement。historical 18 lanes 与 prospective 18 lanes 的 denominator 保持分离；
P-01/P-02 为 `locally_supported`，P-03 因冻结 fixture/oracle contradiction 保持
`inconclusive`，不改写、不替换、不重跑。

M6 唯一 M7 route 是 `remediate_fixture_execution_oracle_adjudication_gaps`。
它是 forward-only admission boundary：未来 formal discovery experiment 的
hypothesis、fixture、expected evidence、oracle 或 claim boundary 缺失/矛盾时，
必须在任何外部副作用前 fail closed；这条路线不构成 M7 scale pass。

M6 parent #82 与 cohort freeze #84 已关闭。M7 parent 为 #98；#99 收口本 source of
truth，#100 已提供 Discovery Campaign 契约，接下来是
`#99 → (#101 与 #102) → #103 → #104`。任何新 capability gap 必须由后续
discovery/qualification 的具体 fixture、execution、oracle 和 evidence 触发。

## 持续推进规则

1. 新能力先有稳定 fixture 和机器 oracle；无法稳定复现即
   `non_accountable`，不得反向制造失败。
2. 每次 formal invocation 继承 #80 的 append-only、attempt-complete、
   no-retry-after-accountable 和 fail-closed 纪律。
3. 每个 non-trivial case 必须有独立 issue、committed run record、Effective
   Execution Identity、artifact inventory、checksums 和 known gaps。
4. 未来 formal discovery admission 继承 M6 route：hypothesis、fixture、expected
   evidence、oracle、claim boundary 任一缺失或矛盾，先 fail closed。
5. 未经独立 ground truth 与预注册统计契约，不声明 benchmark-wide rates。
6. 未经单独授权，不进行 upstream task claim/comment 或 pull request。
