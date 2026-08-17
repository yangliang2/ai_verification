from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

import aiverify.runner.execution_record as execution_record
from aiverify.runner.execution_record import (
    ArtifactStorageError,
    ExecutionRecordStorageError,
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


def test_schema_v2_completed_record_requires_provenance_binding(tmp_path) -> None:
    store = ExecutionRecordStore.establish(
        tmp_path,
        scenario="fixture-scenario",
        started_at="2026-07-17T12:00:00+00:00",
    )
    assert load_execution_record(store.path)["schema_version"] == 2

    record = store.finalize(
        lifecycle_state="completed",
        execution={
            "status": "completed",
            "accounting_eligible": True,
            "reason": None,
            "message": None,
        },
        process_exit_code=0,
        timing={
            "started_at": "2026-07-17T12:00:00+00:00",
            "finished_at": "2026-07-17T12:00:01+00:00",
            "total_seconds": 1.0,
            "phases": [],
        },
        phase_errors=[],
        evidence_refs={
            "execution_provenance": {
                "path": str(tmp_path / "execution-provenance.json"),
                "sha256": "a" * 64,
            }
        },
    )

    assert record["evidence_refs"]["execution_provenance"]["sha256"] == "a" * 64


@pytest.mark.parametrize(
    ("post_publication_fault", "expected_log"),
    (
        (
            "directory-sync",
            "published ExecutionRecord could not confirm directory durability",
        ),
        (
            "temporary-cleanup",
            "published ExecutionRecord could not clean already-published temporary path",
        ),
    ),
)
@pytest.mark.parametrize(
    (
        "lifecycle_state",
        "execution",
        "process_exit_code",
        "phase_errors",
        "evidence_refs",
        "accountable",
    ),
    [
        (
            "completed",
            {
                "status": "completed",
                "accounting_eligible": True,
                "reason": None,
                "message": None,
            },
            0,
            [],
            {
                "execution_provenance": {
                    "path": "execution-provenance.json",
                    "sha256": "a" * 64,
                }
            },
            True,
        ),
        (
            "failed",
            {
                "status": "non_accountable",
                "accounting_eligible": False,
                "reason": "controlled_failure",
                "message": "controlled failure",
            },
            2,
            [
                {
                    "phase": "controlled-phase",
                    "kind": "controlled-kind",
                    "reason": "controlled_failure",
                    "message": "controlled failure",
                }
            ],
            {},
            False,
        ),
    ],
    ids=("accountable-completed", "non-accountable-failed"),
)
def test_finalize_after_published_replace_reports_durability_uncertainty_not_failure(
    tmp_path,
    monkeypatch,
    caplog,
    post_publication_fault,
    expected_log,
    lifecycle_state,
    execution,
    process_exit_code,
    phase_errors,
    evidence_refs,
    accountable,
) -> None:
    """A post-replace error cannot mean an uncommitted terminal record."""
    started_at = "2026-08-16T00:00:00+00:00"
    store = ExecutionRecordStore.establish(
        tmp_path,
        scenario="post-replace-durability",
        started_at=started_at,
    )

    if post_publication_fault == "directory-sync":
        def fail_directory_sync(_path) -> None:
            raise OSError("controlled directory fsync failure after replace")

        monkeypatch.setattr(
            execution_record,
            "_fsync_directory",
            fail_directory_sync,
        )
    else:
        original_unlink = Path.unlink

        def fail_published_temporary_cleanup(path: Path, *args, **kwargs) -> None:
            if (
                path.parent == store.path.parent
                and path.name.startswith(f".{store.path.name}.")
                and path.name.endswith(".tmp")
            ):
                raise OSError("controlled temporary cleanup failure after replace")
            original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", fail_published_temporary_cleanup)

    with caplog.at_level(logging.WARNING, logger=execution_record.__name__):
        record = store.finalize(
            lifecycle_state=lifecycle_state,
            execution=execution,
            process_exit_code=process_exit_code,
            timing={
                "started_at": started_at,
                "finished_at": "2026-08-16T00:00:01+00:00",
                "total_seconds": 1.0,
                "phases": [],
            },
            phase_errors=phase_errors,
            evidence_refs=evidence_refs,
        )

    assert load_execution_record(store.path) == record
    assert is_execution_record_accountable(record) is accountable
    assert expected_log in caplog.text
    assert not list(store.path.parent.glob(f".{store.path.name}.*.tmp"))


def test_finalize_before_published_replace_remains_fail_closed(tmp_path, monkeypatch) -> None:
    """A replace error still preserves the original non-terminal record."""
    started_at = "2026-08-16T00:00:00+00:00"
    store = ExecutionRecordStore.establish(
        tmp_path,
        scenario="pre-replace-storage-failure",
        started_at=started_at,
    )
    before = store.path.read_bytes()

    def fail_replace(_source, _target) -> None:
        raise OSError("controlled replace failure")

    monkeypatch.setattr(execution_record.os, "replace", fail_replace)

    with pytest.raises(ExecutionRecordStorageError, match="controlled replace failure"):
        store.finalize(
            lifecycle_state="completed",
            execution={
                "status": "completed",
                "accounting_eligible": True,
                "reason": None,
                "message": None,
            },
            process_exit_code=0,
            timing={
                "started_at": started_at,
                "finished_at": "2026-08-16T00:00:01+00:00",
                "total_seconds": 1.0,
                "phases": [],
            },
            phase_errors=[],
            evidence_refs={
                "execution_provenance": {
                    "path": "execution-provenance.json",
                    "sha256": "a" * 64,
                }
            },
        )

    assert store.path.read_bytes() == before
    assert not list(store.path.parent.glob(f".{store.path.name}.*.tmp"))


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
