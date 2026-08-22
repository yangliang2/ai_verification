"""Immutable M0.2 catalog contracts for curated Injection Lab sources."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from aiverify.injection.models import (
    InjectionCandidate,
    InjectionContractError,
    SCHEMA_VERSION,
    canonical_json_bytes,
    sha256_hex,
)


class CuratedCatalogError(InjectionContractError):
    """A deterministic catalog rejection with a stable machine-readable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InjectionContractError(f"{field} must be a non-empty string")
    return value


def _reject_unknown(data: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise InjectionContractError(
            f"unknown {label} field(s): " + ", ".join(unknown)
        )


def _relative_path(value: object, field: str) -> str:
    path = _required_text(value, field)
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise InjectionContractError(f"{field} must be a safe relative path")
    return path


def _identity(value: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(value))


@dataclass(frozen=True)
class TaxonomyRelationship:
    """An explicit known or unknown relationship to the behavior taxonomy."""

    status: str
    taxonomy_id: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"known", "unknown"}:
            raise InjectionContractError(
                "taxonomy_relationship.status must be known or unknown"
            )
        if self.status == "known":
            _required_text(self.taxonomy_id, "known taxonomy_relationship taxonomy_id")
        if self.status == "unknown" and self.taxonomy_id is not None:
            raise InjectionContractError(
                "unknown taxonomy_relationship cannot name taxonomy_id"
            )

    @classmethod
    def known(cls, taxonomy_id: str) -> "TaxonomyRelationship":
        return cls(status="known", taxonomy_id=taxonomy_id)

    @classmethod
    def unknown(cls) -> "TaxonomyRelationship":
        return cls(status="unknown")

    def to_dict(self) -> dict[str, str | None]:
        return {"status": self.status, "taxonomy_id": self.taxonomy_id}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaxonomyRelationship":
        if not isinstance(data, Mapping):
            raise InjectionContractError("taxonomy_relationship must be an object")
        _reject_unknown(data, {"status", "taxonomy_id"}, "taxonomy_relationship")
        try:
            return cls(status=data["status"], taxonomy_id=data.get("taxonomy_id"))
        except KeyError as error:
            raise InjectionContractError(
                f"taxonomy_relationship requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class FixtureAnchor:
    """The checked-in fixture byte identity a curated source is anchored to."""

    path: str
    sha256: str

    def __post_init__(self) -> None:
        _relative_path(self.path, "fixture_anchor.path")
        if not isinstance(self.sha256, str) or len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise InjectionContractError(
                "fixture_anchor.sha256 must be a lowercase SHA-256 digest"
            )

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "sha256": self.sha256}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FixtureAnchor":
        if not isinstance(data, Mapping):
            raise InjectionContractError("fixture_anchor must be an object")
        _reject_unknown(data, {"path", "sha256"}, "fixture_anchor")
        try:
            return cls(path=data["path"], sha256=data["sha256"])
        except KeyError as error:
            raise InjectionContractError(
                f"fixture_anchor requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class CuratedSourceEntry:
    """One explicitly declared curated source and its audit-side identity."""

    source_id: str
    candidate: InjectionCandidate
    patch_path: str
    fixture_anchor: FixtureAnchor
    population_classification: str
    taxonomy_relationship: TaxonomyRelationship

    def __post_init__(self) -> None:
        _required_text(self.source_id, "catalog entry source_id")
        if not isinstance(self.candidate, InjectionCandidate):
            raise InjectionContractError("catalog entry candidate must be InjectionCandidate")
        _relative_path(self.patch_path, "catalog entry patch_path")
        if self.patch_path != self.candidate.source_delta.source_ref:
            raise InjectionContractError(
                "catalog entry patch_path must match candidate source_ref"
            )
        if self.population_classification != "curated_controlled_injection":
            raise InjectionContractError(
                "catalog entry population_classification must be curated_controlled_injection"
            )
        if not isinstance(self.fixture_anchor, FixtureAnchor):
            raise InjectionContractError("catalog entry fixture_anchor must be FixtureAnchor")
        if not isinstance(self.taxonomy_relationship, TaxonomyRelationship):
            raise InjectionContractError(
                "catalog entry taxonomy_relationship must be TaxonomyRelationship"
            )

    @property
    def patch_sha256(self) -> str:
        return self.candidate.source_delta.patch_sha256

    @property
    def identity_sha256(self) -> str:
        return _identity(self._identity_dict())

    def _identity_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "source_id": self.source_id,
            "candidate_identity_sha256": self.candidate.identity_sha256,
            "patch_path": self.patch_path,
            "patch_sha256": self.patch_sha256,
            "fixture_anchor": self.fixture_anchor.to_dict(),
            "population_classification": self.population_classification,
            "taxonomy_relationship": self.taxonomy_relationship.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "source_id": self.source_id,
            "candidate": self.candidate.to_dict(),
            "patch_path": self.patch_path,
            "patch_sha256": self.patch_sha256,
            "fixture_anchor": self.fixture_anchor.to_dict(),
            "population_classification": self.population_classification,
            "taxonomy_relationship": self.taxonomy_relationship.to_dict(),
            "identity_sha256": self.identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CuratedSourceEntry":
        if not isinstance(data, Mapping):
            raise InjectionContractError("catalog entry must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "source_id",
                "candidate",
                "patch_path",
                "patch_sha256",
                "fixture_anchor",
                "population_classification",
                "taxonomy_relationship",
                "identity_sha256",
            },
            "catalog entry",
        )
        try:
            if (
                not isinstance(data["schema_version"], int)
                or isinstance(data["schema_version"], bool)
                or data["schema_version"] != SCHEMA_VERSION
            ):
                raise InjectionContractError("unsupported catalog entry schema_version")
            candidate = InjectionCandidate.from_dict(data["candidate"])
            value = cls(
                source_id=data["source_id"],
                candidate=candidate,
                patch_path=data["patch_path"],
                fixture_anchor=FixtureAnchor.from_dict(data["fixture_anchor"]),
                population_classification=data["population_classification"],
                taxonomy_relationship=TaxonomyRelationship.from_dict(
                    data["taxonomy_relationship"]
                ),
            )
            if data["patch_sha256"] != value.patch_sha256:
                raise InjectionContractError("catalog entry patch digest does not match")
            if data["identity_sha256"] != value.identity_sha256:
                raise InjectionContractError("catalog entry identity digest does not match")
            return value
        except KeyError as error:
            raise InjectionContractError(
                f"catalog entry requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class CuratedSourceCatalog:
    """A deterministic collection of source entries eligible for M0 admission."""

    entries: tuple[CuratedSourceEntry, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple) or not self.entries:
            raise InjectionContractError("catalog must contain at least one entry")
        if not all(isinstance(entry, CuratedSourceEntry) for entry in self.entries):
            raise InjectionContractError("catalog entries must be CuratedSourceEntry")
        source_ids = tuple(entry.source_id for entry in self.entries)
        if len(set(source_ids)) != len(source_ids):
            raise InjectionContractError("catalog contains duplicate source_id")
        candidate_ids = tuple(entry.candidate.candidate_id for entry in self.entries)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise InjectionContractError("catalog contains duplicate candidate_id")
        patch_digests = tuple(entry.patch_sha256 for entry in self.entries)
        if len(set(patch_digests)) != len(patch_digests):
            raise InjectionContractError("catalog contains duplicate patch_sha256")
        object.__setattr__(self, "entries", tuple(sorted(self.entries, key=lambda entry: entry.source_id)))

    @property
    def identity_sha256(self) -> str:
        return _identity(
            {
                "schema_version": SCHEMA_VERSION,
                "entries": [entry.identity_sha256 for entry in self.entries],
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "entries": [entry.to_dict() for entry in self.entries],
            "identity_sha256": self.identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CuratedSourceCatalog":
        if not isinstance(data, Mapping):
            raise InjectionContractError("catalog must be an object")
        _reject_unknown(
            data,
            {"schema_version", "entries", "identity_sha256"},
            "catalog",
        )
        try:
            if (
                not isinstance(data["schema_version"], int)
                or isinstance(data["schema_version"], bool)
                or data["schema_version"] != SCHEMA_VERSION
            ):
                raise InjectionContractError("unsupported catalog schema_version")
            entries = data["entries"]
            if not isinstance(entries, list):
                raise InjectionContractError("catalog entries must be an array")
            value = cls(entries=tuple(CuratedSourceEntry.from_dict(entry) for entry in entries))
            if data["identity_sha256"] != value.identity_sha256:
                raise InjectionContractError("catalog identity digest does not match")
            return value
        except KeyError as error:
            raise InjectionContractError(f"catalog requires {error.args[0]}") from error

    def select(self, source_id: str) -> CuratedSourceEntry:
        for entry in self.entries:
            if entry.source_id == source_id:
                return entry
        raise InjectionContractError("catalog source_id is not declared")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CuratedCatalogError("catalog_duplicate_json_key")
        result[key] = value
    return result


def _catalog_error_code(error: InjectionContractError) -> str:
    message = str(error)
    if "duplicate source_id" in message:
        return "catalog_duplicate_source_id"
    if "duplicate candidate_id" in message:
        return "catalog_duplicate_candidate_id"
    if "duplicate patch_sha256" in message:
        return "catalog_duplicate_patch_sha256"
    if "baseline" in message or "candidate" in message:
        return "catalog_invalid_provenance"
    return "catalog_contract_invalid"


def _declared_file(root: Path, relative_path: str, missing_code: str) -> Path:
    path = root.joinpath(*PurePosixPath(relative_path).parts)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        raise CuratedCatalogError(missing_code) from None
    if not resolved.is_file():
        raise CuratedCatalogError(missing_code)
    return resolved


def load_curated_source_catalog(path: str | Path) -> CuratedSourceCatalog:
    """Load a checked-in catalog and bind each declared source to local bytes."""
    catalog_path = Path(path)
    try:
        raw_catalog = catalog_path.read_bytes()
    except OSError:
        raise CuratedCatalogError("catalog_file_unavailable") from None
    try:
        parsed = json.loads(raw_catalog, object_pairs_hook=_reject_duplicate_json_keys)
    except CuratedCatalogError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CuratedCatalogError("catalog_json_invalid") from None
    try:
        catalog = CuratedSourceCatalog.from_dict(parsed)
    except InjectionContractError as error:
        raise CuratedCatalogError(_catalog_error_code(error)) from error

    root = catalog_path.resolve().parent
    for entry in catalog.entries:
        patch = _declared_file(root, entry.patch_path, "catalog_patch_missing")
        if patch.read_bytes() != entry.candidate.source_delta.patch_text.encode("utf-8"):
            raise CuratedCatalogError("catalog_patch_drift")
        fixture = _declared_file(
            root,
            entry.fixture_anchor.path,
            "catalog_fixture_anchor_missing",
        )
        if sha256_hex(fixture.read_bytes()) != entry.fixture_anchor.sha256:
            raise CuratedCatalogError("catalog_fixture_anchor_drift")
    return catalog
