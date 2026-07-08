"""Regression test for the Wikipedia search card L3 seed (#17).

The seed is a text-layout semantic matched pair:

- baseline build renders Search tab card copy about searching Wikipedia
- defect build keeps the same node but renders reading-history copy

L1/L2 are intentionally inconclusive because there is no crash and no boundary
system event. The test replays frozen L3 responses through MockProvider so the seed
stays covered without an emulator or live LLM call.
"""

from __future__ import annotations

import json
from pathlib import Path

from aiverify.agent.oracle.l3 import L3Oracle
from aiverify.agent.oracle.schema import validate_verdict
from aiverify.providers.base import MockProvider
from aiverify.runner.run_spec import load_run_spec

_GOLDSET = Path(__file__).resolve().parents[2] / "bench" / "goldset"
_RUN_SPEC = _GOLDSET / "run-specs" / "wikipedia-ui-rendering-02-search-card-copy-mismatch.yaml"
_FIXTURES = _GOLDSET / "fixtures" / "wikipedia-ui-rendering-02-search-card-copy-mismatch"


def _load(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def _node_for(layout_json: str, resource_id: str) -> dict:
    for node in json.loads(layout_json):
        if node.get("resource-id") == resource_id:
            return node
    raise AssertionError(f"missing resource-id {resource_id}")


def _judge(layout_fixture: str, response_fixture: str) -> dict:
    spec = load_run_spec(_RUN_SPEC)
    provider = MockProvider([_load(response_fixture)])
    trace_summary = "### final checkpoint layout JSON\n" + _load(layout_fixture)
    return L3Oracle(provider).judge(trace_summary, spec.scenario.l3_spec)


def test_run_spec_is_eventless_l3_search_card_seed() -> None:
    spec = load_run_spec(_RUN_SPEC)

    assert spec.scenario.id == "wikipedia-ui-rendering-02-search-card-copy-mismatch"
    assert spec.scenario.system_events == []
    assert spec.scenario.assertions == []
    assert "search_card" in spec.scenario.l3_spec
    assert "search_text_view" in spec.scenario.l3_spec
    assert "reading history" in spec.scenario.l3_spec
    assert spec.diff is not None and spec.diff.name.endswith(
        "wikipedia-ui-rendering-02-search-card-copy-mismatch.patch"
    )
    assert spec.scenario.metric_context.seed_kind == "injected_defect"
    assert spec.scenario.metric_context.taxonomy_category == "ui-rendering"
    assert spec.scenario.metric_context.taxonomy_pattern_id == "ui-rendering-02"
    assert spec.scenario.metric_context.expected_oracle_level == "L3"
    assert spec.scenario.metric_context.expected_oracle_defect_class == "ui_rendering"


def test_defect_build_l3_fails_with_ui_rendering() -> None:
    verdict = _judge("defect-final-layout.json", "defect-l3-response.md")

    validate_verdict(verdict)
    assert verdict["level"] == "L3"
    assert verdict["outcome"] == "fail"
    assert verdict["defect_class_hypothesis"] == "ui_rendering"


def test_baseline_control_l3_passes_under_same_spec() -> None:
    verdict = _judge("baseline-final-layout.json", "baseline-l3-response.md")

    validate_verdict(verdict)
    assert verdict["level"] == "L3"
    assert verdict["outcome"] == "pass"
    assert verdict["defect_class_hypothesis"] is None


def test_fixtures_encode_search_card_copy_mismatch_not_missing_node() -> None:
    baseline_layout = _load("baseline-final-layout.json")
    defect_layout = _load("defect-final-layout.json")

    assert _node_for(baseline_layout, "search_card")
    assert _node_for(defect_layout, "search_card")
    assert _node_for(baseline_layout, "search_text_view").get("text", "").startswith(
        "Search"
    )
    assert _node_for(defect_layout, "search_text_view").get("text") == (
        "Track what you've been reading here."
    )
    assert _node_for(baseline_layout, "search_icon").get(
        "content-desc", ""
    ).startswith("Search")
    assert _node_for(defect_layout, "search_icon").get("content-desc") == (
        "Track what you've been reading here."
    )
