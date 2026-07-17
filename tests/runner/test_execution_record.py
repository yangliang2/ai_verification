from __future__ import annotations

import json

import pytest

from aiverify.runner.execution_record import (
    ArtifactStorageError,
    ExecutionRecordStore,
    ExecutionRecordValidationError,
    execution_record_reason,
    is_execution_record_accountable,
    load_execution_record,
    write_json_artifact,
)


def test_nonterminal_execution_record_is_always_abandoned_and_non_accountable(
    tmp_path,
) -> None:
    store = ExecutionRecordStore.establish(
        tmp_path,
        scenario="fixture-scenario",
        started_at="2026-07-17T12:00:00+00:00",
    )

    record = load_execution_record(store.path)

    assert record["lifecycle_state"] == "in_progress"
    assert is_execution_record_accountable(record) is False
    assert execution_record_reason(record) == "execution_abandoned"


def test_execution_record_loader_rejects_accountable_nonterminal_contradiction(
    tmp_path,
) -> None:
    store = ExecutionRecordStore.establish(
        tmp_path,
        scenario="fixture-scenario",
        started_at="2026-07-17T12:00:00+00:00",
    )
    record = json.loads(store.path.read_text(encoding="utf-8"))
    record["execution"] = {
        "status": "completed",
        "accounting_eligible": True,
        "reason": None,
        "message": None,
    }
    store.path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(
        ExecutionRecordValidationError,
        match="in_progress.*must be non-accountable",
    ):
        load_execution_record(store.path)


@pytest.mark.parametrize(
    ("lifecycle_state", "execution", "exit_code", "message"),
    [
        (
            "completed",
            {
                "status": "non_accountable",
                "accounting_eligible": False,
                "reason": "oracle_execution_error",
                "message": "failed",
            },
            2,
            "completed.*must be accountable",
        ),
        (
            "failed",
            {
                "status": "completed",
                "accounting_eligible": True,
                "reason": None,
                "message": None,
            },
            0,
            "failed.*must be non-accountable",
        ),
    ],
)
def test_execution_record_finalization_rejects_lifecycle_contradictions(
    tmp_path, lifecycle_state, execution, exit_code, message
) -> None:
    store = ExecutionRecordStore.establish(
        tmp_path,
        scenario="fixture-scenario",
        started_at="2026-07-17T12:00:00+00:00",
    )

    with pytest.raises(ExecutionRecordValidationError, match=message):
        store.finalize(
            lifecycle_state=lifecycle_state,
            execution=execution,
            process_exit_code=exit_code,
            timing={
                "started_at": "2026-07-17T12:00:00+00:00",
                "finished_at": "2026-07-17T12:00:01+00:00",
                "total_seconds": 1.0,
                "phases": [],
            },
            phase_errors=[] if lifecycle_state == "completed" else [
                {
                    "phase": "oracle-evaluation",
                    "kind": "oracle",
                    "reason": "oracle_execution_error",
                    "message": "failed",
                }
            ],
            evidence_refs={},
        )

    assert load_execution_record(store.path)["lifecycle_state"] == "in_progress"


def test_json_artifact_write_is_atomic_and_never_overwrites_an_existing_result(
    tmp_path,
) -> None:
    path = tmp_path / "verdict.json"

    write_json_artifact(path, {"attempt": "first"})

    with pytest.raises(ArtifactStorageError, match="verdict.json.*FileExistsError"):
        write_json_artifact(path, {"attempt": "second"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"attempt": "first"}
    assert not list(tmp_path.glob(".verdict.json.*.tmp"))


def test_terminal_execution_record_rejects_a_different_final_phase_reason(
    tmp_path,
) -> None:
    store = ExecutionRecordStore.establish(
        tmp_path,
        scenario="fixture-scenario",
        started_at="2026-07-17T12:00:00+00:00",
    )

    with pytest.raises(
        ExecutionRecordValidationError,
        match="final phase error reason must match execution reason",
    ):
        store.finalize(
            lifecycle_state="failed",
            execution={
                "status": "non_accountable",
                "accounting_eligible": False,
                "reason": "oracle_execution_error",
                "message": "oracle failed",
            },
            process_exit_code=2,
            timing={
                "started_at": "2026-07-17T12:00:00+00:00",
                "finished_at": "2026-07-17T12:00:01+00:00",
                "total_seconds": 1.0,
                "phases": [],
            },
            phase_errors=[
                {
                    "phase": "verdict-output",
                    "kind": "output",
                    "reason": "output_finalization_error",
                    "message": "write failed",
                }
            ],
            evidence_refs={},
        )

    assert load_execution_record(store.path)["lifecycle_state"] == "in_progress"
