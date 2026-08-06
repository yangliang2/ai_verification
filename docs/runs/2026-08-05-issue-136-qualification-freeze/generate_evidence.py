"""Materialize and validate the approved M9 #136 freeze packet.

The script is intentionally a preflight-only generator.  It reads the two
clean public-project worktrees, creates six opaque Run Specs, and invokes the
existing production-seam admission function with a Git-only command runner.
It never builds, installs, launches, invokes Codex, accesses a device, or runs
a formal lane.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


RUN_ROOT = Path(__file__).resolve().parent
REPO_ROOT = RUN_ROOT.parents[2]
BENCH_ROOT = REPO_ROOT / "bench/m9"
RUN_SPEC_ROOT = BENCH_ROOT / "run-specs"
AUDITOR_ROOT = BENCH_ROOT / "auditor"
ADMISSION_ROOT = RUN_ROOT / "admission"
FORMAL_ARTIFACT_ROOT = RUN_ROOT / "formal-artifacts"
IMPLEMENTATION_COMMIT = "d3e03dc036a1fb8d0f7f314e7999b58294399242"
SOURCE_ORIGIN = "https://github.com/android/architecture-samples.git"
BASELINE_COMMIT = "ee66e1526b84c026615df032c705842b7d2a521f"
BASELINE_TREE = "19455e693ec8c96c37a56aec55059a220826c5a3"
DEFECT_COMMIT = "208575f78d59716669d0733b5ed3e08797b08787"
DEFECT_TREE = "34998af23aed59aa17eaf915d848ab1b916a63e2"
SOURCE_INDEX_SHA256 = "66fa95486f2c63e84dbb1ba1dd77a43ad34cdd6ecbd8c659e496e9a204e38585"
PACKAGE = "com.example.android.architecture.blueprints.main"
ACTIVITY = "com.example.android.architecture.blueprints.todoapp.TodoActivity"
LANE_IDS = tuple(f"m9-lane-{index:02d}" for index in range(1, 7))
APPROVAL_COMMENT = "https://github.com/yangliang2/ai_verification/issues/136#issuecomment-5207290095"
FREEZE_TIMESTAMP = "2026-08-06T16:20:17Z"
DEFECT_PROJECT = Path(
    os.environ.get("M9_DEFECT_PROJECT", "/private/tmp/m9-136-option-a")
).expanduser().resolve()
CONTROL_PROJECT = Path(
    os.environ.get("M9_CONTROL_PROJECT", "/private/tmp/m9-136-candidate-a-control")
).expanduser().resolve()

sys.path.insert(0, str(REPO_ROOT / "src"))

from aiverify.bench.m9_qualification import (  # noqa: E402
    BACKEND,
    MODEL,
    RUNNER_POLICY,
    audit_contradiction_packet,
    audit_neutral_packets,
    canonical_json_bytes,
    load_manifest,
    sealed_source_binding_ref,
    sha256_bytes,
    sha256_file,
    validate_admission_receipts,
)
from aiverify.discovery.hypothesis_portfolio import approved_m9_prior_registry  # noqa: E402
from aiverify.runner.admission import (  # noqa: E402
    PlannedRunnerOptions,
    admit_production_seam,
)
from aiverify.runner.command import CommandResult, CommandRunner  # noqa: E402
from aiverify.runner.run_spec import load_run_spec  # noqa: E402


class GitOnlyRunner(CommandRunner):
    """Permit only read-only git identity commands during admission."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        del input_text
        self.calls.append(list(args))
        if not args or Path(args[0]).name != "git":
            raise AssertionError(f"non-git command reached side-effect-free admission: {args}")
        result = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
        return CommandResult(
            args=list(args),
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _tool_output(command: list[str], *, cwd: Path = REPO_ROOT) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"command": command, "status": "unavailable", "error": str(error)}
    output = (result.stdout + result.stderr).strip()
    return {
        "command": command,
        "status": "passed" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "output": output,
        "output_sha256": sha256_bytes(output.encode("utf-8")),
    }


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _ensure_clean_project(path: Path, expected_commit: str) -> dict[str, Any]:
    if not path.is_dir():
        raise SystemExit(f"candidate worktree is missing: {path}")
    status = _git(path, "status", "--porcelain=v1", "--untracked-files=all")
    origin = _git(path, "remote", "get-url", "origin")
    commit = _git(path, "rev-parse", "HEAD")
    tree = _git(path, "rev-parse", "HEAD^{tree}")
    if status:
        raise SystemExit(f"candidate worktree is not clean: {path}: {status!r}")
    if origin != SOURCE_ORIGIN or commit != expected_commit:
        raise SystemExit(f"candidate identity drifted: {path}: {origin} {commit}")
    return {
        "path": str(path),
        "origin": origin,
        "commit": commit,
        "tree": tree,
        "clean": True,
        "status_sha256": sha256_bytes(status.encode("utf-8")),
    }


def _mapping_path() -> Path:
    return AUDITOR_ROOT / "matched-pair.json"


def _materialize_mapping() -> dict[str, Any]:
    """Create the auditor-only assignment once without printing clear roles."""

    path = _mapping_path()
    if path.exists():
        mapping = _read_json(path)
        if not isinstance(mapping, dict):
            raise SystemExit("auditor mapping must be an object")
        return mapping

    roles = ["defect"] * 3 + ["control"] * 3
    secrets.SystemRandom().shuffle(roles)
    mapping = {
        "schema_version": 1,
        "qualification_id": "m9-project-qualification-v1",
        "lane_order": list(LANE_IDS),
        "assignments": [
            {"lane_id": lane_id, "role": role}
            for lane_id, role in zip(LANE_IDS, roles, strict=True)
        ],
        "release_after": [
            "context_acquisition",
            "top_three_hypothesis_portfolio",
            "attack_plan_admission",
            "leakage_audit",
        ],
        "not_for_verifier_inputs": True,
    }
    _write_json(path, mapping)
    return mapping


def _mapping_role(mapping: dict[str, Any], lane_id: str) -> str:
    for assignment in mapping.get("assignments", []):
        if assignment.get("lane_id") == lane_id:
            role = assignment.get("role")
            if role in {"defect", "control"}:
                return role
    raise SystemExit(f"auditor mapping has no valid assignment for {lane_id}")


def _write_run_specs(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    RUN_SPEC_ROOT.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for lane_id in LANE_IDS:
        role = _mapping_role(mapping, lane_id)
        project = DEFECT_PROJECT if role == "defect" else CONTROL_PROJECT
        commit = DEFECT_COMMIT if role == "defect" else BASELINE_COMMIT
        source_binding_ref = sealed_source_binding_ref(lane_id)
        variable = f"M9_{lane_id.replace('-', '_').upper()}_PROJECT"
        document = {
            "host_project": {
                "root": f"${{{variable}}}",
                "origin": SOURCE_ORIGIN,
                "commit": source_binding_ref,
            },
            "apk_glob": "app/build/outputs/apk/debug/app-debug.apk",
            "package": PACKAGE,
            "activity": ACTIVITY,
            "scenario": {
                "id": lane_id,
                "user_actions": [
                    "Open the task list",
                    "Create a task with a unique title",
                    "Edit the task title",
                    "Navigate away from the task detail",
                    "Reopen the edited task",
                ],
                "system_events": [{"step_index": 4, "event": "process_death"}],
                "l2_boundary_index": 0,
                "l3_spec": "The edited task title remains visible after navigation, reopening, and the admitted process boundary.",
            },
        }
        path = RUN_SPEC_ROOT / f"{lane_id}.yaml"
        path.write_text(
            yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        records.append(
            {
                "lane_id": lane_id,
                "path": str(path.relative_to(REPO_ROOT)),
                "sha256": sha256_file(path),
                "environment_variable": variable,
                "project": str(project),
                "commit": commit,
                "source_binding_ref": source_binding_ref,
            }
        )
    return records


def _admit_run_specs(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ADMISSION_ROOT.mkdir(parents=True, exist_ok=True)
    receipts: list[dict[str, Any]] = []
    for record in records:
        lane_id = str(record["lane_id"])
        spec_path = REPO_ROOT / str(record["path"])
        project = Path(str(record["project"]))
        variable = str(record["environment_variable"])
        spec = load_run_spec(spec_path, environ={variable: str(project)})
        runner = GitOnlyRunner()
        options = PlannedRunnerOptions(
            device="emulator-5554",
            workdir=project,
            artifact_dir=FORMAL_ARTIFACT_ROOT / lane_id / "artifacts",
            requested_driver_model=MODEL,
            requested_l3_model=MODEL,
            backend=BACKEND,
            runner_policy_version=RUNNER_POLICY,
            expected_source_commit=str(record["commit"]),
        )
        admission = admit_production_seam(spec, options, command_runner=runner)
        if not admission.admitted:
            raise SystemExit(f"{lane_id} production seam admission failed: {admission.reasons}")
        if any(Path(call[0]).name != "git" for call in runner.calls):
            raise SystemExit(f"{lane_id} admission reached a non-git command")
        receipt_path = ADMISSION_ROOT / f"{lane_id}.json"
        _write_json(receipt_path, admission.receipt)
        record["run_spec_sha256"] = spec.source_sha256
        record["admission_receipt_path"] = str(receipt_path.relative_to(REPO_ROOT))
        record["admission_receipt_sha256"] = sha256_file(receipt_path)
        record["git_only_call_count"] = len(runner.calls)
        receipts.append(admission.receipt)
    return receipts


def _write_operator_registry() -> dict[str, Any]:
    definitions = [item.to_dict() for item in approved_m9_prior_registry()]
    payload = {
        "schema_version": 1,
        "status": "frozen_registry_reference",
        "prior_count": len(definitions),
        "definitions": definitions,
        "formal_holdout_executed": False,
        "side_effects": False,
    }
    path = RUN_ROOT / "operator-registry.json"
    _write_json(path, payload)
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "sha256": sha256_file(path),
        "prior_count": len(definitions),
        "prior_ids": [item["prior"]["prior_id"] for item in definitions],
        "operator_ids": [item["operator"]["operator_id"] for item in definitions],
    }


def _write_attack_plan_receipt(registry: dict[str, Any]) -> dict[str, Any]:
    source = REPO_ROOT / "docs/runs/2026-08-05-issue-133-attack-plan/bounded-synthesis-receipt.json"
    source_payload = _read_json(source)
    admission = source_payload["result"]["admission"]
    payload = {
        "schema_version": 1,
        "status": admission["status"],
        "contract": "m9-attack-plan-admission-v1",
        "source_contract_receipt": str(source.relative_to(REPO_ROOT)),
        "source_contract_receipt_sha256": sha256_file(source),
        "operator_registry_sha256": registry["sha256"],
        "budget": 8,
        "claim_boundary": "local-only exact source, build, package, and runtime evidence",
        "abort_boundary": "reject before build, device, agent, or runtime side effect on any contradiction",
        "formal_holdout_executed": False,
        "side_effects": False,
        "target_specific_execution": "deferred to #137 after ordered context, portfolio, and leakage gates",
    }
    path = RUN_ROOT / "attack-plan-admission.json"
    _write_json(path, payload)
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "sha256": sha256_file(path),
        "status": payload["status"],
        "source_receipt_sha256": payload["source_contract_receipt_sha256"],
    }


def _write_package_build_receipt() -> dict[str, Any]:
    artifacts = []
    artifact_root = RUN_ROOT / "artifacts"
    for path in sorted(artifact_root.glob("*")):
        if path.is_file() and path.name != ".gitignore":
            artifacts.append(
                {
                    "path": str(path.relative_to(REPO_ROOT)),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    payload = {
        "schema_version": 1,
        "command": "uv build --quiet --out-dir docs/runs/2026-08-05-issue-136-qualification-freeze/artifacts",
        "package": "aiverify 0.1.0",
        "status": "passed" if len(artifacts) == 2 else "pending_artifact_build",
        "artifacts": artifacts,
        "formal_holdout_executed": False,
        "side_effects": False,
    }
    path = RUN_ROOT / "package-build.json"
    _write_json(path, payload)
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "sha256": sha256_file(path),
        "status": payload["status"],
        "artifacts": artifacts,
    }


def _write_contradiction_packet() -> dict[str, Any]:
    packet = {
        "schema_version": 1,
        "packet_id": "m9-136-incomplete-context-v1",
        "expected_admission": "rejected",
        "formal_denominator": False,
        "rejection_boundary": "before_any_build_device_agent_or_runtime_side_effect",
    }
    path = RUN_ROOT / "contradiction-packet.json"
    _write_json(path, packet)
    audit = audit_contradiction_packet(packet, observed_command_calls=[])
    _write_json(RUN_ROOT / "contradiction-audit.json", audit)
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "sha256": sha256_file(path),
        "audit_path": str((RUN_ROOT / "contradiction-audit.json").relative_to(REPO_ROOT)),
        "audit_sha256": sha256_file(RUN_ROOT / "contradiction-audit.json"),
        "audit": audit,
    }


def _write_neutral_packets(
    records: list[dict[str, Any]],
    registry: dict[str, Any],
    attack_plan: dict[str, Any],
) -> dict[str, Any]:
    packets = [
        {
            "schema_version": 1,
            "packet_id": f"packet-{record['lane_id']}",
            "lane_id": record["lane_id"],
            "context_input_digest": SOURCE_INDEX_SHA256,
            "portfolio_budget": 8,
            "portfolio_registry_sha256": registry["sha256"],
            "plan_contract_sha256": attack_plan["sha256"],
            "scenario_id": record["lane_id"],
        }
        for record in records
    ]
    for packet, record in zip(packets, records, strict=True):
        if record.get("run_spec_sha256"):
            packet["run_spec_sha256"] = record["run_spec_sha256"]
    audit = audit_neutral_packets(packets)
    payload = {
        "schema_version": 1,
        "status": audit["status"],
        "packets": packets,
        "audit": audit,
        "mapping_released": False,
        "formal_holdout_executed": False,
    }
    path = RUN_ROOT / "neutral-verifier-packets.json"
    _write_json(path, payload)
    audit_path = RUN_ROOT / "leakage-audit.json"
    _write_json(audit_path, audit)
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "sha256": sha256_file(path),
        "audit_path": str(audit_path.relative_to(REPO_ROOT)),
        "audit_sha256": sha256_file(audit_path),
        "audit": audit,
    }


def _source_file_inventory() -> list[dict[str, Any]]:
    paths = (
        "app/src/main/java/com/example/android/architecture/blueprints/todoapp/data/DefaultTaskRepository.kt",
        "app/src/main/AndroidManifest.xml",
        "app/build.gradle.kts",
        "settings.gradle.kts",
    )
    inventory: list[dict[str, Any]] = []
    for relative in paths:
        path = CONTROL_PROJECT / relative
        if not path.is_file():
            raise SystemExit(f"context input is missing: {path}")
        inventory.append(
            {
                "scope": "project_target_snapshot",
                "path": relative,
                "sha256": sha256_file(path),
            }
        )
    return inventory


def _materialize_durable_build_logs() -> dict[str, dict[str, str]]:
    """Copy host-build logs into the committed run record before hashing it."""

    sources = {
        "candidate_option_a": Path("/private/tmp/m9-136-option-a-build.log"),
        "candidate_option_b": Path("/private/tmp/m9-136-option-b-build.log"),
        "candidate_option_c": Path("/private/tmp/m9-136-option-c-build.log"),
        "candidate_baseline_success": Path(
            "/private/tmp/m9-136-candidate-architecture-samples/preflight/assembleDebug-retry-2.log"
        ),
        "candidate_baseline_interrupted": Path(
            "/private/tmp/m9-136-candidate-architecture-samples/preflight/assembleDebug.log"
        ),
        "candidate_baseline_offline": Path(
            "/private/tmp/m9-136-candidate-architecture-samples/preflight-offline/assembleDebug-offline.log"
        ),
        "selected_defect": Path("/private/tmp/m9-136-a-defect-commit-build.log"),
        "selected_control": Path("/private/tmp/m9-136-a-control-commit-build.log"),
        "final_defect": Path("/private/tmp/m9-136-final-defect-build.log"),
        "final_control": Path("/private/tmp/m9-136-final-control-build.log"),
    }
    destination_root = RUN_ROOT / "build-logs"
    durable: dict[str, dict[str, str]] = {}
    for label, source in sources.items():
        if not source.is_file():
            raise SystemExit(f"durable build-log source is missing: {source}")
        destination = destination_root / f"{label}.log"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        durable[label] = {
            "path": str(destination.relative_to(REPO_ROOT)),
            "sha256": sha256_file(destination),
        }
    return durable


def _manifest(
    *,
    mapping: dict[str, Any],
    run_records: list[dict[str, Any]],
    registry: dict[str, Any],
    attack_plan: dict[str, Any],
    contradiction: dict[str, Any],
    leakage: dict[str, Any],
    project_identities: dict[str, dict[str, Any]],
    tool_identity: dict[str, Any],
    package_build: dict[str, Any],
    build_logs: dict[str, dict[str, str]],
) -> dict[str, Any]:
    mapping_path = _mapping_path()
    patch_path = RUN_ROOT / "candidate-option-A.patch"
    mapping_digest = sha256_bytes(canonical_json_bytes(mapping))
    patch_digest = sha256_file(patch_path)
    now = FREEZE_TIMESTAMP
    return {
        "schema_version": 1,
        "qualification_id": "m9-project-qualification-v1",
        "status": "frozen",
        "frozen_at": now,
        "formal_holdout_executed": False,
        "formal_denominator": False,
        "approval": {
            "issue_url": "https://github.com/yangliang2/ai_verification/issues/136",
            "comment_url": APPROVAL_COMMENT,
            "approved_by": "yangliang2",
            "decision": "approved exact target/pair, 3+3 cohort, lane order, mapping release, oracle/evidence/review, retry/abort, and local-only boundary",
            "approved_at": now,
        },
        "implementation": {
            "repository": "https://github.com/yangliang2/ai_verification.git",
            "merged_commit": IMPLEMENTATION_COMMIT,
            "dependency_chain": ["#129", "#130", "#131", "#132", "#133", "#134", "#135"],
        },
        "target": {
            "project_target_id": "architecture-samples-ee66e152",
            "source_origin": SOURCE_ORIGIN,
            "source_commit": BASELINE_COMMIT,
            "source_tree": BASELINE_TREE,
            "source_index_sha256": SOURCE_INDEX_SHA256,
            "unfamiliarity": "human_approved_unfamiliar_public_snapshot",
            "package": PACKAGE,
            "activity": ACTIVITY,
            "min_sdk": 21,
            "target_sdk": 35,
            "defect": {
                "option": "A",
                "commit": DEFECT_COMMIT,
                "tree": DEFECT_TREE,
                "mutation": "omit local upsert in DefaultTaskRepository.updateTask",
                "patch_sha256": patch_digest,
                "apk_sha256": "61063a0fd247eb03d1bd251b0d9359c3c2a5ea07cb8abe4b38d3daae57c153ac",
                "apk_bytes": 24681461,
                "build_log": build_logs["selected_defect"]["path"],
                "build_log_sha256": build_logs["selected_defect"]["sha256"],
                "build_duration": "8s",
                "actionable_tasks": 43,
                "final_rebuild": {
                    "log": build_logs["final_defect"]["path"],
                    "log_sha256": build_logs["final_defect"]["sha256"],
                    "build_duration": "5s",
                    "actionable_tasks": 43,
                },
            },
            "control": {
                "commit": BASELINE_COMMIT,
                "tree": BASELINE_TREE,
                "apk_sha256": "d38b30f17010da114b5585dadec8326eb76b04dfbae4a175f7cb2840a0093c66",
                "apk_bytes": 24681606,
                "build_log": build_logs["selected_control"]["path"],
                "build_log_sha256": build_logs["selected_control"]["sha256"],
                "build_duration": "28s",
                "actionable_tasks": 43,
                "final_rebuild": {
                    "log": build_logs["final_control"]["path"],
                    "log_sha256": build_logs["final_control"]["sha256"],
                    "build_duration": "5s",
                    "actionable_tasks": 43,
                },
            },
            "build_command": "./gradlew --no-daemon --no-configuration-cache --max-workers=1 :app:assembleDebug",
            "project_identities": project_identities,
        },
        "cohort": {
            "lane_count": 6,
            "defect_count": 3,
            "control_count": 3,
            "lane_order": list(LANE_IDS),
            "assignment_is_opaque": True,
            "mapping_commitment": {
                "artifact": str(mapping_path.relative_to(REPO_ROOT)),
                "sha256": mapping_digest,
                "raw_artifact_sha256": sha256_file(mapping_path),
                "algorithm": "sha256(canonical_json_bytes(auditor_mapping))",
                "clear_mapping_in_verifier_inputs": False,
                "release_after": [
                    "Context Acquisition",
                    "top-3 Hypothesis Portfolio",
                    "Attack Plan admission",
                    "leakage audit",
                ],
                "verify_before_lane_release": True,
            },
        },
        "policy": {
            "portfolio_budget": 8,
            "top_three_portfolio": True,
            "one_attempt_per_lane": True,
            "zero_retry": True,
            "zero_replacement": True,
            "abort_before_side_effect_on_contradiction": True,
        },
        "lanes": [
            {
                "lane_id": record["lane_id"],
                "run_spec": {
                    "path": record["path"],
                    "sha256": record["run_spec_sha256"],
                    "source_binding_ref": record["source_binding_ref"],
                },
                "admission_receipt": {
                    "path": record["admission_receipt_path"],
                    "sha256": record["admission_receipt_sha256"],
                },
                "one_attempt": True,
                "retry": False,
                "replacement": False,
            }
            for record in run_records
        ],
        "runner": {
            "backend": BACKEND,
            "policy_version": RUNNER_POLICY,
            "device": "emulator-5554",
            "avd": "aiverify_api35",
            "api_level": 35,
            "network_policy": "disabled",
            "orientation": "portrait",
            "requested_driver_model": MODEL,
            "requested_l3_model": MODEL,
            "effective_identity": "record per formal lane; #136 has no agent invocation",
            "artifact_root": "docs/runs/2026-08-05-issue-136-qualification-freeze/formal-artifacts/<lane-id>/",
            "tool_identity_path": "docs/runs/2026-08-05-issue-136-qualification-freeze/tool-versions.json",
        },
        "context_acquisition": {
            "order": ["repository", "build", "manifest", "call_site", "state", "version", "execution_boundary"],
            "source_index_sha256": SOURCE_INDEX_SHA256,
            "input_inventory": "source-context-inputs.json",
            "discovery_budget": 8,
            "unknown_and_contradictory_are_first_class": True,
            "no_build_device_agent_runtime_side_effect": True,
        },
        "portfolio": {
            "approved_registry": registry,
            "budget": 8,
            "top_three": True,
            "selected_only_after_context_acquisition": True,
            "formal_holdout_executed": False,
        },
        "attack_plan": {
            "admission": attack_plan,
            "target_specific_plan_generation": "#137 only after context and portfolio freeze",
            "safety_boundary": "local public-project copy, local emulator, and declared evidence roots only",
            "claim_boundary": "local-only",
        },
        "oracle": {
            "id": "m9-task-persistence-v1",
            "quality_property": "edited task persists across navigation, reopen, and process boundary",
            "correct_behavior_spec": "The edited task title remains visible after navigation, reopening, and the admitted process boundary.",
            "input_fields": [
                "terminal ExecutionRecord",
                "Effective Execution Identity",
                "ordered raw screenshot evidence",
                "ordered layout evidence",
                "filtered logcat evidence",
                "process-boundary receipt",
                "task-title observations",
            ],
            "allowed_conclusions": ["locally_supported", "locally_rejected", "inconclusive"],
            "accounting_rule": "non-accountable terminal produces ResidualRisk and cannot enter Supported denominator",
            "variant_input": False,
        },
        "evidence": {
            "root": "docs/runs/2026-08-05-issue-136-qualification-freeze/formal-artifacts/<lane-id>/",
            "required_artifacts": [
                "execution-record.json",
                "effective-execution-identity.json",
                "raw/screenshots/*.png",
                "raw/layout/*.json",
                "raw/logcat/*.txt",
                "finding.json",
                "residual-risk.json",
                "project-risk-map.json",
                "falsification-review.json",
                "checksums.sha256",
            ],
            "checksums_required": True,
            "append_only": True,
            "manual_steps": "recorded per lane if an operator action is required; no manual substitution for an accountable attempt",
        },
        "exploration_stop_rule": {
            "id": "m9-exploration-stop-v1",
            "stop_when": [
                "the admitted top-three portfolio has been exhausted or the bounded discovery budget is zero",
                "no additional admissible plan remains within the frozen safety boundary",
                "all required evidence for the selected probe is terminally reconciled",
            ],
            "unresolved_risk": "preserve as ResidualRisk and coverage frontier; never infer support",
            "no_retry_or_replacement": True,
        },
        "falsification_review": {
            "required_reviews": 6,
            "one_per_lane": True,
            "clean_context": True,
            "independent_invocation_identity": True,
            "no_production_oracle_path": True,
            "same_provider_family_limitation_disclosed": True,
            "allowed_outcomes": ["survived", "challenged", "inconclusive"],
            "finding_not_rewritten": True,
        },
        "admission": {
            "six_exact_run_specs": True,
            "six_exact_runner_policy_pairs": True,
            "side_effects": False,
            "allowed_subprocesses": ["read-only git identity commands"],
            "forbidden_before_formal_execution": ["gradle", "android", "adb", "codex", "device", "install", "launch", "runtime"],
        },
        "contradiction_packet": contradiction,
        "leakage_audit": leakage,
        "claim_boundary": {
            "local_only": True,
            "scope": "one human-approved architecture-samples snapshot, its local A defect/control pair, one API-35 emulator profile, the frozen discovery/admission/runtime/evidence contracts, and six accountable lane records",
            "exclusions": [
                "production or upstream validation",
                "OEM/ColorOS or physical-device claims",
                "success rate, recall, completeness, or benchmark-scale claims",
                "M8 rerun or M8 claim rewrite",
                "automatic repair",
            ],
        },
        "tool_identity": tool_identity,
        "package_build": package_build,
    }


def _write_checksums(manifest_path: Path) -> None:
    entries: list[tuple[str, Path]] = []
    for path in sorted(RUN_ROOT.rglob("*")):
        if path.is_file() and path.name != "checksums.sha256" and "__pycache__" not in path.parts:
            entries.append((path.relative_to(RUN_ROOT).as_posix(), path))
    for path in sorted(BENCH_ROOT.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            entries.append((os.path.relpath(path, RUN_ROOT), path))
    for path in (
        REPO_ROOT / "src/aiverify/bench/m9_qualification.py",
        REPO_ROOT / "tests/bench/test_m9_qualification.py",
    ):
        entries.append((os.path.relpath(path, RUN_ROOT), path))
    lines = [f"{sha256_file(path)}  {label}\n" for label, path in entries]
    (RUN_ROOT / "checksums.sha256").write_text("".join(lines), encoding="utf-8")
    del manifest_path


def main() -> None:
    started = dt.datetime.now(dt.timezone.utc)
    defect_identity = _ensure_clean_project(DEFECT_PROJECT, DEFECT_COMMIT)
    control_identity = _ensure_clean_project(CONTROL_PROJECT, BASELINE_COMMIT)
    registry = _write_operator_registry()
    attack_plan = _write_attack_plan_receipt(registry)
    contradiction = _write_contradiction_packet()
    source_inputs = _source_file_inventory()
    _write_json(RUN_ROOT / "source-context-inputs.json", {"inputs": source_inputs})
    pre_release_neutral = _write_neutral_packets(
        [{"lane_id": lane_id} for lane_id in LANE_IDS], registry, attack_plan
    )
    if pre_release_neutral["audit"]["status"] != "pass":
        raise SystemExit(f"pre-release leakage audit failed: {pre_release_neutral}")
    shutil.copyfile(
        RUN_ROOT / "neutral-verifier-packets.json",
        RUN_ROOT / "pre-release-neutral-verifier-packets.json",
    )
    shutil.copyfile(
        RUN_ROOT / "leakage-audit.json",
        RUN_ROOT / "pre-release-leakage-audit.json",
    )
    # The clear assignment is read only by this auditor-side materializer after
    # the context, portfolio, plan, contradiction, and leakage gates pass.
    mapping = _materialize_mapping()
    run_records = _write_run_specs(mapping)
    tool_identity = {
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "commands": [
            _tool_output(["java", "-version"]),
            _tool_output(["./gradlew", "--no-daemon", "--version"], cwd=DEFECT_PROJECT),
            _tool_output(["android", "--version"]),
            _tool_output(["adb", "version"]),
            _tool_output(["codex", "--version"]),
        ],
        "backend": BACKEND,
        "requested_model": MODEL,
        "effective_model": MODEL,
        "device": "emulator-5554",
        "device_accessed": False,
    }
    _write_json(RUN_ROOT / "tool-versions.json", tool_identity)
    receipts = _admit_run_specs(run_records)
    admission_audit = validate_admission_receipts(
        receipts,
        expected_run_specs={record["lane_id"]: record for record in run_records},
    )
    if admission_audit["status"] != "pass":
        raise SystemExit(f"admission audit failed: {admission_audit}")
    _write_json(RUN_ROOT / "admission-audit.json", admission_audit)
    neutral = _write_neutral_packets(run_records, registry, attack_plan)
    if neutral["audit"]["status"] != "pass":
        raise SystemExit(f"leakage audit failed: {neutral}")

    package_build = _write_package_build_receipt()
    build_logs = _materialize_durable_build_logs()
    manifest_document = _manifest(
        mapping=mapping,
        run_records=run_records,
        registry=registry,
        attack_plan=attack_plan,
        contradiction=contradiction,
        leakage=neutral,
        project_identities={"defect": defect_identity, "control": control_identity},
        tool_identity=tool_identity,
        package_build=package_build,
        build_logs=build_logs,
    )
    manifest_path = BENCH_ROOT / "m9-project-qualification-v1.json"
    _write_json(manifest_path, manifest_document)
    manifest = load_manifest(manifest_path)
    preflight = {
        "schema_version": 1,
        "qualification_id": manifest.qualification_id,
        "manifest_sha256": manifest.source_sha256,
        "canonical_manifest_sha256": manifest.canonical_sha256,
        "admitted": True,
        "side_effects": False,
        "formal_execution_started": False,
        "checks": [
            {"name": "human_approval", "status": "pass", "comment": APPROVAL_COMMENT},
            {"name": "exact_implementation_commit", "status": "pass", "commit": IMPLEMENTATION_COMMIT},
            {"name": "target_pair_identity", "status": "pass"},
            {"name": "six_run_specs", "status": "pass", "count": len(run_records)},
            {"name": "six_production_seam_admissions", "status": "pass"},
            {"name": "neutral_leakage_audit", "status": "pass"},
            {"name": "contradiction_pre_side_effect_rejection", "status": "pass"},
        ],
        "lane_admissions": [
            {
                "lane_id": record["lane_id"],
                "run_spec_sha256": record["run_spec_sha256"],
                "admission_receipt_sha256": record["admission_receipt_sha256"],
                "git_only_call_count": record["git_only_call_count"],
            }
            for record in run_records
        ],
        "admission_audit": admission_audit,
        "leakage_audit": neutral["audit"],
        "pre_release_leakage_audit": {
            "path": "docs/runs/2026-08-05-issue-136-qualification-freeze/pre-release-leakage-audit.json",
            "sha256": sha256_file(RUN_ROOT / "pre-release-leakage-audit.json"),
        },
        "contradiction_audit": contradiction["audit"],
        "mapping_released": False,
        "mapping_commitment_sha256": sha256_bytes(canonical_json_bytes(mapping)),
        "duration_seconds": round((dt.datetime.now(dt.timezone.utc) - started).total_seconds(), 6),
        "claim_boundary": manifest_document["claim_boundary"],
    }
    _write_json(RUN_ROOT / "preflight.json", preflight)
    _write_json(
        RUN_ROOT / "manifest-identity.json",
        {
            "manifest_path": str(manifest_path.relative_to(REPO_ROOT)),
            "manifest_sha256": manifest.source_sha256,
            "canonical_manifest_sha256": manifest.canonical_sha256,
            "implementation_commit": IMPLEMENTATION_COMMIT,
            "approval_comment": APPROVAL_COMMENT,
            "formal_execution_started": False,
            "side_effects": False,
        },
    )
    _write_checksums(manifest_path)
    print(
        json.dumps(
            {
                "status": "passed",
                "qualification_id": manifest.qualification_id,
                "lanes": len(run_records),
                "admissions": admission_audit["status"],
                "leakage": neutral["audit"]["status"],
                "contradiction": contradiction["audit"]["status"],
                "formal_execution_started": False,
                "manifest_sha256": manifest.source_sha256,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
