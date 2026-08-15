"""Integrity contract for Issue #169 Runner CLI phase-ordering evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_RUN_RECORD = _ROOT / "docs/runs/2026-08-15-issue-169-runner-cli-phase-ordering"
_CONTRACT_TEST = "tests/runner/test_cli_phase_ordering.py"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _collected_nodeids() -> set[str]:
    """Collect the mapped contract module in a child pytest process."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "--collect-only",
            "-q",
            _CONTRACT_TEST,
        ],
        cwd=_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return {
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().startswith(f"{_CONTRACT_TEST}::")
    }


def test_issue_165_missing_runner_cli_arcs_have_one_contract_test_group() -> None:
    """Every audited Runner CLI gap has one existing, named contract test."""
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
    nodeids: list[str] = []

    assert branch_map["primary_quality_contract"] == "fail-closed accountability"
    assert branch_map["baseline"]["issue"] == 165
    assert branch_map["baseline"]["missing_branch_count"] == len(expected)
    for group in branch_map["test_groups"]:
        assert group["nodeids"]
        nodeids.extend(group["nodeids"])
        mapped.extend(tuple(arc) for arc in group["baseline_missing_branch_arcs"])

    assert len(mapped) == len(set(mapped))
    assert set(mapped) == expected
    assert set(nodeids) <= _collected_nodeids()
