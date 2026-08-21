"""Immutable M0.1 contracts for source-delta materialization.

These contracts deliberately keep source identity separate from the temporary
path of a materialized worktree.  A path is useful for cleanup, but it is never
the identity of a baseline, patch, candidate, or resulting source tree.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = 1
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_OWNERSHIP_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
_VARIANTS = frozenset({"defect", "control"})
_REJECTION_CODES = frozenset(
    {
        "invalid_candidate",
        "caller_checkout_unavailable",
        "repository_origin_mismatch",
        "baseline_commit_unavailable",
        "baseline_tree_unreadable",
        "baseline_tree_mismatch",
        "worktree_root_unsafe",
        "worktree_root_unavailable",
        "worktree_creation_failed",
        "worktree_provenance_mismatch",
        "patch_not_applicable",
        "patch_apply_failed",
        "patch_did_not_change_source",
        "reserved_ownership_path",
        "result_identity_failed",
        "worktree_cleanup_failed",
    }
)


class InjectionContractError(ValueError):
    """Raised when an Injection Lab contract is malformed or contradictory."""


def canonical_json_bytes(value: object) -> bytes:
    """Return the one JSON encoding used by all M0.1 content identities."""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise InjectionContractError("contract value is not canonical JSON") from error


def sha256_hex(value: bytes | str) -> str:
    """Hash bytes, or UTF-8 text, with the Lab's canonical digest algorithm."""
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return sha256(raw).hexdigest()


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InjectionContractError(f"{field} must be a non-empty string")
    return value


def _sha256(value: object, field: str) -> str:
    text = _required_text(value, field)
    if not _SHA256_RE.fullmatch(text):
        raise InjectionContractError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _git_commit(value: object, field: str) -> str:
    text = _required_text(value, field)
    if not _GIT_COMMIT_RE.fullmatch(text):
        raise InjectionContractError(
            f"{field} must be a full lowercase Git object identifier"
        )
    return text


def _version(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value != SCHEMA_VERSION:
        raise InjectionContractError(f"unsupported {field} schema_version")
    return value


def _reject_unknown(data: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise InjectionContractError(
            f"unknown {label} field(s): " + ", ".join(unknown)
        )


def _identity(value: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(value))


@dataclass(frozen=True)
class BaselineProvenance:
    """Immutable source identity for the baseline from which a delta applies."""

    source_origin: str
    commit: str
    source_tree_sha256: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.source_origin, "baseline.source_origin")
        _git_commit(self.commit, "baseline.commit")
        _sha256(self.source_tree_sha256, "baseline.source_tree_sha256")
        _version(self.schema_version, "baseline")

    @property
    def identity_sha256(self) -> str:
        return _identity(self._identity_dict())

    def _identity_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_origin": self.source_origin,
            "commit": self.commit,
            "source_tree_sha256": self.source_tree_sha256,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._identity_dict(),
            "identity_sha256": self.identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BaselineProvenance":
        if not isinstance(data, Mapping):
            raise InjectionContractError("baseline must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "source_origin",
                "commit",
                "source_tree_sha256",
                "identity_sha256",
            },
            "baseline",
        )
        try:
            value = cls(
                source_origin=data["source_origin"],
                commit=data["commit"],
                source_tree_sha256=data["source_tree_sha256"],
                schema_version=data["schema_version"],
            )
            if data["identity_sha256"] != value.identity_sha256:
                raise InjectionContractError("baseline identity digest does not match")
            return value
        except KeyError as error:
            raise InjectionContractError(
                f"baseline requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class SourceDelta:
    """One declared unified-diff source delta and its immutable byte identity."""

    delta_id: str
    patch_text: str
    patch_sha256: str
    source_ref: str | None = None
    format: str = "unified_diff"
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.delta_id, "source_delta.delta_id")
        _required_text(self.patch_text, "source_delta.patch_text")
        _sha256(self.patch_sha256, "source_delta.patch_sha256")
        if self.patch_sha256 != sha256_hex(self.patch_text):
            raise InjectionContractError("source_delta.patch_sha256 does not match patch_text")
        if self.source_ref is not None:
            _required_text(self.source_ref, "source_delta.source_ref")
        if self.format != "unified_diff":
            raise InjectionContractError("M0.1 source_delta.format must be unified_diff")
        _version(self.schema_version, "source_delta")

    @classmethod
    def from_patch(
        cls,
        *,
        delta_id: str,
        patch_text: str,
        source_ref: str | None = None,
    ) -> "SourceDelta":
        """Create a source delta while deriving its byte-level patch digest."""
        return cls(
            delta_id=delta_id,
            patch_text=patch_text,
            patch_sha256=sha256_hex(patch_text),
            source_ref=source_ref,
        )

    @property
    def identity_sha256(self) -> str:
        return _identity(self._identity_dict())

    def _identity_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "delta_id": self.delta_id,
            "format": self.format,
            "patch_sha256": self.patch_sha256,
        }
        if self.source_ref is not None:
            result["source_ref"] = self.source_ref
        return result

    def to_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": self.schema_version,
            "delta_id": self.delta_id,
            "format": self.format,
            "patch_text": self.patch_text,
            "patch_sha256": self.patch_sha256,
            "identity_sha256": self.identity_sha256,
        }
        if self.source_ref is not None:
            result["source_ref"] = self.source_ref
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SourceDelta":
        if not isinstance(data, Mapping):
            raise InjectionContractError("source_delta must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "delta_id",
                "format",
                "patch_text",
                "patch_sha256",
                "source_ref",
                "identity_sha256",
            },
            "source_delta",
        )
        try:
            value = cls(
                delta_id=data["delta_id"],
                patch_text=data["patch_text"],
                patch_sha256=data["patch_sha256"],
                source_ref=data.get("source_ref"),
                format=data["format"],
                schema_version=data["schema_version"],
            )
            if data["identity_sha256"] != value.identity_sha256:
                raise InjectionContractError("source_delta identity digest does not match")
            return value
        except KeyError as error:
            raise InjectionContractError(
                f"source_delta requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class FaultOperator:
    """Versioned metadata for the one source transformation a candidate uses."""

    operator_id: str
    version: str
    applicability: str
    safety_boundary: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field in ("operator_id", "version", "applicability", "safety_boundary"):
            _required_text(getattr(self, field), f"operator.{field}")
        _version(self.schema_version, "operator")

    @property
    def identity_sha256(self) -> str:
        return _identity(self._identity_dict())

    def _identity_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operator_id": self.operator_id,
            "version": self.version,
            "applicability": self.applicability,
            "safety_boundary": self.safety_boundary,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._identity_dict(),
            "identity_sha256": self.identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FaultOperator":
        if not isinstance(data, Mapping):
            raise InjectionContractError("operator must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "operator_id",
                "version",
                "applicability",
                "safety_boundary",
                "identity_sha256",
            },
            "operator",
        )
        try:
            value = cls(
                operator_id=data["operator_id"],
                version=data["version"],
                applicability=data["applicability"],
                safety_boundary=data["safety_boundary"],
                schema_version=data["schema_version"],
            )
            if data["identity_sha256"] != value.identity_sha256:
                raise InjectionContractError("operator identity digest does not match")
            return value
        except KeyError as error:
            raise InjectionContractError(
                f"operator requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class InjectionCandidate:
    """An audit-side proposal containing exactly one curated source delta."""

    candidate_id: str
    baseline: BaselineProvenance
    source_delta: SourceDelta
    operator: FaultOperator
    variant: str = "defect"
    population: str = "curated"
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.candidate_id, "candidate.candidate_id")
        if not isinstance(self.baseline, BaselineProvenance):
            raise InjectionContractError("candidate.baseline must be BaselineProvenance")
        if not isinstance(self.source_delta, SourceDelta):
            raise InjectionContractError("candidate.source_delta must be exactly one SourceDelta")
        if not isinstance(self.operator, FaultOperator):
            raise InjectionContractError("candidate.operator must be FaultOperator")
        if self.variant not in _VARIANTS:
            raise InjectionContractError("candidate.variant must be defect or control")
        if self.population != "curated":
            raise InjectionContractError("M0.1 candidate.population must be curated")
        _version(self.schema_version, "candidate")

    @property
    def identity_sha256(self) -> str:
        return _identity(self._identity_dict())

    def _identity_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "baseline_identity_sha256": self.baseline.identity_sha256,
            "source_delta_identity_sha256": self.source_delta.identity_sha256,
            "operator_identity_sha256": self.operator.identity_sha256,
            "variant": self.variant,
            "population": self.population,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "baseline": self.baseline.to_dict(),
            "source_delta": self.source_delta.to_dict(),
            "operator": self.operator.to_dict(),
            "variant": self.variant,
            "population": self.population,
            "identity_sha256": self.identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "InjectionCandidate":
        if not isinstance(data, Mapping):
            raise InjectionContractError("candidate must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "candidate_id",
                "baseline",
                "source_delta",
                "operator",
                "variant",
                "population",
                "identity_sha256",
            },
            "candidate",
        )
        try:
            value = cls(
                candidate_id=data["candidate_id"],
                baseline=BaselineProvenance.from_dict(data["baseline"]),
                source_delta=SourceDelta.from_dict(data["source_delta"]),
                operator=FaultOperator.from_dict(data["operator"]),
                variant=data["variant"],
                population=data["population"],
                schema_version=data["schema_version"],
            )
            if data["identity_sha256"] != value.identity_sha256:
                raise InjectionContractError("candidate identity digest does not match")
            return value
        except KeyError as error:
            raise InjectionContractError(
                f"candidate requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class MaterializedWorktree:
    """Temporary ownership data, deliberately separate from source identity."""

    path: str
    ownership_token: str
    candidate_identity_sha256: str
    baseline_commit: str
    result_identity_sha256: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        path = Path(self.path)
        if not self.path or not path.is_absolute():
            raise InjectionContractError("worktree.path must be an absolute path")
        if not _OWNERSHIP_TOKEN_RE.fullmatch(self.ownership_token):
            raise InjectionContractError("worktree.ownership_token must be a UUID4 hex token")
        _sha256(self.candidate_identity_sha256, "worktree.candidate_identity_sha256")
        _git_commit(self.baseline_commit, "worktree.baseline_commit")
        _sha256(self.result_identity_sha256, "worktree.result_identity_sha256")
        _version(self.schema_version, "worktree")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "path": self.path,
            "ownership_token": self.ownership_token,
            "candidate_identity_sha256": self.candidate_identity_sha256,
            "baseline_commit": self.baseline_commit,
            "result_identity_sha256": self.result_identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MaterializedWorktree":
        if not isinstance(data, Mapping):
            raise InjectionContractError("worktree must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "path",
                "ownership_token",
                "candidate_identity_sha256",
                "baseline_commit",
                "result_identity_sha256",
            },
            "worktree",
        )
        try:
            return cls(
                path=data["path"],
                ownership_token=data["ownership_token"],
                candidate_identity_sha256=data["candidate_identity_sha256"],
                baseline_commit=data["baseline_commit"],
                result_identity_sha256=data["result_identity_sha256"],
                schema_version=data["schema_version"],
            )
        except KeyError as error:
            raise InjectionContractError(
                f"worktree requires {error.args[0]}"
            ) from error


def result_identity_sha256(
    *,
    baseline_identity_sha256: str,
    patch_identity_sha256: str,
    result_source_tree_sha256: str,
    result_diff_sha256: str,
) -> str:
    """Derive the stable identity of a materialized result, excluding its path."""
    for field, value in (
        ("baseline_identity_sha256", baseline_identity_sha256),
        ("patch_identity_sha256", patch_identity_sha256),
        ("result_source_tree_sha256", result_source_tree_sha256),
        ("result_diff_sha256", result_diff_sha256),
    ):
        _sha256(value, field)
    return _identity(
        {
            "schema_version": SCHEMA_VERSION,
            "baseline_identity_sha256": baseline_identity_sha256,
            "patch_identity_sha256": patch_identity_sha256,
            "result_source_tree_sha256": result_source_tree_sha256,
            "result_diff_sha256": result_diff_sha256,
        }
    )


@dataclass(frozen=True)
class InjectionReceipt:
    """A deterministic materialized or rejected outcome for one candidate."""

    outcome: str
    candidate_identity_sha256: str | None
    baseline_identity_sha256: str | None
    patch_identity_sha256: str | None
    result_source_tree_sha256: str | None = None
    result_diff_sha256: str | None = None
    result_identity_sha256: str | None = None
    rejection_code: str | None = None
    worktree: MaterializedWorktree | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _version(self.schema_version, "receipt")
        for field in (
            "candidate_identity_sha256",
            "baseline_identity_sha256",
            "patch_identity_sha256",
        ):
            value = getattr(self, field)
            if value is not None:
                _sha256(value, f"receipt.{field}")
        if self.outcome == "rejected":
            if self.rejection_code not in _REJECTION_CODES:
                raise InjectionContractError("receipt rejected outcome requires a stable reason")
            if any(
                value is not None
                for value in (
                    self.result_source_tree_sha256,
                    self.result_diff_sha256,
                    self.result_identity_sha256,
                    self.worktree,
                )
            ):
                raise InjectionContractError(
                    "rejected receipt must not contain materialized result data"
                )
            return
        if self.outcome != "materialized":
            raise InjectionContractError("receipt.outcome must be materialized or rejected")
        if self.rejection_code is not None:
            raise InjectionContractError("materialized receipt must not have a rejection_code")
        required = (
            self.candidate_identity_sha256,
            self.baseline_identity_sha256,
            self.patch_identity_sha256,
            self.result_source_tree_sha256,
            self.result_diff_sha256,
            self.result_identity_sha256,
        )
        if any(value is None for value in required):
            raise InjectionContractError(
                "materialized receipt requires complete source identities"
            )
        _sha256(self.result_source_tree_sha256, "receipt.result_source_tree_sha256")
        _sha256(self.result_diff_sha256, "receipt.result_diff_sha256")
        _sha256(self.result_identity_sha256, "receipt.result_identity_sha256")
        if not isinstance(self.worktree, MaterializedWorktree):
            raise InjectionContractError("materialized receipt requires an owned worktree")
        if self.worktree.candidate_identity_sha256 != self.candidate_identity_sha256:
            raise InjectionContractError("worktree candidate identity does not match receipt")
        if self.worktree.result_identity_sha256 != self.result_identity_sha256:
            raise InjectionContractError("worktree result identity does not match receipt")
        expected_result_identity = result_identity_sha256(
            baseline_identity_sha256=self.baseline_identity_sha256,
            patch_identity_sha256=self.patch_identity_sha256,
            result_source_tree_sha256=self.result_source_tree_sha256,
            result_diff_sha256=self.result_diff_sha256,
        )
        if self.result_identity_sha256 != expected_result_identity:
            raise InjectionContractError("receipt result identity does not match content")

    @classmethod
    def rejected(
        cls,
        candidate: InjectionCandidate | None,
        rejection_code: str,
    ) -> "InjectionReceipt":
        return cls(
            outcome="rejected",
            candidate_identity_sha256=(candidate.identity_sha256 if candidate else None),
            baseline_identity_sha256=(
                candidate.baseline.identity_sha256 if candidate else None
            ),
            patch_identity_sha256=(
                candidate.source_delta.identity_sha256 if candidate else None
            ),
            rejection_code=rejection_code,
        )

    @property
    def receipt_identity_sha256(self) -> str:
        """Stable receipt identity excluding transient worktree path/token data."""
        return _identity(
            {
                "schema_version": self.schema_version,
                "outcome": self.outcome,
                "candidate_identity_sha256": self.candidate_identity_sha256,
                "baseline_identity_sha256": self.baseline_identity_sha256,
                "patch_identity_sha256": self.patch_identity_sha256,
                "result_source_tree_sha256": self.result_source_tree_sha256,
                "result_diff_sha256": self.result_diff_sha256,
                "result_identity_sha256": self.result_identity_sha256,
                "rejection_code": self.rejection_code,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "outcome": self.outcome,
            "candidate_identity_sha256": self.candidate_identity_sha256,
            "baseline_identity_sha256": self.baseline_identity_sha256,
            "patch_identity_sha256": self.patch_identity_sha256,
            "result_source_tree_sha256": self.result_source_tree_sha256,
            "result_diff_sha256": self.result_diff_sha256,
            "result_identity_sha256": self.result_identity_sha256,
            "rejection_code": self.rejection_code,
            "receipt_identity_sha256": self.receipt_identity_sha256,
        }
        if self.worktree is not None:
            result["worktree"] = self.worktree.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "InjectionReceipt":
        if not isinstance(data, Mapping):
            raise InjectionContractError("receipt must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "outcome",
                "candidate_identity_sha256",
                "baseline_identity_sha256",
                "patch_identity_sha256",
                "result_source_tree_sha256",
                "result_diff_sha256",
                "result_identity_sha256",
                "rejection_code",
                "worktree",
                "receipt_identity_sha256",
            },
            "receipt",
        )
        try:
            raw_worktree = data.get("worktree")
            value = cls(
                outcome=data["outcome"],
                candidate_identity_sha256=data["candidate_identity_sha256"],
                baseline_identity_sha256=data["baseline_identity_sha256"],
                patch_identity_sha256=data["patch_identity_sha256"],
                result_source_tree_sha256=data["result_source_tree_sha256"],
                result_diff_sha256=data["result_diff_sha256"],
                result_identity_sha256=data["result_identity_sha256"],
                rejection_code=data["rejection_code"],
                worktree=(
                    MaterializedWorktree.from_dict(raw_worktree)
                    if raw_worktree is not None
                    else None
                ),
                schema_version=data["schema_version"],
            )
            if data["receipt_identity_sha256"] != value.receipt_identity_sha256:
                raise InjectionContractError("receipt identity digest does not match")
            return value
        except KeyError as error:
            raise InjectionContractError(
                f"receipt requires {error.args[0]}"
            ) from error


__all__ = [
    "BaselineProvenance",
    "FaultOperator",
    "InjectionCandidate",
    "InjectionContractError",
    "InjectionReceipt",
    "MaterializedWorktree",
    "SCHEMA_VERSION",
    "SourceDelta",
    "canonical_json_bytes",
    "result_identity_sha256",
    "sha256_hex",
]
