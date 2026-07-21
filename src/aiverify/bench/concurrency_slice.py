"""Fail-closed oracle for the deterministic G-08 concurrency slice."""

from __future__ import annotations

import argparse
import json
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = judge_concurrency(json.loads(args.contract.read_text()), json.loads(args.evidence.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    return 0 if result["conclusion"] == "locally_supported" else 1


if __name__ == "__main__":
    raise SystemExit(main())
