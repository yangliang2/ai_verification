"""Fail-closed, independent oracles for issue #74."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _result(conclusion: str, reason: str, findings: list[str]) -> dict[str, Any]:
    return {"conclusion": conclusion, "reason": reason, "accountable": conclusion != "non_accountable", "findings": findings}


def judge_performance_resource(contract: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    required = {"device", "startup", "frames", "resource_pressure", "wakelocks", "runtime"}
    missing = sorted(required - evidence.keys())
    if missing:
        return _result("non_accountable", "missing_performance_evidence", missing)
    device = evidence["device"]
    if device.get("api_level") != contract.get("api_level") or not device.get("serial") or not device.get("build_fingerprint"):
        return _result("non_accountable", "device_identity_mismatch_or_incomplete", [])
    pressure = evidence["resource_pressure"]
    required_receipts = ("storage_setup", "battery_setup", "storage_cleanup", "battery_cleanup")
    bad_receipts = [name for name in required_receipts if pressure.get(name, {}).get("exit_code") != 0 or pressure.get(name, {}).get("observed") is not True]
    if bad_receipts:
        return _result("non_accountable", "resource_setup_or_cleanup_unproven", bad_receipts)
    frames = evidence["frames"]
    numeric = (evidence["startup"].get("total_time_ms"), frames.get("total_frames"), frames.get("slow_frames"), frames.get("frozen_frames"), frames.get("max_frame_ms"))
    if any(not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0 for value in numeric):
        return _result("non_accountable", "metrics_unparseable", [])
    findings: list[str] = []
    if evidence["startup"]["total_time_ms"] > contract["thresholds"]["cold_start_ms"]:
        findings.append("cold_start_threshold_exceeded")
    if frames["frozen_frames"] > contract["thresholds"]["max_frozen_frames"] or frames["max_frame_ms"] >= contract["thresholds"]["frozen_frame_ms"]:
        findings.append("frozen_frame_threshold_exceeded")
    if evidence["runtime"].get("crashes", 0) or evidence["runtime"].get("anrs", 0):
        findings.append("crash_or_anr")
    held = evidence["wakelocks"].get("fixture_held")
    if not isinstance(held, list):
        return _result("non_accountable", "wakelock_observation_missing", [])
    if held:
        findings.append("fixture_wakelock_held")
    return _result("locally_rejected" if findings else "locally_supported", "performance_resource_violations" if findings else "performance_resource_contract_satisfied", findings)


def judge_intent_security(contract: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    expected = {item["id"] for item in contract["security_scenarios"]}
    scenarios = evidence.get("scenarios")
    if not isinstance(scenarios, list):
        return _result("non_accountable", "security_scenarios_missing", [])
    ids = [item.get("id") for item in scenarios]
    if len(ids) != len(set(ids)) or set(ids) != expected:
        return _result("non_accountable", "security_scenario_set_mismatch", sorted(expected - set(ids)))
    if not evidence.get("package_identity", {}).get("sha256") or evidence.get("runtime", {}).get("crashes", 0):
        return _result("non_accountable", "security_identity_or_runtime_untrusted", [])
    findings = [item["id"] for item in scenarios if item.get("observed") is not True]
    return _result("locally_rejected" if findings else "locally_supported", "intent_security_violations" if findings else "intent_security_contract_satisfied", findings)


def judge_slice(contract: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    performance = judge_performance_resource(contract, evidence.get("performance_resource", {}))
    security = judge_intent_security(contract, evidence.get("intent_security", {}))
    domains = {"performance_resource": performance, "intent_security": security}
    if any(not item["accountable"] for item in domains.values()):
        conclusion, reason = "non_accountable", "one_or_more_domains_non_accountable"
    elif any(item["conclusion"] == "locally_rejected" for item in domains.values()):
        conclusion, reason = "locally_rejected", "one_or_more_domains_rejected"
    else:
        conclusion, reason = "locally_supported", "both_domains_supported"
    return {"schema_version": 1, "conclusion": conclusion, "reason": reason, "accountable": conclusion != "non_accountable", "domains": domains}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = judge_slice(json.loads(args.contract.read_text()), json.loads(args.evidence.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    return 0 if result["conclusion"] == "locally_supported" else 1


if __name__ == "__main__":
    raise SystemExit(main())
