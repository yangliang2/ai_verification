"""Regression test for the Wikipedia ui-rendering nav-label-swap seed (L3 exercise, #12).

Freezes the real on-device evidence captured in
docs/runs/2026-07-06-wikipedia-ui-rendering-01-nav-label-swap/ as hardware- and
LLM-independent fixtures: the final checkpoint layouts AND the actual Codex CLI judge
responses. The L3 path is replayed by feeding the frozen judge output through
L3Oracle + MockProvider, so "the semantic oracle catches a wrong-label defect and
passes the clean baseline" stays green without an emulator, a rebuild, or an LLM call.

The seed is a matched pair on the SAME event-less scenario and the SAME l3_spec:
- defect build  (READING_LISTS/SEARCH string resources swapped) -> L3 fail / ui_rendering
- baseline build (correct labels)                               -> L3 pass
Both halves: no crash (L1 inconclusive) and no boundary event (L2 not applicable) —
the defect is invisible to the cheap oracle layers by construction.
"""

from __future__ import annotations

import json
from pathlib import Path

from aiverify.agent.oracle.l3 import L3Oracle
from aiverify.agent.oracle.schema import validate_verdict
from aiverify.providers.base import MockProvider
from aiverify.runner.run_spec import load_run_spec

_GOLDSET = Path(__file__).resolve().parents[2] / "bench" / "goldset"
_RUN_SPEC = _GOLDSET / "run-specs" / "wikipedia-ui-rendering-01-nav-label-swap.yaml"
_FIXTURES = _GOLDSET / "fixtures" / "wikipedia-ui-rendering-01-nav-label-swap"


def _load(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def _nav_labels(layout_json: str) -> dict[str, str]:
    return {
        node["resource-id"]: node.get("content-desc", "")
        for node in json.loads(layout_json)
        if str(node.get("resource-id", "")).startswith("nav_tab_")
    }


def _judge(layout_fixture: str, response_fixture: str) -> dict:
    spec = load_run_spec(_RUN_SPEC)
    provider = MockProvider([_load(response_fixture)])
    trace_summary = (
        "### 最终 checkpoint（after-segment-0）的 UI layout JSON 全文\n"
        + _load(layout_fixture)
    )
    return L3Oracle(provider).judge(trace_summary, spec.scenario.l3_spec)


def test_run_spec_is_an_l3_seed() -> None:
    spec = load_run_spec(_RUN_SPEC)

    assert spec.scenario.id == "wikipedia-ui-rendering-01-nav-label-swap"
    # L1/L2 构造性不可见：无系统事件、无 L2 断言，靠 l3_spec 门控进 L3
    assert spec.scenario.system_events == []
    assert spec.scenario.assertions == []
    assert "nav_tab_reading_lists" in spec.scenario.l3_spec
    assert spec.diff is not None and spec.diff.name.endswith(
        "wikipedia-ui-rendering-01-nav-label-swap.patch"
    )


def test_defect_build_l3_fails_with_ui_rendering() -> None:
    verdict = _judge("defect-final-layout.json", "defect-l3-response.md")

    validate_verdict(verdict)
    assert verdict["level"] == "L3"
    assert verdict["outcome"] == "fail"
    assert verdict["defect_class_hypothesis"] == "ui_rendering"


def test_baseline_control_l3_passes_under_same_spec() -> None:
    # matched pair: the same scenario + the same l3_spec on the unmodified build must
    # pass, so the fail above is attributable to the injected label swap.
    verdict = _judge("baseline-final-layout.json", "baseline-l3-response.md")

    validate_verdict(verdict)
    assert verdict["level"] == "L3"
    assert verdict["outcome"] == "pass"


def test_fixtures_encode_the_matched_pair() -> None:
    # guards the fixtures: identical node set (L2-invisible), only the two labels swap
    baseline = _nav_labels(_load("baseline-final-layout.json"))
    defect = _nav_labels(_load("defect-final-layout.json"))

    assert set(baseline) == set(defect)  # no node appears or disappears
    assert baseline["nav_tab_reading_lists"] == "Saved"
    assert baseline["nav_tab_search"] == "Search"
    assert defect["nav_tab_reading_lists"] == "Search"
    assert defect["nav_tab_search"] == "Saved"
    for untouched in ("nav_tab_home", "nav_tab_edits", "nav_tab_more"):
        assert baseline[untouched] == defect[untouched]
