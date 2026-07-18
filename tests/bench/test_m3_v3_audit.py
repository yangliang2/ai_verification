"""Strict final-audit contract for the immutable M3 v3 slice."""

from __future__ import annotations

from aiverify.bench.m3_audit import _build_criteria
from aiverify.bench.m3_reliability import ReliabilitySummary


def _summary(*, accountable: int) -> ReliabilitySummary:
    return ReliabilitySummary(
        planned_lanes=30,
        first_attempt_accountable=accountable,
        eventual_accountable=accountable,
        retry_count=30 - accountable,
        control_outcomes={"passed_control": 15 if accountable == 30 else 14},
        defect_outcomes={"caught": 15},
        failure_classes={} if accountable == 30 else {"preflight_environment": 1},
        total_seconds=1.0,
        judge_seconds=0.0,
        operational_interventions=0,
    )


def _lane_results(*, accountable: int) -> list[dict]:
    rows = [
        {"role": "baseline", "eventual_accountable": index < accountable}
        for index in range(15)
    ]
    rows.extend(
        {"role": "defect", "eventual_accountable": True} for _ in range(15)
    )
    return rows


def test_v3_gate_rejects_the_v2_29_of_30_accountability_threshold() -> None:
    criteria = _build_criteria(
        _summary(accountable=29),
        lane_results=_lane_results(accountable=14),
        schema_version=3,
        complete_provenance_attempts=29,
    )

    assert criteria["eventual_accountability"] == {
        "status": "failed",
        "actual": 29,
        "required_minimum": 30,
    }
    assert criteria["m3_overall"] == {"status": "failed"}
    assert criteria["complete_execution_provenance"] == {
        "status": "failed",
        "actual": 29,
        "required": 30,
    }


def test_v3_gate_requires_all_15_controls_and_all_15_defects() -> None:
    criteria = _build_criteria(
        _summary(accountable=30),
        lane_results=_lane_results(accountable=15),
        schema_version=3,
        complete_provenance_attempts=30,
    )

    assert criteria["eventual_accountability"]["status"] == "passed"
    assert criteria["zero_accountable_baseline_false_positives"]["actual"] == 0
    assert criteria["passed_baseline_controls"] == {
        "status": "passed",
        "actual": 15,
        "required": 15,
    }
    assert criteria["accountable_defect_consistency"] == {
        "status": "passed",
        "actual": 15,
        "required": 15,
    }
    assert criteria["m3_overall"] == {"status": "passed"}
