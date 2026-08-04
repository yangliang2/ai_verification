"""Fail-closed M6 Qualification Case Package validation and aggregation.

The package is deliberately a thin envelope around the existing runner,
ExecutionRecord, effective-identity, and oracle artifacts.  It does not
reinterpret an oracle result; it only checks that the result is bound to the
attempt and to the frozen cohort slot that claims it.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker

from aiverify.bench.m6_cohort import (
    QualificationCohortManifest,
    load_cohort_manifest,
)
from aiverify.runner.execution_record import (
    ExecutionRecordValidationError,
    load_execution_record,
)


_SCHEMA_PATH = Path(__file__).with_name("m6_case_package_schema.json")
_REQUIRED_FORBIDDEN = frozenset(
    {
        "detection_rate",
        "false_positive_rate",
        "confidence_claim",
        "prospective_goldset",
        "general_android_coverage",
        "upstream_acceptance",
    }
)
_FORBIDDEN_TERMS = (
    "detection_rate",
    "false_positive_rate",
    "confidence",
    "goldset",
    "general_android",
    "upstream_acceptance",
)
_CONCLUSION_TO_OUTCOME = {
    "locally_supported": "pass",
    "locally_rejected": "fail",
    "inconclusive": "inconclusive",
}


class CasePackageValidationError(ValueError):
    """One or more package or aggregate checks failed."""

    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(dict.fromkeys(str(error) for error in errors))
        detail = "\n".join(f"- {error}" for error in self.errors)
        super().__init__(f"M6 qualification case package is invalid:\n{detail}")


@dataclass(frozen=True)
class QualificationAttemptInventory:
    """Validated append-only attempt inventory exposed as a small value object."""

    document: Mapping[str, Any]

    @property
    def attempts(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.document["attempts"])

    @property
    def ledger(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.document["ledger"])

    @property
    def discovered_attempt_ids(self) -> tuple[str, ...]:
        return tuple(self.document["discovered_attempt_ids"])


@dataclass(frozen=True)
class QualificationCasePackage:
    """A validated package and the exact bytes consumed to validate it."""

    source_path: Path
    source_sha256: str
    canonical_sha256: str
    document: Mapping[str, Any]

    @property
    def package_id(self) -> str:
        return str(self.document["package_id"])

    @property
    def cohort_id(self) -> str:
        return str(self.document["cohort"]["cohort_id"])

    @property
    def slot_id(self) -> str:
        return str(self.document["cohort"]["slot_id"])

    @property
    def track(self) -> str:
        return str(self.document["cohort"]["track"])

    @property
    def conclusion(self) -> str:
        return str(self.document["verification"]["conclusion"])

    @property
    def attempts(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.document["attempt_inventory"]["attempts"])

    @property
    def attempt_inventory(self) -> QualificationAttemptInventory:
        return QualificationAttemptInventory(self.document["attempt_inventory"])


@dataclass(frozen=True)
class QualificationAggregate:
    """Validated six-slot aggregate with separate track summaries."""

    manifest: QualificationCohortManifest
    packages: tuple[QualificationCasePackage, ...]
    historical: Mapping[str, Any]
    prospective: Mapping[str, Any]

    @property
    def package_ids(self) -> tuple[str, ...]:
        return tuple(package.package_id for package in self.packages)

    def to_dict(self) -> dict[str, Any]:
        """Return the stable structured report model."""
        return {
            "schema_version": 1,
            "cohort": {
                "cohort_id": self.manifest.cohort_id,
                "manifest_path": _repo_relative(
                    self.manifest.source_path,
                    _infer_root(self.manifest.source_path),
                ),
                "manifest_sha256": self.manifest.source_sha256,
                "slot_count": len(self.packages),
            },
            "packages": [
                {
                    "package_id": package.package_id,
                    "slot_id": package.slot_id,
                    "track": package.track,
                    "conclusion": package.conclusion,
                    "source_sha256": package.source_sha256,
                    "canonical_sha256": package.canonical_sha256,
                }
                for package in sorted(self.packages, key=lambda item: item.slot_id)
            ],
            "historical": dict(self.historical),
            "prospective": dict(self.prospective),
            "claim_boundary": {"local_only": True},
        }

    def summary(self) -> dict[str, Any]:
        """Alias used by callers that treat aggregates like other bench reports."""
        return self.to_dict()


class _DuplicateKeyError(ValueError):
    pass


def _unique_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_schema() -> dict[str, Any]:
    """Load the packaged Draft 2020-12 case-package schema."""
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def self_validate_schema() -> None:
    """Raise if the package schema is not itself a valid JSON Schema."""
    Draft202012Validator.check_schema(load_schema())


def load_case_package(
    path: str | Path,
    *,
    repo_root: str | Path | None = None,
    verify_references: bool = True,
) -> QualificationCasePackage:
    """Load and semantically validate one package.

    ``verify_references=False`` still validates all paths and cross-field
    identity, but is useful for a planning/lint pass before large artifacts are
    copied into a run record.
    """
    source_path = Path(path).resolve()
    try:
        raw = source_path.read_bytes()
    except OSError as error:
        raise CasePackageValidationError(
            [f"package cannot be read: {source_path}: {error}"]
        ) from error
    try:
        document = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_object_pairs
        )
    except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateKeyError) as error:
        raise CasePackageValidationError(
            [f"package is not valid UTF-8 JSON: {error}"]
        ) from error
    if not isinstance(document, dict):
        raise CasePackageValidationError(["package root must be an object"])

    self_validate_schema()
    schema_errors = sorted(
        Draft202012Validator(
            load_schema(), format_checker=FormatChecker()
        ).iter_errors(document),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.message,
        ),
    )
    if schema_errors:
        raise CasePackageValidationError(
            [_render_schema_error(error) for error in schema_errors]
        )

    root = (
        Path(repo_root).resolve()
        if repo_root is not None
        else _infer_root(source_path)
    )
    errors = _semantic_errors(
        document,
        repo_root=root,
        verify_references=verify_references,
    )
    if errors:
        raise CasePackageValidationError(errors)
    canonical = json.dumps(
        document, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return QualificationCasePackage(
        source_path=source_path,
        source_sha256=sha256(raw).hexdigest(),
        canonical_sha256=sha256(canonical).hexdigest(),
        document=document,
    )


def aggregate_packages(
    package_paths: Sequence[str | Path],
    *,
    manifest_path: str | Path,
    repo_root: str | Path | None = None,
    verify_references: bool = True,
) -> QualificationAggregate:
    """Validate exactly the frozen six slots and derive separate summaries."""
    manifest_file = Path(manifest_path).resolve()
    root = Path(repo_root).resolve() if repo_root is not None else _infer_root(manifest_file)
    errors: list[str] = []
    try:
        manifest = load_cohort_manifest(
            manifest_file,
            repo_root=root,
            require_frozen=True,
            verify_references=verify_references,
        )
    except ValueError as error:
        raise CasePackageValidationError([f"cohort manifest: {error}"]) from error

    packages: list[QualificationCasePackage] = []
    for package_path in package_paths:
        try:
            packages.append(
                load_case_package(
                    package_path,
                    repo_root=root,
                    verify_references=verify_references,
                )
            )
        except CasePackageValidationError as error:
            errors.extend(f"{Path(package_path)}: {item}" for item in error.errors)

    expected_slots = {str(slot["id"]): slot for slot in manifest.slots}
    observed_slots = [package.slot_id for package in packages]
    if len(packages) != len(expected_slots):
        errors.append(
            f"aggregate requires exactly {len(expected_slots)} packages; "
            f"got {len(packages)}"
        )
    if len(set(observed_slots)) != len(observed_slots):
        errors.append("aggregate package slots must be unique")
    if set(observed_slots) != set(expected_slots):
        errors.append(
            "aggregate slots must exactly match frozen manifest: "
            + ", ".join(sorted(set(expected_slots) ^ set(observed_slots)))
        )
    package_ids = [package.package_id for package in packages]
    if len(set(package_ids)) != len(package_ids):
        errors.append("aggregate package ids must be unique")

    for package in packages:
        slot = expected_slots.get(package.slot_id)
        if slot is None:
            continue
        if package.cohort_id != manifest.cohort_id:
            errors.append(
                f"package {package.package_id} cohort id contradicts frozen manifest"
            )
        expected_track = str(slot["track"])
        if package.track != expected_track:
            errors.append(
                f"package {package.package_id} track {package.track} contradicts "
                f"slot {package.slot_id} track {expected_track}"
            )
        manifest_ref = package.document["cohort"]["manifest"]
        if manifest_ref["path"] != _repo_relative(manifest_file, root):
            errors.append(
                f"package {package.package_id} manifest path does not bind the "
                "aggregate manifest"
            )
        if manifest_ref["sha256"] != manifest.source_sha256:
            errors.append(
                f"package {package.package_id} manifest checksum does not bind "
                "the aggregate manifest"
            )
        source = package.document["source"]
        if source["repository_url"] != slot["source"]["repository_url"]:
            errors.append(f"package {package.package_id} repository identity differs from slot")
        if source["task_url"] != slot["source"]["task_url"]:
            errors.append(f"package {package.package_id} task identity differs from slot")
        if source["base_revision"] != slot["source"]["base_revision"]:
            errors.append(f"package {package.package_id} base revision differs from slot")
        if package.track == "historical":
            expected = slot["historical"]["fixed_revision"]
            if source["final_diff"]["revision"] != expected:
                errors.append(
                    f"package {package.package_id} historical final diff must bind "
                    "the frozen fixed revision"
                )
        # A replacement is a property of the frozen manifest.  Any package
        # claiming a different source identity is therefore an excluded-only or
        # post-start replacement, not a sixth slot.
        if source["final_diff"]["revision"] == source["base_revision"]:
            errors.append(f"package {package.package_id} final diff cannot equal base revision")

    if errors:
        raise CasePackageValidationError(errors)

    ordered = tuple(sorted(packages, key=lambda package: package.slot_id))
    return QualificationAggregate(
        manifest=manifest,
        packages=ordered,
        historical=_track_summary([p for p in ordered if p.track == "historical"]),
        prospective=_track_summary([p for p in ordered if p.track == "prospective"]),
    )


def render_structured(aggregate: QualificationAggregate) -> str:
    """Render the aggregate model as deterministic JSON."""
    payload = json.dumps(
        aggregate.to_dict(), ensure_ascii=False, indent=2, sort_keys=True
    )
    _assert_render_boundary(payload)
    return payload + "\n"


def render_markdown(aggregate: QualificationAggregate) -> str:
    """Render the same aggregate model as deterministic Markdown."""
    model = aggregate.to_dict()
    lines = [
        "# M6 Qualification Case Package Aggregate",
        "",
        f"Cohort: `{model['cohort']['cohort_id']}`",
        f"Manifest SHA-256: `{model['cohort']['manifest_sha256']}`",
        "",
        "The package is local-only and keeps historical and prospective tracks "
        "as separate populations.",
        "",
        "## Track summaries",
        "",
        "| Track | Cases | Attempts | Accountable attempts | Non-accountable attempts | Operational seconds |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for track in ("historical", "prospective"):
        summary = model[track]
        lines.append(
            f"| {track} | {summary['cases']} | {summary['attempts']} | "
            f"{summary['accountable_attempts']} | {summary['non_accountable_attempts']} | "
            f"{summary['operational_seconds']} |"
        )
    lines.extend(
        [
            "",
            "## Frozen slots",
            "",
            "| Slot | Track | Package | Conclusion |",
            "|---|---|---|---|",
        ]
    )
    for package in model["packages"]:
        lines.append(
            f"| {package['slot_id']} | {package['track']} | "
            f"`{package['package_id']}` | {package['conclusion']} |"
        )
    lines.extend(
        [
            "",
            "## Scope boundary",
            "",
            "Only the recorded local observations, accountability, adjudication, "
            "and operational timing are represented. No population-level or "
            "upstream conclusion is produced.",
            "",
        ]
    )
    rendered = "\n".join(lines)
    _assert_render_boundary(rendered)
    return rendered


def write_reports(
    aggregate: QualificationAggregate,
    json_path: str | Path,
    markdown_path: str | Path,
) -> tuple[Path, Path]:
    """Write both deterministic views, creating parent directories as needed."""
    json_target = Path(json_path)
    markdown_target = Path(markdown_path)
    json_target.parent.mkdir(parents=True, exist_ok=True)
    markdown_target.parent.mkdir(parents=True, exist_ok=True)
    json_target.write_text(render_structured(aggregate), encoding="utf-8")
    markdown_target.write_text(render_markdown(aggregate), encoding="utf-8")
    return json_target, markdown_target


def _semantic_errors(
    document: dict[str, Any], *, repo_root: Path, verify_references: bool
) -> list[str]:
    errors: list[str] = []
    errors.extend(_reference_errors(document, repo_root=repo_root, verify_references=verify_references))
    errors.extend(_cohort_and_source_errors(document, repo_root=repo_root, verify_references=verify_references))
    errors.extend(_historical_pair_errors(document))
    errors.extend(_identity_errors(document))
    errors.extend(_attempt_errors(document, repo_root=repo_root, verify_references=verify_references))
    errors.extend(_conclusion_errors(document, repo_root=repo_root, verify_references=verify_references))
    errors.extend(_claim_errors(document))
    return sorted(set(errors))


def _cohort_and_source_errors(
    document: dict[str, Any], *, repo_root: Path, verify_references: bool
) -> list[str]:
    errors: list[str] = []
    cohort_ref = document["cohort"]["manifest"]
    manifest_path = _resolve_repo_path(
        cohort_ref["path"], repo_root=repo_root, label="cohort.manifest", errors=errors
    )
    if manifest_path is None:
        return errors
    try:
        manifest = load_cohort_manifest(
            manifest_path,
            repo_root=repo_root,
            require_frozen=True,
            verify_references=verify_references,
        )
    except ValueError as error:
        errors.append(f"cohort manifest cannot be consumed: {error}")
        return errors
    if cohort_ref["sha256"] != manifest.source_sha256:
        errors.append("cohort manifest checksum does not match its source bytes")
    if document["cohort"]["cohort_id"] != manifest.cohort_id:
        errors.append("package cohort_id does not match the frozen manifest")
    slot = next(
        (item for item in manifest.slots if item["id"] == document["cohort"]["slot_id"]),
        None,
    )
    if slot is None:
        errors.append(f"package names unknown frozen slot {document['cohort']['slot_id']}")
        return errors
    if document["cohort"]["track"] != slot["track"]:
        errors.append("package track contradicts the frozen slot")
    if document["contract"]["primary_behavior"] != slot["primary_behavior"]:
        errors.append("contract primary behavior does not match frozen slot")
    source = document["source"]
    for key in ("repository_url", "task_url", "base_revision"):
        if source[key] != slot["source"][key]:
            errors.append(f"source.{key} does not match frozen slot")
    if not _task_url_matches_id(source["task_url"], _slot_task_id(slot)):
        errors.append("source task URL does not match frozen task identity")
    if source["final_diff"]["revision"] == source["base_revision"]:
        errors.append("final diff revision must differ from base revision")
    if document["cohort"]["track"] == "historical":
        if source["final_diff"]["revision"] != slot["historical"]["fixed_revision"]:
            errors.append("historical final diff revision does not match frozen fixed revision")
    return errors


def _identity_errors(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    identity = document["execution_identity"]
    if not _meaningful(identity["host"].get("id")):
        errors.append("execution host identity is empty")
    if not _meaningful(identity["host"].get("os")):
        errors.append("execution host OS identity is empty")
    if not _meaningful_mapping(identity["tools"]):
        errors.append("tool identity is empty")
    for name, value in (
        ("backend name", identity["backend"].get("name")),
        ("backend version", identity["backend"].get("version")),
        ("backend model", identity["backend"].get("model")),
        ("deployment package", identity["deployment"].get("package")),
        ("deployment activity", identity["deployment"].get("activity")),
        ("device serial", identity["device"].get("serial")),
        ("device AVD", identity["device"].get("avd")),
        ("device model", identity["device"].get("model")),
        ("device locale", identity["device"].get("locale")),
    ):
        if not _meaningful(value):
            errors.append(f"{name} identity is empty")
    if identity["build"]["revision"] != document["source"]["final_diff"]["revision"]:
        errors.append("build revision does not bind the final diff revision")
    return errors


def _historical_pair_errors(document: dict[str, Any]) -> list[str]:
    """Validate the matched pre-fix/fixed identity carried by one historical package."""
    if document["cohort"]["track"] != "historical":
        if "historical_pair" in document:
            return ["prospective package must not carry historical_pair identity"]
        return []
    errors: list[str] = []
    pair = document["historical_pair"]
    source = document["source"]
    if pair["pre_fix_revision"] != source["base_revision"]:
        errors.append("historical pre-fix revision must bind source.base_revision")
    if pair["fixed_revision"] != source["final_diff"]["revision"]:
        errors.append("historical fixed revision must bind source.final_diff.revision")
    if pair["pre_fix_revision"] == pair["fixed_revision"]:
        errors.append("historical pre-fix and fixed revisions must differ")
    if pair["pre_fix_build"]["revision"] != pair["pre_fix_revision"]:
        errors.append("historical pre-fix build does not bind pre-fix revision")
    if pair["fixed_build"]["revision"] != pair["fixed_revision"]:
        errors.append("historical fixed build does not bind fixed revision")
    attempts = document["attempt_inventory"]["attempts"]
    states = [attempt.get("source_state") for attempt in attempts]
    if any(state not in {"pre_fix", "fixed"} for state in states):
        errors.append("historical attempts must declare pre_fix or fixed source_state")
    if states.count("pre_fix") != 3 or states.count("fixed") != 3:
        errors.append("historical package must contain exactly three pre_fix and three fixed attempts")
    lanes = [str(attempt["lane_id"]) for attempt in attempts]
    if len(lanes) != len(set(lanes)):
        errors.append("historical lane ids must be unique")
    return errors


def _attempt_errors(
    document: dict[str, Any], *, repo_root: Path, verify_references: bool
) -> list[str]:
    errors: list[str] = []
    inventory = document["attempt_inventory"]
    attempts = list(inventory["attempts"])
    by_id: dict[str, Mapping[str, Any]] = {}
    by_lane: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        attempt_id = str(attempt["attempt_id"])
        if attempt_id in by_id:
            errors.append(f"duplicate attempt id: {attempt_id}")
        by_id[attempt_id] = attempt
        by_lane[str(attempt["lane_id"])].append(attempt)
        if attempt.get("quarantined", False):
            errors.append(f"quarantined attempt is not admissible: {attempt_id}")
        if _parse_datetime(attempt["finished_at"]) <= _parse_datetime(attempt["started_at"]):
            errors.append(f"attempt {attempt_id} has non-increasing timestamps")
        if attempt["accountability"] == "accountable" and attempt["process"]["exit_code"] not in {0, 1}:
            errors.append(f"accountable attempt {attempt_id} has invalid process exit code")
        if attempt["accountability"] == "non_accountable" and attempt["process"]["exit_code"] == 0:
            errors.append(f"non-accountable attempt {attempt_id} has successful process exit code")
        for label in ("execution_record", "provenance", "verdict"):
            if label not in attempt:
                errors.append(f"attempt {attempt_id} is missing {label} identity")
        artifact_paths = {
            str(item["path"]) for item in attempt.get("artifacts", [])
        }
        if not artifact_paths:
            errors.append(f"attempt {attempt_id} must preserve an artifact inventory")
        for label in ("execution_record", "provenance", "verdict"):
            if label in attempt and attempt[label]["path"] not in artifact_paths:
                errors.append(
                    f"attempt {attempt_id} artifact inventory omits {label}"
                )

        _cross_check_attempt_artifacts(
            attempt,
            repo_root=repo_root,
            verify_references=verify_references,
            errors=errors,
        )

    discovered = set(inventory["discovered_attempt_ids"])
    actual = set(by_id)
    if discovered != actual:
        errors.append(
            "discovered attempt inventory does not equal declared attempts: "
            f"missing={sorted(actual - discovered)}, hidden={sorted(discovered - actual)}"
        )
    quarantined = set(inventory["quarantined_attempt_ids"])
    if quarantined:
        errors.append("quarantined attempt inventory must be empty")
    if not quarantined.issubset(actual):
        errors.append("quarantined attempt inventory names an orphan attempt")

    ledger = inventory["ledger"]
    event_ids: set[str] = set()
    events: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for event in ledger:
        event_id = str(event["event_id"])
        if event_id in event_ids:
            errors.append(f"duplicate ledger event id: {event_id}")
        event_ids.add(event_id)
        attempt_id = str(event["attempt_id"])
        events[attempt_id].append(event)
        attempt = by_id.get(attempt_id)
        if attempt is None:
            errors.append(f"orphan ledger event {event_id} names {attempt_id}")
            continue
        if event["source_state"] != attempt.get("source_state"):
            errors.append(f"ledger event {event_id} source state contradicts attempt {attempt_id}")
        for key in ("lane_id", "attempt_number"):
            if event[key] != attempt[key]:
                errors.append(f"ledger event {event_id} contradicts attempt {attempt_id} {key}")
        if event["event"] == "started":
            if event.get("accountability") is not None or event.get("process_exit_code") is not None:
                errors.append(f"started event {event_id} has terminal fields")
            if event["occurred_at"] != attempt["started_at"]:
                errors.append(f"started event {event_id} timestamp contradicts attempt")
        else:
            if event.get("accountability") != attempt["accountability"]:
                errors.append(f"finished event {event_id} accountability contradicts attempt")
            if event.get("process_exit_code") != attempt["process"]["exit_code"]:
                errors.append(f"finished event {event_id} process exit contradicts attempt")
            if event["occurred_at"] != attempt["finished_at"]:
                errors.append(f"finished event {event_id} timestamp contradicts attempt")

    for attempt_id, attempt in by_id.items():
        own_events = events.get(attempt_id, [])
        if sum(event["event"] == "started" for event in own_events) != 1:
            errors.append(f"attempt {attempt_id} must have exactly one started ledger event")
        if sum(event["event"] == "finished" for event in own_events) != 1:
            errors.append(f"attempt {attempt_id} must have exactly one finished ledger event")

    for lane_id, lane_attempts in by_lane.items():
        ordered = sorted(lane_attempts, key=lambda item: item["attempt_number"])
        numbers = [int(item["attempt_number"]) for item in ordered]
        if numbers != list(range(1, len(numbers) + 1)):
            errors.append(f"lane {lane_id} attempt numbers must be contiguous from one")
        if len(numbers) > inventory["max_attempts_per_lane"]:
            errors.append(f"lane {lane_id} exceeds the bounded retry limit")
        seen_accountable = False
        for index, attempt in enumerate(ordered):
            if seen_accountable:
                errors.append(f"lane {lane_id} retries after an accountable attempt")
            if attempt["accountability"] == "accountable":
                seen_accountable = True
                if attempt.get("retry_eligible", False):
                    errors.append(f"accountable attempt {attempt['attempt_id']} cannot be retry-eligible")
            if index and ordered[index - 1]["accountability"] == "non_accountable" and not ordered[index - 1].get("retry_eligible", False):
                errors.append(f"lane {lane_id} retries after a non-retryable attempt")

    return errors


def _cross_check_attempt_artifacts(
    attempt: Mapping[str, Any], *, repo_root: Path, verify_references: bool, errors: list[str]
) -> None:
    if not verify_references:
        return
    attempt_id = str(attempt["attempt_id"])
    execution_path = _resolve_repo_path(
        attempt["execution_record"]["path"], repo_root=repo_root, label=f"attempt {attempt_id} execution record", errors=errors
    )
    if execution_path is not None and execution_path.is_file():
        try:
            record = load_execution_record(execution_path)
        except (ExecutionRecordValidationError, OSError, ValueError) as error:
            errors.append(f"attempt {attempt_id} ExecutionRecord invalid: {error}")
        else:
            if record.get("attempt_id") != attempt_id:
                errors.append(f"attempt {attempt_id} ExecutionRecord identity mismatch")
            expected_accountable = record.get("lifecycle_state") == "completed"
            if expected_accountable != (attempt["accountability"] == "accountable"):
                errors.append(f"attempt {attempt_id} accountability contradicts ExecutionRecord")
            process_outcome = record.get("process_outcome")
            record_exit = (
                process_outcome.get("exit_code")
                if isinstance(process_outcome, dict)
                else None
            )
            if record_exit != attempt["process"]["exit_code"]:
                errors.append(f"attempt {attempt_id} process outcome contradicts ExecutionRecord")
            if record.get("started_at") != attempt["started_at"] or record.get("finished_at") != attempt["finished_at"]:
                errors.append(f"attempt {attempt_id} timestamps contradict ExecutionRecord")

    for label in ("provenance", "verdict"):
        path = _resolve_repo_path(
            attempt[label]["path"], repo_root=repo_root, label=f"attempt {attempt_id} {label}", errors=errors
        )
        if path is None or not path.is_file():
            continue
        try:
            value = _load_json_file(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, _DuplicateKeyError) as error:
            errors.append(f"attempt {attempt_id} {label} is not valid JSON: {error}")
            continue
        if isinstance(value, dict) and "attempt_id" in value and value["attempt_id"] != attempt_id:
            errors.append(f"attempt {attempt_id} {label} identity mismatch")
        if label == "provenance" and isinstance(value, dict):
            if value.get("source_state") != attempt.get("source_state"):
                errors.append(f"attempt {attempt_id} provenance source state mismatch")
        if label == "provenance" and isinstance(value, dict) and "attempt_id" not in value:
            errors.append(f"attempt {attempt_id} provenance omits attempt identity")
        if label == "verdict" and isinstance(value, dict):
            execution = value.get("execution")
            if isinstance(execution, dict):
                accountable = execution.get("accounting_eligible") is True
                if accountable != (attempt["accountability"] == "accountable"):
                    errors.append(f"attempt {attempt_id} verdict accountability contradicts package")
                if execution.get("status") == "completed" and attempt["process"]["exit_code"] not in {0, 1}:
                    errors.append(f"attempt {attempt_id} verdict is completed with invalid process exit")


def _conclusion_errors(
    document: dict[str, Any], *, repo_root: Path, verify_references: bool
) -> list[str]:
    errors: list[str] = []
    verification = document["verification"]
    adjudication = document["adjudication"]
    if verification["agent"] == adjudication["agent"]:
        errors.append("verification and adjudication agents must be independent")
    if verification["conclusion"] != adjudication["conclusion"]:
        errors.append("adjudication conclusion contradicts verification conclusion")
    if not adjudication["agreement"]:
        errors.append("adjudication agreement must be true")
    finish_times = [_parse_datetime(attempt["finished_at"]) for attempt in document["attempt_inventory"]["attempts"]]
    if finish_times and _parse_datetime(verification["frozen_at"]) < max(finish_times):
        errors.append("verification frozen_at must be after the last attempt")
    if document["timing"]["duration_seconds"] < 0:
        errors.append("package timing duration must be non-negative")
    verdict_ref = verification["verdict"]
    if verify_references:
        verdict_path = _resolve_repo_path(
            verdict_ref["path"], repo_root=repo_root, label="verification.verdict", errors=errors
        )
        if verdict_path is not None and verdict_path.is_file():
            try:
                verdict = _load_json_file(verdict_path)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, _DuplicateKeyError) as error:
                errors.append(f"verification verdict is not valid JSON: {error}")
            else:
                outcome = verdict.get("outcome") if isinstance(verdict, dict) else None
                expected = _CONCLUSION_TO_OUTCOME.get(verification["conclusion"])
                if expected is not None and outcome is not None and outcome != expected:
                    errors.append("verification conclusion contradicts oracle verdict outcome")
    return errors


def _claim_errors(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    boundary = document["claim_boundary"]
    if not boundary["local_only"]:
        errors.append("claim boundary must remain local-only")
    forbidden = {str(item).lower() for item in boundary["forbidden"]}
    missing = sorted(_REQUIRED_FORBIDDEN - forbidden)
    if missing:
        errors.append("claim boundary is missing forbidden fields: " + ", ".join(missing))
    allowed = list(boundary["allowed"])
    leaked = sorted(
        item for item in allowed
        if any(term in str(item).lower() for term in _FORBIDDEN_TERMS)
    )
    if leaked:
        errors.append("allowed claim boundary leaks forbidden terms: " + ", ".join(leaked))
    return errors


def _reference_errors(
    document: dict[str, Any], *, repo_root: Path, verify_references: bool
) -> list[str]:
    errors: list[str] = []
    for label, reference in _artifact_refs(document):
        resolved = _resolve_repo_path(
            reference["path"], repo_root=repo_root, label=label, errors=errors
        )
        if resolved is None or not verify_references:
            continue
        if not resolved.is_file():
            errors.append(f"{label} artifact does not exist: {reference['path']}")
            continue
        actual = _sha256_file(resolved)
        if actual != reference["sha256"]:
            errors.append(
                f"{label} checksum mismatch for {reference['path']}: expected "
                f"{reference['sha256']}, got {actual}"
            )
    return errors


def _artifact_refs(value: Any, *, path: tuple[str, ...] = ()) -> Iterable[tuple[str, Mapping[str, str]]]:
    if isinstance(value, dict):
        if set(value) == {"path", "sha256"}:
            yield (".".join(path) or "<root>", value)
            return
        for key, child in value.items():
            yield from _artifact_refs(child, path=(*path, str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _artifact_refs(child, path=(*path, str(index)))


def _resolve_repo_path(value: str, *, repo_root: Path, label: str, errors: list[str]) -> Path | None:
    if "\\" in value:
        errors.append(f"{label} must use repository-relative POSIX path syntax")
        return None
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or "." in relative.parts or relative.as_posix() != value:
        errors.append(f"{label} must be a normalized repository-relative path")
        return None
    resolved = (repo_root / Path(*relative.parts)).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        errors.append(f"{label} resolves outside the repository")
        return None
    return resolved


def _infer_root(path: Path) -> Path:
    for parent in (path.parent, *path.parents):
        if (parent / "pyproject.toml").is_file() and (parent / ".git").exists():
            return parent.resolve()
    return path.parent.resolve()


def _repo_relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object_pairs)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _render_schema_error(error: Any) -> str:
    path = ".".join(str(part) for part in error.absolute_path) or "<root>"
    return f"schema {path}: {error.message}"


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _slot_task_id(slot: Mapping[str, Any]) -> str:
    pair = slot["historical"] if slot["track"] == "historical" else slot["prospective"]
    return str(pair["upstream_task_id"])


def _task_url_matches_id(task_url: str, task_id: str) -> bool:
    parsed = urlparse(task_url)
    parts = [part for part in parsed.path.rstrip("/").split("/") if part]
    return bool(parts) and parts[-1].removeprefix("T") == task_id.removeprefix("T")


def _meaningful(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _meaningful_mapping(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(value) and all(
        _meaningful(key) and value_item not in (None, "", [], {})
        for key, value_item in value.items()
    )


def _track_summary(packages: Sequence[QualificationCasePackage]) -> dict[str, Any]:
    conclusions = Counter(package.conclusion for package in packages)
    attempts = [attempt for package in packages for attempt in package.attempts]
    accountable = sum(attempt["accountability"] == "accountable" for attempt in attempts)
    non_accountable = len(attempts) - accountable
    operational_seconds = round(
        sum(float(package.document["timing"]["duration_seconds"]) for package in packages),
        3,
    )
    interventions = sum(len(package.document["timing"]["interventions"]) for package in packages)
    gaps = sum(len(package.document["timing"]["gaps"]) for package in packages)
    return {
        "cases": len(packages),
        "slot_ids": [package.slot_id for package in sorted(packages, key=lambda item: item.slot_id)],
        "attempts": len(attempts),
        "accountable_attempts": accountable,
        "non_accountable_attempts": non_accountable,
        "conclusions": dict(sorted(conclusions.items())),
        "operational_seconds": operational_seconds,
        "interventions": interventions,
        "gaps": gaps,
    }


def _assert_render_boundary(rendered: str) -> None:
    lowered = rendered.lower()
    leaked = [term for term in _FORBIDDEN_TERMS if term in lowered]
    if leaked:
        raise CasePackageValidationError(
            ["renderer would emit forbidden claim terms: " + ", ".join(leaked)]
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("package", type=Path)
    validate.add_argument("--repo-root", type=Path)
    validate.add_argument("--no-verify-references", action="store_true")
    aggregate = commands.add_parser("aggregate")
    aggregate.add_argument("--manifest", type=Path, required=True)
    aggregate.add_argument("--packages", type=Path, nargs="+", required=True)
    aggregate.add_argument("--repo-root", type=Path)
    aggregate.add_argument("--no-verify-references", action="store_true")
    aggregate.add_argument("--json-output", type=Path)
    aggregate.add_argument("--markdown-output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            package = load_case_package(
                args.package,
                repo_root=args.repo_root,
                verify_references=not args.no_verify_references,
            )
            payload = {
                "status": "valid",
                "package_id": package.package_id,
                "cohort_id": package.cohort_id,
                "slot_id": package.slot_id,
                "track": package.track,
                "source_sha256": package.source_sha256,
                "canonical_sha256": package.canonical_sha256,
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        aggregate_model = aggregate_packages(
            args.packages,
            manifest_path=args.manifest,
            repo_root=args.repo_root,
            verify_references=not args.no_verify_references,
        )
        if args.json_output is not None or args.markdown_output is not None:
            if args.json_output is None or args.markdown_output is None:
                parser.error("aggregate requires both --json-output and --markdown-output")
            write_reports(aggregate_model, args.json_output, args.markdown_output)
        else:
            print(render_structured(aggregate_model), end="")
        return 0
    except CasePackageValidationError as error:
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


if __name__ == "__main__":
    raise SystemExit(main())
