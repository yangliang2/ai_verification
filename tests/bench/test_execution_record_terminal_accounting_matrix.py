"""Integrity contract for Issue #171 ExecutionRecord branch disposition."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_RUN_RECORD = _ROOT / "docs/runs/2026-08-16-issue-171-execution-record-terminal-accounting"
_CONTRACT_TEST = "tests/runner/test_execution_record_terminal_accounting.py"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _collected_nodeids() -> set[str]:
    """Collect the contract module so an evidence map cannot name stale tests."""
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


def test_execution_record_missing_branches_have_one_collected_contract_case() -> None:
    """Every baseline gap maps exactly once to a real hermetic contract case."""
    branch_map_path = _RUN_RECORD / "branch-map.json"
    branch_map = _json(branch_map_path)
    baseline = _json(
        branch_map_path.parent / branch_map["baseline"]["coverage_artifact"]
    )
    source_path = branch_map["baseline"]["source_path"]
    expected = {
        tuple(arc)
        for arc in baseline["files"][source_path]["missing_branches"]
    }
    mapped: list[tuple[int, int]] = []
    nodeids: list[str] = []

    assert branch_map["issue"] == 171
    assert branch_map["primary_quality_contract"] == "fail-closed accountability"
    assert branch_map["baseline"]["missing_branch_count"] == len(expected)
    for case in branch_map["contract_cases"]:
        nodeids.append(case["nodeid"])
        mapped.extend(tuple(arc) for arc in case["baseline_missing_branch_arcs"])

    assert len(mapped) == len(set(mapped))
    assert set(mapped) == expected
    assert set(nodeids) <= _collected_nodeids()
