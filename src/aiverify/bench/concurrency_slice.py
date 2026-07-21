"""Fail-closed oracle for the deterministic G-08 concurrency slice."""

from __future__ import annotations

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def _result(conclusion: str, reason: str, findings: list[str]) -> dict[str, Any]:
    return {"conclusion": conclusion, "reason": reason, "accountable": conclusion != "non_accountable", "findings": findings}


def judge_concurrency(contract: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    identity = evidence.get("identity", {})
    if not identity.get("serial") or identity.get("api_level") != contract.get("api_level"):
        return _result("non_accountable", "device_identity_missing_or_mismatched", [])
    if not identity.get("local_apk_sha256") or identity.get("local_apk_sha256") != identity.get("installed_apk_sha256"):
        return _result("non_accountable", "apk_identity_unbound", [])
    runtime = evidence.get("runtime", {})
    if any(runtime.get(key) != 0 for key in ("crashes", "anrs")):
        return _result("locally_rejected", "crash_or_anr", [key for key in ("crashes", "anrs") if runtime.get(key) != 0])
    if runtime.get("cleanup_exit") != 0 or runtime.get("completed") is not True:
        return _result("non_accountable", "runtime_or_cleanup_incomplete", [])
    journal = evidence.get("journal")
    if not isinstance(journal, list) or not journal:
        return _result("non_accountable", "journal_missing", [])
    sequences = [event.get("sequence") for event in journal]
    if sequences != list(range(1, len(journal) + 1)):
        return _result("non_accountable", "journal_sequence_invalid", [])
    schedule_id = evidence.get("schedule_id")
    declaration = next((item for item in contract.get("schedules", []) if item.get("id") == schedule_id), None)
    if declaration is None or any(event.get("schedule_id") != schedule_id for event in journal):
        return _result("non_accountable", "schedule_identity_invalid", [])
    names = [event.get("event") for event in journal]
    unknown = sorted(set(names) - set(declaration["allowed_events"]))
    missing = [name for name in declaration["required_events"] if names.count(name) != 1]
    decisions = [name for name in declaration["decision_events"] if names.count(name) == 1]
    if len(decisions) != 1:
        missing.append("exactly_one_decision_event")
    if unknown or missing:
        return _result("non_accountable", "event_accounting_invalid", [*(f"unknown:{x}" for x in unknown), *(f"missing_or_duplicate:{x}" for x in missing)])
    for before, after in declaration["partial_order"]:
        if names.index(before) >= names.index(after):
            return _result("non_accountable", "partial_order_violated", [f"{before}!<{after}"])
    findings: list[str] = []
    if "APPLY_STALE" in names or evidence.get("final_state") == "old":
        findings.append("stale_result_applied")
    if "APPLY_AFTER_DESTROY" in names:
        findings.append("application_after_destroy")
    if names.count("TERMINAL") != 1:
        return _result("non_accountable", "terminal_event_invalid", [])
    expected = declaration["expected_final_state"]
    if not findings and evidence.get("final_state") != expected:
        return _result("non_accountable", "terminal_state_contradictory", [])
    return _result("locally_rejected" if findings else "locally_supported", "concurrency_invariant_violated" if findings else "concurrency_contract_satisfied", findings)


def judge_lane(contract: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    schedules = evidence.get("schedules")
    if not isinstance(schedules, list):
        return {"schema_version": 1, **_result("non_accountable", "schedule_evidence_missing", []), "schedules": []}
    expected = [item["id"] for item in contract.get("schedules", [])]
    observed = [item.get("schedule_id") for item in schedules]
    if observed != expected:
        return {"schema_version": 1, **_result("non_accountable", "schedule_set_or_order_mismatch", []), "schedules": []}
    results = [{"schedule_id": item["schedule_id"], **judge_concurrency(contract, item)} for item in schedules]
    if any(not item["accountable"] for item in results):
        conclusion, reason = "non_accountable", "one_or_more_schedules_non_accountable"
    elif any(item["conclusion"] == "locally_rejected" for item in results):
        conclusion, reason = "locally_rejected", "one_or_more_schedules_rejected"
    else:
        conclusion, reason = "locally_supported", "all_schedules_supported"
    return {"schema_version": 1, **_result(conclusion, reason, []), "schedules": results}


def validate_raw_receipts(evidence: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    lane = evidence.get("lane")
    lane_root = root / "lanes" / str(lane)
    local = lane_root / "local-apk.sha256"
    installed = lane_root / "installed-apk.sha256"
    runtime = lane_root / "runtime.txt"
    source = lane_root / "source-identity.txt"
    patch_receipt = lane_root / "patch.sha256"
    if not local.is_file() or not installed.is_file():
        return ["apk_receipts_missing"]
    local_hash = local.read_text().split()[0]
    installed_hash = installed.read_text().split()[0]
    if not source.is_file() or f"source_commit={evidence.get('source_commit')}" not in source.read_text() or "source_code_diff_exit=0" not in source.read_text():
        errors.append("source_identity_unbound")
    expected_patches = {"baseline": None, "stale-candidate": "apply-stale-result.patch", "destroy-candidate": "apply-after-destroy.patch"}
    expected_patch = expected_patches.get(lane)
    if not patch_receipt.is_file():
        errors.append("patch_receipt_missing")
    elif expected_patch is None:
        if patch_receipt.read_text().strip() != "patch=none" or evidence.get("patch") is not None:
            errors.append("baseline_patch_identity_invalid")
    else:
        project_root = root.parents[2]
        patch_path = project_root / "bench" / "capability-slices" / "deterministic-concurrency" / "patches" / expected_patch
        if evidence.get("patch") != expected_patch or not patch_path.is_file() or patch_receipt.read_text().split()[0] != hashlib.sha256(patch_path.read_bytes()).hexdigest():
            errors.append("candidate_patch_identity_invalid")
    if not runtime.is_file():
        errors.append("runtime_receipt_missing")
    else:
        runtime_text = runtime.read_text()
        markers = ("window_start_utc=", "window_end_utc=", "crash_query_exit=0", "crash_count=0", "anr_query_exit=0", "anr_count=0", "cleanup_exit=0")
        if any(marker not in runtime_text for marker in markers):
            errors.append("runtime_receipt_incomplete")
    receipt_names = {"new-before-old": "ordering-journal.xml", "destroy-before-release": "destroy-journal.xml"}
    for schedule in evidence.get("schedules", []):
        identity = schedule.get("identity", {})
        if identity.get("local_apk_sha256") != local_hash or identity.get("installed_apk_sha256") != installed_hash:
            errors.append(f"{schedule.get('schedule_id')}:apk_receipt_mismatch")
        receipt = lane_root / receipt_names.get(schedule.get("schedule_id"), "missing")
        if not receipt.is_file():
            errors.append(f"{schedule.get('schedule_id')}:journal_receipt_missing")
            continue
        values = {node.attrib.get("name"): node.text for node in ET.parse(receipt).getroot() if node.tag == "string"}
        observed = []
        for line in (values.get("journal") or "").strip().splitlines():
            sequence, schedule_id, event = line.strip().split("|", 2)
            observed.append({"sequence": int(sequence), "schedule_id": schedule_id, "event": event})
        if observed != schedule.get("journal") or values.get("final_state") != schedule.get("final_state"):
            errors.append(f"{schedule.get('schedule_id')}:journal_receipt_mismatch")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    evidence = json.loads(args.evidence.read_text())
    result = judge_lane(json.loads(args.contract.read_text()), evidence)
    receipt_errors = validate_raw_receipts(evidence, args.evidence.parent)
    if receipt_errors:
        result = {"schema_version": 1, **_result("non_accountable", "raw_receipt_validation_failed", receipt_errors), "schedules": result.get("schedules", [])}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    return 0 if result["conclusion"] == "locally_supported" else 1


if __name__ == "__main__":
    raise SystemExit(main())
