"""Regression test for the Wikipedia config-change duplicated-state seed (#15).

The seed is a matched pair under the same dark-mode (uiMode) configuration
change:

- baseline build keeps exactly one copy of the query -> L2 pass
- defect build appends restored query text to itself -> L2 fail

The defect is intentionally not a simple state-loss case. The current verdict
schema still reports L2 state assertion failures as ``state_loss``, so this test
guards the artifact evidence text and fixtures to preserve the duplicated-state
semantics.
"""

from __future__ import annotations

from pathlib import Path

from aiverify.agent.oracle.schema import validate_verdict
from aiverify.runner.run_spec import load_run_spec
from aiverify.runner.verdict import judge_l2_from_android_layout

_GOLDSET = Path(__file__).resolve().parents[2] / "bench" / "goldset"
_RUN_SPEC = _GOLDSET / "run-specs" / "wikipedia-config-change-02-query-duplication.yaml"
_FIXTURES = _GOLDSET / "fixtures" / "wikipedia-config-change-02-query-duplication"


def _load(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def test_run_spec_parses_with_dark_mode_boundary_and_patch() -> None:
    spec = load_run_spec(_RUN_SPEC)

    assert spec.package == "org.wikipedia.dev"
    assert spec.scenario.id == "wikipedia-config-change-02-query-duplication"
    assert spec.spec is not None and spec.spec.name.endswith(
        "wikipedia-config-change-02-query-duplication.md"
    )
    assert spec.diff is not None and spec.diff.name.endswith(
        "wikipedia-config-change-02-query-duplication.patch"
    )
    event = spec.scenario.system_events[0]
    assert event.event == "dark_mode"
    assert event.args == {"night": "yes"}
    assert "zzsentinelqx" in spec.scenario.user_actions[1]
    assert "Back" in spec.scenario.user_actions[1]
    assert [a.resource_id for a in spec.scenario.assertions] == ["search_src_text"]
    assert [a.expected for a in spec.scenario.assertions] == ["zzsentinelqx"]


def test_defect_build_l2_fails_when_query_is_duplicated() -> None:
    spec = load_run_spec(_RUN_SPEC)

    verdict = judge_l2_from_android_layout(
        _load("defect-before-layout.json"),
        _load("defect-after-layout.json"),
        spec.scenario.assertions,
        trigger_steps=["type sentinel", "[boundary] dark-mode config change"],
    )

    validate_verdict(verdict)
    assert verdict["outcome"] == "fail"
    assert verdict["defect_class_hypothesis"] == "state_loss"
    assert "zzsentinelqxzzsentinelqx" in verdict["evidence"][0]["ref"]


def test_baseline_control_l2_passes_with_single_query_after_same_event() -> None:
    spec = load_run_spec(_RUN_SPEC)

    verdict = judge_l2_from_android_layout(
        _load("control-before-layout.json"),
        _load("control-after-layout.json"),
        spec.scenario.assertions,
        trigger_steps=["type sentinel", "[boundary] dark-mode config change"],
    )

    validate_verdict(verdict)
    assert verdict["outcome"] == "pass"
    assert verdict["defect_class_hypothesis"] is None


def test_fixtures_encode_duplication_not_loss() -> None:
    sentinel = "zzsentinelqx"
    duplicated = sentinel + sentinel

    assert sentinel in _load("control-before-layout.json")
    assert sentinel in _load("control-after-layout.json")
    assert duplicated not in _load("control-after-layout.json")

    assert sentinel in _load("defect-before-layout.json")
    assert duplicated in _load("defect-after-layout.json")
