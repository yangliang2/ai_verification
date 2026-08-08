"""Fresh M9 recovery qualification freeze contracts.

This module validates the recovery-v2 hand-off prepared by issue #152.  It is
deliberately separate from :mod:`aiverify.bench.m9_qualification`: the original
#136/#137 manifest, cohort, source pair, and executor remain immutable.

The contract is preflight-only.  Loading a candidate or validating an admission
receipt never builds, installs, launches, accesses a device, or invokes an
agent.  A candidate packet may be technically admitted while it waits for the
required human freeze approval; only an approved packet may have ``frozen``
status.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import struct
import unicodedata
import zlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from aiverify.bench.m9_qualification import (
    CONTRADICTION_REJECTION_BOUNDARY,
    CONTRADICTION_REQUIRED_FIELDS,
    audit_contradiction_packet,
    audit_neutral_packets,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)
from aiverify.discovery.contracts import Finding, ProjectRiskMap, ResidualRisk
from aiverify.discovery.models import DiscoveryContractError
from aiverify.runner.codex_identity import (
    capture_codex_invocation_identity,
    default_codex_session_root,
)
from aiverify.runner.command import (
    CommandResult,
    CommandRunner,
    SubprocessCommandRunner,
)
from aiverify.runner.execution_identity import (
    ExecutionIdentityError,
    verify_execution_provenance,
)
from aiverify.runner.execution_record import (
    ExecutionRecordValidationError,
    is_execution_record_accountable,
    load_execution_record,
    write_bytes_artifact,
    write_json_artifact,
)


QUALIFICATION_ID = "m9-recovery-project-qualification-v2"
LANE_IDS = tuple(f"m9-r4-lane-{index:02d}" for index in range(1, 7))
SOURCE_ORIGIN = "https://github.com/android/compose-samples.git"
PROJECT_TARGET_COMMIT = "038c8208307508ceedcb5dd07a4fe2794017644c"
PROJECT_TARGET_TREE = "e658ec4cdbb25d8e75a04879e9e20a0c245832e9"
DEFECT_COMMIT = "56b59e237b253bc52e2ce1141dce26af07503415"
DEFECT_TREE = "993432fb446913107df1bc0c040a05f8dae1c5b2"
PROJECT_TARGET_ID = "compose-samples-jetchat-038c8208"
PACKAGE = "com.example.compose.jetchat"
ACTIVITY = "com.example.compose.jetchat.NavActivity"
APK_GLOB = "Jetchat/app/build/outputs/apk/debug/app-debug.apk"
CONTROL_APK_BYTES = 17_511_449
CONTROL_APK_SHA256 = (
    "a1536cec09a33063f7796dc77e0effdf1847a3ad325dcef707216fa87d78386d"
)
DEFECT_APK_BYTES = 17_511_239
DEFECT_APK_SHA256 = (
    "41d7c3ff47f2f2d2a04942d11ab57c6c76ac7314ff6abf8dad14fd9b3149e55b"
)
RUNNER_POLICY = "m9-production-seam-v1"
BACKEND = "codex_cli"
DEVICE = "emulator-5554"
FORMAL_ATTEMPT_ID = "m9-r4-formal-attempt-01"
FORMAL_HYPOTHESIS_ID = "hypothesis-m9-r4-portfolio-2"
R3_RUN_RECORD = (
    "docs/runs/2026-08-07-issue-152-m9-r3-fresh-qualification-freeze"
)
R4_RUN_RECORD = "docs/runs/2026-08-07-m9-r4-formal-attempt-01"
R4_ARTIFACT_ROOT = f"{R4_RUN_RECORD}/formal-artifacts"
CONTRADICTION_PACKET_ID = "m9-r3-incomplete-context-v2"
PROBE_TOKENS = (
    "r4q01-nacre",
    "r4q02-ember",
    "r4q03-lumen",
    "r4q04-cobalt",
    "r4q05-saffron",
    "r4q06-velvet",
)
LOCAL_CLAIM_BOUNDARY = (
    "one approved compose-samples Jetchat matched pair on one local API-35 "
    "emulator in the frozen six-lane M9-R4 attempt"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_APPROVAL_COMMENT_URL = re.compile(
    r"^https://github\.com/yangliang2/ai_verification/"
    r"issues/152#issuecomment-[0-9]+$"
)
_REVIEW_REQUIRED_FIELDS = (
    "path",
    "sha256",
    "schema_version",
    "review_id",
    "lane_id",
    "status",
    "outcome",
    "candidate_finding_id",
    "candidate_finding_sha256",
    "invocation_id",
    "identity_path",
    "identity_sha256",
    "production_invocation_id",
    "production_identity_sha256",
    "clean_context",
    "clean_context_path",
    "clean_context_sha256",
    "output_path",
    "output_sha256",
    "output_schema_path",
    "output_schema_sha256",
    "events_path",
    "events_sha256",
    "invocation_ledger_path",
    "invocation_ledger_sha256",
    "prompt_path",
    "prompt_sha256",
    "backend",
    "requested_model",
    "model_selection",
    "effective_model",
    "authoritative_observation_source",
    "source_role_disclosed",
    "expected_result_disclosed",
    "production_oracle_path_used",
    "same_provider_family_limitation_disclosed",
)
_ATTEMPT_EVIDENCE_REF_FILES = {
    "execution_record": "execution-record.json",
    "execution_provenance": "execution-provenance.json",
    "effective_execution_identity": "effective-execution-identity.json",
    "runner_setup": "runner-setup.json",
    "production_seam_admission": "production-seam-admission.json",
    "screenshot_before": "raw/screenshots/before.png",
    "screenshot_after": "raw/screenshots/after.png",
    "layout_before": "raw/layout/before.json",
    "layout_after": "raw/layout/after.json",
    "filtered_logcat": "raw/logcat/rotation.txt",
    "rotation_event": "rotation-event.json",
    "oracle_receipt": "oracle-receipt.json",
    "finding": "finding.json",
    "residual_risk": "residual-risk.json",
    "project_risk_map": "project-risk-map.json",
    "claim_boundary": "claim-boundary.json",
    "falsification_review": "falsification-review.json",
    "falsification_review_output": "falsification-review-output.json",
    "falsification_review_output_schema": (
        "falsification-review-output-schema.json"
    ),
    "falsification_review_events": "falsification-review-events.jsonl",
    "falsification_review_invocation": (
        "falsification-review-invocation.json"
    ),
    "falsification_review_prompt": "falsification-review-prompt.md",
    "falsification_review_identity": "falsification-review-identity.json",
    "falsification_review_context": "falsification-review-context.json",
    "lane_ledger": "checksums.sha256",
}
_ATTEMPT_VALIDATOR_CHECKS = (
    "execution_record_terminal",
    "execution_record_attempt_bound",
    "execution_provenance_semantically_valid",
    "effective_identity_bound",
    "authoritative_production_identities_bound",
    "fresh_production_admission_bound",
    "runner_setup_bound",
    "raw_oracle_evidence_bound",
    "oracle_bound",
    "finding_evidence_refs_bound",
    "residual_risk_bound",
    "project_risk_map_bound",
    "claim_boundary_local",
    "falsification_review_bound",
    "falsification_review_output_bound",
    "authoritative_review_identity_bound",
    "clean_review_context_bound",
    "review_inputs_role_blind",
    "lane_ledger_exhaustive",
)
_REVIEW_INPUT_FILES = (
    "execution-summary.json",
    "effective-execution-identity.json",
    "raw/screenshots/before.png",
    "raw/screenshots/after.png",
    "raw/layout/before.json",
    "raw/layout/after.json",
    "raw/logcat/rotation.txt",
    "rotation-event.json",
    "oracle-receipt.json",
    "finding.json",
    "claim-boundary.json",
)
_REVIEW_DIMENSIONS = (
    "alternative_explanations",
    "assumption_violations",
    "evidence_integrity",
    "causal_attribution",
    "observation_consistency",
    "claim_boundary",
)
_REVIEW_TERMINAL_FAILURE_STAGES = (
    "runner_exception",
    "runner_command_mismatch",
    "process_exit",
    "timeout",
    "event_stream_persistence",
    "missing_output",
    "identity_capture",
    "final_binding",
)
_PACKET_FIELDS = (
    "history_exclusion",
    "target",
    "cohort",
    "policy",
    "lanes",
    "runner",
    "context_acquisition",
    "portfolio",
    "attack_plan",
    "oracle",
    "evidence",
    "exploration_stop_rule",
    "falsification_review",
    "admission",
    "contradiction_packet",
    "leakage_audit",
    "supported_gate",
    "claim_boundary",
)


class M9RecoveryQualificationError(ValueError):
    """Raised when a recovery-v2 qualification packet is invalid."""

    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(dict.fromkeys(str(error) for error in errors))
        detail = "\n".join(f"- {error}" for error in self.errors)
        super().__init__(f"M9 recovery qualification is invalid:\n{detail}")


class FalsificationReviewExecutionError(RuntimeError):
    """Raised after a single review invocation cannot produce bound evidence."""

    def __init__(self, message: str, *, receipt_path: Path) -> None:
        super().__init__(message)
        self.receipt_path = Path(receipt_path)


@dataclass(frozen=True)
class M9RecoveryQualificationManifest:
    """Exact candidate/frozen manifest bytes and canonical identity."""

    source_path: Path
    source_sha256: str
    canonical_sha256: str
    packet_commitment_sha256: str
    document: Mapping[str, Any]

    @property
    def qualification_id(self) -> str:
        return str(self.document["qualification_id"])

    @property
    def status(self) -> str:
        return str(self.document["status"])

    @property
    def lanes(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.document["lanes"])


@dataclass(frozen=True)
class M9RecoveryAuditorMapping:
    """Exact released mapping bytes after both frozen digests are verified."""

    source_path: Path
    raw_sha256: str
    canonical_sha256: str
    document: Mapping[str, Any]


@dataclass(frozen=True)
class _CodexInvocationIdentity:
    invocation_id: str
    thread_id: str
    turn_id: str
    receipt_sha256: str
    effective_model: str
    workdir: str


@dataclass(frozen=True)
class FalsificationReviewInvocationPlan:
    """Executable, checksum-bound input for one fresh review invocation."""

    lane_id: str
    workdir: Path
    argv_without_prompt: tuple[str, ...]
    prompt: str
    prompt_transport: str
    prompt_path: Path
    prompt_sha256: str
    output_schema_path: Path
    output_schema_sha256: str
    output_path: Path
    events_path: Path
    identity_path: Path
    invocation_ledger_path: Path


def sealed_source_binding_ref(lane_id: str) -> str:
    """Return the role-neutral source binding embedded in one Run Spec."""

    if lane_id not in LANE_IDS:
        raise ValueError(f"unknown M9 recovery lane: {lane_id}")
    value = f"{QUALIFICATION_ID}:{lane_id}:source-binding-v1".encode()
    return sha256_bytes(value)[:40]


def freeze_payload(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return the approval-bound packet, excluding its mutable approval envelope."""

    return {field: document.get(field) for field in _PACKET_FIELDS}


def freeze_payload_sha256(document: Mapping[str, Any]) -> str:
    """Return the stable digest a human approves before freeze finalization."""

    return sha256_bytes(canonical_json_bytes(freeze_payload(document)))


def ensure_candidate_regeneration_allowed(path: str | Path) -> None:
    """Refuse to rewrite a manifest after explicit approval froze it."""

    candidate_path = Path(path)
    if not candidate_path.exists():
        return
    try:
        existing = json.loads(
            candidate_path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_pairs,
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        M9RecoveryQualificationError,
    ) as error:
        raise M9RecoveryQualificationError(
            (f"existing qualification manifest cannot be audited: {error}",)
        ) from error
    if not isinstance(existing, Mapping):
        raise M9RecoveryQualificationError(
            ("existing qualification manifest root must be an object",)
        )
    if existing.get("status") == "frozen":
        raise M9RecoveryQualificationError(
            ("frozen qualification manifests are immutable",)
        )


def ensure_evidence_ledger_regeneration_allowed(path: str | Path) -> None:
    """Refuse to bless changed evidence with a new ledger after freeze."""

    ensure_candidate_regeneration_allowed(path)


def validate_human_approval(
    *,
    comment_url: str,
    approved_by: str,
    approved_at: str,
) -> None:
    """Validate the auditable #152 approval envelope before any file rewrite."""

    errors = _human_approval_errors(
        comment_url=comment_url,
        approved_by=approved_by,
        approved_at=approved_at,
    )
    if errors:
        raise M9RecoveryQualificationError(errors)


def load_manifest(
    path: str | Path,
    *,
    require_frozen: bool = False,
) -> M9RecoveryQualificationManifest:
    """Load and validate one candidate or approved recovery manifest."""

    source_path = Path(path).resolve()
    try:
        raw = source_path.read_bytes()
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        M9RecoveryQualificationError,
    ) as error:
        raise M9RecoveryQualificationError(
            (f"manifest cannot be read: {error}",)
        ) from error
    if not isinstance(document, dict):
        raise M9RecoveryQualificationError(("manifest root must be an object",))
    errors = _manifest_errors(document, require_frozen=require_frozen)
    if errors:
        raise M9RecoveryQualificationError(errors)
    return M9RecoveryQualificationManifest(
        source_path=source_path,
        source_sha256=sha256_bytes(raw),
        canonical_sha256=sha256_bytes(canonical_json_bytes(document)),
        packet_commitment_sha256=freeze_payload_sha256(document),
        document=document,
    )


def load_auditor_mapping(
    path: str | Path,
    *,
    expected_raw_sha256: str,
    expected_canonical_sha256: str,
) -> M9RecoveryAuditorMapping:
    """Load the clear mapping only at its release gate and verify both digests."""

    if not _SHA256.fullmatch(expected_raw_sha256) or not _SHA256.fullmatch(
        expected_canonical_sha256
    ):
        raise M9RecoveryQualificationError(
            ("expected auditor mapping digests must be SHA-256 values",)
        )
    source_path = Path(path).resolve()
    try:
        raw = source_path.read_bytes()
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        M9RecoveryQualificationError,
    ) as error:
        raise M9RecoveryQualificationError(
            (f"auditor mapping cannot be read: {error}",)
        ) from error
    if not isinstance(document, dict):
        raise M9RecoveryQualificationError(
            ("auditor mapping root must be an object",)
        )
    raw_sha = sha256_bytes(raw)
    canonical_sha = sha256_bytes(canonical_json_bytes(document))
    if raw_sha != expected_raw_sha256:
        raise M9RecoveryQualificationError(
            ("released auditor mapping raw bytes contradict the frozen digest",)
        )
    if canonical_sha != expected_canonical_sha256:
        raise M9RecoveryQualificationError(
            (
                "released auditor mapping content contradicts the frozen "
                "canonical commitment",
            )
        )
    errors = _mapping_errors(document)
    if errors:
        raise M9RecoveryQualificationError(errors)
    return M9RecoveryAuditorMapping(
        source_path=source_path,
        raw_sha256=raw_sha,
        canonical_sha256=canonical_sha,
        document=document,
    )


def validate_admission_receipts(
    receipts: Sequence[Mapping[str, Any]],
    *,
    expected_run_specs: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate the exact ordered six-lane side-effect-free admission set."""

    checks: list[dict[str, Any]] = []
    observed_ids: list[str | None] = []
    seen: set[str] = set()
    for receipt in receipts:
        run_spec = receipt.get("run_spec")
        lane_id = run_spec.get("scenario") if isinstance(run_spec, Mapping) else None
        lane_text = str(lane_id) if lane_id is not None else None
        observed_ids.append(lane_text)
        expected = expected_run_specs.get(lane_text or "", {})
        runner_policy = receipt.get("runner_policy")
        options = (
            runner_policy.get("options", {})
            if isinstance(runner_policy, Mapping)
            else {}
        )
        tools = (
            runner_policy.get("tools", {})
            if isinstance(runner_policy, Mapping)
            else {}
        )
        model_selection = (
            tools.get("model_selection", {})
            if isinstance(tools, Mapping)
            else {}
        )
        host = receipt.get("host")
        effects = receipt.get("side_effects")
        artifact_namespace = receipt.get("artifact_namespace")
        known = isinstance(lane_id, str) and lane_id in LANE_IDS
        duplicate = isinstance(lane_id, str) and lane_id in seen
        if isinstance(lane_id, str):
            seen.add(lane_id)
        expected_suffix = (
            f"bench/m9/recovery-v2/run-specs/{lane_id}.yaml"
            if isinstance(lane_id, str)
            else "\0"
        )
        artifact_suffix = (
            f"{R4_ARTIFACT_ROOT}/{lane_id}/artifacts"
            if isinstance(lane_id, str)
            else "\0"
        )
        run_dir_suffix = (
            f"{R4_ARTIFACT_ROOT}/{lane_id}"
            if isinstance(lane_id, str)
            else "\0"
        )
        journey_model = (
            model_selection.get("journey_driver")
            if isinstance(model_selection, Mapping)
            else None
        )
        judge_model = (
            model_selection.get("l3_semantic_judge")
            if isinstance(model_selection, Mapping)
            else None
        )
        passed = (
            known
            and not duplicate
            and receipt.get("status") == "admitted"
            and receipt.get("admitted") is True
            and isinstance(run_spec, Mapping)
            and isinstance(run_spec.get("path"), str)
            and run_spec["path"].endswith(expected_suffix)
            and run_spec.get("sha256") == expected.get("run_spec_sha256")
            and isinstance(host, Mapping)
            and host.get("origin") == SOURCE_ORIGIN
            and host.get("commit") == expected.get("commit")
            and _is_nonempty_string(host.get("host_project"))
            and host.get("host_project") == host.get("repository_root")
            and isinstance(host.get("worktree"), Mapping)
            and host["worktree"].get("clean") is True
            and host["worktree"].get("status_sha256")
            == sha256_bytes(b"")
            and isinstance(effects, Mapping)
            and effects.get("external") is False
            and effects.get("build") is False
            and effects.get("device") is False
            and effects.get("agent") is False
            and options.get("device") == DEVICE
            and options.get("backend") == BACKEND
            and options.get("requested_driver_model") is None
            and options.get("requested_l3_model") is None
            and options.get("runner_policy_version") == RUNNER_POLICY
            and options.get("expected_source_commit") == expected.get("commit")
            and options.get("launch") is True
            and options.get("allow_host_project_subdir") is False
            and options.get("workdir") == host.get("host_project")
            and isinstance(options.get("artifact_dir"), str)
            and options["artifact_dir"].replace("\\", "/").endswith(
                artifact_suffix
            )
            and options.get("android_bin") == "android"
            and options.get("adb_bin") == "adb"
            and options.get("codex_bin") == "codex"
            and isinstance(runner_policy, Mapping)
            and runner_policy.get("backend") == BACKEND
            and runner_policy.get("version") == RUNNER_POLICY
            and isinstance(artifact_namespace, Mapping)
            and artifact_namespace.get("artifact_dir")
            == options.get("artifact_dir")
            and isinstance(artifact_namespace.get("run_dir"), str)
            and artifact_namespace["run_dir"].replace("\\", "/").endswith(
                run_dir_suffix
            )
            and artifact_namespace.get("formal_outputs_absent") is True
            and all(
                isinstance(tools.get(name), Mapping)
                and tools[name].get("requested") == name
                and _is_nonempty_string(tools[name].get("resolved_path"))
                and _is_sha256(tools[name].get("sha256"))
                for name in ("android", "adb", "codex")
            )
            and all(
                isinstance(model, Mapping)
                and model.get("model_override_present") is False
                and model.get("policy") == "codex_cli_default"
                and model.get("requested_model") is None
                for model in (journey_model, judge_model)
            )
        )
        checks.append(
            {
                "lane_id": lane_text or "unknown",
                "status": "pass" if passed else "fail",
                "receipt_status": receipt.get("status"),
                "side_effects": (
                    dict(effects) if isinstance(effects, Mapping) else effects
                ),
            }
        )
    if len(receipts) != 6 or tuple(observed_ids) != LANE_IDS:
        checks.append(
            {
                "lane_id": "population",
                "status": "fail",
                "reason": (
                    f"expected ordered lanes {list(LANE_IDS)}, got {observed_ids}"
                ),
            }
        )
    failures = [item for item in checks if item["status"] != "pass"]
    return {
        "status": "pass" if not failures else "fail",
        "receipt_count": len(receipts),
        "checks": checks,
        "formal_execution_started": False,
    }


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _human_approval_errors(
    *,
    comment_url: object,
    approved_by: object,
    approved_at: object,
) -> tuple[str, ...]:
    errors: list[str] = []
    if (
        not isinstance(comment_url, str)
        or _APPROVAL_COMMENT_URL.fullmatch(comment_url) is None
    ):
        errors.append("approval comment must be an auditable #152 issue comment")
    if not _is_nonempty_string(approved_by):
        errors.append("approval reviewer identity must be nonblank")
    timestamp: dt.datetime | None = None
    if isinstance(approved_at, str):
        try:
            timestamp = dt.datetime.fromisoformat(
                approved_at.replace("Z", "+00:00")
            )
        except ValueError:
            timestamp = None
    if (
        timestamp is None
        or timestamp.tzinfo is None
        or timestamp.utcoffset() is None
    ):
        errors.append("approval timestamp must be parseable and timezone-aware")
    return tuple(errors)


def _strict_count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _sum_evidence_counts(values: Iterable[object]) -> int | None:
    counts = [_strict_count(value) for value in values]
    if any(value is None for value in counts):
        return None
    return sum(value for value in counts if value is not None)


def _review_receipt_is_eligible(
    review: Mapping[str, Any],
    *,
    lane_id: str,
    production_invocation_id: object,
    production_identity_sha256: object,
) -> bool:
    return (
        set(review) == set(_REVIEW_REQUIRED_FIELDS)
        and review.get("schema_version") == 2
        and review.get("review_id") == f"falsification-review-{lane_id}"
        and review.get("lane_id") == lane_id
        and review.get("status") == "complete"
        and review.get("outcome") == "survived"
        and review.get("candidate_finding_id") == f"finding-{lane_id}"
        and _is_sha256(review.get("candidate_finding_sha256"))
        and _is_nonempty_string(review.get("invocation_id"))
        and review.get("identity_path")
        == f"{R4_ARTIFACT_ROOT}/{lane_id}/falsification-review-identity.json"
        and _is_sha256(review.get("identity_sha256"))
        and _is_nonempty_string(production_invocation_id)
        and _is_sha256(production_identity_sha256)
        and review.get("production_invocation_id")
        == production_invocation_id
        and review.get("production_identity_sha256")
        == production_identity_sha256
        and review.get("invocation_id") != production_invocation_id
        and review.get("identity_sha256") != production_identity_sha256
        and review.get("clean_context") is True
        and review.get("clean_context_path")
        == f"{R4_ARTIFACT_ROOT}/{lane_id}/falsification-review-context.json"
        and _is_sha256(review.get("clean_context_sha256"))
        and review.get("output_path")
        == f"{R4_ARTIFACT_ROOT}/{lane_id}/falsification-review-output.json"
        and _is_sha256(review.get("output_sha256"))
        and review.get("output_schema_path")
        == (
            f"{R4_ARTIFACT_ROOT}/{lane_id}/"
            "falsification-review-output-schema.json"
        )
        and _is_sha256(review.get("output_schema_sha256"))
        and review.get("events_path")
        == f"{R4_ARTIFACT_ROOT}/{lane_id}/falsification-review-events.jsonl"
        and _is_sha256(review.get("events_sha256"))
        and review.get("invocation_ledger_path")
        == (
            f"{R4_ARTIFACT_ROOT}/{lane_id}/"
            "falsification-review-invocation.json"
        )
        and _is_sha256(review.get("invocation_ledger_sha256"))
        and review.get("prompt_path")
        == f"{R4_ARTIFACT_ROOT}/{lane_id}/falsification-review-prompt.md"
        and _is_sha256(review.get("prompt_sha256"))
        and review.get("backend") == BACKEND
        and review.get("requested_model") is None
        and review.get("model_selection") == "codex_cli_default"
        and _is_nonempty_string(review.get("effective_model"))
        and review.get("authoritative_observation_source")
        == "codex_cli_event"
        and review.get("source_role_disclosed") is False
        and review.get("expected_result_disclosed") is False
        and review.get("production_oracle_path_used") is False
        and review.get("same_provider_family_limitation_disclosed") is True
    )


def _contradiction_audit_is_eligible(
    contradiction: Mapping[str, Any],
) -> bool:
    return (
        contradiction.get("packet_id") == CONTRADICTION_PACKET_ID
        and contradiction.get("status") == "pass"
        and tuple(contradiction.get("missing_fields", ()))
        == CONTRADICTION_REQUIRED_FIELDS
        and contradiction.get("expected_admission") == "rejected"
        and contradiction.get("formal_denominator") is False
        and contradiction.get("side_effects") is False
        and contradiction.get("rejection_boundary")
        == CONTRADICTION_REJECTION_BOUNDARY
        and contradiction.get("command_calls") == []
        and contradiction.get("pre_side_effect_rejection") is True
    )


def _artifact_reference_is_bound(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and _is_nonempty_string(value.get("path"))
        and _is_sha256(value.get("sha256"))
    )


def _lane_binding_is_valid(lane: Mapping[str, Any]) -> bool:
    lane_id = str(lane.get("lane_id"))
    run_spec = lane.get("run_spec")
    receipt = lane.get("r3_feasibility_admission_receipt")
    planned = lane.get("planned_r4_runner")
    return (
        _artifact_reference_is_bound(run_spec)
        and isinstance(run_spec, Mapping)
        and run_spec.get("source_binding_ref")
        == sealed_source_binding_ref(lane_id)
        and _artifact_reference_is_bound(receipt)
        and isinstance(planned, Mapping)
        and planned.get("artifact_dir_relative")
        == f"{R4_ARTIFACT_ROOT}/{lane_id}/artifacts"
        and planned.get("workdir_binding")
        == "clean_source_worktree_resolved_from_released_mapping"
        and planned.get("source_binding_ref")
        == sealed_source_binding_ref(lane_id)
        and planned.get("path_resolution_root") == "r4_clean_worktree"
        and planned.get("fresh_side_effect_free_re_admission_required") is True
        and _is_nonempty_string(lane.get("probe_token"))
    )


def _bound_file(
    repository_root: Path,
    reference: object,
) -> Path | None:
    if not _artifact_reference_is_bound(reference):
        return None
    path = (repository_root / str(reference["path"])).resolve()
    if (
        not path.is_relative_to(repository_root)
        or not path.is_file()
        or sha256_file(path) != reference.get("sha256")
    ):
        return None
    return path


def _read_json_object(path: Path) -> Mapping[str, Any] | None:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_pairs,
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        M9RecoveryQualificationError,
    ):
        return None
    return value if isinstance(value, Mapping) else None


def _json_digest_without_trailing_newline(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(encoded)


def _version_number(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"\d+(?:\.\d+)+", value)
    return match.group(0) if match is not None else None


def _argv_has_model_override(argv: Sequence[str]) -> bool:
    """Return whether a Codex command explicitly overrides model selection."""

    for index, item in enumerate(argv):
        lowered = item.strip().lower()
        if (
            lowered in {"--model", "-m", "--profile", "-p"}
            or lowered.startswith("--model=")
            or lowered.startswith("--profile=")
            or (lowered.startswith("-p") and not lowered.startswith("--"))
        ):
            return True
        config_value: str | None = None
        if lowered in {"--config", "-c"}:
            if index + 1 < len(argv):
                config_value = argv[index + 1]
        elif lowered.startswith("--config="):
            config_value = item.split("=", 1)[1]
        elif lowered.startswith("-c") and lowered != "-c":
            config_value = item[2:].removeprefix("=")
        if config_value is None:
            continue
        key, separator, _ = config_value.partition("=")
        normalized_key = key.strip().strip("\"'").lower()
        if separator and (
            normalized_key.startswith("model")
            or normalized_key.endswith(".model")
        ):
            return True
    return False


def _falsification_review_argv(
    *,
    workdir: Path,
    output_path: Path,
    output_schema_path: Path,
) -> tuple[str, ...]:
    """Return the one admitted fresh, read-only review command."""

    return (
        "codex",
        "exec",
        "--json",
        "--output-schema",
        str(output_schema_path.resolve()),
        "--output-last-message",
        str(output_path.resolve()),
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--cd",
        str(workdir.resolve()),
    )


def _codex_identity(
    path: Path,
    *,
    expected_role: str,
    require_fresh_session: bool = False,
) -> _CodexInvocationIdentity | None:
    receipt = _read_json_object(path)
    if receipt is None:
        return None
    binary = receipt.get("binary")
    source = receipt.get("effective_model_source")
    observation = receipt.get("source_observation")
    command = receipt.get("command")
    if not all(
        isinstance(value, Mapping)
        for value in (binary, source, observation, command)
    ):
        return None
    session = observation.get("session_meta")
    turn = observation.get("turn_context")
    argv = command.get("argv_without_prompt")
    effective_model = receipt.get("effective_model")
    if (
        receipt.get("schema_version") != 1
        or receipt.get("role") != expected_role
        or receipt.get("backend") != BACKEND
        or receipt.get("requested_model") is not None
        or not _is_nonempty_string(effective_model)
        or binary.get("requested") != "codex"
        or not _is_nonempty_string(binary.get("resolved_path"))
        or not _is_sha256(binary.get("sha256"))
        or not _is_nonempty_string(binary.get("version"))
        or source.get("kind") != "codex_session_turn_context"
        or not _is_sha256(source.get("observation_sha256"))
        or not isinstance(session, Mapping)
        or not isinstance(turn, Mapping)
        or source.get("observation_sha256")
        != _json_digest_without_trailing_newline(observation)
        or session.get("id") != source.get("thread_id")
        or turn.get("turn_id") != source.get("turn_id")
        or turn.get("model") != effective_model
        or session.get("source") != "exec"
        or not _is_nonempty_string(session.get("cwd"))
        or _version_number(session.get("cli_version"))
        != _version_number(binary.get("version"))
        or not isinstance(argv, list)
        or not all(isinstance(item, str) for item in argv)
        or len(argv) < 2
        or argv[:2] != ["codex", "exec"]
        or argv.count("--json") != 1
        or argv.count("--cd") != 1
        or not _is_sha256(command.get("prompt_sha256"))
        or _argv_has_model_override(argv)
        or (
            require_fresh_session
            and any(item.strip().lower() == "resume" for item in argv)
        )
    ):
        return None
    try:
        command_workdir = argv[argv.index("--cd") + 1]
    except (ValueError, IndexError):
        return None
    if command_workdir != session.get("cwd"):
        return None
    if expected_role == "verification-agent-falsification-reviewer-v1":
        lane_root = Path(str(command_workdir)).resolve().parent
        expected_review_argv = _falsification_review_argv(
            workdir=Path(str(command_workdir)),
            output_path=lane_root / "falsification-review-output.json",
            output_schema_path=(
                lane_root / "falsification-review-output-schema.json"
            ),
        )
        if tuple(argv) != expected_review_argv:
            return None
    thread_id = source.get("thread_id")
    turn_id = source.get("turn_id")
    if not _is_nonempty_string(thread_id) or not _is_nonempty_string(turn_id):
        return None
    return _CodexInvocationIdentity(
        invocation_id=f"{thread_id}:{turn_id}",
        thread_id=str(thread_id),
        turn_id=str(turn_id),
        receipt_sha256=sha256_file(path),
        effective_model=str(effective_model),
        workdir=str(command_workdir),
    )


def _production_identities(
    identity: Mapping[str, Any],
    *,
    lane_id: str,
    repository_root: Path,
) -> tuple[_CodexInvocationIdentity, ...] | None:
    invocations = identity.get("invocations")
    if (
        identity.get("schema_version") != 2
        or identity.get("status") != "complete"
        or identity.get("backend") != BACKEND
        or identity.get("selection_policy") != "codex_cli_default"
        or identity.get("requested_model") is not None
        or identity.get("model_override_present") is not False
        or not isinstance(invocations, list)
        or not invocations
    ):
        return None
    observed: list[_CodexInvocationIdentity] = []
    for item in invocations:
        reference = (
            item.get("identity_receipt")
            if isinstance(item, Mapping)
            else None
        )
        role = item.get("role") if isinstance(item, Mapping) else None
        if (
            role not in {"journey_driver", "l3_semantic_judge"}
            or not _artifact_reference_is_bound(reference)
            or not str(reference.get("path", "")).startswith(
                f"{R4_ARTIFACT_ROOT}/{lane_id}/production-identities/"
            )
        ):
            return None
        path = _bound_file(repository_root, reference)
        if path is None:
            return None
        parsed = _codex_identity(path, expected_role=str(role))
        if (
            parsed is None
            or item.get("invocation_id") != parsed.invocation_id
            or item.get("effective_model") != parsed.effective_model
            or item.get("identity_sha256") != parsed.receipt_sha256
        ):
            return None
        observed.append(parsed)
    invocation_ids = {item.invocation_id for item in observed}
    identity_hashes = {item.receipt_sha256 for item in observed}
    if (
        len(invocation_ids) != len(observed)
        or len(identity_hashes) != len(observed)
        or not any(
            item.get("role") == "journey_driver"
            for item in invocations
            if isinstance(item, Mapping)
        )
        or identity.get("production_invocation_id") not in invocation_ids
    ):
        return None
    return tuple(observed)


def _runner_setup_is_eligible(
    setup: Mapping[str, Any],
) -> bool:
    operations = setup.get("operations")
    if not isinstance(operations, list) or len(operations) != 2:
        return False
    clear, launch = operations
    duration = setup.get("duration_seconds")
    return (
        set(setup)
        == {
            "schema_version",
            "status",
            "device",
            "launch_requested",
            "operations",
            "duration_seconds",
        }
        and setup.get("schema_version") == 1
        and setup.get("status") == "passed"
        and setup.get("device") == DEVICE
        and setup.get("launch_requested") is True
        and isinstance(clear, Mapping)
        and set(clear)
        == {"operation", "command", "returncode", "stdout", "stderr"}
        and clear.get("operation") == "logcat_clear"
        and clear.get("returncode") == 0
        and clear.get("command") == ["adb", "-s", DEVICE, "logcat", "-c"]
        and isinstance(clear.get("stdout"), str)
        and isinstance(clear.get("stderr"), str)
        and isinstance(launch, Mapping)
        and set(launch)
        == {"operation", "command", "returncode", "stdout", "stderr"}
        and launch.get("operation") == "explicit_launch"
        and launch.get("returncode") == 0
        and launch.get("command")
        == [
            "adb",
            "-s",
            DEVICE,
            "shell",
            "am",
            "start",
            "-n",
            f"{PACKAGE}/{ACTIVITY}",
        ]
        and isinstance(launch.get("stdout"), str)
        and isinstance(launch.get("stderr"), str)
        and isinstance(duration, (int, float))
        and not isinstance(duration, bool)
        and duration >= 0
    )


def _production_admission_is_eligible(
    receipt: Mapping[str, Any],
    *,
    lane_id: str,
    role: str,
    repository_root: Path,
) -> bool:
    checks = receipt.get("checks")
    namespace = receipt.get("artifact_namespace")
    host = receipt.get("host")
    runner_policy = receipt.get("runner_policy")
    options = (
        runner_policy.get("options")
        if isinstance(runner_policy, Mapping)
        else None
    )
    tools = (
        runner_policy.get("tools")
        if isinstance(runner_policy, Mapping)
        else None
    )
    model_selection = (
        tools.get("model_selection") if isinstance(tools, Mapping) else None
    )
    target = receipt.get("target")
    run_spec = receipt.get("run_spec")
    side_effects = receipt.get("side_effects")
    apk_locator = (
        target.get("apk_locator")
        if isinstance(target, Mapping)
        else None
    )
    if role == "defect":
        expected_commit = DEFECT_COMMIT
    elif role == "control":
        expected_commit = PROJECT_TARGET_COMMIT
    else:
        return False
    expected_run_spec = (
        repository_root
        / "bench/m9/recovery-v2/run-specs"
        / f"{lane_id}.yaml"
    ).resolve()
    expected_lane_root = (
        repository_root / R4_ARTIFACT_ROOT / lane_id
    ).resolve()
    expected_artifact_dir = (expected_lane_root / "artifacts").resolve()
    if not all(
        isinstance(value, Mapping)
        for value in (
            checks,
            namespace,
            host,
            runner_policy,
            options,
            tools,
            model_selection,
            target,
            run_spec,
            side_effects,
            apk_locator,
        )
    ):
        return False
    host_worktree = host.get("worktree")
    expected_checks = {
        "artifact_namespace",
        "host_identity",
        "run_spec_bytes",
        "runner_policy",
        "target_declaration",
    }
    expected_option_fields = {
        "device",
        "workdir",
        "artifact_dir",
        "expected_source_commit",
        "launch",
        "requested_driver_model",
        "requested_l3_model",
        "backend",
        "android_bin",
        "adb_bin",
        "codex_bin",
        "runner_policy_version",
        "allow_host_project_subdir",
    }
    tool_receipts = [tools.get(name) for name in ("adb", "android", "codex")]
    try:
        namespace_artifact_dir = Path(
            str(namespace.get("artifact_dir"))
        ).resolve()
        namespace_run_dir = Path(str(namespace.get("run_dir"))).resolve()
        option_artifact_dir = Path(
            str(options.get("artifact_dir"))
        ).resolve()
        workdir = Path(str(options.get("workdir"))).resolve()
        host_project = Path(str(host.get("host_project"))).resolve()
        host_repository = Path(str(host.get("repository_root"))).resolve()
        run_spec_path = Path(str(run_spec.get("path"))).resolve()
        target_relative_to = Path(
            str(apk_locator.get("relative_to"))
        ).resolve()
    except OSError:
        return False
    return (
        set(receipt)
        == {
            "schema_version",
            "status",
            "admitted",
            "reasons",
            "run_spec",
            "host",
            "target",
            "runner_policy",
            "artifact_namespace",
            "checks",
            "side_effects",
        }
        and receipt.get("schema_version") == 1
        and receipt.get("status") == "admitted"
        and receipt.get("admitted") is True
        and receipt.get("reasons") == []
        and set(checks) == expected_checks
        and all(
            isinstance(checks[name], Mapping)
            and checks[name].get("status") == "passed"
            for name in expected_checks
        )
        and checks["run_spec_bytes"].get("sha256")
        == sha256_file(expected_run_spec)
        and checks["run_spec_bytes"].get("bytes")
        == expected_run_spec.stat().st_size
        and set(namespace)
        == {"run_dir", "artifact_dir", "formal_outputs_absent"}
        and namespace.get("formal_outputs_absent") is True
        and namespace_artifact_dir == expected_artifact_dir
        and namespace_run_dir == expected_lane_root
        and set(host)
        == {
            "repository_root",
            "host_project",
            "origin",
            "commit",
            "worktree",
            "host_project_within_repository",
        }
        and option_artifact_dir == expected_artifact_dir
        and workdir == host_project == host_repository
        and host.get("origin") == SOURCE_ORIGIN
        and host.get("commit") == expected_commit
        and host.get("host_project_within_repository") is False
        and isinstance(host_worktree, Mapping)
        and set(host_worktree) == {"clean", "status_sha256"}
        and host_worktree.get("clean") is True
        and host_worktree.get("status_sha256")
        == sha256_bytes(b"")
        and set(runner_policy) == {"backend", "version", "options", "tools"}
        and runner_policy.get("backend") == BACKEND
        and runner_policy.get("version") == RUNNER_POLICY
        and set(options) == expected_option_fields
        and options.get("backend") == BACKEND
        and options.get("device") == DEVICE
        and options.get("expected_source_commit") == expected_commit
        and options.get("launch") is True
        and options.get("requested_driver_model") is None
        and options.get("requested_l3_model") is None
        and options.get("android_bin") == "android"
        and options.get("adb_bin") == "adb"
        and options.get("codex_bin") == "codex"
        and options.get("runner_policy_version") == RUNNER_POLICY
        and options.get("allow_host_project_subdir") is False
        and set(tools) == {"android", "adb", "codex", "model_selection"}
        and all(
            isinstance(item, Mapping)
            and set(item) == {"requested", "resolved_path", "sha256"}
            and item.get("requested")
            == options.get(f"{name}_bin")
            and _is_nonempty_string(item.get("resolved_path"))
            and _is_sha256(item.get("sha256"))
            for name, item in zip(
                ("adb", "android", "codex"),
                tool_receipts,
                strict=True,
            )
        )
        and set(model_selection)
        == {"journey_driver", "l3_semantic_judge"}
        and all(
            isinstance(model_selection.get(name), Mapping)
            and set(model_selection[name])
            == {"requested_model", "model_override_present", "policy"}
            and model_selection[name].get("requested_model") is None
            and model_selection[name].get("model_override_present") is False
            and model_selection[name].get("policy") == "codex_cli_default"
            for name in ("journey_driver", "l3_semantic_judge")
        )
        and set(run_spec)
        == {"path", "sha256", "serialized_bytes", "scenario"}
        and run_spec_path == expected_run_spec
        and run_spec.get("scenario") == lane_id
        and run_spec.get("sha256") == sha256_file(expected_run_spec)
        and run_spec.get("serialized_bytes") == expected_run_spec.stat().st_size
        and set(target) == {"package", "activity", "apk_locator"}
        and target.get("package") == PACKAGE
        and target.get("activity") == ACTIVITY
        and set(apk_locator) == {"glob", "relative_to"}
        and apk_locator.get("glob") == APK_GLOB
        and target_relative_to == workdir
        and set(side_effects)
        == {"agent", "build", "device", "external", "declaration"}
        and all(
            side_effects.get(name) is False
            for name in ("agent", "build", "device", "external")
        )
        and _is_nonempty_string(side_effects.get("declaration"))
    )


def _png_dimensions(path: Path) -> tuple[int, int] | None:
    """Validate a complete non-interlaced PNG and return its dimensions."""

    try:
        payload = path.read_bytes()
    except OSError:
        return None
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    offset = 8
    chunks: list[tuple[bytes, bytes]] = []
    try:
        while offset < len(payload):
            if offset + 12 > len(payload):
                return None
            length = struct.unpack(">I", payload[offset : offset + 4])[0]
            chunk_type = payload[offset + 4 : offset + 8]
            chunk_end = offset + 12 + length
            if chunk_end > len(payload):
                return None
            data = payload[offset + 8 : offset + 8 + length]
            expected_crc = struct.unpack(
                ">I",
                payload[offset + 8 + length : chunk_end],
            )[0]
            if zlib.crc32(chunk_type + data) & 0xFFFFFFFF != expected_crc:
                return None
            chunks.append((chunk_type, data))
            offset = chunk_end
            if chunk_type == b"IEND":
                break
    except (struct.error, zlib.error):
        return None
    if (
        offset != len(payload)
        or not chunks
        or chunks[0][0] != b"IHDR"
        or chunks[-1] != (b"IEND", b"")
        or sum(kind == b"IHDR" for kind, _ in chunks) != 1
        or sum(kind == b"IEND" for kind, _ in chunks) != 1
        or not any(kind == b"IDAT" and data for kind, data in chunks)
    ):
        return None
    header = chunks[0][1]
    if len(header) != 13:
        return None
    width, height, bit_depth, color_type, compression, filter_method, interlace = (
        struct.unpack(">IIBBBBB", header)
    )
    allowed_depths = {
        0: {1, 2, 4, 8, 16},
        2: {8, 16},
        3: {1, 2, 4, 8},
        4: {8, 16},
        6: {8, 16},
    }
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
    if (
        width < 1
        or height < 1
        or width * height > 50_000_000
        or color_type not in allowed_depths
        or bit_depth not in allowed_depths[color_type]
        or compression != 0
        or filter_method != 0
        or interlace != 0
    ):
        return None
    compressed = b"".join(
        data for kind, data in chunks if kind == b"IDAT"
    )
    try:
        decoded = zlib.decompress(compressed)
    except zlib.error:
        return None
    scanline_bytes = (
        width * channels[color_type] * bit_depth + 7
    ) // 8
    expected_bytes = height * (scanline_bytes + 1)
    if len(decoded) != expected_bytes:
        return None
    if any(
        decoded[row * (scanline_bytes + 1)] > 4
        for row in range(height)
    ):
        return None
    return width, height


def _raw_probe_is_eligible(
    *,
    bound_paths: Mapping[str, Path],
    lane_id: str,
    token: str,
    conclusion: object,
) -> bool:
    before = _read_json_object(bound_paths["layout_before"])
    after = _read_json_object(bound_paths["layout_after"])
    event = _read_json_object(bound_paths["rotation_event"])
    if not all(isinstance(value, Mapping) for value in (before, after, event)):
        return False
    expected_after_visible = conclusion == "locally_rejected"
    before_observation = before.get("text_input_observation")
    after_observation = after.get("text_input_observation")
    if not all(
        isinstance(value, Mapping)
        for value in (before_observation, after_observation)
    ):
        return False

    def text_input_observation_is_eligible(
        observation: Mapping[str, Any],
        *,
        token_visible: bool,
    ) -> bool:
        expected_count = 1 if token_visible else 0
        return (
            observation.get("field_semantics") == "content-desc:Text input"
            and observation.get("input_field_anchor_count") == 1
            and observation.get("input_field_present") is True
            and observation.get("exact_token_node_count") == expected_count
            and observation.get("editable_exact_token_node_count")
            == expected_count
            and observation.get("bound_exact_token_node_count")
            == expected_count
            and observation.get("exact_token_visible_in_input")
            is token_visible
        )

    try:
        logcat = bound_paths["filtered_logcat"].read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    before_dimensions = _png_dimensions(bound_paths["screenshot_before"])
    after_dimensions = _png_dimensions(bound_paths["screenshot_after"])
    return (
        before_dimensions is not None
        and before_dimensions[0] < before_dimensions[1]
        and after_dimensions is not None
        and after_dimensions[0] > after_dimensions[1]
        and bool(logcat.strip())
        and before.get("schema_version") == 1
        and before.get("lane_id") == lane_id
        and before.get("checkpoint") == "before"
        and before.get("orientation") == "portrait"
        and before.get("probe_token") == token
        and before.get("token_visible") is True
        and text_input_observation_is_eligible(
            before_observation,
            token_visible=True,
        )
        and after.get("schema_version") == 1
        and after.get("lane_id") == lane_id
        and after.get("checkpoint") == "after"
        and after.get("orientation") == "landscape"
        and after.get("probe_token") == token
        and after.get("token_visible") is expected_after_visible
        and text_input_observation_is_eligible(
            after_observation,
            token_visible=expected_after_visible,
        )
        and event.get("schema_version") == 1
        and event.get("lane_id") == lane_id
        and event.get("status") == "passed"
        and event.get("event") == "rotate"
        and event.get("rotation_count") == 1
        and event.get("before") == "user_rotation=0"
        and event.get("after") == "user_rotation=1"
        and event.get("accelerometer_rotation") == "0"
        and event.get("activity_recreation_observed") is True
        and event.get("retyped_after_boundary") is False
        and event.get("repaired_after_boundary") is False
    )


def _review_input_is_role_blind(path: Path) -> bool:
    """Reject role, expected-result, or source-assignment material by bytes."""

    try:
        payload = path.read_bytes()
    except OSError:
        return False
    lowered_bytes = payload.lower()
    byte_fragments = (
        b"expected_result",
        b"expected result",
        b"expected_outcome",
        b"expected outcome",
        b"ground truth",
        b"gold role",
        b"source role",
        b"lane role",
        b"role assignment",
        DEFECT_COMMIT.encode(),
        PROJECT_TARGET_COMMIT.encode(),
        DEFECT_TREE.encode(),
        PROJECT_TARGET_TREE.encode(),
    )
    if (
        any(fragment in lowered_bytes for fragment in byte_fragments)
        or re.search(
            rb"(?<![a-z0-9_])(?:defect|control)(?![a-z0-9_])",
            lowered_bytes,
        )
    ):
        return False
    try:
        text = unicodedata.normalize(
            "NFKC",
            payload.decode("utf-8"),
        ).casefold()
    except UnicodeDecodeError:
        return True
    words = re.sub(r"[\W_]+", " ", text)
    if re.search(r"\b(?:defect|control)\b", words):
        return False
    if any(
        phrase in words
        for phrase in (
            "expected result",
            "expected outcome",
            "ground truth",
            "gold role",
            "source role",
            "lane role",
            "role assignment",
            "auditor role",
        )
    ):
        return False
    if path.suffix != ".json":
        return True
    value = _read_json_object(path)
    if value is None:
        return False

    def disclosed(item: object) -> bool:
        if isinstance(item, Mapping):
            for key, child in item.items():
                normalized_key = re.sub(
                    r"[\W_]+",
                    "_",
                    unicodedata.normalize("NFKC", str(key)).casefold(),
                ).strip("_")
                if normalized_key in {
                    "expected_result",
                    "expected_outcome",
                    "ground_truth",
                    "gold_role",
                    "source_role",
                    "lane_role",
                    "role_assignment",
                    "auditor_role",
                }:
                    return True
                if (
                    normalized_key == "role"
                    and isinstance(child, str)
                    and child.casefold() in {"defect", "control"}
                ):
                    return True
                if disclosed(child):
                    return True
            return False
        if isinstance(item, (list, tuple)):
            return any(disclosed(child) for child in item)
        return False

    return not disclosed(value)


def _execution_review_summary(
    execution_record: Mapping[str, Any],
) -> dict[str, Any]:
    timing = execution_record.get("timing")
    execution = execution_record.get("execution")
    evidence_refs = execution_record.get("evidence_refs")
    provenance = (
        evidence_refs.get("execution_provenance")
        if isinstance(evidence_refs, Mapping)
        else None
    )
    return {
        "schema_version": 1,
        "kind": "execution_accountability_summary",
        "lane_id": execution_record.get("scenario"),
        "attempt_id": execution_record.get("attempt_id"),
        "lifecycle_state": execution_record.get("lifecycle_state"),
        "accountable": (
            execution.get("accounting_eligible")
            if isinstance(execution, Mapping)
            else None
        ),
        "process_exit_code": (
            execution_record.get("process_outcome", {}).get("exit_code")
            if isinstance(execution_record.get("process_outcome"), Mapping)
            else None
        ),
        "started_at": execution_record.get("started_at"),
        "finished_at": execution_record.get("finished_at"),
        "total_seconds": (
            timing.get("total_seconds")
            if isinstance(timing, Mapping)
            else None
        ),
        "phase_errors": execution_record.get("phase_errors"),
        "execution_provenance_sha256": (
            provenance.get("sha256")
            if isinstance(provenance, Mapping)
            else None
        ),
    }


def build_execution_review_summary(
    execution_record: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the role-blind accountability summary used by an R4 review."""

    return _execution_review_summary(execution_record)


def _review_context_is_eligible(
    context: Mapping[str, Any],
    *,
    lane_id: str,
    expected_workdir: str,
    repository_root: Path,
) -> bool:
    artifacts = context.get("input_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return False
    expected_names = {
        "execution-summary.json": None,
        "effective-execution-identity.json": (
            "effective-execution-identity.json"
        ),
        "raw/screenshots/before.png": "raw/screenshots/before.png",
        "raw/screenshots/after.png": "raw/screenshots/after.png",
        "raw/layout/before.json": "raw/layout/before.json",
        "raw/layout/after.json": "raw/layout/after.json",
        "raw/logcat/rotation.txt": "raw/logcat/rotation.txt",
        "rotation-event.json": "rotation-event.json",
        "oracle-receipt.json": "oracle-receipt.json",
        "finding.json": "finding.json",
        "claim-boundary.json": "claim-boundary.json",
    }
    lane_root = (repository_root / R4_ARTIFACT_ROOT / lane_id).resolve()
    review_root = (lane_root / "review-input").resolve()
    try:
        identity_workdir = Path(expected_workdir).resolve()
    except OSError:
        return False
    if identity_workdir != review_root or not review_root.is_dir():
        return False
    observed: dict[str, Path] = {}
    ordered_names: list[str] = []
    for reference in artifacts:
        if not _artifact_reference_is_bound(reference):
            return False
        prefix = f"{R4_ARTIFACT_ROOT}/{lane_id}/review-input/"
        path_value = str(reference.get("path"))
        if not path_value.startswith(prefix):
            return False
        name = path_value.removeprefix(prefix)
        if name in observed:
            return False
        path = _bound_file(repository_root, reference)
        if path is None:
            return False
        observed[name] = path
        ordered_names.append(name)
    if (
        set(observed) != set(expected_names)
        or tuple(ordered_names) != _REVIEW_INPUT_FILES
    ):
        return False
    try:
        workspace_entries = {
            path.relative_to(review_root).as_posix(): path
            for path in review_root.rglob("*")
            if path.is_file()
        }
        if any(path.is_symlink() for path in review_root.rglob("*")):
            return False
    except OSError:
        return False
    if set(workspace_entries) != set(expected_names):
        return False
    execution_record = _read_json_object(lane_root / "execution-record.json")
    if execution_record is None:
        return False
    for review_name, source_name in expected_names.items():
        review_path = observed[review_name]
        if workspace_entries[review_name].resolve() != review_path:
            return False
        if source_name is None:
            summary = _read_json_object(review_path)
            if (
                summary is None
                or canonical_json_bytes(summary)
                != canonical_json_bytes(
                    _execution_review_summary(execution_record)
                )
            ):
                return False
        else:
            source_path = (lane_root / source_name).resolve()
            if (
                not source_path.is_file()
                or sha256_file(review_path) != sha256_file(source_path)
            ):
                return False
        if not _review_input_is_role_blind(review_path):
            return False
    return (
        context.get("schema_version") == 2
        and context.get("lane_id") == lane_id
        and context.get("clean_context") is True
        and context.get("source_role_disclosed") is False
        and context.get("expected_result_disclosed") is False
        and context.get("production_oracle_path_used") is False
        and context.get("workdir") == expected_workdir == str(review_root)
    )


def _review_output_schema(input_refs: Sequence[str]) -> dict[str, Any]:
    """Return the exact semantic-only output schema shown to Codex."""

    if tuple(input_refs) != _REVIEW_INPUT_FILES:
        raise M9RecoveryQualificationError(
            ["review prompt inputs must be the exact workspace-relative set"]
        )
    dimension_item = {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "status", "analysis", "evidence_refs"],
        "properties": {
            "id": {"enum": list(_REVIEW_DIMENSIONS)},
            "status": {
                "enum": ["supported", "challenged", "inconclusive"]
            },
            "analysis": {"type": "string", "minLength": 1},
            "evidence_refs": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": {"enum": list(input_refs)},
            },
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "status",
            "outcome",
            "dimensions",
            "reasons",
            "claim_boundary",
            "source_role_disclosed",
            "expected_result_disclosed",
        ],
        "properties": {
            "schema_version": {"const": 1},
            "status": {"const": "complete"},
            "outcome": {
                "enum": ["survived", "challenged", "inconclusive"]
            },
            "dimensions": {
                "type": "array",
                "minItems": len(_REVIEW_DIMENSIONS),
                "maxItems": len(_REVIEW_DIMENSIONS),
                "items": dimension_item,
            },
            "reasons": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
            "claim_boundary": {"const": LOCAL_CLAIM_BOUNDARY},
            "source_role_disclosed": {"const": False},
            "expected_result_disclosed": {"const": False},
        },
    }


def _expected_review_prompt(input_refs: Sequence[str]) -> str:
    """Render the complete executable prompt using workspace-relative paths."""

    schema = _review_output_schema(input_refs)
    return (
        "Independently challenge the candidate Finding using only the "
        "allowlisted files below. The current working directory is the "
        "isolated review-input directory, and every listed path is relative "
        "to it. Do not inspect parent directories or any unlisted file.\n\n"
        "Allowlisted inputs, in required order:\n"
        + "\n".join(f"- {reference}" for reference in input_refs)
        + "\n\nAssess all six dimensions in the schema's exact order. "
        "Use `survived` only when every dimension is `supported` and "
        "`reasons` is empty. Use `challenged` when at least one dimension is "
        "`challenged`; use `inconclusive` when none is challenged and at "
        "least one is inconclusive. For either non-survived outcome, provide "
        "at least one non-empty reason. Evidence references must be selected "
        "only from the allowlist above.\n\nReturn only one JSON object that "
        "conforms exactly to this JSON Schema; do not add Markdown fences or "
        "runtime identifiers/checksums. The runner records invocation "
        "identity and artifact checksums after the command completes.\n"
        + json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )


def prepare_falsification_review_invocation(
    *,
    lane_id: str,
    repository_root: Path,
) -> FalsificationReviewInvocationPlan:
    """Persist the pre-invocation prompt/schema/ledger without invoking Codex."""

    if lane_id not in LANE_IDS:
        raise M9RecoveryQualificationError(["unknown review lane"])
    repository_root = Path(repository_root).resolve()
    lane_root = (repository_root / R4_ARTIFACT_ROOT / lane_id).resolve()
    review_root = (lane_root / "review-input").resolve()
    context_path = lane_root / "falsification-review-context.json"
    context = _read_json_object(context_path)
    if (
        context is None
        or not _review_context_is_eligible(
            context,
            lane_id=lane_id,
            expected_workdir=str(review_root),
            repository_root=repository_root,
        )
    ):
        raise M9RecoveryQualificationError(
            ["review context is not an exact role-blind workspace"]
        )
    prompt = _expected_review_prompt(_REVIEW_INPUT_FILES)
    prompt_path = lane_root / "falsification-review-prompt.md"
    output_schema_path = (
        lane_root / "falsification-review-output-schema.json"
    )
    output_path = lane_root / "falsification-review-output.json"
    events_path = lane_root / "falsification-review-events.jsonl"
    identity_path = lane_root / "falsification-review-identity.json"
    invocation_path = lane_root / "falsification-review-invocation.json"
    receipt_path = lane_root / "falsification-review.json"
    reserved_outputs = (
        prompt_path,
        output_schema_path,
        output_path,
        events_path,
        identity_path,
        invocation_path,
        receipt_path,
    )
    if any(path.exists() for path in reserved_outputs):
        raise M9RecoveryQualificationError(
            ["review invocation namespace is not fresh"]
        )
    output_schema = _review_output_schema(_REVIEW_INPUT_FILES)
    write_bytes_artifact(prompt_path, prompt.encode("utf-8"))
    write_json_artifact(output_schema_path, output_schema)
    argv = _falsification_review_argv(
        workdir=review_root,
        output_path=output_path,
        output_schema_path=output_schema_path,
    )
    prompt_sha256 = sha256_file(prompt_path)
    output_schema_sha256 = sha256_file(output_schema_path)
    write_json_artifact(
        invocation_path,
        {
            "schema_version": 2,
            "role": "verification-agent-falsification-reviewer-v1",
            "call_index": 1,
            "requested_model": None,
            "argv_without_prompt": list(argv),
            "prompt_transport": "final_argv",
            "prompt_sha256": prompt_sha256,
            "output_schema_sha256": output_schema_sha256,
        },
    )
    return FalsificationReviewInvocationPlan(
        lane_id=lane_id,
        workdir=review_root,
        argv_without_prompt=argv,
        prompt=prompt,
        prompt_transport="final_argv",
        prompt_path=prompt_path,
        prompt_sha256=prompt_sha256,
        output_schema_path=output_schema_path,
        output_schema_sha256=output_schema_sha256,
        output_path=output_path,
        events_path=events_path,
        identity_path=identity_path,
        invocation_ledger_path=invocation_path,
    )


def _semantic_review_output_is_valid(
    output: Mapping[str, Any],
    *,
    allowed_refs: set[str],
) -> bool:
    if (
        set(output)
        != {
            "schema_version",
            "status",
            "outcome",
            "dimensions",
            "reasons",
            "claim_boundary",
            "source_role_disclosed",
            "expected_result_disclosed",
        }
        or output.get("schema_version") != 1
        or output.get("status") != "complete"
        or output.get("outcome")
        not in {"survived", "challenged", "inconclusive"}
        or output.get("claim_boundary") != LOCAL_CLAIM_BOUNDARY
        or output.get("source_role_disclosed") is not False
        or output.get("expected_result_disclosed") is not False
    ):
        return False
    reasons = output.get("reasons")
    dimensions = output.get("dimensions")
    if (
        not isinstance(reasons, list)
        or any(not _is_nonempty_string(reason) for reason in reasons)
        or not isinstance(dimensions, list)
        or len(dimensions) != len(_REVIEW_DIMENSIONS)
    ):
        return False
    statuses: list[str] = []
    for expected_id, dimension in zip(
        _REVIEW_DIMENSIONS,
        dimensions,
        strict=True,
    ):
        if not isinstance(dimension, Mapping):
            return False
        evidence_refs = dimension.get("evidence_refs")
        status = dimension.get("status")
        if (
            set(dimension) != {"id", "status", "analysis", "evidence_refs"}
            or dimension.get("id") != expected_id
            or status not in {"supported", "challenged", "inconclusive"}
            or not _is_nonempty_string(dimension.get("analysis"))
            or not isinstance(evidence_refs, list)
            or not evidence_refs
            or any(not isinstance(item, str) for item in evidence_refs)
            or len(evidence_refs) != len(set(evidence_refs))
            or not set(evidence_refs).issubset(allowed_refs)
        ):
            return False
        statuses.append(str(status))
    outcome = output.get("outcome")
    if outcome == "survived":
        return set(statuses) == {"supported"} and reasons == []
    if outcome == "challenged":
        return "challenged" in statuses and bool(reasons)
    return (
        "challenged" not in statuses
        and "inconclusive" in statuses
        and bool(reasons)
    )


def _review_result_is_eligible(
    *,
    bound_paths: Mapping[str, Path],
    lane_id: str,
    review: Mapping[str, Any],
    context: Mapping[str, Any],
    identity: _CodexInvocationIdentity,
    require_survived: bool = True,
) -> bool:
    output_path = bound_paths["falsification_review_output"]
    output_schema_path = bound_paths[
        "falsification_review_output_schema"
    ]
    events_path = bound_paths["falsification_review_events"]
    invocation_path = bound_paths["falsification_review_invocation"]
    prompt_path = bound_paths["falsification_review_prompt"]
    try:
        output_text = output_path.read_text(encoding="utf-8").strip()
        prompt_text = prompt_path.read_text(encoding="utf-8")
        output = json.loads(
            output_text,
            object_pairs_hook=_unique_pairs,
        )
        events = [
            json.loads(line, object_pairs_hook=_unique_pairs)
            for line in events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        invocation = json.loads(
            invocation_path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_pairs,
        )
        identity_payload = _read_json_object(
            bound_paths["falsification_review_identity"]
        )
        output_schema = _read_json_object(output_schema_path)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        M9RecoveryQualificationError,
    ):
        return False
    if (
        not isinstance(output, Mapping)
        or not isinstance(invocation, Mapping)
        or not isinstance(identity_payload, Mapping)
        or not isinstance(output_schema, Mapping)
        or len(events) < 3
        or any(not isinstance(event, Mapping) for event in events)
    ):
        return False
    context_artifacts = context.get("input_artifacts")
    if not isinstance(context_artifacts, list):
        return False
    prefix = f"{R4_ARTIFACT_ROOT}/{lane_id}/review-input/"
    ordered_refs: list[str] = []
    for item in context_artifacts:
        if (
            not _artifact_reference_is_bound(item)
            or not str(item.get("path")).startswith(prefix)
        ):
            return False
        ordered_refs.append(str(item["path"]).removeprefix(prefix))
    if tuple(ordered_refs) != _REVIEW_INPUT_FILES:
        return False
    allowed_refs = set(ordered_refs)
    if not _semantic_review_output_is_valid(
        output,
        allowed_refs=allowed_refs,
    ):
        return False
    thread_events = [
        event for event in events if event.get("type") == "thread.started"
    ]
    agent_messages = [
        event.get("item")
        for event in events
        if event.get("type") == "item.completed"
        and isinstance(event.get("item"), Mapping)
        and event["item"].get("type") == "agent_message"
    ]
    turn_events = [
        event for event in events if event.get("type") == "turn.completed"
    ]
    return (
        review.get("schema_version") == 2
        and review.get("review_id") == f"falsification-review-{lane_id}"
        and review.get("lane_id") == lane_id
        and review.get("invocation_id") == identity.invocation_id
        and review.get("status") == "complete"
        and review.get("outcome") == output.get("outcome")
        and (
            not require_survived
            or (
                output.get("outcome") == "survived"
                and all(
                    item.get("status") == "supported"
                    for item in output["dimensions"]
                )
            )
        )
        and review.get("clean_context_sha256")
        == sha256_file(bound_paths["falsification_review_context"])
        and review.get("candidate_finding_id") == f"finding-{lane_id}"
        and review.get("candidate_finding_sha256")
        == sha256_file(bound_paths["finding"])
        and len(thread_events) == 1
        and thread_events[0].get("thread_id") == identity.thread_id
        and len(agent_messages) == 1
        and agent_messages[0].get("text", "").strip() == output_text
        and len(turn_events) == 1
        and prompt_text == _expected_review_prompt(ordered_refs)
        and canonical_json_bytes(output_schema)
        == canonical_json_bytes(_review_output_schema(ordered_refs))
        and set(invocation)
        == {
            "schema_version",
            "role",
            "call_index",
            "requested_model",
            "argv_without_prompt",
            "prompt_transport",
            "prompt_sha256",
            "output_schema_sha256",
        }
        and invocation.get("schema_version") == 2
        and invocation.get("role")
        == "verification-agent-falsification-reviewer-v1"
        and invocation.get("call_index") == 1
        and invocation.get("requested_model") is None
        and invocation.get("prompt_transport") == "final_argv"
        and invocation.get("argv_without_prompt")
        == identity_payload.get("command", {}).get("argv_without_prompt")
        and invocation.get("prompt_sha256")
        == identity_payload.get("command", {}).get("prompt_sha256")
        == sha256_file(prompt_path)
        and invocation.get("output_schema_sha256")
        == sha256_file(output_schema_path)
        and review.get("output_sha256") == sha256_file(output_path)
        and review.get("output_schema_sha256")
        == sha256_file(output_schema_path)
        and review.get("events_sha256") == sha256_file(events_path)
        and review.get("invocation_ledger_sha256")
        == sha256_file(invocation_path)
        and review.get("prompt_sha256") == sha256_file(prompt_path)
    )


def build_falsification_review_receipt(
    *,
    lane_id: str,
    repository_root: Path,
    production_invocation_id: str,
    production_identity_sha256: str,
) -> dict[str, Any]:
    """Build the runner-owned envelope after a review command completes."""

    if (
        lane_id not in LANE_IDS
        or not _is_nonempty_string(production_invocation_id)
        or not _is_sha256(production_identity_sha256)
    ):
        raise M9RecoveryQualificationError(
            ["review receipt production identity is incomplete"]
        )
    repository_root = Path(repository_root).resolve()
    lane_root = (repository_root / R4_ARTIFACT_ROOT / lane_id).resolve()
    bound_paths = {
        key: lane_root / filename
        for key, filename in _ATTEMPT_EVIDENCE_REF_FILES.items()
        if key.startswith("falsification_review")
    }
    bound_paths["finding"] = lane_root / "finding.json"
    identity = _codex_identity(
        bound_paths["falsification_review_identity"],
        expected_role="verification-agent-falsification-reviewer-v1",
        require_fresh_session=True,
    )
    context = _read_json_object(
        bound_paths["falsification_review_context"]
    )
    output = _read_json_object(bound_paths["falsification_review_output"])
    if (
        identity is None
        or context is None
        or output is None
        or identity.invocation_id == production_invocation_id
        or identity.receipt_sha256 == production_identity_sha256
        or not _review_context_is_eligible(
            context,
            lane_id=lane_id,
            expected_workdir=identity.workdir,
            repository_root=repository_root,
        )
    ):
        raise M9RecoveryQualificationError(
            ["review runtime identity, output, or clean context is invalid"]
        )

    def evidence_path(path: Path) -> str:
        try:
            return path.resolve().relative_to(repository_root).as_posix()
        except ValueError as error:
            raise M9RecoveryQualificationError(
                ["review artifact is outside the evidence repository"]
            ) from error

    receipt = {
        "schema_version": 2,
        "review_id": f"falsification-review-{lane_id}",
        "lane_id": lane_id,
        "status": "complete",
        "outcome": output.get("outcome"),
        "candidate_finding_id": f"finding-{lane_id}",
        "candidate_finding_sha256": sha256_file(bound_paths["finding"]),
        "invocation_id": identity.invocation_id,
        "identity_path": evidence_path(
            bound_paths["falsification_review_identity"]
        ),
        "identity_sha256": identity.receipt_sha256,
        "production_invocation_id": production_invocation_id,
        "production_identity_sha256": production_identity_sha256,
        "clean_context": True,
        "clean_context_path": evidence_path(
            bound_paths["falsification_review_context"]
        ),
        "clean_context_sha256": sha256_file(
            bound_paths["falsification_review_context"]
        ),
        "output_path": evidence_path(
            bound_paths["falsification_review_output"]
        ),
        "output_sha256": sha256_file(
            bound_paths["falsification_review_output"]
        ),
        "output_schema_path": evidence_path(
            bound_paths["falsification_review_output_schema"]
        ),
        "output_schema_sha256": sha256_file(
            bound_paths["falsification_review_output_schema"]
        ),
        "events_path": evidence_path(
            bound_paths["falsification_review_events"]
        ),
        "events_sha256": sha256_file(
            bound_paths["falsification_review_events"]
        ),
        "invocation_ledger_path": evidence_path(
            bound_paths["falsification_review_invocation"]
        ),
        "invocation_ledger_sha256": sha256_file(
            bound_paths["falsification_review_invocation"]
        ),
        "prompt_path": evidence_path(
            bound_paths["falsification_review_prompt"]
        ),
        "prompt_sha256": sha256_file(
            bound_paths["falsification_review_prompt"]
        ),
        "backend": BACKEND,
        "requested_model": None,
        "model_selection": "codex_cli_default",
        "effective_model": identity.effective_model,
        "authoritative_observation_source": "codex_cli_event",
        "source_role_disclosed": False,
        "expected_result_disclosed": False,
        "production_oracle_path_used": False,
        "same_provider_family_limitation_disclosed": True,
    }
    if not _review_result_is_eligible(
        bound_paths=bound_paths,
        lane_id=lane_id,
        review=receipt,
        context=context,
        identity=identity,
        require_survived=False,
    ):
        raise M9RecoveryQualificationError(
            ["review command artifacts do not satisfy the frozen contract"]
        )
    return receipt


def persist_falsification_review_receipt(
    *,
    lane_id: str,
    repository_root: Path,
    production_invocation_id: str,
    production_identity_sha256: str,
) -> dict[str, Any]:
    """Create the append-only runner envelope for one terminal review."""

    receipt = build_falsification_review_receipt(
        lane_id=lane_id,
        repository_root=repository_root,
        production_invocation_id=production_invocation_id,
        production_identity_sha256=production_identity_sha256,
    )
    lane_root = (
        Path(repository_root).resolve() / R4_ARTIFACT_ROOT / lane_id
    )
    write_json_artifact(
        lane_root / "falsification-review.json",
        receipt,
    )
    return receipt


def _validate_review_production_binding(
    *,
    lane_id: str,
    repository_root: Path,
    production_invocation_id: str,
    production_identity_sha256: str,
) -> Mapping[str, Any]:
    """Validate the caller's production identity before any review side effect."""

    if (
        lane_id not in LANE_IDS
        or not _is_nonempty_string(production_invocation_id)
        or not _is_sha256(production_identity_sha256)
    ):
        raise M9RecoveryQualificationError(
            ["review receipt production identity is incomplete"]
        )
    repository_root = Path(repository_root).resolve()
    lane_root = (repository_root / R4_ARTIFACT_ROOT / lane_id).resolve()
    identity_path = lane_root / "effective-execution-identity.json"
    identity = _read_json_object(identity_path)
    parsed = (
        _production_identities(
            identity,
            lane_id=lane_id,
            repository_root=repository_root,
        )
        if isinstance(identity, Mapping)
        else None
    )
    if (
        identity is None
        or parsed is None
        or sha256_file(identity_path) != production_identity_sha256
        or identity.get("production_invocation_id")
        != production_invocation_id
        or production_invocation_id
        not in {item.invocation_id for item in parsed}
    ):
        raise M9RecoveryQualificationError(
            ["review production identity does not match the bound lane"]
        )
    return identity


def _review_artifact_reference(
    path: Path,
    *,
    repository_root: Path,
) -> dict[str, str] | None:
    try:
        if not path.is_file():
            return None
        relative = path.resolve().relative_to(repository_root.resolve())
        digest = sha256_file(path)
    except (OSError, ValueError):
        return None
    return {
        "path": relative.as_posix(),
        "sha256": digest,
    }


def _persist_falsification_review_failure(
    *,
    plan: FalsificationReviewInvocationPlan,
    repository_root: Path,
    production_invocation_id: str,
    production_identity_sha256: str,
    stage: str,
    reason: str,
    started_at: str,
    finished_at: str,
    timeout_seconds: int,
    result: CommandResult | None,
    fallback_stderr: str = "",
) -> Path:
    """Persist one terminal no-retry receipt after an attempted invocation."""

    repository_root = Path(repository_root).resolve()
    lane_root = (repository_root / R4_ARTIFACT_ROOT / plan.lane_id).resolve()
    receipt_path = lane_root / "falsification-review.json"
    stdout = result.stdout if result is not None else ""
    stderr = result.stderr if result is not None else fallback_stderr
    returncode = result.returncode if result is not None else None
    artifacts = {
        "context": _review_artifact_reference(
            lane_root / "falsification-review-context.json",
            repository_root=repository_root,
        ),
        "prompt": _review_artifact_reference(
            plan.prompt_path,
            repository_root=repository_root,
        ),
        "output_schema": _review_artifact_reference(
            plan.output_schema_path,
            repository_root=repository_root,
        ),
        "invocation_ledger": _review_artifact_reference(
            plan.invocation_ledger_path,
            repository_root=repository_root,
        ),
        "events": _review_artifact_reference(
            plan.events_path,
            repository_root=repository_root,
        ),
        "semantic_output": _review_artifact_reference(
            plan.output_path,
            repository_root=repository_root,
        ),
        "identity": _review_artifact_reference(
            plan.identity_path,
            repository_root=repository_root,
        ),
    }
    payload = {
        "schema_version": 2,
        "kind": "falsification_review_terminal_failure",
        "review_id": f"falsification-review-{plan.lane_id}",
        "lane_id": plan.lane_id,
        "formal_attempt_id": FORMAL_ATTEMPT_ID,
        "status": "failed",
        "outcome": "inconclusive",
        "terminal": True,
        "failure_stage": stage,
        "reason": reason,
        "retry_permitted": False,
        "replacement_permitted": False,
        "discretionary_rerun_permitted": False,
        "invocation_attempt_count": 1,
        "started_at": started_at,
        "finished_at": finished_at,
        "production_binding": {
            "status": "validated_pre_invocation",
            "invocation_id": production_invocation_id,
            "identity_path": (
                f"{R4_ARTIFACT_ROOT}/{plan.lane_id}/"
                "effective-execution-identity.json"
            ),
            "identity_sha256": production_identity_sha256,
        },
        "command": {
            "argv_without_prompt": list(plan.argv_without_prompt),
            "argv_without_prompt_sha256": sha256_bytes(
                canonical_json_bytes(list(plan.argv_without_prompt))
            ),
            "final_argv_sha256": sha256_bytes(
                canonical_json_bytes(
                    [*plan.argv_without_prompt, plan.prompt]
                )
            ),
            "prompt_transport": plan.prompt_transport,
            "prompt_sha256": plan.prompt_sha256,
            "output_schema_sha256": plan.output_schema_sha256,
            "workdir": str(plan.workdir),
            "timeout_seconds": timeout_seconds,
        },
        "process": {
            "reported_args": (
                list(result.args) if result is not None else None
            ),
            "reported_args_sha256": (
                sha256_bytes(canonical_json_bytes(list(result.args)))
                if result is not None
                else None
            ),
            "returncode": returncode,
            "stdout": stdout,
            "stdout_sha256": sha256_bytes(stdout.encode("utf-8")),
            "stderr": stderr,
            "stderr_sha256": sha256_bytes(stderr.encode("utf-8")),
        },
        "artifacts": artifacts,
        "checksum_seal": {
            "lane_ledger": "checksums.sha256",
            "required": True,
        },
    }
    write_json_artifact(receipt_path, payload)
    return receipt_path


def execute_falsification_review(
    *,
    lane_id: str,
    repository_root: Path,
    production_invocation_id: str,
    production_identity_sha256: str,
    runner: CommandRunner | None = None,
    session_root: Path | None = None,
    timeout_seconds: int = 600,
) -> dict[str, Any]:
    """Execute exactly one fresh review and persist its runner-owned envelope."""

    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or timeout_seconds <= 0
    ):
        raise M9RecoveryQualificationError(
            ["review timeout must be a positive integer"]
        )
    repository_root = Path(repository_root).resolve()
    _validate_review_production_binding(
        lane_id=lane_id,
        repository_root=repository_root,
        production_invocation_id=production_invocation_id,
        production_identity_sha256=production_identity_sha256,
    )
    plan = prepare_falsification_review_invocation(
        lane_id=lane_id,
        repository_root=repository_root,
    )
    command = [*plan.argv_without_prompt, plan.prompt]
    command_runner = runner or SubprocessCommandRunner()
    started_at = dt.datetime.now(dt.timezone.utc).isoformat(
        timespec="microseconds"
    )
    try:
        result = command_runner.run(
            command,
            cwd=plan.workdir,
            timeout_seconds=timeout_seconds,
            input_text="",
        )
    except Exception as error:
        finished_at = dt.datetime.now(dt.timezone.utc).isoformat(
            timespec="microseconds"
        )
        event_persistence_detail = ""
        try:
            write_bytes_artifact(plan.events_path, b"")
        except Exception as event_error:
            event_persistence_detail = (
                "; empty event-stream persistence also failed with "
                f"{type(event_error).__name__}: {event_error}"
            )
        receipt_path = _persist_falsification_review_failure(
            plan=plan,
            repository_root=repository_root,
            production_invocation_id=production_invocation_id,
            production_identity_sha256=production_identity_sha256,
            stage="runner_exception",
            reason=(
                "review command runner raised "
                f"{type(error).__name__}: {error}"
                f"{event_persistence_detail}"
            ),
            started_at=started_at,
            finished_at=finished_at,
            timeout_seconds=timeout_seconds,
            result=None,
            fallback_stderr=(
                f"{type(error).__name__}: {error}"
                f"{event_persistence_detail}"
            ),
        )
        raise FalsificationReviewExecutionError(
            "fresh review runner raised an exception; "
            "no retry is permitted",
            receipt_path=receipt_path,
        ) from error
    try:
        write_bytes_artifact(
            plan.events_path,
            result.stdout.encode("utf-8"),
        )
    except Exception as error:
        receipt_path = _persist_falsification_review_failure(
            plan=plan,
            repository_root=repository_root,
            production_invocation_id=production_invocation_id,
            production_identity_sha256=production_identity_sha256,
            stage="event_stream_persistence",
            reason=f"{type(error).__name__}: {error}",
            started_at=started_at,
            finished_at=dt.datetime.now(dt.timezone.utc).isoformat(
                timespec="microseconds"
            ),
            timeout_seconds=timeout_seconds,
            result=result,
        )
        raise FalsificationReviewExecutionError(
            "fresh review event stream could not be persisted; "
            "no retry is permitted",
            receipt_path=receipt_path,
        ) from error
    if result.args != command:
        receipt_path = _persist_falsification_review_failure(
            plan=plan,
            repository_root=repository_root,
            production_invocation_id=production_invocation_id,
            production_identity_sha256=production_identity_sha256,
            stage="runner_command_mismatch",
            reason="review runner reported a command other than the frozen argv",
            started_at=started_at,
            finished_at=dt.datetime.now(dt.timezone.utc).isoformat(
                timespec="microseconds"
            ),
            timeout_seconds=timeout_seconds,
            result=result,
        )
        raise FalsificationReviewExecutionError(
            "fresh review runner reported a different command; "
            "no retry is permitted",
            receipt_path=receipt_path,
        )
    if result.returncode != 0:
        failure_stage = (
            "timeout" if result.returncode == 124 else "process_exit"
        )
        receipt_path = _persist_falsification_review_failure(
            plan=plan,
            repository_root=repository_root,
            production_invocation_id=production_invocation_id,
            production_identity_sha256=production_identity_sha256,
            stage=failure_stage,
            reason=(
                "review invocation timed out"
                if failure_stage == "timeout"
                else (
                    "review invocation exited with return code "
                    f"{result.returncode}"
                )
            ),
            started_at=started_at,
            finished_at=dt.datetime.now(dt.timezone.utc).isoformat(
                timespec="microseconds"
            ),
            timeout_seconds=timeout_seconds,
            result=result,
        )
        raise FalsificationReviewExecutionError(
            "fresh review invocation failed with exit code "
            f"{result.returncode}; no retry is permitted",
            receipt_path=receipt_path,
        )
    if not plan.output_path.is_file():
        receipt_path = _persist_falsification_review_failure(
            plan=plan,
            repository_root=repository_root,
            production_invocation_id=production_invocation_id,
            production_identity_sha256=production_identity_sha256,
            stage="missing_output",
            reason="review invocation did not create the semantic output",
            started_at=started_at,
            finished_at=dt.datetime.now(dt.timezone.utc).isoformat(
                timespec="microseconds"
            ),
            timeout_seconds=timeout_seconds,
            result=result,
        )
        raise FalsificationReviewExecutionError(
            "fresh review invocation did not produce its semantic output; "
            "no retry is permitted",
            receipt_path=receipt_path,
        )
    try:
        capture_codex_invocation_identity(
            role="verification-agent-falsification-reviewer-v1",
            requested_model=None,
            command=command,
            codex_bin="codex",
            runner=command_runner,
            events_path=plan.events_path,
            receipt_path=plan.identity_path,
            session_root=session_root or default_codex_session_root(),
        )
    except Exception as error:
        receipt_path = _persist_falsification_review_failure(
            plan=plan,
            repository_root=repository_root,
            production_invocation_id=production_invocation_id,
            production_identity_sha256=production_identity_sha256,
            stage="identity_capture",
            reason=f"{type(error).__name__}: {error}",
            started_at=started_at,
            finished_at=dt.datetime.now(dt.timezone.utc).isoformat(
                timespec="microseconds"
            ),
            timeout_seconds=timeout_seconds,
            result=result,
        )
        raise FalsificationReviewExecutionError(
            "fresh review identity capture failed; no retry is permitted",
            receipt_path=receipt_path,
        ) from error
    try:
        return persist_falsification_review_receipt(
            lane_id=lane_id,
            repository_root=repository_root,
            production_invocation_id=production_invocation_id,
            production_identity_sha256=production_identity_sha256,
        )
    except Exception as error:
        receipt_path = _persist_falsification_review_failure(
            plan=plan,
            repository_root=repository_root,
            production_invocation_id=production_invocation_id,
            production_identity_sha256=production_identity_sha256,
            stage="final_binding",
            reason=f"{type(error).__name__}: {error}",
            started_at=started_at,
            finished_at=dt.datetime.now(dt.timezone.utc).isoformat(
                timespec="microseconds"
            ),
            timeout_seconds=timeout_seconds,
            result=result,
        )
        raise FalsificationReviewExecutionError(
            "fresh review artifacts failed final binding; "
            "no retry is permitted",
            receipt_path=receipt_path,
        ) from error


def _execution_provenance_is_eligible(
    *,
    lane_id: str,
    role: str,
    repository_root: Path,
    execution_record: Mapping[str, Any],
    admission: Mapping[str, Any],
    effective_identity: Mapping[str, Any],
    production_identities: Sequence[_CodexInvocationIdentity],
) -> bool:
    """Validate complete runner provenance and bind it to the frozen lane."""

    lane_root = (repository_root / R4_ARTIFACT_ROOT / lane_id).resolve()
    execution_refs = execution_record.get("evidence_refs")
    binding = (
        execution_refs.get("execution_provenance")
        if isinstance(execution_refs, Mapping)
        else None
    )
    try:
        provenance = verify_execution_provenance(
            binding,
            attempt_id=str(execution_record.get("attempt_id")),
            scenario=lane_id,
            base_dir=lane_root,
        )
    except (ExecutionIdentityError, OSError, ValueError):
        return False
    if role == "defect":
        expected_commit = DEFECT_COMMIT
        expected_apk_bytes = DEFECT_APK_BYTES
        expected_apk_sha256 = DEFECT_APK_SHA256
    elif role == "control":
        expected_commit = PROJECT_TARGET_COMMIT
        expected_apk_bytes = CONTROL_APK_BYTES
        expected_apk_sha256 = CONTROL_APK_SHA256
    else:
        return False
    run_spec = provenance.get("run_spec")
    host = provenance.get("host")
    apk = provenance.get("apk")
    device = provenance.get("device")
    tools = provenance.get("tools")
    deployment = provenance.get("deployment")
    roles = provenance.get("roles")
    admission_host = admission.get("host")
    admission_policy = admission.get("runner_policy")
    admission_tools = (
        admission_policy.get("tools")
        if isinstance(admission_policy, Mapping)
        else None
    )
    if not all(
        isinstance(value, Mapping)
        for value in (
            run_spec,
            host,
            apk,
            device,
            tools,
            deployment,
            roles,
            admission_host,
            admission_tools,
        )
    ):
        return False
    frozen_path = (
        repository_root
        / "bench/m9/recovery-v2/run-specs"
        / f"{lane_id}.yaml"
    ).resolve()
    try:
        snapshot_path = (lane_root / str(run_spec["snapshot_path"])).resolve()
        invocation_path = Path(str(run_spec["invocation_path"])).resolve()
        frozen_document = yaml.safe_load(frozen_path.read_text(encoding="utf-8"))
        resolved_document = yaml.safe_load(
            snapshot_path.read_text(encoding="utf-8")
        )
        source_root = Path(str(host["repository_root"])).resolve()
        apk_artifacts = apk.get("artifacts")
        deployment_target = deployment.get("target")
        device_profile = device.get("profile")
    except (KeyError, OSError, UnicodeDecodeError, yaml.YAMLError):
        return False
    if (
        not isinstance(frozen_document, Mapping)
        or not isinstance(resolved_document, Mapping)
        or not isinstance(apk_artifacts, list)
        or len(apk_artifacts) != 1
        or not isinstance(apk_artifacts[0], Mapping)
        or not isinstance(deployment_target, Mapping)
        or not isinstance(device_profile, Mapping)
    ):
        return False
    expected_resolved = json.loads(
        json.dumps(frozen_document, ensure_ascii=False)
    )
    frozen_host = expected_resolved.get("host_project")
    if not isinstance(frozen_host, dict):
        return False
    frozen_host["commit"] = expected_commit

    effective_invocations = effective_identity.get("invocations")
    if not isinstance(effective_invocations, list):
        return False
    effective_refs: set[tuple[str, str]] = set()
    prefix = f"{R4_ARTIFACT_ROOT}/{lane_id}/"
    for item in effective_invocations:
        reference = (
            item.get("identity_receipt")
            if isinstance(item, Mapping)
            else None
        )
        if (
            not _artifact_reference_is_bound(reference)
            or not str(reference.get("path")).startswith(prefix)
        ):
            return False
        effective_refs.add(
            (
                str(reference["path"]).removeprefix(prefix),
                str(reference["sha256"]),
            )
        )
    provenance_refs: set[tuple[str, str]] = set()
    for role_name in ("journey_driver", "l3_semantic_judge"):
        role_payload = roles.get(role_name)
        if not isinstance(role_payload, Mapping):
            return False
        invocations = role_payload.get("invocations")
        if not isinstance(invocations, list):
            return False
        for reference in invocations:
            if not _artifact_reference_is_bound(reference):
                return False
            provenance_refs.add(
                (str(reference["path"]), str(reference["sha256"]))
            )
    apk_artifact = apk_artifacts[0]
    expected_apk_path = (source_root / APK_GLOB).resolve()
    tool_pairs = (
        ("android_cli", "android"),
        ("adb", "adb"),
        ("codex_cli", "codex"),
    )
    try:
        captured_at = dt.datetime.fromisoformat(
            str(provenance.get("captured_at")).replace("Z", "+00:00")
        )
    except ValueError:
        return False
    return (
        captured_at.tzinfo is not None
        and captured_at.utcoffset() is not None
        and run_spec.get("frozen_source_sha256") == sha256_file(frozen_path)
        and run_spec.get("source_binding_ref")
        == sealed_source_binding_ref(lane_id)
        and invocation_path == snapshot_path
        and resolved_document == expected_resolved
        and host.get("origin") == SOURCE_ORIGIN
        and host.get("commit") == expected_commit
        and host.get("repository_root")
        == host.get("worktree_root", host.get("repository_root"))
        and host.get("repository_root")
        == admission_host.get("repository_root")
        == admission_host.get("host_project")
        == run_spec.get("host_project")
        and host.get("worktree", {}).get("clean") is True
        and host.get("worktree", {}).get("status") == ""
        and host.get("worktree", {}).get("untracked_files") == []
        and Path(str(apk_artifact.get("path"))).resolve()
        == expected_apk_path
        and isinstance(apk_artifact.get("bytes"), int)
        and not isinstance(apk_artifact.get("bytes"), bool)
        and apk_artifact.get("bytes") == expected_apk_bytes
        and apk_artifact.get("sha256") == expected_apk_sha256
        and device.get("serial") == DEVICE
        and device.get("api_level") == "35"
        and device_profile.get("kind") == "emulator"
        and device_profile.get("name") == "aiverify_api35"
        and deployment_target.get("device") == DEVICE
        and deployment_target.get("package") == PACKAGE
        and deployment_target.get("component") == f"{PACKAGE}/{ACTIVITY}"
        and all(
            isinstance(tools.get(provenance_name), Mapping)
            and isinstance(admission_tools.get(admission_name), Mapping)
            and all(
                tools[provenance_name].get(key)
                == admission_tools[admission_name].get(key)
                for key in ("requested", "resolved_path", "sha256")
            )
            for provenance_name, admission_name in tool_pairs
        )
        and roles["journey_driver"].get("status") == "invoked"
        and (
            roles["l3_semantic_judge"].get("status") == "invoked"
            or (
                role == "defect"
                and roles["l3_semantic_judge"].get("status")
                == "not_applicable"
                and roles["l3_semantic_judge"].get("reason")
                == "gated_by_lower_oracle"
            )
        )
        and provenance_refs == effective_refs
        and len(effective_refs) == len(production_identities)
        and {
            identity.invocation_id for identity in production_identities
        }
        == {
            str(item.get("invocation_id"))
            for item in effective_invocations
            if isinstance(item, Mapping)
        }
    )


def _lane_ledger_is_exhaustive(
    ledger_path: Path,
    *,
    lane_root: Path,
) -> bool:
    ledger_entries: dict[str, str] = {}
    try:
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            digest, separator, label = line.partition("  ")
            candidate = (lane_root / label).resolve()
            if (
                separator != "  "
                or not _is_sha256(digest)
                or not label
                or label in ledger_entries
                or not candidate.is_relative_to(lane_root)
                or not candidate.is_file()
                or sha256_file(candidate) != digest
            ):
                return False
            ledger_entries[label] = digest
    except (OSError, UnicodeDecodeError):
        return False
    ignored = {"checksums.sha256", "attempt-evidence-validation.json"}
    actual = {
        path.relative_to(lane_root).as_posix(): sha256_file(path)
        for path in lane_root.rglob("*")
        if path.is_file()
        and path.relative_to(lane_root).as_posix() not in ignored
    }
    return ledger_entries == actual


def _attempt_evidence_is_eligible(
    row: Mapping[str, Any],
    *,
    repository_root: Path,
) -> bool:
    lane_id = str(row.get("lane_id"))
    evidence = row.get("attempt_evidence")
    if lane_id not in LANE_IDS or not isinstance(evidence, Mapping):
        return False
    refs = evidence.get("refs")
    checks = evidence.get("validator_checks")
    validation_receipt = row.get("attempt_evidence_receipt")
    if (
        not isinstance(refs, Mapping)
        or set(refs) != set(_ATTEMPT_EVIDENCE_REF_FILES)
        or not isinstance(checks, Mapping)
        or tuple(checks) != _ATTEMPT_VALIDATOR_CHECKS
        or any(value is not True for value in checks.values())
        or not _artifact_reference_is_bound(validation_receipt)
        or validation_receipt.get("path")
        != (
            f"{R4_ARTIFACT_ROOT}/{lane_id}/"
            "attempt-evidence-validation.json"
        )
    ):
        return False
    lane_root = (repository_root / R4_ARTIFACT_ROOT / lane_id).resolve()
    if not lane_root.is_dir():
        return False
    bound_paths: dict[str, Path] = {}
    for key, filename in _ATTEMPT_EVIDENCE_REF_FILES.items():
        reference = refs.get(key)
        if (
            not _artifact_reference_is_bound(reference)
            or reference.get("path")
            != f"{R4_ARTIFACT_ROOT}/{lane_id}/{filename}"
        ):
            return False
        path = _bound_file(repository_root, reference)
        if path is None:
            return False
        bound_paths[key] = path
    validation_path = _bound_file(repository_root, validation_receipt)
    if validation_path is None:
        return False
    persisted_validation = _read_json_object(validation_path)
    if (
        persisted_validation is None
        or canonical_json_bytes(persisted_validation)
        != canonical_json_bytes(evidence)
        or not _lane_ledger_is_exhaustive(
            bound_paths["lane_ledger"],
            lane_root=lane_root,
        )
    ):
        return False

    try:
        execution_record = load_execution_record(
            bound_paths["execution_record"]
        )
    except ExecutionRecordValidationError:
        return False
    identity = _read_json_object(bound_paths["effective_execution_identity"])
    setup = _read_json_object(bound_paths["runner_setup"])
    admission = _read_json_object(bound_paths["production_seam_admission"])
    oracle = _read_json_object(bound_paths["oracle_receipt"])
    finding_payload = _read_json_object(bound_paths["finding"])
    residual_payload = _read_json_object(bound_paths["residual_risk"])
    risk_map_payload = _read_json_object(bound_paths["project_risk_map"])
    claim_boundary = _read_json_object(bound_paths["claim_boundary"])
    persisted_review = _read_json_object(bound_paths["falsification_review"])
    review_identity = _codex_identity(
        bound_paths["falsification_review_identity"],
        expected_role="verification-agent-falsification-reviewer-v1",
        require_fresh_session=True,
    )
    review_context = _read_json_object(
        bound_paths["falsification_review_context"]
    )
    review = row.get("falsification_review")
    if not all(
        isinstance(value, Mapping)
        for value in (
            identity,
            setup,
            admission,
            oracle,
            finding_payload,
            residual_payload,
            risk_map_payload,
            claim_boundary,
            persisted_review,
            review_context,
            review,
        )
    ) or review_identity is None:
        return False
    production_identities = _production_identities(
        identity,
        lane_id=lane_id,
        repository_root=repository_root,
    )
    if production_identities is None:
        return False
    try:
        finding = Finding.from_dict(finding_payload)
        residual = ResidualRisk.from_dict(residual_payload)
        risk_map = ProjectRiskMap.from_dict(risk_map_payload)
    except DiscoveryContractError:
        return False

    token = PROBE_TOKENS[LANE_IDS.index(lane_id)]
    expected_finding = {
        "locally_supported": "supported",
        "locally_rejected": "rejected",
        "inconclusive": "inconclusive",
    }.get(row.get("finding_conclusion"))
    raw_refs = {
        key: refs[key]
        for key in (
            "screenshot_before",
            "screenshot_after",
            "layout_before",
            "layout_after",
            "filtered_logcat",
            "rotation_event",
        )
    }
    review_payload = {
        key: value
        for key, value in review.items()
        if key not in {"path", "sha256"}
    }
    execution_refs = execution_record.get("evidence_refs")
    finding_required_refs = {
        "execution-record.json",
        "effective-execution-identity.json",
        "oracle-receipt.json",
        "raw/screenshots/before.png",
        "raw/screenshots/after.png",
        "raw/layout/before.json",
        "raw/layout/after.json",
        "raw/logcat/rotation.txt",
        "rotation-event.json",
    }
    return (
        evidence.get("schema_version") == 2
        and evidence.get("validation_version")
        == "m9-recovery-attempt-evidence-v2"
        and evidence.get("status") == "validated"
        and evidence.get("lane_id") == lane_id
        and evidence.get("formal_attempt_id") == FORMAL_ATTEMPT_ID
        and evidence.get("terminal_lifecycle") == "terminal"
        and evidence.get("execution_record_attempt_id")
        == execution_record.get("attempt_id")
        == row.get("execution_record_attempt_id")
        and evidence.get("accountable") is row.get("accountable")
        and evidence.get("finding_conclusion")
        == row.get("finding_conclusion")
        and evidence.get("production_invocation_id")
        == row.get("production_invocation_id")
        and evidence.get("production_identity_sha256")
        == row.get("production_identity_sha256")
        and evidence.get("evidence_refs_sha256")
        == sha256_bytes(canonical_json_bytes(refs))
        and execution_record.get("scenario") == lane_id
        and execution_record.get("lifecycle_state") == "completed"
        and is_execution_record_accountable(execution_record)
        is row.get("accountable")
        and isinstance(execution_refs, Mapping)
        and execution_refs.get("runner_setup") == "runner-setup.json"
        and isinstance(execution_refs.get("execution_provenance"), Mapping)
        and execution_refs["execution_provenance"].get("path")
        == "execution-provenance.json"
        and execution_refs["execution_provenance"].get("sha256")
        == refs["execution_provenance"].get("sha256")
        and _execution_provenance_is_eligible(
            lane_id=lane_id,
            role=str(row.get("role")),
            repository_root=repository_root,
            execution_record=execution_record,
            admission=admission,
            effective_identity=identity,
            production_identities=production_identities,
        )
        and identity.get("production_invocation_id")
        == row.get("production_invocation_id")
        and refs["effective_execution_identity"].get("sha256")
        == row.get("production_identity_sha256")
        and identity.get("execution_record_attempt_id")
        == execution_record.get("attempt_id")
        and _runner_setup_is_eligible(setup)
        and _production_admission_is_eligible(
            admission,
            lane_id=lane_id,
            role=str(row.get("role")),
            repository_root=repository_root,
        )
        and _raw_probe_is_eligible(
            bound_paths=bound_paths,
            lane_id=lane_id,
            token=token,
            conclusion=row.get("finding_conclusion"),
        )
        and oracle.get("schema_version") == 2
        and oracle.get("oracle_id")
        == "m9-unsent-draft-config-recreation-v1"
        and oracle.get("lane_id") == lane_id
        and oracle.get("accountable") is row.get("accountable")
        and oracle.get("conclusion") == row.get("finding_conclusion")
        and oracle.get("status") == "complete"
        and oracle.get("hypothesis_id") == FORMAL_HYPOTHESIS_ID
        and isinstance(oracle.get("explored_fact_ids"), list)
        and tuple(oracle["explored_fact_ids"]) == risk_map.explored_fact_ids
        and oracle.get("probe_token") == token
        and oracle.get("sent") is False
        and oracle.get("retyped_after_boundary") is False
        and oracle.get("repaired_after_boundary") is False
        and oracle.get("evidence_refs") == raw_refs
        and expected_finding is not None
        and finding.finding_id == f"finding-{lane_id}"
        and finding.target_id == PROJECT_TARGET_ID
        and finding.hypothesis_id == FORMAL_HYPOTHESIS_ID
        and finding.conclusion == expected_finding
        and finding.claim_boundary == LOCAL_CLAIM_BOUNDARY
        and finding_required_refs.issubset(set(finding.evidence_refs))
        and residual.risk_id == f"residual-{lane_id}"
        and residual.target_id == PROJECT_TARGET_ID
        and residual.hypothesis_id == FORMAL_HYPOTHESIS_ID
        and residual.scope == LOCAL_CLAIM_BOUNDARY
        and residual.status in {"open", "accepted"}
        and residual.next_probe is not None
        and "new approved" in residual.next_probe.lower()
        and {"execution-record.json", "oracle-receipt.json"}.issubset(
            set(residual.basis_refs)
        )
        and risk_map.map_id == f"risk-map-{lane_id}"
        and risk_map.target_id == PROJECT_TARGET_ID
        and risk_map.findings == (finding,)
        and risk_map.residual_risks == (residual,)
        and bool(risk_map.explored_fact_ids)
        and len(set(risk_map.explored_fact_ids))
        == len(risk_map.explored_fact_ids)
        and bool(risk_map.coverage_frontier)
        and claim_boundary.get("schema_version") == 2
        and claim_boundary.get("lane_id") == lane_id
        and claim_boundary.get("scope") == LOCAL_CLAIM_BOUNDARY
        and claim_boundary.get("local_only") is True
        and claim_boundary.get("preserved_runtime_result")
        == "#137 remains Not Supported and is never rerun or rewritten"
        and {
            "production",
            "upstream",
            "OEM",
            "ColorOS",
            "physical-device",
        }.issubset(set(claim_boundary.get("excluded_claims", ())))
        and canonical_json_bytes(persisted_review)
        == canonical_json_bytes(review_payload)
        and review.get("path") == refs["falsification_review"].get("path")
        and review.get("sha256") == refs["falsification_review"].get("sha256")
        and review.get("identity_path")
        == refs["falsification_review_identity"].get("path")
        and review.get("identity_sha256") == review_identity.receipt_sha256
        == refs["falsification_review_identity"].get("sha256")
        and review.get("invocation_id") == review_identity.invocation_id
        and review.get("effective_model") == review_identity.effective_model
        and review.get("clean_context_path")
        == refs["falsification_review_context"].get("path")
        and review.get("clean_context_sha256")
        == refs["falsification_review_context"].get("sha256")
        and review.get("output_path")
        == refs["falsification_review_output"].get("path")
        and review.get("output_sha256")
        == refs["falsification_review_output"].get("sha256")
        and review.get("output_schema_path")
        == refs["falsification_review_output_schema"].get("path")
        and review.get("output_schema_sha256")
        == refs["falsification_review_output_schema"].get("sha256")
        and review.get("events_path")
        == refs["falsification_review_events"].get("path")
        and review.get("events_sha256")
        == refs["falsification_review_events"].get("sha256")
        and review.get("invocation_ledger_path")
        == refs["falsification_review_invocation"].get("path")
        and review.get("invocation_ledger_sha256")
        == refs["falsification_review_invocation"].get("sha256")
        and review.get("prompt_path")
        == refs["falsification_review_prompt"].get("path")
        and review.get("prompt_sha256")
        == refs["falsification_review_prompt"].get("sha256")
        and _review_context_is_eligible(
            review_context,
            lane_id=lane_id,
            expected_workdir=review_identity.workdir,
            repository_root=repository_root,
        )
        and _review_result_is_eligible(
            bound_paths=bound_paths,
            lane_id=lane_id,
            review=review,
            context=review_context,
            identity=review_identity,
        )
    )


def _formal_attempt_artifact_audit(
    repository_root: Path,
    *,
    rows: Sequence[Mapping[str, Any]],
    attempt_inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    attempt_root = (repository_root / R4_RUN_RECORD).resolve()
    artifact_root = (repository_root / R4_ARTIFACT_ROOT).resolve()
    result: dict[str, Any] = {
        "lane_roots_exact": False,
        "execution_records_exhaustive": False,
        "execution_record_count": 0,
        "execution_record_attempt_ids_unique": False,
        "inventory_execution_records_bound": False,
    }
    if not attempt_root.is_dir() or not artifact_root.is_dir():
        return result
    try:
        lane_roots = {
            path.name
            for path in artifact_root.iterdir()
            if path.is_dir()
        }
    except OSError:
        return result
    result["lane_roots_exact"] = lane_roots == set(LANE_IDS)

    candidates: set[Path] = set()
    try:
        files = tuple(
            path for path in attempt_root.rglob("*") if path.is_file()
        )
    except OSError:
        return result
    for path in files:
        named_as_record = path.name.startswith("execution-record")
        try:
            load_execution_record(path)
        except (ExecutionRecordValidationError, UnicodeDecodeError):
            if named_as_record:
                return result
            continue
        candidates.add(path)
    expected_paths = {
        (artifact_root / lane_id / "execution-record.json").resolve()
        for lane_id in LANE_IDS
    }
    actual_records: list[dict[str, Any]] = []
    for path in sorted(candidates):
        try:
            record = load_execution_record(path)
        except ExecutionRecordValidationError:
            return result
        try:
            relative = path.resolve().relative_to(repository_root).as_posix()
        except ValueError:
            return result
        actual_records.append(
            {
                "lane_id": record.get("scenario"),
                "execution_record_attempt_id": record.get("attempt_id"),
                "path": relative,
                "sha256": sha256_file(path),
            }
        )
    result["execution_record_count"] = len(actual_records)
    result["execution_records_exhaustive"] = (
        {path.resolve() for path in candidates} == expected_paths
        and len(actual_records) == len(LANE_IDS)
    )
    attempt_ids = [
        item.get("execution_record_attempt_id") for item in actual_records
    ]
    result["execution_record_attempt_ids_unique"] = (
        len(attempt_ids) == 6
        and all(_is_nonempty_string(value) for value in attempt_ids)
        and len(set(attempt_ids)) == 6
    )
    expected_records: list[dict[str, Any]] = []
    for row in rows:
        evidence = row.get("attempt_evidence")
        refs = evidence.get("refs") if isinstance(evidence, Mapping) else None
        execution_ref = (
            refs.get("execution_record") if isinstance(refs, Mapping) else None
        )
        if not _artifact_reference_is_bound(execution_ref):
            return result
        expected_records.append(
            {
                "lane_id": row.get("lane_id"),
                "execution_record_attempt_id": row.get(
                    "execution_record_attempt_id"
                ),
                "path": execution_ref.get("path"),
                "sha256": execution_ref.get("sha256"),
            }
        )
    inventory_entry = (
        attempt_inventory[0] if len(attempt_inventory) == 1 else None
    )
    result["inventory_execution_records_bound"] = bool(
        isinstance(inventory_entry, Mapping)
        and inventory_entry.get("execution_records") == actual_records
        and expected_records == actual_records
    )
    return result


def reconcile_formal_rows(
    rows: Sequence[Mapping[str, Any]],
    contradiction: Mapping[str, Any],
    *,
    auditor_mapping: Mapping[str, Any],
    expected_mapping_commitment_sha256: str,
    expected_contradiction_audit_sha256: str,
    formal_attempt_inventory: Sequence[Mapping[str, Any]],
    formal_attempt_inventory_receipt: Mapping[str, Any],
    evidence_repository_root: str | Path,
) -> dict[str, Any]:
    """Apply the frozen all-or-nothing Supported gate without writing evidence."""

    if not _is_sha256(expected_mapping_commitment_sha256):
        raise M9RecoveryQualificationError(
            ("expected auditor mapping commitment is not a SHA-256 digest",)
        )
    if not _is_sha256(expected_contradiction_audit_sha256):
        raise M9RecoveryQualificationError(
            ("expected contradiction audit commitment is not a SHA-256 digest",)
        )
    actual_mapping_commitment = sha256_bytes(
        canonical_json_bytes(auditor_mapping)
    )
    if actual_mapping_commitment != expected_mapping_commitment_sha256:
        raise M9RecoveryQualificationError(
            ("released auditor mapping contradicts its frozen commitment",)
        )
    mapping_errors = _mapping_errors(auditor_mapping)
    if mapping_errors:
        raise M9RecoveryQualificationError(mapping_errors)
    assignments = auditor_mapping.get("assignments")
    if not isinstance(assignments, list):
        raise M9RecoveryQualificationError(
            ("released auditor mapping assignments are unavailable",)
        )
    assignment_ids = tuple(item.get("lane_id") for item in assignments)
    assignment_roles = tuple(item.get("role") for item in assignments)
    if assignment_ids != LANE_IDS:
        raise M9RecoveryQualificationError(
            ("released auditor mapping lane order drifted",)
        )

    ordered = list(rows)
    if tuple(item.get("lane_id") for item in ordered) != LANE_IDS:
        raise M9RecoveryQualificationError(
            ("formal reconciliation lane order drifted",)
        )
    role_values = tuple(item.get("role") for item in ordered)
    if role_values != assignment_roles:
        raise M9RecoveryQualificationError(
            ("formal reconciliation roles contradict the committed mapping",)
        )
    defect = [item for item in ordered if item["role"] == "defect"]
    control = [item for item in ordered if item["role"] == "control"]
    evidence_root = Path(evidence_repository_root).resolve()
    accountable = sum(item.get("accountable") is True for item in ordered)
    defect_supported = sum(
        item.get("accountable") is True
        and item.get("finding_conclusion") == "locally_supported"
        for item in defect
    )
    control_rejected = sum(
        item.get("accountable") is True
        and item.get("finding_conclusion") == "locally_rejected"
        for item in control
    )
    attempt_evidence_validated = sum(
        _attempt_evidence_is_eligible(
            item,
            repository_root=evidence_root,
        )
        for item in ordered
    )
    reviews = [
        item.get("falsification_review")
        if isinstance(item.get("falsification_review"), Mapping)
        else {}
        for item in ordered
    ]
    review_eligible = [
        _review_receipt_is_eligible(
            review,
            lane_id=str(item.get("lane_id")),
            production_invocation_id=item.get("production_invocation_id"),
            production_identity_sha256=item.get("production_identity_sha256"),
        )
        for item, review in zip(ordered, reviews, strict=True)
    ]
    review_survived = sum(review_eligible)
    review_authoritative_identities: list[_CodexInvocationIdentity] = []
    for item in ordered:
        evidence = item.get("attempt_evidence")
        refs = evidence.get("refs") if isinstance(evidence, Mapping) else None
        reference = (
            refs.get("falsification_review_identity")
            if isinstance(refs, Mapping)
            else None
        )
        path = _bound_file(evidence_root, reference)
        parsed = (
            _codex_identity(
                path,
                expected_role=(
                    "verification-agent-falsification-reviewer-v1"
                ),
                require_fresh_session=True,
            )
            if path is not None
            else None
        )
        if parsed is not None:
            review_authoritative_identities.append(parsed)
    review_identities_unique = bool(
        review_survived == 6
        and len(review_authoritative_identities) == 6
        and len(
            {
                identity.invocation_id
                for identity in review_authoritative_identities
            }
        )
        == 6
        and len(
            {
                identity.thread_id
                for identity in review_authoritative_identities
            }
        )
        == 6
        and len(
            {
                identity.receipt_sha256
                for identity in review_authoritative_identities
            }
        )
        == 6
        and all(
            len({str(review.get(field)) for review in reviews}) == 6
            for field in (
                "invocation_id",
                "identity_sha256",
                "clean_context_sha256",
                "production_invocation_id",
                "production_identity_sha256",
            )
        )
    )
    production_invocation_ids: list[str] = []
    production_thread_ids: list[str] = []
    production_invocation_identity_hashes: list[str] = []
    production_identities_authoritative = True
    for item in ordered:
        evidence = item.get("attempt_evidence")
        refs = evidence.get("refs") if isinstance(evidence, Mapping) else None
        identity_ref = (
            refs.get("effective_execution_identity")
            if isinstance(refs, Mapping)
            else None
        )
        identity_path = _bound_file(evidence_root, identity_ref)
        identity = (
            _read_json_object(identity_path)
            if identity_path is not None
            else None
        )
        parsed = (
            _production_identities(
                identity,
                lane_id=str(item.get("lane_id")),
                repository_root=evidence_root,
            )
            if isinstance(identity, Mapping)
            else None
        )
        if parsed is None:
            production_identities_authoritative = False
            continue
        production_invocation_ids.extend(
            identity.invocation_id for identity in parsed
        )
        production_thread_ids.extend(
            identity.thread_id for identity in parsed
        )
        production_invocation_identity_hashes.extend(
            identity.receipt_sha256 for identity in parsed
        )
    production_identities_unique = bool(
        production_identities_authoritative
        and len(production_invocation_ids) >= 6
        and len(set(production_invocation_ids))
        == len(production_invocation_ids)
        and len(set(production_invocation_identity_hashes))
        == len(production_invocation_identity_hashes)
    )
    review_invocation_ids = {
        identity.invocation_id
        for identity in review_authoritative_identities
    }
    review_thread_ids = {
        identity.thread_id
        for identity in review_authoritative_identities
    }
    review_identity_hashes = {
        identity.receipt_sha256
        for identity in review_authoritative_identities
    }
    review_production_identities_disjoint = bool(
        review_identities_unique
        and production_identities_unique
        and review_invocation_ids.isdisjoint(production_invocation_ids)
        and review_thread_ids.isdisjoint(production_thread_ids)
        and review_identity_hashes.isdisjoint(
            production_invocation_identity_hashes
        )
    )
    actual_contradiction_commitment = sha256_bytes(
        canonical_json_bytes(contradiction)
    )
    if (
        actual_contradiction_commitment
        != expected_contradiction_audit_sha256
    ):
        raise M9RecoveryQualificationError(
            ("contradiction audit contradicts its frozen commitment",)
        )
    contradiction_passed = (
        _contradiction_audit_is_eligible(contradiction)
    )

    attempt_inventory = list(formal_attempt_inventory)
    inventory_path = _bound_file(
        evidence_root,
        formal_attempt_inventory_receipt,
    )
    persisted_inventory: object = None
    if inventory_path is not None:
        try:
            persisted_inventory = json.loads(
                inventory_path.read_text(encoding="utf-8"),
                object_pairs_hook=_unique_pairs,
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            M9RecoveryQualificationError,
        ):
            persisted_inventory = None
    inventory_bound = (
        formal_attempt_inventory_receipt.get("path")
        == f"{R4_RUN_RECORD}/formal-attempt-inventory.json"
        and isinstance(persisted_inventory, Mapping)
        and persisted_inventory.get("schema_version") == 2
        and persisted_inventory.get("formal_attempts") == attempt_inventory
    )
    artifact_audit = _formal_attempt_artifact_audit(
        evidence_root,
        rows=ordered,
        attempt_inventory=attempt_inventory,
    )
    formal_attempt_count = len(attempt_inventory)
    retry_count = _sum_evidence_counts(
        item.get("retry_count") for item in attempt_inventory
    )
    replacement_count = _sum_evidence_counts(
        item.get("replacement_count") for item in attempt_inventory
    )
    discretionary_rerun_count = _sum_evidence_counts(
        item.get("discretionary_rerun_count") for item in attempt_inventory
    )
    lane_attempt_count = _sum_evidence_counts(
        item.get("lane_attempt_count") for item in ordered
    )
    lane_retry_count = _sum_evidence_counts(
        item.get("retry_count") for item in ordered
    )
    lane_replacement_count = _sum_evidence_counts(
        item.get("replacement_count") for item in ordered
    )
    lane_discretionary_rerun_count = _sum_evidence_counts(
        item.get("discretionary_rerun_count") for item in ordered
    )
    attempt_entry = attempt_inventory[0] if formal_attempt_count == 1 else {}
    one_attempt_passed = (
        inventory_bound
        and artifact_audit["lane_roots_exact"]
        and artifact_audit["execution_records_exhaustive"]
        and artifact_audit["execution_record_count"] == 6
        and artifact_audit["execution_record_attempt_ids_unique"]
        and artifact_audit["inventory_execution_records_bound"]
        and formal_attempt_count == 1
        and attempt_entry.get("formal_attempt_id") == FORMAL_ATTEMPT_ID
        and _strict_count(attempt_entry.get("attempt_number")) == 1
        and tuple(attempt_entry.get("lane_order", ())) == LANE_IDS
        and _strict_count(attempt_entry.get("lane_count")) == 6
        and _strict_count(attempt_entry.get("terminal_lane_count")) == 6
        and retry_count == 0
        and replacement_count == 0
        and discretionary_rerun_count == 0
        and lane_attempt_count == 6
        and lane_retry_count == 0
        and lane_replacement_count == 0
        and lane_discretionary_rerun_count == 0
        and all(
            item.get("formal_attempt_id") == FORMAL_ATTEMPT_ID
            and _strict_count(item.get("lane_attempt_count")) == 1
            and _strict_count(item.get("retry_count")) == 0
            and _strict_count(item.get("replacement_count")) == 0
            and _strict_count(item.get("discretionary_rerun_count")) == 0
            and item.get("terminal") is True
            for item in ordered
        )
    )
    gates = {
        "six_of_six_accountable": accountable == 6,
        "attempt_evidence_six_of_six_validated": (
            attempt_evidence_validated == 6
        ),
        "defect_three_of_three_supported": defect_supported == 3,
        "control_three_of_three_rejected": control_rejected == 3,
        "falsification_six_of_six_survived": review_survived == 6,
        "review_identities_unique_and_policy_bound": (
            review_production_identities_disjoint
        ),
        "contradiction_rejected_before_side_effect": contradiction_passed,
        "formal_attempt_inventory_checksum_bound": inventory_bound,
        "formal_attempt_artifacts_exhaustively_enumerated": all(
            artifact_audit.values()
        ),
        "one_formal_attempt_zero_retry_replacement": one_attempt_passed,
    }
    return {
        "schema_version": 2,
        "lane_order": list(LANE_IDS),
        "lanes": [
            {key: value for key, value in item.items() if key != "role"}
            for item in ordered
        ],
        "counts": {
            "lane_count": len(ordered),
            "accountable": accountable,
            "attempt_evidence_validated": attempt_evidence_validated,
            "defect_supported": defect_supported,
            "control_locally_rejected": control_rejected,
            "falsification_review_survived": review_survived,
            "review_identities_unique": review_identities_unique,
            "production_identities_authoritative": (
                production_identities_authoritative
            ),
            "production_identities_unique": production_identities_unique,
            "review_production_identities_disjoint": (
                review_production_identities_disjoint
            ),
            "contradiction_packet_pre_side_effect": contradiction_passed,
            "lane_attempt_count": lane_attempt_count,
            "lane_retry_count": lane_retry_count,
            "lane_replacement_count": lane_replacement_count,
            "lane_discretionary_rerun_count": (
                lane_discretionary_rerun_count
            ),
            "formal_attempt_inventory_checksum_bound": inventory_bound,
            **artifact_audit,
        },
        "aggregate_result": "Supported" if all(gates.values()) else "Not Supported",
        "supported_gate": gates,
        "formal_holdout_executed": True,
        "formal_attempt_count": formal_attempt_count,
        "retry_count": retry_count,
        "replacement_count": replacement_count,
        "discretionary_rerun_count": discretionary_rerun_count,
        "formal_attempt_inventory": attempt_inventory,
        "mapping_commitment_sha256": actual_mapping_commitment,
        "mapping_assignment_verified": True,
        "contradiction_audit_sha256": actual_contradiction_commitment,
    }


def validate_formal_attempt_row(
    row: Mapping[str, Any],
    *,
    evidence_repository_root: str | Path,
) -> bool:
    """Validate one sealed R4 row against every frozen byte-level contract."""

    return _attempt_evidence_is_eligible(
        row,
        repository_root=Path(evidence_repository_root).resolve(),
    )


def _manifest_errors(
    document: Mapping[str, Any],
    *,
    require_frozen: bool,
) -> tuple[str, ...]:
    errors: list[str] = []

    if document.get("schema_version") != 2:
        errors.append("schema_version must be 2")
    if document.get("qualification_id") != QUALIFICATION_ID:
        errors.append("qualification_id is not the recovery-v2 qualification")
    status = document.get("status")
    if status not in {"awaiting_human_approval", "frozen"}:
        errors.append("status must await human approval or be frozen")
    if require_frozen and status != "frozen":
        errors.append("formal execution requires frozen status")
    if document.get("formal_holdout_executed") is not False:
        errors.append("formal_holdout_executed must remain false in R3")
    if document.get("formal_denominator") is not False:
        errors.append("formal_denominator must remain false in R3")
    for field in _PACKET_FIELDS:
        value = document.get(field)
        if field == "lanes":
            if not isinstance(value, list):
                errors.append("approval-bound lanes section must be a list")
        elif not isinstance(value, Mapping):
            errors.append(f"approval-bound {field} section must be an object")

    approval = document.get("approval")
    if not isinstance(approval, Mapping):
        errors.append("approval must be an object")
    elif status == "frozen":
        approval_errors = _human_approval_errors(
            comment_url=approval.get("comment_url"),
            approved_by=approval.get("approved_by"),
            approved_at=approval.get("approved_at"),
        )
        if (
            approval.get("status") != "approved"
            or approval.get("issue_url")
            != "https://github.com/yangliang2/ai_verification/issues/152"
            or document.get("frozen_at") != approval.get("approved_at")
            or approval_errors
        ):
            errors.append("frozen status requires explicit auditable human approval")
            errors.extend(approval_errors)
    elif (
        approval.get("status") != "pending"
        or approval.get("issue_url")
        != "https://github.com/yangliang2/ai_verification/issues/152"
        or approval.get("comment_url") is not None
        or approval.get("approved_by") is not None
        or approval.get("approved_at") is not None
        or document.get("frozen_at") is not None
    ):
        errors.append("candidate status requires a clean pending approval envelope")

    history = document.get("history_exclusion")
    if not isinstance(history, Mapping):
        errors.append("history exclusion must be an object")
    else:
        required = {
            "m9-project-qualification-v1",
            "m9-r1-recovery-baseline",
            "m9-r2-non-holdout-canary",
        }
        observed = set(history.get("forbidden_qualification_ids", ()))
        if not required.issubset(observed):
            errors.append("historical frozen/canary populations are not excluded")
        if history.get("reuse_permitted") is not False:
            errors.append("historical population reuse must be forbidden")
        if (
            history.get("copy_into_denominator_permitted") is not False
            or history.get("historical_artifact_rewrite_permitted") is not False
            or not {"#136", "#137", "#148", "#150"}.issubset(
                set(history.get("forbidden_issues", ()))
            )
        ):
            errors.append("immutable historical issue boundaries drifted")
        freshness = history.get("freshness_audit")
        audit = (
            freshness.get("audit")
            if isinstance(freshness, Mapping)
            else None
        )
        freshness_command = (
            audit.get("command")
            if isinstance(audit, Mapping)
            and isinstance(audit.get("command"), list)
            else []
        )
        if (
            not _artifact_reference_is_bound(freshness)
            or not isinstance(audit, Mapping)
            or audit.get("status") != "pass"
            or audit.get("base_main_commit")
            != "099cf64228273ef67bd23c6bad4af6239e580aa1"
            or audit.get("returncode") != 1
            or audit.get("stdout") != ""
            or audit.get("stderr") != ""
            or audit.get("matched_paths") != []
            or audit.get("historical_population_reused") is not False
            or tuple(freshness_command[:4])
            != ("git", "grep", "-n", "-E")
            or freshness_command[-3:]
            != [
                "099cf64228273ef67bd23c6bad4af6239e580aa1",
                "--",
                ".",
            ]
        ):
            errors.append("fresh-cohort base-tree absence audit is incomplete")

    target = document.get("target")
    if not isinstance(target, Mapping):
        errors.append("target must be an object")
    else:
        expected = {
            "source_origin": SOURCE_ORIGIN,
            "source_commit": PROJECT_TARGET_COMMIT,
            "source_tree": PROJECT_TARGET_TREE,
            "package": PACKAGE,
            "activity": ACTIVITY,
            "apk_glob": APK_GLOB,
        }
        for key, value in expected.items():
            if target.get(key) != value:
                errors.append(f"target {key} drifted")
        defect = target.get("defect")
        control = target.get("control")
        if not isinstance(defect, Mapping) or (
            defect.get("commit") != DEFECT_COMMIT
            or defect.get("tree") != DEFECT_TREE
        ):
            errors.append("target defect identity drifted")
        if not isinstance(control, Mapping) or (
            control.get("commit") != PROJECT_TARGET_COMMIT
            or control.get("tree") != PROJECT_TARGET_TREE
        ):
            errors.append("target control identity drifted")
        for label, snapshot, expected_commit in (
            ("defect", defect, DEFECT_COMMIT),
            ("control", control, PROJECT_TARGET_COMMIT),
        ):
            apk = snapshot.get("apk") if isinstance(snapshot, Mapping) else None
            source_identity = (
                snapshot.get("source_identity")
                if isinstance(snapshot, Mapping)
                else None
            )
            if (
                not isinstance(apk, Mapping)
                or apk.get("package") != PACKAGE
                or apk.get("launchable_activities") != [ACTIVITY]
                or not _is_sha256(apk.get("sha256"))
                or _strict_count(apk.get("bytes")) in {None, 0}
                or not isinstance(source_identity, Mapping)
                or source_identity.get("commit") != expected_commit
            ):
                errors.append(f"target {label} built APK identity is incomplete")

    cohort = document.get("cohort")
    lanes = document.get("lanes")
    if not isinstance(cohort, Mapping):
        errors.append("cohort must be an object")
    else:
        if (
            cohort.get("lane_count") != 6
            or cohort.get("defect_count") != 3
            or cohort.get("control_count") != 3
        ):
            errors.append("cohort must be exactly three defect and three control")
        if tuple(cohort.get("lane_order", ())) != LANE_IDS:
            errors.append("cohort lane order drifted")
        if cohort.get("blocked_randomization") != "three_blocks_of_one_plus_one":
            errors.append("cohort blocked randomization policy drifted")
        commitment = cohort.get("mapping_commitment")
        if not isinstance(commitment, Mapping):
            errors.append("mapping commitment must be an object")
        else:
            if not _SHA256.fullmatch(str(commitment.get("sha256", ""))):
                errors.append("mapping canonical commitment is invalid")
            if not _SHA256.fullmatch(
                str(commitment.get("raw_artifact_sha256", ""))
            ):
                errors.append("mapping raw commitment is invalid")
            if commitment.get("clear_mapping_in_verifier_inputs") is not False:
                errors.append("clear mapping must be excluded from verifier inputs")
    if (
        not isinstance(lanes, list)
        or tuple(item.get("lane_id") for item in lanes) != LANE_IDS
    ):
        errors.append("lanes must contain six opaque IDs in approved order")
    elif any(
        "role" in lane
        or "variant" in lane
        or "source_commit" in lane
        or lane.get("one_attempt") is not True
        or lane.get("retry") is not False
        or lane.get("replacement") is not False
        or not _lane_binding_is_valid(lane)
        for lane in lanes
    ):
        errors.append("lane contract leaks assignment or changes one-attempt policy")
    elif len({str(lane.get("probe_token")) for lane in lanes}) != 6:
        errors.append("all six formal probe tokens must be distinct")

    runner = document.get("runner")
    if not isinstance(runner, Mapping):
        errors.append("runner must be an object")
    elif (
        runner.get("backend") != BACKEND
        or runner.get("policy_version") != RUNNER_POLICY
        or runner.get("device") != DEVICE
        or runner.get("requested_driver_model") is not None
        or runner.get("requested_l3_model") is not None
        or runner.get("model_selection") != "codex_cli_default"
        or runner.get("pre_lane_orientation") != "portrait"
    ):
        errors.append("runner identity/default-model/orientation policy drifted")

    policy = document.get("policy")
    if not isinstance(policy, Mapping) or any(
        policy.get(key) is not expected
        for key, expected in (
            ("one_formal_attempt", True),
            ("one_attempt_per_lane", True),
            ("zero_retry", True),
            ("zero_replacement", True),
            ("zero_discretionary_rerun", True),
            ("denominator_changes_after_start", False),
        )
    ):
        errors.append("formal one-attempt accounting policy drifted")

    context = document.get("context_acquisition")
    source_index = (
        context.get("source_index") if isinstance(context, Mapping) else None
    )
    if (
        not isinstance(context, Mapping)
        or tuple(context.get("order", ()))
        != (
            "repository",
            "build",
            "manifest",
            "call_site",
            "state",
            "version",
            "execution_boundary",
        )
        or context.get("discovery_budget") != 8
        or context.get("unknown_and_contradictory_are_first_class") is not True
        or context.get("no_build_device_agent_runtime_side_effect") is not True
        or context.get("fresh_execution_required_in_r4") is not True
        or not _artifact_reference_is_bound(source_index)
        or not _is_sha256(
            source_index.get("canonical_inventory_sha256")
            if isinstance(source_index, Mapping)
            else None
        )
        or (
            _strict_count(source_index.get("input_count"))
            if isinstance(source_index, Mapping)
            else None
        )
        != 6
    ):
        errors.append("Context Acquisition contract or source index drifted")

    portfolio = document.get("portfolio")
    registry = (
        portfolio.get("approved_registry")
        if isinstance(portfolio, Mapping)
        else None
    )
    registry_operator_count = (
        len(registry.get("operator_ids", ()))
        if isinstance(registry, Mapping)
        else None
    )
    if (
        not isinstance(portfolio, Mapping)
        or portfolio.get("budget") != 8
        or portfolio.get("top_three") is not True
        or portfolio.get("selected_only_after_fresh_context_acquisition")
        is not True
        or portfolio.get("formal_holdout_executed") is not False
        or not _artifact_reference_is_bound(registry)
        or (
            _strict_count(registry.get("prior_count"))
            if isinstance(registry, Mapping)
            else None
        )
        != 3
        or registry_operator_count != 3
    ):
        errors.append("Hypothesis Portfolio contract or registry drifted")

    attack = document.get("attack_plan")
    attack_contract = (
        attack.get("contract") if isinstance(attack, Mapping) else None
    )
    if (
        not isinstance(attack, Mapping)
        or attack.get("target_specific_plan_generation")
        != "R4 only after fresh context and portfolio freeze"
        or attack.get("claim_boundary") != "local-only"
        or not _artifact_reference_is_bound(attack_contract)
        or (
            attack_contract.get("status")
            if isinstance(attack_contract, Mapping)
            else None
        )
        != "admitted_contract_reference"
        or not _is_sha256(
            attack_contract.get("source_receipt_sha256")
            if isinstance(attack_contract, Mapping)
            else None
        )
    ):
        errors.append("Attack Plan contract or source receipt drifted")

    oracle = document.get("oracle")
    boundary = oracle.get("boundary") if isinstance(oracle, Mapping) else None
    if (
        not isinstance(oracle, Mapping)
        or oracle.get("id") != "m9-unsent-draft-config-recreation-v1"
        or oracle.get("quality_property")
        != "unsent TextFieldValue survives activity recreation"
        or not _is_nonempty_string(oracle.get("correct_behavior_spec"))
        or oracle.get("variant_input") is not False
        or tuple(oracle.get("allowed_conclusions", ()))
        != ("locally_supported", "locally_rejected", "inconclusive")
        or not isinstance(boundary, Mapping)
        or boundary.get("event") != "rotate"
        or boundary.get("rotation") != 1
        or boundary.get("activity_recreation_expected") is not True
    ):
        errors.append("oracle or configuration-recreation boundary drifted")

    evidence = document.get("evidence")
    attempt_inventory = (
        evidence.get("formal_attempt_inventory")
        if isinstance(evidence, Mapping)
        else None
    )
    attempt_validation = (
        evidence.get("attempt_evidence_validation")
        if isinstance(evidence, Mapping)
        else None
    )
    required_artifacts = (
        set(evidence.get("required_artifacts", ()))
        if isinstance(evidence, Mapping)
        else set()
    )
    if (
        not isinstance(evidence, Mapping)
        or evidence.get("root") != f"{R4_ARTIFACT_ROOT}/<lane-id>/"
        or evidence.get("checksums_required") is not True
        or evidence.get("append_only") is not True
        or evidence.get("formal_attempt_root_must_be_empty") is not True
        or not {
            "execution-record.json",
            "execution-provenance.json",
            "effective-execution-identity.json",
            "production-identities/*.json",
            "runner-setup.json",
            "production-seam-admission.json",
            "raw/screenshots/before.png",
            "raw/screenshots/after.png",
            "raw/layout/before.json",
            "raw/layout/after.json",
            "raw/logcat/rotation.txt",
            "rotation-event.json",
            "oracle-receipt.json",
            "finding.json",
            "residual-risk.json",
            "project-risk-map.json",
            "claim-boundary.json",
            "falsification-review.json",
            "falsification-review-output.json",
            "falsification-review-output-schema.json",
            "falsification-review-events.jsonl",
            "falsification-review-invocation.json",
            "falsification-review-prompt.md",
            "falsification-review-identity.json",
            "falsification-review-context.json",
            "review-input/execution-summary.json",
            "review-input/effective-execution-identity.json",
            "review-input/raw/screenshots/before.png",
            "review-input/raw/screenshots/after.png",
            "review-input/raw/layout/before.json",
            "review-input/raw/layout/after.json",
            "review-input/raw/logcat/rotation.txt",
            "review-input/rotation-event.json",
            "review-input/oracle-receipt.json",
            "review-input/finding.json",
            "review-input/claim-boundary.json",
            "attempt-evidence-validation.json",
            "checksums.sha256",
        }.issubset(required_artifacts)
        or not isinstance(attempt_inventory, Mapping)
        or attempt_inventory.get("path")
        != f"{R4_RUN_RECORD}/formal-attempt-inventory.json"
        or attempt_inventory.get("formal_attempt_id") != FORMAL_ATTEMPT_ID
        or attempt_inventory.get("required_before_reconciliation") is not True
        or not isinstance(attempt_validation, Mapping)
        or attempt_validation.get("version")
        != "m9-recovery-attempt-evidence-v2"
        or attempt_validation.get("repository_root") != "r4_clean_worktree"
        or attempt_validation.get("byte_validation_required_before_counting")
        is not True
        or attempt_validation.get("required_refs")
        != _ATTEMPT_EVIDENCE_REF_FILES
        or tuple(attempt_validation.get("validator_check_ids", ()))
        != _ATTEMPT_VALIDATOR_CHECKS
        or len(attempt_validation.get("validator_checks", ()))
        != len(_ATTEMPT_VALIDATOR_CHECKS)
    ):
        errors.append("formal evidence and attempt-inventory contract drifted")

    stop_rule = document.get("exploration_stop_rule")
    if (
        not isinstance(stop_rule, Mapping)
        or stop_rule.get("id") != "m9-recovery-exploration-stop-v2"
        or stop_rule.get("no_retry_or_replacement") is not True
        or len(stop_rule.get("stop_when", ())) != 3
        or stop_rule.get("unresolved_risk")
        != "preserve as ResidualRisk; never infer support"
    ):
        errors.append("exploration stop rule drifted")

    admission = document.get("admission")
    admission_audit = (
        admission.get("audit") if isinstance(admission, Mapping) else None
    )
    admission_checks = (
        admission_audit.get("checks")
        if isinstance(admission_audit, Mapping)
        else None
    )
    path_rebinding = (
        admission.get("path_rebinding")
        if isinstance(admission, Mapping)
        else None
    )
    if (
        not isinstance(admission, Mapping)
        or admission.get("six_exact_run_specs") is not True
        or admission.get("six_exact_runner_policy_pairs") is not True
        or admission.get("side_effects") is not False
        or admission.get("r3_receipt_scope")
        != "side_effect_free_feasibility_only_not_reusable_for_r4"
        or admission.get("r4_fresh_re_admission_required") is not True
        or not isinstance(admission_audit, Mapping)
        or admission_audit.get("status") != "pass"
        or admission_audit.get("receipt_count") != 6
        or admission_audit.get("formal_execution_started") is not False
        or not isinstance(admission_checks, list)
        or len(admission_checks) != 6
        or any(item.get("status") != "pass" for item in admission_checks)
        or not isinstance(path_rebinding, Mapping)
        or path_rebinding.get("only_paths_may_be_re_resolved") is not True
        or not _is_nonempty_string(path_rebinding.get("workdir"))
        or f"{R4_ARTIFACT_ROOT}/<lane-id>/artifacts"
        not in str(path_rebinding.get("artifact_dir", ""))
        or set(path_rebinding.get("immutable_runner_fields", ()))
        != {
            "device",
            "backend",
            "requested_driver_model",
            "requested_l3_model",
            "runner_policy_version",
            "expected_source_commit",
            "launch",
            "allow_host_project_subdir",
            "android_bin",
            "adb_bin",
            "codex_bin",
        }
    ):
        errors.append("side-effect-free admission or R4 path binding drifted")

    contradiction_packet = document.get("contradiction_packet")
    contradiction_audit = (
        contradiction_packet.get("audit")
        if isinstance(contradiction_packet, Mapping)
        else None
    )
    if (
        not isinstance(contradiction_packet, Mapping)
        or not _artifact_reference_is_bound(contradiction_packet)
        or not _is_nonempty_string(contradiction_packet.get("audit_path"))
        or not _is_sha256(contradiction_packet.get("audit_sha256"))
        or not _is_sha256(
            contradiction_packet.get("audit_canonical_sha256")
        )
        or not isinstance(contradiction_audit, Mapping)
        or not _contradiction_audit_is_eligible(contradiction_audit)
        or sha256_bytes(canonical_json_bytes(contradiction_audit))
        != contradiction_packet.get("audit_canonical_sha256")
    ):
        errors.append("denominator-external contradiction audit is not bound")

    leakage = document.get("leakage_audit")
    neutral = (
        leakage.get("neutral_packets") if isinstance(leakage, Mapping) else None
    )
    neutral_audit = neutral.get("audit") if isinstance(neutral, Mapping) else None
    run_specs = (
        leakage.get("run_specs") if isinstance(leakage, Mapping) else None
    )
    run_spec_audit = (
        run_specs.get("audit") if isinstance(run_specs, Mapping) else None
    )
    if (
        not isinstance(leakage, Mapping)
        or leakage.get("mapping_released") is not False
        or not _artifact_reference_is_bound(neutral)
        or not _is_nonempty_string(
            neutral.get("audit_path") if isinstance(neutral, Mapping) else None
        )
        or not _is_sha256(
            neutral.get("audit_sha256") if isinstance(neutral, Mapping) else None
        )
        or not isinstance(neutral_audit, Mapping)
        or neutral_audit.get("status") != "pass"
        or neutral_audit.get("packet_count") != 6
        or neutral_audit.get("mapping_released") is not False
        or not _artifact_reference_is_bound(run_specs)
        or not isinstance(run_spec_audit, Mapping)
        or run_spec_audit.get("status") != "pass"
        or run_spec_audit.get("mapping_released") is not False
        or len(run_spec_audit.get("checks", ())) != 6
    ):
        errors.append("neutral-packet or RunSpec leakage audit drifted")

    supported = document.get("supported_gate")
    expected_supported = {
        "accountable": "6/6",
        "attempt_evidence_validated": "6/6",
        "defect_supported": "3/3",
        "control_rejected": "3/3",
        "falsification_review_survived": "6/6",
        "review_identities_unique_and_policy_bound": True,
        "contradiction_pre_side_effect": True,
        "formal_attempt_inventory_checksum_bound": True,
        "formal_attempt_artifacts_exhaustively_enumerated": True,
        "one_formal_attempt_zero_retry_replacement": True,
        "all_required": True,
    }
    if not isinstance(supported, Mapping) or any(
        supported.get(key) != value for key, value in expected_supported.items()
    ):
        errors.append("Supported gate drifted")

    review = document.get("falsification_review")
    if not isinstance(review, Mapping) or (
        review.get("required_reviews") != 6
        or review.get("one_per_lane") is not True
        or review.get("clean_context") is not True
        or review.get("backend") != BACKEND
        or review.get("requested_model") is not None
        or review.get("model_selection") != "codex_cli_default"
        or review.get("role_and_expected_result_withheld") is not True
        or review.get("no_production_oracle_path") is not True
        or review.get("independent_invocation_identity") is not True
        or review.get("globally_disjoint_from_all_production_identities")
        is not True
        or review.get("authoritative_identity_receipt_required") is not True
        or review.get("checksum_bound_clean_context_required") is not True
        or review.get("isolated_allowlisted_workdir_required") is not True
        or review.get("byte_level_role_and_expected_result_scan_required")
        is not True
        or review.get("source_bytes_or_semantic_projection_bound") is not True
        or review.get("resume_forbidden") is not True
        or review.get("thread_id_disjoint_from_all_production") is not True
        or review.get("explicit_model_override_forbidden") is not True
        or review.get("read_only_exact_command_required") is not True
        or review.get("structured_output_and_event_stream_required")
        is not True
        or review.get("semantic_output_only") is not True
        or review.get("runner_generated_receipt_envelope") is not True
        or review.get("workspace_relative_prompt_inputs") is not True
        or review.get("prompt_embeds_exact_schema_and_dimensions") is not True
        or review.get("prompt_transport") != "final_argv"
        or review.get("runtime_metadata_excluded_from_model_output")
        is not True
        or review.get("output_schema_enforced_by_codex_cli") is not True
        or review.get("single_invocation_no_retry") is not True
        or review.get("pre_invocation_production_binding_required")
        is not True
        or review.get("terminal_failure_receipt_required") is not True
        or review.get("terminal_failure_receipt_schema_version") != 2
        or review.get("terminal_failure_receipt_lane_ledger_required")
        is not True
        or tuple(review.get("terminal_failure_stages", ()))
        != _REVIEW_TERMINAL_FAILURE_STAGES
        or review.get("execution_helper")
        != (
            "aiverify.bench.m9_recovery_qualification."
            "execute_falsification_review"
        )
        or tuple(review.get("required_input_files", ()))
        != _REVIEW_INPUT_FILES
        or review.get("same_provider_family_limitation_disclosed") is not True
        or tuple(review.get("required_receipt_fields", ()))
        != _REVIEW_REQUIRED_FIELDS
        or tuple(review.get("unique_fields_across_reviews", ()))
        != (
            "invocation_id",
            "identity_sha256",
            "clean_context_sha256",
            "production_invocation_id",
            "production_identity_sha256",
        )
    ):
        errors.append("Falsification Review identity/blinding policy drifted")

    claim = document.get("claim_boundary")
    if not isinstance(claim, Mapping) or claim.get("local_only") is not True:
        errors.append("claim boundary must remain local-only")
    exclusions = set(claim.get("exclusions", ())) if isinstance(claim, Mapping) else set()
    if not {
        "rewrite or rerun of #136/#137",
        "R1/R2 population reuse",
        "production, upstream, OEM, ColorOS, or physical-device claims",
    }.issubset(exclusions):
        errors.append("claim boundary exclusions are incomplete")

    packet = document.get("packet_commitment")
    actual_packet = freeze_payload_sha256(document)
    if not isinstance(packet, Mapping):
        errors.append("packet commitment must be an object")
    elif (
        packet.get("algorithm") != "sha256(canonical_json_bytes(freeze_payload))"
        or packet.get("sha256") != actual_packet
    ):
        errors.append("packet commitment contradicts freeze payload")

    return tuple(dict.fromkeys(errors))


def _mapping_errors(document: Mapping[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    if (
        document.get("schema_version") != 2
        or document.get("qualification_id") != QUALIFICATION_ID
        or tuple(document.get("lane_order", ())) != LANE_IDS
        or document.get("blocked_randomization")
        != "three_blocks_of_one_plus_one"
        or document.get("not_for_verifier_inputs") is not True
    ):
        errors.append("released auditor mapping identity/order/policy drifted")
    assignments = document.get("assignments")
    if not isinstance(assignments, list) or len(assignments) != 6:
        errors.append("released auditor mapping is not a six-lane population")
        return tuple(errors)
    assignment_ids = tuple(item.get("lane_id") for item in assignments)
    assignment_roles = tuple(item.get("role") for item in assignments)
    if (
        assignment_ids != LANE_IDS
        or sorted(assignment_roles) != ["control"] * 3 + ["defect"] * 3
        or any(
            set(assignment_roles[index : index + 2])
            != {"control", "defect"}
            for index in range(0, 6, 2)
        )
    ):
        errors.append(
            "released auditor mapping violates the frozen blocked 3+3 design"
        )
    return tuple(errors)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise M9RecoveryQualificationError(
                (f"duplicate manifest key: {key}",)
            )
        result[key] = value
    return result


__all__ = [
    "ACTIVITY",
    "APK_GLOB",
    "BACKEND",
    "CONTROL_APK_BYTES",
    "CONTROL_APK_SHA256",
    "CONTRADICTION_PACKET_ID",
    "CONTRADICTION_REJECTION_BOUNDARY",
    "CONTRADICTION_REQUIRED_FIELDS",
    "DEFECT_COMMIT",
    "DEFECT_APK_BYTES",
    "DEFECT_APK_SHA256",
    "DEFECT_TREE",
    "DEVICE",
    "FORMAL_ATTEMPT_ID",
    "FORMAL_HYPOTHESIS_ID",
    "LANE_IDS",
    "M9RecoveryAuditorMapping",
    "M9RecoveryQualificationError",
    "M9RecoveryQualificationManifest",
    "PACKAGE",
    "PROJECT_TARGET_COMMIT",
    "PROJECT_TARGET_TREE",
    "QUALIFICATION_ID",
    "R4_ARTIFACT_ROOT",
    "R4_RUN_RECORD",
    "RUNNER_POLICY",
    "SOURCE_ORIGIN",
    "audit_contradiction_packet",
    "audit_neutral_packets",
    "build_execution_review_summary",
    "canonical_json_bytes",
    "freeze_payload",
    "freeze_payload_sha256",
    "ensure_candidate_regeneration_allowed",
    "ensure_evidence_ledger_regeneration_allowed",
    "execute_falsification_review",
    "load_auditor_mapping",
    "load_manifest",
    "reconcile_formal_rows",
    "sealed_source_binding_ref",
    "sha256_bytes",
    "sha256_file",
    "validate_admission_receipts",
    "validate_formal_attempt_row",
    "validate_human_approval",
]
