from __future__ import annotations

import json

from aiverify.agent.oracle.schema import validate_verdict
from aiverify.runner.run_spec import AssertionSpec
from aiverify.runner.verdict import (
    android_layout_json_to_uiautomator_xml,
    judge_l2_from_android_layout,
)


def _layout(text: str) -> str:
    return json.dumps(
        [
            {
                "resource-id": "org.wikipedia.dev:id/search_src_text",
                "text": text,
                "state": ["focused"],
                "bounds": "[0,0][100,100]",
            }
        ]
    )


def test_android_layout_json_to_xml_supports_resource_id_and_state() -> None:
    xml = android_layout_json_to_uiautomator_xml(_layout("hello"))

    assert "org.wikipedia.dev:id/search_src_text" in xml
    assert 'text="hello"' in xml
    assert 'focused="true"' in xml


def test_judge_l2_from_android_layout_passes_matching_assertion() -> None:
    verdict = judge_l2_from_android_layout(
        _layout("aiverify-smoke-1739"),
        _layout("aiverify-smoke-1739"),
        [
            AssertionSpec(
                resource_id="org.wikipedia.dev:id/search_src_text",
                attr="text",
                expected="aiverify-smoke-1739",
            )
        ],
    )

    validate_verdict(verdict)
    assert verdict["outcome"] == "pass"


def test_judge_l2_from_android_layout_fails_changed_text() -> None:
    verdict = judge_l2_from_android_layout(
        _layout("aiverify-smoke-1739"),
        _layout(""),
        [
            AssertionSpec(
                resource_id="org.wikipedia.dev:id/search_src_text",
                attr="text",
                expected="aiverify-smoke-1739",
            )
        ],
    )

    validate_verdict(verdict)
    assert verdict["outcome"] == "fail"
    assert verdict["defect_class_hypothesis"] == "state_loss"


def test_judge_l2_from_android_layout_inconclusive_on_malformed_json() -> None:
    verdict = judge_l2_from_android_layout(
        "{not-json",
        _layout("x"),
        [],
    )

    validate_verdict(verdict)
    assert verdict["outcome"] == "inconclusive"
