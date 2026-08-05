from __future__ import annotations

import json
import shutil
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
    verify_change_target_diff,
    verify_state_evolution_matched_pair,
    verify_state_evolution_provenance,
)
from aiverify.discovery import ChangeTarget, ProjectTarget

_FIXTURE = Path("bench/discovery-fixtures/state-evolution")
_CONTRACT = _FIXTURE / "contract.json"
_CONTEXT = _FIXTURE / "context-manifest.json"
_ADAPTER = Path("bench/capability-slices/state-evolution/adapter.json")
_PAIR = _FIXTURE / "auditor" / "matched-pair.json"
_DIFF = Path("bench/capability-slices/lifecycle-recovery/patches/stale-migration-guard.patch")


def _project_target() -> ProjectTarget:
    return ProjectTarget(
        target_id="project-state-evolution-001",
        source_origin="fixture://state-evolution",
        source_commit="state-evolution-v1",
        worktree=str(Path.cwd()),
        scope=("state-evolution",),
        discovery_budget=8,
    )


def _change_target() -> ChangeTarget:
    return ChangeTarget(
        target_id="change-state-evolution-001",
        source_origin="fixture://state-evolution",
        source_commit="state-evolution-v1",
        worktree=str(Path.cwd()),
        diff_ref=str(_DIFF),
        diff_sha256="7109a3a3e7d1e0416ffe4c0a06de10982c8fdc99f1cfc888c266acc328674a42",
    )


def _process_event(*, before: list[str] | None = None, after: list[str] | None = None) -> dict:
    return {
        "event": "process_death",
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
        "package": "dev.aiverify.lifecyclefixture",
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
    return {"event": "backup_restore", "status": "passed", "evidence": evidence}


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


def _migration_evidence(contract, **overrides: object) -> dict[str, object]:
    evidence: dict[str, object] = {
        "status": "passed",
        "edge_id": contract.migration.edge_id,
        "count": 1,
        "from_schema": contract.migration.from_schema,
        "to_schema": contract.migration.to_schema,
        "from_revision": contract.migration.from_revision,
        "to_revision": contract.migration.to_revision,
        "exactly_once": True,
    }
    evidence.update(overrides)
    return evidence


def test_contract_schema_and_round_trip_are_strict(tmp_path: Path) -> None:
    self_validate_state_evolution_schema()
    contract = load_state_evolution_contract(_CONTRACT)
    assert contract.to_dict() == json.loads(_CONTRACT.read_text(encoding="utf-8"))

    tampered = contract.to_dict()
    tampered["variant"] = "defect"
    with pytest.raises(StateEvolutionContractError, match="unknown fixture contract field"):
        type(contract).from_dict(tampered)

    malformed = contract.to_dict()
    del malformed["migration"]
    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text(json.dumps(malformed), encoding="utf-8")
    with pytest.raises(StateEvolutionContractError, match="schema validation"):
        load_state_evolution_contract(malformed_path)

    receipt = verify_state_evolution_provenance(_CONTRACT)
    assert receipt.valid is True
    assert len(receipt.checks) == 5
    pair_receipt = verify_state_evolution_matched_pair(_PAIR, repo_root=Path.cwd())
    assert pair_receipt.valid is True, pair_receipt.to_dict()
    assert len(pair_receipt.checks) >= 15


@pytest.mark.parametrize("tamper", ["pair_id", "protocol", "source_path", "patch"])
def test_matched_pair_rejects_tampered_auditor_claims(tmp_path: Path, tamper: str) -> None:
    pair = json.loads(_PAIR.read_text(encoding="utf-8"))
    if tamper == "pair_id":
        pair["pair_id"] = "wrong-pair"
    elif tamper == "protocol":
        protocol = tmp_path / "protocol.json"
        protocol_data = json.loads((_FIXTURE / "protocol.json").read_text(encoding="utf-8"))
        protocol_data["package"] = "wrong.package"
        protocol.write_text(json.dumps(protocol_data), encoding="utf-8")
        pair["protocol"]["sha256"] = "0" * 64
        pair["protocol"]["path"] = str(protocol)
    elif tamper == "source_path":
        pair["source_pair"]["changed"]["source_path"] = "../contract.json"
    else:
        patch_path = tmp_path / "tampered.patch"
        patch_path.write_text("diff --git a/a b/b\n@@ -1 +1 @@\n-old\n+new\n+extra\n", encoding="utf-8")
        pair["source_pair"]["changed"]["change_path"] = str(patch_path)
    path = tmp_path / "matched-pair.json"
    path.write_text(json.dumps(pair), encoding="utf-8")
    receipt = verify_state_evolution_matched_pair(path, repo_root=Path.cwd())
    assert receipt.valid is False, receipt.to_dict()


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
    assert verify_change_target_diff(change.target, repo_root=Path.cwd()).valid is True
    bad_change = ChangeTarget(
        target_id=change.target.target_id,
        source_origin=change.target.source_origin,
        source_commit=change.target.source_commit,
        worktree=change.target.worktree,
        diff_ref=change.target.diff_ref,
        diff_sha256="0" * 64,
    )
    assert verify_change_target_diff(bad_change, repo_root=Path.cwd()).valid is False
    with pytest.raises(StateEvolutionContractError, match="ChangeTarget diff provenance"):
        load_state_evolution_context(_CONTEXT, bad_change, contract_path=_CONTRACT)


def test_context_marks_contradictory_required_fact_without_inventing_observation(tmp_path: Path) -> None:
    data = json.loads(_CONTEXT.read_text(encoding="utf-8"))
    fact = next(item for item in data["facts"] if item["fact_id"] == "fact-schema-migration")
    fact["status"] = "contradictory"
    path = tmp_path / "context.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    context = load_state_evolution_context(path, _project_target(), contract_path=_CONTRACT)
    assert context.derivation_ready is False
    assert any("fact-schema-migration is contradictory" in item for item in context.unresolved)


def test_context_fails_closed_when_bound_source_bytes_drift(tmp_path: Path) -> None:
    copied = tmp_path / "state-evolution"
    shutil.copytree(_FIXTURE, copied)
    source = copied / "LegacyStateWriter.kt"
    source.write_text(source.read_text(encoding="utf-8") + "\n// drift\n", encoding="utf-8")
    receipt = verify_state_evolution_provenance(copied / "contract.json")
    assert receipt.valid is False
    with pytest.raises(StateEvolutionContractError, match="fixture contract provenance"):
        load_state_evolution_context(
            copied / "context-manifest.json",
            _project_target(),
            contract_path=copied / "contract.json",
        )


def test_provenance_read_error_is_a_failed_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    original = Path.read_bytes

    def unreadable(path: Path) -> bytes:
        if path.name == "LegacyStateWriter.kt":
            raise OSError("permission denied")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", unreadable)
    receipt = verify_state_evolution_provenance(_CONTRACT)
    assert receipt.valid is False
    failed = next(item for item in receipt.checks if item["ref"] == "LegacyStateWriter.kt")
    assert failed["status"] == "fail"
    assert "permission denied" in failed["error"]


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
            "migration_evidence": _migration_evidence(contract),
        }
    )
    assert all(item.passed for item in checks)

    imported = adapter.import_old_state(adapter.create_old_state().to_dict())
    assert imported == contract.old_state
    replay = adapter.replay()
    assert replay.terminal is True
    assert replay.seed == contract.old_state
    assert [item.phase_id for item in replay.phases] == [step["step_id"] for step in plan]
    assert replay.to_dict()["local_only"] is True

    seen: list[str] = []

    def record_phase(step, payload):
        seen.append(step.step_id)
        assert payload
        return {"status": "recorded", "evidence_ref": f"test://{step.step_id}"}

    injected = adapter.replay(phase_runner=record_phase)
    assert seen == [step["step_id"] for step in plan]
    assert all(item.status == "recorded" for item in injected.phases)

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
        migration_evidence=_migration_evidence(contract),
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
        "migration_evidence": _migration_evidence(contract),
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
        "migration_evidence": _migration_evidence(contract),
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

    wrong_identity = judge_state_evolution(
        **common,
        execution_identity={**_identity(), "activity": "dev.other.Activity"},
    )
    assert wrong_identity["conclusion"] == "non_accountable"
    assert wrong_identity["reason"] == "execution_identity_missing_or_contradictory"

    wrong_transport_input = {
        **common,
        "execution_identity": _identity(),
        "backup_event": _backup_event(transport="com.example.Untrusted/.Transport"),
    }
    wrong_transport = judge_state_evolution(**wrong_transport_input)
    assert wrong_transport["conclusion"] == "non_accountable"
    assert wrong_transport["reason"] == "backup_restore_evidence_missing_or_failed"

    missing_input = {
        **common,
        "execution_identity": _identity(),
        "backup_restored_state": {"sentinel": "AIVERIFY-ISSUE-71-SENTINEL"},
    }
    missing_state = judge_state_evolution(**missing_input)
    assert missing_state["conclusion"] == "non_accountable"
    assert missing_state["classification"] == "inconclusive"

    explicit_loss_input = {
        **missing_input,
        "state_loss_evidence": {
            "status": "passed",
            "loss_confirmed": True,
            "boundary": "backup_restore",
            "reason": "schema and revision fields absent after restore",
        },
    }
    explicit_loss = judge_state_evolution(**explicit_loss_input)
    assert explicit_loss["conclusion"] == "locally_rejected"
    assert explicit_loss["classification"] == "state_loss"


def test_oracle_requires_one_bound_migration_and_event_identities() -> None:
    contract = load_state_evolution_contract(_CONTRACT)
    common = {
        "contract": contract,
        "initial_state": _state(contract, current=False),
        "rotated_state": _state(contract, current=False),
        "process_restored_state": _state(contract, current=False),
        "backup_restored_state": _state(contract, current=True),
        "process_event": _process_event(),
        "backup_event": _backup_event(),
        "execution_identity": _identity(),
        "migration_evidence": _migration_evidence(contract),
    }
    for invalid in (
        None,
        _migration_evidence(contract, count=2),
        _migration_evidence(contract, edge_id="other-edge"),
        _migration_evidence(contract, applied_edge_ids=[contract.migration.edge_id, "other-edge"]),
    ):
        result = judge_state_evolution(**{**common, "migration_evidence": invalid})
        assert result["conclusion"] == "non_accountable"
        assert result["reason"] == "migration_evidence_missing_or_contradictory"

    wrong_process_event = judge_state_evolution(
        **{**common, "process_event": {**_process_event(), "event": "backup_restore"}}
    )
    assert wrong_process_event["reason"] == "process_identity_missing_or_unchanged"
    wrong_backup_event = judge_state_evolution(
        **{**common, "backup_event": {**_backup_event(), "event": "process_death"}}
    )
    assert wrong_backup_event["reason"] == "backup_restore_evidence_missing_or_failed"


def test_oracle_crash_requires_complete_coherent_state() -> None:
    contract = load_state_evolution_contract(_CONTRACT)
    common = {
        "contract": contract,
        "initial_state": _state(contract, current=False),
        "rotated_state": _state(contract, current=False),
        "process_restored_state": _state(contract, current=False),
        "backup_restored_state": _state(contract, current=True),
        "process_event": _process_event(),
        "backup_event": _backup_event(),
        "execution_identity": _identity(),
        "migration_evidence": _migration_evidence(contract),
        "crash_detected": True,
    }
    missing = judge_state_evolution(
        **{**common, "backup_restored_state": {"sentinel": contract.current_state.sentinel}}
    )
    assert missing["conclusion"] == "non_accountable"
    assert missing["classification"] == "inconclusive"
    contradictory = judge_state_evolution(
        **{**common, "process_restored_state": _state(contract, current=True)}
    )
    assert contradictory["conclusion"] == "non_accountable"
    assert contradictory["classification"] == "inconclusive"
    crash = judge_state_evolution(**common)
    assert crash["conclusion"] == "locally_rejected"
    assert crash["classification"] == "crash"


def test_replay_rejects_invalid_injected_status() -> None:
    contract = load_state_evolution_contract(_CONTRACT)
    adapter = StateEvolutionRuntimeAdapter(contract)

    def invalid_status(step, payload):
        return {"status": "maybe", "evidence_ref": f"test://{step.step_id}"}

    with pytest.raises(StateEvolutionContractError, match="status must be recorded or failed"):
        adapter.replay(phase_runner=invalid_status)


def test_contract_rejects_invalid_migration_edge() -> None:
    with pytest.raises(StateEvolutionContractError, match="incremental schema upgrade"):
        MigrationEdge(
            edge_id="bad",
            from_schema=1,
            to_schema=1,
            from_revision=1,
            to_revision=1,
            operation="noop",
        )
    with pytest.raises(StateEvolutionContractError, match="exactly once"):
        MigrationEdge(
            edge_id="not-once",
            from_schema=1,
            to_schema=2,
            from_revision=1,
            to_revision=2,
            operation="double",
            exactly_once=False,
        )
    with pytest.raises(StateEvolutionContractError, match="incremental schema upgrade"):
        MigrationEdge(
            edge_id="downgrade",
            from_schema=2,
            to_schema=1,
            from_revision=2,
            to_revision=3,
            operation="downgrade",
        )
    with pytest.raises(StateEvolutionContractError, match="monotonically"):
        MigrationEdge(
            edge_id="same-revision",
            from_schema=1,
            to_schema=2,
            from_revision=2,
            to_revision=2,
            operation="non-incremental",
        )
    with pytest.raises(StateEvolutionContractError, match="events must be"):
        RecoveryBoundary(boundary_id="bad", events=("process_death",))
