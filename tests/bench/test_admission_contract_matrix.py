"""Integrity contract for Issue #167 admission rejection evidence."""

from __future__ import annotations

import json
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_RUN_RECORD = (
    _ROOT / "docs/runs/2026-08-15-issue-167-admission-rejection-contracts"
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_issue_165_missing_admission_arcs_have_one_contract_test_group() -> None:
    """Every audited gap has a readable fail-closed test disposition."""
    branch_map_path = _RUN_RECORD / "branch-map.json"
    branch_map = _json(branch_map_path)
    baseline = _json(
        (branch_map_path.parent / branch_map["baseline"]["coverage_artifact"]).resolve()
    )
    source_path = branch_map["baseline"]["source_path"]
    expected = {
        tuple(arc)
        for arc in baseline["files"][source_path]["missing_branches"]
    }
    mapped: list[tuple[int, int]] = []

    assert branch_map["primary_quality_contract"] == "fail-closed accountability"
    assert branch_map["baseline"]["issue"] == 165
    assert branch_map["baseline"]["missing_branch_count"] == len(expected)
    for group in branch_map["test_groups"]:
        assert group["nodeids"]
        mapped.extend(tuple(arc) for arc in group["baseline_missing_branch_arcs"])

    assert len(mapped) == len(set(mapped))
    assert set(mapped) == expected
