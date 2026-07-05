"""Regression test for the Wikipedia config-change baseline Goldset smoke seed (#8).

Freezes the real on-device evidence captured in
docs/runs/2026-07-05-wikipedia-config-change-smoke/ as hardware-independent
fixtures, so the verdict chain (run-spec assertion -> Android CLI layout JSON ->
verdict.py -> L2Oracle) stays green without an emulator.

Baseline (no injected defect): Wikipedia retains the search query across a
configuration change, so L2 must report outcome=pass.
"""

from __future__ import annotations

from pathlib import Path

from aiverify.agent.oracle.schema import validate_verdict
from aiverify.runner.run_spec import load_run_spec
from aiverify.runner.verdict import judge_l2_from_android_layout

_GOLDSET = Path(__file__).resolve().parents[2] / "bench" / "goldset"
_RUN_SPEC = _GOLDSET / "run-specs" / "wikipedia-config-change-smoke.yaml"
_FIXTURES = _GOLDSET / "fixtures" / "wikipedia-config-change-smoke"


def _load(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def test_run_spec_parses_with_boundary_rotate_event() -> None:
    spec = load_run_spec(_RUN_SPEC)

    assert spec.package == "org.wikipedia.dev"
    assert spec.scenario.id == "wikipedia-config-change-smoke"
    # rotation injected at the last user action's Journey Segment Boundary
    assert len(spec.scenario.system_events) == 1
    event = spec.scenario.system_events[0]
    assert event.event == "rotate"
    assert event.step_index == len(spec.scenario.user_actions) - 1
    # single state assertion on the classic SearchView EditText
    assert [a.resource_id for a in spec.scenario.assertions] == ["search_src_text"]


def test_baseline_smoke_l2_passes_on_captured_evidence() -> None:
    spec = load_run_spec(_RUN_SPEC)
    before = _load("before-layout.json")
    after = _load("after-layout.json")

    verdict = judge_l2_from_android_layout(
        before,
        after,
        spec.scenario.assertions,
        trigger_steps=["type sentinel", "[boundary] rotate portrait->landscape"],
    )

    validate_verdict(verdict)
    assert verdict["level"] == "L2"
    # baseline: query retained across rotation -> pass, no defect hypothesis
    assert verdict["outcome"] == "pass"
    assert verdict["defect_class_hypothesis"] is None


def test_captured_evidence_actually_holds_the_sentinel() -> None:
    # guards the fixtures themselves: both layouts must carry the sentinel text,
    # otherwise the pass above would be vacuous.
    sentinel = "zzsentinelqx"
    assert sentinel in _load("before-layout.json")
    assert sentinel in _load("after-layout.json")
