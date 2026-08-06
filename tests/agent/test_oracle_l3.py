"""L3Oracle 单测——LLM 语义判定器（MockProvider 驱动）。

覆盖四个路径：
1. 成功路径：MockProvider 返回合法 JSON → 正确解析并通过 schema 校验
2. markdown 包裹：返回 ```json ... ``` 包裹的 JSON → 正确解析
3. 重试路径：第一次返回不合法 JSON，第二次返回合法 JSON → 重试成功
4. 双次失败路径：两次均返回不合法 JSON → 抛出 VerdictValidationError
"""

import json
import uuid

import pytest

from aiverify.providers import MockProvider
from aiverify.agent.oracle import L3Oracle, VerdictValidationError, validate_verdict

# ---------------------------------------------------------------------------
# 辅助：构造合法 verdict JSON 字符串
# ---------------------------------------------------------------------------

def _valid_verdict_json(
    outcome: str = "fail",
    defect_class: str | None = "ui_rendering",
) -> str:
    verdict = {
        "verdict_id": f"L3-{uuid.uuid4().hex[:8]}",
        "level": "L3",
        "outcome": outcome,
        "defect_class_hypothesis": defect_class,
        "trigger_steps": ["打开设置页面", "滚动到底部"],
        "evidence": [
            {
                "type": "llm_reasoning",
                "ref": "截图显示按钮文字溢出边界，超出容器宽度约 12dp",
                "note": "与规格要求的自适应布局不符",
            }
        ],
        "confidence": 0.82,
    }
    return json.dumps(verdict, ensure_ascii=False)


# 不合法 JSON（缺少必填字段 outcome）
_INVALID_VERDICT_JSON = json.dumps(
    {
        "verdict_id": "L3-badtest1",
        "level": "L3",
        # outcome 字段缺失
        "defect_class_hypothesis": None,
        "trigger_steps": [],
        "evidence": [],
        "confidence": 0.5,
    }
)

_TRACE = "步骤1：启动应用；步骤2：横屏旋转；步骤3：观察按钮布局"
_SPEC = "旋转后所有按钮应自适应容器宽度，文字不得溢出。"
_SCREENSHOTS = ["screenshots/step2_landscape.png"]

# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------


def test_l3_success_path():
    """MockProvider 返回合法 JSON → 正常解析，verdict 通过 schema 校验。"""
    provider = MockProvider([_valid_verdict_json("fail", "ui_rendering")])
    oracle = L3Oracle(provider)

    verdict = oracle.judge(
        _TRACE,
        _SPEC,
        _SCREENSHOTS,
        trigger_steps=["横屏旋转"],
    )

    assert verdict["level"] == "L3"
    assert verdict["outcome"] == "fail"
    assert verdict["defect_class_hypothesis"] == "ui_rendering"
    assert verdict["confidence"] == pytest.approx(0.82)

    # provider 只被调用一次
    assert len(provider.calls) == 1

    # prompt 中包含轨迹和规格关键词
    assert _TRACE in provider.calls[0]["prompt"]
    assert _SPEC in provider.calls[0]["prompt"]

    validate_verdict(verdict)


def test_l3_markdown_wrapped_json():
    """LLM 返回 ```json ... ``` 包裹的 JSON → 正确解析。"""
    wrapped = f"```json\n{_valid_verdict_json('pass', None)}\n```"
    provider = MockProvider([wrapped])
    oracle = L3Oracle(provider)

    verdict = oracle.judge(_TRACE, _SPEC)

    assert verdict["outcome"] == "pass"
    validate_verdict(verdict)


def test_l3_markdown_no_lang_tag():
    """LLM 返回 ``` ... ```（无语言标签）包裹的 JSON → 正确解析。"""
    wrapped = f"```\n{_valid_verdict_json('inconclusive', None)}\n```"
    provider = MockProvider([wrapped])
    oracle = L3Oracle(provider)

    verdict = oracle.judge(_TRACE, _SPEC)
    assert verdict["outcome"] == "inconclusive"
    validate_verdict(verdict)


def test_l3_retry_on_first_invalid():
    """第一次返回不合法 JSON，第二次返回合法 JSON → 重试成功，共调用 2 次。"""
    provider = MockProvider([_INVALID_VERDICT_JSON, _valid_verdict_json("fail")])
    oracle = L3Oracle(provider)

    verdict = oracle.judge(_TRACE, _SPEC)

    assert verdict["outcome"] == "fail"
    # provider 被调用了两次（首次失败后重试）
    assert len(provider.calls) == 2

    validate_verdict(verdict)


def test_l3_formal_one_attempt_does_not_retry_invalid_output():
    """The M9 formal lane policy treats malformed output as terminal."""
    provider = MockProvider([_INVALID_VERDICT_JSON, _valid_verdict_json("fail")])
    oracle = L3Oracle(provider)

    with pytest.raises(VerdictValidationError):
        oracle.judge(_TRACE, _SPEC, retry_invalid=False)

    assert len(provider.calls) == 1


def test_l3_raises_after_double_failure():
    """两次均返回不合法 JSON → 抛出 VerdictValidationError。"""
    provider = MockProvider([_INVALID_VERDICT_JSON, _INVALID_VERDICT_JSON])
    oracle = L3Oracle(provider)

    with pytest.raises(VerdictValidationError):
        oracle.judge(_TRACE, _SPEC)

    # provider 被调用了两次
    assert len(provider.calls) == 2


def test_l3_screenshot_refs_in_prompt():
    """截图引用列表应出现在 prompt 中。"""
    provider = MockProvider([_valid_verdict_json()])
    oracle = L3Oracle(provider)

    oracle.judge(_TRACE, _SPEC, ["shot1.png", "shot2.png"])

    prompt = provider.calls[0]["prompt"]
    assert "shot1.png" in prompt
    assert "shot2.png" in prompt


def test_l3_no_screenshots_handled():
    """无截图引用时 prompt 不崩溃，包含占位文本。"""
    provider = MockProvider([_valid_verdict_json()])
    oracle = L3Oracle(provider)

    oracle.judge(_TRACE, _SPEC, [])

    prompt = provider.calls[0]["prompt"]
    assert "无截图引用" in prompt


def test_l3_all_defect_classes_accepted():
    """taxonomy 五类均应通过 schema 校验。"""
    classes = [
        "crash_stability",
        "state_loss",
        "ui_rendering",
        "performance_regression",
        "permission_security",
    ]
    for cls in classes:
        provider = MockProvider([_valid_verdict_json("fail", cls)])
        oracle = L3Oracle(provider)
        verdict = oracle.judge(_TRACE, _SPEC)
        assert verdict["defect_class_hypothesis"] == cls
        validate_verdict(verdict)


def test_l3_provider_exhausted_raises():
    """provider 响应耗尽时 MockProvider 抛 RuntimeError（非 VerdictValidationError）。"""
    provider = MockProvider([])  # 无响应
    oracle = L3Oracle(provider)

    with pytest.raises(RuntimeError, match="预置响应已耗尽"):
        oracle.judge(_TRACE, _SPEC)
