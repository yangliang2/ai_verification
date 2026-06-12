"""验证计划生成器单测。

覆盖路径：
- (a) 首次合法 JSON → 成功解析并校验
- (b) 首次畸形、重试合法 → 成功且 provider 被调用 2 次
- (c) 两次均畸形 → 抛 PlanGenerationError
- markdown 代码块包裹剥离
- schema 拒绝（缺必填字段）
"""

from __future__ import annotations

import json

import pytest

from aiverify.providers import MockProvider
from aiverify.agent.planner import (
    PlanGenerationError,
    PlanGenerator,
    ScenarioCluster,
    SpecBlindSpot,
    VerificationPlan,
)


# ---------------------------------------------------------------------------
# 测试夹具 / 工厂函数
# ---------------------------------------------------------------------------

def _valid_plan_dict() -> dict:
    """返回一个符合 plan_schema.json 的最小合法计划字典。"""
    return {
        "change_summary": "新增了登录按钮防抖逻辑",
        "scenario_clusters": [
            {
                "id": "SC-001",
                "target_screens": ["LoginScreen"],
                "user_actions": ["输入账号密码", "连续快速点击登录按钮"],
                "system_events": [
                    {"step_index": 1, "event": "network_off"}
                ],
                "expected_behavior": "仅触发一次登录请求，不重复提交",
                "related_defect_patterns": ["DP-042"],
            }
        ],
        "spec_blind_spots": [
            {
                "description": "规格未描述弱网下的重试策略",
                "rationale": "diff 中无超时处理逻辑",
            }
        ],
    }


def _valid_plan_json() -> str:
    return json.dumps(_valid_plan_dict(), ensure_ascii=False)


SAMPLE_DIFF = "--- a/Login.kt\n+++ b/Login.kt\n@@ -10,6 +10,8 @@\n+    debounce(300)"
SAMPLE_SPEC = "用户点击登录后系统应仅发送一次认证请求。"
SAMPLE_TAXONOMY: list[dict] = [
    {
        "id": "DP-042",
        "name": "重复提交",
        "description": "用户操作触发多次相同请求",
        "trigger_scenario": "快速连点按钮",
    }
]


# ---------------------------------------------------------------------------
# 路径 (a)：首次返回合法 JSON → 成功解析校验
# ---------------------------------------------------------------------------

def test_generate_succeeds_on_first_valid_response():
    """首次 LLM 响应为合法 JSON 时，generate 应成功返回 VerificationPlan。"""
    provider = MockProvider([_valid_plan_json()])
    gen = PlanGenerator(provider)

    plan = gen.generate(SAMPLE_DIFF, SAMPLE_SPEC, SAMPLE_TAXONOMY)

    assert isinstance(plan, VerificationPlan)
    assert plan.change_summary == "新增了登录按钮防抖逻辑"
    assert len(plan.scenario_clusters) == 1
    cluster = plan.scenario_clusters[0]
    assert isinstance(cluster, ScenarioCluster)
    assert cluster.id == "SC-001"
    assert cluster.target_screens == ["LoginScreen"]
    assert cluster.system_events[0].event == "network_off"
    assert cluster.system_events[0].step_index == 1
    assert cluster.related_defect_patterns == ["DP-042"]
    assert len(plan.spec_blind_spots) == 1
    blind = plan.spec_blind_spots[0]
    assert isinstance(blind, SpecBlindSpot)
    assert "弱网" in blind.description
    # provider 只被调用一次
    assert len(provider.calls) == 1


# ---------------------------------------------------------------------------
# 路径 (b)：首次畸形、重试合法 → 成功且 provider 被调用 2 次
# ---------------------------------------------------------------------------

def test_generate_retries_on_first_invalid_response():
    """首次响应畸形、第二次合法时，generate 应成功并调用 provider 共 2 次。"""
    provider = MockProvider(["这不是JSON{{{", _valid_plan_json()])
    gen = PlanGenerator(provider)

    plan = gen.generate(SAMPLE_DIFF, SAMPLE_SPEC, SAMPLE_TAXONOMY)

    assert isinstance(plan, VerificationPlan)
    assert len(provider.calls) == 2
    # 重试 prompt 应包含上一次输出与错误信息提示
    retry_prompt = provider.calls[1]["prompt"]
    assert "重试提示" in retry_prompt or "上一次输出" in retry_prompt


# ---------------------------------------------------------------------------
# 路径 (c)：两次均畸形 → 抛 PlanGenerationError
# ---------------------------------------------------------------------------

def test_generate_raises_on_two_invalid_responses():
    """连续两次 LLM 响应均无法解析时，应抛出 PlanGenerationError。"""
    provider = MockProvider(["not-json-1", "not-json-2"])
    gen = PlanGenerator(provider)

    with pytest.raises(PlanGenerationError) as exc_info:
        gen.generate(SAMPLE_DIFF, SAMPLE_SPEC, SAMPLE_TAXONOMY)

    assert len(provider.calls) == 2
    assert "两次" in str(exc_info.value) or "第一次" in str(exc_info.value)


# ---------------------------------------------------------------------------
# markdown 代码块包裹剥离
# ---------------------------------------------------------------------------

def test_generate_strips_markdown_fence():
    """LLM 输出用 ```json ... ``` 包裹时，应正确剥离并解析。"""
    wrapped = f"```json\n{_valid_plan_json()}\n```"
    provider = MockProvider([wrapped])
    gen = PlanGenerator(provider)

    plan = gen.generate(SAMPLE_DIFF, SAMPLE_SPEC, SAMPLE_TAXONOMY)

    assert isinstance(plan, VerificationPlan)
    assert len(provider.calls) == 1


def test_generate_strips_plain_markdown_fence():
    """LLM 输出用 ``` ... ``` 包裹（不含 json 标记）时，应正确剥离并解析。"""
    wrapped = f"```\n{_valid_plan_json()}\n```"
    provider = MockProvider([wrapped])
    gen = PlanGenerator(provider)

    plan = gen.generate(SAMPLE_DIFF, SAMPLE_SPEC, SAMPLE_TAXONOMY)

    assert isinstance(plan, VerificationPlan)


# ---------------------------------------------------------------------------
# schema 拒绝：缺必填字段
# ---------------------------------------------------------------------------

def test_generate_rejects_missing_required_field():
    """缺少 change_summary 的 JSON 应触发 schema 校验失败，最终抛 PlanGenerationError。"""
    bad = _valid_plan_dict()
    del bad["change_summary"]
    bad_json = json.dumps(bad, ensure_ascii=False)
    # 两次都返回缺字段的 JSON
    provider = MockProvider([bad_json, bad_json])
    gen = PlanGenerator(provider)

    with pytest.raises(PlanGenerationError):
        gen.generate(SAMPLE_DIFF, SAMPLE_SPEC, SAMPLE_TAXONOMY)


def test_generate_rejects_invalid_system_event_enum():
    """system_events 中使用了非法 event 枚举值时，应触发 schema 校验失败。"""
    bad = _valid_plan_dict()
    bad["scenario_clusters"][0]["system_events"][0]["event"] = "explode"
    bad_json = json.dumps(bad, ensure_ascii=False)
    provider = MockProvider([bad_json, bad_json])
    gen = PlanGenerator(provider)

    with pytest.raises(PlanGenerationError):
        gen.generate(SAMPLE_DIFF, SAMPLE_SPEC, SAMPLE_TAXONOMY)


# ---------------------------------------------------------------------------
# 空 taxonomy 与空 system_events
# ---------------------------------------------------------------------------

def test_generate_with_empty_taxonomy():
    """空 taxonomy_patterns 列表时，generate 应正常工作。"""
    plan_dict = _valid_plan_dict()
    plan_dict["scenario_clusters"][0]["system_events"] = []
    plan_dict["scenario_clusters"][0]["related_defect_patterns"] = []
    provider = MockProvider([json.dumps(plan_dict, ensure_ascii=False)])
    gen = PlanGenerator(provider)

    plan = gen.generate(SAMPLE_DIFF, SAMPLE_SPEC, [])

    assert isinstance(plan, VerificationPlan)
    assert plan.scenario_clusters[0].system_events == []
    assert plan.scenario_clusters[0].related_defect_patterns == []
