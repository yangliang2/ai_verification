"""Side-effect-free admission for the production Run Spec seam.

Admission deliberately stops at the boundary before build, installation, device
access, or agent invocation.  It resolves the host with read-only git commands,
binds the exact Run Spec bytes, and records the runner policy that a later
formal invocation must consume unchanged.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from aiverify.runner.command import CommandRunner, SubprocessCommandRunner
from aiverify.runner.execution_record import (
    ExecutionRecordStore,
    write_bytes_artifact,
)
from aiverify.runner.run_spec import RunSpec


ADMISSION_SCHEMA_VERSION = 1
RUNNER_POLICY_VERSION = "m9-production-seam-v1"
SUPPORTED_BACKEND = "codex_cli"
_PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")


class ProductionSeamAdmissionError(ValueError):
    """Raised when a formal runner consumes a missing or contradictory receipt."""


@dataclass(frozen=True)
class PlannedRunnerOptions:
    """Exact runner policy planned for one formal invocation."""

    device: str
    workdir: Path
    artifact_dir: Path
    expected_source_commit: str | None = None
    launch: bool = True
    requested_driver_model: str | None = None
    requested_l3_model: str | None = None
    backend: str = SUPPORTED_BACKEND
    android_bin: str = "android"
    adb_bin: str = "adb"
    codex_bin: str = "codex"
    runner_policy_version: str = RUNNER_POLICY_VERSION
    allow_host_project_subdir: bool = False

    def as_dict(self) -> dict[str, object]:
        """Return a canonical, JSON-compatible representation."""
        return {
            "device": self.device,
            "workdir": str(Path(self.workdir).resolve()),
            "artifact_dir": str(Path(self.artifact_dir).resolve()),
            "expected_source_commit": self.expected_source_commit,
            "launch": self.launch,
            "requested_driver_model": self.requested_driver_model,
            "requested_l3_model": self.requested_l3_model,
            "backend": self.backend,
            "android_bin": self.android_bin,
            "adb_bin": self.adb_bin,
            "codex_bin": self.codex_bin,
            "runner_policy_version": self.runner_policy_version,
            "allow_host_project_subdir": self.allow_host_project_subdir,
        }


@dataclass(frozen=True)
class AdmissionResult:
    """Checksum-bound result of the side-effect-free admission pass."""

    admitted: bool
    receipt: dict[str, object]
    receipt_bytes: bytes
    receipt_sha256: str
    reasons: tuple[str, ...]

    def require_admitted(self) -> None:
        """Raise the formal-run error if this result is not admitted."""
        if not self.admitted:
            detail = "; ".join(self.reasons) or "unknown admission failure"
            raise ProductionSeamAdmissionError(detail)


def admit_production_seam(
    spec: RunSpec,
    options: PlannedRunnerOptions,
    *,
    serialized_run_spec: bytes | None = None,
    command_runner: CommandRunner | None = None,
) -> AdmissionResult:
    """Admit exact Run Spec bytes and runner options without external side effects.

    The only subprocesses issued by this function are read-only git identity
    queries.  In particular it never invokes android, adb, codex, a build tool,
    a device, or a Verification Agent Backend.
    """
    runner = command_runner or SubprocessCommandRunner()
    checks: dict[str, object] = {}
    reasons: list[str] = []
    source_bytes: bytes | None = None
    source_sha256: str | None = None

    try:
        source_bytes = _read_exact_run_spec(spec, serialized_run_spec)
        source_sha256 = _sha256_bytes(source_bytes)
        checks["run_spec_bytes"] = {
            "status": "passed",
            "sha256": source_sha256,
            "bytes": len(source_bytes),
        }
    except ProductionSeamAdmissionError as error:
        reasons.append(str(error))
        checks["run_spec_bytes"] = {"status": "failed", "message": str(error)}

    host: dict[str, object] = {}
    try:
        host = _resolve_host(spec, options, runner)
        checks["host_identity"] = {"status": "passed"}
    except ProductionSeamAdmissionError as error:
        reasons.append(str(error))
        checks["host_identity"] = {"status": "failed", "message": str(error)}

    try:
        target = _validate_target(spec, options)
        checks["target_declaration"] = {"status": "passed"}
    except ProductionSeamAdmissionError as error:
        reasons.append(str(error))
        target = _target_declaration(spec)
        checks["target_declaration"] = {
            "status": "failed",
            "message": str(error),
        }

    try:
        tools = _validate_runner_policy(spec, options)
        checks["runner_policy"] = {"status": "passed"}
    except ProductionSeamAdmissionError as error:
        reasons.append(str(error))
        tools = {}
        checks["runner_policy"] = {"status": "failed", "message": str(error)}

    try:
        artifact_namespace = _validate_artifact_namespace(options)
        checks["artifact_namespace"] = {"status": "passed"}
    except ProductionSeamAdmissionError as error:
        reasons.append(str(error))
        artifact_namespace = {
            "run_dir": str(Path(options.artifact_dir).resolve().parent),
            "artifact_dir": str(Path(options.artifact_dir).resolve()),
        }
        checks["artifact_namespace"] = {
            "status": "failed",
            "message": str(error),
        }

    admitted = not reasons
    receipt: dict[str, object] = {
        "schema_version": ADMISSION_SCHEMA_VERSION,
        "status": "admitted" if admitted else "rejected",
        "admitted": admitted,
        "reasons": reasons,
        "run_spec": {
            "path": str(spec.source_path.resolve()) if spec.source_path else None,
            "sha256": source_sha256,
            "serialized_bytes": len(source_bytes) if source_bytes is not None else None,
            "scenario": spec.scenario.id,
        },
        "host": host,
        "target": target,
        "runner_policy": {
            "version": options.runner_policy_version,
            "backend": options.backend,
            "options": options.as_dict(),
            "tools": tools,
        },
        "artifact_namespace": artifact_namespace,
        "checks": checks,
        "side_effects": {
            "external": False,
            "build": False,
            "device": False,
            "agent": False,
            "declaration": "read-only git and local source/metadata inspection only",
        },
    }
    receipt_bytes = _encoded_json(receipt)
    return AdmissionResult(
        admitted=admitted,
        receipt=receipt,
        receipt_bytes=receipt_bytes,
        receipt_sha256=_sha256_bytes(receipt_bytes),
        reasons=tuple(reasons),
    )


def write_admission_receipt(result: AdmissionResult, path: Path) -> None:
    """Create one durable admission receipt without replacing prior evidence."""
    write_bytes_artifact(Path(path), result.receipt_bytes)


def verify_admitted_receipt(
    receipt: Mapping[str, object] | AdmissionResult,
    spec: RunSpec,
    options: PlannedRunnerOptions,
    *,
    command_runner: CommandRunner | None = None,
) -> None:
    """Re-admit and compare a receipt before any formal runner side effect."""
    if isinstance(receipt, AdmissionResult):
        expected = receipt
    else:
        payload = dict(receipt)
        expected_bytes = _encoded_json(payload)
        expected = AdmissionResult(
            admitted=payload.get("admitted") is True,
            receipt=payload,
            receipt_bytes=expected_bytes,
            receipt_sha256=_sha256_bytes(expected_bytes),
            reasons=tuple(
                value for value in payload.get("reasons", []) if isinstance(value, str)
            ),
        )
    expected.require_admitted()
    current = admit_production_seam(
        spec,
        options,
        command_runner=command_runner,
    )
    current.require_admitted()
    if current.receipt["run_spec"] != expected.receipt.get("run_spec"):
        raise ProductionSeamAdmissionError("admission receipt Run Spec drift")
    if current.receipt["runner_policy"] != expected.receipt.get("runner_policy"):
        raise ProductionSeamAdmissionError("admission receipt runner-option drift")
    if current.receipt["host"] != expected.receipt.get("host"):
        raise ProductionSeamAdmissionError("admission receipt source/worktree drift")
    if current.receipt["target"] != expected.receipt.get("target"):
        raise ProductionSeamAdmissionError("admission receipt target drift")
    if current.receipt["artifact_namespace"] != expected.receipt.get(
        "artifact_namespace"
    ):
        raise ProductionSeamAdmissionError("admission receipt artifact namespace drift")


def establish_and_abandon_temporary_record(
    run_dir: Path,
    *,
    scenario: str,
    admission_receipt: AdmissionResult,
) -> dict[str, object]:
    """Exercise a temporary, terminally abandoned record outside formal attempts."""
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    store = ExecutionRecordStore.establish(
        Path(run_dir),
        artifact_dir=Path(run_dir) / "temporary-artifacts",
        scenario=scenario,
        started_at=started_at,
    )
    finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return store.finalize(
        lifecycle_state="preflight_rejected",
        execution={
            "status": "non_accountable",
            "accounting_eligible": False,
            "reason": "production_seam_admission_rejected",
            "message": "; ".join(admission_receipt.reasons) or "temporary admission envelope",
        },
        process_exit_code=2,
        timing={
            "started_at": started_at,
            "finished_at": finished_at,
            "total_seconds": 0.0,
            "phases": [
                {
                    "phase": "production-seam-admission",
                    "kind": "preflight",
                    "seconds": 0.0,
                }
            ],
        },
        phase_errors=[
            {
                "phase": "production-seam-admission",
                "kind": "preflight",
                "reason": "production_seam_admission_rejected",
                "message": "; ".join(admission_receipt.reasons)
                or "temporary admission envelope",
            }
        ],
        evidence_refs={"admission_receipt_sha256": admission_receipt.receipt_sha256},
    )


def _read_exact_run_spec(spec: RunSpec, serialized: bytes | None) -> bytes:
    if spec.source_path is None or spec.source_sha256 is None:
        raise ProductionSeamAdmissionError("exact serialized Run Spec source is unavailable")
    try:
        source = spec.source_path.resolve().read_bytes()
    except OSError as error:
        raise ProductionSeamAdmissionError(
            f"exact serialized Run Spec source cannot be read: {error}"
        ) from error
    digest = _sha256_bytes(source)
    if digest != spec.source_sha256:
        raise ProductionSeamAdmissionError("exact serialized Run Spec source drifted")
    if serialized is not None and serialized != source:
        raise ProductionSeamAdmissionError("provided serialized Run Spec bytes drifted")
    return source


def _resolve_host(
    spec: RunSpec,
    options: PlannedRunnerOptions,
    runner: CommandRunner,
) -> dict[str, object]:
    host_project = spec.host_project.resolve()
    workdir = Path(options.workdir).resolve()
    if not host_project.is_dir():
        raise ProductionSeamAdmissionError("host project directory is missing")
    root_result = _git(runner, options, workdir, "rev-parse", "--show-toplevel")
    repository_root = Path(root_result.stdout.strip()).resolve()
    if repository_root != workdir:
        raise ProductionSeamAdmissionError("runner workdir is not the repository root")
    if host_project != repository_root:
        if not options.allow_host_project_subdir:
            raise ProductionSeamAdmissionError(
                "host project subdirectory is not admitted by runner policy"
            )
        try:
            host_project.relative_to(repository_root)
        except ValueError as error:
            raise ProductionSeamAdmissionError(
                "host project is outside the repository root"
            ) from error
    origin = _git(runner, options, workdir, "remote", "get-url", "origin").stdout.strip()
    commit = _git(runner, options, workdir, "rev-parse", "HEAD").stdout.strip().lower()
    status = _git(
        runner,
        options,
        workdir,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    ).stdout
    if not origin or not _GIT_SHA1_RE.fullmatch(commit):
        raise ProductionSeamAdmissionError("host origin or commit identity is unavailable")
    if status.strip():
        raise ProductionSeamAdmissionError("host worktree is not clean")
    locator = spec.host_locator
    if locator is None:
        raise ProductionSeamAdmissionError("portable host origin and commit locator is required")
    if origin != locator.expected_origin:
        raise ProductionSeamAdmissionError("host origin contradicts Run Spec locator")
    expected_commit = options.expected_source_commit or locator.expected_commit
    if not _GIT_SHA1_RE.fullmatch(expected_commit):
        raise ProductionSeamAdmissionError(
            "expected source commit binding is not a Git commit"
        )
    if commit != expected_commit:
        raise ProductionSeamAdmissionError("host commit contradicts Run Spec locator")
    return {
        "repository_root": str(repository_root),
        "host_project": str(host_project),
        "origin": origin,
        "commit": commit,
        "worktree": {
            "clean": True,
            "status_sha256": _sha256_bytes(status.encode("utf-8")),
        },
        "host_project_within_repository": host_project != repository_root,
    }


def _validate_target(spec: RunSpec, options: PlannedRunnerOptions) -> dict[str, object]:
    if not _PACKAGE_RE.fullmatch(spec.package):
        raise ProductionSeamAdmissionError("Run Spec package identity is invalid")
    if not spec.activity or not spec.activity.strip():
        raise ProductionSeamAdmissionError("Run Spec activity identity is required")
    glob = spec.apk_glob.strip()
    glob_path = Path(glob)
    if glob_path.is_absolute() or any(part == ".." for part in glob_path.parts):
        raise ProductionSeamAdmissionError("APK locator escapes the host project")
    if not glob:
        raise ProductionSeamAdmissionError("APK locator declaration is empty")
    if not options.device.strip():
        raise ProductionSeamAdmissionError("deployment device identity is required")
    return _target_declaration(spec)


def _target_declaration(spec: RunSpec) -> dict[str, object]:
    return {
        "package": spec.package,
        "activity": spec.activity,
        "apk_locator": {"glob": spec.apk_glob, "relative_to": str(spec.host_project.resolve())},
    }


def _validate_runner_policy(
    spec: RunSpec,
    options: PlannedRunnerOptions,
) -> dict[str, object]:
    if options.backend != SUPPORTED_BACKEND:
        raise ProductionSeamAdmissionError(
            f"unsupported Verification Agent Backend: {options.backend}"
        )
    if not options.runner_policy_version.strip():
        raise ProductionSeamAdmissionError("runner policy version is required")
    if not options.requested_driver_model or not options.requested_driver_model.strip():
        raise ProductionSeamAdmissionError("requested driver model is required")
    if options.requested_l3_model is not None and not options.requested_l3_model.strip():
        raise ProductionSeamAdmissionError("requested L3 model cannot be empty")
    resolved: dict[str, object] = {}
    for label, requested in (
        ("android", options.android_bin),
        ("adb", options.adb_bin),
        ("codex", options.codex_bin),
    ):
        path = _resolve_executable(requested)
        resolved[label] = {
            "requested": requested,
            "resolved_path": str(path),
            "sha256": _sha256_file(path),
        }
    return resolved


def _validate_artifact_namespace(options: PlannedRunnerOptions) -> dict[str, object]:
    artifact_dir = Path(options.artifact_dir).resolve()
    run_dir = artifact_dir.parent
    if not artifact_dir.is_absolute() or artifact_dir == Path("/"):
        raise ProductionSeamAdmissionError("artifact namespace must be an absolute directory")
    if artifact_dir == run_dir or run_dir == Path("/"):
        raise ProductionSeamAdmissionError("artifact namespace must have a run directory")
    for name in ("execution-record.json", "verdict.json", "live-validation-gate.json"):
        if (run_dir / name).exists():
            raise ProductionSeamAdmissionError(
                f"formal attempt namespace already contains {name}"
            )
    return {
        "run_dir": str(run_dir),
        "artifact_dir": str(artifact_dir),
        "formal_outputs_absent": True,
    }


def _git(
    runner: CommandRunner,
    options: PlannedRunnerOptions,
    workdir: Path,
    *args: str,
):
    result = runner.run(
        ["git", *args], cwd=workdir, timeout_seconds=30
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no output"
        raise ProductionSeamAdmissionError(
            f"git identity command failed ({' '.join(args)}): {detail}"
        )
    return result


def _resolve_executable(requested: str) -> Path:
    candidate = Path(requested).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() or "/" in requested else None
    if resolved is None:
        found = shutil.which(requested)
        resolved = Path(found).resolve() if found else None
    if resolved is None or not resolved.is_file() or not resolved.stat().st_mode & 0o111:
        raise ProductionSeamAdmissionError(f"runner prerequisite is not executable: {requested}")
    return resolved


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _encoded_json(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
