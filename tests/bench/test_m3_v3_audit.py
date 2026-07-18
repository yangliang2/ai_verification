"""Strict final-audit contract for the immutable M3 v3 slice."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from aiverify.bench.m3_audit import (
    _build_criteria,
    _validate_lane_apk_identity,
    _validate_lane_execution_identity,
    audited_report_to_dict,
    build_audited_report,
    render_audited_markdown,
)
from aiverify.bench.m3_reliability import ReliabilitySummary, load_manifest
from aiverify.bench.run_record_checksums import verify_manifest


_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = _ROOT / "bench" / "goldset" / "m3-reliability-slice-v3.yaml"
_FINAL_RUN = (
    _ROOT / "docs" / "runs" / "2026-07-17-m3-v3-final-audited-comparison"
)


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
        formal_attempts=30,
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
        formal_attempts=30,
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


def test_v3_provenance_gate_counts_attempts_including_retries() -> None:
    criteria = _build_criteria(
        _summary(accountable=30),
        lane_results=_lane_results(accountable=15),
        schema_version=3,
        complete_provenance_attempts=30,
        formal_attempts=31,
    )

    assert criteria["complete_execution_provenance"] == {
        "status": "failed",
        "actual": 30,
        "required": 31,
    }
    assert criteria["m3_overall"] == {"status": "failed"}


def test_v3_lane_role_is_bound_to_the_deployed_apk_hash() -> None:
    provenance = {
        "deployment": {
            "installed_artifacts": [{"sha256": "defect-hash"}],
        }
    }
    package_environment = {
        "application": {
            "baseline_apk": {"sha256": "baseline-hash"},
            "defect_apk": {"sha256": "defect-hash"},
        }
    }

    try:
        _validate_lane_apk_identity(
            provenance,
            role="baseline",
            package_environment=package_environment,
            lane_id="fixture-baseline-1",
        )
    except ValueError as error:
        assert "baseline APK" in str(error)
    else:
        raise AssertionError("baseline lane accepted the defect APK")


def test_v3_attempt_provenance_is_bound_to_frozen_execution_identity(
    tmp_path: Path,
) -> None:
    attempt_dir = (
        _ROOT
        / "docs/runs/2026-07-17-m3-v3-anr-reliability/lanes"
        / "v3-anr-baseline-1/attempt-1"
    )
    provenance = json.loads(
        (attempt_dir / "execution-provenance.json").read_text(encoding="utf-8")
    )
    package_environment = json.loads(
        (
            _ROOT
            / "docs/runs/2026-07-17-m3-v3-anr-reliability/environment.json"
        ).read_text(encoding="utf-8")
    )

    _validate_lane_execution_identity(
        provenance,
        role="baseline",
        package_environment=package_environment,
        lane_id="v3-anr-baseline-1",
        attempt_dir=attempt_dir,
    )

    for field, value, message in (
        (("run_spec", "consumed_sha256"), "wrong", "Run Spec"),
        (("host", "commit"), "wrong", "host identity"),
        (("tools", "codex_cli", "version"), "codex-cli 0.0.0", "Codex CLI"),
    ):
        contradicted = deepcopy(provenance)
        target = contradicted
        for key in field[:-1]:
            target = target[key]
        target[field[-1]] = value
        with pytest.raises(ValueError, match=message):
            _validate_lane_execution_identity(
                contradicted,
                role="baseline",
                package_environment=package_environment,
                lane_id="v3-anr-baseline-1",
                attempt_dir=attempt_dir,
            )

    invocation_ref = provenance["roles"]["journey_driver"]["invocations"][0]
    identity = json.loads(
        (attempt_dir / invocation_ref["path"]).read_text(encoding="utf-8")
    )
    identity["effective_model"] = "wrong-model"
    (tmp_path / "identity.json").write_text(json.dumps(identity), encoding="utf-8")
    contradicted = deepcopy(provenance)
    contradicted["roles"]["journey_driver"]["invocations"][0]["path"] = (
        "identity.json"
    )
    with pytest.raises(ValueError, match="journey_driver effective identity"):
        _validate_lane_execution_identity(
            contradicted,
            role="baseline",
            package_environment=package_environment,
            lane_id="v3-anr-baseline-1",
            attempt_dir=tmp_path,
        )


def test_committed_failed_v3_audit_is_derived_from_all_30_fresh_lanes() -> None:
    report = build_audited_report(
        load_manifest(_MANIFEST, repo_root=_ROOT),
        environment_path=_FINAL_RUN / "environment.json",
    )

    assert report.inventory["planned_lanes"] == 30
    assert report.inventory["formal_attempts"] == 54
    assert report.summary.eventual_accountable == 6
    assert report.summary.control_outcomes == {"passed_control": 3}
    assert report.summary.defect_outcomes == {"caught": 3}
    assert report.summary.failure_classes == {"execution_identity": 48}
    assert report.criteria["m3_overall"] == {"status": "failed"}
    assert report.criteria["complete_execution_provenance"] == {
        "status": "failed",
        "actual": 6,
        "required": 54,
    }
    assert len(report.lane_results) == 30
    assert sum(len(row["attempt_lineage"]) for row in report.lane_results) == 54
    assert {
        attempt["execution_provenance_status"]
        for row in report.lane_results
        for attempt in row["attempt_lineage"]
    } == {"missing", "verified"}
    assert report.comparison is not None
    assert report.comparison["prior_comparison"]["historical"]["summary"][
        "eventual_accountable"
    ] == 27
    assert report.comparison["historical"]["summary"][
        "eventual_accountable"
    ] == 29

    assert json.loads((_FINAL_RUN / "summary.json").read_text(encoding="utf-8")) == (
        audited_report_to_dict(report)
    )
    assert (_FINAL_RUN / "report.md").read_text(
        encoding="utf-8"
    ) == render_audited_markdown(report)
    for package in {
        lane.evidence_dir.parent.parent
        for lane in load_manifest(_MANIFEST, repo_root=_ROOT).lanes
    }:
        assert verify_manifest(package) == []
