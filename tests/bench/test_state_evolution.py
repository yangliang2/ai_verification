from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiverify.bench.state_evolution import (
    MigrationEdge,
    RecoveryBoundary,
    StateEvolutionContractError,
    StateEvolutionRuntimeAdapter,
    judge_state_evolution,
    load_state_evolution_context,
    load_state_evolution_contract,
    self_validate_state_evolution_schema,
    validate_state_evolution_context,
    verify_state_evolution_provenance,
)
from aiverify.discovery import ChangeTarget, ProjectTarget

_FIXTURE = Path("bench/discovery-fixtures/state-evolution")
_CONTRACT = _FIXTURE / "contract.json"
_CONTEXT = _FIXTURE / "context-manifest.json"
_ADAPTER = Path("bench/capability-slices/state-evolution/adapter.json")


def _project_target() -> ProjectTarget:
    return ProjectTarget(
        target_id="project-state-evolution-001",
        source_origin="fixture://state-evolution",
        source_commit="state-evolution-v1",
        worktree=str(_FIXTURE),
        scope=("state-evolution",),
        discovery_budget=8,
    )


def _change_target() -> ChangeTarget:
    return ChangeTarget(
        target_id="change-state-evolution-001",
        source_origin="fixture://state-evolution",
        source_commit="state-evolution-v1",
        worktree=str(_FIXTURE),
        diff_ref="matched-state-change.patch",
        diff_sha256="a" * 64,
    )


def _process_event(*, before: list[str] | None = None, after: list[str] | None = None) -> dict:
    return {
        "status": "passed",
        "evidence": {
            "before_pids": before or ["101"],
            "background_status": "success",
            "background_resumed_package": "com.android.launcher3",
            "target_resumed_after_home": False,
            "kill_status": "success",
            "process_absent_after_kill": True,
            "relaunch_status": "success",
            "foreground_resumed_package": "dev.aiverify.lifecyclefixture",
            "target_resumed_after_relaunch": True,
            "after_pids": after or ["202"],
        },
    }


def _backup_event(**overrides: object) -> dict:
    evidence: dict[str, object] = {
        "transport": "com.android.localtransport/.LocalTransport",
        "previous_transport": "com.google.android.gms/.backup.BackupTransportService",
        "backup_was_enabled": False,
        "backup_status": "success",
        "clear_data_status": "success",
        "clear_data_output": "Success",
        "restore_status": "success",
        "restore_token": "1",
        "cleanup_status": "success",
        "cleanup_transport": "com.google.android.gms/.backup.BackupTransportService",
        "cleanup_backup_enabled": False,
    }
    evidence.update(overrides)
    return {"status": "passed", "evidence": evidence}


def _identity() -> dict[str, str]:
    return {
        "package": "dev.aiverify.lifecyclefixture",
        "activity": "dev.aiverify.lifecyclefixture.MainActivity",
        "state_epoch": "local-recovery-epoch-v1",
    }


def _state(contract, *, current: bool) -> dict[str, str]:
    snapshot = contract.current_state if current else contract.old_state
    return {
        "sentinel": snapshot.sentinel,
        "schema_version": str(snapshot.schema_version),
        "revision": str(snapshot.revision),
        "migration_status": snapshot.migration_status,
    }


def test_contract_schema_and_round_trip_are_strict() -> None:
    self_validate_state_evolution_schema()
    contract = load_state_evolution_contract(_CONTRACT)
    assert contract.to_dict() == json.loads(_CONTRACT.read_text(encoding="utf-8"))

    tampered = contract.to_dict()
    tampered["variant"] = "defect"
    with pytest.raises(StateEvolutionContractError, match="unknown fixture contract field"):
        type(contract).from_dict(tampered)

    receipt = verify_state_evolution_provenance(_CONTRACT)
    assert receipt.valid is True
    assert len(receipt.checks) == 5


def test_context_uses_same_graph_for_change_and_no_diff_project_targets() -> None:
    project = load_state_evolution_context(_CONTEXT, _project_target(), contract_path=_CONTRACT)
    change = load_state_evolution_context(_CONTEXT, _change_target(), contract_path=_CONTRACT)

    assert project.graph.target_id == "project-state-evolution-001"
    assert change.graph.target_id == "change-state-evolution-001"
    assert project.provenance_bound is True
    assert project.derivation_ready is True
    assert any("Runtime process" in item for item in project.unresolved)
    path = project.graph.trace_forward("legacy-writer")
    assert path.node_ids[-1] == "durable-state-contract"
    assert "edge-runtime-identity" in path.unresolved_edge_ids
    assert validate_state_evolution_context(project)


def test_context_marks_contradictory_required_fact_without_inventing_observation(tmp_path: Path) -> None:
    data = json.loads(_CONTEXT.read_text(encoding="utf-8"))
    fact = next(item for item in data["facts"] if item["fact_id"] == "fact-schema-migration")
    fact["status"] = "contradictory"
    path = tmp_path / "context.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    context = load_state_evolution_context(path, _project_target(), contract_path=_CONTRACT)
    assert context.derivation_ready is False
    assert any("fact-schema-migration is contradictory" in item for item in context.unresolved)


def test_adapter_is_bounded_and_has_no_variant_or_verdict_leakage() -> None:
    contract = load_state_evolution_contract(_CONTRACT)
    adapter = StateEvolutionRuntimeAdapter(contract)
    plan = adapter.plan()
    assert [step["event"] for step in plan if "event" in step] == [
        "rotate",
        "process_death",
        "backup_restore",
    ]
    serialized = json.dumps({"contract": contract.to_dict(), "plan": plan}, sort_keys=True).lower()
    for forbidden in ("defect", "control", "journey", "verdict", "expected_outcome"):
        assert forbidden not in serialized

    checks = adapter.validate_evidence(
        {
            "terminal": True,
            "process_event": _process_event(),
            "backup_event": _backup_event(),
            "execution_identity": _identity(),
        }
    )
    assert all(item.passed for item in checks)

    adapter_document = json.loads(_ADAPTER.read_text(encoding="utf-8"))
    assert adapter_document["safety"] == {
        "local_only": True,
        "reversible": True,
        "one_attempt": True,
        "retry_after_accountability": False,
    }
    adapter_text = json.dumps(adapter_document, sort_keys=True).lower()
    for forbidden in ("defect", "control", "journey", "verdict", "expected_outcome"):
        assert forbidden not in adapter_text


def test_oracle_supports_correct_restoration_without_variant_input() -> None:
    contract = load_state_evolution_contract(_CONTRACT)
    verdict = judge_state_evolution(
        contract=contract,
        initial_state=_state(contract, current=False),
        rotated_state=_state(contract, current=False),
        process_restored_state=_state(contract, current=False),
        backup_restored_state=_state(contract, current=True),
        process_event=_process_event(),
        backup_event=_backup_event(),
        execution_identity=_identity(),
    )
    assert verdict["conclusion"] == "locally_supported"
    assert verdict["classification"] == "correct_restoration"
    assert verdict["accountable"] is True


def test_oracle_classifies_stale_state_and_silent_reset() -> None:
    contract = load_state_evolution_contract(_CONTRACT)
    common = {
        "contract": contract,
        "initial_state": _state(contract, current=False),
        "rotated_state": _state(contract, current=False),
        "process_restored_state": _state(contract, current=False),
        "process_event": _process_event(),
        "backup_event": _backup_event(),
        "execution_identity": _identity(),
    }
    stale = judge_state_evolution(**common, backup_restored_state=_state(contract, current=False))
    assert stale["classification"] == "stale_state"
    reset = judge_state_evolution(
        **common,
        backup_restored_state={
            "sentinel": "UNINITIALIZED",
            "schema_version": "2",
            "revision": "0",
            "migration_status": "RESET_DEFAULTS",
        },
    )
    assert reset["classification"] == "silent_reset"


def test_oracle_fails_closed_on_missing_or_contradictory_identity_and_evidence() -> None:
    contract = load_state_evolution_contract(_CONTRACT)
    common = {
        "contract": contract,
        "initial_state": _state(contract, current=False),
        "rotated_state": _state(contract, current=False),
        "process_restored_state": _state(contract, current=False),
        "backup_restored_state": _state(contract, current=True),
        "process_event": _process_event(),
        "backup_event": _backup_event(),
    }
    missing_identity = judge_state_evolution(**common, execution_identity=None)
    assert missing_identity["conclusion"] == "non_accountable"
    assert missing_identity["classification"] == "inconclusive"

    unchanged_input = {**common, "execution_identity": _identity(), "process_event": _process_event(before=["101"], after=["101"])}
    unchanged_process = judge_state_evolution(**unchanged_input)
    assert unchanged_process["reason"] == "process_identity_missing_or_unchanged"

    malformed_input = {**common, "execution_identity": _identity(), "backup_restored_state": "not-json"}
    malformed = judge_state_evolution(**malformed_input)
    assert malformed["reason"] == "state_observation_missing_or_invalid"


def test_contract_rejects_invalid_migration_edge() -> None:
    with pytest.raises(StateEvolutionContractError, match="cross a schema boundary"):
        MigrationEdge(
            edge_id="bad",
            from_schema=1,
            to_schema=1,
            from_revision=1,
            to_revision=1,
            operation="noop",
        )
    with pytest.raises(StateEvolutionContractError, match="events must be"):
        RecoveryBoundary(boundary_id="bad", events=("process_death",))
