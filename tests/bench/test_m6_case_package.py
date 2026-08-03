"""Contract tests for the common M6 Qualification Case Package."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from aiverify.bench.m6_case_package import (
    CasePackageValidationError,
    aggregate_packages,
    load_case_package,
    render_markdown,
    render_structured,
    self_validate_schema,
)


MANIFEST = Path("bench/m6/m6-qualification-v1.yaml")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(manifest_ref: dict[str, str]) -> dict[str, str]:
    return dict(manifest_ref)


def _base_package(repo_root: Path, slot_id: str) -> dict:
    manifest_path = repo_root / MANIFEST
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    slot = next(item for item in manifest["slots"] if item["id"] == slot_id)
    ref = {"path": MANIFEST.as_posix(), "sha256": _sha(manifest_path)}
    final_revision = (
        slot["historical"]["fixed_revision"]
        if slot["track"] == "historical"
        else "a" * 40
    )
    if final_revision == slot["source"]["base_revision"]:
        final_revision = "b" * 40
    started = "2026-08-03T18:00:00Z"
    finished = "2026-08-03T18:00:01Z"
    attempt_id = f"attempt-{slot_id.lower()}"
    attempt_ref = _artifact(ref)
    attempt = {
        "attempt_id": attempt_id,
        "lane_id": f"{slot_id}-baseline-01",
        "attempt_number": 1,
        "evidence_root": f"docs/runs/m6/{slot_id.lower()}",
        "execution_record": attempt_ref,
        "provenance": _artifact(ref),
        "verdict": _artifact(ref),
        "process": {"exit_code": 0},
        "accountability": "accountable",
        "retry_eligible": False,
        "quarantined": False,
        "artifacts": [attempt_ref, _artifact(ref), _artifact(ref)],
        "started_at": started,
        "finished_at": finished,
    }
    identity = {
        "id": f"agent-{slot_id}",
        "role": "verification-agent",
        "backend": "codex",
        "model": "gpt-test",
        "session_id": f"session-{slot_id}",
    }
    return {
        "schema_version": 1,
        "package_id": f"m6-{slot_id.lower()}",
        "cohort": {
            "manifest": ref,
            "cohort_id": manifest["cohort_id"],
            "slot_id": slot_id,
            "track": slot["track"],
        },
        "source": {
            "repository_url": slot["source"]["repository_url"],
            "task_url": slot["source"]["task_url"],
            "base_revision": slot["source"]["base_revision"],
            "final_diff": {"revision": final_revision, "patch": _artifact(ref)},
        },
        "contract": {
            "primary_behavior": slot["primary_behavior"],
            "run_spec": _artifact(ref),
            "journey": _artifact(ref),
            "oracle": _artifact(ref),
            "environment": _artifact(ref),
        },
        "execution_identity": {
            "host": {"id": "host-1", "os": "Darwin", "commit": "c" * 40, "patch": _artifact(ref)},
            "tools": {"python": "3.14", "git": "2.50"},
            "backend": {"name": "codex", "version": "1", "model": "gpt-test"},
            "build": {"revision": final_revision, "variant": "debug", "duration_seconds": 1.0, "log": _artifact(ref)},
            "deployment": {
                "package": "org.example.app",
                "activity": "org.example.app.MainActivity",
                "apk": _artifact(ref),
                "installed_binary": _artifact(ref),
                "deployment_receipt": _artifact(ref),
            },
            "device": {
                "serial": "emulator-5554",
                "api_level": 35,
                "avd": "test-avd",
                "model": "test-device",
                "locale": "en-US",
                "orientation": "portrait",
            },
        },
        "attempt_inventory": {
            "max_attempts_per_lane": 2,
            "discovered_attempt_ids": [attempt_id],
            "quarantined_attempt_ids": [],
            "ledger": [
                {"event_id": f"{attempt_id}-start", "event": "started", "attempt_id": attempt_id, "lane_id": attempt["lane_id"], "attempt_number": 1, "occurred_at": started, "process_exit_code": None, "accountability": None},
                {"event_id": f"{attempt_id}-finish", "event": "finished", "attempt_id": attempt_id, "lane_id": attempt["lane_id"], "attempt_number": 1, "occurred_at": finished, "process_exit_code": 0, "accountability": "accountable"},
            ],
            "attempts": [attempt],
        },
        "verification": {
            "agent": identity,
            "conclusion": "locally_supported",
            "verdict": _artifact(ref),
            "oracle_output": _artifact(ref),
            "frozen_at": "2026-08-03T18:00:02Z",
        },
        "adjudication": {
            "agent": {**identity, "id": f"auditor-{slot_id}", "session_id": f"audit-{slot_id}"},
            "conclusion": "locally_supported",
            "agreement": True,
            "evidence": _artifact(ref),
        },
        "timing": {"duration_seconds": 2.0, "interventions": [], "gaps": []},
        "claim_boundary": {
            "local_only": True,
            "allowed": ["local_conclusions", "accountability", "operational_metrics"],
            "forbidden": [
                "combined_track_denominator", "detection_rate", "false_positive_rate",
                "confidence_claim", "prospective_goldset", "general_android_coverage", "upstream_acceptance",
            ],
        },
    }


def _write_package(root: Path, package: dict) -> Path:
    path = root / f"{package['package_id']}.json"
    path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
    return path


def test_schema_is_self_validating() -> None:
    self_validate_schema()


def test_complete_package_validates_without_reinterpreting_oracle(tmp_path: Path) -> None:
    package_path = _write_package(tmp_path, _base_package(Path.cwd(), "H-01"))
    package = load_case_package(
        package_path,
        repo_root=Path.cwd(),
        verify_references=False,
    )
    assert package.slot_id == "H-01"
    assert package.attempt_inventory.attempts[0]["accountability"] == "accountable"


@pytest.mark.parametrize(
    ("path", "message"),
    [
        (("source", "final_diff"), "final_diff"),
        (("contract", "run_spec"), "run_spec"),
        (("execution_identity", "backend", "model"), "backend"),
        (("execution_identity", "deployment", "apk"), "deployment"),
        (("execution_identity", "device", "serial"), "device"),
        (("verification", "agent"), "verification"),
        (("adjudication", "agent"), "adjudication"),
    ],
)
def test_required_identity_omissions_fail(tmp_path: Path, path: tuple[str, ...], message: str) -> None:
    package = _base_package(Path.cwd(), "H-01")
    target = package
    for part in path[:-1]:
        target = target[part]
    del target[path[-1]]
    with pytest.raises(CasePackageValidationError, match=message):
        load_case_package(_write_package(tmp_path, package), repo_root=Path.cwd(), verify_references=False)


def test_ledger_hidden_attempt_and_forbidden_claims_fail(tmp_path: Path) -> None:
    package = _base_package(Path.cwd(), "H-01")
    package["attempt_inventory"]["discovered_attempt_ids"].append("hidden")
    with pytest.raises(CasePackageValidationError, match="discovered attempt"):
        load_case_package(_write_package(tmp_path, package), repo_root=Path.cwd(), verify_references=False)

    package = _base_package(Path.cwd(), "H-01")
    package["claim_boundary"]["allowed"].append("detection_rate")
    with pytest.raises(CasePackageValidationError, match="allowed claim"):
        load_case_package(_write_package(tmp_path, package), repo_root=Path.cwd(), verify_references=False)


def test_checksum_tampering_fails_closed(tmp_path: Path) -> None:
    package = _base_package(Path.cwd(), "H-01")
    package["cohort"]["manifest"]["sha256"] = "0" * 64
    with pytest.raises(CasePackageValidationError, match="checksum mismatch"):
        load_case_package(_write_package(tmp_path, package), repo_root=Path.cwd())


def test_contradictory_adjudication_and_post_accountable_retry_fail(tmp_path: Path) -> None:
    package = _base_package(Path.cwd(), "H-01")
    package["adjudication"]["conclusion"] = "locally_rejected"
    with pytest.raises(CasePackageValidationError, match="adjudication conclusion"):
        load_case_package(_write_package(tmp_path, package), repo_root=Path.cwd(), verify_references=False)

    package = _base_package(Path.cwd(), "H-01")
    original = package["attempt_inventory"]["attempts"][0]
    retry = copy.deepcopy(original)
    retry["attempt_id"] = "attempt-retry"
    retry["attempt_number"] = 2
    retry["retry_eligible"] = False
    retry["started_at"] = "2026-08-03T18:00:02Z"
    retry["finished_at"] = "2026-08-03T18:00:03Z"
    package["attempt_inventory"]["attempts"].append(retry)
    package["attempt_inventory"]["discovered_attempt_ids"].append("attempt-retry")
    package["attempt_inventory"]["ledger"].extend([
        {"event_id": "retry-start", "event": "started", "attempt_id": "attempt-retry", "lane_id": original["lane_id"], "attempt_number": 2, "occurred_at": retry["started_at"], "process_exit_code": None, "accountability": None},
        {"event_id": "retry-finish", "event": "finished", "attempt_id": "attempt-retry", "lane_id": original["lane_id"], "attempt_number": 2, "occurred_at": retry["finished_at"], "process_exit_code": 0, "accountability": "accountable"},
    ])
    with pytest.raises(CasePackageValidationError, match="retries after an accountable"):
        load_case_package(_write_package(tmp_path, package), repo_root=Path.cwd(), verify_references=False)


def test_aggregate_is_exactly_six_and_renders_deterministically(tmp_path: Path) -> None:
    package_paths = [
        _write_package(tmp_path, _base_package(Path.cwd(), slot_id))
        for slot_id in ("H-01", "H-02", "H-03", "P-01", "P-02", "P-03")
    ]
    aggregate = aggregate_packages(
        package_paths,
        manifest_path=MANIFEST,
        repo_root=Path.cwd(),
        verify_references=False,
    )
    structured = render_structured(aggregate)
    markdown = render_markdown(aggregate)
    assert structured == render_structured(aggregate)
    assert markdown == render_markdown(aggregate)
    assert '"historical"' in structured and '"prospective"' in structured
    assert "detection_rate" not in structured.lower()
    assert "false_positive_rate" not in markdown.lower()

    with pytest.raises(CasePackageValidationError, match="exactly 6"):
        aggregate_packages(package_paths[:-1], manifest_path=MANIFEST, repo_root=Path.cwd(), verify_references=False)
