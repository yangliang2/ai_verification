"""Regression test for the Wikipedia navigation Back-button seed (#16).

The seed is a matched pair around the same Back path and dark-mode observation
boundary:

- baseline build returns from SearchActivity to the Search tab -> L2 pass
- defect build swallows the Activity-level Back callback -> L2 fail

The current verdict schema still reports L2 assertion failures as
``state_loss``. The test guards the artifact evidence text and fixtures to keep
the navigation-specific semantics visible.
"""

from __future__ import annotations

from pathlib import Path

from aiverify.agent.oracle.schema import validate_verdict
from aiverify.runner.run_spec import load_run_spec
from aiverify.runner.verdict import judge_l2_from_android_layout

_GOLDSET = Path(__file__).resolve().parents[2] / "bench" / "goldset"
_RUN_SPEC = _GOLDSET / "run-specs" / "wikipedia-navigation-02-back-button-swallowed.yaml"
_FIXTURES = _GOLDSET / "fixtures" / "wikipedia-navigation-02-back-button-swallowed"


def _load(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def test_run_spec_parses_with_back_path_dark_mode_boundary_and_patch() -> None:
    spec = load_run_spec(_RUN_SPEC)

    assert spec.package == "org.wikipedia.dev"
    assert spec.scenario.id == "wikipedia-navigation-02-back-button-swallowed"
    assert spec.spec is not None and spec.spec.name.endswith(
        "wikipedia-navigation-02-back-button-swallowed.md"
    )
    assert spec.diff is not None and spec.diff.name.endswith(
        "wikipedia-navigation-02-back-button-swallowed.patch"
    )
    event = spec.scenario.system_events[0]
    assert event.event == "dark_mode"
    assert event.args == {"night": "yes"}
    assert "zznavbackqx" in spec.scenario.user_actions[1]
    assert "second time" in spec.scenario.user_actions[1]
    assert "should return" not in spec.scenario.user_actions[1]
    assert "finish the segment" in spec.scenario.user_actions[1]
    assert [(a.resource_id, a.attr, a.expected) for a in spec.scenario.assertions] == [
        ("search_card", "resource-id", "search_card")
    ]
    assert spec.scenario.metric_context.seed_kind == "injected_defect"
    assert spec.scenario.metric_context.taxonomy_category == "navigation"
    assert spec.scenario.metric_context.taxonomy_pattern_id == "navigation-02"
    assert spec.scenario.metric_context.expected_oracle_level == "L2"
    assert spec.scenario.metric_context.expected_oracle_defect_class == "state_loss"


def test_defect_build_l2_fails_when_back_is_swallowed() -> None:
    spec = load_run_spec(_RUN_SPEC)

    verdict = judge_l2_from_android_layout(
        _load("defect-before-layout.json"),
        _load("defect-after-layout.json"),
        spec.scenario.assertions,
        trigger_steps=["second Back should leave SearchActivity", "[boundary] dark-mode"],
    )

    validate_verdict(verdict)
    assert verdict["outcome"] == "fail"
    assert verdict["defect_class_hypothesis"] == "state_loss"
    assert "search_card" in verdict["evidence"][0]["ref"]


def test_baseline_control_l2_passes_when_search_card_returns() -> None:
    spec = load_run_spec(_RUN_SPEC)

    verdict = judge_l2_from_android_layout(
        _load("control-before-layout.json"),
        _load("control-after-layout.json"),
        spec.scenario.assertions,
        trigger_steps=["second Back should leave SearchActivity", "[boundary] dark-mode"],
    )

    validate_verdict(verdict)
    assert verdict["outcome"] == "pass"
    assert verdict["defect_class_hypothesis"] is None


def test_fixtures_encode_navigation_back_swallow_not_crash() -> None:
    assert "search_card" in _load("control-before-layout.json")
    assert "search_card" in _load("control-after-layout.json")
    assert "search_src_text" not in _load("control-after-layout.json")

    assert "search_src_text" in _load("defect-before-layout.json")
    assert "search_src_text" in _load("defect-after-layout.json")
    assert "search_card" not in _load("defect-after-layout.json")
