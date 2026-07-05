"""Regression test for the Wikipedia lifecycle-04 recreation-crash Goldset seed (#9, M1 seed 2).

Freezes the real on-device crash logcat captured in
docs/runs/2026-07-05-wikipedia-lifecycle-04-recreation-crash/ as a fixture, so the
"verifier catches a config-change recreation crash via L1" result stays green
without an emulator.

Complements the config-change-01 seed (L2 / state_loss): same dark-mode trigger,
different defect, caught by the L1 crash oracle (crash_stability).
"""

from __future__ import annotations

from pathlib import Path

from aiverify.agent.oracle import L1Oracle
from aiverify.agent.oracle.schema import validate_verdict
from aiverify.runner.run_spec import load_run_spec

_GOLDSET = Path(__file__).resolve().parents[2] / "bench" / "goldset"
_RUN_SPEC = _GOLDSET / "run-specs" / "wikipedia-lifecycle-04-recreation-crash.yaml"
_FIXTURES = _GOLDSET / "fixtures" / "wikipedia-lifecycle-04-recreation-crash"

_CLEAN_LOGCAT = (
    "07-05 18:10:00.000  100  100 I MainActivity: onCreate\n"
    "07-05 18:10:00.100  100  100 D SearchFragment: onCreateView\n"
)


def test_run_spec_parses_with_dark_mode_and_crash_patch() -> None:
    spec = load_run_spec(_RUN_SPEC)

    assert spec.scenario.id == "wikipedia-lifecycle-04-recreation-crash"
    assert spec.scenario.system_events[0].event == "dark_mode"
    assert spec.diff is not None and spec.diff.name.endswith(
        "wikipedia-lifecycle-04-recreation-crash.patch"
    )


def test_l1_flags_the_recreation_crash() -> None:
    crash_logcat = (_FIXTURES / "crash-logcat.txt").read_text(encoding="utf-8")

    verdict = L1Oracle().judge(crash_logcat, trigger_steps=["[boundary] dark-mode recreation"])

    validate_verdict(verdict)
    assert verdict["outcome"] == "fail"
    assert verdict["defect_class_hypothesis"] == "crash_stability"
    refs = " ".join(e["ref"] for e in verdict["evidence"])
    assert "FATAL EXCEPTION" in refs


def test_baseline_clean_logcat_is_inconclusive() -> None:
    # matched behavior: with no injected defect there is no crash under the same event,
    # so L1 abstains (it never has authority to declare pass).
    verdict = L1Oracle().judge(_CLEAN_LOGCAT)

    validate_verdict(verdict)
    assert verdict["outcome"] == "inconclusive"


def test_crash_fixture_actually_contains_the_injected_crash() -> None:
    crash_logcat = (_FIXTURES / "crash-logcat.txt").read_text(encoding="utf-8")
    assert "UninitializedPropertyAccessException" in crash_logcat
    assert "configChangeToken" in crash_logcat
