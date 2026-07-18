"""Durable attempt-level accountability record for public runner invocations."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path


class ExecutionRecordStorageError(RuntimeError):
    """Raised when a durable ExecutionRecord cannot be established or updated."""


class ExecutionRecordValidationError(ValueError):
    """Raised when an ExecutionRecord is structurally or semantically invalid."""


class ArtifactStorageError(RuntimeError):
    """Raised when a durable runner JSON artifact cannot be created."""


@dataclass(frozen=True)
class ExecutionRecordStore:
    """Own one durable, atomically updated ExecutionRecord file."""

    path: Path
    attempt_id: str

    @classmethod
    def establish(
        cls,
        run_dir: Path,
        *,
        artifact_dir: Path | None = None,
        scenario: str,
        started_at: str,
    ) -> ExecutionRecordStore:
        """Create one non-terminal record without replacing an earlier attempt."""
        run_dir = Path(run_dir)
        owned_artifact_dir = (
            Path(artifact_dir) if artifact_dir is not None else run_dir / "artifacts"
        )
        attempt_id = str(uuid.uuid4())
        path = run_dir / "execution-record.json"
        owned_outputs = [
            run_dir / "execution-record.json",
            run_dir / "verdict.json",
            run_dir / "live-validation-gate.json",
            owned_artifact_dir,
        ]
        existing = [candidate for candidate in owned_outputs if candidate.exists()]
        if existing:
            names = ", ".join(candidate.name for candidate in existing)
            raise ExecutionRecordStorageError(
                f"cannot establish ExecutionRecord: existing runner output: {names}"
            )
        record = {
            "schema_version": 2,
            "attempt_id": attempt_id,
            "scenario": scenario,
            "lifecycle_state": "in_progress",
            "started_at": started_at,
            "finished_at": None,
            "execution": {
                "status": "non_accountable",
                "accounting_eligible": False,
                "reason": None,
                "message": None,
            },
            "process_outcome": None,
            "timing": {
                "started_at": started_at,
                "finished_at": None,
                "total_seconds": None,
                "phases": [],
            },
            "phase_errors": [],
            "evidence_refs": {},
        }
        validate_execution_record(record)
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
            _create_exclusive_json(path, record)
        except (OSError, TypeError, ValueError) as error:
            raise ExecutionRecordStorageError(
                f"cannot establish ExecutionRecord at {path}: {error}"
            ) from error
        return cls(path=path, attempt_id=attempt_id)

    def finalize(
        self,
        *,
        lifecycle_state: str,
        execution: dict,
        process_exit_code: int,
        timing: dict,
        phase_errors: list[dict],
        evidence_refs: dict[str, object],
    ) -> dict:
        """Atomically replace the initial record with its handled terminal state."""
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ExecutionRecordStorageError(
                f"cannot finalize ExecutionRecord at {self.path}: {error}"
            ) from error
        validate_execution_record(record)
        if record.get("attempt_id") != self.attempt_id:
            raise ExecutionRecordValidationError(
                "attempt identity changed before finalization"
            )
        if record.get("lifecycle_state") != "in_progress":
            raise ExecutionRecordValidationError("ExecutionRecord is already terminal")
        try:
            finished_at = timing["finished_at"]
        except (KeyError, TypeError) as error:
            raise ExecutionRecordValidationError(
                "terminal timing.finished_at is required"
            ) from error
        record.update(
            {
                "lifecycle_state": lifecycle_state,
                "finished_at": finished_at,
                "execution": execution,
                "process_outcome": {"exit_code": process_exit_code},
                "timing": timing,
                "phase_errors": phase_errors,
                "evidence_refs": evidence_refs,
            }
        )
        validate_execution_record(record)
        try:
            _replace_json(self.path, record)
        except OSError as error:
            raise ExecutionRecordStorageError(
                f"cannot finalize ExecutionRecord at {self.path}: {error}"
            ) from error
        return record


def load_execution_record(path: Path) -> dict:
    """Load and validate one authoritative ExecutionRecord."""
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ExecutionRecordValidationError(
            f"invalid ExecutionRecord at {path}: {error}"
        ) from error
    validate_execution_record(record)
    return record


def validate_execution_record(record: object) -> None:
    """Reject structural and cross-field accountability contradictions."""
    if not isinstance(record, dict):
        raise ExecutionRecordValidationError("ExecutionRecord must be an object")
    schema_version = record.get("schema_version")
    if schema_version not in {1, 2}:
        raise ExecutionRecordValidationError("unsupported ExecutionRecord schema_version")
    for key in ("attempt_id", "scenario", "started_at"):
        value = record.get(key)
        if not isinstance(value, str) or not value:
            raise ExecutionRecordValidationError(
                f"ExecutionRecord {key} must be a non-empty string"
            )

    lifecycle = record.get("lifecycle_state")
    if lifecycle not in {
        "in_progress",
        "completed",
        "preflight_rejected",
        "interrupted",
        "failed",
    }:
        raise ExecutionRecordValidationError(
            f"unsupported ExecutionRecord lifecycle_state: {lifecycle!r}"
        )
    execution = record.get("execution")
    if not isinstance(execution, dict):
        raise ExecutionRecordValidationError("ExecutionRecord execution must be an object")
    status = execution.get("status")
    eligible = execution.get("accounting_eligible")
    reason = execution.get("reason")
    if not isinstance(record.get("timing"), dict):
        raise ExecutionRecordValidationError("ExecutionRecord timing must be an object")
    timing = record["timing"]
    if timing.get("started_at") != record["started_at"]:
        raise ExecutionRecordValidationError(
            "ExecutionRecord timing.started_at contradicts started_at"
        )
    if not isinstance(timing.get("phases"), list):
        raise ExecutionRecordValidationError("ExecutionRecord timing.phases must be a list")
    if not isinstance(record.get("phase_errors"), list):
        raise ExecutionRecordValidationError("ExecutionRecord phase_errors must be a list")
    if not isinstance(record.get("evidence_refs"), dict):
        raise ExecutionRecordValidationError("ExecutionRecord evidence_refs must be an object")

    if lifecycle == "in_progress":
        if status != "non_accountable" or eligible is not False:
            raise ExecutionRecordValidationError(
                "in_progress ExecutionRecord must be non-accountable"
            )
        if reason is not None:
            raise ExecutionRecordValidationError(
                "in_progress ExecutionRecord cannot have a terminal reason"
            )
        if record.get("finished_at") is not None or record.get("process_outcome") is not None:
            raise ExecutionRecordValidationError(
                "in_progress ExecutionRecord cannot have terminal outcome fields"
            )
        if timing.get("finished_at") is not None or timing.get("total_seconds") is not None:
            raise ExecutionRecordValidationError(
                "in_progress ExecutionRecord cannot have terminal timing"
            )
        if record["phase_errors"]:
            raise ExecutionRecordValidationError(
                "in_progress ExecutionRecord cannot have terminal phase errors"
            )
        return

    finished_at = record.get("finished_at")
    if not isinstance(finished_at, str) or not finished_at:
        raise ExecutionRecordValidationError(
            f"{lifecycle} ExecutionRecord requires finished_at"
        )
    if timing.get("finished_at") != finished_at:
        raise ExecutionRecordValidationError(
            "ExecutionRecord timing.finished_at contradicts finished_at"
        )
    total_seconds = timing.get("total_seconds")
    if (
        not isinstance(total_seconds, (int, float))
        or isinstance(total_seconds, bool)
        or total_seconds < 0
    ):
        raise ExecutionRecordValidationError(
            "terminal ExecutionRecord requires non-negative timing.total_seconds"
        )
    process = record.get("process_outcome")
    exit_code = process.get("exit_code") if isinstance(process, dict) else None

    if lifecycle == "completed":
        if status != "completed" or eligible is not True:
            raise ExecutionRecordValidationError(
                "completed ExecutionRecord must be accountable"
            )
        if reason is not None or exit_code not in {0, 1}:
            raise ExecutionRecordValidationError(
                "completed ExecutionRecord requires no reason and exit code 0 or 1"
            )
        if record["phase_errors"]:
            raise ExecutionRecordValidationError(
                "completed ExecutionRecord cannot contain phase errors"
            )
        if schema_version == 2:
            provenance = record["evidence_refs"].get("execution_provenance")
            if not isinstance(provenance, dict):
                raise ExecutionRecordValidationError(
                    "schema-v2 completed ExecutionRecord requires execution provenance"
                )
            path = provenance.get("path")
            digest = provenance.get("sha256")
            if (
                not isinstance(path, str)
                or not path
                or not isinstance(digest, str)
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise ExecutionRecordValidationError(
                    "schema-v2 execution provenance binding is invalid"
                )
        return

    if status != "non_accountable" or eligible is not False:
        raise ExecutionRecordValidationError(
            f"{lifecycle} ExecutionRecord must be non-accountable"
        )
    if not isinstance(reason, str) or not reason:
        raise ExecutionRecordValidationError(
            f"{lifecycle} ExecutionRecord requires a canonical reason"
        )
    if exit_code != 2:
        raise ExecutionRecordValidationError(
            f"{lifecycle} ExecutionRecord requires exit code 2"
        )
    if not record["phase_errors"]:
        raise ExecutionRecordValidationError(
            f"{lifecycle} ExecutionRecord requires ordered phase errors"
        )
    for index, phase_error in enumerate(record["phase_errors"]):
        if not isinstance(phase_error, dict):
            raise ExecutionRecordValidationError(
                f"ExecutionRecord phase_errors[{index}] must be an object"
            )
        for key in ("phase", "kind", "reason", "message"):
            value = phase_error.get(key)
            if not isinstance(value, str) or not value:
                raise ExecutionRecordValidationError(
                    f"ExecutionRecord phase_errors[{index}].{key} "
                    "must be a non-empty string"
                )
    if record["phase_errors"][-1]["reason"] != reason:
        raise ExecutionRecordValidationError(
            "ExecutionRecord final phase error reason must match execution reason"
        )


def is_execution_record_accountable(record: dict) -> bool:
    """Return true only for a structurally valid completed accountable record."""
    validate_execution_record(record)
    return record["lifecycle_state"] == "completed"


def execution_record_reason(record: dict) -> str | None:
    """Return the canonical non-accountable reason, including abandonment."""
    validate_execution_record(record)
    if record["lifecycle_state"] == "in_progress":
        return "execution_abandoned"
    return record["execution"]["reason"]


def write_json_artifact(path: Path, payload: dict) -> None:
    """Durably create one JSON artifact without replacing prior evidence."""
    path = Path(path)
    try:
        _create_exclusive_json(path, payload)
    except (OSError, TypeError, ValueError) as error:
        raise ArtifactStorageError(
            f"cannot persist JSON artifact at {path}: "
            f"{type(error).__name__}: {error}"
        ) from error


def write_bytes_artifact(path: Path, payload: bytes) -> None:
    """Durably create one arbitrary evidence artifact without replacement."""
    path = Path(path)
    try:
        _create_exclusive_bytes(path, payload)
    except OSError as error:
        raise ArtifactStorageError(
            f"cannot persist artifact at {path}: {type(error).__name__}: {error}"
        ) from error


def _encoded_json(payload: dict) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _create_exclusive_json(path: Path, payload: dict) -> None:
    _create_exclusive_bytes(path, _encoded_json(payload))


def _create_exclusive_bytes(path: Path, payload: bytes) -> None:
    temp_path = path.parent / f".{path.name}.{uuid.uuid4()}.tmp"
    try:
        with temp_path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp_path, path)
        _fsync_directory(path.parent)
    finally:
        temp_path.unlink(missing_ok=True)


def _replace_json(path: Path, payload: dict) -> None:
    temp_path = path.parent / f".{path.name}.{uuid.uuid4()}.tmp"
    try:
        with temp_path.open("xb") as stream:
            stream.write(_encoded_json(payload))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        _fsync_directory(path.parent)
    finally:
        temp_path.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
