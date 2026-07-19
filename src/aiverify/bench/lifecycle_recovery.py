"""Machine oracle for the lifecycle and backup-recovery capability slice."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aiverify.runner.execution_identity import (
    ExecutionIdentityError,
    verify_execution_provenance,
)
from aiverify.runner.execution_record import (
    is_execution_record_accountable,
    load_execution_record,
    write_json_artifact,
)


@dataclass(frozen=True)
class LifecycleRecoveryContract:
    """Known-good literals supplied by the committed deterministic fixture."""

    sentinel: str
    pre_restore_schema: str
    restored_schema: str
    pre_restore_revision: str
    restored_revision: str
    pre_restore_migration: str
    restored_migration: str
    reset_sentinel: str
    sentinel_resource: str = "fixture_sentinel"
    schema_resource: str = "fixture_schema_version"
    revision_resource: str = "fixture_revision"
    migration_resource: str = "fixture_migration_status"


def load_lifecycle_recovery_contract(path: str | Path) -> LifecycleRecoveryContract:
    """Load the stable fixture literals and resource IDs from a contract file."""
    document = _load_json_object(Path(path), label="lifecycle recovery contract")
    state = _mapping(document, "state")
    fixture = _mapping(document, "fixture")
    resources = _mapping(fixture, "resources")
    return LifecycleRecoveryContract(
        sentinel=_string(state, "sentinel"),
        pre_restore_schema=_string(state, "pre_restore_schema"),
        restored_schema=_string(state, "restored_schema"),
        pre_restore_revision=_string(state, "pre_restore_revision"),
        restored_revision=_string(state, "restored_revision"),
        pre_restore_migration=_string(state, "pre_restore_migration"),
        restored_migration=_string(state, "restored_migration"),
        reset_sentinel=_string(state, "reset_sentinel"),
        sentinel_resource=_string(resources, "sentinel"),
        schema_resource=_string(resources, "schema_version"),
        revision_resource=_string(resources, "revision"),
        migration_resource=_string(resources, "migration_status"),
    )


def judge_lifecycle_recovery(
    *,
    contract: LifecycleRecoveryContract,
    initial_layout: str,
    rotated_layout: str,
    process_restored_layout: str,
    backup_restored_layout: str,
    process_event: dict[str, Any],
    backup_event: dict[str, Any],
    crash_detected: bool,
) -> dict[str, Any]:
    """Return one fail-closed conclusion for a lifecycle recovery attempt."""
    try:
        observations = {
            "initial": _read_observation(initial_layout, contract),
            "rotation": _read_observation(rotated_layout, contract),
            "process_death": _read_observation(process_restored_layout, contract),
            "backup_restore": _read_observation(backup_restored_layout, contract),
        }
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        return {
            "schema_version": 1,
            "conclusion": "non_accountable",
            "classification": "non_accountable",
            "reason": "layout_evidence_missing_or_invalid",
            "accountable": False,
            "observations": {},
            "evidence_error": f"{type(error).__name__}: {error}",
        }
    pre_restore = {
        "sentinel": contract.sentinel,
        "schema_version": contract.pre_restore_schema,
        "revision": contract.pre_restore_revision,
        "migration_status": contract.pre_restore_migration,
    }
    restored = {
        "sentinel": contract.sentinel,
        "schema_version": contract.restored_schema,
        "revision": contract.restored_revision,
        "migration_status": contract.restored_migration,
    }
    process_evidence = process_event.get("evidence", {})
    if not isinstance(process_evidence, dict):
        process_evidence = {}
    before_pids = _pid_set(process_evidence.get("before_pids"))
    after_pids = _pid_set(process_evidence.get("after_pids"))
    backup_evidence = backup_event.get("evidence", {})
    if not isinstance(backup_evidence, dict):
        backup_evidence = {}
    process_is_accountable = (
        process_event.get("status") == "passed"
        and bool(before_pids)
        and bool(after_pids)
        and before_pids.isdisjoint(after_pids)
        and process_evidence.get("background_status") == "success"
        and bool(process_evidence.get("background_resumed_package"))
        and process_evidence.get("target_resumed_after_home") is False
        and process_evidence.get("kill_status") == "success"
        and process_evidence.get("process_absent_after_kill") is True
        and process_evidence.get("relaunch_status") == "success"
        and bool(process_evidence.get("foreground_resumed_package"))
        and process_evidence.get("target_resumed_after_relaunch") is True
    )
    previous_transport = backup_evidence.get("previous_transport")
    backup_was_enabled = backup_evidence.get("backup_was_enabled")
    backup_is_accountable = (
        backup_event.get("status") == "passed"
        and backup_evidence.get("backup_status") == "success"
        and backup_evidence.get("clear_data_status") == "success"
        and backup_evidence.get("clear_data_output") == "Success"
        and backup_evidence.get("restore_status") == "success"
        and bool(backup_evidence.get("restore_token"))
        and bool(backup_evidence.get("transport"))
        and bool(previous_transport)
        and isinstance(backup_was_enabled, bool)
        and backup_evidence.get("cleanup_status") == "success"
        and backup_evidence.get("cleanup_transport") == previous_transport
        and backup_evidence.get("cleanup_backup_enabled") is backup_was_enabled
    )
    events_are_accountable = process_is_accountable and backup_is_accountable
    pre_restore_is_exact = all(
        observations[phase] == pre_restore
        for phase in ("initial", "rotation", "process_death")
    )
    correct = (
        events_are_accountable
        and pre_restore_is_exact
        and observations["backup_restore"] == restored
    )
    state_is_missing = any(
        value is None
        for observation in observations.values()
        for value in observation.values()
    )
    if crash_detected and events_are_accountable:
        conclusion = "locally_rejected"
        classification = "crash"
        reason = "crash_detected"
        accountable = True
    elif events_are_accountable and state_is_missing:
        conclusion = "locally_rejected"
        classification = "state_loss"
        reason = "required_state_missing"
        accountable = True
    elif (
        events_are_accountable
        and pre_restore_is_exact
        and observations["backup_restore"]["sentinel"] == contract.reset_sentinel
    ):
        conclusion = "locally_rejected"
        classification = "silent_reset"
        reason = "restored_state_matches_known_defaults"
        accountable = True
    elif (
        events_are_accountable
        and pre_restore_is_exact
        and observations["backup_restore"] == pre_restore
    ):
        conclusion = "locally_rejected"
        classification = "stale_state"
        reason = "restored_state_remains_at_pre_migration_version"
        accountable = True
    elif not crash_detected and correct:
        conclusion = "locally_supported"
        classification = "correct_restoration"
        reason = "exact_state_continuity_and_migration_observed"
        accountable = True
    else:
        conclusion = "non_accountable"
        classification = "non_accountable"
        if not process_is_accountable:
            reason = "process_identity_missing_or_unchanged"
        elif not backup_is_accountable:
            reason = "backup_restore_evidence_missing_or_failed"
        else:
            reason = "state_outcome_unclassified"
        accountable = False
    return {
        "schema_version": 1,
        "conclusion": conclusion,
        "classification": classification,
        "reason": reason,
        "accountable": accountable,
        "observations": observations,
    }


def judge_lifecycle_recovery_run(
    *,
    run_dir: str | Path,
    contract_path: str | Path,
) -> dict[str, Any]:
    """Replay a completed runner attempt and return one fail-closed conclusion."""
    run_root = Path(run_dir).resolve()
    contract_source = Path(contract_path).resolve()
    try:
        contract_document = _load_json_object(
            contract_source,
            label="lifecycle recovery contract",
        )
        contract = load_lifecycle_recovery_contract(contract_source)
        record = load_execution_record(run_root / "execution-record.json")
        if not is_execution_record_accountable(record):
            raise ValueError("ExecutionRecord is not completed and accountable")

        runner_verdict = _load_json_object(
            run_root / "verdict.json",
            label="runner verdict",
        )
        if runner_verdict.get("scenario") != record["scenario"]:
            raise ValueError("runner verdict scenario contradicts ExecutionRecord")
        execution = runner_verdict.get("execution")
        if not isinstance(execution, dict) or execution.get("status") != "completed":
            raise ValueError("runner verdict is not completed")
        verify_execution_provenance(
            runner_verdict.get("execution_provenance"),
            attempt_id=record["attempt_id"],
            scenario=record["scenario"],
            base_dir=run_root,
        )

        checkpoint_names = _mapping(contract_document, "checkpoints")
        layout_paths = {
            phase: run_root
            / "artifacts"
            / _safe_relative_string(checkpoint_names, phase)
            / "layout.json"
            for phase in (
                "initial",
                "rotated",
                "process_restored",
                "backup_restored",
            )
        }
        event_paths = _mapping(contract_document, "system_events")
        events = {
            event: _load_json_object(
                run_root / "artifacts" / _safe_relative_string(event_paths, event),
                label=f"{event} system event",
            )
            for event in ("rotate", "process_death", "backup_restore")
        }
        for expected_event, event_payload in events.items():
            if (
                event_payload.get("schema_version") != 1
                or event_payload.get("event") != expected_event
                or event_payload.get("status") != "passed"
            ):
                raise ValueError(f"{expected_event} event evidence is contradictory")

        injected_events = runner_verdict.get("injected_events")
        if not isinstance(injected_events, list) or [
            item.get("event") if isinstance(item, dict) else None
            for item in injected_events
        ] != ["rotate", "process_death", "backup_restore"]:
            raise ValueError("runner event order is missing or contradictory")
        expected_event_refs = [
            f"artifacts/{_safe_relative_string(event_paths, event)}"
            for event in ("rotate", "process_death", "backup_restore")
        ]
        evidence_refs = runner_verdict.get("system_event_evidence")
        if evidence_refs != expected_event_refs:
            raise ValueError("runner system-event evidence binding is incomplete")
        if record["evidence_refs"].get("system_events") != expected_event_refs:
            raise ValueError(
                "ExecutionRecord system-event evidence binding is incomplete"
            )

        l1 = runner_verdict.get("l1")
        if not isinstance(l1, dict) or l1.get("outcome") not in {
            "pass",
            "fail",
            "inconclusive",
        }:
            raise ValueError("runner L1 crash verdict is missing or invalid")

        verdict = judge_lifecycle_recovery(
            contract=contract,
            initial_layout=layout_paths["initial"].read_text(encoding="utf-8"),
            rotated_layout=layout_paths["rotated"].read_text(encoding="utf-8"),
            process_restored_layout=layout_paths["process_restored"].read_text(
                encoding="utf-8"
            ),
            backup_restored_layout=layout_paths["backup_restored"].read_text(
                encoding="utf-8"
            ),
            process_event=events["process_death"],
            backup_event=events["backup_restore"],
            crash_detected=l1["outcome"] == "fail",
        )
        verdict["run_evidence"] = {
            "run_dir": str(run_root),
            "contract": str(contract_source),
            "execution_record": str(run_root / "execution-record.json"),
            "execution_provenance": str(run_root / "execution-provenance.json"),
            "layouts": {key: str(value) for key, value in layout_paths.items()},
            "system_events": {
                key: str(
                    run_root
                    / "artifacts"
                    / _safe_relative_string(event_paths, key)
                )
                for key in events
            },
        }
        return verdict
    except (
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        ExecutionIdentityError,
    ) as error:
        return {
            "schema_version": 1,
            "conclusion": "non_accountable",
            "classification": "non_accountable",
            "reason": "run_evidence_missing_or_invalid",
            "accountable": False,
            "observations": {},
            "evidence_error": f"{type(error).__name__}: {error}",
            "run_evidence": {
                "run_dir": str(run_root),
                "contract": str(contract_source),
            },
        }


def _read_observation(
    layout_json: str,
    contract: LifecycleRecoveryContract,
) -> dict[str, str | None]:
    data = json.loads(layout_json)
    if not isinstance(data, list):
        raise ValueError("Android layout evidence must be a JSON list")
    by_id = {
        str(item.get("resource-id", "")).rsplit("/", 1)[-1]: item.get("text")
        for item in data
        if isinstance(item, dict)
    }
    return {
        "sentinel": by_id.get(contract.sentinel_resource),
        "schema_version": by_id.get(contract.schema_resource),
        "revision": by_id.get(contract.revision_resource),
        "migration_status": by_id.get(contract.migration_resource),
    }


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object")
    return data


def _pid_set(value: object) -> set[str]:
    if not isinstance(value, list) or not all(
        isinstance(pid, str) and pid.isdecimal() for pid in value
    ):
        return set()
    return set(value)


def _mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _safe_relative_string(data: dict[str, Any], key: str) -> str:
    value = _string(data, key)
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"{key} must be a safe relative evidence path")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aiverify.lifecycle-recovery-oracle",
        description="Replay one lifecycle/backup recovery runner attempt.",
    )
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    verdict = judge_lifecycle_recovery_run(
        run_dir=args.run_dir,
        contract_path=args.contract,
    )
    try:
        write_json_artifact(args.output, verdict)
    except Exception as error:
        print(f"cannot write lifecycle oracle verdict: {error}", file=sys.stderr)
        return 2
    print(json.dumps(verdict, ensure_ascii=False, sort_keys=True))
    if verdict["conclusion"] == "locally_supported":
        return 0
    if verdict["conclusion"] == "locally_rejected":
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
