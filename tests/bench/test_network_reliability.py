from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from aiverify.bench.network_reliability import (
    build_evidence_bundle,
    evaluate_network_pair,
    main,
)
from aiverify.runner.run_spec import load_run_spec


_ROOT = Path(__file__).resolve().parents[2]


def _bundle(role: str) -> dict:
    return {
        "schema_version": 1,
        "role": role,
        "fixture_id": "issue-69-network-v1",
        "journey_sha256": "a" * 64,
        "device": {"serial": "emulator-5554", "api": 35, "avd": "aiverify_api35"},
        "apk": {
            "package": "org.wikipedia.dev",
            "sha256": ("b" if role == "baseline" else "c") * 64,
        },
        "system_events": [
            {"step_index": 0, "event": "network_off", "args": {}},
            {
                "step_index": 1,
                "event": "wait",
                "args": {"seconds": "1", "expect_network": "off"},
            },
            {"step_index": 2, "event": "network_on", "args": {}},
            {
                "step_index": 3,
                "event": "wait",
                "args": {"seconds": "1", "expect_network": "on"},
            },
        ],
        "checkpoints": {
            "online": {"state": "content", "content": "online-v1"},
            "offline": {"state": "cached", "content": "cached-v1"},
            "timeout": {"state": "timeout", "retry_enabled": True},
            "retry": {"state": "content", "content": "retry-v1"},
            "cancellation": {"state": "cancelled"},
            "ordered_response": {"state": "content", "content": "new-v2"},
            "recovery": {"state": "content", "content": "recovered-v3"},
        },
        "network_events": [
            {"sequence": 1, "scenario": "online", "kind": "response_applied", "request_id": "online-1", "content": "online-v1"},
            {"sequence": 2, "scenario": "offline", "kind": "cache_shown", "request_id": "offline-1", "content": "cached-v1"},
            {"sequence": 3, "scenario": "timeout", "kind": "request_started", "request_id": "timeout-1"},
            {"sequence": 4, "scenario": "timeout", "kind": "request_timed_out", "request_id": "timeout-1"},
            {"sequence": 5, "scenario": "timeout", "kind": "request_cancelled", "request_id": "timeout-1"},
            {"sequence": 6, "scenario": "retry", "kind": "retry_attempt", "request_id": "retry-1", "attempt": 1},
            {"sequence": 7, "scenario": "retry", "kind": "retry_attempt", "request_id": "retry-1", "attempt": 2},
            {"sequence": 8, "scenario": "retry", "kind": "retry_attempt", "request_id": "retry-1", "attempt": 3},
            {"sequence": 9, "scenario": "retry", "kind": "response_applied", "request_id": "retry-1", "content": "retry-v1"},
            {"sequence": 10, "scenario": "cancellation", "kind": "request_started", "request_id": "cancel-1"},
            {"sequence": 11, "scenario": "cancellation", "kind": "request_cancelled", "request_id": "cancel-1"},
            {"sequence": 12, "scenario": "ordered_response", "kind": "request_started", "request_id": "old"},
            {"sequence": 13, "scenario": "ordered_response", "kind": "request_started", "request_id": "new"},
            {"sequence": 14, "scenario": "ordered_response", "kind": "response_applied", "request_id": "new", "content": "new-v2"},
            {"sequence": 15, "scenario": "ordered_response", "kind": "response_ignored", "request_id": "old", "content": "old-v1"},
            {"sequence": 16, "scenario": "recovery", "kind": "response_applied", "request_id": "recovery-1", "content": "recovered-v3"},
        ],
        "logcat": "",
    }


def test_matched_pair_supports_good_baseline_and_detects_candidate_faults() -> None:
    baseline = _bundle("baseline")
    candidate = deepcopy(_bundle("candidate"))
    candidate["network_events"][9:9] = [
        {"sequence": 9.1, "scenario": "retry", "kind": "retry_attempt", "request_id": "retry-1", "attempt": 4},
        {"sequence": 9.2, "scenario": "retry", "kind": "retry_attempt", "request_id": "retry-1", "attempt": 5},
        {"sequence": 9.3, "scenario": "retry", "kind": "retry_attempt", "request_id": "retry-1", "attempt": 6},
    ]
    candidate["network_events"].append(
        {"sequence": 17, "scenario": "ordered_response", "kind": "response_applied", "request_id": "old", "content": "old-v1"}
    )
    candidate["checkpoints"]["ordered_response"]["content"] = "old-v1"

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "locally_supported"
    assert verdict["baseline"]["outcome"] == "pass"
    assert verdict["candidate"]["outcome"] == "fail"
    assert verdict["candidate"]["faults"] == [
        "retry_storm",
        "stale_response_overwrite",
    ]
    assert verdict["claims"] == {
        "detection_rate": False,
        "goldset": False,
        "upstream_acceptance": False,
    }


def test_pair_is_non_accountable_when_event_sequence_is_not_strictly_increasing() -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    candidate["network_events"][1]["sequence"] = 1

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "non_accountable"
    assert verdict["candidate"] == {
        "outcome": "inconclusive",
        "faults": ["evidence_invalid"],
    }


def test_pair_requires_network_transitions_and_wait_postconditions() -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    baseline["system_events"] = []
    candidate["system_events"] = []

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "non_accountable"
    assert verdict["reason"] == "baseline system-event evidence is invalid"


def test_oracle_detects_response_applied_after_cancellation() -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    candidate["network_events"].append(
        {
            "sequence": 17,
            "scenario": "cancellation",
            "kind": "response_applied",
            "request_id": "cancel-1",
            "content": "late-v1",
        }
    )

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "locally_supported"
    assert verdict["candidate"]["faults"] == ["cancellation_failed"]


def test_pair_is_non_accountable_without_successful_recovery_marker() -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    baseline["network_events"] = [
        event
        for event in baseline["network_events"]
        if event["scenario"] != "recovery"
    ]

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "non_accountable"
    assert verdict["baseline"] == {
        "outcome": "inconclusive",
        "faults": ["evidence_invalid"],
    }


def test_oracle_detects_blank_or_error_terminal_ui() -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    candidate["checkpoints"]["recovery"] = {"state": "error", "content": ""}

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "locally_supported"
    assert verdict["candidate"]["faults"] == ["blank_or_error_state"]


def test_oracle_detects_candidate_crash_or_anr() -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    candidate["logcat"] = (
        "E AndroidRuntime: FATAL EXCEPTION: main\n"
        "E AndroidRuntime: Process: org.wikipedia.dev, PID: 1234"
    )

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "locally_supported"
    assert verdict["candidate"]["faults"] == ["crash_or_anr"]


def test_oracle_ignores_androidruntime_shutdown_from_evidence_tool_process() -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    baseline["logcat"] = "D AndroidRuntime: Shutting down VM"
    candidate["logcat"] = (
        "E AndroidRuntime: FATAL EXCEPTION: main\n"
        "E AndroidRuntime: Process: org.wikipedia.dev, PID: 1234"
    )

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "locally_supported"
    assert verdict["baseline"]["outcome"] == "pass"
    assert verdict["candidate"]["faults"] == ["crash_or_anr"]


def test_oracle_detects_duplicate_retry_attempt() -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    candidate["network_events"].insert(
        8,
        {
            "sequence": 8.5,
            "scenario": "retry",
            "kind": "retry_attempt",
            "request_id": "retry-1",
            "attempt": 3,
        },
    )

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "locally_supported"
    assert verdict["candidate"]["faults"] == [
        "duplicate_retry",
        "retry_storm",
    ]


def test_cli_writes_one_machine_checkable_conclusion(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    output = tmp_path / "conclusion.json"
    baseline.write_text(json.dumps(_bundle("baseline")), encoding="utf-8")
    faulty = _bundle("candidate")
    faulty["logcat"] = "ActivityManager: ANR in org.wikipedia.dev"
    candidate.write_text(json.dumps(faulty), encoding="utf-8")

    exit_code = main(
        [
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["conclusion"] == "locally_supported"
    assert list(key for key in payload if key == "conclusion") == ["conclusion"]


def test_cli_fails_closed_with_one_conclusion_for_malformed_json(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    output = tmp_path / "conclusion.json"
    baseline.write_text(json.dumps(_bundle("baseline")), encoding="utf-8")
    candidate.write_text("{not valid json", encoding="utf-8")

    exit_code = main(
        [
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert payload["conclusion"] == "non_accountable"
    assert payload["reason"] == "candidate evidence could not be parsed"


def test_pair_fails_closed_for_malformed_event_fields() -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    candidate["network_events"][5]["attempt"] = {"unexpected": "shape"}

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "non_accountable"
    assert verdict["candidate"] == {
        "outcome": "inconclusive",
        "faults": ["evidence_invalid"],
    }


@pytest.mark.parametrize(
    "malformation",
    [
        "device_array",
        "fixture_id_number",
        "journey_sha_number",
        "apk_package_object",
        "apk_sha_object",
        "event_missing_request_id",
        "event_content_object",
        "sequence_nan",
    ],
)
def test_pair_fails_closed_for_all_malformed_provenance_and_event_shapes(
    malformation: str,
) -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    candidate["logcat"] = "ActivityManager: ANR in org.wikipedia.dev"

    if malformation == "device_array":
        baseline["device"] = candidate["device"] = []
    elif malformation == "fixture_id_number":
        baseline["fixture_id"] = candidate["fixture_id"] = 69
    elif malformation == "journey_sha_number":
        baseline["journey_sha256"] = candidate["journey_sha256"] = 69
    elif malformation == "apk_package_object":
        baseline["apk"]["package"] = candidate["apk"]["package"] = {
            "unexpected": "shape"
        }
    elif malformation == "apk_sha_object":
        baseline["apk"]["sha256"] = {"unexpected": "shape"}
    elif malformation == "event_missing_request_id":
        candidate["network_events"][0].pop("request_id")
    elif malformation == "event_content_object":
        candidate["network_events"][0]["content"] = {"unexpected": "shape"}
    elif malformation == "sequence_nan":
        candidate["network_events"][0]["sequence"] = float("nan")

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "non_accountable"


def test_committed_network_run_specs_share_the_same_journey_contract() -> None:
    baseline = load_run_spec(
        _ROOT / "bench/goldset/run-specs/wikipedia-network-reliability-01-baseline.yaml",
        environ={"WIKIPEDIA_SOURCE": "/tmp/wikipedia-baseline"},
    )
    candidate = load_run_spec(
        _ROOT / "bench/goldset/run-specs/wikipedia-network-reliability-01-candidate.yaml",
        environ={"WIKIPEDIA_SOURCE": "/tmp/wikipedia-candidate"},
    )

    assert baseline.scenario.user_actions == candidate.scenario.user_actions
    assert baseline.scenario.system_events == candidate.scenario.system_events
    assert [event.event for event in baseline.scenario.system_events] == [
        "network_off",
        "wait",
        "wait",
        "network_on",
        "wait",
        "wait",
        "wait",
        "wait",
    ]
    assert baseline.scenario.metric_context.seed_kind == "baseline_control"
    assert candidate.scenario.metric_context.seed_kind == "injected_defect"
    assert baseline.diff != candidate.diff


def test_build_evidence_bundle_extracts_layout_state_and_structured_logcat(
    tmp_path: Path,
) -> None:
    layout = tmp_path / "online-layout.json"
    layout.write_text(
        json.dumps(
            [
                {
                    "text": (
                        "Fixture ID: issue-69-network-v1\n"
                        "Scenario: online\nState: content\n"
                        "Content: online-v1\nRetry enabled: false"
                    )
                }
            ]
        ),
        encoding="utf-8",
    )
    logcat = tmp_path / "logcat.txt"
    logcat.write_text(
        '07-19 I AIVerifyNetwork: {"sequence":1,"scenario":"online",'
        '"kind":"response_applied","request_id":"online-1",'
        '"content":"online-v1"}\n',
        encoding="utf-8",
    )

    bundle = build_evidence_bundle(
        role="baseline",
        fixture_id="issue-69-network-v1",
        journey_sha256="a" * 64,
        device={"serial": "emulator-5554", "api": 35, "avd": "aiverify_api35"},
        apk={"package": "org.wikipedia.dev", "sha256": "b" * 64},
        system_events=[],
        checkpoint_layouts={"online": layout},
        logcat_path=logcat,
    )

    assert bundle["checkpoints"]["online"] == {
        "state": "content",
        "content": "online-v1",
        "retry_enabled": False,
    }
    assert bundle["network_events"] == [
        {
            "sequence": 1,
            "scenario": "online",
            "kind": "response_applied",
            "request_id": "online-1",
            "content": "online-v1",
        }
    ]
