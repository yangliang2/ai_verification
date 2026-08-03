# HANDOFF

更新时间：2026-08-02

项目当前从“补齐 Android capability slice”转向“M6 blinded AI-change
verification qualification”。接手者应先读
[`docs/current-capability-claim-matrix.md`](docs/current-capability-claim-matrix.md)，
不要从旧 issue 编号或聊天记录推断当前声明。

## 当前 tracker 状态

- #58 已按 #80 fresh M3.1 gate 关闭：冻结 30-lane population 达到 30/30
  first-attempt/eventual accountability、15/15 controls passed、15/15 expected
  defect catches、0 retries、30/30 complete provenance。
- #59 已按 retrospective pilot 关闭：M4 保持两个 accountable
  `locally_supported`、一个 `non_accountable` 的原始结果；由于执行早于后来有效的
  #80 gate，chronology violation 永久保留。
- M5 parent #68 与 G-01～G-08 children 已关闭；结论都是 fixture-bound，不是
  Android 通用覆盖。
- M6 parent 是 #82。执行依赖：

```text
#83 → #84 → #85 → (#86 与 #87) → #88
```

- #83 发布当前 claim matrix 并同步 living docs。
- #84 是 human-required：冻结三个 historical exact-revision pairs、三个
  prospective tasks 与 replacement pool。它完成前不得启动 formal M6 lane。
- #85 建立统一 Qualification Case Package 与 evidence-derived aggregate。
- #86 运行 historical track；#87 运行 blinded prospective track。两者可在
  #85 后独立推进，但 denominator 不能合并。
- #88 聚合、独立审计并形成 M7 go/no-go。

## 当前证据基线

### 公共执行与信任合同

- Run Spec → Codex CLI Verification Agent Backend → Android CLI/adb → Journey
  Segment Boundary → oracle → verdict/run record 已有
  [MVP](docs/runs/2026-06-15-afk-verification/README.md) 和
  [end-to-end](docs/runs/2026-07-05-end-to-end-cli-codex/README.md) 证据。
- #60：
  [ExecutionRecord/system-event](docs/runs/2026-07-17-issue-60-execution-record-system-event/README.md)
  在外部副作用前建立 attempt identity，所有 handled terminal path 原子终结；
  event exception、timeout、non-zero 与 postcondition mismatch fail closed。
- #61：
  [Effective Execution Identity](docs/runs/2026-07-17-issue-61-effective-execution-identity/README.md)
  checksum-bind consumed Run Spec、host commit/worktree、完整 APK/安装态、device、
  tool 与每个 agent role 的 requested/effective model。
- #67：
  [portable host locator](docs/runs/2026-07-18-issue-67-portable-host-locator/README.md)
  绑定 expected origin/commit 与 resolved local path；identity mismatch fail closed。
- #80：
  [fresh M3.1 run](docs/runs/2026-07-21-issue-80-m3-fresh/README.md) 是当前
  attempt-complete gate。五个 package checksum inventory 为 743/743 entries，
  root inventory 为 769/769 entries；唯一独立 Verification Agent 给出
  `locally_supported`。

#80 只支持 Wikipedia、Codex CLI、单台 API 35 emulator、冻结五 seed/30 lane
人口。它不是跨 host/backend/device-fleet 的 reliability 结论。

### 历史 benchmark populations

- M1：五个 Goldset-derived seed 的有界端到端证据。
- M2-beta：10 included injected-defect seeds caught、10 matched controls passed；
  两个 L3 repeatability-only packages 独立记账。
- 原 M3：27/30 eventually accountable，milestone `FAILED`，保持不可变。
- M3 v2：29/30 eventually accountable；是独立人口，且没有完整的当前 identity
  contract。
- #62 M3.1 v3：6/30 eventually accountable，`FAILED`，保留 stale
  identity/environment failure。
- #80 fresh M3.1：30/30 accountable，当前 trust gate `PASSED`；不得把不同
  30-lane populations 合并或用后来结果覆盖早期失败。

### M4 chronology

[M4 aggregate](docs/runs/2026-07-18-m4-aggregate/README.md) 保留：

- T426553：accountable，`locally_supported`；
- T426989：accountable，`locally_supported`；
- T409797：`non_accountable`；
- T337177：pre-execution excluded/replaced。

M4 execution 发生在后来有效的 #80 gate 之前。因此 #59 是 retrospective
closure，不证明原 entry-gate 顺序合规；三个 admitted cases 也不能产生
detection/false-positive rate、Goldset 或 upstream acceptance 声明。

### M5 bounded capability slices

| Gap | 证据 | 有界观察 |
|---|---|---|
| G-01 network | [#69](docs/runs/2026-07-19-issue-69-network-reliability/README.md) | baseline pass；`retry_storm`、`stale_response_overwrite` candidate rejected |
| G-02 permission | [#70](docs/runs/2026-07-19-issue-70-runtime-permission/README.md) | denial/permanent denial/revocation baseline graceful；candidate rejected |
| G-03 lifecycle/backup | [#71](docs/runs/2026-07-19-issue-71-lifecycle-backup-recovery/README.md) | baseline restoration supported；stale migration rejected |
| G-04 compatibility | [#72](docs/runs/2026-07-20-issue-72-compatibility-matrix/README.md) | 4/4 baseline cells；forced-LTR rejected in three Arabic cells |
| G-05 accessibility | [#73](docs/runs/2026-07-20-issue-73-accessibility/README.md) | 3/3 baseline checkpoints；missing-name candidate rejected |
| G-06 performance | [#74](docs/runs/2026-07-20-issue-74-performance-intent/README.md) | bounded thresholds supported；frozen-frame candidate rejected |
| G-07 Intent safety | [#74](docs/runs/2026-07-20-issue-74-performance-intent/README.md) | unsafe nested Intent rejected；boundary/token receipts retained |
| G-08 concurrency | [#78](docs/runs/2026-07-21-issue-78-deterministic-concurrency/README.md) | baseline supported；stale/destroy candidates rejected |

完整边界见
[`docs/research/2026-07-19-verification-gap-register.md`](docs/research/2026-07-19-verification-gap-register.md)。

## M6 必须保持的测量合同

1. Cohort 在 outcome 前冻结：三个 exact historical pairs、三个 prospective
   changes，以及 pre-execution replacement pool。
2. Historical admission 必须基于 exact revision 的 matched pre-fix fail / fixed
   pass；reverse-applied fix 只能标为 controlled injection，不能标为 Goldset。
3. Prospective task input 先冻结，Development Agent candidate 再冻结，然后才由
   分离会话中的 Verification Agent 盲测。
4. 一个 case 只有一个 primary behavior contract；supplemental tests 不增加
   counted case。
5. 每 case 计划三个 baseline 和三个 candidate observations，共 36 formal
   lanes；retry policy 必须预注册，accountable 后不重试。
6. 每个 formal invocation 使用公共 Run Spec seam，继承 #80 的 fail-closed、
   append-only、attempt-complete、identity-bound 纪律。
7. Historical 与 prospective 结果使用不同 denominator；本阶段不计算统计
   detection/false-positive rate。
8. Verification Agent conclusion 冻结后才允许 independent adjudication；
   adjudication 不能反向修改 verifier 输出。
9. Local Conclusion 只能是 `locally_supported`、`locally_rejected` 或
   `non_accountable`，永远不等于 upstream acceptance。
10. 未获单独授权，不进行 upstream task claim/comment、upstream PR 或任何会
    影响上游项目状态的动作。

## 运行与验证入口

安装本项目测试依赖：

```bash
uv venv .venv
uv pip install --python .venv/bin/python pytest pyyaml jsonschema
PYTHONPATH=src .venv/bin/python -m pytest
```

Run Spec 推荐使用 portable host locator：

```yaml
host_project:
  root: ${WIKIPEDIA_SOURCE}
  origin: https://github.com/wikimedia/apps-android-wikipedia
  commit: <frozen-commit>
```

运行示例：

```bash
WIKIPEDIA_SOURCE=/absolute/path/to/host \
  PYTHONPATH=src .venv/bin/python -m aiverify.runner case.yaml \
  --device emulator-5554 \
  --artifact-dir docs/runs/<date>-<slug>/artifacts
```

不要从全局工具版本或当前 host checkout 推断运行身份。每次 formal run 的
source、worktree、APK、installed package、device、tool、backend/model 都必须
进入 Effective Execution Identity。

## Durable evidence 纪律

每个非平凡完成 issue 都应提交 `docs/runs/<date>-<slug>/`，至少记录：

- source revision under test 与 final evidence commit；
- exact commands、exit status、pass/fail counts、duration 和相关 tool versions；
- files/modules/tests 如何满足 acceptance criteria；
- emulator/device/manual steps；
- artifact inventory 和重要 checksum；
- skipped checks、known gaps 与 claim boundary。

GitHub 完成评论必须链接 committed run record，不能只引用 `/tmp` 或聊天历史。
run record 与其 artifacts 在 commit 前都不算 durable evidence。

## 接手时的正确下一步

1. 确认 #83 的 claim matrix PR 已合入且 #83 已关闭。
2. 处理 #84 的 human-required cohort freeze；未冻结前只允许准备资料，不允许
   formal case execution。
3. #84 完成后实现 #85 common Qualification Case Package。
4. #85 通过后分别推进 #86、#87；最后由 #88 聚合并独立审计。

任何文档或报告都必须同时说明支持结论和非声明范围。若实现、run record 与
tracker 冲突，以 committed raw evidence 为准，先修 source-of-truth，再继续下游
formal population。
