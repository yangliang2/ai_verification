"""Prepare the fresh M9-R3 candidate freeze without formal execution.

The default mode validates the two exact public-project worktrees, copies their
host-only build evidence, creates six role-neutral Run Specs, and admits every
Run Spec/runner pair with a Git-only command runner.  It never installs,
launches, accesses a device, invokes Codex, or executes a formal lane.

Human approval is a separate operation.  ``--finalize-approval-url`` changes
only the approval envelope and status; the stable freeze-payload commitment
must remain byte-for-byte identical.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml


RUN_ROOT = Path(__file__).resolve().parent
REPO_ROOT = RUN_ROOT.parents[2]
BENCH_ROOT = REPO_ROOT / "bench/m9/recovery-v2"
RUN_SPEC_ROOT = BENCH_ROOT / "run-specs"
AUDITOR_ROOT = BENCH_ROOT / "auditor"
ADMISSION_ROOT = RUN_ROOT / "admission"
MANIFEST_PATH = REPO_ROOT / "bench/m9/m9-recovery-project-qualification-v2.json"
SNAPSHOT_A = Path("/private/tmp/m9-r3-snapshot-a")
SNAPSHOT_B = Path("/private/tmp/m9-r3-snapshot-b")
SNAPSHOT_A_BUILD_LOG = Path("/private/tmp/m9-r3-snapshot-a-build.log")
SNAPSHOT_B_BUILD_LOG = Path("/private/tmp/m9-r3-snapshot-b-build.log")
BASE_MAIN_COMMIT = "099cf64228273ef67bd23c6bad4af6239e580aa1"
ISSUE_URL = "https://github.com/yangliang2/ai_verification/issues/152"
UPSTREAM_PR_URL = "https://github.com/android/compose-samples/pull/996"
UPSTREAM_PR_BASE = "743e5177c925a5b48049a718de7aa9d36799bd29"
UPSTREAM_HEAD = "5c66b10bed66fa4efe75146bb5b9795cf36f09da"
UPSTREAM_MERGED_AT = "2022-10-24T19:45:22Z"
TOKENS = (
    "r4q01-nacre",
    "r4q02-ember",
    "r4q03-lumen",
    "r4q04-cobalt",
    "r4q05-saffron",
    "r4q06-velvet",
)
SOURCE_SCOPE = (
    "Jetchat/app/src/main/java/com/example/compose/jetchat/conversation/UserInput.kt",
    "Jetchat/app/src/main/AndroidManifest.xml",
    "Jetchat/app/build.gradle.kts",
    "Jetchat/settings.gradle.kts",
    "Jetchat/gradle/libs.versions.toml",
    "LICENSE",
)

sys.path.insert(0, str(REPO_ROOT / "src"))

from aiverify.bench.m9_recovery_qualification import (  # noqa: E402
    ACTIVITY,
    APK_GLOB,
    BACKEND,
    CONTRADICTION_PACKET_ID,
    DEFECT_COMMIT,
    DEFECT_TREE,
    DEVICE,
    FORMAL_ATTEMPT_ID,
    LANE_IDS,
    PACKAGE,
    PROJECT_TARGET_COMMIT,
    PROJECT_TARGET_TREE,
    QUALIFICATION_ID,
    R4_ARTIFACT_ROOT,
    R4_RUN_RECORD,
    RUNNER_POLICY,
    SOURCE_ORIGIN,
    audit_contradiction_packet,
    audit_neutral_packets,
    canonical_json_bytes,
    ensure_candidate_regeneration_allowed,
    ensure_evidence_ledger_regeneration_allowed,
    freeze_payload_sha256,
    load_auditor_mapping,
    load_manifest,
    sealed_source_binding_ref,
    sha256_bytes,
    sha256_file,
    validate_admission_receipts,
    validate_human_approval,
)
from aiverify.discovery.hypothesis_portfolio import (  # noqa: E402
    approved_m9_prior_registry,
)
from aiverify.runner.admission import (  # noqa: E402
    PlannedRunnerOptions,
    admit_production_seam,
)
from aiverify.runner.command import CommandResult, CommandRunner  # noqa: E402
from aiverify.runner.run_spec import load_run_spec  # noqa: E402


class GitOnlyRunner(CommandRunner):
    """Permit only read-only Git identity calls during R3 admission."""

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
            raise AssertionError(
                f"non-Git command reached side-effect-free admission: {args}"
            )
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


def _normalize_evidence_text(value: str) -> str:
    """Remove trailing whitespace while preserving line content and final LF."""

    normalized = "\n".join(line.rstrip() for line in value.splitlines())
    return normalized + ("\n" if value.endswith(("\n", "\r")) else "")


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
        timeout=120,
    )
    return result.stdout.strip()


def _tool_output(command: list[str], *, cwd: Path = REPO_ROOT) -> dict[str, Any]:
    started = dt.datetime.now(dt.timezone.utc)
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "command": command,
            "status": "unavailable",
            "error": str(error),
        }
    output = (result.stdout + result.stderr).strip()
    return {
        "command": command,
        "status": "passed" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "duration_seconds": round(
            (dt.datetime.now(dt.timezone.utc) - started).total_seconds(),
            6,
        ),
        "output": output,
        "output_sha256": sha256_bytes(output.encode("utf-8")),
    }


def _ensure_source(
    path: Path,
    *,
    expected_commit: str,
    expected_tree: str,
) -> dict[str, Any]:
    if not path.is_dir():
        raise SystemExit(f"candidate source is missing: {path}")
    status = _git(path, "status", "--porcelain=v1", "--untracked-files=all")
    origin = _git(path, "remote", "get-url", "origin")
    commit = _git(path, "rev-parse", "HEAD")
    tree = _git(path, "rev-parse", "HEAD^{tree}")
    if status:
        raise SystemExit(f"candidate source is not clean: {path}: {status!r}")
    if (
        origin != SOURCE_ORIGIN
        or commit != expected_commit
        or tree != expected_tree
    ):
        raise SystemExit(
            f"candidate identity drifted: {path}: {origin} {commit} {tree}"
        )
    return {
        "path": str(path),
        "origin": origin,
        "commit": commit,
        "tree": tree,
        "clean": True,
        "status_sha256": sha256_bytes(status.encode("utf-8")),
    }


def _write_freshness_audit() -> dict[str, Any]:
    pattern = (
        "compose-samples|Jetchat|"
        f"{DEFECT_COMMIT}|{PROJECT_TARGET_COMMIT}|m9-unsent-draft"
    )
    command = [
        "git",
        "grep",
        "-n",
        "-E",
        pattern,
        BASE_MAIN_COMMIT,
        "--",
        ".",
    ]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    passed = (
        result.returncode == 1
        and result.stdout == ""
        and result.stderr == ""
    )
    payload = {
        "schema_version": 2,
        "status": "pass" if passed else "fail",
        "base_main_commit": BASE_MAIN_COMMIT,
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "stdout_sha256": sha256_bytes(result.stdout.encode("utf-8")),
        "stderr_sha256": sha256_bytes(result.stderr.encode("utf-8")),
        "matched_paths": [],
        "historical_population_reused": False,
    }
    path = RUN_ROOT / "freshness-audit.json"
    _write_json(path, payload)
    if not passed:
        raise SystemExit(f"freshness audit failed: {payload}")
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "sha256": sha256_file(path),
        "audit": payload,
    }


def _apk_record(source: Path) -> dict[str, Any]:
    path = source / APK_GLOB
    if not path.is_file():
        raise SystemExit(f"built APK is missing: {path}")
    apkanalyzer = shutil.which("apkanalyzer")
    if apkanalyzer is None:
        raise SystemExit("apkanalyzer is required for built APK identity proof")
    resolved_tool = Path(apkanalyzer).resolve()

    def inspect(verb: str) -> dict[str, Any]:
        command = [str(resolved_tool), "manifest", verb, str(path)]
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        if result.returncode != 0:
            raise SystemExit(
                f"APK inspection failed: {command}: {result.stderr.strip()}"
            )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        return {
            "command": command,
            "returncode": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_sha256": sha256_bytes(stdout.encode("utf-8")),
            "stderr_sha256": sha256_bytes(stderr.encode("utf-8")),
        }

    package_inspection = inspect("application-id")
    manifest_inspection = inspect("print")
    try:
        root = ET.fromstring(str(manifest_inspection["stdout"]))
    except ET.ParseError as error:
        raise SystemExit(f"apkanalyzer returned invalid manifest XML: {error}") from error
    android_name = "{http://schemas.android.com/apk/res/android}name"
    launchable: list[str] = []
    for activity in root.findall("./application/activity"):
        actions = {
            str(node.get(android_name))
            for node in activity.findall("./intent-filter/action")
        }
        categories = {
            str(node.get(android_name))
            for node in activity.findall("./intent-filter/category")
        }
        if (
            "android.intent.action.MAIN" in actions
            and "android.intent.category.LAUNCHER" in categories
        ):
            launchable.append(str(activity.get(android_name)))
    if (
        package_inspection["stdout"] != PACKAGE
        or launchable != [ACTIVITY]
    ):
        raise SystemExit(
            "built APK identity drifted: "
            f"package={package_inspection['stdout']!r}, "
            f"launchable={launchable!r}"
        )
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "package": package_inspection["stdout"],
        "launchable_activities": launchable,
        "inspection": {
            "tool": {
                "requested": "apkanalyzer",
                "resolved_path": str(resolved_tool),
                "sha256": sha256_file(resolved_tool),
            },
            "package": package_inspection,
            "manifest": manifest_inspection,
        },
    }


def _parse_build_log(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"build log is missing: {path}")
    text = path.read_text(encoding="utf-8")
    real = re.search(r"^real ([0-9.]+)$", text, flags=re.MULTILINE)
    tasks = re.search(
        r"^([0-9]+) actionable tasks: (.+)$",
        text,
        flags=re.MULTILINE,
    )
    successful = "BUILD SUCCESSFUL" in text
    if not successful or real is None or tasks is None:
        raise SystemExit(f"build log is not a complete successful build: {path}")
    return {
        "status": "passed",
        "duration_seconds": float(real.group(1)),
        "actionable_tasks": int(tasks.group(1)),
        "task_summary": tasks.group(2),
        "source_path": str(path),
        "sha256": sha256_file(path),
    }


def _copy_build_evidence(
    source_identities: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    log_root = RUN_ROOT / "build-logs"
    log_root.mkdir(parents=True, exist_ok=True)
    builds: dict[str, Any] = {}
    for label, source, source_log in (
        ("snapshot-a", SNAPSHOT_A, SNAPSHOT_A_BUILD_LOG),
        ("snapshot-b", SNAPSHOT_B, SNAPSHOT_B_BUILD_LOG),
    ):
        destination = log_root / f"{label}.log"
        raw_log = source_log.read_bytes()
        normalized_log = _normalize_evidence_text(
            raw_log.decode("utf-8")
        )
        destination.write_text(normalized_log, encoding="utf-8")
        parsed = _parse_build_log(destination)
        parsed["path"] = str(destination.relative_to(REPO_ROOT))
        parsed.pop("source_path", None)
        parsed["external_source_path"] = str(source_log)
        parsed["external_source_sha256"] = sha256_bytes(raw_log)
        parsed["normalization"] = "rstrip_trailing_whitespace_per_line"
        parsed["apk"] = _apk_record(source)
        parsed["source_identity"] = source_identities[label]
        builds[label] = parsed
    _write_json(RUN_ROOT / "buildability.json", builds)
    _write_json(
        RUN_ROOT / "apk-identity.json",
        {
            "schema_version": 2,
            "status": "passed",
            "snapshots": {
                label: {
                    "source_commit": builds[label]["source_identity"]["commit"],
                    "apk": builds[label]["apk"],
                }
                for label in ("snapshot-a", "snapshot-b")
            },
            "device_accessed": False,
        },
    )
    return builds


def _write_auditor_provenance(
    source_identities: dict[str, dict[str, Any]],
    builds: dict[str, Any],
    freshness: dict[str, Any],
) -> dict[str, Any]:
    auditor = RUN_ROOT / "auditor"
    auditor.mkdir(parents=True, exist_ok=True)
    raw_diff = subprocess.run(
        [
            "git",
            "diff",
            "--no-ext-diff",
            "--binary",
            DEFECT_COMMIT,
            PROJECT_TARGET_COMMIT,
            "--",
            SOURCE_SCOPE[0],
        ],
        cwd=SNAPSHOT_A,
        text=True,
        capture_output=True,
        check=True,
        timeout=120,
    ).stdout
    diff = _normalize_evidence_text(raw_diff)
    patch = auditor / "matched-pair.patch"
    patch.write_text(diff, encoding="utf-8")
    changed = _git(
        SNAPSHOT_A,
        "diff",
        "--name-only",
        DEFECT_COMMIT,
        PROJECT_TARGET_COMMIT,
    ).splitlines()
    parent_line = _git(
        SNAPSHOT_B,
        "rev-list",
        "--parents",
        "-n",
        "1",
        PROJECT_TARGET_COMMIT,
    ).split()
    payload = {
        "schema_version": 2,
        "auditor_only": True,
        "source_origin": SOURCE_ORIGIN,
        "upstream_pr": {
            "url": UPSTREAM_PR_URL,
            "number": 996,
            "base_sha_at_open": UPSTREAM_PR_BASE,
            "head_sha": UPSTREAM_HEAD,
            "merge_commit_sha": PROJECT_TARGET_COMMIT,
            "merge_parents": parent_line[1:],
            "merged_at": UPSTREAM_MERGED_AT,
            "title": (
                "[Jetchat] Improve UserInputText textState using "
                "rememberSaveable"
            ),
            "reported_reproduction": [
                "open Jetchat on a resizable large device",
                "enter unsent text in UserInputText",
                "resize through multi-window",
                "observe the text reset before the fix",
            ],
            "reported_solution": (
                "replace remember with rememberSaveable and "
                "TextFieldValue.Saver"
            ),
        },
        "matched_pair": {
            "defect": source_identities["snapshot-a"],
            "control": source_identities["snapshot-b"],
            "first_parent_is_defect": parent_line[1] == DEFECT_COMMIT,
            "changed_files": changed,
            "changed_file_count": len(changed),
            "patch": str(patch.relative_to(REPO_ROOT)),
            "patch_sha256": sha256_file(patch),
            "upstream_raw_patch_sha256": sha256_bytes(
                raw_diff.encode("utf-8")
            ),
            "patch_normalization": "rstrip_trailing_whitespace_per_line",
        },
        "builds": builds,
        "license": {
            "spdx": "Apache-2.0",
            "path": "LICENSE",
            "sha256": sha256_file(SNAPSHOT_B / "LICENSE"),
        },
        "freshness": {
            "project": "android/compose-samples Jetchat",
            "behavior": "unsent Compose TextFieldValue across configuration recreation",
            "absent_from_repository_before_r3": True,
            "historical_input_reuse": False,
            "base_tree_audit": freshness,
        },
    }
    path = auditor / "candidate-provenance.json"
    _write_json(path, payload)
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "sha256": sha256_file(path),
        "patch": str(patch.relative_to(REPO_ROOT)),
        "patch_sha256": sha256_file(patch),
    }


def _source_inventory() -> dict[str, Any]:
    inputs: list[dict[str, Any]] = []
    for relative in SOURCE_SCOPE:
        path = SNAPSHOT_B / relative
        if not path.is_file():
            raise SystemExit(f"source context input is missing: {path}")
        inputs.append(
            {
                "scope": "project_target_snapshot",
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    digest = sha256_bytes(canonical_json_bytes(inputs))
    payload = {
        "schema_version": 2,
        "source_origin": SOURCE_ORIGIN,
        "source_commit": PROJECT_TARGET_COMMIT,
        "source_tree": PROJECT_TARGET_TREE,
        "inputs": inputs,
        "canonical_inventory_sha256": digest,
        "role_or_expected_result_included": False,
    }
    path = RUN_ROOT / "source-context-inputs.json"
    _write_json(path, payload)
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "sha256": sha256_file(path),
        "canonical_inventory_sha256": digest,
        "input_count": len(inputs),
    }


def _write_registry_and_plan() -> tuple[dict[str, Any], dict[str, Any]]:
    definitions = [item.to_dict() for item in approved_m9_prior_registry()]
    registry_payload = {
        "schema_version": 2,
        "status": "frozen_registry_reference",
        "prior_count": len(definitions),
        "definitions": definitions,
        "formal_holdout_executed": False,
        "side_effects": False,
    }
    registry_path = RUN_ROOT / "operator-registry.json"
    _write_json(registry_path, registry_payload)
    registry = {
        "path": str(registry_path.relative_to(REPO_ROOT)),
        "sha256": sha256_file(registry_path),
        "prior_count": len(definitions),
        "prior_ids": [item["prior"]["prior_id"] for item in definitions],
        "operator_ids": [
            item["operator"]["operator_id"] for item in definitions
        ],
    }

    source = (
        REPO_ROOT
        / "docs/runs/2026-08-05-issue-133-attack-plan/"
        "bounded-synthesis-receipt.json"
    )
    plan_payload = {
        "schema_version": 2,
        "status": "admitted_contract_reference",
        "contract": "m9-attack-plan-admission-v1",
        "source_contract_receipt": str(source.relative_to(REPO_ROOT)),
        "source_contract_receipt_sha256": sha256_file(source),
        "operator_registry_sha256": registry["sha256"],
        "budget": 8,
        "formal_target_specific_generation": (
            "R4 only after fresh Context Acquisition and portfolio freeze"
        ),
        "abort_boundary": (
            "reject before build, device, agent, or runtime side effect on "
            "any contradiction"
        ),
        "formal_holdout_executed": False,
        "side_effects": False,
    }
    plan_path = RUN_ROOT / "attack-plan-contract.json"
    _write_json(plan_path, plan_payload)
    plan = {
        "path": str(plan_path.relative_to(REPO_ROOT)),
        "sha256": sha256_file(plan_path),
        "status": plan_payload["status"],
        "source_receipt_sha256": plan_payload[
            "source_contract_receipt_sha256"
        ],
    }
    return registry, plan


def _write_contradiction() -> dict[str, Any]:
    packet = {
        "schema_version": 2,
        "packet_id": CONTRADICTION_PACKET_ID,
        "expected_admission": "rejected",
        "formal_denominator": False,
        "rejection_boundary": (
            "before_any_build_device_agent_or_runtime_side_effect"
        ),
    }
    packet_path = RUN_ROOT / "contradiction-packet.json"
    _write_json(packet_path, packet)
    audit = audit_contradiction_packet(packet, observed_command_calls=[])
    audit_path = RUN_ROOT / "contradiction-audit.json"
    _write_json(audit_path, audit)
    if audit["status"] != "pass":
        raise SystemExit(f"contradiction audit failed: {audit}")
    return {
        "path": str(packet_path.relative_to(REPO_ROOT)),
        "sha256": sha256_file(packet_path),
        "audit_path": str(audit_path.relative_to(REPO_ROOT)),
        "audit_sha256": sha256_file(audit_path),
        "audit_canonical_sha256": sha256_bytes(canonical_json_bytes(audit)),
        "audit": audit,
    }


def _mapping_path() -> Path:
    return AUDITOR_ROOT / "matched-pair.json"


def _materialize_mapping() -> dict[str, Any]:
    path = _mapping_path()
    if path.exists():
        value = _read_json(path)
        if not isinstance(value, dict):
            raise SystemExit("auditor mapping must be an object")
        mapping = value
    else:
        roles: list[str] = []
        random = secrets.SystemRandom()
        for _ in range(3):
            block = ["defect", "control"]
            random.shuffle(block)
            roles.extend(block)
        mapping = {
            "schema_version": 2,
            "qualification_id": QUALIFICATION_ID,
            "lane_order": list(LANE_IDS),
            "blocked_randomization": "three_blocks_of_one_plus_one",
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
    validated = load_auditor_mapping(
        path,
        expected_raw_sha256=sha256_file(path),
        expected_canonical_sha256=sha256_bytes(
            canonical_json_bytes(mapping)
        ),
    )
    return dict(validated.document)


def _mapping_role(mapping: dict[str, Any], lane_id: str) -> str:
    for assignment in mapping.get("assignments", []):
        if assignment.get("lane_id") == lane_id:
            role = assignment.get("role")
            if role in {"defect", "control"}:
                return str(role)
    raise SystemExit(f"mapping has no valid assignment for {lane_id}")


def _run_spec_document(lane_id: str, token: str) -> dict[str, Any]:
    variable = f"M9_{lane_id.replace('-', '_').upper()}_PROJECT"
    return {
        "host_project": {
            "root": f"${{{variable}}}",
            "origin": SOURCE_ORIGIN,
            "commit": sealed_source_binding_ref(lane_id),
        },
        "apk_glob": APK_GLOB,
        "package": PACKAGE,
        "activity": ACTIVITY,
        "live_validation": {
            "timeout_seconds": 30,
        },
        "scenario": {
            "id": lane_id,
            "user_actions": [
                (
                    "On the launched Jetchat conversation screen, locate the "
                    "Text input field. Do not type or tap Send yet."
                ),
                (
                    "Tap Text input, enter the exact token "
                    f"{token}, dismiss only the soft keyboard without sending, "
                    f"verify {token} remains visible, and leave the unsent "
                    "draft in place."
                ),
                (
                    "After the configuration boundary, do not type, repair, "
                    "send, navigate, or reopen anything. Inspect the same Text "
                    f"input field and report whether the exact token {token} "
                    "remains visible."
                ),
            ],
            "system_events": [
                {
                    "step_index": 1,
                    "event": "rotate",
                    "args": {"rotation": "1"},
                }
            ],
            "l2_boundary_index": 0,
            "l3_spec": (
                f"The unsent draft token {token} remains present in the "
                "Jetchat Text input after the admitted portrait-to-landscape "
                "activity recreation, without retyping or sending it."
            ),
        },
    }


def _write_run_specs(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    RUN_SPEC_ROOT.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for lane_id, token in zip(LANE_IDS, TOKENS, strict=True):
        role = _mapping_role(mapping, lane_id)
        source = SNAPSHOT_A if role == "defect" else SNAPSHOT_B
        commit = DEFECT_COMMIT if role == "defect" else PROJECT_TARGET_COMMIT
        path = RUN_SPEC_ROOT / f"{lane_id}.yaml"
        path.write_text(
            yaml.safe_dump(
                _run_spec_document(lane_id, token),
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        records.append(
            {
                "lane_id": lane_id,
                "token": token,
                "path": str(path.relative_to(REPO_ROOT)),
                "run_spec_sha256": sha256_file(path),
                "environment_variable": (
                    f"M9_{lane_id.replace('-', '_').upper()}_PROJECT"
                ),
                "source": str(source),
                "commit": commit,
                "source_binding_ref": sealed_source_binding_ref(lane_id),
            }
        )
    return records


def _audit_run_specs(records: list[dict[str, Any]]) -> dict[str, Any]:
    forbidden = {
        "role-defect": b"defect",
        "role-control": b"control",
        "snapshot-a-path": str(SNAPSHOT_A).encode(),
        "snapshot-b-path": str(SNAPSHOT_B).encode(),
        "defect-commit": DEFECT_COMMIT.encode(),
        "control-commit": PROJECT_TARGET_COMMIT.encode(),
        "defect-tree": DEFECT_TREE.encode(),
        "control-tree": PROJECT_TARGET_TREE.encode(),
    }
    checks = []
    for record in records:
        source = (REPO_ROOT / record["path"]).read_bytes().lower()
        found = sorted(
            name for name, needle in forbidden.items() if needle.lower() in source
        )
        checks.append(
            {
                "lane_id": record["lane_id"],
                "status": "pass" if not found else "fail",
                "forbidden_material": found,
                "role_disclosed": False if not found else None,
                "actual_source_identity_disclosed": False if not found else None,
            }
        )
    result = {
        "schema_version": 2,
        "status": (
            "pass"
            if len(checks) == 6
            and all(item["status"] == "pass" for item in checks)
            else "fail"
        ),
        "checks": checks,
        "mapping_released": False,
    }
    path = RUN_ROOT / "run-spec-leakage-audit.json"
    _write_json(path, result)
    if result["status"] != "pass":
        raise SystemExit(f"Run Spec leakage audit failed: {result}")
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "sha256": sha256_file(path),
        "audit": result,
    }


def _write_neutral_packets(
    records: list[dict[str, Any]],
    *,
    source_inventory: dict[str, Any],
    registry: dict[str, Any],
    plan: dict[str, Any],
    name: str,
) -> dict[str, Any]:
    packets = []
    for lane_id in LANE_IDS:
        packet = {
            "schema_version": 2,
            "packet_id": f"packet-{lane_id}",
            "lane_id": lane_id,
            "context_input_digest": source_inventory[
                "canonical_inventory_sha256"
            ],
            "portfolio_budget": 8,
            "portfolio_registry_sha256": registry["sha256"],
            "plan_contract_sha256": plan["sha256"],
            "scenario_id": lane_id,
        }
        record = next(
            (item for item in records if item.get("lane_id") == lane_id),
            None,
        )
        if record is not None and record.get("run_spec_sha256"):
            packet["run_spec_sha256"] = record["run_spec_sha256"]
        packets.append(packet)
    audit = audit_neutral_packets(packets)
    payload = {
        "schema_version": 2,
        "status": audit["status"],
        "packets": packets,
        "audit": audit,
        "mapping_released": False,
        "formal_holdout_executed": False,
    }
    path = RUN_ROOT / f"{name}-neutral-verifier-packets.json"
    audit_path = RUN_ROOT / f"{name}-leakage-audit.json"
    _write_json(path, payload)
    _write_json(audit_path, audit)
    if audit["status"] != "pass":
        raise SystemExit(f"{name} neutral packet audit failed: {audit}")
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "sha256": sha256_file(path),
        "audit_path": str(audit_path.relative_to(REPO_ROOT)),
        "audit_sha256": sha256_file(audit_path),
        "audit": audit,
    }


def _admit_run_specs(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ADMISSION_ROOT.mkdir(parents=True, exist_ok=True)
    receipts: list[dict[str, Any]] = []
    for record in records:
        lane_id = str(record["lane_id"])
        source = Path(str(record["source"]))
        variable = str(record["environment_variable"])
        spec_path = REPO_ROOT / str(record["path"])
        spec = load_run_spec(spec_path, environ={variable: str(source)})
        runner = GitOnlyRunner()
        options = PlannedRunnerOptions(
            device=DEVICE,
            workdir=source,
            artifact_dir=(
                REPO_ROOT
                / R4_ARTIFACT_ROOT
                / lane_id
                / "artifacts"
            ),
            expected_source_commit=str(record["commit"]),
            launch=True,
            requested_driver_model=None,
            requested_l3_model=None,
            backend=BACKEND,
            runner_policy_version=RUNNER_POLICY,
            allow_host_project_subdir=False,
        )
        admission = admit_production_seam(
            spec,
            options,
            command_runner=runner,
        )
        if not admission.admitted:
            raise SystemExit(
                f"{lane_id} production admission failed: {admission.reasons}"
            )
        if any(Path(call[0]).name != "git" for call in runner.calls):
            raise SystemExit(f"{lane_id} admission invoked a non-Git command")
        receipt_path = ADMISSION_ROOT / f"{lane_id}.json"
        _write_json(receipt_path, admission.receipt)
        record["admission_receipt_path"] = str(
            receipt_path.relative_to(REPO_ROOT)
        )
        record["admission_receipt_sha256"] = sha256_file(receipt_path)
        record["git_only_call_count"] = len(runner.calls)
        receipts.append(admission.receipt)
    return receipts


def _tool_identity() -> dict[str, Any]:
    payload = {
        "schema_version": 2,
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "commands": [
            _tool_output(["git", "--version"]),
            _tool_output(["java", "-version"]),
            _tool_output(
                ["./gradlew", "--no-daemon", "--version"],
                cwd=SNAPSHOT_B / "Jetchat",
            ),
            _tool_output(["android", "--version"]),
            _tool_output(["adb", "version"]),
            _tool_output(["codex", "--version"]),
        ],
        "backend": BACKEND,
        "model_selection": "codex_cli_default",
        "requested_driver_model": None,
        "requested_l3_model": None,
        "device": DEVICE,
        "device_accessed": False,
    }
    path = RUN_ROOT / "tool-versions.json"
    _write_json(path, payload)
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "sha256": sha256_file(path),
        "payload": payload,
    }


def _candidate_manifest(
    *,
    source_identities: dict[str, dict[str, Any]],
    freshness: dict[str, Any],
    builds: dict[str, Any],
    provenance: dict[str, Any],
    source_inventory: dict[str, Any],
    mapping: dict[str, Any],
    records: list[dict[str, Any]],
    admission_audit: dict[str, Any],
    registry: dict[str, Any],
    plan: dict[str, Any],
    contradiction: dict[str, Any],
    leakage: dict[str, Any],
    run_spec_leakage: dict[str, Any],
    tools: dict[str, Any],
) -> dict[str, Any]:
    mapping_path = _mapping_path()
    mapping_canonical = sha256_bytes(canonical_json_bytes(mapping))
    manifest: dict[str, Any] = {
        "schema_version": 2,
        "qualification_id": QUALIFICATION_ID,
        "status": "awaiting_human_approval",
        "prepared_at": dt.datetime.now(dt.timezone.utc).isoformat(
            timespec="seconds"
        ),
        "frozen_at": None,
        "formal_holdout_executed": False,
        "formal_denominator": False,
        "approval": {
            "status": "pending",
            "issue_url": ISSUE_URL,
            "comment_url": None,
            "approved_by": None,
            "approved_at": None,
            "required_scope": [
                "exact ProjectTarget snapshot and matched pair",
                "six-lane blocked hidden assignment commitment",
                "unsent-draft portrait-to-landscape recreation probe",
                "one formal attempt with zero retry or replacement",
                "all-or-nothing Supported gate and local-only boundary",
            ],
        },
        "implementation": {
            "repository": "https://github.com/yangliang2/ai_verification.git",
            "base_main_commit": BASE_MAIN_COMMIT,
            "issue": "#152",
            "branch": "m9-r3-fresh-qualification-freeze",
            "qualification_module": (
                "src/aiverify/bench/m9_recovery_qualification.py"
            ),
            "formal_consumer_entrypoint": (
                "python -m aiverify.bench.m9_recovery_formal"
            ),
            "formal_consumer_implementation": "R4 only after merged freeze",
        },
        "history_exclusion": {
            "forbidden_qualification_ids": [
                "m9-project-qualification-v1",
                "m9-r1-recovery-baseline",
                "m9-r2-non-holdout-canary",
            ],
            "forbidden_issues": ["#136", "#137", "#148", "#150"],
            "reuse_permitted": False,
            "copy_into_denominator_permitted": False,
            "historical_artifact_rewrite_permitted": False,
            "freshness_audit": freshness,
        },
        "target": {
            "project_target_id": "compose-samples-jetchat-038c8208",
            "source_origin": SOURCE_ORIGIN,
            "source_commit": PROJECT_TARGET_COMMIT,
            "source_tree": PROJECT_TARGET_TREE,
            "source_index_sha256": source_inventory[
                "canonical_inventory_sha256"
            ],
            "source_scope": list(SOURCE_SCOPE),
            "unfamiliarity": "fresh_public_project_and_behavior_for_m9_recovery",
            "package": PACKAGE,
            "activity": ACTIVITY,
            "apk_glob": APK_GLOB,
            "min_sdk": 21,
            "target_sdk": 33,
            "compile_sdk": 33,
            "license": "Apache-2.0",
            "upstream_pr": UPSTREAM_PR_URL,
            "matched_pair_relation": (
                "control merge commit has defect commit as first parent and "
                "differs by one focused source file"
            ),
            "defect": {
                "commit": DEFECT_COMMIT,
                "tree": DEFECT_TREE,
                "source_identity": source_identities["snapshot-a"],
                "apk": builds["snapshot-a"]["apk"],
                "build_log": builds["snapshot-a"]["path"],
                "build_log_sha256": builds["snapshot-a"]["sha256"],
            },
            "control": {
                "commit": PROJECT_TARGET_COMMIT,
                "tree": PROJECT_TARGET_TREE,
                "source_identity": source_identities["snapshot-b"],
                "apk": builds["snapshot-b"]["apk"],
                "build_log": builds["snapshot-b"]["path"],
                "build_log_sha256": builds["snapshot-b"]["sha256"],
            },
            "focused_diff": provenance,
            "build_command": (
                "./gradlew --no-daemon --no-configuration-cache "
                "--max-workers=1 :app:assembleDebug"
            ),
            "build_cwd": "Jetchat",
        },
        "cohort": {
            "lane_count": 6,
            "defect_count": 3,
            "control_count": 3,
            "lane_order": list(LANE_IDS),
            "blocked_randomization": "three_blocks_of_one_plus_one",
            "assignment_is_opaque": True,
            "mapping_commitment": {
                "artifact": str(mapping_path.relative_to(REPO_ROOT)),
                "sha256": mapping_canonical,
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
            "one_formal_attempt": True,
            "one_attempt_per_lane": True,
            "zero_retry": True,
            "zero_replacement": True,
            "zero_discretionary_rerun": True,
            "denominator_changes_after_start": False,
            "adverse_result_is_terminal": True,
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
                "r3_feasibility_admission_receipt": {
                    "path": record["admission_receipt_path"],
                    "sha256": record["admission_receipt_sha256"],
                },
                "planned_r4_runner": {
                    "artifact_dir_relative": (
                        f"{R4_ARTIFACT_ROOT}/{record['lane_id']}/artifacts"
                    ),
                    "workdir_binding": (
                        "clean_source_worktree_resolved_from_released_mapping"
                    ),
                    "source_binding_ref": record["source_binding_ref"],
                    "path_resolution_root": "r4_clean_worktree",
                    "fresh_side_effect_free_re_admission_required": True,
                },
                "probe_token": record["token"],
                "one_attempt": True,
                "retry": False,
                "replacement": False,
            }
            for record in records
        ],
        "runner": {
            "backend": BACKEND,
            "policy_version": RUNNER_POLICY,
            "device": DEVICE,
            "avd": "aiverify_api35",
            "api_level": 35,
            "network_policy": "disabled",
            "pre_lane_orientation": "portrait",
            "boundary_orientation": "landscape",
            "orientation_postconditions": {
                "before": "user_rotation=0",
                "after": "user_rotation=1",
                "accelerometer_rotation": "0",
            },
            "package_reset": "idempotent already-absent-or-cleared",
            "live_validation": (
                "environment gate before deployment; installed app surface "
                "is verified by explicit launch and the first Journey "
                "checkpoint"
            ),
            "requested_driver_model": None,
            "requested_l3_model": None,
            "model_selection": "codex_cli_default",
            "effective_model_identity": (
                "record each invocation from authoritative Codex CLI event"
            ),
            "instruction_contract": [
                "type the exact lane token once",
                "never tap Send",
                "after the boundary never retype, repair, navigate, or reopen",
                "the driver reports observations; the oracle decides",
            ],
            "tool_identity_path": tools["path"],
        },
        "context_acquisition": {
            "order": [
                "repository",
                "build",
                "manifest",
                "call_site",
                "state",
                "version",
                "execution_boundary",
            ],
            "source_index": source_inventory,
            "discovery_budget": 8,
            "unknown_and_contradictory_are_first_class": True,
            "no_build_device_agent_runtime_side_effect": True,
            "fresh_execution_required_in_r4": True,
        },
        "portfolio": {
            "approved_registry": registry,
            "budget": 8,
            "top_three": True,
            "selected_only_after_fresh_context_acquisition": True,
            "formal_holdout_executed": False,
        },
        "attack_plan": {
            "contract": plan,
            "target_specific_plan_generation": (
                "R4 only after fresh context and portfolio freeze"
            ),
            "safety_boundary": (
                "local public-project copy, local emulator, and declared "
                "evidence roots only"
            ),
            "claim_boundary": "local-only",
        },
        "oracle": {
            "id": "m9-unsent-draft-config-recreation-v1",
            "quality_property": (
                "unsent TextFieldValue survives activity recreation"
            ),
            "correct_behavior_spec": (
                "The exact unsent lane token remains in Jetchat Text input "
                "after the admitted portrait-to-landscape configuration "
                "recreation without retyping or sending."
            ),
            "boundary": {
                "event": "rotate",
                "rotation": 1,
                "activity_recreation_expected": True,
            },
            "input_fields": [
                "terminal ExecutionRecord",
                "Effective Execution Identity",
                "ordered before/after screenshot evidence",
                "ordered before/after layout evidence",
                "filtered logcat evidence",
                "rotation event receipt and postconditions",
                "exact lane-token observations",
            ],
            "allowed_conclusions": [
                "locally_supported",
                "locally_rejected",
                "inconclusive",
            ],
            "accounting_rule": (
                "non-accountable terminal evidence cannot enter Supported"
            ),
            "variant_input": False,
        },
        "evidence": {
            "root": f"{R4_ARTIFACT_ROOT}/<lane-id>/",
            "formal_attempt_inventory": {
                "path": f"{R4_RUN_RECORD}/formal-attempt-inventory.json",
                "formal_attempt_id": FORMAL_ATTEMPT_ID,
                "required_before_reconciliation": True,
            },
            "attempt_evidence_validation": {
                "version": "m9-recovery-attempt-evidence-v2",
                "repository_root": "r4_clean_worktree",
                "byte_validation_required_before_counting": True,
                "required_refs": {
                    "execution_record": "execution-record.json",
                    "execution_provenance": "execution-provenance.json",
                    "effective_execution_identity": (
                        "effective-execution-identity.json"
                    ),
                    "runner_setup": "runner-setup.json",
                    "production_seam_admission": (
                        "production-seam-admission.json"
                    ),
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
                    "falsification_review_output": (
                        "falsification-review-output.json"
                    ),
                    "falsification_review_output_schema": (
                        "falsification-review-output-schema.json"
                    ),
                    "falsification_review_events": (
                        "falsification-review-events.jsonl"
                    ),
                    "falsification_review_invocation": (
                        "falsification-review-invocation.json"
                    ),
                    "falsification_review_prompt": (
                        "falsification-review-prompt.md"
                    ),
                    "falsification_review_identity": (
                        "falsification-review-identity.json"
                    ),
                    "falsification_review_context": (
                        "falsification-review-context.json"
                    ),
                    "lane_ledger": "checksums.sha256",
                },
                "validator_check_ids": [
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
                ],
                "validator_checks": [
                    "terminal authoritative ExecutionRecord",
                    "ExecutionRecord attempt id bound to lane and inventory",
                    (
                        "complete execution provenance semantically validated "
                        "and cross-bound"
                    ),
                    "effective production identity summary",
                    "authoritative Codex event receipts for all production invocations",
                    "fresh R4 production-seam admission",
                    "successful explicit runner setup and launch",
                    "ordered screenshot/layout/logcat/rotation evidence",
                    "oracle conclusion, token observations, and accountability",
                    "semantic Finding and evidence references",
                    "semantic ResidualRisk preserving unresolved frontier",
                    "semantic Project Risk Map",
                    "local-only claim boundary preserving #137",
                    "separate bound Falsification Review",
                    (
                        "structured review output, invocation ledger, and "
                        "Codex event stream cross-bound"
                    ),
                    "authoritative Codex event receipt for the review",
                    "checksum-bound clean review context",
                    (
                        "byte-scanned allowlisted review inputs with role and "
                        "expected result withheld"
                    ),
                    "exhaustive lane checksum ledger",
                ],
            },
            "required_artifacts": [
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
            ],
            "checksums_required": True,
            "append_only": True,
            "formal_attempt_root_must_be_empty": True,
        },
        "exploration_stop_rule": {
            "id": "m9-recovery-exploration-stop-v2",
            "stop_when": [
                "the admitted top-three portfolio is exhausted",
                "no additional admissible plan remains in the frozen boundary",
                "all required evidence for the selected probe is terminal",
            ],
            "unresolved_risk": (
                "preserve as ResidualRisk; never infer support"
            ),
            "no_retry_or_replacement": True,
        },
        "falsification_review": {
            "required_reviews": 6,
            "one_per_lane": True,
            "clean_context": True,
            "independent_invocation_identity": True,
            "globally_disjoint_from_all_production_identities": True,
            "authoritative_identity_receipt_required": True,
            "checksum_bound_clean_context_required": True,
            "isolated_allowlisted_workdir_required": True,
            "byte_level_role_and_expected_result_scan_required": True,
            "source_bytes_or_semantic_projection_bound": True,
            "resume_forbidden": True,
            "thread_id_disjoint_from_all_production": True,
            "explicit_model_override_forbidden": True,
            "read_only_exact_command_required": True,
            "structured_output_and_event_stream_required": True,
            "semantic_output_only": True,
            "runner_generated_receipt_envelope": True,
            "workspace_relative_prompt_inputs": True,
            "prompt_embeds_exact_schema_and_dimensions": True,
            "prompt_transport": "final_argv",
            "runtime_metadata_excluded_from_model_output": True,
            "output_schema_enforced_by_codex_cli": True,
            "single_invocation_no_retry": True,
            "pre_invocation_production_binding_required": True,
            "terminal_failure_receipt_required": True,
            "terminal_failure_receipt_schema_version": 2,
            "terminal_failure_receipt_lane_ledger_required": True,
            "terminal_failure_stages": [
                "runner_exception",
                "runner_command_mismatch",
                "process_exit",
                "timeout",
                "event_stream_persistence",
                "missing_output",
                "identity_capture",
                "final_binding",
            ],
            "execution_helper": (
                "aiverify.bench.m9_recovery_qualification."
                "execute_falsification_review"
            ),
            "required_input_files": [
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
            ],
            "backend": BACKEND,
            "requested_model": None,
            "model_selection": "codex_cli_default",
            "effective_model_identity": (
                "record each review from authoritative Codex CLI event"
            ),
            "role_and_expected_result_withheld": True,
            "no_production_oracle_path": True,
            "same_provider_family_limitation_disclosed": True,
            "required_receipt_fields": [
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
            ],
            "unique_fields_across_reviews": [
                "invocation_id",
                "identity_sha256",
                "clean_context_sha256",
                "production_invocation_id",
                "production_identity_sha256",
            ],
            "allowed_outcomes": [
                "survived",
                "challenged",
                "inconclusive",
            ],
            "finding_not_rewritten": True,
        },
        "admission": {
            "six_exact_run_specs": True,
            "six_exact_runner_policy_pairs": True,
            "audit": admission_audit,
            "side_effects": False,
            "r3_receipt_scope": (
                "side_effect_free_feasibility_only_not_reusable_for_r4"
            ),
            "r4_fresh_re_admission_required": True,
            "path_rebinding": {
                "only_paths_may_be_re_resolved": True,
                "workdir": (
                    "resolve a fresh clean source worktree from the released "
                    "lane mapping; reverify origin, commit, and tree"
                ),
                "artifact_dir": (
                    f"resolve {R4_ARTIFACT_ROOT}/<lane-id>/artifacts "
                    "against the R4 clean repository worktree"
                ),
                "immutable_runner_fields": [
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
                ],
            },
            "receipts_are_auditor_evidence_not_verifier_inputs": True,
            "allowed_subprocesses": ["read-only git identity commands"],
            "forbidden_before_formal_execution": [
                "gradle",
                "android",
                "adb",
                "codex",
                "device",
                "install",
                "launch",
                "runtime",
            ],
        },
        "contradiction_packet": contradiction,
        "leakage_audit": {
            "neutral_packets": leakage,
            "run_specs": run_spec_leakage,
            "mapping_released": False,
        },
        "supported_gate": {
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
            "otherwise": "Not Supported",
        },
        "claim_boundary": {
            "local_only": True,
            "scope": (
                "one approved compose-samples Jetchat matched pair, one "
                "API-35 emulator profile, six frozen lanes, and one formal "
                "attempt"
            ),
            "preserved_runtime_result": (
                "#137 remains Not Supported and is never rerun or rewritten"
            ),
            "known_gaps": [
                (
                    "R3 performs no emulator, UI, agent, oracle, or review "
                    "execution; all six runtime results remain unknown"
                ),
                (
                    "the controlled rotation probe is an evidence-grounded "
                    "configuration-recreation analogue of the upstream "
                    "multi-window resize report, not a replay of its exact UI "
                    "gesture"
                ),
                (
                    "R4 must implement and statically verify the recovery-v2 "
                    "formal consumer before starting the single attempt, "
                    "without changing this packet"
                ),
            ],
            "exclusions": [
                "rewrite or rerun of #136/#137",
                "R1/R2 population reuse",
                (
                    "production, upstream, OEM, ColorOS, or physical-device "
                    "claims"
                ),
                "success rate, recall, completeness, or benchmark-scale claims",
                "automatic repair",
            ],
        },
        "tool_identity": tools,
        "package_buildability": {
            "status": "passed",
            "snapshot_a_duration_seconds": builds["snapshot-a"][
                "duration_seconds"
            ],
            "snapshot_b_duration_seconds": builds["snapshot-b"][
                "duration_seconds"
            ],
            "formal_holdout_executed": False,
        },
    }
    manifest["packet_commitment"] = {
        "algorithm": "sha256(canonical_json_bytes(freeze_payload))",
        "sha256": freeze_payload_sha256(manifest),
        "approval_envelope_excluded": True,
        "status_and_timestamps_excluded": True,
    }
    return manifest


def _write_manifest_identity(manifest: Any) -> None:
    _write_json(
        RUN_ROOT / "manifest-identity.json",
        {
            "schema_version": 2,
            "manifest_path": str(MANIFEST_PATH.relative_to(REPO_ROOT)),
            "manifest_sha256": manifest.source_sha256,
            "canonical_manifest_sha256": manifest.canonical_sha256,
            "packet_commitment_sha256": (
                manifest.packet_commitment_sha256
            ),
            "status": manifest.status,
            "formal_execution_started": False,
            "side_effects": False,
        },
    )


def _write_checksums(*, allow_frozen: bool = False) -> int:
    if not allow_frozen:
        ensure_evidence_ledger_regeneration_allowed(MANIFEST_PATH)
    entries: dict[str, Path] = {}
    for path in sorted(RUN_ROOT.rglob("*")):
        if (
            path.is_file()
            and path.name != "checksums.sha256"
            and "__pycache__" not in path.parts
        ):
            entries[path.relative_to(RUN_ROOT).as_posix()] = path
    for path in sorted(BENCH_ROOT.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            entries[os.path.relpath(path, RUN_ROOT)] = path
    for path in (
        MANIFEST_PATH,
        REPO_ROOT / "src/aiverify/bench/m9_recovery_qualification.py",
        REPO_ROOT / "tests/bench/test_m9_recovery_qualification.py",
    ):
        if path.is_file():
            entries[os.path.relpath(path, RUN_ROOT)] = path
    lines = [
        f"{sha256_file(path)}  {label}\n"
        for label, path in sorted(entries.items())
    ]
    (RUN_ROOT / "checksums.sha256").write_text(
        "".join(lines),
        encoding="utf-8",
    )
    return len(lines)


def _verify_checksums() -> int:
    ledger = RUN_ROOT / "checksums.sha256"
    failures: list[str] = []
    count = 0
    for line in ledger.read_text(encoding="utf-8").splitlines():
        digest, separator, label = line.partition("  ")
        count += 1
        path = (RUN_ROOT / label).resolve()
        if (
            separator != "  "
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or not path.is_relative_to(REPO_ROOT.resolve())
            or not path.is_file()
            or sha256_file(path) != digest
        ):
            failures.append(label or f"line-{count}")
    if failures:
        raise SystemExit(f"checksum verification failed: {failures}")
    return count


def _generate_candidate() -> None:
    ensure_candidate_regeneration_allowed(MANIFEST_PATH)
    started = dt.datetime.now(dt.timezone.utc)
    source_identities = {
        "snapshot-a": _ensure_source(
            SNAPSHOT_A,
            expected_commit=DEFECT_COMMIT,
            expected_tree=DEFECT_TREE,
        ),
        "snapshot-b": _ensure_source(
            SNAPSHOT_B,
            expected_commit=PROJECT_TARGET_COMMIT,
            expected_tree=PROJECT_TARGET_TREE,
        ),
    }
    freshness = _write_freshness_audit()
    builds = _copy_build_evidence(source_identities)
    provenance = _write_auditor_provenance(
        source_identities,
        builds,
        freshness,
    )
    source_inventory = _source_inventory()
    registry, plan = _write_registry_and_plan()
    contradiction = _write_contradiction()
    pre_release = _write_neutral_packets(
        [],
        source_inventory=source_inventory,
        registry=registry,
        plan=plan,
        name="pre-release",
    )
    mapping = _materialize_mapping()
    records = _write_run_specs(mapping)
    run_spec_leakage = _audit_run_specs(records)
    receipts = _admit_run_specs(records)
    admission_audit = validate_admission_receipts(
        receipts,
        expected_run_specs={
            str(record["lane_id"]): record for record in records
        },
    )
    if admission_audit["status"] != "pass":
        raise SystemExit(f"admission audit failed: {admission_audit}")
    _write_json(RUN_ROOT / "admission-audit.json", admission_audit)
    leakage = _write_neutral_packets(
        records,
        source_inventory=source_inventory,
        registry=registry,
        plan=plan,
        name="final",
    )
    tools = _tool_identity()
    document = _candidate_manifest(
        source_identities=source_identities,
        freshness=freshness,
        builds=builds,
        provenance=provenance,
        source_inventory=source_inventory,
        mapping=mapping,
        records=records,
        admission_audit=admission_audit,
        registry=registry,
        plan=plan,
        contradiction=contradiction,
        leakage=leakage,
        run_spec_leakage=run_spec_leakage,
        tools=tools,
    )
    _write_json(MANIFEST_PATH, document)
    manifest = load_manifest(MANIFEST_PATH)
    preflight = {
        "schema_version": 2,
        "qualification_id": QUALIFICATION_ID,
        "status": "technically_admitted_awaiting_human_approval",
        "manifest_sha256": manifest.source_sha256,
        "canonical_manifest_sha256": manifest.canonical_sha256,
        "packet_commitment_sha256": manifest.packet_commitment_sha256,
        "admitted": True,
        "approval_gate_passed": False,
        "side_effects": False,
        "formal_execution_started": False,
        "formal_holdout_executed": False,
        "checks": [
            {"name": "fresh_source_pair_identity", "status": "pass"},
            {"name": "focused_one_file_upstream_diff", "status": "pass"},
            {"name": "host_buildability_both_snapshots", "status": "pass"},
            {"name": "six_exact_run_specs", "status": "pass", "count": 6},
            {
                "name": "six_production_seam_admissions",
                "status": "pass",
            },
            {"name": "neutral_leakage_audit", "status": "pass"},
            {
                "name": "contradiction_pre_side_effect_rejection",
                "status": "pass",
            },
            {
                "name": "human_freeze_approval",
                "status": "pending",
            },
        ],
        "lane_admissions": [
            {
                "lane_id": record["lane_id"],
                "run_spec_sha256": record["run_spec_sha256"],
                "admission_receipt_sha256": record[
                    "admission_receipt_sha256"
                ],
                "git_only_call_count": record["git_only_call_count"],
            }
            for record in records
        ],
        "admission_audit": admission_audit,
        "pre_release_leakage_audit": pre_release,
        "final_leakage_audit": leakage,
        "run_spec_leakage_audit": run_spec_leakage,
        "contradiction_audit": contradiction["audit"],
        "mapping_released": False,
        "duration_seconds": round(
            (dt.datetime.now(dt.timezone.utc) - started).total_seconds(),
            6,
        ),
        "claim_boundary": document["claim_boundary"],
    }
    _write_json(RUN_ROOT / "preflight.json", preflight)
    _write_json(
        RUN_ROOT / "candidate-decision-packet.json",
        {
            "schema_version": 2,
            "status": "awaiting_human_approval",
            "issue": ISSUE_URL,
            "manifest": str(MANIFEST_PATH.relative_to(REPO_ROOT)),
            "manifest_sha256": manifest.source_sha256,
            "packet_commitment_sha256": (
                manifest.packet_commitment_sha256
            ),
            "project_target": {
                "source_origin": SOURCE_ORIGIN,
                "source_commit": PROJECT_TARGET_COMMIT,
                "source_tree": PROJECT_TARGET_TREE,
                "package": PACKAGE,
                "activity": ACTIVITY,
            },
            "matched_pair": {
                "defect_commit": DEFECT_COMMIT,
                "defect_tree": DEFECT_TREE,
                "control_commit": PROJECT_TARGET_COMMIT,
                "control_tree": PROJECT_TARGET_TREE,
                "upstream_pr": UPSTREAM_PR_URL,
            },
            "cohort": {
                "lanes": 6,
                "defect": 3,
                "control": 3,
                "mapping_commitment_sha256": document["cohort"][
                    "mapping_commitment"
                ]["sha256"],
                "mapping_raw_sha256": document["cohort"][
                    "mapping_commitment"
                ]["raw_artifact_sha256"],
                "clear_mapping_in_verifier_inputs": False,
            },
            "probe": document["oracle"],
            "policy": document["policy"],
            "supported_gate": document["supported_gate"],
            "claim_boundary": document["claim_boundary"],
            "formal_execution_started": False,
        },
    )
    _write_manifest_identity(manifest)
    count = _write_checksums()
    print(
        json.dumps(
            {
                "status": "awaiting_human_approval",
                "technical_admission": "passed",
                "lanes": 6,
                "admissions": admission_audit["status"],
                "leakage": leakage["audit"]["status"],
                "contradiction": contradiction["audit"]["status"],
                "formal_execution_started": False,
                "manifest_sha256": manifest.source_sha256,
                "packet_commitment_sha256": (
                    manifest.packet_commitment_sha256
                ),
                "checksum_entries": count,
            },
            sort_keys=True,
        )
    )


def _finalize_approval(
    *,
    comment_url: str,
    approved_by: str,
    approved_at: str,
) -> None:
    validate_human_approval(
        comment_url=comment_url,
        approved_by=approved_by,
        approved_at=approved_at,
    )
    candidate = load_manifest(MANIFEST_PATH)
    if candidate.status != "awaiting_human_approval":
        raise SystemExit(
            f"manifest is not awaiting approval: {candidate.status}"
        )
    before = candidate.packet_commitment_sha256
    document = dict(candidate.document)
    document["status"] = "frozen"
    document["frozen_at"] = approved_at
    document["approval"] = {
        **dict(document["approval"]),
        "status": "approved",
        "comment_url": comment_url,
        "approved_by": approved_by,
        "approved_at": approved_at,
    }
    _write_json(MANIFEST_PATH, document)
    frozen = load_manifest(MANIFEST_PATH, require_frozen=True)
    if frozen.packet_commitment_sha256 != before:
        raise SystemExit("approval finalization changed the approved freeze payload")
    preflight = _read_json(RUN_ROOT / "preflight.json")
    preflight["status"] = "frozen_after_explicit_human_approval"
    preflight["manifest_sha256"] = frozen.source_sha256
    preflight["canonical_manifest_sha256"] = frozen.canonical_sha256
    preflight["approval_gate_passed"] = True
    for check in preflight.get("checks", []):
        if check.get("name") == "human_freeze_approval":
            check["status"] = "pass"
            check["comment_url"] = comment_url
            check["approved_by"] = approved_by
            check["approved_at"] = approved_at
    _write_json(RUN_ROOT / "preflight.json", preflight)
    decision = _read_json(RUN_ROOT / "candidate-decision-packet.json")
    decision["status"] = "human_approved_frozen"
    decision["approval"] = {
        "comment_url": comment_url,
        "approved_by": approved_by,
        "approved_at": approved_at,
    }
    decision["manifest_sha256"] = frozen.source_sha256
    _write_json(RUN_ROOT / "candidate-decision-packet.json", decision)
    _write_manifest_identity(frozen)
    count = _write_checksums(allow_frozen=True)
    print(
        json.dumps(
            {
                "status": "frozen",
                "manifest_sha256": frozen.source_sha256,
                "packet_commitment_sha256": before,
                "checksum_entries": count,
                "formal_execution_started": False,
            },
            sort_keys=True,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-only", action="store_true")
    parser.add_argument("--verify-ledger", action="store_true")
    parser.add_argument("--finalize-approval-url")
    parser.add_argument("--approved-by", default="yangliang2")
    parser.add_argument("--approved-at")
    args = parser.parse_args(argv)
    selected_modes = sum(
        bool(value)
        for value in (
            args.ledger_only,
            args.verify_ledger,
            args.finalize_approval_url,
        )
    )
    if selected_modes > 1:
        parser.error(
            "--ledger-only, --verify-ledger, and approval finalization "
            "are mutually exclusive"
        )
    if args.approved_at and not args.finalize_approval_url:
        parser.error("--approved-at requires --finalize-approval-url")
    if args.verify_ledger:
        print(json.dumps({"checksum_entries_verified": _verify_checksums()}))
        return 0
    if args.ledger_only:
        print(json.dumps({"checksum_entries": _write_checksums()}))
        return 0
    if args.finalize_approval_url:
        approved_at = args.approved_at or dt.datetime.now(
            dt.timezone.utc
        ).isoformat(timespec="seconds")
        _finalize_approval(
            comment_url=args.finalize_approval_url,
            approved_by=args.approved_by,
            approved_at=approved_at,
        )
        return 0
    _generate_candidate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
