"""L3 LLM 语义判定器——仅在 L1/L2 信号不足时介入。

设计原则
--------
L3 是最昂贵的层，只在前两层弃权（inconclusive）时才应调用。
输入：执行轨迹摘要 + 规格文本 + screenshots 引用列表。
流程：组 prompt → provider.complete → 解析 JSON verdict →
      schema 校验失败重试一次 → 二次失败抛 VerdictValidationError。

真实 provider 接线（API key 配置、模型选择等）见 HANDOFF.md。
"""

from __future__ import annotations

import json
from typing import Any

from aiverify.providers.base import LLMProvider
from aiverify.providers.parsing import extract_json_block
from aiverify.agent.oracle.schema import validate_verdict, VerdictValidationError

# ---------------------------------------------------------------------------
# Prompt 模板
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
你是一名专业的 Android 应用质量验证专家（Oracle L3）。
请根据执行轨迹摘要、功能规格和截图引用，判断应用行为是否存在缺陷。

你必须以合法的 JSON 对象作答，严格符合以下 schema 要求：
- verdict_id: 字符串，格式 "L3-<8位hex>"
- level: 固定为 "L3"
- outcome: "fail" | "pass" | "inconclusive"
- defect_class_hypothesis: "crash_stability"|"state_loss"|"ui_rendering"|"performance_regression"|"permission_security"|null
- trigger_steps: 字符串列表（从轨迹中提取的关键步骤）
- evidence: 列表，每项含 type("llm_reasoning")、ref(推理依据)、note(说明)
- confidence: 0~1 之间的浮点数

不要输出 JSON 之外的任何内容。如果必须解释，请放入 evidence[].note 中。
"""

_USER_TEMPLATE = """\
## 执行轨迹摘要
{trace_summary}

## 功能规格
{spec_text}

## 截图引用
{screenshots_section}

请输出符合要求的 verdict JSON。
"""


def _build_prompt(
    trace_summary: str,
    spec_text: str,
    screenshot_refs: list[str],
) -> str:
    """组装发送给 LLM 的用户侧 prompt。"""
    if screenshot_refs:
        screenshots_section = "\n".join(
            f"- {ref}" for ref in screenshot_refs
        )
    else:
        screenshots_section = "（无截图引用）"

    return _USER_TEMPLATE.format(
        trace_summary=trace_summary,
        spec_text=spec_text,
        screenshots_section=screenshots_section,
    )



class L3Oracle:
    """LLM 语义判定器（L3 层）。

    仅在 L1/L2 均返回 inconclusive 时才应调用（调用成本最高）。
    内部对 LLM 输出做 schema 校验，失败后自动重试一次；
    二次失败抛 VerdictValidationError，由调用方决定如何处理。
    """

    def __init__(self, provider: LLMProvider) -> None:
        """
        参数
        ----
        provider:
            实现 LLMProvider 接口的供应商实例。
            真实接线（API key / 模型配置）见 HANDOFF.md。
        """
        self._provider = provider

    def _call_and_parse(self, prompt: str) -> dict[str, Any]:
        """调用 provider 并解析响应为 dict（不做 schema 校验）。"""
        result = self._provider.complete(prompt, system=_SYSTEM_PROMPT)
        raw_json = extract_json_block(result.text)
        return json.loads(raw_json)

    def judge(
        self,
        trace_summary: str,
        spec_text: str,
        screenshot_refs: list[str] | None = None,
        *,
        trigger_steps: list[str] | None = None,
        retry_invalid: bool = True,
    ) -> dict[str, Any]:
        """执行 L3 语义判定。

        参数
        ----
        trace_summary:
            执行轨迹摘要文本（步骤序列、观察到的行为等）。
        spec_text:
            功能规格文本（期望行为描述）。
        screenshot_refs:
            截图引用路径/描述列表，可选。
        trigger_steps:
            外部提供的触发步骤（会被注入 prompt，LLM 可参考）。

        返回
        ----
        符合 verdict_schema.json 的 verdict dict。

        异常
        ----
        VerdictValidationError:
            LLM 输出经两次尝试后仍不符合 schema。
        json.JSONDecodeError:
            LLM 输出无法解析为 JSON（未重试，属于严重格式错误）。
        """
        if screenshot_refs is None:
            screenshot_refs = []
        if trigger_steps is None:
            trigger_steps = []

        prompt = _build_prompt(trace_summary, spec_text, screenshot_refs)

        # 第一次尝试
        verdict = self._call_and_parse(prompt)

        # schema 校验；普通 runner 可重试一次。正式 M9 lane 传入
        # retry_invalid=False，把格式错误作为本次唯一尝试的终态。
        try:
            validate_verdict(verdict)
        except VerdictValidationError:
            if not retry_invalid:
                raise
            # 第二次尝试（重试 prompt 保持不变，provider 可能返回不同结果）
            verdict = self._call_and_parse(prompt)
            validate_verdict(verdict)  # 二次失败直接抛出，由调用方处理

        return verdict
