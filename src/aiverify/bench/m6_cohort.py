"""Fail-closed loader and validator for the M6 qualification cohort."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

import yaml
from jsonschema import Draft202012Validator, FormatChecker


_SCHEMA_PATH = Path(__file__).with_name("m6_cohort_schema.json")
_EXPECTED_SLOT_IDS = frozenset(
    {"H-01", "H-02", "H-03", "P-01", "P-02", "P-03"}
)
_REQUIRED_FAILURE_ROUTES = frozenset(
    {"fixture", "execution", "oracle", "adjudication"}
)
_REQUIRED_HISTORICAL_CLAIMS = frozenset(
    {
        "matched_fail_pass_observations",
        "local_conclusions",
        "accountability",
        "operational_metrics",
    }
)
_REQUIRED_PROSPECTIVE_CLAIMS = frozenset(
    {
        "blinded_case_observations",
        "local_conclusions",
        "adjudication_agreement",
        "accountability",
        "operational_metrics",
    }
)
_REQUIRED_FORBIDDEN_CLAIMS = frozenset(
    {
        "combined_track_denominator",
        "detection_rate",
        "false_positive_rate",
        "confidence_claim",
        "prospective_goldset",
        "general_android_coverage",
        "upstream_acceptance",
    }
)
_CLAIM_LEAKAGE_TERMS = (
    "combined_track",
    "detection_rate",
    "false_positive_rate",
    "confidence",
    "goldset",
    "general_android",
    "upstream_acceptance",
    "benchmark_wide",
)


class CohortValidationError(ValueError):
    """One or more cohort checks failed."""

    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(errors)
        detail = "\n".join(f"- {error}" for error in self.errors)
        super().__init__(f"M6 cohort manifest is invalid:\n{detail}")


@dataclass(frozen=True)
class QualificationCohortManifest:
    """Validated manifest plus the exact consumed source identity."""

    source_path: Path
    source_sha256: str
    canonical_sha256: str
    document: Mapping[str, Any]

    @property
    def cohort_id(self) -> str:
        return str(self.document["cohort_id"])

    @property
    def status(self) -> str:
        return str(self.document["status"])

    @property
    def slots(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.document["slots"])

    def summary(self) -> dict[str, Any]:
        track_counts = Counter(str(slot["track"]) for slot in self.slots)
        families = sorted({str(slot["risk_family"]) for slot in self.slots})
        planned_lanes = sum(
            int(slot["repetitions"]["baseline"])
            + int(slot["repetitions"]["candidate"])
            for slot in self.slots
        )
        return {
            "schema_version": self.document["schema_version"],
            "cohort_id": self.cohort_id,
            "status": self.status,
            "source_path": self.source_path.as_posix(),
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "slots": len(self.slots),
            "historical_slots": track_counts["historical"],
            "prospective_slots": track_counts["prospective"],
            "risk_families": families,
            "planned_lanes": planned_lanes,
            "replacement_candidates": len(self.document["replacement_pool"]),
            "replacement_events": len(self.document["replacement_events"]),
            "formal_invocations_started": len(
                self.document["execution_state"]["formal_invocations_started"]
            ),
        }


class _UniqueKeyLoader(yaml.SafeLoader):
    """YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as error:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from error
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_schema() -> dict[str, Any]:
    """Load the packaged Draft 2020-12 schema."""
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def self_validate_schema() -> None:
    """Raise when the packaged schema is not itself a valid JSON Schema."""
    Draft202012Validator.check_schema(load_schema())


def load_cohort_manifest(
    path: str | Path,
    *,
    repo_root: str | Path | None = None,
    require_frozen: bool = True,
    verify_references: bool = True,
) -> QualificationCohortManifest:
    """Load and fully validate one M6 qualification cohort manifest."""
    source_path = Path(path).resolve()
    try:
        raw = source_path.read_bytes()
    except OSError as error:
        raise CohortValidationError(
            [f"manifest cannot be read: {source_path}: {error}"]
        ) from error
    try:
        document = yaml.load(raw.decode("utf-8"), Loader=_UniqueKeyLoader)
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        raise CohortValidationError([f"manifest is not valid UTF-8 YAML: {error}"]) from error
    if not isinstance(document, dict):
        raise CohortValidationError(["manifest root must be an object"])

    self_validate_schema()
    schema_errors = sorted(
        Draft202012Validator(
            load_schema(),
            format_checker=FormatChecker(),
        ).iter_errors(document),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.message,
        ),
    )
    if schema_errors:
        raise CohortValidationError(
            [_render_schema_error(error) for error in schema_errors]
        )

    root = (
        Path(repo_root).resolve()
        if repo_root is not None
        else _find_repository_root(source_path)
    )
    try:
        source_path.relative_to(root)
    except ValueError as error:
        raise CohortValidationError(
            ["manifest source must be located inside the repository root"]
        ) from error
    semantic_errors = _semantic_errors(
        document,
        repo_root=root,
        require_frozen=require_frozen,
        verify_references=verify_references,
    )
    if semantic_errors:
        raise CohortValidationError(semantic_errors)

    canonical = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return QualificationCohortManifest(
        source_path=source_path,
        source_sha256=sha256(raw).hexdigest(),
        canonical_sha256=sha256(canonical).hexdigest(),
        document=document,
    )


def _render_schema_error(error: Any) -> str:
    path = ".".join(str(part) for part in error.absolute_path) or "<root>"
    return f"schema {path}: {error.message}"


def _find_repository_root(source_path: Path) -> Path:
    for parent in (source_path.parent, *source_path.parents):
        if (parent / "pyproject.toml").is_file() and (parent / ".git").exists():
            return parent.resolve()
    raise CohortValidationError(
        [
            "repository root could not be inferred; pass --repo-root "
            "or place the manifest inside the repository"
        ]
    )


def _semantic_errors(
    document: dict[str, Any],
    *,
    repo_root: Path,
    require_frozen: bool,
    verify_references: bool,
) -> list[str]:
    errors: list[str] = []
    status = document["status"]
    frozen_at = document["frozen_at"]
    approval = document["maintainer_approval"]
    if require_frozen and status != "frozen":
        errors.append("status must be frozen for formal consumption")
    if status == "frozen":
        if frozen_at is None:
            errors.append("frozen manifest requires frozen_at")
        if approval is None:
            errors.append("frozen manifest requires maintainer_approval")
        if frozen_at is not None and approval is not None:
            if _parse_datetime(approval["approved_at"]) > _parse_datetime(frozen_at):
                errors.append("maintainer approval cannot occur after frozen_at")
    elif frozen_at is not None or approval is not None:
        errors.append("draft manifest must not claim frozen_at or maintainer approval")

    slots = document["slots"]
    slot_ids = [str(slot["id"]) for slot in slots]
    if len(set(slot_ids)) != len(slot_ids):
        errors.append("slot ids must be unique")
    if set(slot_ids) != _EXPECTED_SLOT_IDS:
        errors.append(
            "slot ids must be exactly H-01..H-03 and P-01..P-03"
        )
    for slot in slots:
        expected_prefix = "H-" if slot["track"] == "historical" else "P-"
        if not str(slot["id"]).startswith(expected_prefix):
            errors.append(
                f"slot {slot['id']} id prefix contradicts track {slot['track']}"
            )

    track_counts = Counter(str(slot["track"]) for slot in slots)
    if track_counts != Counter({"historical": 3, "prospective": 3}):
        errors.append("cohort must contain exactly three slots in each track")
    families = {str(slot["risk_family"]) for slot in slots}
    if len(families) < 4:
        errors.append("six admitted slots must cover at least four risk families")

    planned_lanes = sum(
        int(slot["repetitions"]["baseline"])
        + int(slot["repetitions"]["candidate"])
        for slot in slots
    )
    if planned_lanes != document["policy"]["formal_lanes"]["planned_lanes"]:
        errors.append("slot repetitions must total the frozen 36-lane plan")

    errors.extend(
        _slot_admission_errors(
            slots,
            document["policy"],
            frozen_at=frozen_at,
        )
    )
    errors.extend(_claim_errors(document["policy"]))
    errors.extend(_identity_errors(document))
    errors.extend(_replacement_errors(document))
    errors.extend(_invocation_errors(document))
    errors.extend(
        _reference_errors(
            document,
            repo_root=repo_root,
            verify_references=verify_references,
        )
    )
    return sorted(set(errors))


def _slot_admission_errors(
    slots: list[dict[str, Any]],
    policy: dict[str, Any],
    *,
    frozen_at: str | None,
) -> list[str]:
    errors: list[str] = []
    expected_network = policy["blinding"]["verifier_network_policy"]
    for slot in slots:
        slot_id = slot["id"]
        task_id = (
            slot["historical"]["upstream_task_id"]
            if slot["track"] == "historical"
            else slot["prospective"]["upstream_task_id"]
        )
        if not _task_url_matches_id(slot["source"]["task_url"], task_id):
            errors.append(f"slot {slot_id} task URL does not match {task_id}")
        if (
            frozen_at is not None
            and _parse_datetime(slot["admission"]["admitted_at"])
            > _parse_datetime(frozen_at)
        ):
            errors.append(f"slot {slot_id} admission cannot occur after frozen_at")
        if slot["track"] == "historical":
            admission = slot["historical"]
            if slot["source"]["base_revision"] != admission["pre_fix_revision"]:
                errors.append(
                    f"slot {slot_id} base revision must equal exact pre-fix revision"
                )
            if admission["pre_fix_revision"] == admission["fixed_revision"]:
                errors.append(
                    f"slot {slot_id} pre-fix and fixed revisions must differ"
                )
        else:
            admission = slot["prospective"]
            if admission["verifier_network_policy"] != expected_network:
                errors.append(
                    f"slot {slot_id} verifier network policy contradicts cohort policy"
                )
    return errors


def _task_url_matches_id(task_url: str, task_id: str) -> bool:
    expected = task_id.removeprefix("T")
    parsed = urlparse(task_url)
    path_parts = [part for part in parsed.path.rstrip("/").split("/") if part]
    return bool(path_parts) and path_parts[-1].removeprefix("T") == expected


def _claim_errors(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    claims = policy["claims"]
    historical = set(claims["historical_allowed"])
    prospective = set(claims["prospective_allowed"])
    forbidden = set(claims["forbidden"])
    missing_historical = sorted(_REQUIRED_HISTORICAL_CLAIMS - historical)
    missing_prospective = sorted(_REQUIRED_PROSPECTIVE_CLAIMS - prospective)
    missing_forbidden = sorted(_REQUIRED_FORBIDDEN_CLAIMS - forbidden)
    if missing_historical:
        errors.append(
            "historical claim boundary is missing: "
            + ", ".join(missing_historical)
        )
    if missing_prospective:
        errors.append(
            "prospective claim boundary is missing: "
            + ", ".join(missing_prospective)
        )
    if missing_forbidden:
        errors.append(
            "forbidden claim boundary is missing: " + ", ".join(missing_forbidden)
        )
    leaked = sorted(
        claim
        for claim in historical | prospective
        if claim in forbidden
        or any(term in claim.lower() for term in _CLAIM_LEAKAGE_TERMS)
    )
    if leaked:
        errors.append("allowed claim lists leak forbidden claims: " + ", ".join(leaked))
    if historical == prospective:
        errors.append("historical and prospective claim contracts must remain distinct")
    failure_routes = set(policy["failure_routes"])
    missing_routes = sorted(_REQUIRED_FAILURE_ROUTES - failure_routes)
    if missing_routes:
        errors.append(
            "failure routing is missing: " + ", ".join(missing_routes)
        )
    return errors


def _identity_errors(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    slots = document["slots"]
    pool = document["replacement_pool"]
    events_by_candidate = {
        event["candidate_id"]: event for event in document["replacement_events"]
    }

    _append_duplicate_errors(
        errors,
        "admitted task identity",
        [
            (slot["source"]["repository_url"], slot["source"]["task_url"])
            for slot in slots
        ],
    )
    _append_duplicate_errors(
        errors,
        "replacement candidate id",
        [candidate["candidate_id"] for candidate in pool],
    )
    _append_duplicate_errors(
        errors,
        "replacement task identity",
        [
            (
                candidate["source"]["repository_url"],
                candidate["source"]["task_url"],
            )
            for candidate in pool
        ],
    )
    _append_duplicate_errors(
        errors,
        "exclusion candidate id",
        [exclusion["candidate_id"] for exclusion in document["exclusions"]],
    )

    slot_identity = {
        (slot["source"]["repository_url"], slot["source"]["task_url"]): slot
        for slot in slots
    }
    for exclusion in document["exclusions"]:
        identity = (
            exclusion["source"]["repository_url"],
            exclusion["source"]["task_url"],
        )
        admitted = slot_identity.get(identity)
        if admitted is not None:
            errors.append(
                f"exclusion {exclusion['candidate_id']} overlaps admitted "
                f"slot {admitted['id']}"
            )
    for candidate in pool:
        identity = (
            candidate["source"]["repository_url"],
            candidate["source"]["task_url"],
        )
        admitted = slot_identity.get(identity)
        if admitted is None:
            continue
        event = events_by_candidate.get(candidate["candidate_id"])
        if event is None or event["slot_id"] != admitted["id"]:
            errors.append(
                f"replacement {candidate['candidate_id']} overlaps admitted "
                "task identity without a matching replacement event"
            )

    admitted_task_ids = {
        (
            slot["historical"]["upstream_task_id"]
            if slot["track"] == "historical"
            else slot["prospective"]["upstream_task_id"]
        )
        for slot in slots
    }
    for candidate in pool:
        candidate_task_id = _task_id_from_url(candidate["source"]["task_url"])
        if candidate_task_id in admitted_task_ids:
            event = events_by_candidate.get(candidate["candidate_id"])
            if event is None:
                errors.append(
                    f"replacement {candidate['candidate_id']} overlaps admitted "
                    f"task id {candidate_task_id}"
                )
    return errors


def _append_duplicate_errors(
    errors: list[str], label: str, values: Iterable[Any]
) -> None:
    counts = Counter(values)
    duplicates = sorted(repr(value) for value, count in counts.items() if count > 1)
    if duplicates:
        errors.append(f"duplicate {label}: " + ", ".join(duplicates))


def _task_id_from_url(task_url: str) -> str | None:
    last = urlparse(task_url).path.rstrip("/").rsplit("/", 1)[-1]
    normalized = last if last.startswith("T") else f"T{last}"
    return normalized if normalized[1:].isdigit() else None


def _replacement_errors(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    slots = {slot["id"]: slot for slot in document["slots"]}
    candidates = {
        candidate["candidate_id"]: candidate
        for candidate in document["replacement_pool"]
    }
    exclusions = {
        exclusion["candidate_id"]: exclusion
        for exclusion in document["exclusions"]
    }
    invocations = document["execution_state"]["formal_invocations_started"]
    frozen_at = (
        _parse_datetime(document["frozen_at"])
        if document["frozen_at"] is not None
        else None
    )

    ranks: dict[str, list[int]] = {"historical": [], "prospective": []}
    for candidate in candidates.values():
        ranks[candidate["track"]].append(candidate["rank"])
        expected_prefix = "H-" if candidate["track"] == "historical" else "P-"
        if not candidate["candidate_id"].startswith(expected_prefix):
            errors.append(
                f"replacement {candidate['candidate_id']} id prefix contradicts "
                f"track {candidate['track']}"
            )
        if candidate["track"] == "historical":
            pair = candidate["historical"]
            if candidate["source"]["base_revision"] != pair["pre_fix_revision"]:
                errors.append(
                    f"replacement {candidate['candidate_id']} base revision must "
                    "equal exact pre-fix revision"
                )
            if pair["pre_fix_revision"] == pair["fixed_revision"]:
                errors.append(
                    f"replacement {candidate['candidate_id']} revisions must differ"
                )
    for track, observed in ranks.items():
        if not observed:
            errors.append(f"replacement pool must include a {track} candidate")
        elif sorted(observed) != list(range(1, len(observed) + 1)):
            errors.append(f"{track} replacement ranks must be contiguous from 1")

    for exclusion in exclusions.values():
        expected_prefix = "H-" if exclusion["track"] == "historical" else "P-"
        if not exclusion["candidate_id"].startswith(expected_prefix):
            errors.append(
                f"exclusion {exclusion['candidate_id']} id prefix contradicts "
                f"track {exclusion['track']}"
            )

    seen_slots: set[str] = set()
    seen_candidates: set[str] = set()
    for event in document["replacement_events"]:
        slot = slots.get(event["slot_id"])
        candidate = candidates.get(event["candidate_id"])
        exclusion = exclusions.get(event["replaced_candidate_id"])
        if slot is None:
            errors.append(f"replacement event names unknown slot {event['slot_id']}")
            continue
        if candidate is None:
            errors.append(
                f"replacement event names unregistered candidate "
                f"{event['candidate_id']}"
            )
            continue
        if exclusion is None:
            errors.append(
                f"replacement event lacks exclusion ledger entry "
                f"{event['replaced_candidate_id']}"
            )
        elif exclusion["track"] != slot["track"]:
            errors.append(
                f"replacement event exclusion track contradicts slot {slot['id']}"
            )
        else:
            if exclusion["candidate_id"] == candidate["candidate_id"]:
                errors.append(
                    f"replacement candidate {candidate['candidate_id']} is also excluded"
                )
            if exclusion["evidence"] != event["exclusion_evidence"]:
                errors.append(
                    f"replacement event for slot {slot['id']} does not bind the "
                    "exclusion ledger checksum"
                )
            if _parse_datetime(exclusion["excluded_at"]) > _parse_datetime(
                event["occurred_at"]
            ):
                errors.append(
                    f"replacement event for slot {slot['id']} predates exclusion"
                )
        if candidate["track"] != slot["track"]:
            errors.append(
                f"replacement {candidate['candidate_id']} cannot cross tracks "
                f"into slot {slot['id']}"
            )
        if (
            candidate["source"]["repository_url"],
            candidate["source"]["task_url"],
        ) != (
            slot["source"]["repository_url"],
            slot["source"]["task_url"],
        ):
            errors.append(
                f"slot {slot['id']} does not carry replacement "
                f"{candidate['candidate_id']} source identity"
            )
        if event["slot_id"] in seen_slots:
            errors.append(f"slot {event['slot_id']} has multiple replacement events")
        if event["candidate_id"] in seen_candidates:
            errors.append(
                f"candidate {event['candidate_id']} is used by multiple events"
            )
        seen_slots.add(event["slot_id"])
        seen_candidates.add(event["candidate_id"])

        event_at = _parse_datetime(event["occurred_at"])
        if frozen_at is not None and event_at > frozen_at:
            errors.append(
                f"replacement event for slot {slot['id']} cannot occur after frozen_at"
            )
        earlier_candidates = [
            earlier
            for earlier in candidates.values()
            if earlier["track"] == candidate["track"]
            and earlier["rank"] < candidate["rank"]
        ]
        # A ranked replacement can be admitted into an earlier slot while a
        # later slot is still waiting for the next candidate. Such a consumed
        # candidate is no longer an available fallback, but it is not an
        # exclusion either. Keep it in the ledger as an earlier admission so a
        # single ordered pool can fill multiple slots without falsely failing
        # the "all earlier candidates must be accounted for" check.
        consumed_before_event = {
            earlier_event["candidate_id"]
            for earlier_event in document["replacement_events"]
            if earlier_event is not event
            and _parse_datetime(earlier_event["occurred_at"]) < event_at
        }
        missing_prior_exclusions = sorted(
            earlier["candidate_id"]
            for earlier in earlier_candidates
            if earlier["candidate_id"] not in exclusions
            and earlier["candidate_id"] not in consumed_before_event
        )
        if missing_prior_exclusions:
            errors.append(
                f"replacement {candidate['candidate_id']} skips unexcluded "
                "earlier candidates: "
                + ", ".join(missing_prior_exclusions)
            )
        for invocation in invocations:
            if (
                invocation["slot_id"] == event["slot_id"]
                and event_at >= _parse_datetime(invocation["started_at"])
            ):
                errors.append(
                    f"replacement for slot {event['slot_id']} occurred at or after "
                    "its first formal invocation"
                )
    return errors


def _invocation_errors(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    slots = {slot["id"] for slot in document["slots"]}
    invocations = document["execution_state"]["formal_invocations_started"]
    _append_duplicate_errors(
        errors,
        "formal lane id",
        [invocation["lane_id"] for invocation in invocations],
    )
    frozen_at = (
        _parse_datetime(document["frozen_at"])
        if document["frozen_at"] is not None
        else None
    )
    if frozen_at is None and invocations:
        errors.append("draft cohort cannot have formal invocations")
    for invocation in invocations:
        if invocation["slot_id"] not in slots:
            errors.append(
                f"formal invocation names unknown slot {invocation['slot_id']}"
            )
        if (
            frozen_at is not None
            and _parse_datetime(invocation["started_at"]) < frozen_at
        ):
            errors.append(
                f"formal invocation {invocation['lane_id']} predates cohort freeze"
            )
    return errors


def _reference_errors(
    document: dict[str, Any],
    *,
    repo_root: Path,
    verify_references: bool,
) -> list[str]:
    errors: list[str] = []
    artifact_refs = list(_artifact_refs(document))
    for label, reference in artifact_refs:
        resolved = _resolve_repo_path(
            reference["path"],
            repo_root=repo_root,
            label=label,
            errors=errors,
        )
        if resolved is None or not verify_references:
            continue
        if not resolved.is_file():
            errors.append(f"{label} artifact does not exist: {reference['path']}")
            continue
        actual = _sha256_file(resolved)
        if actual != reference["sha256"]:
            errors.append(
                f"{label} checksum mismatch for {reference['path']}: "
                f"expected {reference['sha256']}, got {actual}"
            )

    path_only_refs: list[tuple[str, str, bool]] = []
    for slot in document["slots"]:
        path_only_refs.append(
            (f"slot {slot['id']} evidence_root", slot["evidence_root"], False)
        )
    for candidate in document["replacement_pool"]:
        path_only_refs.append(
            (
                f"replacement {candidate['candidate_id']} preliminary_fixture",
                candidate["preliminary_fixture"],
                True,
            )
        )
    for label, value, must_exist in path_only_refs:
        resolved = _resolve_repo_path(
            value,
            repo_root=repo_root,
            label=label,
            errors=errors,
        )
        if (
            resolved is not None
            and verify_references
            and must_exist
            and not resolved.exists()
        ):
            errors.append(f"{label} does not exist: {value}")
    return errors


def _artifact_refs(
    value: Any, *, path: tuple[str, ...] = ()
) -> Iterable[tuple[str, dict[str, str]]]:
    if isinstance(value, dict):
        if set(value) == {"path", "sha256"}:
            yield (".".join(path), value)
            return
        for key, child in value.items():
            yield from _artifact_refs(child, path=(*path, str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _artifact_refs(child, path=(*path, str(index)))


def _resolve_repo_path(
    value: str,
    *,
    repo_root: Path,
    label: str,
    errors: list[str],
) -> Path | None:
    if "\\" in value:
        errors.append(f"{label} must use repository-relative POSIX path syntax")
        return None
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or "." in relative.parts
        or relative.as_posix() != value
    ):
        errors.append(f"{label} must be a normalized repository-relative path")
        return None
    resolved = (repo_root / Path(*relative.parts)).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        errors.append(f"{label} resolves outside the repository")
        return None
    return resolved


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate an M6 qualification cohort manifest."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument(
        "--allow-draft",
        action="store_true",
        help="validate a draft without authorizing formal consumption",
    )
    parser.add_argument(
        "--no-verify-references",
        action="store_true",
        help="validate reference syntax without reading referenced files",
    )
    args = parser.parse_args(argv)
    try:
        manifest = load_cohort_manifest(
            args.manifest,
            repo_root=args.repo_root,
            require_frozen=not args.allow_draft,
            verify_references=not args.no_verify_references,
        )
    except CohortValidationError as error:
        print(
            json.dumps(
                {"status": "invalid", "errors": list(error.errors)},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    summary = manifest.summary()
    summary["manifest_status"] = summary.pop("status")
    print(
        json.dumps(
            {"status": "valid", **summary},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
