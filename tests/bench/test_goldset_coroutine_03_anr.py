"""Regression test for the Wikipedia coroutine-concurrency-03 ANR Goldset seed (#9, M1 seed 3).

Freezes the real on-device ANR logcat captured in
docs/runs/2026-07-05-wikipedia-coroutine-concurrency-03-anr/ as a fixture, so the
"verifier catches a main-thread-block ANR via L1" result stays green without an emulator.

This seed is event-less: the ANR is triggered by typing (a user action), not a system
event, so L2 is not applicable and L1 must catch the ANR from the segment logcat.
"""

from __future__ import annotations

from pathlib import Path

from aiverify.agent.oracle import L1Oracle
from aiverify.agent.oracle.schema import validate_verdict
from aiverify.runner.run_spec import load_run_spec

_GOLDSET = Path(__file__).resolve().parents[2] / "bench" / "goldset"
_RUN_SPEC = _GOLDSET / "run-specs" / "wikipedia-coroutine-concurrency-03-main-thread-anr.yaml"
_FIXTURES = _GOLDSET / "fixtures" / "wikipedia-coroutine-concurrency-03-anr"


def test_run_spec_parses_as_event_less_scenario() -> None:
    spec = load_run_spec(_RUN_SPEC)

    assert spec.scenario.id == "wikipedia-coroutine-concurrency-03-main-thread-anr"
    assert spec.scenario.system_events == []
    assert spec.diff is not None and spec.diff.name.endswith(
        "wikipedia-coroutine-concurrency-03-main-thread-anr.patch"
    )


def test_l1_flags_the_anr() -> None:
    anr_logcat = (_FIXTURES / "anr-logcat.txt").read_text(encoding="utf-8")

    verdict = L1Oracle().judge(anr_logcat, trigger_steps=["type query (blocks main thread)"])

    validate_verdict(verdict)
    assert verdict["outcome"] == "fail"
    assert verdict["defect_class_hypothesis"] == "crash_stability"
    refs = " ".join(e["ref"] for e in verdict["evidence"])
    assert "ANR in" in refs


def test_anr_fixture_is_the_injected_block() -> None:
    anr_logcat = (_FIXTURES / "anr-logcat.txt").read_text(encoding="utf-8")
    assert "ANR in org.wikipedia.dev" in anr_logcat
    assert "SearchActivity" in anr_logcat
