"""验证计划生成器。

PlanGenerator 接收代码差异、规格文本与 taxonomy 模式，调用 LLM provider
生成结构化验证计划（VerificationPlan）。内部使用 jsonschema 校验 LLM 输出，
畸形输出时携带错误信息重试一次，仍失败抛 PlanGenerationError。
"""

from __future__ import annotations

import json
import pathlib

import jsonschema

from aiverify.providers import LLMProvider
from aiverify.providers.parsing import extract_json_block

from .models import ScenarioCluster, SpecBlindSpot, SystemEventStep, VerificationPlan

# 加载与本模块同目录的 JSON Schema 文件
_SCHEMA_PATH = pathlib.Path(__file__).parent / "plan_schema.json"
_PLAN_SCHEMA: dict = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))

#: 系统提示：角色设定与输出格式约束
_SYSTEM_PROMPT = """你是一名资深移动端 QA 工程师，专精 Android 行为层验证。
你的任务是：根据代码差异（diff）、产品规格与已知缺陷模式（taxonomy），
生成一份 JSON 格式的验证计划。

输出要求：
- 纯 JSON，不要包裹 markdown 代码块（或仅用 ```json ... ``` 包裹）
- 严格遵循给定的 JSON Schema
- scenario_clusters 至少包含 1 个场景簇
- 所有字符串字段使用中文或英文均可，保持一致性"""


def _build_prompt(
    diff_text: str,
    spec_text: str,
    taxonomy_patterns: list[dict],
    *,
    previous_output: str = "",
    validation_error: str = "",
) -> str:
    """组装发送给 LLM 的 prompt。

    Args:
        diff_text: 代码差异文本（unified diff 格式）。
        spec_text: 产品规格文本。
        taxonomy_patterns: taxonomy 模式列表，每项含 id/name/description/trigger_scenario 字段。
        previous_output: 上一次 LLM 输出（重试时使用）。
        validation_error: 上一次校验错误信息（重试时使用）。

    Returns:
        组装好的 prompt 字符串。
    """
    # 将 taxonomy 模式格式化为摘要
    taxonomy_summary_lines: list[str] = []
    for p in taxonomy_patterns:
        pid = p.get("id", "")
        name = p.get("name", "")
        desc = p.get("description", "")
        trigger = p.get("trigger_scenario", "")
        taxonomy_summary_lines.append(
            f"- [{pid}] {name}: {desc}"
            + (f"（触发场景：{trigger}）" if trigger else "")
        )
    taxonomy_summary = (
        "\n".join(taxonomy_summary_lines) if taxonomy_summary_lines else "（无 taxonomy 模式）"
    )

    schema_str = json.dumps(_PLAN_SCHEMA, ensure_ascii=False, indent=2)

    parts = [
        "## 代码差异（diff）",
        "```",
        diff_text.strip(),
        "```",
        "",
        "## 产品规格",
        spec_text.strip(),
        "",
        "## 已知缺陷模式（taxonomy）",
        taxonomy_summary,
        "",
        "## 输出 JSON Schema（严格遵循）",
        "```json",
        schema_str,
        "```",
        "",
        "请根据以上信息，输出符合上述 Schema 的验证计划 JSON。",
    ]

    if previous_output and validation_error:
        parts += [
            "",
            "---",
            "【重试提示】上一次输出未通过校验，请修正后重新输出。",
            f"上一次输出：\n```\n{previous_output}\n```",
            f"校验错误：{validation_error}",
        ]

    return "\n".join(parts)



def _parse_and_validate(raw_text: str) -> dict:
    """解析 JSON 并用 jsonschema 校验。

    Args:
        raw_text: LLM 返回的原始文本。

    Returns:
        校验通过的 Python dict。

    Raises:
        ValueError: JSON 解析失败或 schema 校验失败，错误信息含详情。
    """
    cleaned = extract_json_block(raw_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 解析失败：{exc}") from exc

    try:
        jsonschema.validate(data, _PLAN_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise ValueError(f"Schema 校验失败：{exc.message}") from exc

    return data


def _dict_to_plan(data: dict) -> VerificationPlan:
    """将校验通过的 dict 转换为 VerificationPlan dataclass。

    Args:
        data: 已通过 jsonschema 校验的字典。

    Returns:
        VerificationPlan 实例。
    """
    clusters: list[ScenarioCluster] = []
    for c in data.get("scenario_clusters", []):
        events = [
            SystemEventStep(step_index=e["step_index"], event=e["event"])
            for e in c.get("system_events", [])
        ]
        clusters.append(
            ScenarioCluster(
                id=c["id"],
                target_screens=c["target_screens"],
                user_actions=c["user_actions"],
                system_events=events,
                expected_behavior=c["expected_behavior"],
                related_defect_patterns=c.get("related_defect_patterns") or [],
            )
        )

    blind_spots = [
        SpecBlindSpot(description=b["description"], rationale=b["rationale"])
        for b in data.get("spec_blind_spots", [])
    ]

    return VerificationPlan(
        change_summary=data["change_summary"],
        scenario_clusters=clusters,
        spec_blind_spots=blind_spots,
    )


class PlanGenerationError(Exception):
    """计划生成失败：LLM 两次输出均无法通过解析或 schema 校验。"""


class PlanGenerator:
    """验证计划生成器。

    使用注入的 LLMProvider 将代码差异、规格与 taxonomy 模式转化为
    结构化验证计划（VerificationPlan）。

    Attributes:
        provider: 用于生成计划的 LLM provider 实例。
    """

    def __init__(self, provider: LLMProvider) -> None:
        """初始化生成器。

        Args:
            provider: LLMProvider 实例，负责实际的 LLM 调用。
        """
        self.provider = provider

    def generate(
        self,
        diff_text: str,
        spec_text: str,
        taxonomy_patterns: list[dict],
    ) -> VerificationPlan:
        """生成验证计划。

        内部流程：
        1. 组装 prompt（含 diff、规格、taxonomy 摘要、Schema 格式要求）
        2. 调用 provider.complete 获取 LLM 输出
        3. 解析 JSON 并用 jsonschema 校验
        4. 若失败，携带上次输出与错误信息重试一次
        5. 两次均失败则抛 PlanGenerationError

        Args:
            diff_text: 代码差异文本（unified diff 格式）。
            spec_text: 产品规格文本。
            taxonomy_patterns: taxonomy 模式列表，每项应含
                id/name/description/trigger_scenario 字段；由调用方注入，
                本模块不依赖任何 taxonomy loader。

        Returns:
            解析并校验通过的 VerificationPlan 实例。

        Raises:
            PlanGenerationError: LLM 两次输出均无法通过解析或 schema 校验。
        """
        # 第一次尝试
        prompt = _build_prompt(diff_text, spec_text, taxonomy_patterns)
        result = self.provider.complete(prompt, system=_SYSTEM_PROMPT)
        first_output = result.text

        try:
            data = _parse_and_validate(first_output)
            return _dict_to_plan(data)
        except ValueError as first_err:
            first_error_msg = str(first_err)

        # 第二次尝试（携带上次输出与校验错误）
        retry_prompt = _build_prompt(
            diff_text,
            spec_text,
            taxonomy_patterns,
            previous_output=first_output,
            validation_error=first_error_msg,
        )
        retry_result = self.provider.complete(retry_prompt, system=_SYSTEM_PROMPT)
        second_output = retry_result.text

        try:
            data = _parse_and_validate(second_output)
            return _dict_to_plan(data)
        except ValueError as second_err:
            raise PlanGenerationError(
                f"验证计划生成失败，两次 LLM 输出均无法通过校验。\n"
                f"第一次错误：{first_error_msg}\n"
                f"第二次错误：{second_err}"
            ) from second_err
