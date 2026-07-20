import copy
import json
from pathlib import Path

from aiverify.bench.performance_intent_slice import judge_slice, validate_receipt_files
from aiverify.runner.run_spec import load_run_spec


CONTRACT = json.loads(Path("bench/capability-slices/performance-intent-security/contract.json").read_text())


def evidence():
    receipts = {name: {"exit_code": 0, "observed": True} for name in ("storage_setup", "battery_setup", "storage_cleanup", "battery_cleanup")}
    return {
        "performance_resource": {
            "apk_identity": {"local_sha256": "abc", "installed_sha256": "abc"},
            "raw_receipts": {"startup": "startup.txt", "frame": "frame.xml", "resource": "resource.txt", "runtime": "runtime.txt"},
            "device": {"serial": "emulator-5554", "api_level": 35, "build_fingerprint": "fixture/fingerprint"},
            "startup": {"total_time_ms": 320},
            "frames": {"total_frames": 20, "slow_frames": 0, "frozen_frames": 0, "max_frame_ms": 12.0},
            "resource_pressure": receipts,
            "wakelocks": {"fixture_held": []},
            "runtime": {"crashes": 0, "anrs": 0},
        },
        "intent_security": {
            "apk_identity": {"local_sha256": "abc", "installed_sha256": "abc"},
            "raw_receipts": {"security": "security.txt", "pending_intent": "prefs.xml", "runtime": "runtime.txt"},
            "package_identity": {"sha256": "abc"},
            "runtime": {"crashes": 0},
            "scenarios": [{"id": item["id"], "observed": True} for item in CONTRACT["security_scenarios"]],
        },
    }


def test_baseline_requires_both_domains_and_supports_when_both_pass():
    result = judge_slice(CONTRACT, evidence())
    assert result["conclusion"] == "locally_supported"
    assert set(result["domains"]) == {"performance_resource", "intent_security"}


def test_frozen_frame_candidate_is_rejected_only_by_performance_oracle():
    data = evidence()
    data["performance_resource"]["frames"].update(frozen_frames=1, max_frame_ms=901)
    result = judge_slice(CONTRACT, data)
    assert result["conclusion"] == "locally_rejected"
    assert result["domains"]["performance_resource"]["findings"] == ["frozen_frame_threshold_exceeded"]
    assert result["domains"]["intent_security"]["conclusion"] == "locally_supported"


def test_unsafe_nested_intent_candidate_is_rejected_only_by_security_oracle():
    data = evidence()
    next(item for item in data["intent_security"]["scenarios"] if item["id"] == "nested_intent_rejected")["observed"] = False
    result = judge_slice(CONTRACT, data)
    assert result["domains"]["intent_security"]["findings"] == ["nested_intent_rejected"]
    assert result["domains"]["performance_resource"]["conclusion"] == "locally_supported"


def test_missing_domain_cannot_be_masked_by_other_domain():
    data = evidence()
    del data["performance_resource"]["frames"]
    result = judge_slice(CONTRACT, data)
    assert result["conclusion"] == "non_accountable"
    assert result["domains"]["intent_security"]["conclusion"] == "locally_supported"


def test_resource_cleanup_wakelock_startup_crash_and_scenario_set_fail_closed():
    cases = []
    cleanup = evidence(); cleanup["performance_resource"]["resource_pressure"]["battery_cleanup"]["observed"] = False; cases.append((cleanup, "non_accountable"))
    lock = evidence(); lock["performance_resource"]["wakelocks"]["fixture_held"] = ["Issue74Lock"]; cases.append((lock, "locally_rejected"))
    startup = evidence(); startup["performance_resource"]["startup"]["total_time_ms"] = 1001; cases.append((startup, "locally_rejected"))
    crash = evidence(); crash["performance_resource"]["runtime"]["crashes"] = 1; cases.append((crash, "locally_rejected"))
    missing = evidence(); missing["intent_security"]["scenarios"].pop(); cases.append((missing, "non_accountable"))
    for data, expected in cases:
        assert judge_slice(CONTRACT, data)["conclusion"] == expected


def test_boolean_or_negative_metrics_are_not_accepted_as_numbers():
    for value in (True, -1, "12"):
        data = evidence()
        data["performance_resource"]["frames"]["total_frames"] = value
        assert judge_slice(CONTRACT, data)["conclusion"] == "non_accountable"


def test_receipt_files_must_exist_for_cli_accountability(tmp_path):
    data = evidence()
    assert validate_receipt_files(data, tmp_path)


def test_three_run_specs_are_matched_and_candidates_are_narrow():
    root = Path("bench/capability-slices/performance-intent-security")
    specs = [load_run_spec(root / "run-specs" / name) for name in ("baseline.yaml", "performance-candidate.yaml", "security-candidate.yaml")]
    assert specs[0].scenario.user_actions == specs[1].scenario.user_actions == specs[2].scenario.user_actions
    assert specs[0].scenario.assertions == specs[1].scenario.assertions == specs[2].scenario.assertions
    assert specs[0].diff is None
    assert "DRAW_DELAY_MS = 900" in specs[1].diff.read_text()
    assert "startActivity(nested)" in specs[2].diff.read_text()
