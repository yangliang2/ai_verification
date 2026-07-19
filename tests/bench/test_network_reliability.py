from __future__ import annotations

from copy import deepcopy
import hashlib
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


def _sync_logcat(bundle: dict, extra: str = "") -> None:
    fixture_ready = {
        "sequence": 0,
        "scenario": "fixture",
        "kind": "fixture_ready",
        "request_id": "fixture-1",
        "content": "issue-69-network-v1",
    }
    markers = [fixture_ready, *bundle["network_events"]]
    lines = [
        f"I AIVerifyNetwork: {json.dumps(event, separators=(',', ':'))}"
        for event in markers
    ]
    if extra:
        lines.append(extra)
    bundle["logcat"] = "\n".join(lines) + "\n"


def _bundle(role: str) -> dict:
    bundle = {
        "schema_version": 1,
        "role": role,
        "fixture_id": "issue-69-network-v1",
        "journey_sha256": "d9ff0cdec1734f3c2cf6fba05035b2bc53c579aacf9760bba61fb9c3afd4c415",
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
                "args": {
                    "seconds": "0.2",
                    "expect_network": "off",
                    "expect_resumed": "target",
                },
            },
            {
                "step_index": 2,
                "event": "wait",
                "args": {
                    "seconds": "0.6",
                    "expect_network": "off",
                    "expect_resumed": "target",
                },
            },
            {"step_index": 3, "event": "network_on", "args": {}},
            {
                "step_index": 4,
                "event": "wait",
                "args": {
                    "seconds": "0.2",
                    "expect_network": "on",
                    "expect_resumed": "target",
                },
            },
            {
                "step_index": 5,
                "event": "wait",
                "args": {
                    "seconds": "0.6",
                    "expect_network": "on",
                    "expect_resumed": "target",
                },
            },
            {
                "step_index": 6,
                "event": "wait",
                "args": {
                    "seconds": "0.6",
                    "expect_network": "on",
                    "expect_resumed": "target",
                },
            },
            {
                "step_index": 7,
                "event": "wait",
                "args": {
                    "seconds": "0.2",
                    "expect_network": "on",
                    "expect_resumed": "target",
                },
            },
        ],
        "checkpoints": {
            "online": {"state": "content", "content": "online-v1", "retry_enabled": False},
            "offline": {"state": "cached", "content": "cached-v1", "retry_enabled": False},
            "timeout": {"state": "timeout", "content": "", "retry_enabled": True},
            "retry": {"state": "content", "content": "retry-v1", "retry_enabled": False},
            "cancellation": {"state": "cancelled", "content": "", "retry_enabled": False},
            "ordered_response": {"state": "content", "content": "new-v2", "retry_enabled": False},
            "recovery": {"state": "content", "content": "recovered-v3", "retry_enabled": False},
        },
        "network_events": [
            {"sequence": 1, "scenario": "online", "kind": "network_observed", "request_id": "online-1", "content": "on"},
            {"sequence": 2, "scenario": "online", "kind": "response_applied", "request_id": "online-1", "content": "online-v1"},
            {"sequence": 3, "scenario": "offline", "kind": "network_observed", "request_id": "offline-1", "content": "off"},
            {"sequence": 4, "scenario": "offline", "kind": "cache_shown", "request_id": "offline-1", "content": "cached-v1"},
            {"sequence": 5, "scenario": "timeout", "kind": "request_started", "request_id": "timeout-1"},
            {"sequence": 6, "scenario": "timeout", "kind": "request_timed_out", "request_id": "timeout-1"},
            {"sequence": 7, "scenario": "timeout", "kind": "request_cancelled", "request_id": "timeout-1"},
            {"sequence": 8, "scenario": "retry", "kind": "retry_attempt", "request_id": "retry-1", "attempt": 1},
            {"sequence": 9, "scenario": "retry", "kind": "retry_attempt", "request_id": "retry-1", "attempt": 2},
            {"sequence": 10, "scenario": "retry", "kind": "retry_attempt", "request_id": "retry-1", "attempt": 3},
            {"sequence": 11, "scenario": "retry", "kind": "response_applied", "request_id": "retry-1", "content": "retry-v1"},
            {"sequence": 12, "scenario": "cancellation", "kind": "request_started", "request_id": "cancel-1"},
            {"sequence": 13, "scenario": "cancellation", "kind": "request_cancelled", "request_id": "cancel-1"},
            {"sequence": 14, "scenario": "cancellation", "kind": "response_ignored", "request_id": "cancel-1", "content": "late-v1"},
            {"sequence": 15, "scenario": "ordered_response", "kind": "request_started", "request_id": "old"},
            {"sequence": 16, "scenario": "ordered_response", "kind": "request_started", "request_id": "new"},
            {"sequence": 17, "scenario": "ordered_response", "kind": "response_applied", "request_id": "new", "content": "new-v2"},
            {"sequence": 18, "scenario": "ordered_response", "kind": "response_ignored", "request_id": "old", "content": "old-v1"},
            {"sequence": 19, "scenario": "recovery", "kind": "network_observed", "request_id": "recovery-1", "content": "on"},
            {"sequence": 20, "scenario": "recovery", "kind": "response_applied", "request_id": "recovery-1", "content": "recovered-v3"},
        ],
    }
    _sync_logcat(bundle)
    return bundle


def test_matched_pair_supports_good_baseline_and_detects_candidate_faults() -> None:
    baseline = _bundle("baseline")
    candidate = deepcopy(_bundle("candidate"))
    retry_response = next(
        index
        for index, event in enumerate(candidate["network_events"])
        if event["scenario"] == "retry" and event["kind"] == "response_applied"
    )
    candidate["network_events"][retry_response:retry_response] = [
        {"sequence": 10.1, "scenario": "retry", "kind": "retry_attempt", "request_id": "retry-1", "attempt": 4},
        {"sequence": 10.2, "scenario": "retry", "kind": "retry_attempt", "request_id": "retry-1", "attempt": 5},
        {"sequence": 10.3, "scenario": "retry", "kind": "retry_attempt", "request_id": "retry-1", "attempt": 6},
    ]
    old_resolution = next(
        index
        for index, event in enumerate(candidate["network_events"])
        if event["scenario"] == "ordered_response"
        and event["kind"] == "response_ignored"
    )
    candidate["network_events"][old_resolution] = {
        "sequence": 18,
        "scenario": "ordered_response",
        "kind": "response_applied",
        "request_id": "old",
        "content": "old-v1",
    }
    candidate["checkpoints"]["ordered_response"]["content"] = "old-v1"
    _sync_logcat(candidate)

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
    late_response = next(
        event
        for event in candidate["network_events"]
        if event["scenario"] == "cancellation"
        and event["kind"] == "response_ignored"
    )
    late_response["kind"] = "response_applied"
    _sync_logcat(candidate)

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


def test_oracle_rejects_stale_recovery_content_on_baseline() -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    baseline["checkpoints"]["recovery"]["content"] = "stale-v1"
    baseline["network_events"][-1]["content"] = "stale-v1"
    _sync_logcat(baseline)
    _sync_logcat(candidate, "ActivityManager: ANR in org.wikipedia.dev")

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "locally_rejected"
    assert verdict["baseline"] == {"outcome": "fail", "faults": ["stale_data"]}


def test_pair_is_non_accountable_without_retry_attempt_evidence() -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    baseline["network_events"] = [
        event
        for event in baseline["network_events"]
        if not (
            event["scenario"] == "retry" and event["kind"] == "retry_attempt"
        )
    ]
    candidate["logcat"] = "ActivityManager: ANR in org.wikipedia.dev"

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "non_accountable"
    assert verdict["baseline"]["faults"] == ["evidence_invalid"]


def test_pair_is_non_accountable_without_cancellation_late_resolution() -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    baseline["network_events"] = [
        event
        for event in baseline["network_events"]
        if not (
            event["scenario"] == "cancellation"
            and event["kind"] == "response_ignored"
        )
    ]

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "non_accountable"


def test_pair_is_non_accountable_without_delayed_old_response_completion() -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    baseline["network_events"] = [
        event
        for event in baseline["network_events"]
        if not (
            event["scenario"] == "ordered_response"
            and event.get("request_id") == "old"
            and event["kind"] == "response_ignored"
        )
    ]

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "non_accountable"


@pytest.mark.parametrize(
    ("field", "value"),
    [("state", "cached"), ("retry_enabled", True)],
)
def test_oracle_rejects_invalid_ordered_checkpoint_semantics(
    field: str, value: object
) -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    baseline["checkpoints"]["ordered_response"][field] = value
    _sync_logcat(candidate, "ActivityManager: ANR in org.wikipedia.dev")

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "locally_rejected"
    assert verdict["baseline"] == {
        "outcome": "fail",
        "faults": ["scenario_contract_failed"],
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "extra_checkpoint",
        "extra_scenario_event",
        "reordered_scenario_blocks",
        "duplicate_cancellation_resolution",
        "duplicate_ordered_resolution",
    ],
)
def test_pair_fails_closed_for_extra_duplicate_or_reordered_scenario_evidence(
    mutation: str,
) -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    candidate["logcat"] = "ActivityManager: ANR in org.wikipedia.dev"

    if mutation == "extra_checkpoint":
        baseline["checkpoints"]["eighth_scenario"] = {
            "state": "content",
            "content": "unexpected-v1",
            "retry_enabled": False,
        }
    elif mutation == "extra_scenario_event":
        baseline["network_events"].append(
            {
                "sequence": 21,
                "scenario": "eighth_scenario",
                "kind": "response_applied",
                "request_id": "extra-1",
                "content": "unexpected-v1",
            }
        )
    elif mutation == "reordered_scenario_blocks":
        recovery = [
            event
            for event in baseline["network_events"]
            if event["scenario"] == "recovery"
        ]
        other = [
            event
            for event in baseline["network_events"]
            if event["scenario"] != "recovery"
        ]
        baseline["network_events"] = recovery + other
        for sequence, event in enumerate(baseline["network_events"], start=1):
            event["sequence"] = sequence
    elif mutation == "duplicate_cancellation_resolution":
        baseline["network_events"].insert(
            14,
            {
                "sequence": 14.5,
                "scenario": "cancellation",
                "kind": "response_ignored",
                "request_id": "cancel-1",
                "content": "late-v1",
            },
        )
    elif mutation == "duplicate_ordered_resolution":
        baseline["network_events"].insert(
            18,
            {
                "sequence": 18.5,
                "scenario": "ordered_response",
                "kind": "response_ignored",
                "request_id": "old",
                "content": "old-v1",
            },
        )

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "non_accountable"


@pytest.mark.parametrize(
    "mutation",
    [
        "baseline_checkpoint_missing_content",
        "candidate_checkpoint_missing_retry_enabled",
        "candidate_event_missing_required_content",
        "extra_system_wait",
        "boolean_wait_seconds",
        "offset_system_steps",
        "drifted_wait_seconds",
        "missing_logcat",
        "wrong_package",
    ],
)
def test_pair_fails_closed_for_missing_fields_or_system_event_schedule_drift(
    mutation: str,
) -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    candidate["logcat"] = "ActivityManager: ANR in org.wikipedia.dev"

    if mutation == "baseline_checkpoint_missing_content":
        baseline["checkpoints"]["timeout"].pop("content")
    elif mutation == "candidate_checkpoint_missing_retry_enabled":
        candidate["checkpoints"]["online"].pop("retry_enabled")
    elif mutation == "candidate_event_missing_required_content":
        recovery_response = next(
            event
            for event in candidate["network_events"]
            if event["scenario"] == "recovery"
            and event["kind"] == "response_applied"
        )
        recovery_response.pop("content")
    elif mutation == "extra_system_wait":
        extra = {
            "step_index": 8,
            "event": "wait",
            "args": {
                "seconds": "0.2",
                "expect_network": "on",
                "expect_resumed": "target",
            },
        }
        baseline["system_events"].append(deepcopy(extra))
        candidate["system_events"].append(deepcopy(extra))
    elif mutation == "boolean_wait_seconds":
        baseline["system_events"][1]["args"]["seconds"] = True
        candidate["system_events"][1]["args"]["seconds"] = True
    elif mutation == "offset_system_steps":
        for bundle in (baseline, candidate):
            for event in bundle["system_events"]:
                event["step_index"] += 10
    elif mutation == "drifted_wait_seconds":
        baseline["system_events"][1]["args"]["seconds"] = "59"
        candidate["system_events"][1]["args"]["seconds"] = "59"
    elif mutation == "missing_logcat":
        candidate.pop("logcat")
    elif mutation == "wrong_package":
        baseline["apk"]["package"] = "org.example.other"
        candidate["apk"]["package"] = "org.example.other"

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "non_accountable"


@pytest.mark.parametrize(
    "invalid_logcat",
    [
        "   \n",
        "unrelated evidence\n",
        "I AIVerifyNetwork: {not valid json\n",
    ],
)
def test_pair_requires_authoritative_structured_logcat(
    invalid_logcat: str,
) -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    candidate["logcat"] = invalid_logcat

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "non_accountable"


def test_pair_rejects_network_events_that_disagree_with_logcat() -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    candidate["network_events"][-1]["content"] = "contradictory-v1"

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "non_accountable"


def test_pair_requires_fixture_ready_to_be_first_structured_marker() -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    lines = candidate["logcat"].splitlines()
    candidate["logcat"] = "\n".join([*lines[1:], lines[0]]) + "\n"

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "non_accountable"


def test_oracle_detects_blank_or_error_terminal_ui() -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    candidate["checkpoints"]["recovery"] = {
        "state": "error",
        "content": "",
        "retry_enabled": False,
    }

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "locally_supported"
    assert verdict["candidate"]["faults"] == ["blank_or_error_state"]


def test_oracle_detects_candidate_crash_or_anr() -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    _sync_logcat(candidate, (
        "E AndroidRuntime: FATAL EXCEPTION: main\n"
        "E AndroidRuntime: Process: org.wikipedia.dev, PID: 1234"
    ))

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "locally_supported"
    assert verdict["candidate"]["faults"] == ["crash_or_anr"]


def test_oracle_ignores_androidruntime_shutdown_from_evidence_tool_process() -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    _sync_logcat(baseline, "D AndroidRuntime: Shutting down VM")
    _sync_logcat(candidate, (
        "E AndroidRuntime: FATAL EXCEPTION: main\n"
        "E AndroidRuntime: Process: org.wikipedia.dev, PID: 1234"
    ))

    verdict = evaluate_network_pair(baseline, candidate)

    assert verdict["conclusion"] == "locally_supported"
    assert verdict["baseline"]["outcome"] == "pass"
    assert verdict["candidate"]["faults"] == ["crash_or_anr"]


def test_oracle_detects_duplicate_retry_attempt() -> None:
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    retry_response = next(
        index
        for index, event in enumerate(candidate["network_events"])
        if event["scenario"] == "retry" and event["kind"] == "response_applied"
    )
    candidate["network_events"].insert(
        retry_response,
        {
            "sequence": 10.5,
            "scenario": "retry",
            "kind": "retry_attempt",
            "request_id": "retry-1",
            "attempt": 3,
        },
    )
    _sync_logcat(candidate)

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
    _sync_logcat(faulty, "ActivityManager: ANR in org.wikipedia.dev")
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
    retry_attempt = next(
        event
        for event in candidate["network_events"]
        if event["scenario"] == "retry" and event["kind"] == "retry_attempt"
    )
    retry_attempt["attempt"] = {"unexpected": "shape"}

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
        "system_event_duplicate_step",
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
    elif malformation == "system_event_duplicate_step":
        baseline["system_events"][1]["step_index"] = 0
        candidate["system_events"][1]["step_index"] = 0

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


def test_accepted_journeys_bind_complete_effective_execution_identity() -> None:
    run_record = _ROOT / "docs/runs/2026-07-19-issue-69-network-reliability"
    identity = json.loads(
        (run_record / "effective-execution-identity.json").read_text(
            encoding="utf-8"
        )
    )

    assert identity["identity_status"] == "complete"
    for role in ("baseline", "candidate"):
        journey = json.loads(
            (run_record / role / "journey-result.json").read_text(encoding="utf-8")
        )
        assert journey["effective_execution_identity"] == (
            f"../effective-execution-identity.json#/attempts/{role}"
        )
        consumed = identity["attempts"][role]["consumed_run_spec"]
        run_spec_bytes = (_ROOT / consumed["path"]).read_bytes()
        assert hashlib.sha256(run_spec_bytes).hexdigest() == consumed["sha256"]
        assert identity["attempts"][role]["host"]["worktree"].startswith("/")
        assert identity["attempts"][role]["apk"]["local_sha256"] == (
            identity["attempts"][role]["apk"]["installed_sha256"]
        )

    for agent in identity["agent_roles"].values():
        assert agent["backend"]
        assert agent["requested_model"]
        assert agent["effective_model"]
        assert agent["authoritative_observation_source"]


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
        '07-19 I AIVerifyNetwork: {"sequence":0,"scenario":"fixture",'
        '"kind":"fixture_ready","request_id":"fixture-1",'
        '"content":"issue-69-network-v1"}\n'
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
