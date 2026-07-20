"""Fail-closed oracle for the bounded issue #72 compatibility matrix."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CompatibilityCell:
    id: str
    locale: str
    direction: str
    orientation: str
    form_factor: str
    title: str


def load_contract(path: str | Path) -> tuple[list[CompatibilityCell], str]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    cells = [CompatibilityCell(**cell) for cell in document["cells"]]
    if len({cell.id for cell in cells}) != len(cells):
        raise ValueError("compatibility contract contains duplicate cell ids")
    return cells, str(document["sentinel"])


def judge_cell(
    *, cell: CompatibilityCell, sentinel: str, layout: list[dict[str, Any]]
) -> dict[str, Any]:
    by_id = {
        str(node.get("resource-id")): node
        for node in layout
        if isinstance(node, dict) and node.get("resource-id")
    }
    required = {
        "compatibility_title", "compatibility_start_anchor",
        "compatibility_end_anchor", "compatibility_state",
        "compatibility_direction", "compatibility_configuration",
    }
    missing = sorted(required - by_id.keys())
    if missing:
        return _result(cell, "non_accountable", "missing_layout_evidence", missing=missing)
    if any(by_id[name].get("off-screen") is True for name in required):
        return _result(cell, "locally_rejected", "clipped_or_off_screen")
    if str(by_id["compatibility_title"].get("text")) != cell.title:
        return _result(cell, "locally_rejected", "wrong_or_missing_resource")
    if str(by_id["compatibility_state"].get("text")) != sentinel:
        return _result(cell, "locally_rejected", "state_reset")
    expected_direction = f"DIRECTION_{cell.direction.upper()}"
    if str(by_id["compatibility_direction"].get("text")) != expected_direction:
        return _result(cell, "locally_rejected", "semantic_direction_drift")
    config = str(by_id["compatibility_configuration"].get("text", ""))
    fields = dict(re.findall(r"(?:^|;)([^=;]+)=([^;]+)", config))
    try:
        width_dp = int(fields["width_dp"])
        smallest_width_dp = int(fields["smallest_width_dp"])
    except (KeyError, ValueError):
        return _result(cell, "non_accountable", "configuration_unobservable")
    if not fields.get("locale", "").lower().startswith(cell.locale.lower()):
        return _result(cell, "non_accountable", "locale_postcondition_mismatch")
    if fields.get("orientation") != cell.orientation:
        return _result(cell, "non_accountable", "orientation_postcondition_mismatch")
    if cell.form_factor == "tablet" and smallest_width_dp < 600:
        return _result(cell, "non_accountable", "tablet_profile_not_effective")
    if cell.form_factor == "phone" and smallest_width_dp >= 600:
        return _result(cell, "non_accountable", "phone_profile_not_effective")
    try:
        start_x = _center_x(by_id["compatibility_start_anchor"])
        end_x = _center_x(by_id["compatibility_end_anchor"])
    except ValueError:
        return _result(cell, "non_accountable", "anchor_geometry_unobservable")
    correct_order = start_x > end_x if cell.direction == "rtl" else start_x < end_x
    if not correct_order or start_x == end_x:
        return _result(cell, "locally_rejected", "rtl_relative_order_violation")
    return _result(
        cell,
        "locally_supported",
        "compatibility_invariants_satisfied",
        width_dp=width_dp,
        smallest_width_dp=smallest_width_dp,
        start_x=start_x,
        end_x=end_x,
    )


def judge_matrix(
    *, contract_path: str | Path, layouts: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    cells, sentinel = load_contract(contract_path)
    expected_ids = {cell.id for cell in cells}
    extra = sorted(set(layouts) - expected_ids)
    results = []
    for cell in cells:
        layout = layouts.get(cell.id)
        if layout is None:
            results.append(_result(cell, "non_accountable", "cell_not_executed"))
        else:
            results.append(judge_cell(cell=cell, sentinel=sentinel, layout=layout))
    accountable = not extra and all(
        result["conclusion"] != "non_accountable" for result in results
    )
    if extra:
        conclusion = "non_accountable"
        reason = "undeclared_matrix_cells"
    elif not accountable:
        conclusion = "non_accountable"
        reason = "matrix_incomplete_or_untrusted"
    elif any(result["conclusion"] == "locally_rejected" for result in results):
        conclusion = "locally_rejected"
        reason = "one_or_more_cells_rejected"
    else:
        conclusion = "locally_supported"
        reason = "all_preregistered_cells_supported"
    return {
        "schema_version": 1,
        "conclusion": conclusion,
        "reason": reason,
        "accountable": accountable,
        "cells": results,
        "undeclared_cells": extra,
    }


def judge_matrix_runs(
    *, contract_path: str | Path, lane_root: str | Path
) -> dict[str, Any]:
    """Judge completed runner lanes, including event and execution accountability."""
    cells, _ = load_contract(contract_path)
    root = Path(lane_root)
    layouts: dict[str, list[dict[str, Any]]] = {}
    lane_errors: dict[str, str] = {}
    for cell in cells:
        lane = root / cell.id
        try:
            record = json.loads((lane / "execution-record.json").read_text(encoding="utf-8"))
            execution = record.get("execution", {})
            if (
                record.get("lifecycle_state") != "completed"
                or execution.get("status") != "completed"
                or execution.get("accounting_eligible") is not True
            ):
                raise ValueError("ExecutionRecord is not completed and accountable")
            events = [
                json.loads(
                    (lane / "artifacts" / f"system-event-{index}" / "event.json")
                    .read_text(encoding="utf-8")
                )
                for index in range(3)
            ]
            if [event.get("event") for event in events] != [
                "locale_change", "rotate", "locale_change"
            ] or any(event.get("status") != "passed" for event in events):
                raise ValueError("locale/rotation/cleanup event lineage is incomplete")
            locale_evidence = events[0].get("evidence", {})
            cleanup_evidence = events[2].get("evidence", {})
            if locale_evidence.get("observed", {}).get("locales") != cell.locale:
                raise ValueError("effective cell locale contradicts contract")
            if cleanup_evidence.get("observed", {}).get("locales") != "en-US":
                raise ValueError("locale cleanup postcondition is missing")
            layouts[cell.id] = json.loads(
                (lane / "artifacts" / "after-event-1" / "layout.json")
                .read_text(encoding="utf-8")
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            lane_errors[cell.id] = f"{type(error).__name__}: {error}"
    result = judge_matrix(contract_path=contract_path, layouts=layouts)
    if lane_errors:
        result["conclusion"] = "non_accountable"
        result["reason"] = "runner_lane_evidence_invalid"
        result["accountable"] = False
    result["lane_errors"] = lane_errors
    return result


def _center_x(node: dict[str, Any]) -> int:
    match = re.fullmatch(r"\[(-?\d+),(-?\d+)\]", str(node.get("center", "")))
    if match is None:
        raise ValueError("invalid center")
    return int(match.group(1))


def _result(cell: CompatibilityCell, conclusion: str, reason: str, **details: Any) -> dict[str, Any]:
    return {
        "cell_id": cell.id,
        "conclusion": conclusion,
        "reason": reason,
        "accountable": conclusion != "non_accountable",
        "details": details,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True)
    parser.add_argument("--layouts", required=True, type=Path)
    parser.add_argument("--runner-lanes", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.runner_lanes:
        result = judge_matrix_runs(
            contract_path=args.contract, lane_root=args.layouts
        )
    else:
        layouts = {
            path.stem: json.loads(path.read_text(encoding="utf-8"))
            for path in args.layouts.glob("*.json")
        }
        result = judge_matrix(contract_path=args.contract, layouts=layouts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if result["conclusion"] == "locally_supported" else 1


if __name__ == "__main__":
    raise SystemExit(main())
