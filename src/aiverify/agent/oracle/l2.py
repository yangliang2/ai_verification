"""L2 状态断言判定器——基于 accessibility tree XML 的前后状态比对。

输入：操作前后两份 uiautomator dump 格式的 XML 字符串 + 期望断言列表。
输出：符合 verdict_schema.json 的 verdict dict。

设计原则
--------
L2 通过解析 XML 并比对关键节点属性来判断状态是否保留。
期望断言格式：{ "resource_id": str, "attr": str, "expected": str }
- 节点存在且属性值匹配 → pass
- 节点存在但属性值不匹配 → fail（state_diff 证据含具体差异）
- 节点在操作后消失 → fail（evidence 说明节点消失）
"""

from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET
from typing import Any, TypedDict

from aiverify.agent.oracle.schema import validate_verdict


class Assertion(TypedDict):
    """单条期望断言。

    resource_id: 目标节点的 resource-id 属性值（精确匹配）。
    attr:        要校验的属性名（如 "text"、"checked"）。
    expected:    期望的属性值字符串。
    """

    resource_id: str
    attr: str
    expected: str


def _find_node_by_resource_id(
    root: ET.Element, resource_id: str
) -> ET.Element | None:
    """在 XML 树中递归查找第一个 resource-id 匹配的节点。"""
    for node in root.iter():
        if node.get("resource-id") == resource_id:
            return node
    return None


class L2Oracle:
    """基于 accessibility tree XML 的状态断言判定器（L2 层）。

    比较操作前后两份 uiautomator dump XML，根据调用者提供的断言列表
    判断关键节点属性是否在操作后得到保留。

    L2 可宣告 pass（所有断言通过）或 fail（至少一条断言失败），
    无法判断（如 XML 格式错误）时返回 inconclusive。
    """

    def judge(
        self,
        xml_before: str,
        xml_after: str,
        assertions: list[Assertion],
        *,
        trigger_steps: list[str] | None = None,
    ) -> dict[str, Any]:
        """执行 L2 状态断言判定。

        参数
        ----
        xml_before:
            操作前的 uiautomator dump XML 字符串。
        xml_after:
            操作后的 uiautomator dump XML 字符串。
        assertions:
            期望断言列表，每项含 resource_id / attr / expected。
        trigger_steps:
            触发本次判定的操作步骤列表，可选。

        返回
        ----
        符合 verdict_schema.json 的 verdict dict：
        - 所有断言通过 → outcome="pass"
        - 任一断言失败 → outcome="fail"，state_diff 证据含具体差异
        - 解析异常 → outcome="inconclusive"
        """
        if trigger_steps is None:
            trigger_steps = []

        # 解析 XML
        try:
            root_before = ET.fromstring(xml_before)
            root_after = ET.fromstring(xml_after)
        except ET.ParseError as exc:
            verdict: dict[str, Any] = {
                "verdict_id": f"L2-{uuid.uuid4().hex[:8]}",
                "level": "L2",
                "outcome": "inconclusive",
                "defect_class_hypothesis": None,
                "trigger_steps": trigger_steps,
                "evidence": [
                    {
                        "type": "state_diff",
                        "ref": str(exc),
                        "note": "XML 解析失败，无法执行状态断言",
                    }
                ],
                "confidence": 0.0,
            }
            validate_verdict(verdict)
            return verdict

        fail_evidence: list[dict[str, str]] = []

        for assertion in assertions:
            resource_id = assertion["resource_id"]
            attr = assertion["attr"]
            expected = assertion["expected"]

            node_before = _find_node_by_resource_id(root_before, resource_id)
            node_after = _find_node_by_resource_id(root_after, resource_id)

            if node_after is None:
                # 节点在操作后消失
                before_val = node_before.get(attr, "<absent>") if node_before else "<absent>"
                diff_text = (
                    f"resource-id={resource_id!r}：操作后节点消失。"
                    f"操作前 {attr}={before_val!r}，期望保留 {attr}={expected!r}"
                )
                fail_evidence.append(
                    {
                        "type": "state_diff",
                        "ref": diff_text,
                        "note": f"节点 {resource_id!r} 在操作后从 accessibility tree 中消失",
                    }
                )
            else:
                actual = node_after.get(attr, "<absent>")
                if actual != expected:
                    diff_text = (
                        f"resource-id={resource_id!r} attr={attr!r}："
                        f"期望={expected!r}，实际={actual!r}"
                    )
                    fail_evidence.append(
                        {
                            "type": "state_diff",
                            "ref": diff_text,
                            "note": f"属性 {attr!r} 值与期望不符",
                        }
                    )

        if fail_evidence:
            outcome = "fail"
            defect_class: str | None = "state_loss"
            confidence = 0.9
            evidence = fail_evidence
        else:
            outcome = "pass"
            defect_class = None
            confidence = 0.9
            # pass 时提供一条概要证据，说明所有断言均通过
            evidence = [
                {
                    "type": "state_diff",
                    "ref": f"已校验 {len(assertions)} 条断言，全部通过",
                    "note": "L2 状态断言全部满足",
                }
            ] if assertions else []

        verdict = {
            "verdict_id": f"L2-{uuid.uuid4().hex[:8]}",
            "level": "L2",
            "outcome": outcome,
            "defect_class_hypothesis": defect_class,
            "trigger_steps": trigger_steps,
            "evidence": evidence,
            "confidence": confidence,
        }
        validate_verdict(verdict)
        return verdict
