"""Integrity contract for the Issue #165 coverage audit projection."""

from __future__ import annotations

import json
from pathlib import Path


_RUN_RECORD = (
    Path(__file__).resolve().parents[2]
    / "docs/runs/2026-08-13-issue-165-risk-weighted-white-box-coverage-audit"
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_p0_p1_branch_actions_cover_every_missing_coverage_arc() -> None:
    """Map every P0/P1 unmeasured arc to one concrete follow-up action."""
    risk_map = _json(_RUN_RECORD / "risk-map.json")
    coverage = _json(_RUN_RECORD / risk_map["coverage_artifact"])

    assert risk_map["primary_quality_contract"]["name"] == "fail-closed accountability"
    assert "Verification Agent" in risk_map["primary_quality_contract"]["definition"]

    expected_arcs: set[tuple[str, int, int]] = set()
    assigned_arcs: set[tuple[str, int, int, str]] = set()
    cli_is_p0_external_side_effect_boundary = False

    for surface in risk_map["surfaces"]:
        priority = surface["priority"]
        if priority not in {"P0", "P1"}:
            continue

        assert surface["quality_contract"] == "fail-closed accountability"
        assert surface["branch_disposition"] == "all_missing_branch_arcs"
        assert surface["next_action"].strip()
        if "src/aiverify/runner/cli.py" in surface["source_paths"]:
            cli_is_p0_external_side_effect_boundary = (
                priority == "P0"
                and "external-side-effect" in surface["trust_boundary"]
            )
        for source_path in surface["source_paths"]:
            file_coverage = coverage["files"][source_path]
            measurement = risk_map["coverage_measurements"][source_path]
            summary = file_coverage["summary"]
            assert measurement == {
                "covered_branches": summary["covered_branches"],
                "num_branches": summary["num_branches"],
                "missing_branches": summary["missing_branches"],
                "covered_branch_percentage": summary["percent_branches_covered"],
                "combined_coverage_percentage": summary["percent_covered"],
            }
            for from_line, to_line in file_coverage["missing_branches"]:
                expected_arcs.add((source_path, from_line, to_line))
                assigned_arcs.add((source_path, from_line, to_line, surface["id"]))

    assert cli_is_p0_external_side_effect_boundary
    assert expected_arcs
    assert len(assigned_arcs) == len(expected_arcs)
    assert {
        (source_path, from_line, to_line)
        for source_path, from_line, to_line, _ in assigned_arcs
    } == expected_arcs


def test_verification_totals_are_derived_from_coverage_artifact() -> None:
    """Keep the durable high-level summary auditable against coverage.py JSON."""
    verification = _json(_RUN_RECORD / "verification.json")
    coverage = _json(_RUN_RECORD / "artifacts/coverage.json")
    report = verification["measurement"]["report"]
    totals = coverage["totals"]

    for key in (
        "covered_lines",
        "num_statements",
        "missing_lines",
        "covered_branches",
        "num_branches",
        "missing_branches",
        "num_partial_branches",
        "percent_covered",
        "percent_statements_covered",
        "percent_branches_covered",
    ):
        verification_key = {
            "percent_covered": "percent_total",
            "percent_statements_covered": "percent_statements",
            "percent_branches_covered": "percent_branches",
            "num_partial_branches": "partial_branches",
        }.get(key, key)
        assert report[verification_key] == totals[key]
