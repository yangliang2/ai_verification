"""Final audited comparison tests for the fresh M3 v2 reliability slice."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

import aiverify.bench.m3_audit as m3_audit
from aiverify.bench.m3_audit import (
    audited_report_to_dict,
    build_audited_report,
    render_audited_markdown,
)
from aiverify.bench.m3_reliability import load_manifest
from aiverify.bench.run_record_checksums import verify_manifest


_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = _ROOT / "bench" / "goldset" / "m3-reliability-slice-v2.yaml"
_FINAL_RUN = (
    _ROOT / "docs" / "runs" / "2026-07-16-m3-v2-final-audited-comparison"
)


def _report():
    return build_audited_report(
        load_manifest(_MANIFEST, repo_root=_ROOT),
        environment_path=_FINAL_RUN / "environment.json",
    )


def test_v2_final_audit_derives_complete_pass_without_combining_baselines() -> None:
    report = _report()

    assert report.schema_version == 2
    assert report.inventory == {
        "selected_seeds": 5,
        "lane_roles": 2,
        "repetitions_per_role": 3,
        "planned_lanes": 30,
        "formal_attempts": 31,
        "evidence_packages": 5,
    }
    assert report.summary.first_attempt_accountable == 29
    assert report.summary.eventual_accountable == 29
    assert report.summary.retry_count == 1
    assert report.summary.control_outcomes == {"passed_control": 14}
    assert report.summary.defect_outcomes == {"caught": 15}
    assert report.summary.failure_classes == {"preflight_environment": 2}
    assert report.summary.total_seconds == 3640.533
    assert report.summary.judge_seconds == 165.102
    assert report.summary.operational_interventions == 1
    assert report.criteria["m3_overall"] == {"status": "passed"}
    assert report.oracle_breakdown == {
        "L1": {
            "planned": 12,
            "eventual_accountable": 11,
            "passed_controls": 5,
            "caught_defects": 6,
            "non_accountable": 1,
        },
        "L2": {
            "planned": 12,
            "eventual_accountable": 12,
            "passed_controls": 6,
            "caught_defects": 6,
            "non_accountable": 0,
        },
        "L3": {
            "planned": 6,
            "eventual_accountable": 6,
            "passed_controls": 3,
            "caught_defects": 3,
            "non_accountable": 0,
        },
    }

    comparison = report.comparison
    assert comparison is not None
    assert comparison["denominators_combined"] is False
    assert comparison["selective_lane_replacement"] is False
    assert comparison["historical"]["slice_id"] == (
        "m3-verification-agent-reliability"
    )
    assert comparison["historical"]["summary"]["planned_lanes"] == 30
    assert comparison["historical"]["summary"]["eventual_accountable"] == 27
    assert comparison["historical"]["criteria"]["m3_overall"] == {
        "status": "failed"
    }
    assert comparison["rebaseline"]["summary"]["planned_lanes"] == 30
    assert comparison["rebaseline"]["summary"]["eventual_accountable"] == 29
    assert comparison["rebaseline"]["criteria"]["m3_overall"] == {
        "status": "passed"
    }
    assert comparison["descriptive_delta"] == {
        "first_attempt_accountable": 5,
        "eventual_accountable": 2,
        "retry_count": -5,
        "total_seconds": -964.805,
        "judge_seconds": 67.833,
        "operational_interventions": -8,
    }
    assert "combined_summary" not in comparison


def test_v2_final_audit_retains_every_attempt_and_mixed_package_identity() -> None:
    report = _report()

    assert len(report.lane_results) == 30
    assert sum(len(row["attempt_lineage"]) for row in report.lane_results) == 31
    assert all(
        row["final_status"] in {"accountable", "non_accountable"}
        for row in report.lane_results
    )
    assert all(
        attempt["checksum_status"] == "verified"
        for row in report.lane_results
        for attempt in row["attempt_lineage"]
    )
    exhausted = next(
        row for row in report.lane_results if row["lane_id"] == "v2-anr-baseline-3"
    )
    assert exhausted["final_status"] == "non_accountable"
    assert len(exhausted["attempt_lineage"]) == 2

    identities = report.execution_identity["package_environments"]
    assert len(identities) == 5
    assert {row["device"]["api_level"] for row in identities} == {35, 36}
    assert {row["device"]["avd"] for row in identities} == {
        "aiverify_api35",
        "medium_phone",
    }
    assert report.execution_identity["identity_coverage"] == {
        "package_environment": "5/5",
        "device_serial_crosscheck": "31/31",
        "host_path_crosscheck": "31/31",
        "run_spec_command_crosscheck": "31/31",
        "run_spec_sha256_retained": "3/5",
        "manifest_sha256_retained": "3/5",
        "host_commit_retained": "3/5",
        "backend_version_retained": "4/5",
        "model_identity_retained": "1/5",
        "model_override_crosscheck": "6/6",
    }
    assert sum(row["lane_count"] for row in identities) == 30
    assert sum(row["formal_attempts"] for row in identities) == 31
    assert [row["model_identity"]["status"] for row in identities].count(
        "retained"
    ) == 1


def test_committed_v2_audit_documents_are_generated_from_one_model() -> None:
    report = _report()

    assert verify_manifest(_FINAL_RUN) == []
    assert json.loads((_FINAL_RUN / "summary.json").read_text(encoding="utf-8")) == (
        audited_report_to_dict(report)
    )
    markdown = render_audited_markdown(report)
    assert (_FINAL_RUN / "report.md").read_text(encoding="utf-8") == markdown
    assert "Original (distinct 30)" in markdown
    assert "V2 (distinct 30)" in markdown
    assert "27 / 30" in markdown
    assert "29 / 30" in markdown
    assert "API 35" in markdown and "API 36" in markdown
    assert "Model identity retained | 1/5" in markdown
    assert "30 + 30" in markdown


@pytest.mark.parametrize(
    ("criterion", "reason", "comparison_row"),
    [
        (
            "eventual_accountability",
            "eventual accountability",
            "| Eventual accountable | 27 / 30 | 28 / 30 |",
        ),
        (
            "zero_accountable_baseline_false_positives",
            "accountable baseline false positives",
            "| Accountable baseline false positives | 0 | 1 |",
        ),
        (
            "accountable_defect_consistency",
            "accountable defect consistency",
            "| Accountable defects caught | 12 / 12 | 14 / 15 |",
        ),
    ],
)
def test_v2_report_keeps_each_failed_criterion_independently_visible(
    criterion: str, reason: str, comparison_row: str
) -> None:
    report = _report()
    criteria = {key: dict(value) for key, value in report.criteria.items()}
    criteria["m3_overall"] = {"status": "failed"}
    summary = report.summary
    if criterion == "eventual_accountability":
        criteria[criterion]["status"] = "failed"
        criteria[criterion]["actual"] = 28
        summary = replace(
            summary,
            first_attempt_accountable=28,
            eventual_accountable=28,
        )
    elif criterion == "zero_accountable_baseline_false_positives":
        criteria[criterion]["status"] = "failed"
        criteria[criterion]["actual"] = 1
        summary = replace(
            summary,
            control_outcomes={"false_positive": 1, "passed_control": 13},
        )
    else:
        criteria[criterion]["status"] = "failed"
        criteria[criterion]["actual"] = 14
        summary = replace(
            summary,
            defect_outcomes={"caught": 14, "missed": 1},
        )

    markdown = render_audited_markdown(
        replace(report, summary=summary, criteria=criteria)
    )

    assert "M3 overall | **FAILED**" in markdown
    assert "| M3 decision | **FAILED** | **FAILED** |" in markdown
    assert comparison_row in markdown
    assert reason in markdown


def test_v2_final_audit_fails_closed_on_historical_record_checksum_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verified = verify_manifest

    def fail_historical(path: Path) -> list[str]:
        if Path(path).name == "2026-07-13-m3-final-reliability-baseline":
            return ["checksum mismatch: historical summary"]
        return verified(path)

    monkeypatch.setattr(m3_audit, "verify_manifest", fail_historical)

    with pytest.raises(ValueError, match="historical comparison record"):
        _report()


def test_v2_final_audit_fails_closed_on_package_device_identity_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_json = m3_audit._load_json

    def mismatched(path: Path, *, label: str) -> dict:
        value = load_json(path, label=label)
        if (
            Path(path).name == "environment.json"
            and Path(path).parent.name == "2026-07-15-m3-v2-query-duplication-reliability"
        ):
            value = json.loads(json.dumps(value))
            value["device"]["serial"] = "different-device"
        return value

    monkeypatch.setattr(m3_audit, "_load_json", mismatched)

    with pytest.raises(ValueError, match="package environment device"):
        _report()


def test_v2_final_audit_fails_closed_on_model_override_contradiction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_verified_attempt = m3_audit.load_verified_attempt

    def overridden(*args, **kwargs):
        metadata, verdict = load_verified_attempt(*args, **kwargs)
        lane = kwargs["lane"]
        if lane.lane_id == "v2-search-card-baseline-1":
            metadata = json.loads(json.dumps(metadata))
            metadata["runner_command"].extend(["--model", "different-model"])
        return metadata, verdict

    monkeypatch.setattr(m3_audit, "load_verified_attempt", overridden)

    with pytest.raises(ValueError, match="no-override model identity"):
        _report()
