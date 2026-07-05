# Goldset Seed Spec — Wikipedia config-change baseline Smoke Slice

> Issue: [#8](https://github.com/yangliang2/ai_verification/issues/8) — First Wikipedia config-change Goldset smoke seed.
> Type: **Smoke Slice**（证明验证链可执行，不声称基准检测性能）。
> Run record: [`docs/runs/2026-07-05-wikipedia-config-change-smoke/`](../../../docs/runs/2026-07-05-wikipedia-config-change-smoke/README.md)

## 目标

用最小的端到端运行证明：`run-spec → 段边界注入旋转 → Android CLI 抓 layout → L1/L2 oracle → verdict`
这条链在一个真实 config-change 场景下可执行，且在"应当通过"时正确报 PASS。

这是 baseline（**未注入缺陷**）。它验证的是 harness 的"阴性对照"——当被测行为其实正确时，
验证器不误报。有了可信的 PASS，后续注入等价缺陷得到的 FAIL 才可信。

## 缺陷模式对照

| 维度 | 值 |
|---|---|
| taxonomy 类别 | `config-change` |
| taxonomy 模式 | `config-change-01`（旋转后 UI 状态丢失，未持久化）/ `config-change-05`（Compose 用 remember 而非 rememberSaveable） |
| 症状轴（verdict 枚举） | `state_loss`（注入缺陷时）；baseline 为无缺陷 |
| 真实历史对照 | `candidates.md` C1 (Tusky #45 回复旋转丢正文)、C3 (Thunderbird #10288 旋转后收件人重复) |

## 场景

宿主：`org.wikipedia.dev`（apps-android-wikipedia @ `6ccb8d8`），搜索输入用经典 `SearchView`，
其 EditText 暴露 resource-id `search_src_text`——适合 L2 状态断言。

1. 打开 Search tab → 点 `search_card` → 进入搜索输入。
2. 点 `search_src_text`，输入 sentinel `zzsentinelqx`。
3. **[Journey Segment Boundary]** 注入 `rotate`（竖→横）。
4. 抓旋转前后两份 `android layout` JSON。
5. `judge_l2_from_android_layout` 断言 `search_src_text.text == zzsentinelqx`。

## 期望 verdict

- **L2 = pass** — 旋转后 sentinel 文本保留（Wikipedia 正确恢复查询）。
- **L1 = inconclusive** — 无崩溃/ANR，L1 弃权（符合"L1 无宣告通过权"的设计）。

实测结果与 verdict JSON 见 run record；判定由 `bench/goldset/fixtures/wikipedia-config-change-smoke/`
的 layout fixture 固化为回归测试 `tests/bench/test_goldset_config_change_smoke.py`。

## 已知边界

- 这是**阴性对照**，不证明验证器能"抓到"config-change 缺陷；那属于注入缺陷的下一步。
- Wikipedia 搜索页的结果列表为 Compose，`android layout` 不暴露其 resource-id；本 seed 只断言
  经典 View 的 `search_src_text`，避开 Compose 无 id 的节点。
- 旋转经 `adb settings user_rotation` 注入；截图尺寸（1080x2400 → 2400x1080）作为旋转真实发生的证据。
