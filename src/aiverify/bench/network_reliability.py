"""Fail-closed oracle for the deterministic network-reliability slice."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any


_REQUIRED_SCENARIOS = (
    "online",
    "offline",
    "timeout",
    "retry",
    "cancellation",
    "ordered_response",
    "recovery",
)
_NETWORK_EVENT = re.compile(r"\bAIVerifyNetwork:\s+(\{.*\})$")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_FIXTURE_ID = "issue-69-network-v1"
_JOURNEY_SHA256 = "d9ff0cdec1734f3c2cf6fba05035b2bc53c579aacf9760bba61fb9c3afd4c415"
_PACKAGE = "org.wikipedia.dev"
_EXPECTED_SYSTEM_EVENTS = (
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
)
_EXPECTED_CHECKPOINTS = {
    "online": {
        "state": "content",
        "content": "online-v1",
        "retry_enabled": False,
    },
    "offline": {
        "state": "cached",
        "content": "cached-v1",
        "retry_enabled": False,
    },
    "timeout": {"state": "timeout", "content": "", "retry_enabled": True},
    "retry": {
        "state": "content",
        "content": "retry-v1",
        "retry_enabled": False,
    },
    "cancellation": {
        "state": "cancelled",
        "content": "",
        "retry_enabled": False,
    },
    "recovery": {
        "state": "content",
        "content": "recovered-v3",
        "retry_enabled": False,
    },
}
_EXPECTED_EVENT_CONTENT = {
    ("online", "network_observed", "online-1"): "on",
    ("online", "response_applied", "online-1"): "online-v1",
    ("offline", "network_observed", "offline-1"): "off",
    ("offline", "cache_shown", "offline-1"): "cached-v1",
    ("retry", "response_applied", "retry-1"): "retry-v1",
    ("cancellation", "response_ignored", "cancel-1"): "late-v1",
    ("cancellation", "response_applied", "cancel-1"): "late-v1",
    ("ordered_response", "response_applied", "new"): "new-v2",
    ("ordered_response", "response_ignored", "old"): "old-v1",
    ("ordered_response", "response_applied", "old"): "old-v1",
    ("recovery", "network_observed", "recovery-1"): "on",
    ("recovery", "response_applied", "recovery-1"): "recovered-v3",
}


def build_evidence_bundle(
    *,
    role: str,
    fixture_id: str,
    journey_sha256: str,
    device: Mapping[str, Any],
    apk: Mapping[str, Any],
    system_events: list[Mapping[str, Any]],
    checkpoint_layouts: Mapping[str, Path],
    logcat_path: Path,
) -> dict[str, Any]:
    """Build an oracle bundle from Android layout and structured logcat evidence."""

    checkpoints = {
        name: _checkpoint_from_layout(path)
        for name, path in checkpoint_layouts.items()
    }
    logcat = Path(logcat_path).read_text(encoding="utf-8")
    events = _network_events_from_logcat(logcat)
    if events is None:
        raise ValueError("logcat network markers are missing or malformed")
    return {
        "schema_version": 1,
        "role": role,
        "fixture_id": fixture_id,
        "journey_sha256": journey_sha256,
        "device": dict(device),
        "apk": dict(apk),
        "system_events": [dict(event) for event in system_events],
        "checkpoints": checkpoints,
        "network_events": events,
        "logcat": logcat,
    }


def _checkpoint_from_layout(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"layout must be a list: {path}")
    texts = [
        item.get("text")
        for item in payload
        if isinstance(item, Mapping)
        and isinstance(item.get("text"), str)
        and item["text"].startswith("Fixture ID:")
    ]
    if len(texts) != 1:
        raise ValueError(f"layout must contain exactly one fixture status: {path}")
    fields = {}
    for line in texts[0].splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip().lower().replace(" ", "_")] = value.strip()
    if not all(key in fields for key in ("state", "content", "retry_enabled")):
        raise ValueError(f"fixture status fields are incomplete: {path}")
    if fields["retry_enabled"] not in {"true", "false"}:
        raise ValueError(f"retry_enabled is not boolean text: {path}")
    return {
        "state": fields["state"],
        "content": fields["content"],
        "retry_enabled": fields["retry_enabled"] == "true",
    }


def evaluate_network_pair(baseline: object, candidate: object) -> dict[str, Any]:
    """Evaluate matched baseline/candidate evidence and return one conclusion.

    Missing or contradictory provenance is non-accountable. A supported slice
    requires a clean baseline and at least one machine-detected candidate fault.
    """

    if not isinstance(baseline, Mapping) or not isinstance(candidate, Mapping):
        return _pair_verdict(
            conclusion="non_accountable",
            baseline={"outcome": "not_run", "faults": []},
            candidate={"outcome": "not_run", "faults": []},
            reason="evidence bundle must be a JSON object",
        )

    mismatch = _matched_pair_error(baseline, candidate)
    if mismatch is not None:
        return _pair_verdict(
            conclusion="non_accountable",
            baseline={"outcome": "not_run", "faults": []},
            candidate={"outcome": "not_run", "faults": []},
            reason=mismatch,
        )

    baseline_verdict = _judge_bundle(baseline)
    candidate_verdict = _judge_bundle(candidate)
    if (
        "evidence_invalid" in baseline_verdict["faults"]
        or "evidence_invalid" in candidate_verdict["faults"]
    ):
        conclusion = "non_accountable"
        reason = "required network evidence is missing or malformed"
    elif baseline_verdict["outcome"] != "pass":
        conclusion = "locally_rejected"
        reason = "baseline did not demonstrate graceful network behavior"
    elif candidate_verdict["outcome"] != "fail":
        conclusion = "locally_rejected"
        reason = "candidate fault escaped the network oracle"
    else:
        conclusion = "locally_supported"
        reason = "matched baseline passed and candidate fault was detected"
    return _pair_verdict(
        conclusion=conclusion,
        baseline=baseline_verdict,
        candidate=candidate_verdict,
        reason=reason,
    )


def _pair_verdict(
    *,
    conclusion: str,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "conclusion": conclusion,
        "reason": reason,
        "baseline": baseline,
        "candidate": candidate,
        "claims": {
            "detection_rate": False,
            "goldset": False,
            "upstream_acceptance": False,
        },
    }


def _matched_pair_error(
    baseline: Mapping[str, Any], candidate: Mapping[str, Any]
) -> str | None:
    for role, bundle in (("baseline", baseline), ("candidate", candidate)):
        error = _bundle_identity_error(bundle, role)
        if error is not None:
            return f"{role} {error}"
    for field in ("fixture_id", "journey_sha256", "device", "system_events"):
        if baseline.get(field) != candidate.get(field):
            return f"matched-pair field differs: {field}"
    if not _has_required_network_transitions(baseline.get("system_events")):
        return "required network transition evidence is missing"
    if baseline["apk"]["package"] != candidate["apk"]["package"]:
        return "matched-pair package differs"
    if baseline["apk"]["sha256"] == candidate["apk"]["sha256"]:
        return "baseline/candidate APK identities are identical"
    return None


def _bundle_identity_error(bundle: Mapping[str, Any], role: str) -> str | None:
    schema_version = bundle.get("schema_version")
    if schema_version != 1 or isinstance(schema_version, bool):
        return "evidence schema is unsupported"
    if bundle.get("role") != role:
        return "role is invalid"
    fixture_id = bundle.get("fixture_id")
    if fixture_id != _FIXTURE_ID:
        return "fixture identity is invalid"
    journey_sha256 = bundle.get("journey_sha256")
    if journey_sha256 != _JOURNEY_SHA256:
        return "Journey identity is invalid"

    device = bundle.get("device")
    if not isinstance(device, Mapping):
        return "device identity is invalid"
    serial = device.get("serial")
    api = device.get("api")
    avd = device.get("avd")
    if (
        not isinstance(serial, str)
        or not serial
        or not isinstance(api, int)
        or isinstance(api, bool)
        or api <= 0
        or not isinstance(avd, str)
        or not avd
    ):
        return "device identity is invalid"

    apk = bundle.get("apk")
    if not isinstance(apk, Mapping):
        return "APK identity is invalid"
    package = apk.get("package")
    sha256 = apk.get("sha256")
    if (
        package != _PACKAGE
        or not isinstance(sha256, str)
        or _SHA256.fullmatch(sha256) is None
    ):
        return "APK identity is invalid"

    system_events = bundle.get("system_events")
    if (
        not _system_events_are_well_formed(system_events)
        or tuple(system_events) != _EXPECTED_SYSTEM_EVENTS
    ):
        return "system-event evidence is invalid"
    return None


def _system_events_are_well_formed(raw: object) -> bool:
    if not isinstance(raw, list) or not raw:
        return False
    previous_step_index = -1
    for item in raw:
        if not isinstance(item, Mapping):
            return False
        step_index = item.get("step_index")
        event = item.get("event")
        args = item.get("args")
        if (
            not isinstance(step_index, int)
            or isinstance(step_index, bool)
            or step_index < 0
            or not isinstance(event, str)
            or event not in {"network_off", "network_on", "wait"}
            or not isinstance(args, Mapping)
        ):
            return False
        if step_index <= previous_step_index:
            return False
        previous_step_index = step_index
        if event != "wait":
            continue
        try:
            raw_seconds = args["seconds"]
            if isinstance(raw_seconds, bool):
                return False
            seconds = float(raw_seconds)
        except (KeyError, TypeError, ValueError):
            return False
        expected_network = args.get("expect_network")
        expected_resumed = args.get("expect_resumed")
        if (
            not math.isfinite(seconds)
            or not 0 <= seconds <= 60
            or (expected_network is None and expected_resumed is None)
            or (
                expected_network is not None
                and (
                    not isinstance(expected_network, str)
                    or expected_network not in {"off", "on"}
                )
            )
            or (
                expected_resumed is not None
                and (
                    not isinstance(expected_resumed, str)
                    or expected_resumed not in {"target", "other"}
                )
            )
        ):
            return False
    return True


def _has_required_network_transitions(raw: object) -> bool:
    if not isinstance(raw, list) or not all(isinstance(item, Mapping) for item in raw):
        return False
    expected = (
        ("network_off", None),
        ("wait", "off"),
        ("network_on", None),
        ("wait", "on"),
    )
    cursor = 0
    for item in raw:
        event, network = expected[cursor]
        args = item.get("args")
        if item.get("event") != event or not isinstance(args, Mapping):
            continue
        if network is not None and args.get("expect_network") != network:
            continue
        cursor += 1
        if cursor == len(expected):
            return True
    return False


def _judge_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    checkpoints = bundle.get("checkpoints")
    events = bundle.get("network_events")
    if not isinstance(checkpoints, Mapping) or not isinstance(events, list):
        return {"outcome": "inconclusive", "faults": ["evidence_invalid"]}
    if set(checkpoints) != set(_REQUIRED_SCENARIOS):
        return {"outcome": "inconclusive", "faults": ["evidence_invalid"]}
    if not all(isinstance(event, Mapping) for event in events):
        return {"outcome": "inconclusive", "faults": ["evidence_invalid"]}
    if any(
        not isinstance(event.get("scenario"), str)
        or not isinstance(event.get("kind"), str)
        or not isinstance(event.get("request_id"), str)
        or not event.get("request_id")
        or ("content" in event and not isinstance(event.get("content"), str))
        for event in events
    ):
        return {"outcome": "inconclusive", "faults": ["evidence_invalid"]}
    if any(
        (
            event.get("scenario"),
            event.get("kind"),
            event.get("request_id"),
        )
        in _EXPECTED_EVENT_CONTENT
        and "content" not in event
        for event in events
    ):
        return {"outcome": "inconclusive", "faults": ["evidence_invalid"]}
    sequences = [event.get("sequence") for event in events]
    if (
        not all(
            isinstance(value, int | float)
            and not isinstance(value, bool)
            and math.isfinite(value)
            for value in sequences
        )
        or any(left >= right for left, right in zip(sequences, sequences[1:]))
    ):
        return {"outcome": "inconclusive", "faults": ["evidence_invalid"]}

    faults: set[str] = set()
    logcat = bundle.get("logcat")
    if not isinstance(logcat, str) or not logcat.strip():
        return {"outcome": "inconclusive", "faults": ["evidence_invalid"]}
    extracted_events = _network_events_from_logcat(logcat)
    if extracted_events is None or extracted_events != events:
        return {"outcome": "inconclusive", "faults": ["evidence_invalid"]}
    package = str(bundle.get("apk", {}).get("package", ""))
    if _has_package_crash_or_anr(logcat, package):
        faults.add("crash_or_anr")

    for name, checkpoint in checkpoints.items():
        if not isinstance(checkpoint, Mapping):
            return {"outcome": "inconclusive", "faults": ["evidence_invalid"]}
        if set(checkpoint) != {"state", "content", "retry_enabled"}:
            return {"outcome": "inconclusive", "faults": ["evidence_invalid"]}
        state = checkpoint.get("state")
        if (
            not isinstance(state, str)
            or (
                "content" in checkpoint
                and not isinstance(checkpoint.get("content"), str)
            )
            or (
                "retry_enabled" in checkpoint
                and not isinstance(checkpoint.get("retry_enabled"), bool)
            )
        ):
            return {"outcome": "inconclusive", "faults": ["evidence_invalid"]}
        if state in {"blank", "error"}:
            faults.add("blank_or_error_state")
        if state in {"content", "cached"} and not checkpoint.get("content"):
            faults.add("blank_or_error_state")

    for scenario, expected in _EXPECTED_CHECKPOINTS.items():
        checkpoint = checkpoints[scenario]
        if checkpoint != expected:
            state = checkpoint.get("state")
            if state in {"blank", "error"} or (
                state in {"content", "cached"} and not checkpoint.get("content")
            ):
                continue
            if scenario in {"offline", "recovery"} and checkpoint.get("content"):
                faults.add("stale_data")
            else:
                faults.add("scenario_contract_failed")

    retry_attempts = [
        event.get("attempt")
        for event in events
        if event.get("scenario") == "retry" and event.get("kind") == "retry_attempt"
    ]
    if not all(
        isinstance(attempt, int) and not isinstance(attempt, bool)
        for attempt in retry_attempts
    ):
        return {"outcome": "inconclusive", "faults": ["evidence_invalid"]}
    if len(retry_attempts) > 3:
        faults.add("retry_storm")
    if len(retry_attempts) != len(set(retry_attempts)):
        faults.add("duplicate_retry")
    elif retry_attempts != list(range(1, len(retry_attempts) + 1)):
        faults.add("retry_sequence_invalid")

    cancellation = [
        event
        for event in events
        if event.get("scenario") == "cancellation"
    ]
    cancelled_requests = {
        event.get("request_id")
        for event in cancellation
        if event.get("kind") == "request_cancelled"
    }
    if any(
        event.get("kind") == "response_applied"
        and event.get("request_id") in cancelled_requests
        for event in cancellation
    ):
        faults.add("cancellation_failed")

    ordered = [
        event
        for event in events
        if event.get("scenario") == "ordered_response"
    ]
    terminal = checkpoints["ordered_response"]
    if terminal.get("state") != "content" or terminal.get("retry_enabled") is not False:
        faults.add("scenario_contract_failed")
    started = [event.get("request_id") for event in ordered if event.get("kind") == "request_started"]
    applied = [event for event in ordered if event.get("kind") == "response_applied"]
    if len(started) >= 2 and applied:
        newest_request = started[-1]
        last_applied = applied[-1]
        if (
            last_applied.get("request_id") != newest_request
            or terminal.get("content") != last_applied.get("content")
        ):
            faults.add("stale_response_overwrite")

    faults.update(_event_semantic_faults(events))

    if not _required_evidence_is_complete(events):
        faults.add("evidence_invalid")

    ordered_faults = sorted(faults)
    if ordered_faults == ["evidence_invalid"]:
        outcome = "inconclusive"
    else:
        outcome = "fail" if faults - {"evidence_invalid"} else "pass"
    return {"outcome": outcome, "faults": ordered_faults}


def _has_package_crash_or_anr(logcat: str, package: str) -> bool:
    if not package:
        return False
    escaped = re.escape(package)
    fatal = "FATAL EXCEPTION" in logcat and re.search(
        rf"\bProcess:\s*{escaped}(?:,|\s|$)", logcat
    )
    anr = re.search(rf"\bANR in\s+{escaped}(?:\s|$)", logcat)
    died = re.search(rf"\b{escaped}\b.*\bhas died\b", logcat)
    return bool(fatal or anr or died)


def _network_events_from_logcat(logcat: str) -> list[dict[str, Any]] | None:
    tagged_events: list[dict[str, Any]] = []
    for line in logcat.splitlines():
        if "AIVerifyNetwork:" not in line:
            continue
        match = _NETWORK_EVENT.search(line)
        if match is None:
            return None
        try:
            event = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
        if not isinstance(event, dict):
            return None
        tagged_events.append(event)
    if len(tagged_events) < 2:
        return None
    fixture = tagged_events[0]
    if (
        fixture.get("scenario") != "fixture"
        or fixture.get("kind") != "fixture_ready"
        or fixture.get("request_id") != "fixture-1"
        or fixture.get("content") != _FIXTURE_ID
        or any(event.get("scenario") == "fixture" for event in tagged_events[1:])
    ):
        return None
    sequences = [event.get("sequence") for event in tagged_events]
    if (
        not all(
            isinstance(sequence, int | float)
            and not isinstance(sequence, bool)
            and math.isfinite(sequence)
            for sequence in sequences
        )
        or any(left >= right for left, right in zip(sequences, sequences[1:]))
        or sequences[1] != sequences[0] + 1
    ):
        return None
    return tagged_events[1:]


def _required_evidence_is_complete(events: list[Mapping[str, Any]]) -> bool:
    scenario_rank = {
        scenario: rank for rank, scenario in enumerate(_REQUIRED_SCENARIOS)
    }
    if any(event.get("scenario") not in scenario_rank for event in events):
        return False
    observed_ranks = [scenario_rank[event["scenario"]] for event in events]
    if any(
        left > right for left, right in zip(observed_ranks, observed_ranks[1:])
    ):
        return False

    online = _scenario_events(events, "online")
    offline = _scenario_events(events, "offline")
    timeout = _scenario_events(events, "timeout")
    retry = _scenario_events(events, "retry")
    cancellation = _scenario_events(events, "cancellation")
    ordered = _scenario_events(events, "ordered_response")
    recovery = _scenario_events(events, "recovery")

    retry_attempts = [event for event in retry if event.get("kind") == "retry_attempt"]
    retry_complete = (
        len(retry_attempts) >= 3
        and len(retry) == len(retry_attempts) + 1
        and all(
            event.get("request_id") == "retry-1" for event in retry_attempts
        )
        and _matches_event(retry[-1], "response_applied", "retry-1")
    )
    cancellation_complete = (
        len(cancellation) == 3
        and _matches_event(cancellation[0], "request_started", "cancel-1")
        and _matches_event(cancellation[1], "request_cancelled", "cancel-1")
        and all(
            event.get("kind") in {"response_ignored", "response_applied"}
            and event.get("request_id") == "cancel-1"
            for event in cancellation[2:]
        )
    )
    ordered_complete = (
        len(ordered) == 4
        and _matches_event(ordered[0], "request_started", "old")
        and _matches_event(ordered[1], "request_started", "new")
        and _matches_event(ordered[2], "response_applied", "new")
        and all(
            event.get("kind") in {"response_ignored", "response_applied"}
            and event.get("request_id") == "old"
            for event in ordered[3:]
        )
    )
    return (
        _matches_scenario(
            online,
            (("network_observed", "online-1"), ("response_applied", "online-1")),
        )
        and _matches_scenario(
            offline,
            (("network_observed", "offline-1"), ("cache_shown", "offline-1")),
        )
        and _matches_scenario(
            timeout,
            (
                ("request_started", "timeout-1"),
                ("request_timed_out", "timeout-1"),
                ("request_cancelled", "timeout-1"),
            ),
        )
        and retry_complete
        and cancellation_complete
        and ordered_complete
        and _matches_scenario(
            recovery,
            (
                ("network_observed", "recovery-1"),
                ("response_applied", "recovery-1"),
            ),
        )
    )


def _scenario_events(
    events: list[Mapping[str, Any]], scenario: str
) -> list[Mapping[str, Any]]:
    return [event for event in events if event.get("scenario") == scenario]


def _matches_event(event: Mapping[str, Any], kind: str, request_id: str) -> bool:
    return event.get("kind") == kind and event.get("request_id") == request_id


def _matches_scenario(
    events: list[Mapping[str, Any]], expected: tuple[tuple[str, str], ...]
) -> bool:
    return len(events) == len(expected) and all(
        _matches_event(event, kind, request_id)
        for event, (kind, request_id) in zip(events, expected)
    )


def _event_semantic_faults(events: list[Mapping[str, Any]]) -> set[str]:
    faults: set[str] = set()
    for event in events:
        key = (event.get("scenario"), event.get("kind"), event.get("request_id"))
        expected = _EXPECTED_EVENT_CONTENT.get(key)
        if expected is None or event.get("content") == expected:
            continue
        if event.get("scenario") in {"offline", "recovery"}:
            faults.add("stale_data")
        else:
            faults.add("scenario_contract_failed")
    return faults


def main(argv: list[str] | None = None) -> int:
    """Evaluate two evidence bundles and persist exactly one conclusion."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    conclusion: dict[str, Any]
    try:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        conclusion = _pair_verdict(
            conclusion="non_accountable",
            baseline={"outcome": "not_run", "faults": []},
            candidate={"outcome": "not_run", "faults": []},
            reason="baseline evidence could not be parsed",
        )
    else:
        try:
            candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            conclusion = _pair_verdict(
                conclusion="non_accountable",
                baseline={"outcome": "not_run", "faults": []},
                candidate={"outcome": "not_run", "faults": []},
                reason="candidate evidence could not be parsed",
            )
        else:
            conclusion = evaluate_network_pair(baseline, candidate)
    args.output.write_text(
        json.dumps(conclusion, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "locally_supported": 0,
        "locally_rejected": 1,
        "non_accountable": 2,
    }[conclusion["conclusion"]]


if __name__ == "__main__":
    raise SystemExit(main())
