"""Pre-device preparation and admission for the four-lane runtime family.

The one-lane preparation contract lives in :mod:`aiverify.runtime_preparation`.
This module is the deliberately boring family orchestrator around that seam. It
owns only stage receipts, lane disposition, artifact preservation, and the
family-wide gates. It never imports an execution backend and never creates an
``ExecutionRecord`` or a device session.

The public API accepts already materialized lane inputs. Materialization and
mapping disclosure therefore remain the responsibility of the source-authority
boundary; this stage receives opaque lane IDs in the frozen order only.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import shutil
import stat
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from aiverify.bench import runtime_calibration, runtime_mapping
from aiverify.runner.admission import PlannedRunnerOptions, SourceAuthority
from aiverify.runner.run_spec import RunSpec, load_run_spec
from aiverify.runtime_preparation import (
    ApkInspector,
    ApkMetadata,
    CommandRunner,
    MappedRuntimeSourceAuthority,
    MappedSealedInjectionSourceAuthority,
    RuntimeBuildRecipe,
    RuntimeInputVault,
    RuntimePreparationReceipt,
    RuntimePreparationVerificationError,
    RuntimeSigningIdentity,
    prepare_runtime_case,
    sealed_apk_binding_from_receipt,
    verify_runtime_preparation_receipt,
)

SCHEMA_VERSION = 1
RUNTIME_FAMILY_PREPARATION_STAGE = "prepare-family"
RUNTIME_FAMILY_PREPARATION_CLAIM_BOUNDARY = "local_runtime_family_preparation_only"
RUNTIME_FAMILY_PREPARATION_FILENAME = "family-preparation.json"
RUNTIME_FAMILY_PREPARATION_LANE_STATUSES = (
    "prepared",
    "preparation_rejected",
    "not_prepared_due_to_family_abort",
    "prepared_but_family_not_admitted",
)
RUNTIME_FAMILY_PREPARATION_FAILURE_SCOPES = (
    "lane_local",
    "shared",
    "unknown",
)
RUNTIME_FAMILY_PREPARATION_STAGE_STATUSES = (
    "accepted",
    "rejected",
    "abandoned",
    "absent",
    "invalid",
)
_PREPARATION_RUNTIME_EFFECTS = {
    "shell": False,
    "device": False,
    "android_deployment": False,
    "execution_record": False,
    "agent_or_model": False,
}
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class RuntimeFamilyPreparationError(ValueError):
    """Raised when family preparation cannot produce a valid terminal stage."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


class RuntimeFamilyLaneFailure(RuntimeFamilyPreparationError):
    """A lane preparer may use this to classify a terminal lane-local failure."""

    def __init__(
        self,
        code: str,
        *,
        scope: Literal["lane_local", "shared", "unknown"] = "unknown",
        build_started: bool = True,
        build_attempts: int = 1,
    ) -> None:
        if scope not in RUNTIME_FAMILY_PREPARATION_FAILURE_SCOPES:
            raise ValueError("runtime family lane failure scope is invalid")
        if not isinstance(build_attempts, int) or isinstance(build_attempts, bool):
            raise TypeError("runtime family build attempt count is invalid")
        if (
            build_attempts < 0
            or (build_started and build_attempts != 1)
            or (not build_started and build_attempts != 0)
        ):
            raise ValueError("runtime family build-attempt contract is invalid")
        super().__init__(code)
        self.scope = scope
        self.build_started = build_started
        self.build_attempts = build_attempts


@dataclass(frozen=True)
class RuntimeFamilyLaneInput:
    """The exact, source-authorized inputs for one opaque family lane."""

    lane_id: str
    source_authority: SourceAuthority
    build_recipe: RuntimeBuildRecipe
    spec: RunSpec
    options: PlannedRunnerOptions
    apk_inspector: ApkInspector
    build_runner: CommandRunner | None = None
    admission_command_runner: CommandRunner | None = None
    runtime_input_vault: RuntimeInputVault | None = None
    runtime_signing_identity: RuntimeSigningIdentity | None = None
    expected_apk_metadata: ApkMetadata | None = None
    allow_test_substitutes: bool = False

    def __post_init__(self) -> None:
        if self.lane_id not in runtime_mapping.FROZEN_LANE_ORDER:
            raise ValueError("runtime family lane ID is not in frozen order")
        if not isinstance(self.source_authority, SourceAuthority):
            raise TypeError("runtime family source authority is unavailable")
        if not isinstance(self.build_recipe, RuntimeBuildRecipe):
            raise TypeError("runtime family build recipe is unavailable")
        if not isinstance(self.spec, RunSpec):
            raise TypeError("runtime family Run Spec is unavailable")
        if not isinstance(self.options, PlannedRunnerOptions):
            raise TypeError("runtime family runner options are unavailable")
        if not isinstance(self.apk_inspector, ApkInspector):
            raise TypeError("runtime family APK inspector is unavailable")
        for runner in (self.build_runner, self.admission_command_runner):
            if runner is not None and not isinstance(runner, CommandRunner):
                raise TypeError("runtime family command runner is unavailable")
        if self.runtime_input_vault is not None and not isinstance(
            self.runtime_input_vault, RuntimeInputVault
        ):
            raise TypeError("runtime family Runtime Input Vault is invalid")
        if self.runtime_signing_identity is not None and not isinstance(
            self.runtime_signing_identity, RuntimeSigningIdentity
        ):
            raise TypeError("runtime family signing identity is invalid")
        if self.expected_apk_metadata is not None and not isinstance(
            self.expected_apk_metadata, ApkMetadata
        ):
            raise TypeError("runtime family expected APK metadata is invalid")
        if not isinstance(self.allow_test_substitutes, bool):
            raise TypeError("runtime family test substitute policy is invalid")


# These names are useful to integrations that use "preparation input" or
# "lane" rather than the longer contract name.
RuntimeFamilyPreparationInput = RuntimeFamilyLaneInput
RuntimeFamilyLane = RuntimeFamilyLaneInput


@dataclass(frozen=True)
class RuntimeFamilyLaneResult:
    """Optional result wrapper for recording fakes and custom lane preparers."""

    receipt: RuntimePreparationReceipt | Mapping[str, object] | None = None
    artifacts: tuple[Path, ...] = ()
    build_started: bool = True
    build_attempts: int = 1
    failure_scope: Literal["lane_local", "shared", "unknown"] | None = None
    rejection_code: str | None = None
    private_environment_root: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.artifacts, tuple) or any(
            not isinstance(path, Path) for path in self.artifacts
        ):
            raise TypeError("runtime family result artifacts are invalid")
        if not isinstance(self.build_started, bool):
            raise TypeError("runtime family build-started flag is invalid")
        if not isinstance(self.build_attempts, int) or isinstance(
            self.build_attempts, bool
        ):
            raise TypeError("runtime family build-attempt count is invalid")
        if self.build_attempts < 0:
            raise ValueError("runtime family build-attempt count is invalid")
        if not self.build_started and self.build_attempts != 0:
            raise ValueError("runtime family build-attempt contract is invalid")
        if self.failure_scope is not None and self.failure_scope not in (
            "lane_local",
            "shared",
            "unknown",
        ):
            raise ValueError("runtime family failure scope is invalid")
        if self.private_environment_root is not None and not isinstance(
            self.private_environment_root, Path
        ):
            raise ValueError("runtime family private environment path is invalid")


@dataclass(frozen=True)
class RuntimeFamilyPreparationRow:
    """One immutable disposition row emitted by family preparation."""

    lane_id: str
    status: str
    source_worktree: Path
    artifact_root: Path
    build_started: bool
    build_attempts: int
    artifacts: tuple[Mapping[str, object], ...] = ()
    preparation_receipt: Mapping[str, object] | None = None
    preparation_receipt_sha256: str | None = None
    rejection_code: str | None = None
    failure_scope: str | None = None
    private_environment_root: Path | None = None

    def __post_init__(self) -> None:
        if self.lane_id not in runtime_mapping.FROZEN_LANE_ORDER:
            raise ValueError("runtime family row lane ID is not in frozen order")
        if self.status not in RUNTIME_FAMILY_PREPARATION_LANE_STATUSES:
            raise ValueError("runtime family row status is invalid")
        if not isinstance(self.source_worktree, Path) or not isinstance(
            self.artifact_root, Path
        ):
            raise TypeError("runtime family row path is invalid")
        for path in (self.source_worktree, self.artifact_root):
            if not path.is_absolute() or path.resolve() != path:
                raise ValueError("runtime family row path must be canonical")
        if not isinstance(self.build_started, bool):
            raise TypeError("runtime family row build-started flag is invalid")
        if not isinstance(self.build_attempts, int) or isinstance(
            self.build_attempts, bool
        ):
            raise TypeError("runtime family row build-attempt count is invalid")
        if self.build_attempts < 0 or (
            not self.build_started and self.build_attempts != 0
        ):
            raise ValueError("runtime family row build-attempt contract is invalid")
        if self.failure_scope is not None and self.failure_scope not in (
            "lane_local",
            "shared",
            "unknown",
        ):
            raise ValueError("runtime family row failure scope is invalid")
        if (
            self.preparation_receipt is None
            and self.preparation_receipt_sha256 is not None
        ):
            raise ValueError("runtime family row receipt digest is unavailable")
        if (
            self.preparation_receipt is not None
            and self.preparation_receipt_sha256
            != _canonical_sha256(self.preparation_receipt)
        ):
            raise ValueError("runtime family row receipt digest drifted")
        if self.status in {"prepared", "prepared_but_family_not_admitted"} and (
            self.preparation_receipt is None
            or self.preparation_receipt.get("prepared") is not True
        ):
            raise ValueError("runtime family prepared row receipt is unavailable")
        if self.status == "not_prepared_due_to_family_abort" and (
            self.preparation_receipt is not None
            or self.build_started
            or self.build_attempts != 0
        ):
            raise ValueError("runtime family abort row contains a fabricated attempt")
        if self.private_environment_root is not None and not isinstance(
            self.private_environment_root, Path
        ):
            raise ValueError("runtime family row private environment path is invalid")
        if self.private_environment_root is not None and (
            not self.private_environment_root.is_absolute()
            or self.private_environment_root.resolve() != self.private_environment_root
        ):
            raise ValueError(
                "runtime family row private environment path is not canonical"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "lane_id": self.lane_id,
            "status": self.status,
            "source_worktree": str(self.source_worktree),
            "artifact_root": str(self.artifact_root),
            "build_started": self.build_started,
            "build_attempts": self.build_attempts,
            "artifacts": [dict(item) for item in self.artifacts],
            "preparation_receipt": (
                dict(self.preparation_receipt)
                if self.preparation_receipt is not None
                else None
            ),
            "preparation_receipt_sha256": self.preparation_receipt_sha256,
            "rejection_code": self.rejection_code,
            "failure_scope": self.failure_scope,
            "private_environment_root": (
                str(self.private_environment_root)
                if self.private_environment_root is not None
                else None
            ),
        }


@dataclass(frozen=True)
class RuntimeFamilyPreparationReceipt:
    """Checksum-bound terminal receipt for ``prepare-family``."""

    accepted: bool
    candidate_root: Path
    predecessor_root: Path
    output_root: Path
    mapping_release_id: str
    mapping_release_identity_sha256: str
    mapping_release_sha256: str
    candidate_identity_sha256: str
    candidate_manifest_sha256: str
    candidate_artifact_inventory_sha256: str
    rows: tuple[RuntimeFamilyPreparationRow, ...]
    gates: Mapping[str, Mapping[str, object]]
    reason: str | None
    start_receipt_sha256: str
    terminal_identity_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise TypeError("runtime family accepted flag is invalid")
        if not isinstance(self.rows, tuple) or any(
            not isinstance(row, RuntimeFamilyPreparationRow) for row in self.rows
        ):
            raise TypeError("runtime family terminal rows are invalid")
        if not isinstance(self.gates, Mapping):
            raise TypeError("runtime family gates are invalid")
        for path in (self.candidate_root, self.predecessor_root, self.output_root):
            if not isinstance(path, Path):
                raise TypeError("runtime family terminal path is invalid")
        if self.status not in {"accepted", "rejected"}:
            raise ValueError("runtime family terminal status is invalid")
        if self.accepted != (self.status == "accepted"):
            raise ValueError("runtime family terminal status contradicts accepted flag")
        if self.lane_ids != runtime_mapping.FROZEN_LANE_ORDER:
            raise ValueError("runtime family terminal lane order is invalid")
        if len(self.rows) != 4:
            raise ValueError("runtime family terminal row cardinality is invalid")
        for path in (self.candidate_root, self.predecessor_root, self.output_root):
            if not path.is_absolute() or path.resolve() != path:
                raise ValueError("runtime family terminal path must be canonical")
        if not isinstance(self.mapping_release_id, str) or not self.mapping_release_id:
            raise ValueError("runtime family mapping release ID is invalid")
        if any(not isinstance(value, Mapping) for value in self.gates.values()):
            raise ValueError("runtime family gates are invalid")
        if self.reason is not None and not isinstance(self.reason, str):
            raise TypeError("runtime family terminal reason is invalid")
        for value in (
            self.mapping_release_identity_sha256,
            self.mapping_release_sha256,
            self.candidate_identity_sha256,
            self.candidate_manifest_sha256,
            self.candidate_artifact_inventory_sha256,
            self.start_receipt_sha256,
        ):
            if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
                raise ValueError("runtime family terminal digest is invalid")
        if self.terminal_identity_sha256 is not None and (
            not isinstance(self.terminal_identity_sha256, str)
            or _HEX_64.fullmatch(self.terminal_identity_sha256) is None
        ):
            raise ValueError("runtime family terminal identity is invalid")

    @property
    def status(self) -> str:
        return "accepted" if self.accepted else "rejected"

    @property
    def identity_sha256(self) -> str:
        body = self.to_dict(include_identity=False)
        body.pop("terminal_identity_sha256", None)
        return _canonical_sha256(body)

    @property
    def lane_ids(self) -> tuple[str, ...]:
        return tuple(row.lane_id for row in self.rows)

    def to_dict(self, *, include_identity: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "stage": RUNTIME_FAMILY_PREPARATION_STAGE,
            "status": self.status,
            "accepted": self.accepted,
            "claim_boundary": RUNTIME_FAMILY_PREPARATION_CLAIM_BOUNDARY,
            "candidate_root": str(self.candidate_root),
            "predecessor_root": str(self.predecessor_root),
            "output_root": str(self.output_root),
            "mapping_release_id": self.mapping_release_id,
            "mapping_release_identity_sha256": self.mapping_release_identity_sha256,
            "mapping_release_sha256": self.mapping_release_sha256,
            "candidate_identity_sha256": self.candidate_identity_sha256,
            "candidate_manifest_sha256": self.candidate_manifest_sha256,
            "candidate_artifact_inventory_sha256": self.candidate_artifact_inventory_sha256,
            "lane_ids": list(self.lane_ids),
            "rows": [row.to_dict() for row in self.rows],
            "gates": {name: dict(value) for name, value in self.gates.items()},
            "reason": self.reason,
            "start_receipt_sha256": self.start_receipt_sha256,
            "terminal_identity_sha256": self.terminal_identity_sha256,
        }
        if include_identity:
            result["identity_sha256"] = self.identity_sha256
        return result


RuntimeFamilyPreparationStageReceipt = RuntimeFamilyPreparationReceipt


RuntimeFamilyLanePreparer = Callable[
    [RuntimeFamilyLaneInput],
    RuntimePreparationReceipt | RuntimeFamilyLaneResult | Mapping[str, object],
]
RuntimeFamilyHealthCheck = Callable[..., bool]


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: object) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_path(value: str | Path) -> Path:
    raw = Path(value).expanduser()
    return raw.resolve()


def _is_overlapping(first: Path, second: Path) -> bool:
    return (
        first == second or first.is_relative_to(second) or second.is_relative_to(first)
    )


def _prepare_output_root(output_root: str | Path) -> Path:
    raw = Path(output_root).expanduser()
    if raw.is_symlink():
        raise RuntimeFamilyPreparationError("family_output_root_symlink")
    root = raw.resolve()
    if root.exists():
        if not root.is_dir() or any(root.iterdir()):
            raise RuntimeFamilyPreparationError("family_output_root_not_empty")
    else:
        try:
            root.mkdir(parents=True, exist_ok=False)
        except OSError as error:
            raise RuntimeFamilyPreparationError(
                "family_output_root_unavailable"
            ) from error
    return root


def _write_json_exclusive(path: Path, document: Mapping[str, object]) -> str:
    if path.exists() or path.is_symlink():
        raise RuntimeFamilyPreparationError("family_stage_receipt_already_exists")
    payload = _canonical_bytes(document)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except FileExistsError as error:
        raise RuntimeFamilyPreparationError(
            "family_stage_receipt_already_exists"
        ) from error
    except OSError as error:
        raise RuntimeFamilyPreparationError(
            "family_stage_receipt_write_failed"
        ) from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError as error:
            raise RuntimeFamilyPreparationError(
                "family_stage_receipt_cleanup_failed"
            ) from error
    return _sha256_bytes(payload)


def _stage_identity(document: Mapping[str, object], field: str) -> str:
    value = dict(document)
    value.pop(field, None)
    # Stage receipts use the repository-wide compact canonical identity. The
    # embedded one-lane preparation receipt retains its own pretty-JSON
    # checksum contract and is deliberately handled separately.
    return runtime_calibration.canonical_sha256(value)


def _read_json(path: Path, code: str) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeFamilyPreparationError(code)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeFamilyPreparationError(code) from error
    if not isinstance(value, dict):
        raise RuntimeFamilyPreparationError(code)
    return value


def _load_mapping_predecessor(
    predecessor_root: str | Path,
    *,
    candidate: runtime_calibration.CandidateInputs,
) -> tuple[runtime_mapping.RuntimeMappingRelease, Path, str, str]:
    root = _canonical_path(predecessor_root)
    if runtime_mapping.stage_status(root) != "accepted":
        raise RuntimeFamilyPreparationError("mapping_predecessor_not_accepted")
    terminal_path = root / "stage-terminal.json"
    terminal = _read_json(terminal_path, "mapping_predecessor_not_accepted")
    if (
        terminal.get("stage") != "admit-family"
        or terminal.get("status") != "accepted"
        or terminal.get("candidate_root") != str(candidate.root)
    ):
        raise RuntimeFamilyPreparationError("mapping_predecessor_input_mismatch")
    release_path = root / runtime_mapping.RUNTIME_MAPPING_RELEASE_FILENAME
    try:
        release = runtime_mapping.load_runtime_mapping_release(release_path)
        runtime_mapping.verify_runtime_mapping_release(
            release,
            candidate_root=candidate.root,
        )
        release_bytes = release_path.read_bytes()
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        runtime_mapping.RuntimeMappingError,
    ) as error:
        raise RuntimeFamilyPreparationError("mapping_predecessor_invalid") from error
    expected_candidate = (
        candidate.candidate_identity_sha256,
        candidate.manifest_sha256,
        candidate.artifact_inventory_sha256,
    )
    if (
        terminal.get("candidate_identity_sha256"),
        terminal.get("manifest_sha256"),
        terminal.get("artifact_inventory_sha256"),
    ) != expected_candidate:
        raise RuntimeFamilyPreparationError("mapping_predecessor_input_mismatch")
    if terminal.get(
        "mapping_release_identity_sha256"
    ) != release.identity_sha256 or terminal.get(
        "mapping_release_sha256"
    ) != _sha256_bytes(release_bytes):
        raise RuntimeFamilyPreparationError("mapping_predecessor_identity_mismatch")
    terminal_bytes = terminal_path.read_bytes()
    terminal_identity = terminal.get("terminal_identity_sha256")
    if not isinstance(terminal_identity, str) or not _HEX_64.fullmatch(
        terminal_identity
    ):
        raise RuntimeFamilyPreparationError("mapping_predecessor_identity_mismatch")
    if terminal_identity != _stage_identity(terminal, "terminal_identity_sha256"):
        raise RuntimeFamilyPreparationError("mapping_predecessor_identity_mismatch")
    return release, root, _sha256_bytes(terminal_bytes), _sha256_bytes(release_bytes)


def _candidate_recipe(
    candidate: runtime_calibration.CandidateInputs,
    lane_id: str,
) -> RuntimeBuildRecipe:
    lane_number = runtime_mapping.FROZEN_LANE_ORDER.index(lane_id) + 1
    path = (
        candidate.root / "runtime" / "lanes" / f"lane-{lane_number:02d}" / "recipe.json"
    )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return RuntimeBuildRecipe.from_dict(value)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as error:
        raise RuntimeFamilyPreparationError("candidate_recipe_unavailable") from error


def _candidate_spec_path(
    candidate: runtime_calibration.CandidateInputs, lane_id: str
) -> Path:
    lane_number = runtime_mapping.FROZEN_LANE_ORDER.index(lane_id) + 1
    return (
        candidate.root
        / "runtime"
        / "lanes"
        / f"lane-{lane_number:02d}"
        / "run-spec.yaml"
    )


def _effective_signer(lane: RuntimeFamilyLaneInput) -> RuntimeSigningIdentity | None:
    if lane.runtime_signing_identity is not None:
        return lane.runtime_signing_identity
    if lane.runtime_input_vault is not None:
        return lane.runtime_input_vault.manifest.signing_identity
    return None


def _verify_vault(lane: RuntimeFamilyLaneInput) -> None:
    vault = lane.runtime_input_vault
    signer = _effective_signer(lane)
    if not isinstance(vault, RuntimeInputVault):
        raise RuntimeFamilyPreparationError("runtime_input_vault_unavailable")
    if vault.manifest_path is None:
        raise RuntimeFamilyPreparationError("runtime_input_vault_manifest_unavailable")
    try:
        manifest_bytes = vault.manifest_path.read_bytes()
        if manifest_bytes != vault.manifest.canonical_bytes:
            raise ValueError("manifest bytes drifted")
        vault.verify()
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise RuntimeFamilyPreparationError("runtime_input_vault_rejected") from error
    if not isinstance(signer, RuntimeSigningIdentity):
        raise RuntimeFamilyPreparationError("runtime_signing_identity_unavailable")
    if signer.to_dict() != vault.manifest.signing_identity.to_dict():
        raise RuntimeFamilyPreparationError("runtime_signing_identity_mismatch")


def _validate_lane_inputs(
    lane_inputs: Mapping[str, RuntimeFamilyLaneInput]
    | Sequence[RuntimeFamilyLaneInput],
    *,
    candidate: runtime_calibration.CandidateInputs,
    release: runtime_mapping.RuntimeMappingRelease,
    output_root: Path,
) -> tuple[RuntimeFamilyLaneInput, ...]:
    if isinstance(lane_inputs, Mapping):
        if tuple(lane_inputs) != runtime_mapping.FROZEN_LANE_ORDER:
            raise RuntimeFamilyPreparationError("family_lane_order_mismatch")
        ordered = tuple(
            lane_inputs[lane_id] for lane_id in runtime_mapping.FROZEN_LANE_ORDER
        )
    else:
        ordered = tuple(lane_inputs)
        if any(not isinstance(item, RuntimeFamilyLaneInput) for item in ordered):
            raise RuntimeFamilyPreparationError("family_lane_inputs_invalid")
        if tuple(item.lane_id for item in ordered) != runtime_mapping.FROZEN_LANE_ORDER:
            raise RuntimeFamilyPreparationError("family_lane_order_mismatch")
    if len(ordered) != 4 or any(
        not isinstance(item, RuntimeFamilyLaneInput) for item in ordered
    ):
        raise RuntimeFamilyPreparationError("family_lane_inputs_invalid")
    if (
        tuple(lane.lane_id for lane in release.lanes)
        != runtime_mapping.FROZEN_LANE_ORDER
    ):
        raise RuntimeFamilyPreparationError("mapping_lane_order_mismatch")

    worktrees: list[Path] = []
    for lane, mapped_lane in zip(ordered, release.lanes):
        if lane.lane_id != mapped_lane.lane_id:
            raise RuntimeFamilyPreparationError("family_lane_order_mismatch")
        source_path = lane.spec.source_path
        expected_spec_path = _candidate_spec_path(candidate, lane.lane_id).resolve()
        if (
            source_path is None
            or source_path.is_symlink()
            or source_path.resolve() != expected_spec_path
        ):
            raise RuntimeFamilyPreparationError("family_run_spec_identity_mismatch")
        if lane.spec.source_sha256 != mapped_lane.run_spec_raw_sha256:
            raise RuntimeFamilyPreparationError("family_run_spec_identity_mismatch")
        if lane.spec.host_project.resolve() != lane.options.workdir.resolve():
            raise RuntimeFamilyPreparationError("family_worktree_identity_mismatch")
        raw_worktree = lane.options.workdir.expanduser()
        worktree = raw_worktree.resolve()
        if raw_worktree.is_symlink() or not worktree.is_dir():
            raise RuntimeFamilyPreparationError("family_worktree_unavailable")
        if any(_is_overlapping(worktree, other) for other in worktrees):
            raise RuntimeFamilyPreparationError("family_worktree_not_independent")
        if _is_overlapping(worktree, candidate.root) or _is_overlapping(
            worktree, output_root
        ):
            raise RuntimeFamilyPreparationError("family_worktree_location_invalid")
        for relative in (
            Path("app/build/outputs/apk/debug/app-debug.apk"),
            Path("build/app-debug.apk"),
        ):
            existing = worktree / relative
            if existing.exists() or existing.is_symlink():
                raise RuntimeFamilyPreparationError("family_worktree_not_fresh")
        worktrees.append(worktree)

        expected_recipe = _candidate_recipe(candidate, lane.lane_id)
        actual_recipe = lane.build_recipe.to_dict()
        candidate_recipe = expected_recipe.to_dict()
        for key in (
            "command",
            "timeout_seconds",
            "output_relative_path",
            "environment_policy",
        ):
            if actual_recipe.get(key) != candidate_recipe.get(key):
                raise RuntimeFamilyPreparationError("family_recipe_identity_mismatch")
        if (
            lane.build_recipe.output_relative_path
            != expected_recipe.output_relative_path
        ):
            raise RuntimeFamilyPreparationError("family_recipe_identity_mismatch")
        if lane.spec.apk_glob != expected_recipe.apk_glob:
            raise RuntimeFamilyPreparationError("family_run_spec_output_mismatch")
        try:
            expected_loaded_spec = load_run_spec(expected_spec_path)
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            raise RuntimeFamilyPreparationError(
                "candidate_run_spec_unavailable"
            ) from error
        if (
            lane.spec.apk_glob != expected_loaded_spec.apk_glob
            or lane.spec.package != expected_loaded_spec.package
            or lane.spec.activity != expected_loaded_spec.activity
            or lane.spec.scenario.id != expected_loaded_spec.scenario.id
            or lane.spec
            != replace(
                expected_loaded_spec,
                host_project=lane.spec.host_project,
            )
        ):
            raise RuntimeFamilyPreparationError("family_run_spec_identity_mismatch")
        if lane.spec.package != "com.darkempire78.opencalculator.debug":
            raise RuntimeFamilyPreparationError("family_package_identity_mismatch")

        _verify_vault(lane)
        assert lane.runtime_input_vault is not None
        signer = _effective_signer(lane)
        assert signer is not None
        if (
            lane.runtime_input_vault.manifest.family_id != release.family_id
            or lane.runtime_input_vault.manifest.family_version
            != release.family_version
        ):
            raise RuntimeFamilyPreparationError("runtime_input_vault_family_mismatch")
        if not lane.allow_test_substitutes and (
            mapped_lane.source_request.worktree_path != str(worktree)
        ):
            raise RuntimeFamilyPreparationError("family_worktree_mapping_mismatch")

        verifier = getattr(lane.source_authority, "verify_runtime_source_request", None)
        if callable(verifier):
            try:
                verifier(mapped_lane.source_request)
            except Exception as error:
                raise RuntimeFamilyPreparationError(
                    "family_source_input_rejected"
                ) from error
        verify_inputs = getattr(lane.source_authority, "verify_runtime_inputs", None)
        if callable(verify_inputs):
            try:
                verify_inputs(lane.build_recipe, lane.spec)
            except Exception as error:
                raise RuntimeFamilyPreparationError(
                    "family_source_input_rejected"
                ) from error
        if not lane.allow_test_substitutes and type(lane.source_authority) not in {
            MappedRuntimeSourceAuthority,
            MappedSealedInjectionSourceAuthority,
        }:
            raise RuntimeFamilyPreparationError(
                "family_mapped_source_authority_required"
            )
        binding = getattr(lane.source_authority, "mapping_binding", None)
        if isinstance(binding, Mapping) and (
            binding.get("release_id") != release.release_id
            or binding.get("release_identity_sha256") != release.identity_sha256
            or binding.get("lane_id") != lane.lane_id
        ):
            raise RuntimeFamilyPreparationError("family_mapping_binding_mismatch")

    return ordered


def _staged_lane_input(
    lane: RuntimeFamilyLaneInput, output_root: Path, index: int
) -> RuntimeFamilyLaneInput:
    lane_root = output_root / "lanes" / f"lane-{index:02d}"
    artifact_root = lane_root / "artifacts"
    return replace(lane, options=replace(lane.options, artifact_dir=artifact_root))


def _receipt_document(
    receipt: RuntimePreparationReceipt | Mapping[str, object],
) -> dict[str, object]:
    if isinstance(receipt, RuntimePreparationReceipt):
        try:
            document = receipt.receipt
            if (
                _canonical_bytes(document) != receipt.receipt_bytes
                or _sha256_bytes(receipt.receipt_bytes) != receipt.receipt_sha256
            ):
                raise RuntimeFamilyPreparationError("preparation_receipt_bytes_drifted")
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            if isinstance(error, RuntimeFamilyPreparationError):
                raise
            raise RuntimeFamilyPreparationError(
                "preparation_receipt_unavailable"
            ) from error
        return document
    if isinstance(receipt, Mapping):
        return dict(receipt)
    raise RuntimeFamilyPreparationError("preparation_receipt_unavailable")


def _receipt_digest(document: Mapping[str, object]) -> str:
    return _canonical_sha256(document)


def _verify_receipt_identity(document: Mapping[str, object]) -> None:
    identity = document.get("receipt_identity_sha256")
    body = dict(document)
    body.pop("receipt_identity_sha256", None)
    if not isinstance(identity, str) or identity != _canonical_sha256(body):
        raise RuntimeFamilyPreparationError("preparation_receipt_identity_mismatch")


def _descriptor(
    path: Path, *, root: Path, kind: str, preserved: bool
) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeFamilyPreparationError("preparation_artifact_unavailable")
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise RuntimeFamilyPreparationError(
            "preparation_artifact_outside_output"
        ) from error
    details = path.stat()
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise RuntimeFamilyPreparationError("preparation_artifact_not_immutable")
    if details.st_mode & 0o222:
        raise RuntimeFamilyPreparationError("preparation_artifact_not_immutable")
    return {
        "kind": kind,
        "path": str(resolved),
        "bytes": details.st_size,
        "sha256": _file_sha256(path),
        "mode": f"{stat.S_IMODE(details.st_mode):04o}",
        "regular": True,
        "symlink": False,
        "hard_links": details.st_nlink,
        "preserved": preserved,
    }


def _copy_preserved_artifact(source: Path, destination: Path) -> Path | None:
    if source.is_symlink() or not source.is_file():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        return None
    try:
        shutil.copyfile(source, destination)
        destination.chmod(0o444)
        with destination.open("rb") as stream:
            os.fsync(stream.fileno())
    except OSError as error:
        destination.unlink(missing_ok=True)
        raise RuntimeFamilyPreparationError(
            "preparation_artifact_preservation_failed"
        ) from error
    return destination


def _receipt_artifact_paths(
    document: Mapping[str, object], lane: RuntimeFamilyLaneInput
) -> list[Path]:
    paths: list[Path] = []
    sealed = document.get("sealed_apk")
    if isinstance(sealed, Mapping) and isinstance(sealed.get("path"), str):
        paths.append(Path(sealed["path"]))
    apk = document.get("apk")
    if isinstance(apk, Mapping):
        built = apk.get("built_path")
        if isinstance(built, str):
            candidate = Path(built)
            paths.append(
                candidate
                if candidate.is_absolute()
                else lane.options.workdir / candidate
            )
        path = apk.get("path")
        if isinstance(path, str):
            candidate = Path(path)
            paths.append(
                candidate
                if candidate.is_absolute()
                else lane.options.workdir / candidate
            )
    return paths


def _preserve_artifacts(
    lane: RuntimeFamilyLaneInput,
    lane_result: RuntimeFamilyLaneResult,
    document: Mapping[str, object] | None,
    *,
    lane_root: Path,
    output_root: Path,
) -> tuple[Mapping[str, object], ...]:
    if document is None and not lane_result.artifacts:
        return ()
    candidates = list(lane_result.artifacts)
    if document is not None:
        candidates.extend(_receipt_artifact_paths(document, lane))
    descriptors: list[Mapping[str, object]] = []
    observed: set[Path] = set()
    for index, source in enumerate(candidates, start=1):
        try:
            resolved = source.resolve()
        except OSError:
            continue
        if resolved in observed:
            continue
        observed.add(resolved)
        if not resolved.is_file() or resolved.is_symlink():
            continue
        try:
            resolved.relative_to(output_root)
        except ValueError:
            destination = (
                lane_root / "preserved" / f"artifact-{index:02d}-{resolved.name}"
            )
            copied = _copy_preserved_artifact(resolved, destination)
            if copied is None:
                continue
            resolved = copied
            descriptors.append(
                _descriptor(
                    resolved,
                    root=output_root,
                    kind="preserved_artifact",
                    preserved=True,
                )
            )
        else:
            descriptors.append(
                _descriptor(
                    resolved, root=output_root, kind="observed_artifact", preserved=True
                )
            )
    return tuple(descriptors)


def _validate_prepared_receipt(
    receipt: RuntimePreparationReceipt | Mapping[str, object],
    lane: RuntimeFamilyLaneInput,
    *,
    output_root: Path,
    allow_test_substitutes: bool,
) -> tuple[dict[str, object], dict[str, object]]:
    document = _receipt_document(receipt)
    _verify_receipt_identity(document)
    if (
        document.get("schema_version") != 1
        or document.get("status") != "prepared"
        or document.get("prepared") is not True
        or document.get("rejection_code") is not None
        or document.get("claim_boundary") != "local_source_build_preparation_only"
    ):
        raise RuntimeFamilyPreparationError("preparation_receipt_not_prepared")
    sealed = document.get("sealed_apk")
    if not isinstance(sealed, Mapping):
        raise RuntimeFamilyPreparationError("sealed_apk_handoff_missing")
    try:
        sealed_binding = sealed_apk_binding_from_receipt(receipt)
    except (
        RuntimePreparationVerificationError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        raise RuntimeFamilyPreparationError("sealed_apk_handoff_invalid") from error
    if sealed_binding is None:
        raise RuntimeFamilyPreparationError("sealed_apk_handoff_missing")
    sealed_path, sealed_size, sealed_digest = sealed_binding
    expected_path = (lane.options.artifact_dir / "build" / "app-debug.apk").resolve()
    if (
        sealed_path != expected_path
        or not sealed_path.is_file()
        or sealed_path.is_symlink()
    ):
        raise RuntimeFamilyPreparationError("sealed_apk_handoff_path_mismatch")
    details = sealed_path.stat()
    if (
        details.st_size != sealed_size
        or _file_sha256(sealed_path) != sealed_digest
        or details.st_nlink != 1
        or details.st_mode & 0o222
        or not stat.S_ISREG(details.st_mode)
    ):
        raise RuntimeFamilyPreparationError("sealed_apk_handoff_drifted")
    try:
        sealed_path.relative_to(output_root)
    except ValueError as error:
        raise RuntimeFamilyPreparationError(
            "sealed_apk_handoff_outside_output"
        ) from error

    if document.get("runtime_effects") != _PREPARATION_RUNTIME_EFFECTS:
        raise RuntimeFamilyPreparationError("preparation_runtime_effects_present")
    build = document.get("build")
    if not isinstance(build, Mapping):
        raise RuntimeFamilyPreparationError("preparation_build_identity_missing")
    if build.get("retry") is not False:
        raise RuntimeFamilyPreparationError("preparation_build_retry_forbidden")
    if build.get("args") != list(lane.build_recipe.args):
        raise RuntimeFamilyPreparationError("preparation_build_recipe_mismatch")
    build_identity = build.get("identity_sha256")
    build_body = dict(build)
    build_body.pop("identity_sha256", None)
    if build_identity != _canonical_sha256(build_body):
        raise RuntimeFamilyPreparationError("preparation_build_identity_mismatch")
    signing = build.get("runtime_signing_identity")
    signer = _effective_signer(lane)
    if not isinstance(signing, Mapping) or not isinstance(
        signer, RuntimeSigningIdentity
    ):
        raise RuntimeFamilyPreparationError("preparation_signing_identity_missing")
    if dict(signing) != signer.to_dict():
        raise RuntimeFamilyPreparationError("preparation_signing_identity_mismatch")
    private_root = build.get("private_input_root")
    if not allow_test_substitutes and (
        not isinstance(private_root, str) or not private_root
    ):
        raise RuntimeFamilyPreparationError("preparation_private_environment_missing")

    apk = document.get("apk")
    if not isinstance(apk, Mapping):
        raise RuntimeFamilyPreparationError("preparation_apk_metadata_missing")
    for field_name in (
        "package",
        "launcher_activity",
        "version_code",
        "version_name",
        "min_sdk",
        "target_sdk",
        "compile_sdk",
        "debuggable",
        "signer_sha256",
        "signer_count",
        "v1_verified",
        "v2_verified",
    ):
        if field_name not in apk:
            raise RuntimeFamilyPreparationError("preparation_apk_metadata_incomplete")
    if (
        apk.get("package") != lane.spec.package
        or apk.get("launcher_activity") != lane.spec.activity
    ):
        raise RuntimeFamilyPreparationError("preparation_apk_metadata_mismatch")
    if (
        apk.get("path") != str(sealed_path)
        or apk.get("bytes") != sealed_size
        or apk.get("sha256") != sealed_digest
    ):
        raise RuntimeFamilyPreparationError("preparation_apk_handoff_mismatch")
    source = document.get("source")
    if not isinstance(source, Mapping):
        raise RuntimeFamilyPreparationError("preparation_source_identity_missing")
    source_identity = source.get("identity_sha256")
    source_body = dict(source)
    source_body.pop("identity_sha256", None)
    if source_identity != _canonical_sha256(source_body):
        raise RuntimeFamilyPreparationError("preparation_source_identity_mismatch")
    before = source.get("before")
    after = source.get("after")
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        raise RuntimeFamilyPreparationError("preparation_source_identity_incomplete")
    if dict(before) != dict(after):
        raise RuntimeFamilyPreparationError("preparation_source_drifted")
    mapping_binding = source.get("mapping_binding")
    authority_binding = getattr(lane.source_authority, "mapping_binding", None)
    if isinstance(authority_binding, Mapping) and (
        not isinstance(mapping_binding, Mapping)
        or dict(mapping_binding) != dict(authority_binding)
    ):
        raise RuntimeFamilyPreparationError("preparation_mapping_handoff_mismatch")
    if not isinstance(mapping_binding, Mapping) and not allow_test_substitutes:
        raise RuntimeFamilyPreparationError("preparation_mapping_handoff_missing")

    if not allow_test_substitutes:
        try:
            verify_runtime_preparation_receipt(
                receipt,
                spec=lane.spec,
                options=lane.options,
                source_authority=lane.source_authority,
                apk_inspector=lane.apk_inspector,
                command_runner=lane.admission_command_runner,
                runtime_input_vault=lane.runtime_input_vault,
                runtime_signing_identity=signer,
                expected_apk_metadata=lane.expected_apk_metadata,
            )
        except (
            RuntimePreparationVerificationError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            raise RuntimeFamilyPreparationError(
                "preparation_receipt_reverification_failed"
            ) from error
    return document, {
        "sealed_path": str(sealed_path),
        "sealed_bytes": sealed_size,
        "sealed_sha256": sealed_digest,
        "private_environment_root": private_root,
    }


def _default_failure_scope(
    code: str | None,
) -> Literal["lane_local", "shared", "unknown"]:
    if not code:
        return "unknown"
    shared_markers = (
        "vault",
        "signing_identity",
        "tool",
        "environment",
        "recipe",
        "source",
        "mapping",
        "candidate",
        "ambient",
        "runner",
        "authority",
        "inspector",
        "worktree",
    )
    local_markers = (
        "build_failed",
        "build_timeout",
        "apk_missing",
        "apk_extra",
        "apk_inspection",
        "apk_metadata",
        "apk_package",
        "apk_signer",
        "sealed_apk",
        "sealed_",
        "build_output",
    )
    if any(marker in code for marker in shared_markers):
        return "shared"
    if any(marker in code for marker in local_markers):
        return "lane_local"
    return "unknown"


def _normalize_lane_result(
    result: RuntimePreparationReceipt | RuntimeFamilyLaneResult | Mapping[str, object],
) -> RuntimeFamilyLaneResult:
    if isinstance(result, RuntimeFamilyLaneResult):
        return result
    if isinstance(result, RuntimePreparationReceipt):
        return RuntimeFamilyLaneResult(
            receipt=result,
            build_started=True,
            build_attempts=1,
            failure_scope=(
                None
                if result.prepared
                else _default_failure_scope(result.rejection_code)
            ),
            rejection_code=result.rejection_code,
        )
    if isinstance(result, Mapping):
        document = dict(result)
        raw_rejection = document.get("rejection_code")
        rejection_code = raw_rejection if isinstance(raw_rejection, str) else None
        raw_scope = (
            None
            if document.get("prepared") is True
            else _default_failure_scope(rejection_code)
        )
        return RuntimeFamilyLaneResult(
            receipt=document,
            build_started=True,
            build_attempts=1,
            failure_scope=raw_scope,
            rejection_code=rejection_code,
        )
    raise RuntimeFamilyPreparationError("family_lane_result_invalid")


def _invoke_health_check(
    callback: RuntimeFamilyHealthCheck,
    row: RuntimeFamilyPreparationRow,
    lane: RuntimeFamilyLaneInput,
) -> bool:
    try:
        signature = inspect.signature(callback)
        parameters = tuple(signature.parameters.values())
        positional = tuple(
            parameter
            for parameter in parameters
            if parameter.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        )
        variadic = any(
            parameter.kind == inspect.Parameter.VAR_POSITIONAL
            for parameter in parameters
        )
        if variadic or len(positional) >= 2:
            value = callback(row, lane)
        elif len(positional) == 1:
            value = callback(row)
        else:
            value = callback()
    except (TypeError, ValueError) as error:
        raise RuntimeFamilyPreparationError(
            "family_shared_health_check_failed"
        ) from error
    if not isinstance(value, bool):
        raise RuntimeFamilyPreparationError("family_shared_health_check_failed")
    return value


def _default_health_check(
    lane_inputs: tuple[RuntimeFamilyLaneInput, ...],
    *,
    candidate_root: Path,
    predecessor_root: Path,
) -> bool:
    try:
        candidate = runtime_calibration.verify_candidate_inputs(candidate_root)
        release, _, _, _ = _load_mapping_predecessor(
            predecessor_root,
            candidate=candidate,
        )
        vault_identities: set[str] = set()
        signer_identities: set[str] = set()
        for lane, mapped_lane in zip(lane_inputs, release.lanes):
            if lane.lane_id != mapped_lane.lane_id:
                return False
            _verify_vault(lane)
            assert lane.runtime_input_vault is not None
            signer = _effective_signer(lane)
            if signer is None:
                return False
            vault_identities.add(lane.runtime_input_vault.manifest.identity_sha256)
            signer_identities.add(_canonical_sha256(signer.to_dict()))
            for tool in lane.build_recipe.tool_identities:
                tool.verify()
            verifier = getattr(
                lane.source_authority, "verify_runtime_source_request", None
            )
            if callable(verifier):
                verifier(mapped_lane.source_request)
            verify_inputs = getattr(
                lane.source_authority, "verify_runtime_inputs", None
            )
            if callable(verify_inputs):
                verify_inputs(lane.build_recipe, lane.spec)
        if len(vault_identities) != 1 or len(signer_identities) != 1:
            return False
    except Exception:  # noqa: BLE001 - shared health is fail-closed
        return False
    return True


def _gate(passed: bool, **details: object) -> dict[str, object]:
    return {"passed": passed, **details}


def _family_gates(
    rows: tuple[RuntimeFamilyPreparationRow, ...],
    lane_inputs: tuple[RuntimeFamilyLaneInput, ...],
    *,
    output_root: Path,
    mapping_release_id: str,
    mapping_release_identity_sha256: str,
) -> dict[str, dict[str, object]]:
    prepared = tuple(row for row in rows if row.status == "prepared")
    all_prepared = len(rows) == 4 and len(prepared) == 4
    gates: dict[str, dict[str, object]] = {
        "all_lanes_prepared": _gate(
            all_prepared,
            statuses={row.lane_id: row.status for row in rows},
        )
    }
    documents: dict[str, Mapping[str, object]] = {}
    bindings: dict[str, dict[str, object]] = {}
    metadata: dict[str, Mapping[str, object]] = {}
    signers: dict[str, Mapping[str, object]] = {}
    receipt_identities: dict[str, str] = {}
    if all_prepared:
        for row, lane in zip(rows, lane_inputs):
            assert row.preparation_receipt is not None
            documents[row.lane_id] = row.preparation_receipt
            receipt_identities[row.lane_id] = str(
                row.preparation_receipt.get("receipt_identity_sha256")
            )
            apk = row.preparation_receipt.get("apk")
            build = row.preparation_receipt.get("build")
            source = row.preparation_receipt.get("source")
            if isinstance(apk, Mapping):
                metadata[row.lane_id] = apk
            if isinstance(build, Mapping) and isinstance(
                build.get("runtime_signing_identity"), Mapping
            ):
                signers[row.lane_id] = build["runtime_signing_identity"]
            if isinstance(source, Mapping) and isinstance(
                source.get("mapping_binding"), Mapping
            ):
                bindings[row.lane_id] = dict(source["mapping_binding"])

    sealed_paths: dict[str, Path] = {}
    sealed_digests: dict[str, str] = {}
    sealed_valid = all_prepared and len(documents) == 4
    for row in prepared:
        try:
            assert row.preparation_receipt is not None
            sealed_binding = sealed_apk_binding_from_receipt(row.preparation_receipt)
            if sealed_binding is None:
                raise ValueError
            sealed_path, size, digest = sealed_binding
            if (
                sealed_path is None
                or not sealed_path.is_file()
                or sealed_path.is_symlink()
            ):
                raise ValueError
            if (
                sealed_path.stat().st_size != size
                or _file_sha256(sealed_path) != digest
            ):
                raise ValueError
            sealed_path.resolve().relative_to(output_root)
            sealed_paths[row.lane_id] = sealed_path
            sealed_digests[row.lane_id] = digest
        except (
            RuntimePreparationVerificationError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            sealed_valid = False
    gates["sealed_apks"] = _gate(
        sealed_valid and len(sealed_paths) == 4,
        sha256_by_lane=sealed_digests,
    )

    receipt_identity_valid = (
        all_prepared
        and len(receipt_identities) == 4
        and all(_HEX_64.fullmatch(value) for value in receipt_identities.values())
    )
    gates["receipt_identity"] = _gate(
        receipt_identity_valid,
        identity_sha256_by_lane=receipt_identities,
    )

    signer_valid = (
        all_prepared
        and len(signers) == 4
        and len({_canonical_sha256(value) for value in signers.values()}) == 1
    )
    gates["family_signing_identity"] = _gate(
        signer_valid,
        identity_sha256_by_lane={
            lane_id: _canonical_sha256(value) for lane_id, value in signers.items()
        },
    )

    vault_identities = {
        lane.runtime_input_vault.manifest.identity_sha256
        for lane in lane_inputs
        if lane.runtime_input_vault is not None
    }
    gates["family_vault_identity"] = _gate(
        len(vault_identities) == 1 and len(lane_inputs) == 4,
        identity_sha256_by_lane={
            lane.lane_id: lane.runtime_input_vault.manifest.identity_sha256
            for lane in lane_inputs
            if lane.runtime_input_vault is not None
        },
    )

    metadata_valid = all_prepared and len(metadata) == 4
    if metadata_valid:
        fields = (
            "package",
            "launcher_activity",
            "version_code",
            "version_name",
            "min_sdk",
            "target_sdk",
            "compile_sdk",
            "debuggable",
            "signer_sha256",
            "signer_count",
            "v1_verified",
            "v2_verified",
        )
        for field_name in fields:
            values = [
                metadata[lane_id].get(field_name)
                for lane_id in runtime_mapping.FROZEN_LANE_ORDER
            ]
            if (
                any(value is None for value in values)
                or len(set(map(str, values))) != 1
            ):
                metadata_valid = False
                break
        for lane, lane_id in zip(lane_inputs, runtime_mapping.FROZEN_LANE_ORDER):
            signer = _effective_signer(lane)
            expected_values = _metadata_document(
                ApkMetadata(
                    package=lane.spec.package,
                    launcher_activity=lane.spec.activity or "",
                    version_code=54,
                    version_name="3.2.1",
                    min_sdk=21,
                    target_sdk=35,
                    compile_sdk=35,
                    debuggable=True,
                    signer_sha256=(
                        signer.certificate_sha256 if signer is not None else None
                    ),
                    signer_count=1,
                    v1_verified=True,
                    v2_verified=True,
                )
            )
            if any(
                metadata[lane_id].get(key) != value
                for key, value in expected_values.items()
                if value is not None
            ):
                metadata_valid = False
            if lane.expected_apk_metadata is not None:
                declared_values = _metadata_document(lane.expected_apk_metadata)
                if any(
                    value is not None and value != expected_values.get(key)
                    for key, value in declared_values.items()
                ):
                    metadata_valid = False
    gates["family_metadata_identity"] = _gate(
        metadata_valid,
        metadata_sha256_by_lane={
            lane_id: _canonical_sha256(value) for lane_id, value in metadata.items()
        },
    )

    environment_roots = {
        row.lane_id: str(row.private_environment_root)
        for row in prepared
        if row.private_environment_root is not None
    }
    environments_valid = (
        all(row.private_environment_root is not None for row in prepared)
        and len(environment_roots) == 4
        and len(set(environment_roots.values())) == 4
        and all(Path(path).is_dir() for path in environment_roots.values())
        and all(
            not _is_overlapping(Path(path), output_root)
            and all(
                not _is_overlapping(Path(path), row.source_worktree) for row in rows
            )
            for path in environment_roots.values()
        )
    )
    gates["independent_build_environments"] = _gate(
        environments_valid,
        path_sha256_by_lane={
            lane_id: _canonical_sha256(path)
            for lane_id, path in environment_roots.items()
        },
    )

    single_build_valid = all(
        row.status == "prepared"
        and row.build_started is True
        and row.build_attempts == 1
        for row in rows
    )
    gates["single_build_attempt"] = _gate(single_build_valid)

    effects_valid = (
        all(
            isinstance(document.get("runtime_effects"), Mapping)
            and dict(cast(Mapping[str, object], document["runtime_effects"]))
            == _PREPARATION_RUNTIME_EFFECTS
            for document in documents.values()
        )
        if all_prepared
        else False
    )
    gates["no_runtime_effects"] = _gate(effects_valid)

    handoff_valid = all_prepared and len(bindings) == 4
    if handoff_valid:
        for lane_id, binding in bindings.items():
            if (
                binding.get("lane_id") != lane_id
                or binding.get("release_id") != mapping_release_id
                or binding.get("release_identity_sha256")
                != mapping_release_identity_sha256
            ):
                handoff_valid = False
    gates["mapping_handoff_identity"] = _gate(
        handoff_valid,
        binding_sha256_by_lane={
            lane_id: _canonical_sha256(value) for lane_id, value in bindings.items()
        },
    )

    source_valid = all_prepared
    for document in documents.values():
        source = document.get("source")
        source_identity = (
            source.get("identity_sha256") if isinstance(source, Mapping) else None
        )
        source_body = dict(source) if isinstance(source, Mapping) else {}
        source_body.pop("identity_sha256", None)
        if (
            not isinstance(source, Mapping)
            or not isinstance(source.get("before"), Mapping)
            or not isinstance(source.get("after"), Mapping)
            or source_identity != _canonical_sha256(source_body)
            or dict(source["before"]) != dict(source["after"])
        ):
            source_valid = False
            break
    gates["source_identity"] = _gate(source_valid)

    equality_valid = False
    inequality_valid = False
    if len(sealed_paths) == 4:
        try:
            equal_control = (
                sealed_paths[runtime_mapping.FROZEN_LANE_ORDER[0]].read_bytes()
                == sealed_paths[runtime_mapping.FROZEN_LANE_ORDER[2]].read_bytes()
            )
            equal_defect = (
                sealed_paths[runtime_mapping.FROZEN_LANE_ORDER[1]].read_bytes()
                == sealed_paths[runtime_mapping.FROZEN_LANE_ORDER[3]].read_bytes()
            )
            equality_valid = (
                equal_control
                and equal_defect
                and sealed_digests[runtime_mapping.FROZEN_LANE_ORDER[0]]
                == sealed_digests[runtime_mapping.FROZEN_LANE_ORDER[2]]
                and sealed_digests[runtime_mapping.FROZEN_LANE_ORDER[1]]
                == sealed_digests[runtime_mapping.FROZEN_LANE_ORDER[3]]
            )
            different_control_defect = (
                sealed_paths[runtime_mapping.FROZEN_LANE_ORDER[0]].read_bytes()
                != sealed_paths[runtime_mapping.FROZEN_LANE_ORDER[1]].read_bytes()
            )
            inequality_valid = (
                len(
                    {
                        sealed_digests[runtime_mapping.FROZEN_LANE_ORDER[0]],
                        sealed_digests[runtime_mapping.FROZEN_LANE_ORDER[1]],
                    }
                )
                == 2
                and different_control_defect
            )
        except KeyError:
            pass
    gates["within_variant_byte_equality"] = _gate(
        equality_valid,
        sha256_by_lane=sealed_digests,
    )
    gates["control_defect_byte_inequality"] = _gate(
        inequality_valid,
        sha256_by_lane=sealed_digests,
    )
    return gates


def _metadata_document(metadata: ApkMetadata) -> dict[str, object]:
    return {
        "package": metadata.package,
        "launcher_activity": metadata.launcher_activity,
        "version_code": metadata.version_code,
        "version_name": metadata.version_name,
        "min_sdk": metadata.min_sdk,
        "target_sdk": metadata.target_sdk,
        "compile_sdk": metadata.compile_sdk,
        "debuggable": metadata.debuggable,
        "signer_sha256": metadata.signer_sha256,
        "signer_count": metadata.signer_count,
        "v1_verified": metadata.v1_verified,
        "v2_verified": metadata.v2_verified,
    }


def _all_gates_pass(gates: Mapping[str, Mapping[str, object]]) -> bool:
    return bool(gates) and all(value.get("passed") is True for value in gates.values())


def _receipt_from_document(
    document: Mapping[str, object],
) -> RuntimeFamilyPreparationReceipt:
    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("stage") != RUNTIME_FAMILY_PREPARATION_STAGE
    ):
        raise RuntimeFamilyPreparationError("family_preparation_receipt_invalid")
    if document.get("claim_boundary") != RUNTIME_FAMILY_PREPARATION_CLAIM_BOUNDARY:
        raise RuntimeFamilyPreparationError("family_preparation_claim_boundary_invalid")
    raw_rows = document.get("rows")
    if not isinstance(raw_rows, list):
        raise RuntimeFamilyPreparationError("family_preparation_rows_invalid")
    rows: list[RuntimeFamilyPreparationRow] = []
    for raw in raw_rows:
        if not isinstance(raw, Mapping):
            raise RuntimeFamilyPreparationError("family_preparation_rows_invalid")
        try:
            receipt_doc = raw.get("preparation_receipt")
            if receipt_doc is not None and not isinstance(receipt_doc, Mapping):
                raise ValueError
            artifacts = raw.get("artifacts", [])
            if not isinstance(artifacts, list) or any(
                not isinstance(item, Mapping) for item in artifacts
            ):
                raise ValueError
            private_root = raw.get("private_environment_root")
            row = RuntimeFamilyPreparationRow(
                lane_id=raw["lane_id"],
                status=raw["status"],
                source_worktree=Path(raw["source_worktree"]),
                artifact_root=Path(raw["artifact_root"]),
                build_started=raw["build_started"],
                build_attempts=raw["build_attempts"],
                artifacts=tuple(dict(item) for item in artifacts),
                preparation_receipt=dict(receipt_doc)
                if isinstance(receipt_doc, Mapping)
                else None,
                preparation_receipt_sha256=raw.get("preparation_receipt_sha256"),
                rejection_code=raw.get("rejection_code"),
                failure_scope=raw.get("failure_scope"),
                private_environment_root=Path(private_root)
                if isinstance(private_root, str)
                else None,
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, RuntimeFamilyPreparationError):
                raise
            raise RuntimeFamilyPreparationError(
                "family_preparation_rows_invalid"
            ) from error
        rows.append(row)
    try:
        gates = document["gates"]
        if not isinstance(gates, Mapping) or any(
            not isinstance(value, Mapping) for value in gates.values()
        ):
            raise ValueError
        accepted = cast(bool, document["accepted"])
        candidate_root = cast(str, document["candidate_root"])
        predecessor_root = cast(str, document["predecessor_root"])
        output_root = cast(str, document["output_root"])
        mapping_release_id = cast(str, document["mapping_release_id"])
        mapping_release_identity = cast(
            str, document["mapping_release_identity_sha256"]
        )
        mapping_release_sha256 = cast(str, document["mapping_release_sha256"])
        candidate_identity = cast(str, document["candidate_identity_sha256"])
        candidate_manifest = cast(str, document["candidate_manifest_sha256"])
        candidate_artifacts = cast(str, document["candidate_artifact_inventory_sha256"])
        start_receipt = cast(str, document["start_receipt_sha256"])
        raw_reason = document.get("reason")
        reason = raw_reason if isinstance(raw_reason, str) else None
        raw_terminal_identity = document.get("terminal_identity_sha256")
        if (
            not isinstance(raw_terminal_identity, str)
            or _HEX_64.fullmatch(raw_terminal_identity) is None
        ):
            raise ValueError
        terminal_identity = raw_terminal_identity
        receipt = RuntimeFamilyPreparationReceipt(
            accepted=accepted,
            candidate_root=Path(candidate_root),
            predecessor_root=Path(predecessor_root),
            output_root=Path(output_root),
            mapping_release_id=mapping_release_id,
            mapping_release_identity_sha256=mapping_release_identity,
            mapping_release_sha256=mapping_release_sha256,
            candidate_identity_sha256=candidate_identity,
            candidate_manifest_sha256=candidate_manifest,
            candidate_artifact_inventory_sha256=candidate_artifacts,
            rows=tuple(rows),
            gates={str(name): dict(value) for name, value in gates.items()},
            reason=reason,
            start_receipt_sha256=start_receipt,
            terminal_identity_sha256=terminal_identity,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeFamilyPreparationError(
            "family_preparation_receipt_invalid"
        ) from error
    if (
        document.get("status") != receipt.status
        or document.get("identity_sha256") != receipt.identity_sha256
    ):
        raise RuntimeFamilyPreparationError(
            "family_preparation_receipt_identity_mismatch"
        )
    raw_lane_ids = document.get("lane_ids")
    if not isinstance(raw_lane_ids, list) or any(
        not isinstance(value, str) for value in raw_lane_ids
    ):
        raise RuntimeFamilyPreparationError("family_preparation_lane_order_mismatch")
    if tuple(raw_lane_ids) != receipt.lane_ids:
        raise RuntimeFamilyPreparationError("family_preparation_lane_order_mismatch")
    return receipt


def load_runtime_family_preparation(
    path: str | Path,
) -> RuntimeFamilyPreparationReceipt:
    """Load a family preparation receipt from a stage root or receipt path."""
    raw = Path(path).expanduser()
    receipt_path = raw / RUNTIME_FAMILY_PREPARATION_FILENAME if raw.is_dir() else raw
    return _receipt_from_document(
        _read_json(receipt_path, "family_preparation_receipt_unavailable")
    )


def verify_runtime_family_preparation(
    receipt: RuntimeFamilyPreparationReceipt | Mapping[str, object] | str | Path,
    *,
    candidate_root: str | Path | None = None,
    predecessor_root: str | Path | None = None,
) -> None:
    """Reverify the terminal family receipt and every preserved APK binding."""
    if isinstance(receipt, (str, Path)):
        value = load_runtime_family_preparation(receipt)
    elif isinstance(receipt, RuntimeFamilyPreparationReceipt):
        identity_body = receipt.to_dict(include_identity=False)
        identity_body.pop("terminal_identity_sha256", None)
        if receipt.identity_sha256 != _canonical_sha256(identity_body):
            raise RuntimeFamilyPreparationError(
                "family_preparation_receipt_identity_mismatch"
            )
        value = receipt
    elif isinstance(receipt, Mapping):
        value = _receipt_from_document(receipt)
    else:
        raise RuntimeFamilyPreparationError("family_preparation_receipt_unavailable")
    if value.lane_ids != runtime_mapping.FROZEN_LANE_ORDER or len(value.rows) != 4:
        raise RuntimeFamilyPreparationError("family_preparation_lane_order_mismatch")
    selected_candidate = _canonical_path(candidate_root or value.candidate_root)
    try:
        candidate = runtime_calibration.verify_candidate_inputs(selected_candidate)
    except (
        runtime_calibration.CandidateVerificationError,
        RuntimeError,
        OSError,
        ValueError,
    ) as error:
        raise RuntimeFamilyPreparationError("candidate_input_mismatch") from error
    if (
        candidate.candidate_identity_sha256 != value.candidate_identity_sha256
        or candidate.manifest_sha256 != value.candidate_manifest_sha256
        or candidate.artifact_inventory_sha256
        != value.candidate_artifact_inventory_sha256
    ):
        raise RuntimeFamilyPreparationError("candidate_input_mismatch")
    selected_predecessor = _canonical_path(predecessor_root or value.predecessor_root)
    release, _, _, release_sha = _load_mapping_predecessor(
        selected_predecessor,
        candidate=candidate,
    )
    if (
        release.release_id != value.mapping_release_id
        or release.identity_sha256 != value.mapping_release_identity_sha256
        or release_sha != value.mapping_release_sha256
    ):
        raise RuntimeFamilyPreparationError("mapping_predecessor_identity_mismatch")
    if stage_status(value.output_root) != value.status:
        raise RuntimeFamilyPreparationError("family_stage_terminal_mismatch")
    terminal = _read_json(
        value.output_root / "stage-terminal.json",
        "family_stage_terminal_invalid",
    )
    if (
        terminal.get("start_receipt_sha256") != value.start_receipt_sha256
        or terminal.get("status") != value.status
        or terminal.get("preparation_identity_sha256") != value.identity_sha256
        or terminal.get("terminal_identity_sha256") != value.terminal_identity_sha256
    ):
        raise RuntimeFamilyPreparationError("family_stage_terminal_mismatch")
    for row in value.rows:
        if row.status in {"prepared", "prepared_but_family_not_admitted"} and (
            not row.build_started or row.build_attempts != 1
        ):
            raise RuntimeFamilyPreparationError("family_build_attempt_count_invalid")
        if row.preparation_receipt is not None:
            if row.preparation_receipt_sha256 != _canonical_sha256(
                row.preparation_receipt
            ):
                raise RuntimeFamilyPreparationError("preparation_receipt_drifted")
            prepared = row.preparation_receipt.get("prepared") is True
            if row.status == "prepared" and not prepared:
                raise RuntimeFamilyPreparationError("prepared_row_receipt_missing")
            try:
                _verify_receipt_identity(row.preparation_receipt)
            except RuntimeFamilyPreparationError:
                if row.status != "preparation_rejected":
                    raise
            if prepared and row.status != "preparation_rejected":
                sealed = row.preparation_receipt.get("sealed_apk")
                if not isinstance(sealed, Mapping):
                    raise RuntimeFamilyPreparationError("sealed_apk_handoff_missing")
                sealed_path = sealed.get("path")
                sealed_size = sealed.get("bytes")
                sealed_digest = sealed.get("sha256")
                expected_path = (
                    row.artifact_root / "build" / "app-debug.apk"
                ).resolve()
                if (
                    not isinstance(sealed_path, str)
                    or Path(sealed_path) != expected_path
                    or not isinstance(sealed_size, int)
                    or isinstance(sealed_size, bool)
                    or not isinstance(sealed_digest, str)
                    or not expected_path.is_file()
                    or expected_path.is_symlink()
                ):
                    raise RuntimeFamilyPreparationError("sealed_apk_handoff_invalid")
                details = expected_path.stat()
                if (
                    details.st_size != sealed_size
                    or _file_sha256(expected_path) != sealed_digest
                    or details.st_nlink != 1
                    or details.st_mode & 0o222
                ):
                    raise RuntimeFamilyPreparationError("sealed_apk_handoff_drifted")
                if (
                    row.preparation_receipt.get("runtime_effects")
                    != _PREPARATION_RUNTIME_EFFECTS
                ):
                    raise RuntimeFamilyPreparationError(
                        "preparation_runtime_effects_present"
                    )
                build = row.preparation_receipt.get("build")
                if not isinstance(build, Mapping) or build.get("retry") is not False:
                    raise RuntimeFamilyPreparationError(
                        "preparation_build_identity_missing"
                    )
                source = row.preparation_receipt.get("source")
                if (
                    not isinstance(source, Mapping)
                    or not isinstance(source.get("before"), Mapping)
                    or not isinstance(source.get("after"), Mapping)
                ):
                    raise RuntimeFamilyPreparationError(
                        "preparation_source_identity_incomplete"
                    )
        elif row.status in {"prepared", "prepared_but_family_not_admitted"}:
            raise RuntimeFamilyPreparationError("prepared_row_receipt_missing")
        for raw_artifact in row.artifacts:
            path = raw_artifact.get("path")
            if not isinstance(path, str):
                raise RuntimeFamilyPreparationError("preparation_artifact_invalid")
            artifact = Path(path)
            try:
                if artifact.resolve() != artifact:
                    raise ValueError
                artifact.resolve().relative_to(value.output_root)
            except ValueError as error:
                raise RuntimeFamilyPreparationError(
                    "preparation_artifact_outside_output"
                ) from error
            if artifact.is_symlink() or not artifact.is_file():
                raise RuntimeFamilyPreparationError("preparation_artifact_unavailable")
            details = artifact.stat()
            if (
                raw_artifact.get("bytes") != details.st_size
                or raw_artifact.get("sha256") != _file_sha256(artifact)
                or details.st_nlink != 1
                or details.st_mode & 0o222
            ):
                raise RuntimeFamilyPreparationError("preparation_artifact_drifted")
    if value.accepted and not _all_gates_pass(value.gates):
        raise RuntimeFamilyPreparationError("family_gates_not_satisfied")


def stage_status(output_root: str | Path) -> str:
    """Return the structural status of a ``prepare-family`` stage root."""
    root = _canonical_path(output_root)
    start_path = root / "stage-start.json"
    terminal_path = root / "stage-terminal.json"
    if start_path.is_symlink() or terminal_path.is_symlink():
        return "invalid"
    if not start_path.is_file():
        return "absent"
    try:
        start = _read_json(start_path, "family_stage_start_invalid")
        if start.get("stage") != RUNTIME_FAMILY_PREPARATION_STAGE or start.get(
            "start_identity_sha256"
        ) != _stage_identity(start, "start_identity_sha256"):
            return "invalid"
        if not terminal_path.is_file():
            return "abandoned"
        terminal = _read_json(terminal_path, "family_stage_terminal_invalid")
        if (
            terminal.get("stage") != RUNTIME_FAMILY_PREPARATION_STAGE
            or terminal.get("start_receipt_sha256")
            != _sha256_bytes(start_path.read_bytes())
            or terminal.get("terminal_identity_sha256")
            != _stage_identity(terminal, "terminal_identity_sha256")
        ):
            return "invalid"
        receipt_path = root / RUNTIME_FAMILY_PREPARATION_FILENAME
        value = load_runtime_family_preparation(receipt_path)
        if (
            terminal.get("status") != value.status
            or terminal.get("preparation_identity_sha256") != value.identity_sha256
            or value.output_root != root
        ):
            return "invalid"
        if terminal.get("terminal_identity_sha256") != value.terminal_identity_sha256:
            return "invalid"
        if terminal.get("status") not in {"accepted", "rejected"}:
            return "invalid"
        return str(terminal["status"])
    except (
        RuntimeFamilyPreparationError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        return "invalid"


def is_stage_abandoned(output_root: str | Path) -> bool:
    return stage_status(output_root) == "abandoned"


def _terminal_rows(
    rows: list[RuntimeFamilyPreparationRow],
    *,
    accepted: bool,
) -> tuple[RuntimeFamilyPreparationRow, ...]:
    if accepted:
        return tuple(rows)
    return tuple(
        replace(row, status="prepared_but_family_not_admitted")
        if row.status == "prepared"
        else row
        for row in rows
    )


def prepare_runtime_family(
    *,
    candidate_root: str | Path,
    predecessor_root: str | Path,
    output_root: str | Path,
    lane_inputs: Mapping[str, RuntimeFamilyLaneInput]
    | Sequence[RuntimeFamilyLaneInput],
    lane_preparer: RuntimeFamilyLanePreparer | None = None,
    shared_health_check: RuntimeFamilyHealthCheck | None = None,
    health_check: RuntimeFamilyHealthCheck | None = None,
) -> RuntimeFamilyPreparationReceipt:
    """Prepare the four APK lanes and close one family-wide admission decision.

    All validation before ``stage-start.json`` is side-effect free with respect
    to source worktrees. Once the start receipt exists, each lane is called at
    most once in frozen order. A normal exception is terminalized as an
    unknown/shared failure; ``KeyboardInterrupt`` and other ``BaseException``
    values intentionally leave the stage abandoned.
    """
    output = _prepare_output_root(output_root)
    candidate_path = _canonical_path(candidate_root)
    predecessor_path = _canonical_path(predecessor_root)
    if _is_overlapping(output, candidate_path) or _is_overlapping(
        output, predecessor_path
    ):
        raise RuntimeFamilyPreparationError("family_output_root_location_invalid")
    try:
        candidate = runtime_calibration.verify_candidate_inputs(candidate_path)
    except (
        runtime_calibration.CandidateVerificationError,
        RuntimeError,
        OSError,
        ValueError,
    ) as error:
        raise RuntimeFamilyPreparationError("candidate_input_mismatch") from error
    release, predecessor, predecessor_terminal_sha256, release_sha256 = (
        _load_mapping_predecessor(
            predecessor_path,
            candidate=candidate,
        )
    )
    ordered = _validate_lane_inputs(
        lane_inputs,
        candidate=candidate,
        release=release,
        output_root=output,
    )
    if health_check is not None and shared_health_check is not None:
        raise RuntimeFamilyPreparationError("family_health_check_ambiguous")
    selected_health_check = health_check or shared_health_check
    start: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "stage": RUNTIME_FAMILY_PREPARATION_STAGE,
        "status": "started",
        "claim_boundary": RUNTIME_FAMILY_PREPARATION_CLAIM_BOUNDARY,
        "candidate_root": str(candidate.root),
        "predecessor_root": str(predecessor),
        "output_root": str(output),
        "candidate_identity_sha256": candidate.candidate_identity_sha256,
        "candidate_manifest_sha256": candidate.manifest_sha256,
        "candidate_artifact_inventory_sha256": candidate.artifact_inventory_sha256,
        "mapping_release_id": release.release_id,
        "mapping_release_identity_sha256": release.identity_sha256,
        "mapping_release_sha256": release_sha256,
        "predecessor_terminal_sha256": predecessor_terminal_sha256,
        "lane_ids": list(runtime_mapping.FROZEN_LANE_ORDER),
        "started_at": _now(),
    }
    start["start_identity_sha256"] = _stage_identity(start, "start_identity_sha256")
    start_sha256 = _write_json_exclusive(output / "stage-start.json", start)

    rows: list[RuntimeFamilyPreparationRow] = []
    abort_reason: str | None = None
    abort_scope: str | None = None
    for index, original_lane in enumerate(ordered, start=1):
        staged_lane = _staged_lane_input(original_lane, output, index)
        lane_root = output / "lanes" / f"lane-{index:02d}"
        artifact_root = lane_root / "artifacts"
        if abort_reason is not None:
            rows.append(
                RuntimeFamilyPreparationRow(
                    lane_id=staged_lane.lane_id,
                    status="not_prepared_due_to_family_abort",
                    source_worktree=staged_lane.options.workdir.resolve(),
                    artifact_root=artifact_root,
                    build_started=False,
                    build_attempts=0,
                    rejection_code=abort_reason,
                    failure_scope=abort_scope,
                )
            )
            continue
        try:
            lane_root.mkdir(parents=True, exist_ok=False)
            artifact_root.mkdir(parents=False, exist_ok=False)
        except OSError:
            abort_reason = "family_lane_output_unavailable"
            abort_scope = "shared"
            rows.append(
                RuntimeFamilyPreparationRow(
                    lane_id=staged_lane.lane_id,
                    status="preparation_rejected",
                    source_worktree=staged_lane.options.workdir.resolve(),
                    artifact_root=artifact_root,
                    build_started=False,
                    build_attempts=0,
                    rejection_code=abort_reason,
                    failure_scope=abort_scope,
                )
            )
            continue
        preparer = lane_preparer or _default_lane_preparer
        normalized: RuntimeFamilyLaneResult
        try:
            normalized = _normalize_lane_result(preparer(staged_lane))
        except RuntimeFamilyLaneFailure as error:
            normalized = RuntimeFamilyLaneResult(
                receipt=None,
                build_started=error.build_started,
                build_attempts=error.build_attempts,
                failure_scope=error.scope,
                rejection_code=error.code,
            )
        except Exception as error:  # noqa: BLE001 - ordinary failures close the family
            normalized = RuntimeFamilyLaneResult(
                receipt=None,
                build_started=True,
                build_attempts=1,
                failure_scope="unknown",
                rejection_code=getattr(error, "code", "family_lane_preparation_failed"),
            )
        document: dict[str, object] | None = None
        receipt_digest: str | None = None
        rejection_code = normalized.rejection_code
        failure_scope = normalized.failure_scope
        artifacts: tuple[Mapping[str, object], ...] = ()
        private_root = normalized.private_environment_root
        if normalized.receipt is not None:
            try:
                document = _receipt_document(normalized.receipt)
                receipt_digest = _receipt_digest(document)
                if normalized.build_started and normalized.build_attempts != 1:
                    raise RuntimeFamilyPreparationError(
                        "family_build_attempt_count_invalid"
                    )
                if document.get("prepared") is True:
                    _validate_prepared_receipt(
                        normalized.receipt,
                        staged_lane,
                        output_root=output,
                        allow_test_substitutes=staged_lane.allow_test_substitutes,
                    )
                    failure_scope = None
                    rejection_code = None
                    build_document = document.get("build")
                    recorded_private_root = (
                        build_document.get("private_input_root")
                        if isinstance(build_document, Mapping)
                        else None
                    )
                    if isinstance(recorded_private_root, str):
                        private_root = private_root or Path(recorded_private_root)
                else:
                    raw_rejection_code = document.get("rejection_code")
                    receipt_rejection_code = (
                        raw_rejection_code
                        if isinstance(raw_rejection_code, str)
                        else "preparation_rejected"
                    )
                    rejection_code = rejection_code or receipt_rejection_code
                    failure_scope = failure_scope or _default_failure_scope(
                        rejection_code
                    )
            except RuntimeFamilyPreparationError as error:
                rejection_code = rejection_code or error.code
                failure_scope = failure_scope or "unknown"
        else:
            rejection_code = rejection_code or "family_lane_preparation_failed"
            failure_scope = failure_scope or "unknown"
        if (
            document is not None
            and document.get("prepared") is True
            and failure_scope is None
        ):
            status = "prepared"
        else:
            status = "preparation_rejected"
        try:
            artifacts = _preserve_artifacts(
                staged_lane,
                normalized,
                document,
                lane_root=lane_root,
                output_root=output,
            )
        except RuntimeFamilyPreparationError as error:
            status = "preparation_rejected"
            rejection_code = error.code
            failure_scope = "shared"
        row = RuntimeFamilyPreparationRow(
            lane_id=staged_lane.lane_id,
            status=status,
            source_worktree=staged_lane.options.workdir.resolve(),
            artifact_root=artifact_root,
            build_started=normalized.build_started,
            build_attempts=normalized.build_attempts,
            artifacts=artifacts,
            preparation_receipt=document,
            preparation_receipt_sha256=receipt_digest,
            rejection_code=rejection_code,
            failure_scope=failure_scope,
            private_environment_root=private_root,
        )
        rows.append(row)
        if status != "prepared":
            if failure_scope != "lane_local":
                abort_reason = rejection_code or "family_lane_preparation_failed"
                abort_scope = failure_scope or "unknown"
            else:
                remaining_index = index + 1
                if remaining_index <= 4:
                    next_lane = ordered[remaining_index - 1]
                    try:
                        healthy = (
                            _invoke_health_check(selected_health_check, row, next_lane)
                            if selected_health_check is not None
                            else _default_health_check(
                                ordered,
                                candidate_root=candidate.root,
                                predecessor_root=predecessor,
                            )
                        )
                    except RuntimeFamilyPreparationError:
                        healthy = False
                    if not healthy:
                        abort_reason = "family_shared_health_rejected"
                        abort_scope = "shared"

    provisional_rows = tuple(rows)
    gates = _family_gates(
        provisional_rows,
        ordered,
        output_root=output,
        mapping_release_id=release.release_id,
        mapping_release_identity_sha256=release.identity_sha256,
    )
    accepted = (
        len(rows) == 4
        and all(row.status == "prepared" for row in rows)
        and _all_gates_pass(gates)
    )
    final_rows = _terminal_rows(rows, accepted=accepted)
    if not accepted and abort_reason is None:
        failed_gate = next(
            (name for name, value in gates.items() if value.get("passed") is not True),
            None,
        )
        abort_reason = failed_gate or "family_not_admitted"
        abort_scope = abort_scope or "shared"
    terminal_reason = None if accepted else abort_reason
    base_receipt = RuntimeFamilyPreparationReceipt(
        accepted=accepted,
        candidate_root=candidate.root,
        predecessor_root=predecessor,
        output_root=output,
        mapping_release_id=release.release_id,
        mapping_release_identity_sha256=release.identity_sha256,
        mapping_release_sha256=release_sha256,
        candidate_identity_sha256=candidate.candidate_identity_sha256,
        candidate_manifest_sha256=candidate.manifest_sha256,
        candidate_artifact_inventory_sha256=candidate.artifact_inventory_sha256,
        rows=final_rows,
        gates=gates,
        reason=terminal_reason,
        start_receipt_sha256=start_sha256,
    )
    terminal: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "stage": RUNTIME_FAMILY_PREPARATION_STAGE,
        "status": base_receipt.status,
        "claim_boundary": RUNTIME_FAMILY_PREPARATION_CLAIM_BOUNDARY,
        "candidate_root": str(candidate.root),
        "predecessor_root": str(predecessor),
        "output_root": str(output),
        "candidate_identity_sha256": candidate.candidate_identity_sha256,
        "candidate_manifest_sha256": candidate.manifest_sha256,
        "candidate_artifact_inventory_sha256": candidate.artifact_inventory_sha256,
        "mapping_release_id": release.release_id,
        "mapping_release_identity_sha256": release.identity_sha256,
        "mapping_release_sha256": release_sha256,
        "preparation_identity_sha256": base_receipt.identity_sha256,
        "reason": terminal_reason,
        "start_receipt_sha256": start_sha256,
        "finished_at": _now(),
    }
    terminal["terminal_identity_sha256"] = _stage_identity(
        terminal, "terminal_identity_sha256"
    )
    final_receipt = replace(
        base_receipt,
        terminal_identity_sha256=cast(str, terminal["terminal_identity_sha256"]),
    )
    _write_json_exclusive(
        output / RUNTIME_FAMILY_PREPARATION_FILENAME, final_receipt.to_dict()
    )
    _write_json_exclusive(output / "stage-terminal.json", terminal)
    return final_receipt


def _default_lane_preparer(lane: RuntimeFamilyLaneInput) -> RuntimeFamilyLaneResult:
    def existing_built_paths() -> tuple[Path, ...]:
        return tuple(
            path
            for path in (
                lane.options.workdir
                / "app"
                / "build"
                / "outputs"
                / "apk"
                / "debug"
                / "app-debug.apk",
                lane.options.workdir / "build" / "app-debug.apk",
            )
            if path.is_file() and not path.is_symlink()
        )

    built_paths = existing_built_paths()
    try:
        receipt = prepare_runtime_case(
            source_authority=lane.source_authority,
            build_recipe=lane.build_recipe,
            spec=lane.spec,
            options=lane.options,
            build_runner=lane.build_runner,
            apk_inspector=lane.apk_inspector,
            admission_command_runner=lane.admission_command_runner,
            runtime_input_vault=lane.runtime_input_vault,
            runtime_signing_identity=lane.runtime_signing_identity,
            expected_apk_metadata=lane.expected_apk_metadata,
            sealed_apk_path=lane.options.artifact_dir / "build" / "app-debug.apk",
            allow_test_substitutes=lane.allow_test_substitutes,
        )
    except Exception as error:  # noqa: BLE001 - preserve outputs from a failed build
        return RuntimeFamilyLaneResult(
            receipt=None,
            artifacts=existing_built_paths(),
            build_started=True,
            build_attempts=1,
            failure_scope="unknown",
            rejection_code=getattr(error, "code", "family_lane_preparation_failed"),
        )
    # The one-lane function deliberately returns a small rejected receipt after
    # cleaning private inputs. The source-side APK is still a real artifact and
    # must be handed to the family preservation path before the next lane.
    refreshed_built_paths = tuple(
        path
        for path in (
            lane.options.workdir
            / "app"
            / "build"
            / "outputs"
            / "apk"
            / "debug"
            / "app-debug.apk",
            lane.options.workdir / "build" / "app-debug.apk",
        )
        if path.is_file() and not path.is_symlink()
    )
    return RuntimeFamilyLaneResult(
        receipt=receipt,
        artifacts=tuple(dict.fromkeys((*built_paths, *refreshed_built_paths))),
        build_started=True,
        build_attempts=1,
    )


# Short names used by the stage vocabulary and by callers migrating from the
# one-lane function.
prepare_family = prepare_runtime_family
prepare_runtime_calibration_family = prepare_runtime_family
admit_prepared_family = prepare_runtime_family
load_family_preparation = load_runtime_family_preparation
verify_family_preparation = verify_runtime_family_preparation


__all__ = [
    "RUNTIME_FAMILY_PREPARATION_CLAIM_BOUNDARY",
    "RUNTIME_FAMILY_PREPARATION_FAILURE_SCOPES",
    "RUNTIME_FAMILY_PREPARATION_FILENAME",
    "RUNTIME_FAMILY_PREPARATION_LANE_STATUSES",
    "RUNTIME_FAMILY_PREPARATION_STAGE",
    "RUNTIME_FAMILY_PREPARATION_STAGE_STATUSES",
    "RuntimeFamilyHealthCheck",
    "RuntimeFamilyLane",
    "RuntimeFamilyLaneFailure",
    "RuntimeFamilyLaneInput",
    "RuntimeFamilyLanePreparer",
    "RuntimeFamilyLaneResult",
    "RuntimeFamilyPreparationError",
    "RuntimeFamilyPreparationInput",
    "RuntimeFamilyPreparationReceipt",
    "RuntimeFamilyPreparationRow",
    "RuntimeFamilyPreparationStageReceipt",
    "admit_prepared_family",
    "is_stage_abandoned",
    "load_family_preparation",
    "load_runtime_family_preparation",
    "prepare_family",
    "prepare_runtime_calibration_family",
    "prepare_runtime_family",
    "stage_status",
    "verify_family_preparation",
    "verify_runtime_family_preparation",
]
