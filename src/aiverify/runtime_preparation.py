"""Source-authorized, non-runtime preparation for one runner handoff."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from aiverify.injection import (
    InjectionAdmission,
    InjectionMaterializerError,
    VerifierPacket,
    inspect_materialized_receipt_source,
    source_tree_sha256_for_commit,
)
from aiverify.runner.admission import (
    CleanCheckoutSourceAuthority,
    PlannedRunnerOptions,
    ProductionSeamAdmissionError,
    SourceAuthority,
    admit_production_seam,
    verify_admitted_receipt,
)
from aiverify.runner.command import CommandResult, CommandRunner, SubprocessCommandRunner
from aiverify.runner.run_spec import RunSpec


RUNTIME_PREPARATION_SCHEMA_VERSION = 1
RUNTIME_PREPARATION_CLAIM_BOUNDARY = "local_source_build_preparation_only"
_PROHIBITED_EXECUTABLES = frozenset(
    {
        "adb",
        "android",
        "bash",
        "cmd",
        "codex",
        "emulator",
        "fish",
        "powershell",
        "pwsh",
        "sh",
        "zsh",
    }
)
_PACKAGE_LINE = re.compile(r"^package: name='([^']+)'", re.MULTILINE)
_ACTIVITY_LINE = re.compile(r"^launchable-activity: name='([^']+)'", re.MULTILINE)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: Mapping[str, object]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )


def _identity(value: Mapping[str, object]) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class RuntimeBuildRecipe:
    """Canonical shell-free build request plus the expected APK locator."""

    args: tuple[str, ...]
    timeout_seconds: int
    apk_glob: str


@dataclass(frozen=True)
class ApkMetadata:
    """Manifest identities needed by the runner contract."""

    package: str
    launcher_activity: str


class ApkInspector(ABC):
    """Inspect package and launcher identity without installing an APK."""

    @abstractmethod
    def inspect(self, apk_path: Path) -> ApkMetadata:
        """Return the manifest identity for one exact local APK."""


class ApkInspectionError(RuntimeError):
    """Raised when a local APK manifest cannot be inspected."""


class AaptApkInspector(ApkInspector):
    """Production APK inspector backed by ``aapt2 dump badging``."""

    def __init__(
        self,
        executable: str = "aapt2",
        *,
        command_runner: CommandRunner | None = None,
    ) -> None:
        if command_runner is not None and not isinstance(command_runner, CommandRunner):
            raise ValueError("APK inspector command runner must implement CommandRunner")
        self._executable = executable
        self._runner = command_runner or SubprocessCommandRunner()

    def inspect(self, apk_path: Path) -> ApkMetadata:
        try:
            result = self._runner.run(
                [self._executable, "dump", "badging", str(Path(apk_path).resolve())],
                cwd=Path(apk_path).resolve().parent,
                timeout_seconds=30,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            raise ApkInspectionError("APK manifest inspection failed") from error
        if (
            not isinstance(result, CommandResult)
            or not isinstance(result.stdout, str)
            or result.returncode != 0
        ):
            raise ApkInspectionError("APK manifest inspection failed")
        package_match = _PACKAGE_LINE.search(result.stdout)
        activity_match = _ACTIVITY_LINE.search(result.stdout)
        if package_match is None or activity_match is None:
            raise ApkInspectionError("APK package or launcher activity is unavailable")
        package = package_match.group(1)
        activity = activity_match.group(1)
        if activity.startswith("."):
            activity = f"{package}{activity}"
        elif "." not in activity:
            activity = f"{package}.{activity}"
        return ApkMetadata(package=package, launcher_activity=activity)


@dataclass(frozen=True)
class RuntimePreparationReceipt:
    """Checksum-bound prepared or stable rejected preparation outcome."""

    prepared: bool
    receipt_bytes: bytes
    receipt_sha256: str
    rejection_code: str | None

    @property
    def receipt(self) -> dict[str, object]:
        """Decode a fresh copy so callers cannot mutate the sealed outcome."""
        value = json.loads(self.receipt_bytes)
        if not isinstance(value, dict):
            raise RuntimeError("runtime preparation receipt bytes are invalid")
        return value


class RuntimePreparationVerificationError(ValueError):
    """Raised when a prepared handoff no longer matches live local state."""


class SealedInjectionSourceAuthority(SourceAuthority):
    """Admit exactly one sealed injection and its matching blind-safe packet."""

    def __init__(
        self,
        admission: InjectionAdmission,
        packet: VerifierPacket,
    ) -> None:
        self._admission = admission
        self._packet = packet

    def resolve_host(
        self,
        spec: RunSpec,
        options: PlannedRunnerOptions,
        runner: CommandRunner,
    ) -> dict[str, object]:
        admission = self._admission
        packet = self._packet
        if not isinstance(admission, InjectionAdmission) or admission.status != "sealed":
            raise ProductionSeamAdmissionError("sealed injection admission is required")
        if not isinstance(packet, VerifierPacket):
            raise ProductionSeamAdmissionError("blind-safe injection packet is required")
        receipt = admission.receipt
        package = admission.package
        if receipt is None or receipt.worktree is None or package is None:
            raise ProductionSeamAdmissionError("sealed injection source is incomplete")
        try:
            receipt_path = Path(receipt.worktree.path).resolve(strict=True)
            packet_path = Path(packet.worktree_path).resolve(strict=True)
            host_project = spec.host_project.resolve(strict=True)
            workdir = Path(options.workdir).resolve(strict=True)
        except OSError as error:
            raise ProductionSeamAdmissionError(
                "sealed injection worktree is unavailable"
            ) from error
        if len({receipt_path, packet_path, host_project, workdir}) != 1:
            raise ProductionSeamAdmissionError("sealed injection worktree path mismatch")
        if (
            packet.receipt_identity_sha256 != receipt.receipt_identity_sha256
            or package.receipt_identity_sha256 != receipt.receipt_identity_sha256
            or packet.materialized_source_tree_sha256
            != receipt.result_source_tree_sha256
            or packet.result_diff_sha256 != receipt.result_diff_sha256
            or packet.source_commit != receipt.worktree.baseline_commit
            or receipt.worktree.candidate_identity_sha256
            != package.candidate_identity_sha256
        ):
            raise ProductionSeamAdmissionError("sealed injection identity mismatch")
        if packet.patch_path:
            try:
                declared_patch = Path(packet.patch_path).resolve(strict=True).read_bytes()
            except OSError as error:
                raise ProductionSeamAdmissionError(
                    "sealed injection packet material is unavailable"
                ) from error
            if declared_patch != packet.patch_text.encode("utf-8"):
                raise ProductionSeamAdmissionError(
                    "sealed injection packet material drifted"
                )
        locator = spec.host_locator
        if locator is None:
            raise ProductionSeamAdmissionError(
                "portable host origin and commit locator is required"
            )
        expected_commit = options.expected_source_commit or locator.expected_commit
        if (
            locator.expected_origin != packet.source_origin
            or expected_commit != packet.source_commit
        ):
            raise ProductionSeamAdmissionError(
                "Run Spec locator contradicts sealed injection"
            )
        origin = self._git(runner, workdir, "remote", "get-url", "origin")
        commit = self._git(runner, workdir, "rev-parse", "HEAD").lower()
        root = Path(
            self._git(runner, workdir, "rev-parse", "--show-toplevel")
        ).resolve()
        if root != workdir or origin != packet.source_origin or commit != packet.source_commit:
            raise ProductionSeamAdmissionError(
                "sealed injection Git provenance mismatch"
            )
        try:
            baseline_tree = source_tree_sha256_for_commit(workdir, commit)
            inspection = inspect_materialized_receipt_source(receipt)
        except (InjectionMaterializerError, OSError, RuntimeError, ValueError) as error:
            raise ProductionSeamAdmissionError(
                "sealed injection source identity is unavailable"
            ) from error
        if baseline_tree != packet.baseline_source_tree_sha256:
            raise ProductionSeamAdmissionError(
                "sealed injection baseline source identity mismatch"
            )
        authority = {
            "kind": "sealed_injection",
            "admission_identity_sha256": admission.identity_sha256,
            "packet_identity_sha256": packet.identity_sha256,
            "receipt_identity_sha256": receipt.receipt_identity_sha256,
            "result_identity_sha256": receipt.result_identity_sha256,
            "materialized_source_tree_sha256": inspection.source_tree_sha256,
            "result_diff_sha256": inspection.result_diff_sha256,
        }
        authority["identity_sha256"] = _identity(authority)
        return {
            "repository_root": str(root),
            "host_project": str(host_project),
            "origin": origin,
            "commit": commit,
            "worktree": {
                "clean": False,
                "status_sha256": inspection.status_sha256,
                "declared_injection": True,
            },
            "host_project_within_repository": False,
            "source_authority": authority,
        }

    @staticmethod
    def _git(runner: CommandRunner, workdir: Path, *arguments: str) -> str:
        result = runner.run(
            ["git", *arguments],
            cwd=workdir,
            timeout_seconds=30,
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise ProductionSeamAdmissionError(
                f"sealed injection Git identity failed ({' '.join(arguments)})"
            )
        return result.stdout.strip()


def _rejected(code: str) -> RuntimePreparationReceipt:
    document: dict[str, object] = {
        "schema_version": RUNTIME_PREPARATION_SCHEMA_VERSION,
        "status": "rejected",
        "prepared": False,
        "rejection_code": code,
        "claim_boundary": RUNTIME_PREPARATION_CLAIM_BOUNDARY,
    }
    document["receipt_identity_sha256"] = _identity(document)
    encoded = _canonical_bytes(document)
    return RuntimePreparationReceipt(
        prepared=False,
        receipt_bytes=encoded,
        receipt_sha256=_sha256_bytes(encoded),
        rejection_code=code,
    )


def _validate_recipe(recipe: RuntimeBuildRecipe, spec: RunSpec) -> str | None:
    if not isinstance(recipe, RuntimeBuildRecipe):
        return "invalid_build_recipe"
    if (
        not isinstance(recipe.args, tuple)
        or not recipe.args
        or any(not isinstance(argument, str) or not argument for argument in recipe.args)
    ):
        return "invalid_build_recipe"
    if (
        not isinstance(recipe.timeout_seconds, int)
        or isinstance(recipe.timeout_seconds, bool)
        or not 1 <= recipe.timeout_seconds <= 3600
    ):
        return "invalid_build_recipe"
    locator = Path(recipe.apk_glob)
    if (
        not recipe.apk_glob
        or locator.is_absolute()
        or ".." in locator.parts
        or recipe.apk_glob != spec.apk_glob
    ):
        return "invalid_build_recipe"
    argument_basenames = {Path(argument).name.lower() for argument in recipe.args}
    if argument_basenames & _PROHIBITED_EXECUTABLES:
        return "prohibited_build_command"
    normalized_arguments = {argument.lower() for argument in recipe.args[1:]}
    if any(
        argument.startswith(("install", "connected", "device"))
        or argument in {"adb", "android", "codex"}
        for argument in normalized_arguments
    ):
        return "prohibited_build_command"
    return None


def _resolve_build_executable(command: str, host: Path) -> Path:
    candidate = Path(command).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
    elif "/" in command:
        resolved = (host / candidate).resolve()
        try:
            resolved.relative_to(host)
        except ValueError as error:
            raise OSError("relative build executable escapes host") from error
    else:
        found = shutil.which(command)
        if found is None:
            raise OSError("build executable is unavailable")
        resolved = Path(found).resolve()
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise OSError("build executable is unavailable")
    return resolved


def _locate_apk(host: Path, locator: str) -> tuple[Path | None, str | None]:
    matches: list[Path] = []
    escaped = False
    for candidate in host.glob(locator):
        if not candidate.is_file():
            continue
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(host)
        except (OSError, ValueError):
            escaped = True
            continue
        matches.append(resolved)
    if escaped:
        return None, "apk_outside_host"
    ordered = sorted(matches, key=lambda path: path.as_posix())
    if not ordered:
        return None, "apk_missing"
    if len(ordered) != 1:
        return None, "apk_ambiguous"
    return ordered[0], None


def prepare_runtime_case(
    *,
    source_authority: SourceAuthority,
    build_recipe: RuntimeBuildRecipe,
    spec: RunSpec,
    options: PlannedRunnerOptions,
    build_runner: CommandRunner | None = None,
    apk_inspector: ApkInspector | None = None,
    admission_command_runner: CommandRunner | None = None,
) -> RuntimePreparationReceipt:
    """Admit, build, inspect, and seal one local APK without runtime effects."""
    if not isinstance(spec, RunSpec):
        return _rejected("invalid_run_spec")
    if not isinstance(options, PlannedRunnerOptions):
        return _rejected("invalid_runner_options")
    if not isinstance(source_authority, SourceAuthority):
        return _rejected("invalid_source_authority")
    if build_runner is not None and not isinstance(build_runner, CommandRunner):
        return _rejected("invalid_build_runner")
    if admission_command_runner is not None and not isinstance(
        admission_command_runner, CommandRunner
    ):
        return _rejected("invalid_admission_runner")
    recipe_rejection = _validate_recipe(build_recipe, spec)
    if recipe_rejection is not None:
        return _rejected(recipe_rejection)
    if not isinstance(apk_inspector, ApkInspector):
        return _rejected("apk_inspector_unavailable")

    try:
        admission = admit_production_seam(
            spec,
            options,
            command_runner=admission_command_runner,
            source_authority=source_authority,
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        return _rejected("source_admission_unavailable")
    if not admission.admitted:
        checks = admission.receipt.get("checks")
        host_check = checks.get("host_identity") if isinstance(checks, dict) else None
        return _rejected(
            "source_admission_rejected"
            if isinstance(host_check, dict) and host_check.get("status") == "failed"
            else "production_admission_rejected"
        )

    host = Path(spec.host_project).resolve()
    try:
        build_executable = _resolve_build_executable(
            build_recipe.args[0],
            host,
        )
        build_executable_sha256 = _sha256_file(build_executable)
    except OSError:
        return _rejected("build_executable_unavailable")
    runner = build_runner or SubprocessCommandRunner()
    started = time.monotonic()
    try:
        build_result = runner.run(
            list(build_recipe.args),
            cwd=host,
            timeout_seconds=build_recipe.timeout_seconds,
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        return _rejected("build_unavailable")
    duration_seconds = round(max(0.0, time.monotonic() - started), 6)
    if (
        not isinstance(build_result, CommandResult)
        or not isinstance(build_result.args, list)
        or not isinstance(build_result.stdout, str)
        or not isinstance(build_result.stderr, str)
        or not isinstance(build_result.returncode, int)
        or isinstance(build_result.returncode, bool)
    ):
        return _rejected("build_unavailable")
    if build_result.args != list(build_recipe.args):
        return _rejected("build_command_mismatch")
    if build_result.returncode == 124:
        return _rejected("build_timeout")
    if build_result.returncode != 0:
        return _rejected("build_failed")

    try:
        apk_path, apk_rejection = _locate_apk(host, build_recipe.apk_glob)
    except (OSError, RuntimeError, ValueError):
        return _rejected("apk_locator_failed")
    if apk_rejection is not None or apk_path is None:
        return _rejected(apk_rejection or "apk_missing")
    try:
        apk_bytes = apk_path.read_bytes()
        metadata = apk_inspector.inspect(apk_path)
    except (ApkInspectionError, OSError, RuntimeError, TypeError, ValueError):
        return _rejected("apk_inspection_failed")
    if not isinstance(metadata, ApkMetadata):
        return _rejected("apk_inspection_failed")
    if metadata.package != spec.package:
        return _rejected("apk_package_mismatch")
    if metadata.launcher_activity != spec.activity:
        return _rejected("apk_activity_mismatch")
    try:
        post_build_admission = verify_admitted_receipt(
            admission,
            spec,
            options,
            command_runner=admission_command_runner,
            source_authority=source_authority,
        )
    except (OSError, ProductionSeamAdmissionError, RuntimeError, TypeError, ValueError):
        return _rejected("post_build_source_drift")

    assert spec.source_path is not None
    try:
        source_bytes = spec.source_path.read_bytes()
    except OSError:
        return _rejected("post_build_run_spec_drift")
    if spec.source_sha256 != _sha256_bytes(source_bytes):
        return _rejected("post_build_run_spec_drift")
    build_identity: dict[str, object] = {
        "args": list(build_recipe.args),
        "apk_glob": build_recipe.apk_glob,
        "cwd": str(host),
        "timeout_seconds": build_recipe.timeout_seconds,
        "returncode": build_result.returncode,
        "duration_seconds": duration_seconds,
        "stdout_sha256": _sha256_bytes(build_result.stdout.encode("utf-8")),
        "stderr_sha256": _sha256_bytes(build_result.stderr.encode("utf-8")),
        "executable": {
            "path": str(build_executable),
            "sha256": build_executable_sha256,
        },
    }
    build_identity["identity_sha256"] = _identity(build_identity)
    host_receipt = admission.receipt["host"]
    post_build_host_receipt = post_build_admission.receipt["host"]
    assert isinstance(host_receipt, dict)
    assert isinstance(post_build_host_receipt, dict)
    source_identity = {
        "authority_kind": type(source_authority).__name__,
        "identity_sha256": _identity(host_receipt),
        "before": host_receipt,
        "after": post_build_host_receipt,
    }
    document: dict[str, object] = {
        "schema_version": RUNTIME_PREPARATION_SCHEMA_VERSION,
        "status": "prepared",
        "prepared": True,
        "rejection_code": None,
        "claim_boundary": RUNTIME_PREPARATION_CLAIM_BOUNDARY,
        "run_spec": {
            "path": str(spec.source_path.resolve()),
            "bytes": len(source_bytes),
            "sha256": _sha256_bytes(source_bytes),
            "scenario": spec.scenario.id,
        },
        "source": source_identity,
        "production_admission": admission.receipt,
        "production_admission_sha256": admission.receipt_sha256,
        "build": build_identity,
        "apk": {
            "path": apk_path.relative_to(host).as_posix(),
            "bytes": len(apk_bytes),
            "sha256": _sha256_bytes(apk_bytes),
            "package": metadata.package,
            "launcher_activity": metadata.launcher_activity,
        },
    }
    document["receipt_identity_sha256"] = _identity(document)
    encoded = _canonical_bytes(document)
    return RuntimePreparationReceipt(
        prepared=True,
        receipt_bytes=encoded,
        receipt_sha256=_sha256_bytes(encoded),
        rejection_code=None,
    )


def _verified_receipt_document(
    receipt: RuntimePreparationReceipt | Mapping[str, object],
) -> dict[str, object]:
    if isinstance(receipt, RuntimePreparationReceipt):
        document = receipt.receipt
        encoded = _canonical_bytes(document)
        if (
            encoded != receipt.receipt_bytes
            or _sha256_bytes(encoded) != receipt.receipt_sha256
        ):
            raise RuntimePreparationVerificationError(
                "runtime preparation receipt bytes drifted"
            )
    elif isinstance(receipt, Mapping):
        document = dict(receipt)
    else:
        raise RuntimePreparationVerificationError(
            "runtime preparation receipt is unavailable"
        )
    identity = document.get("receipt_identity_sha256")
    identity_document = dict(document)
    identity_document.pop("receipt_identity_sha256", None)
    if not isinstance(identity, str) or identity != _identity(identity_document):
        raise RuntimePreparationVerificationError(
            "runtime preparation receipt identity drifted"
        )
    if (
        document.get("schema_version") != RUNTIME_PREPARATION_SCHEMA_VERSION
        or document.get("status") != "prepared"
        or document.get("prepared") is not True
        or document.get("rejection_code") is not None
        or document.get("claim_boundary") != RUNTIME_PREPARATION_CLAIM_BOUNDARY
    ):
        raise RuntimePreparationVerificationError(
            "runtime preparation receipt is not prepared"
        )
    return document


def verify_runtime_preparation_receipt(
    receipt: RuntimePreparationReceipt | Mapping[str, object],
    *,
    spec: RunSpec,
    options: PlannedRunnerOptions,
    source_authority: SourceAuthority,
    apk_inspector: ApkInspector,
    command_runner: CommandRunner | None = None,
) -> None:
    """Revalidate source, Run Spec, options, receipt, and APK before runtime."""
    document = _verified_receipt_document(receipt)
    if not isinstance(spec, RunSpec) or not isinstance(options, PlannedRunnerOptions):
        raise RuntimePreparationVerificationError(
            "runtime preparation contract is invalid"
        )
    if not isinstance(source_authority, SourceAuthority):
        raise RuntimePreparationVerificationError(
            "runtime preparation source authority is unavailable"
        )
    if not isinstance(apk_inspector, ApkInspector):
        raise RuntimePreparationVerificationError(
            "runtime preparation APK inspector is unavailable"
        )
    if command_runner is not None and not isinstance(command_runner, CommandRunner):
        raise RuntimePreparationVerificationError(
            "runtime preparation admission runner is unavailable"
        )
    run_spec = document.get("run_spec")
    if not isinstance(run_spec, dict) or spec.source_path is None:
        raise RuntimePreparationVerificationError(
            "runtime preparation Run Spec is unavailable"
        )
    try:
        source_bytes = spec.source_path.resolve().read_bytes()
    except OSError as error:
        raise RuntimePreparationVerificationError(
            "runtime preparation Run Spec is unavailable"
        ) from error
    expected_run_spec = {
        "path": str(spec.source_path.resolve()),
        "bytes": len(source_bytes),
        "sha256": _sha256_bytes(source_bytes),
        "scenario": spec.scenario.id,
    }
    if run_spec != expected_run_spec:
        raise RuntimePreparationVerificationError(
            "runtime preparation Run Spec drifted"
        )

    admission = document.get("production_admission")
    if not isinstance(admission, dict):
        raise RuntimePreparationVerificationError(
            "runtime preparation admission is unavailable"
        )
    if document.get("production_admission_sha256") != _sha256_bytes(
        _canonical_bytes(admission)
    ):
        raise RuntimePreparationVerificationError(
            "runtime preparation admission identity drifted"
        )
    source = document.get("source")
    host = admission.get("host")
    if (
        not isinstance(source, dict)
        or not isinstance(host, dict)
        or source.get("before") != host
        or source.get("after") != host
        or source.get("identity_sha256") != _identity(host)
    ):
        raise RuntimePreparationVerificationError(
            "runtime preparation source receipt drifted"
        )

    build = document.get("build")
    if not isinstance(build, dict):
        raise RuntimePreparationVerificationError(
            "runtime preparation build identity is unavailable"
        )
    build_identity = build.get("identity_sha256")
    build_body = dict(build)
    build_body.pop("identity_sha256", None)
    args = build_body.get("args")
    timeout = build_body.get("timeout_seconds")
    duration = build_body.get("duration_seconds")
    apk_glob = build_body.get("apk_glob")
    executable = build_body.get("executable")
    host_path = spec.host_project.resolve()
    try:
        current_executable = _resolve_build_executable(
            args[0] if isinstance(args, list) and args else "",
            host_path,
        )
        executable_matches = (
            isinstance(executable, dict)
            and executable.get("path") == str(current_executable)
            and executable.get("sha256") == _sha256_file(current_executable)
        )
    except OSError:
        executable_matches = False
    if (
        not isinstance(build_identity, str)
        or build_identity != _identity(build_body)
        or not isinstance(args, list)
        or any(not isinstance(argument, str) for argument in args)
        or not isinstance(timeout, int)
        or isinstance(timeout, bool)
        or not isinstance(duration, (int, float))
        or isinstance(duration, bool)
        or duration < 0
        or not executable_matches
        or build_body.get("cwd") != str(host_path)
        or build_body.get("returncode") != 0
        or _validate_recipe(
            RuntimeBuildRecipe(
                args=tuple(args),
                timeout_seconds=timeout,
                apk_glob=apk_glob if isinstance(apk_glob, str) else "",
            ),
            spec,
        )
        is not None
    ):
        raise RuntimePreparationVerificationError(
            "runtime preparation build identity drifted"
        )

    apk = document.get("apk")
    if not isinstance(apk, dict):
        raise RuntimePreparationVerificationError(
            "runtime preparation APK identity is unavailable"
        )
    raw_path = apk.get("path")
    if not isinstance(raw_path, str):
        raise RuntimePreparationVerificationError(
            "runtime preparation APK path drifted"
        )
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimePreparationVerificationError(
            "runtime preparation APK path drifted"
        )
    try:
        apk_path = host_path.joinpath(*relative.parts).resolve(strict=True)
        apk_path.relative_to(host_path)
    except (OSError, ValueError) as error:
        raise RuntimePreparationVerificationError(
            "runtime preparation APK path drifted"
        ) from error
    located_apk, locator_error = _locate_apk(host_path, spec.apk_glob)
    if locator_error is not None or located_apk != apk_path:
        raise RuntimePreparationVerificationError(
            "runtime preparation APK set drifted"
        )
    try:
        apk_bytes = apk_path.read_bytes()
    except OSError as error:
        raise RuntimePreparationVerificationError(
            "runtime preparation APK bytes drifted"
        ) from error
    if (
        apk.get("bytes") != len(apk_bytes)
        or apk.get("sha256") != _sha256_bytes(apk_bytes)
    ):
        raise RuntimePreparationVerificationError(
            "runtime preparation APK bytes drifted"
        )
    try:
        metadata = apk_inspector.inspect(apk_path)
    except (
        ApkInspectionError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        raise RuntimePreparationVerificationError(
            "runtime preparation APK inspection failed"
        ) from error
    if not isinstance(metadata, ApkMetadata):
        raise RuntimePreparationVerificationError(
            "runtime preparation APK inspection failed"
        )
    if (
        metadata.package != apk.get("package")
        or metadata.package != spec.package
        or metadata.launcher_activity != apk.get("launcher_activity")
        or metadata.launcher_activity != spec.activity
    ):
        raise RuntimePreparationVerificationError(
            "runtime preparation APK manifest drifted"
        )
    try:
        verify_admitted_receipt(
            admission,
            spec,
            options,
            command_runner=command_runner,
            source_authority=source_authority,
        )
    except (
        OSError,
        ProductionSeamAdmissionError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        raise RuntimePreparationVerificationError(
            "runtime preparation source or runner policy drifted"
        ) from error


__all__ = [
    "AaptApkInspector",
    "ApkInspectionError",
    "ApkInspector",
    "ApkMetadata",
    "CleanCheckoutSourceAuthority",
    "RuntimeBuildRecipe",
    "RuntimePreparationReceipt",
    "RuntimePreparationVerificationError",
    "SealedInjectionSourceAuthority",
    "prepare_runtime_case",
    "verify_runtime_preparation_receipt",
]
