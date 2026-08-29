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
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from aiverify.injection.materialization import (
    InjectionMaterializerError,
    source_tree_sha256_for_commit,
    source_tree_sha256_from_worktree,
)
from aiverify.runner.command import CommandRunner, SubprocessCommandRunner
from aiverify.runner.execution_record import (
    ExecutionRecordStore,
    write_bytes_artifact,
)
from aiverify.runner.deterministic_backend import (
    DeterministicDriverPlanError,
    validate_deterministic_driver_plan,
)
from aiverify.runner.journey_backend import (
    CODEX_CLI,
    DEFAULT_JOURNEY_BACKEND,
    DETERMINISTIC_ANDROID_V1,
    DriverPlanBinding,
    JourneyBackendSelectionError,
    JourneyDriverSelection,
    SUPPORTED_JOURNEY_BACKENDS,
)
from aiverify.runner.run_spec import RunSpec


ADMISSION_SCHEMA_VERSION = 1
RUNNER_POLICY_VERSION = "m9-production-seam-v1"
DEFAULT_BACKEND = DEFAULT_JOURNEY_BACKEND
# Kept for callers that imported the old singular name; the supported set is
# exposed as SUPPORTED_BACKENDS for new policy consumers.
SUPPORTED_BACKEND = DEFAULT_BACKEND
SUPPORTED_BACKENDS = SUPPORTED_JOURNEY_BACKENDS
_PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")


class ProductionSeamAdmissionError(ValueError):
    """Raised when a formal runner consumes a missing or contradictory receipt."""


@dataclass(frozen=True)
class SourceAuthorityBinding:
    """Immutable authority-specific digest claims for one admitted source."""

    kind: str
    claims: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ValueError("source authority binding kind is required")
        if (
            not isinstance(self.claims, tuple)
            or self.claims != tuple(sorted(self.claims))
            or len({name for name, _ in self.claims}) != len(self.claims)
        ):
            raise ValueError("source authority binding claims must be unique and sorted")
        for name, digest in self.claims:
            if (
                not isinstance(name, str)
                or not name.strip()
                or not isinstance(digest, str)
                or not _SHA256_RE.fullmatch(digest)
            ):
                raise ValueError("source authority binding claim is invalid")

    def to_dict(self) -> dict[str, str]:
        body = {"kind": self.kind, **dict(self.claims)}
        body["identity_sha256"] = _sha256_bytes(_encoded_json(body))
        return body


@dataclass(frozen=True)
class HostWorktreeIdentity:
    """Both declared source bytes and every build-visible worktree byte."""

    clean: bool
    status_sha256: str
    source_tree_sha256: str
    complete_tree_sha256: str
    declared_injection: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.clean, bool) or not isinstance(
            self.declared_injection, bool
        ):
            raise ValueError("host worktree flags must be booleans")
        for field in (
            "status_sha256",
            "source_tree_sha256",
            "complete_tree_sha256",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
                raise ValueError(f"host worktree {field} is invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "clean": self.clean,
            "status_sha256": self.status_sha256,
            "source_tree_sha256": self.source_tree_sha256,
            "complete_tree_sha256": self.complete_tree_sha256,
            "declared_injection": self.declared_injection,
        }


@dataclass(frozen=True)
class HostAuthority:
    """Validated immutable Effective Execution Identity for a local host."""

    repository_root: str
    host_project: str
    origin: str
    commit: str
    worktree: HostWorktreeIdentity
    host_project_within_repository: bool
    source_authority: SourceAuthorityBinding | None = None

    def __post_init__(self) -> None:
        repository_root = Path(self.repository_root)
        host_project = Path(self.host_project)
        if not repository_root.is_absolute() or not host_project.is_absolute():
            raise ValueError("host authority paths must be absolute")
        if (
            str(repository_root.resolve()) != self.repository_root
            or str(host_project.resolve()) != self.host_project
        ):
            raise ValueError("host authority paths must be canonical")
        try:
            host_project.relative_to(repository_root)
        except ValueError as error:
            raise ValueError("host authority project is outside repository") from error
        if self.host_project_within_repository != (host_project != repository_root):
            raise ValueError("host authority project relationship is contradictory")
        if not isinstance(self.origin, str) or not self.origin.strip():
            raise ValueError("host authority origin is required")
        if not _GIT_SHA1_RE.fullmatch(self.commit):
            raise ValueError("host authority commit is invalid")
        if not isinstance(self.worktree, HostWorktreeIdentity):
            raise ValueError("host authority worktree identity is required")
        if self.source_authority is not None and not isinstance(
            self.source_authority, SourceAuthorityBinding
        ):
            raise ValueError("host source authority binding is invalid")
        if self.worktree.declared_injection != (self.source_authority is not None):
            raise ValueError("host source authority binding is contradictory")

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "repository_root": self.repository_root,
            "host_project": self.host_project,
            "origin": self.origin,
            "commit": self.commit,
            "worktree": self.worktree.to_dict(),
            "host_project_within_repository": self.host_project_within_repository,
        }
        if self.source_authority is not None:
            result["source_authority"] = self.source_authority.to_dict()
        return result


class SourceAuthority(ABC):
    """Read-only authority for one exact host source state."""

    @abstractmethod
    def resolve_host(
        self,
        spec: RunSpec,
        options: "PlannedRunnerOptions",
        runner: CommandRunner,
    ) -> HostAuthority:
        """Return the canonical host receipt or reject the source state."""


class CleanCheckoutSourceAuthority(SourceAuthority):
    """Preserve the existing policy that admits only a clean checkout."""

    def resolve_host(
        self,
        spec: RunSpec,
        options: "PlannedRunnerOptions",
        runner: CommandRunner,
    ) -> HostAuthority:
        return _resolve_clean_host(spec, options, runner)


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
    backend: str = DEFAULT_BACKEND
    android_bin: str = "android"
    adb_bin: str = "adb"
    codex_bin: str = "codex"
    runner_policy_version: str = RUNNER_POLICY_VERSION
    allow_host_project_subdir: bool = False
    driver_plan_path: Path | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a canonical, JSON-compatible representation."""
        result: dict[str, object] = {
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
        # Keep the legacy Codex receipt shape byte-for-byte compatible.  A
        # deterministic selection carries its plan as an explicit policy input.
        if self.driver_plan_path is not None:
            result["driver_plan_path"] = str(
                Path(self.driver_plan_path).expanduser().resolve()
            )
        return result

    def journey_driver_selection(self) -> JourneyDriverSelection:
        """Return the backend choice kept outside the backend-neutral Run Spec."""
        return JourneyDriverSelection(
            backend=self.backend,
            requested_model=self.requested_driver_model,
            driver_plan_path=self.driver_plan_path,
        )


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
    source_authority: SourceAuthority | None = None,
) -> AdmissionResult:
    """Admit exact Run Spec bytes and runner options without external side effects.

    The only subprocesses issued by this function are read-only git identity
    queries.  In particular it never invokes android, adb, codex, a build tool,
    a device, or a Verification Agent Backend.
    """
    runner = command_runner or SubprocessCommandRunner()
    authority = source_authority or CleanCheckoutSourceAuthority()
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
        resolved_host = authority.resolve_host(spec, options, runner)
        if not isinstance(resolved_host, HostAuthority):
            raise ProductionSeamAdmissionError(
                "source authority returned an invalid host identity"
            )
        _validate_host_authority(resolved_host, spec, options)
        host = resolved_host.to_dict()
        checks["host_identity"] = {"status": "passed"}
    except ProductionSeamAdmissionError as error:
        reasons.append(str(error))
        checks["host_identity"] = {"status": "failed", "message": str(error)}
    except (TypeError, ValueError):
        message = "source authority returned an invalid host identity"
        reasons.append(message)
        checks["host_identity"] = {"status": "failed", "message": message}

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

    driver_plan: dict[str, object] | None = None
    try:
        tools = _validate_runner_policy(spec, options)
        selection = options.journey_driver_selection()
        try:
            selection.validate()
        except JourneyBackendSelectionError as error:
            raise ProductionSeamAdmissionError(str(error)) from error
        if options.backend == DETERMINISTIC_ANDROID_V1:
            if source_bytes is None or spec.source_path is None:
                raise ProductionSeamAdmissionError(
                    "deterministic Driver Plan requires exact Run Spec source bytes"
                )
            plan_path = Path(selection.driver_plan_path).expanduser().resolve()
            try:
                plan_bytes = plan_path.read_bytes()
                binding = DriverPlanBinding(
                    path=plan_path,
                    sha256=_sha256_bytes(plan_bytes),
                    bytes=len(plan_bytes),
                )
                driver_plan = binding.to_dict()
                validate_deterministic_driver_plan(
                    plan_path,
                    serialized_run_spec=source_bytes,
                    run_spec_path=spec.source_path,
                    expected_actions=spec.scenario.user_actions,
                    plan_bytes=plan_bytes,
                )
            except (OSError, DeterministicDriverPlanError) as error:
                raise ProductionSeamAdmissionError(str(error)) from error
        else:
            try:
                binding = selection.bind_driver_plan()
            except JourneyBackendSelectionError as error:
                raise ProductionSeamAdmissionError(str(error)) from error
            if binding is not None:
                driver_plan = binding.to_dict()
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
    runner_policy: dict[str, object] = {
        "version": options.runner_policy_version,
        "backend": options.backend,
        "options": options.as_dict(),
        "tools": tools,
    }
    if driver_plan is not None:
        runner_policy["driver_plan"] = driver_plan
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
        "runner_policy": runner_policy,
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
    source_authority: SourceAuthority | None = None,
) -> AdmissionResult:
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
        source_authority=source_authority,
    )
    if current.receipt["run_spec"] != expected.receipt.get("run_spec"):
        raise ProductionSeamAdmissionError("admission receipt Run Spec drift")
    if current.receipt["runner_policy"] != expected.receipt.get("runner_policy"):
        raise ProductionSeamAdmissionError("admission receipt runner-option drift")
    current.require_admitted()
    if not _host_receipts_match(
        current.receipt["host"],
        expected.receipt.get("host"),
    ):
        raise ProductionSeamAdmissionError("admission receipt source/worktree drift")
    if current.receipt["target"] != expected.receipt.get("target"):
        raise ProductionSeamAdmissionError("admission receipt target drift")
    if current.receipt["artifact_namespace"] != expected.receipt.get(
        "artifact_namespace"
    ):
        raise ProductionSeamAdmissionError("admission receipt artifact namespace drift")
    return current


def _host_receipts_match(current: object, expected: object) -> bool:
    """Compare host identity, admitting only a pristine legacy clean receipt."""
    if current == expected:
        return True
    if not isinstance(current, Mapping) or not isinstance(expected, Mapping):
        return False
    current_host = dict(current)
    expected_host = dict(expected)
    if "source_authority" in current_host or "source_authority" in expected_host:
        return False
    current_worktree = current_host.get("worktree")
    expected_worktree = expected_host.get("worktree")
    if not isinstance(current_worktree, Mapping) or not isinstance(
        expected_worktree, Mapping
    ):
        return False
    legacy_worktree = dict(expected_worktree)
    if set(legacy_worktree) != {"clean", "status_sha256"} or legacy_worktree.get(
        "clean"
    ) is not True:
        return False
    current_worktree = dict(current_worktree)
    if current_worktree.get("source_tree_sha256") != current_worktree.get(
        "complete_tree_sha256"
    ):
        return False
    for field in (
        "source_tree_sha256",
        "complete_tree_sha256",
        "declared_injection",
    ):
        current_worktree.pop(field, None)
    current_host["worktree"] = current_worktree
    return current_host == expected_host


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


def _validate_host_authority(
    host: HostAuthority,
    spec: RunSpec,
    options: PlannedRunnerOptions,
) -> None:
    repository_root = Path(host.repository_root)
    host_project = Path(host.host_project)
    if repository_root != Path(options.workdir).resolve():
        raise ProductionSeamAdmissionError(
            "source authority repository contradicts runner workdir"
        )
    if host_project != spec.host_project.resolve():
        raise ProductionSeamAdmissionError(
            "source authority project contradicts Run Spec"
        )
    if host_project != repository_root and not options.allow_host_project_subdir:
        raise ProductionSeamAdmissionError(
            "host project subdirectory is not admitted by runner policy"
        )
    locator = spec.host_locator
    if locator is None:
        raise ProductionSeamAdmissionError(
            "portable host origin and commit locator is required"
        )
    if host.origin != locator.expected_origin:
        raise ProductionSeamAdmissionError(
            "source authority origin contradicts Run Spec locator"
        )
    expected_commit = options.expected_source_commit or locator.expected_commit
    if not _GIT_SHA1_RE.fullmatch(expected_commit) or host.commit != expected_commit:
        raise ProductionSeamAdmissionError(
            "source authority commit contradicts Run Spec locator"
        )


def _resolve_clean_host(
    spec: RunSpec,
    options: PlannedRunnerOptions,
    runner: CommandRunner,
) -> HostAuthority:
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
    try:
        source_tree_sha256 = source_tree_sha256_for_commit(repository_root, commit)
        complete_tree_sha256 = source_tree_sha256_from_worktree(
            repository_root,
            ignore_ownership_marker=False,
        )
    except (InjectionMaterializerError, OSError, RuntimeError, ValueError) as error:
        raise ProductionSeamAdmissionError(
            "host source tree identity is unavailable"
        ) from error
    return HostAuthority(
        repository_root=str(repository_root),
        host_project=str(host_project),
        origin=origin,
        commit=commit,
        worktree=HostWorktreeIdentity(
            clean=True,
            status_sha256=_sha256_bytes(status.encode("utf-8")),
            source_tree_sha256=source_tree_sha256,
            complete_tree_sha256=complete_tree_sha256,
        ),
        host_project_within_repository=host_project != repository_root,
    )


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
    try:
        selection = options.journey_driver_selection()
        selection.validate()
    except JourneyBackendSelectionError as error:
        raise ProductionSeamAdmissionError(str(error)) from error
    if not options.runner_policy_version.strip():
        raise ProductionSeamAdmissionError("runner policy version is required")
    if options.requested_l3_model is not None and not options.requested_l3_model.strip():
        raise ProductionSeamAdmissionError("requested L3 model cannot be empty")
    resolved: dict[str, object] = {}
    prerequisites = [
        ("android", options.android_bin),
        ("adb", options.adb_bin),
    ]
    if selection.backend == CODEX_CLI:
        prerequisites.append(("codex", options.codex_bin))
    for label, requested in prerequisites:
        path = _resolve_executable(requested)
        resolved[label] = {
            "requested": requested,
            "resolved_path": str(path),
            "sha256": _sha256_file(path),
        }
    resolved["model_selection"] = {
        "journey_driver": _journey_model_selection(selection),
        "l3_semantic_judge": _model_selection(options.requested_l3_model),
    }
    return resolved


def _journey_model_selection(selection: JourneyDriverSelection) -> dict[str, object]:
    if selection.backend == CODEX_CLI:
        return _model_selection(selection.requested_model)
    return {
        "policy": "deterministic_android_v1_no_model",
        "requested_model": None,
        "model_override_present": False,
    }


def _model_selection(requested_model: str | None) -> dict[str, object]:
    """Describe whether Codex CLI chooses its default or receives an override."""

    return {
        "policy": (
            "codex_cli_default"
            if requested_model is None
            else "explicit_model_override"
        ),
        "requested_model": requested_model,
        "model_override_present": requested_model is not None,
    }


def _validate_artifact_namespace(options: PlannedRunnerOptions) -> dict[str, object]:
    artifact_dir = Path(options.artifact_dir).resolve()
    run_dir = artifact_dir.parent
    if not artifact_dir.is_absolute() or artifact_dir == Path("/"):
        raise ProductionSeamAdmissionError("artifact namespace must be an absolute directory")
    if artifact_dir == run_dir or run_dir == Path("/"):
        raise ProductionSeamAdmissionError("artifact namespace must have a run directory")
    for name in (
        "execution-record.json",
        "verdict.json",
        "live-validation-gate.json",
        "runner-setup.json",
    ):
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
