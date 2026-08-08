# HANDOFF

更新时间：2026-08-08

M9 与 M9-R 均已以不可变的 `Not Supported` 失败证据收口。#137 的六条 lane 均在
install 前 non-accountable；fresh recovery packet #154 的唯一调用更早在
`PORTFOLIO_FROZEN` fail closed，未到 mapping、device、model 或 runtime。#157
机械归约得到 0/6 accountable、0/6 evidence-valid、0/3 defect support、0/3
control rejection、0/6 review，零 retry/replacement/rerun。接手者应先读
[`docs/current-capability-claim-matrix.md`](docs/current-capability-claim-matrix.md)，
再读 [#137 formal run](docs/runs/2026-08-06-issue-137-formal-execution/README.md)
与 [#157 R5 run](docs/runs/2026-08-08-issue-157-m9-r5-reconciliation/README.md)，
不要从旧 issue 编号或聊天记录推断当前声明。M8 与首次 M9 人口都保持不可变。

## 当前 tracker 状态

- #58 已按 #80 fresh M3.1 gate 关闭：冻结 30-lane population 达到 30/30
  first-attempt/eventual accountability、15/15 controls passed、15/15 expected
  defect catches、0 retries、30/30 complete provenance。
- #59 已按 retrospective pilot 关闭：M4 保持两个 accountable
  `locally_supported`、一个 `non_accountable` 的原始结果；由于执行早于后来有效的
  #80 gate，chronology violation 永久保留。
- M5 parent #68 与 G-01～G-08 children 已关闭；结论都是 fixture-bound，不是
  Android 通用覆盖。
- M6 已通过 PR #97 与 [#88 aggregate](docs/runs/2026-08-03-issue-88-aggregate/README.md)
  完成；#82 parent 与 #84 cohort freeze 已在 source-of-truth 收口后关闭。
  六个 package、36 lanes、0 retries、6/6 adjudication agreement 是不可变的本地事实。
- M6 执行依赖（已完成）为：

```text
#83 → #84 → #85 → (#86 与 #87) → #88
```

- #83 发布 claim matrix，#84 冻结 cohort，#85 建立 common Qualification Case
  Package，#86/#87 分开运行两个 track，#88 聚合并独立审计。
- P-01/P-02 为 `locally_supported`，P-03 因冻结的 fixture/oracle contradiction
  保持 `inconclusive`；historical/prospective denominator 不合并。
- M7 唯一 forward route 是
  `remediate_fixture_execution_oracle_adjudication_gaps`。它只约束未来 admission，
  不替换、修复或重跑冻结的 P-03。

- M7 parent 是 #98；其 discovery/admission/runtime slices 已完成，下面的依赖是
  历史执行顺序，不是当前待办：

```text
#99 ────────────────────────────────┐
                                    ├→ #104 blinded qualification
#100 → (#101 || #102) → #103 ───────┘
```

- #99 收口 living source of truth 与 forward remediation boundary；#100 已合入，
  提供 Discovery Campaign、Project/Change Target、Quality Context Graph、Risk
  Hypothesis、Attack Plan、Finding、Residual Risk 及 fail-closed admission 契约。
- #101/#102 可在 #100 后并行；#103 依赖两者；#104 依赖 #99 与 #103，冻结 4 cells ×
  3 repetitions = 12 lanes 的 blinded dual-entry qualification。

- M8 parent [#117](https://github.com/yangliang2/ai_verification/issues/117) 与 children
  #118–#122 已关闭，PR #123–#127 已合入。最终 [PR #127
  `957f108`](https://github.com/yangliang2/ai_verification/commit/957f108d88afd74a8787b42be568ab558c5fb9b1)
  消费 exact #121 manifest，12/12 lanes 均在 execution-identity capture 阶段成为
  `non-accountable`，因此 aggregate 为 `0/12 accountable`、`inconclusive`。
- M9 parent [#128](https://github.com/yangliang2/ai_verification/issues/128) 已在 R5
  终局证据合入后收口。#129–#137 的原实现、冻结和执行证据保持不变；#137 的真实
  aggregate 仍是 `Not Supported`、0/6 accountable，没有 install/launch/agent/
  runtime evidence。
- M9-R #148–#157 已完成。R2 historical canary 的 2/2 accountable 结果只证明
  forward readiness；R3 fresh packet 的 R4 正式调用在 Attack Plan contract gate
  终止。R5 是 pre-runtime `Not Supported`，不是 runtime FAIL。#158 只做 future-only
  contract hardening，不重开 parent 或正式 packet。

## M8 immutable result

Durable evidence 是
[`docs/runs/2026-08-05-issue-122-formal-execution/README.md`](docs/runs/2026-08-05-issue-122-formal-execution/README.md)。#122 在 exact #121
manifest 上按既定顺序完成 12 条 lane，每条只有一次 terminal attempt；共同原因是
冻结 Run Spec 的 fixture `host_project` 子目录与 runner 要求的 repository-root
identity 不兼容。没有 APK install、launch、agent invocation、Journey、system event
或 observed state evidence；change/project 分母分别为 0/6 accountable。修复提交
`22af9b2` 未用于重跑或替换，原 static migration receipts 也不构成 Finding。

这组 M8 结果不可重跑、不可改写、不可替换、不可与 M7 合并。任何未来 state-evolution
qualification 都必须新建并冻结 cohort/contract；M8 不进入 M9 denominator。

## M9 source-of-truth contract

正式 M9 只接收无 diff 的完整 `ProjectTarget`、immutable source provenance、scope 和
bounded budget。`ChangeTarget` 只做 regression coverage。批准的 discovery chain 是：

```text
ProjectTarget
→ Context Acquisition
→ Hypothesis Portfolio
→ Attack Plan
→ production-seam admission
→ accountable runtime execution
→ Falsification Review
→ Project Risk Map
```

三 priors 必须在一个 bounded Hypothesis Portfolio 中竞争：synchronous critical-path
temporal propagation、state-evolution compatibility drift、lifetime/ownership drift。
正式 cohort 是 `project-defect × 3` 与 `project-control × 3` 六条 lane；另有一个
incomplete/contradictory context packet，必须在任何 build/device/agent/runtime side
effect 前拒绝并留在 denominator 外。每条 lane one attempt、zero retry、zero replacement。
Hidden mapping 只能在 Context Acquisition、portfolio freeze、Attack Plan admission 和
leakage audit 后释放。

Falsification Review 必须使用 clean context、separate invocation identity，并绕开
production adjudication/oracle implementation path；same-provider operation 可用，但
same-family limitation 必须明示。所有结果都只支持 exact source/build/device/operator/
backend-model/oracle/review/evidence 范围内的 local-only claim。

## ADR assessment

#129 已复核 ADR-0001、0002、0003。当前只新增 domain vocabulary、source-of-truth 和
bounded qualification boundary，没有新增 hard-to-reverse architecture、provider、data
ownership 或 production-operation choice，因此不新增 ADR。若后续实现把 same-family
review limitation 变成不可逆系统政策，应重新评估 ADR 门槛。

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
- #148：
  [M9-R1 recovery baseline](docs/runs/2026-08-07-issue-148-m9-r1-recovery-baseline/README.md)
  在不执行旧 cohort 的前提下复现 package-clear 失败语义，恢复出字节级一致的
  control/defect canary APK，并将 absent/installed/failed/contradictory package
  reset 分开记账。它只证明 R2 readiness。

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

1. 保持 M8 #117–#122、M9 #136/#137、M9-R #152/#154/#157 证据不可变；不得重跑、
   替换、改写、回填或合并 population。
2. #154 packet 已耗尽。任何 consumer、Attack Plan、inventory 或 reducer 修复都不得
   触发第二次 formal command。
3. 当前唯一明确的 forward work 是 #158：在未来 packet 声明 namespace 前完成
   target-specific plan preclaim，并让 pre-runtime terminal rows 双向绑定 inventory、
   区分 “attempt reconciled” 与 “runtime executed”。
4. 若未来需要再次度量 M9，必须另开 PRD、选择全新 cohort/mapping、重新人工冻结并
   获得新的正式执行授权；#158 本身不提供该授权。

任何文档或报告都必须同时说明支持结论和非声明范围。若实现、run record 与
tracker 冲突，以 committed raw evidence 为准，先修 source-of-truth，再继续下游
formal population。
