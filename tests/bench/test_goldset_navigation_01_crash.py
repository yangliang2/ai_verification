"""Regression test for the Wikipedia navigation-01 double-open crash Goldset seed (#9, M1 seed 4).

Freezes the real on-device "Fragment already added" crash logcat captured in
docs/runs/2026-07-05-wikipedia-navigation-01-double-open-crash/ as a fixture, so the
"verifier catches a double-open navigation crash via L1" result stays green without an
emulator. Event-less: the crash is triggered by tapping the More nav tab.
"""

from __future__ import annotations

from pathlib import Path

from aiverify.agent.oracle import L1Oracle
from aiverify.agent.oracle.schema import validate_verdict
from aiverify.runner.run_spec import load_run_spec

_GOLDSET = Path(__file__).resolve().parents[2] / "bench" / "goldset"
_RUN_SPEC = _GOLDSET / "run-specs" / "wikipedia-navigation-01-double-open-crash.yaml"
_FIXTURES = _GOLDSET / "fixtures" / "wikipedia-navigation-01-double-open-crash"


def test_run_spec_parses_event_less_navigation_seed() -> None:
    spec = load_run_spec(_RUN_SPEC)

    assert spec.scenario.id == "wikipedia-navigation-01-double-open-crash"
    assert spec.scenario.system_events == []
    assert spec.diff is not None and spec.diff.name.endswith(
        "wikipedia-navigation-01-double-open-crash.patch"
    )


def test_l1_flags_the_double_open_crash() -> None:
    crash_logcat = (_FIXTURES / "crash-logcat.txt").read_text(encoding="utf-8")

    verdict = L1Oracle().judge(crash_logcat, trigger_steps=["tap More nav tab"])

    validate_verdict(verdict)
    assert verdict["outcome"] == "fail"
    assert verdict["defect_class_hypothesis"] == "crash_stability"
    refs = " ".join(e["ref"] for e in verdict["evidence"])
    assert "FATAL EXCEPTION" in refs


def test_crash_fixture_is_fragment_already_added() -> None:
    crash_logcat = (_FIXTURES / "crash-logcat.txt").read_text(encoding="utf-8")
    assert "Fragment already added" in crash_logcat
    assert "MenuNavTabDialog" in crash_logcat
