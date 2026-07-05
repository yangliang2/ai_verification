"""Regression test for the Wikipedia config-change INJECTED DEFECT seed (#8, positive half).

Freezes the real on-device evidence captured in
docs/runs/2026-07-05-wikipedia-config-change-01-defect/ as hardware-independent
fixtures, so the "verifier catches a config-change state-loss defect" result stays
green without an emulator or a rebuild.

The seed is a matched pair under the SAME dark-mode (uiMode) config-change event:
- defect build  (isSaveFromParentEnabled = false) -> query lost   -> L2 fail / state_loss
- baseline build (unmodified)                      -> query kept   -> L2 pass

Rotation is deliberately NOT used: SearchActivity declares
android:configChanges="orientation|screenSize", so rotation never recreates the
activity and cannot exercise the save/restore path. See the run record.
"""

from __future__ import annotations

from pathlib import Path

from aiverify.agent.oracle.schema import validate_verdict
from aiverify.runner.run_spec import load_run_spec
from aiverify.runner.verdict import judge_l2_from_android_layout

_GOLDSET = Path(__file__).resolve().parents[2] / "bench" / "goldset"
_RUN_SPEC = _GOLDSET / "run-specs" / "wikipedia-config-change-01-defect.yaml"
_FIXTURES = _GOLDSET / "fixtures" / "wikipedia-config-change-01-defect"


def _load(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def test_run_spec_parses_with_dark_mode_event() -> None:
    spec = load_run_spec(_RUN_SPEC)

    assert spec.package == "org.wikipedia.dev"
    assert spec.scenario.id == "wikipedia-config-change-01-defect"
    event = spec.scenario.system_events[0]
    assert event.event == "dark_mode"
    assert event.args.get("night") == "yes"
    # the run spec points at the injected-defect patch artifact
    assert spec.diff is not None and spec.diff.name.endswith(
        "wikipedia-config-change-01-search-query-loss.patch"
    )


def test_defect_build_l2_fails_with_state_loss() -> None:
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


def test_baseline_control_l2_passes_under_same_event() -> None:
    # matched pair: same scenario + same dark-mode event on the unmodified build
    # must pass, so the fail above is attributable to the injected line only.
    spec = load_run_spec(_RUN_SPEC)

    verdict = judge_l2_from_android_layout(
        _load("control-before-layout.json"),
        _load("control-after-layout.json"),
        spec.scenario.assertions,
        trigger_steps=["type sentinel", "[boundary] dark-mode config change"],
    )

    validate_verdict(verdict)
    assert verdict["outcome"] == "pass"


def test_fixtures_encode_the_matched_pair() -> None:
    # guards the fixtures: the defect loses the sentinel after the event, the
    # control keeps it — otherwise the fail/pass above would be vacuous.
    sentinel = "zzsentinelqx"
    assert sentinel in _load("defect-before-layout.json")
    assert sentinel not in _load("defect-after-layout.json")
    assert sentinel in _load("control-before-layout.json")
    assert sentinel in _load("control-after-layout.json")
