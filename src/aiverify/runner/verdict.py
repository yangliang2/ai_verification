"""Verdict helpers for runner evidence."""

from __future__ import annotations

import json
import uuid
import xml.etree.ElementTree as ET
from typing import Any

from aiverify.agent.oracle import L2Oracle, validate_verdict
from aiverify.runner.run_spec import AssertionSpec


def judge_l2_from_android_layout(
    before_layout_json: str,
    after_layout_json: str,
    assertions: list[AssertionSpec],
    *,
    trigger_steps: list[str] | None = None,
) -> dict[str, Any]:
    """Evaluate L2 assertions from Android CLI layout JSON evidence."""
    try:
        before_xml = android_layout_json_to_uiautomator_xml(before_layout_json)
        after_xml = android_layout_json_to_uiautomator_xml(after_layout_json)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        verdict: dict[str, Any] = {
            "verdict_id": f"L2-{uuid.uuid4().hex[:8]}",
            "level": "L2",
            "outcome": "inconclusive",
            "defect_class_hypothesis": None,
            "trigger_steps": trigger_steps or [],
            "evidence": [
                {
                    "type": "state_diff",
                    "ref": str(exc),
                    "note": "Android CLI layout JSON 无法转换为状态断言输入",
                }
            ],
            "confidence": 0.0,
        }
        validate_verdict(verdict)
        return verdict

    oracle_assertions = [
        {"resource_id": a.resource_id, "attr": a.attr, "expected": a.expected}
        for a in assertions
    ]
    return L2Oracle().judge(
        before_xml,
        after_xml,
        oracle_assertions,
        trigger_steps=trigger_steps,
    )


def android_layout_json_to_uiautomator_xml(layout_json: str) -> str:
    """Convert Android CLI flat layout JSON to a minimal uiautomator-like XML tree."""
    data = json.loads(layout_json)
    if isinstance(data, dict) and "added" in data:
        # layout --diff shape is not suitable for full state assertion.
        raise ValueError("layout diff JSON cannot be used as full state evidence")
    if not isinstance(data, list):
        raise ValueError("layout JSON must be a list of elements")

    root = ET.Element("hierarchy")
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        node = ET.SubElement(root, "node")
        node.set("index", str(index))
        resource_id = _first_str(item, "resource-id", "resourceId")
        if resource_id:
            node.set("resource-id", resource_id)
        text = _first_str(item, "text")
        if text is not None:
            node.set("text", text)
        content_desc = _first_str(item, "content-desc", "contentDesc")
        if content_desc:
            node.set("content-desc", content_desc)
        bounds = _first_str(item, "bounds")
        if bounds:
            node.set("bounds", bounds)
        state = item.get("state", [])
        if isinstance(state, list):
            node.set("checked", "true" if "checked" in state else "false")
            node.set("selected", "true" if "selected" in state else "false")
            node.set("focused", "true" if "focused" in state else "false")
    return ET.tostring(root, encoding="unicode")


def _first_str(item: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str):
            return value
    return None
