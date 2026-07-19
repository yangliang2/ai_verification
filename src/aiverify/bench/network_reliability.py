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
    events = []
    for line in logcat.splitlines():
        match = _NETWORK_EVENT.search(line)
        if match is not None:
            event = json.loads(match.group(1))
            if event.get("scenario") != "fixture":
                events.append(event)
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
    return None


def _bundle_identity_error(bundle: Mapping[str, Any], role: str) -> str | None:
    schema_version = bundle.get("schema_version")
    if schema_version != 1 or isinstance(schema_version, bool):
        return "evidence schema is unsupported"
    if bundle.get("role") != role:
        return "role is invalid"
    fixture_id = bundle.get("fixture_id")
    if not isinstance(fixture_id, str) or not fixture_id:
        return "fixture identity is invalid"
    journey_sha256 = bundle.get("journey_sha256")
    if not isinstance(journey_sha256, str) or _SHA256.fullmatch(journey_sha256) is None:
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
        not isinstance(package, str)
        or not package
        or not isinstance(sha256, str)
        or _SHA256.fullmatch(sha256) is None
    ):
        return "APK identity is invalid"

    if not _system_events_are_well_formed(bundle.get("system_events")):
        return "system-event evidence is invalid"
    return None


def _system_events_are_well_formed(raw: object) -> bool:
    if not isinstance(raw, list) or not raw:
        return False
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
        if event != "wait":
            continue
        try:
            seconds = float(args["seconds"])
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
    if any(name not in checkpoints for name in _REQUIRED_SCENARIOS):
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
    logcat = bundle.get("logcat", "")
    if not isinstance(logcat, str):
        return {"outcome": "inconclusive", "faults": ["evidence_invalid"]}
    package = str(bundle.get("apk", {}).get("package", ""))
    if _has_package_crash_or_anr(logcat, package):
        faults.add("crash_or_anr")

    for name, checkpoint in checkpoints.items():
        if not isinstance(checkpoint, Mapping):
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
    started = [event.get("request_id") for event in ordered if event.get("kind") == "request_started"]
    applied = [event for event in ordered if event.get("kind") == "response_applied"]
    if len(started) >= 2 and applied:
        newest_request = started[-1]
        last_applied = applied[-1]
        terminal = checkpoints["ordered_response"]
        if (
            last_applied.get("request_id") != newest_request
            or terminal.get("content") != last_applied.get("content")
        ):
            faults.add("stale_response_overwrite")

    if not _required_evidence_is_complete(checkpoints, events):
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


def _required_evidence_is_complete(
    checkpoints: Mapping[str, Any], events: list[Mapping[str, Any]]
) -> bool:
    timeout_kinds = {
        event.get("kind")
        for event in events
        if event.get("scenario") == "timeout"
    }
    cancellation_kinds = {
        event.get("kind")
        for event in events
        if event.get("scenario") == "cancellation"
    }
    recovery_responses = [
        event
        for event in events
        if event.get("scenario") == "recovery"
        and event.get("kind") == "response_applied"
    ]
    online_responses = [
        event
        for event in events
        if event.get("scenario") == "online"
        and event.get("kind") == "response_applied"
    ]
    offline_cache = [
        event
        for event in events
        if event.get("scenario") == "offline"
        and event.get("kind") == "cache_shown"
    ]
    retry_responses = [
        event
        for event in events
        if event.get("scenario") == "retry"
        and event.get("kind") == "response_applied"
    ]
    ordered_events = [
        event for event in events if event.get("scenario") == "ordered_response"
    ]
    return (
        bool(online_responses)
        and bool(offline_cache)
        and {"request_timed_out", "request_cancelled"} <= timeout_kinds
        and bool(retry_responses)
        and "request_cancelled" in cancellation_kinds
        and sum(event.get("kind") == "request_started" for event in ordered_events) >= 2
        and any(event.get("kind") == "response_applied" for event in ordered_events)
        and bool(recovery_responses)
    )


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
