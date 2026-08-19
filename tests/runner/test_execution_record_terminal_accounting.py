"""Hermetic terminal-accounting contracts for Issue #171."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import aiverify.runner.execution_record as execution_record
from aiverify.runner.execution_record import (
    ArtifactStorageError,
    ExecutionRecordStorageError,
    ExecutionRecordStore,
    ExecutionRecordValidationError,
    execution_record_reason,
    load_execution_record,
    validate_execution_record,
    write_bytes_artifact,
    write_json_artifact,
)


_STARTED_AT = "2026-08-16T00:00:00+00:00"
_FINISHED_AT = "2026-08-16T00:00:01+00:00"
_REASON = "controlled_terminal_failure"


def _phase_error(reason: str = _REASON) -> dict[str, str]:
    return {
        "phase": "controlled-phase",
        "kind": "controlled-kind",
        "reason": reason,
        "message": "controlled failure",
    }


def _in_progress_record() -> dict[str, object]:
    return {
        "schema_version": 2,
        "attempt_id": "attempt-171",
        "scenario": "execution-record-terminal-accounting",
        "lifecycle_state": "in_progress",
        "started_at": _STARTED_AT,
        "finished_at": None,
        "execution": {
            "status": "non_accountable",
            "accounting_eligible": False,
            "reason": None,
            "message": None,
        },
        "process_outcome": None,
        "timing": {
            "started_at": _STARTED_AT,
            "finished_at": None,
            "total_seconds": None,
            "phases": [],
        },
        "phase_errors": [],
        "evidence_refs": {},
    }


def _failed_record() -> dict[str, object]:
    record = _in_progress_record()
    record.update(
        {
            "lifecycle_state": "failed",
            "finished_at": _FINISHED_AT,
            "execution": {
                "status": "non_accountable",
                "accounting_eligible": False,
                "reason": _REASON,
                "message": "controlled failure",
            },
            "process_outcome": {"exit_code": 2},
            "timing": {
                "started_at": _STARTED_AT,
                "finished_at": _FINISHED_AT,
                "total_seconds": 1.0,
                "phases": [],
            },
            "phase_errors": [_phase_error()],
        }
    )
    return record


def _completed_record() -> dict[str, object]:
    record = _failed_record()
    record.update(
        {
            "lifecycle_state": "completed",
            "execution": {
                "status": "completed",
                "accounting_eligible": True,
                "reason": None,
                "message": None,
            },
            "process_outcome": {"exit_code": 0},
            "phase_errors": [],
            "evidence_refs": {
                "execution_provenance": {
                    "path": "execution-provenance.json",
                    "sha256": "a" * 64,
                }
            },
        }
    )
    return record


def _establish(tmp_path: Path) -> ExecutionRecordStore:
    return ExecutionRecordStore.establish(
        tmp_path / "run",
        scenario="execution-record-terminal-accounting",
        started_at=_STARTED_AT,
    )


def _failed_finalize_kwargs() -> dict[str, object]:
    return {
        "lifecycle_state": "failed",
        "execution": {
            "status": "non_accountable",
            "accounting_eligible": False,
            "reason": _REASON,
            "message": "controlled failure",
        },
        "process_exit_code": 2,
        "timing": {
            "started_at": _STARTED_AT,
            "finished_at": _FINISHED_AT,
            "total_seconds": 1.0,
            "phases": [],
        },
        "phase_errors": [_phase_error()],
        "evidence_refs": {},
    }


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda record: record.update({"lifecycle_state": "unknown"}),
            "unsupported ExecutionRecord lifecycle_state",
        ),
        (
            lambda record: record.update({"execution": []}),
            "execution must be an object",
        ),
        (
            lambda record: record.update({"timing": []}),
            "timing must be an object",
        ),
        (
            lambda record: record["timing"].update({"started_at": "different"}),  # type: ignore[index,union-attr]
            "timing.started_at contradicts started_at",
        ),
        (
            lambda record: record["timing"].update({"phases": {}}),  # type: ignore[index,union-attr]
            "timing.phases must be a list",
        ),
        (
            lambda record: record.update({"phase_errors": {}}),
            "phase_errors must be a list",
        ),
        (
            lambda record: record.update({"evidence_refs": []}),
            "evidence_refs must be an object",
        ),
        (
            lambda record: record["execution"].update({"reason": _REASON}),  # type: ignore[index,union-attr]
            "in_progress ExecutionRecord cannot have a terminal reason",
        ),
        (
            lambda record: record.update({"finished_at": _FINISHED_AT}),
            "in_progress ExecutionRecord cannot have terminal outcome fields",
        ),
        (
            lambda record: record["timing"].update(  # type: ignore[index,union-attr]
                {"finished_at": _FINISHED_AT, "total_seconds": 1.0}
            ),
            "in_progress ExecutionRecord cannot have terminal timing",
        ),
        (
            lambda record: record.update({"phase_errors": [_phase_error()]}),
            "in_progress ExecutionRecord cannot have terminal phase errors",
        ),
    ],
    ids=(
        "unsupported-lifecycle",
        "execution-not-object",
        "timing-not-object",
        "timing-start-mismatch",
        "timing-phases-not-list",
        "phase-errors-not-list",
        "references-not-object",
        "terminal-reason",
        "terminal-outcome",
        "terminal-timing",
        "terminal-phase-errors",
    ),
)
def test_validate_rejects_each_in_progress_contradiction(
    mutate, message: str
) -> None:
    """Every in-progress contradiction fails before accountable promotion."""
    record = _in_progress_record()
    mutate(record)

    with pytest.raises(ExecutionRecordValidationError, match=message):
        validate_execution_record(record)


@pytest.mark.parametrize(
    ("record", "message"),
    [
        ([], "ExecutionRecord must be an object"),
        ({**_in_progress_record(), "schema_version": 3}, "unsupported ExecutionRecord"),
        ({**_in_progress_record(), "scenario": ""}, "scenario must be a non-empty string"),
    ],
    ids=("not-an-object", "unsupported-schema", "empty-required-field"),
)
def test_validate_rejects_root_shape_contradictions(record, message: str) -> None:
    """Root-shape failures cannot be treated as execution evidence."""
    with pytest.raises(ExecutionRecordValidationError, match=message):
        validate_execution_record(record)


@pytest.mark.parametrize(
    ("record_factory", "mutate", "message"),
    [
        (
            _failed_record,
            lambda record: record.update({"finished_at": None}),
            "failed ExecutionRecord requires finished_at",
        ),
        (
            _failed_record,
            lambda record: record["timing"].update(  # type: ignore[index,union-attr]
                {"finished_at": "different"}
            ),
            "timing.finished_at contradicts finished_at",
        ),
        (
            _failed_record,
            lambda record: record["timing"].update({"total_seconds": True}),  # type: ignore[index,union-attr]
            "requires non-negative timing.total_seconds",
        ),
        (
            _completed_record,
            lambda record: record["execution"].update({"reason": _REASON}),  # type: ignore[index,union-attr]
            "completed ExecutionRecord requires no reason",
        ),
        (
            _completed_record,
            lambda record: record.update({"phase_errors": [_phase_error()]}),
            "completed ExecutionRecord cannot contain phase errors",
        ),
        (
            _completed_record,
            lambda record: record.update({"evidence_refs": {}}),
            "requires execution provenance",
        ),
        (
            _completed_record,
            lambda record: record["evidence_refs"]["execution_provenance"].update(  # type: ignore[index,union-attr]
                {"sha256": "not-a-digest"}
            ),
            "execution provenance binding is invalid",
        ),
        (
            _failed_record,
            lambda record: record["execution"].update({"reason": None}),  # type: ignore[index,union-attr]
            "requires a canonical reason",
        ),
        (
            _failed_record,
            lambda record: record.update({"process_outcome": {"exit_code": 1}}),
            "requires exit code 2",
        ),
        (
            _failed_record,
            lambda record: record.update({"phase_errors": []}),
            "requires ordered phase errors",
        ),
        (
            _failed_record,
            lambda record: record.update({"phase_errors": ["not-an-object"]}),
            "phase_errors\\[0\\] must be an object",
        ),
        (
            _failed_record,
            lambda record: record.update(
                {
                    "phase_errors": [
                        {**_phase_error(), "message": ""},
                    ]
                }
            ),
            "phase_errors\\[0\\].message must be a non-empty string",
        ),
    ],
    ids=(
        "missing-finished-at",
        "timing-finished-at-mismatch",
        "invalid-total-seconds",
        "completed-reason",
        "completed-phase-errors",
        "completed-missing-provenance",
        "completed-invalid-provenance",
        "missing-canonical-reason",
        "non-accountable-exit-code",
        "missing-phase-errors",
        "phase-error-not-object",
        "phase-error-missing-message",
    ),
)
def test_validate_rejects_each_terminal_contradiction(
    record_factory, mutate, message: str
) -> None:
    """Terminal contradictions stay non-claimable at the validation boundary."""
    record = record_factory()
    mutate(record)

    with pytest.raises(ExecutionRecordValidationError, match=message):
        validate_execution_record(record)


def test_schema_v1_completed_record_does_not_require_v2_provenance() -> None:
    """Version-one completed records remain valid without a v2-only receipt."""
    record = _completed_record()
    record["schema_version"] = 1
    record["evidence_refs"] = {}

    validate_execution_record(record)


def test_loader_rejects_invalid_json_before_returning_an_execution_record(
    tmp_path: Path,
) -> None:
    """Malformed persisted bytes cannot become a Local Conclusion input."""
    path = tmp_path / "execution-record.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(ExecutionRecordValidationError, match="invalid ExecutionRecord"):
        load_execution_record(path)


@pytest.mark.parametrize(
    "case",
    ("attempt-identity", "already-terminal"),
)
def test_finalize_rejects_changed_identity_or_a_second_terminalization(
    tmp_path: Path, case: str
) -> None:
    """Finalize only owns its original, in-progress ExecutionRecord."""
    store = _establish(tmp_path)
    if case == "attempt-identity":
        record = load_execution_record(store.path)
        record["attempt_id"] = "other-attempt"
        store.path.write_text(json.dumps(record), encoding="utf-8")
        message = "attempt identity changed before finalization"
    else:
        store.finalize(**_failed_finalize_kwargs())
        message = "ExecutionRecord is already terminal"
    before = store.path.read_bytes()

    with pytest.raises(ExecutionRecordValidationError, match=message):
        store.finalize(**_failed_finalize_kwargs())

    assert store.path.read_bytes() == before


@pytest.mark.parametrize(
    "case",
    ("corrupt-record", "missing-finished-at", "replace-failure"),
)
def test_finalize_storage_failures_leave_the_persisted_record_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    """Read, timing, and replace failures cannot partially terminalize a record."""
    store = _establish(tmp_path)
    kwargs = _failed_finalize_kwargs()

    if case == "corrupt-record":
        store.path.write_text("{", encoding="utf-8")
        message = "cannot finalize ExecutionRecord"
        error_type = ExecutionRecordStorageError
    elif case == "missing-finished-at":
        kwargs["timing"] = {}
        message = "terminal timing.finished_at is required"
        error_type = ExecutionRecordValidationError
    else:
        monkeypatch.setattr(
            execution_record,
            "_replace_json",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("blocked replace")),
        )
        message = "cannot finalize ExecutionRecord"
        error_type = ExecutionRecordStorageError
    before = store.path.read_bytes()

    with pytest.raises(error_type, match=message):
        store.finalize(**kwargs)

    assert store.path.read_bytes() == before
    assert not list(store.path.parent.glob(f".{store.path.name}.*.tmp"))


@pytest.mark.parametrize(
    "lifecycle_state",
    ("preflight_rejected", "interrupted", "failed"),
)
def test_terminal_non_accountable_finalization_is_exactly_once(
    tmp_path: Path, lifecycle_state: str
) -> None:
    """Every successful rejected attempt becomes one consistent terminal record."""
    store = _establish(tmp_path)
    kwargs = _failed_finalize_kwargs()
    kwargs["lifecycle_state"] = lifecycle_state

    record = store.finalize(**kwargs)

    assert record["lifecycle_state"] == lifecycle_state
    assert record["execution"]["status"] == "non_accountable"
    assert record["execution"]["accounting_eligible"] is False
    assert record["execution"]["reason"] == _REASON
    assert record["process_outcome"] == {"exit_code": 2}
    assert record["phase_errors"][-1]["reason"] == _REASON
    assert load_execution_record(store.path) == record

    with pytest.raises(ExecutionRecordValidationError, match="already terminal"):
        store.finalize(**kwargs)


def test_terminal_execution_record_reason_is_the_canonical_reason() -> None:
    """A terminal rejected record exposes its recorded canonical reason."""
    assert execution_record_reason(_failed_record()) == _REASON


@pytest.mark.parametrize(
    "owned_output",
    (
        "execution-record.json",
        "verdict.json",
        "live-validation-gate.json",
        "runner-setup.json",
        "artifacts",
    ),
)
def test_establish_rejects_existing_runner_output_without_overwriting_it(
    tmp_path: Path, owned_output: str
) -> None:
    """A second attempt cannot replace an owned runner output."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    existing = run_dir / owned_output
    if owned_output == "artifacts":
        existing.mkdir()
    else:
        existing.write_text("preserved", encoding="utf-8")

    with pytest.raises(ExecutionRecordStorageError, match="existing runner output"):
        ExecutionRecordStore.establish(
            run_dir,
            scenario="execution-record-terminal-accounting",
            started_at=_STARTED_AT,
        )

    assert existing.is_dir() or existing.read_text(encoding="utf-8") == "preserved"
    assert not (run_dir / "execution-record.json").exists() or (
        owned_output == "execution-record.json"
    )


def test_establish_wraps_an_exclusive_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Initial persistence failure cannot return an untracked attempt."""
    monkeypatch.setattr(
        execution_record,
        "_create_exclusive_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("blocked create")),
    )

    with pytest.raises(ExecutionRecordStorageError, match="cannot establish"):
        _establish(tmp_path)

    assert not (tmp_path / "run" / "execution-record.json").exists()


@pytest.mark.parametrize(
    "writer",
    (
        lambda path: write_json_artifact(path, {"status": "first"}),
        lambda path: write_bytes_artifact(path, b"first"),
    ),
    ids=("json", "bytes"),
)
def test_exclusive_artifact_writes_preserve_existing_evidence(
    tmp_path: Path, writer
) -> None:
    """Both artifact helpers reject replacement and remove their temporary file."""
    path = tmp_path / "evidence.bin"
    path.write_bytes(b"original")

    with pytest.raises(ArtifactStorageError, match="cannot persist"):
        writer(path)

    assert path.read_bytes() == b"original"
    assert not list(tmp_path.glob(f".{path.name}.*.tmp"))


@pytest.mark.parametrize(
    "cleanup_failure", (False, True), ids=("cleanup", "cleanup-error")
)
def test_atomic_replace_failure_preserves_the_original_record_and_handles_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cleanup_failure: bool
) -> None:
    """A pre-publication failure preserves the original authoritative record."""
    path = tmp_path / "execution-record.json"
    path.write_text('{"state":"original"}\n', encoding="utf-8")

    monkeypatch.setattr(
        execution_record.os,
        "replace",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("blocked replace")),
    )
    if cleanup_failure:
        original_unlink = Path.unlink

        def fail_cleanup_before_removal(candidate: Path, *args, **kwargs) -> None:
            if (
                candidate.parent == path.parent
                and execution_record._is_unpublished_execution_record_path(candidate)
            ):
                raise OSError("blocked temporary cleanup")
            original_unlink(candidate, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", fail_cleanup_before_removal)

    expected_error = "blocked temporary cleanup" if cleanup_failure else "blocked replace"
    with pytest.raises(OSError, match=expected_error):
        execution_record._replace_json(path, {"state": "replacement"})

    assert path.read_text(encoding="utf-8") == '{"state":"original"}\n'
    temporary_paths = [
        candidate
        for candidate in tmp_path.iterdir()
        if execution_record._is_unpublished_execution_record_path(candidate)
    ]
    if cleanup_failure:
        assert len(temporary_paths) == 1
        with pytest.raises(ExecutionRecordValidationError, match="temporary"):
            load_execution_record(temporary_paths[0])
    else:
        assert temporary_paths == []
