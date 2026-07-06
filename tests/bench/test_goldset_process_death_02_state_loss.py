"""Regression test for the Wikipedia process-death tab-state-loss seed (M1 seed 5).

Freezes the real on-device evidence captured in
docs/runs/2026-07-06-wikipedia-process-death-02-tab-state-loss/ as
hardware-independent fixtures, so the "verifier catches a process-death state-loss
defect" result stays green without an emulator or a rebuild.

The seed is a matched pair under the SAME process_death event (HOME -> am kill ->
explicit launcher-intent relaunch):
- defect build  (tab state in an in-memory singleton) -> tab list lost -> L2 fail / state_loss
- baseline build (tab state in Prefs.tabs)            -> tab list kept -> L2 pass

Key host findings behind the assertion choice (see the seed spec): after real process
death the CURRENT article restores via system saved-state + intent redelivery — it
never depends on the app's own persistence. What Prefs.tabs actually carries across
process death is the tab list, observable as toolbar `tabsCountText` ("2" vs "1").
"""

from __future__ import annotations

from pathlib import Path

from aiverify.agent.oracle.schema import validate_verdict
from aiverify.runner.run_spec import load_run_spec
from aiverify.runner.verdict import judge_l2_from_android_layout

_GOLDSET = Path(__file__).resolve().parents[2] / "bench" / "goldset"
_RUN_SPEC = _GOLDSET / "run-specs" / "wikipedia-process-death-02-tab-state-loss.yaml"
_FIXTURES = _GOLDSET / "fixtures" / "wikipedia-process-death-02-tab-state-loss"

_TRIGGER = ["open Cat and Dog tabs", "[boundary] process death (home + am kill + relaunch)"]


def _load(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def test_run_spec_parses_with_process_death_event() -> None:
    spec = load_run_spec(_RUN_SPEC)

    assert spec.package == "org.wikipedia.dev"
    assert spec.activity == "org.wikipedia.DefaultIcon"
    assert spec.scenario.id == "wikipedia-process-death-02-tab-state-loss"
    event = spec.scenario.system_events[0]
    assert event.event == "process_death"
    assert spec.diff is not None and spec.diff.name.endswith(
        "wikipedia-process-death-02-tab-state-loss.patch"
    )
    assertion = spec.scenario.assertions[0]
    assert (assertion.resource_id, assertion.attr, assertion.expected) == (
        "tabsCountText", "text", "2",
    )


def test_defect_build_l2_fails_with_state_loss() -> None:
    spec = load_run_spec(_RUN_SPEC)

    verdict = judge_l2_from_android_layout(
        _load("defect-before-layout.json"),
        _load("defect-after-layout.json"),
        spec.scenario.assertions,
        trigger_steps=_TRIGGER,
    )

    validate_verdict(verdict)
    assert verdict["outcome"] == "fail"
    assert verdict["defect_class_hypothesis"] == "state_loss"


def test_baseline_control_l2_passes_under_same_event() -> None:
    # matched pair: same scenario + same process_death event on the unmodified build
    # must pass, so the fail above is attributable to the injected persistence rewire.
    spec = load_run_spec(_RUN_SPEC)

    verdict = judge_l2_from_android_layout(
        _load("control-before-layout.json"),
        _load("control-after-layout.json"),
        spec.scenario.assertions,
        trigger_steps=_TRIGGER,
    )

    validate_verdict(verdict)
    assert verdict["outcome"] == "pass"


def _tabs_count(layout_json: str) -> str | None:
    import json

    for node in json.loads(layout_json):
        if node.get("resource-id") == "tabsCountText":
            return node.get("text")
    return None


def test_fixtures_encode_the_matched_pair() -> None:
    # guards the fixtures: both builds show 2 tabs before the event; after real
    # process death the baseline keeps 2, while the defect build restores into an
    # empty tab list — PageActivity bails to the main feed, so the article toolbar
    # (and tabsCountText with it) is gone entirely. (When the current article is
    # re-derivable from intent redelivery the same defect instead shows "1"; both
    # shapes are state loss and both fail the "2" assertion.)
    assert _tabs_count(_load("defect-before-layout.json")) == "2"
    assert _tabs_count(_load("control-before-layout.json")) == "2"
    assert _tabs_count(_load("defect-after-layout.json")) is None
    assert _tabs_count(_load("control-after-layout.json")) == "2"
