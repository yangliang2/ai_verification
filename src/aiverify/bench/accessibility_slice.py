"""Fail-closed oracle for the bounded issue #73 accessibility slice."""

from __future__ import annotations

import argparse
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def load_contract(path: str | Path) -> dict[str, Any]:
    contract = json.loads(Path(path).read_text(encoding="utf-8"))
    checkpoints = contract.get("checkpoints", [])
    ids = [item.get("id") for item in checkpoints]
    if not ids or len(ids) != len(set(ids)) or any(not item for item in ids):
        raise ValueError("accessibility contract checkpoint ids must be unique")
    return contract


def contrast_ratio(foreground: str, background: str) -> float:
    def luminance(value: str) -> float:
        if re.fullmatch(r"#[0-9A-Fa-f]{6}", value) is None:
            raise ValueError("colors must use #RRGGBB")
        channels = [int(value[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    first, second = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (first + 0.05) / (second + 0.05)


def judge_accessibility(
    *, contract_path: str | Path, checkpoints: dict[str, list[dict[str, Any]]], density: float
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    expected = [item["id"] for item in contract["checkpoints"]]
    extra = sorted(set(checkpoints) - set(expected))
    results: list[dict[str, Any]] = []
    if not math.isfinite(density) or density <= 0:
        return _aggregate(expected, [], extra, "non_accountable", "density_unobservable")
    for declaration in contract["checkpoints"]:
        checkpoint_id = declaration["id"]
        layout = checkpoints.get(checkpoint_id)
        if layout is None:
            results.append(_result(checkpoint_id, "non_accountable", "checkpoint_not_executed"))
            continue
        results.append(_judge_checkpoint(declaration, layout, density))
    if extra:
        return _aggregate(expected, results, extra, "non_accountable", "undeclared_checkpoints")
    if any(item["conclusion"] == "non_accountable" for item in results):
        return _aggregate(expected, results, extra, "non_accountable", "evidence_incomplete_or_untrusted")
    if any(item["conclusion"] == "locally_rejected" for item in results):
        return _aggregate(expected, results, extra, "locally_rejected", "one_or_more_accessibility_checks_rejected")
    return _aggregate(expected, results, extra, "locally_supported", "all_preregistered_accessibility_checks_supported")


def load_uiautomator_layout(path: str | Path) -> list[dict[str, Any]]:
    """Normalize the installed device accessibility hierarchy without screenshots."""
    root = ET.parse(path).getroot()
    result: list[dict[str, Any]] = []
    for element in root.iter("node"):
        resource_id = element.attrib.get("resource-id", "")
        if ":id/" not in resource_id:
            continue
        interactions = [
            name
            for name in ("clickable", "focusable", "scrollable", "long-clickable")
            if element.attrib.get(name) == "true"
        ]
        result.append({
            "resource-id": resource_id.rsplit("/", 1)[-1],
            "text": element.attrib.get("text", ""),
            "content-desc": element.attrib.get("content-desc", ""),
            "bounds": element.attrib.get("bounds", ""),
            "interactions": interactions,
        })
    return result


def _judge_checkpoint(declaration: dict[str, Any], layout: list[dict[str, Any]], density: float) -> dict[str, Any]:
    checkpoint_id = declaration["id"]
    nodes = [node for node in layout if isinstance(node, dict)]
    by_id: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        resource_id = str(node.get("resource-id", ""))
        if resource_id:
            by_id.setdefault(resource_id, []).append(node)
    for required in declaration.get("nodes", []):
        resource_id = required["resource_id"]
        matches = by_id.get(resource_id, [])
        if len(matches) != 1:
            if not matches:
                return _result(checkpoint_id, "locally_rejected", "missing_accessible_node", resource_id=resource_id)
            return _result(checkpoint_id, "non_accountable", "duplicate_required_node", resource_id=resource_id)
        node = matches[0]
        source = required.get("name_source", "accessibility_name")
        if source == "content-desc":
            name = str(node.get("content-desc") or "").strip()
        else:
            name = str(node.get("content-desc") or node.get("text") or "").strip()
        if required.get("accessible_name") and name != required["accessible_name"]:
            return _result(checkpoint_id, "locally_rejected", "missing_or_wrong_accessible_name", resource_id=resource_id, observed=name)
        interactions = set(node.get("interactions", []))
        if required.get("actionable") and not ({"clickable", "focusable"} & interactions):
            return _result(checkpoint_id, "locally_rejected", "inaccessible_actionable_control", resource_id=resource_id)
        if required.get("actionable"):
            bounds = _bounds(node)
            if bounds is None:
                return _result(checkpoint_id, "non_accountable", "target_geometry_unobservable", resource_id=resource_id)
            width_dp = (bounds[2] - bounds[0]) / density
            height_dp = (bounds[3] - bounds[1]) / density
            minimum = float(required.get("minimum_target_dp", 48))
            if width_dp < minimum or height_dp < minimum:
                return _result(checkpoint_id, "locally_rejected", "undersized_touch_target", resource_id=resource_id, width_dp=width_dp, height_dp=height_dp, minimum_dp=minimum)
    names: dict[str, list[str]] = {}
    for required in declaration.get("nodes", []):
        if required.get("unique_name"):
            node = by_id[required["resource_id"]][0]
            source = required.get("name_source", "accessibility_name")
            name = str(node.get("content-desc") or "").strip() if source == "content-desc" else str(node.get("content-desc") or node.get("text") or "").strip()
            names.setdefault(name, []).append(required["resource_id"])
    duplicate = next((ids for name, ids in names.items() if name and len(ids) > 1), None)
    if duplicate:
        return _result(checkpoint_id, "locally_rejected", "duplicate_accessible_name", resource_ids=duplicate)
    observed_order = [str(node.get("resource-id")) for node in nodes if str(node.get("resource-id", "")) in declaration.get("traversal_order", [])]
    if observed_order != declaration.get("traversal_order", []):
        return _result(checkpoint_id, "locally_rejected", "incorrect_traversal_order", observed=observed_order)
    for check in declaration.get("contrast", []):
        try:
            ratio = contrast_ratio(check["foreground"], check["background"])
        except (KeyError, ValueError, TypeError):
            return _result(checkpoint_id, "non_accountable", "contrast_inputs_unmeasurable", check_id=check.get("id"))
        if ratio < float(check["minimum_ratio"]):
            return _result(checkpoint_id, "locally_rejected", "contrast_violation", check_id=check["id"], ratio=ratio, minimum_ratio=check["minimum_ratio"])
    return _result(checkpoint_id, "locally_supported", "checkpoint_invariants_satisfied")


def _bounds(node: dict[str, Any]) -> tuple[int, int, int, int] | None:
    value = str(node.get("bounds", ""))
    match = re.fullmatch(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", value)
    return tuple(map(int, match.groups())) if match else None


def _result(checkpoint_id: str, conclusion: str, reason: str, **details: Any) -> dict[str, Any]:
    return {"checkpoint_id": checkpoint_id, "conclusion": conclusion, "reason": reason, "accountable": conclusion != "non_accountable", "details": details}


def _aggregate(expected: list[str], results: list[dict[str, Any]], extra: list[str], conclusion: str, reason: str) -> dict[str, Any]:
    return {"schema_version": 1, "conclusion": conclusion, "reason": reason, "accountable": conclusion != "non_accountable", "expected_checkpoints": expected, "checkpoints": results, "undeclared_checkpoints": extra}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True)
    parser.add_argument("--layouts", required=True, type=Path)
    parser.add_argument("--density", required=True, type=float)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--uiautomator-xml", action="store_true")
    args = parser.parse_args(argv)
    if args.uiautomator_xml:
        layouts = {path.stem: load_uiautomator_layout(path) for path in args.layouts.glob("*.xml")}
    else:
        layouts = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in args.layouts.glob("*.json")}
    result = judge_accessibility(contract_path=args.contract, checkpoints=layouts, density=args.density)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if result["conclusion"] == "locally_supported" else 1


if __name__ == "__main__":
    raise SystemExit(main())
