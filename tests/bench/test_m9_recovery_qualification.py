"""Contract tests for the fresh M9-R3 recovery freeze."""

from __future__ import annotations

import copy
import datetime as dt
import json
import os
import struct
import zlib
from pathlib import Path

import jsonschema
import pytest
import yaml

from aiverify.bench.m9_recovery_qualification import (
    ACTIVITY,
    APK_GLOB,
    BACKEND,
    CONTROL_APK_BYTES,
    CONTROL_APK_SHA256,
    DEFECT_APK_BYTES,
    DEFECT_APK_SHA256,
    DEFECT_COMMIT,
    DEVICE,
    FalsificationReviewExecutionError,
    FalsificationReviewInvocationPlan,
    FORMAL_ATTEMPT_ID,
    FORMAL_HYPOTHESIS_ID,
    LANE_IDS,
    LOCAL_CLAIM_BOUNDARY,
    M9RecoveryQualificationError,
    PACKAGE,
    PROBE_TOKENS,
    PROJECT_TARGET_COMMIT,
    PROJECT_TARGET_ID,
    R4_ARTIFACT_ROOT,
    R4_RUN_RECORD,
    RUNNER_POLICY,
    SOURCE_ORIGIN,
    _execution_review_summary,
    _expected_review_prompt,
    build_falsification_review_receipt,
    canonical_json_bytes,
    ensure_candidate_regeneration_allowed,
    ensure_evidence_ledger_regeneration_allowed,
    execute_falsification_review,
    freeze_payload_sha256,
    load_auditor_mapping,
    load_manifest,
    persist_falsification_review_receipt,
    prepare_falsification_review_invocation,
    reconcile_formal_rows,
    sealed_source_binding_ref,
    sha256_bytes,
    validate_admission_receipts,
)
from aiverify.runner.command import CommandResult, CommandRunner


ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "bench/m9/m9-recovery-project-qualification-v2.json"
MAPPING = ROOT / "bench/m9/recovery-v2/auditor/matched-pair.json"


def _formal_fixture(tmp_path: Path) -> dict[str, object]:
    def write_json(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def write_png(path: Path, marker: str) -> None:
        def chunk(kind: bytes, payload: bytes) -> bytes:
            return (
                struct.pack(">I", len(payload))
                + kind
                + payload
                + struct.pack(
                    ">I",
                    zlib.crc32(kind + payload) & 0xFFFFFFFF,
                )
            )

        width, height = (
            (1, 2) if marker.endswith("-before") else (2, 1)
        )
        color = marker.encode("utf-8")[0]
        scanlines = b"".join(
            b"\x00" + bytes((color, 64, 128, 255)) * width
            for _ in range(height)
        )
        payload = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(
                b"IHDR",
                struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0),
            )
            + chunk(b"IDAT", zlib.compress(scanlines))
            + chunk(b"IEND", b"")
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    def artifact_ref(path: Path) -> dict[str, str]:
        return {
            "path": path.relative_to(tmp_path).as_posix(),
            "sha256": sha256_bytes(path.read_bytes()),
        }

    def codex_identity(
        *,
        role: str,
        thread_id: str,
        turn_id: str,
        workdir: str,
        prompt_sha256: str = "d" * 64,
    ) -> dict[str, object]:
        observation = {
            "session_meta": {
                "id": thread_id,
                "cwd": workdir,
                "cli_version": "0.144.6",
                "source": "exec",
            },
            "turn_context": {
                "turn_id": turn_id,
                "model": "gpt-5.6-sol",
            },
        }
        observation_sha256 = sha256_bytes(
            json.dumps(
                observation,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        argv = ["codex", "exec", "--json"]
        if role == "journey_driver":
            argv.extend(
                [
                    "--output-schema",
                    "/schema.json",
                    "--cd",
                    workdir,
                    "--dangerously-bypass-approvals-and-sandbox",
                ]
            )
        elif role == "l3_semantic_judge":
            argv.extend(["--cd", workdir, "--sandbox", "read-only"])
        else:
            lane_root = Path(workdir).parent
            argv.extend(
                [
                    "--output-schema",
                    str(
                        lane_root
                        / "falsification-review-output-schema.json"
                    ),
                    "--output-last-message",
                    str(lane_root / "falsification-review-output.json"),
                    "--skip-git-repo-check",
                    "--sandbox",
                    "read-only",
                    "--cd",
                    workdir,
                ]
            )
        return {
            "schema_version": 1,
            "role": role,
            "backend": BACKEND,
            "binary": {
                "requested": "codex",
                "resolved_path": "/usr/local/bin/codex",
                "sha256": "c" * 64,
                "version": "codex-cli 0.144.6",
            },
            "requested_model": None,
            "effective_model": "gpt-5.6-sol",
            "effective_model_source": {
                "kind": "codex_session_turn_context",
                "observation_sha256": observation_sha256,
                "thread_id": thread_id,
                "turn_id": turn_id,
            },
            "source_observation": observation,
            "command": {
                "argv_without_prompt": argv,
                "prompt_sha256": prompt_sha256,
            },
        }

    def bind_identity(value: dict[str, object]) -> dict[str, object]:
        value["identity_sha256"] = sha256_bytes(
            json.dumps(
                {
                    key: item
                    for key, item in value.items()
                    if key != "identity_sha256"
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        return value

    manifest = load_manifest(MANIFEST)
    commitment = manifest.document["cohort"]["mapping_commitment"]
    released = load_auditor_mapping(
        MAPPING,
        expected_raw_sha256=commitment["raw_artifact_sha256"],
        expected_canonical_sha256=commitment["sha256"],
    )
    mapping = released.document
    roles = {
        item["lane_id"]: item["role"] for item in mapping["assignments"]
    }
    for lane_id in LANE_IDS:
        source = (
            ROOT
            / "bench/m9/recovery-v2/run-specs"
            / f"{lane_id}.yaml"
        )
        destination = (
            tmp_path
            / "bench/m9/recovery-v2/run-specs"
            / f"{lane_id}.yaml"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())

    formal_fact_ids = (
        "fact-formal-context-input",
        "fact-formal-context-recreation",
        "fact-formal-context-source",
    )
    rows = []
    for index, lane_id in enumerate(LANE_IDS, start=1):
        token = PROBE_TOKENS[index - 1]
        production_thread_id = f"production-thread-{index}"
        production_turn_id = f"production-turn-{index}"
        production_invocation_id = (
            f"{production_thread_id}:{production_turn_id}"
        )
        review_thread_id = f"review-thread-{index}"
        review_turn_id = f"review-turn-{index}"
        finding_conclusion = (
            "locally_supported"
            if roles[lane_id] == "defect"
            else "locally_rejected"
        )
        after_token_visible = finding_conclusion == "locally_rejected"

        def text_input_observation(token_visible: bool) -> dict[str, object]:
            count = 1 if token_visible else 0
            return {
                "field_semantics": "content-desc:Text input",
                "input_field_anchor_count": 1,
                "exact_token_node_count": count,
                "editable_exact_token_node_count": count,
                "bound_exact_token_node_count": count,
                "input_field_present": True,
                "exact_token_visible_in_input": token_visible,
            }

        def text_input_nodes(token_visible: bool) -> list[dict[str, object]]:
            nodes: list[dict[str, object]] = [
                {
                    "content-desc": "Text input",
                    "center": "[540,1000]",
                }
            ]
            if token_visible:
                nodes.append(
                    {
                        "text": token,
                        "interactions": [
                            "clickable",
                            "focusable",
                            "long-clickable",
                        ],
                        "center": "[420,1000]",
                    }
                )
            return nodes
        reference_files = {
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
        }
        lane_root = tmp_path / R4_ARTIFACT_ROOT / lane_id
        source_workdir = str(tmp_path / "sources" / lane_id)
        review_workdir = str(lane_root / "review-input")
        started_at = "2026-08-07T12:00:00+00:00"
        finished_at = "2026-08-07T12:00:01+00:00"
        execution_record_attempt_id = f"runner-attempt-{index}"
        expected_commit = (
            DEFECT_COMMIT
            if roles[lane_id] == "defect"
            else PROJECT_TARGET_COMMIT
        )
        runner_setup = {
            "schema_version": 1,
            "status": "passed",
            "device": DEVICE,
            "launch_requested": True,
            "operations": [
                {
                    "operation": "logcat_clear",
                    "command": ["adb", "-s", DEVICE, "logcat", "-c"],
                    "returncode": 0,
                    "stdout": "",
                    "stderr": "",
                },
                {
                    "operation": "explicit_launch",
                    "command": [
                        "adb",
                        "-s",
                        DEVICE,
                        "shell",
                        "am",
                        "start",
                        "-n",
                        f"{PACKAGE}/{ACTIVITY}",
                    ],
                    "returncode": 0,
                    "stdout": "Starting\n",
                    "stderr": "",
                },
            ],
            "duration_seconds": 0.1,
        }
        write_json(lane_root / "runner-setup.json", runner_setup)

        run_spec_path = (
            tmp_path
            / "bench/m9/recovery-v2/run-specs"
            / f"{lane_id}.yaml"
        )
        artifact_dir = str(lane_root / "artifacts")
        admission = {
            "schema_version": 1,
            "status": "admitted",
            "admitted": True,
            "reasons": [],
            "artifact_namespace": {
                "artifact_dir": artifact_dir,
                "run_dir": str(lane_root),
                "formal_outputs_absent": True,
            },
            "checks": {
                "artifact_namespace": {"status": "passed"},
                "host_identity": {"status": "passed"},
                "run_spec_bytes": {
                    "status": "passed",
                    "sha256": sha256_bytes(run_spec_path.read_bytes()),
                    "bytes": run_spec_path.stat().st_size,
                },
                "runner_policy": {"status": "passed"},
                "target_declaration": {"status": "passed"},
            },
            "host": {
                "commit": expected_commit,
                "origin": SOURCE_ORIGIN,
                "host_project": source_workdir,
                "repository_root": source_workdir,
                "host_project_within_repository": False,
                "worktree": {
                    "clean": True,
                    "status_sha256": sha256_bytes(b""),
                },
            },
            "run_spec": {
                "path": str(run_spec_path),
                "scenario": lane_id,
                "sha256": sha256_bytes(run_spec_path.read_bytes()),
                "serialized_bytes": run_spec_path.stat().st_size,
            },
            "runner_policy": {
                "backend": BACKEND,
                "version": RUNNER_POLICY,
                "options": {
                    "artifact_dir": artifact_dir,
                    "adb_bin": "adb",
                    "allow_host_project_subdir": False,
                    "android_bin": "android",
                    "backend": BACKEND,
                    "codex_bin": "codex",
                    "device": DEVICE,
                    "expected_source_commit": expected_commit,
                    "launch": True,
                    "requested_driver_model": None,
                    "requested_l3_model": None,
                    "runner_policy_version": RUNNER_POLICY,
                    "workdir": source_workdir,
                },
                "tools": {
                    "adb": {
                        "requested": "adb",
                        "resolved_path": "/usr/local/bin/adb",
                        "sha256": "a" * 64,
                    },
                    "android": {
                        "requested": "android",
                        "resolved_path": "/usr/local/bin/android",
                        "sha256": "b" * 64,
                    },
                    "codex": {
                        "requested": "codex",
                        "resolved_path": "/usr/local/bin/codex",
                        "sha256": "c" * 64,
                    },
                    "model_selection": {
                        name: {
                            "requested_model": None,
                            "model_override_present": False,
                            "policy": "codex_cli_default",
                        }
                        for name in (
                            "journey_driver",
                            "l3_semantic_judge",
                        )
                    },
                },
            },
            "side_effects": {
                "agent": False,
                "build": False,
                "device": False,
                "external": False,
                "declaration": (
                    "read-only git and local source/metadata inspection only"
                ),
            },
            "target": {
                "package": PACKAGE,
                "activity": ACTIVITY,
                "apk_locator": {
                    "glob": APK_GLOB,
                    "relative_to": source_workdir,
                },
            },
        }
        write_json(lane_root / "production-seam-admission.json", admission)

        before_source_root = lane_root / "artifacts/after-segment-0"
        after_source_root = lane_root / "artifacts/after-event-0"
        before_source_screen = before_source_root / "screen.png"
        after_source_screen = after_source_root / "screen.png"
        before_source_layout = before_source_root / "layout.json"
        after_source_layout = after_source_root / "layout.json"
        after_source_logcat = after_source_root / "logcat.txt"
        event_source = lane_root / "artifacts/system-event-0/event.json"
        before_nodes = text_input_nodes(True)
        after_nodes = text_input_nodes(after_token_visible)
        write_png(before_source_screen, f"{lane_id}-before")
        write_png(after_source_screen, f"{lane_id}-after")
        write_json(before_source_layout, before_nodes)
        write_json(after_source_layout, after_nodes)
        after_checkpoint_logcat = (
            f"I/ActivityTaskManager: {lane_id} configuration completed\n"
        )
        after_source_logcat.write_text(
            after_checkpoint_logcat,
            encoding="utf-8",
        )
        write_json(
            event_source,
            {
                "status": "passed",
                "event": "rotate",
                "evidence": {
                    "accelerometer_rotation": "0",
                    "user_rotation": "1",
                },
            },
        )
        before_raw_screen = lane_root / "raw/screenshots/before.png"
        after_raw_screen = lane_root / "raw/screenshots/after.png"
        before_raw_screen.parent.mkdir(parents=True, exist_ok=True)
        before_raw_screen.write_bytes(before_source_screen.read_bytes())
        after_raw_screen.write_bytes(after_source_screen.read_bytes())
        write_json(
            lane_root / "raw/layout/before.json",
            {
                "schema_version": 1,
                "lane_id": lane_id,
                "checkpoint": "before",
                "orientation": "portrait",
                "probe_token": token,
                "token_visible": True,
                "text_input_observation": text_input_observation(True),
                "nodes": before_nodes,
                "source_screenshot_path": "artifacts/after-segment-0/screen.png",
                "source_screenshot_sha256": sha256_bytes(
                    before_source_screen.read_bytes()
                ),
                "source_layout_path": "artifacts/after-segment-0/layout.json",
                "source_layout_sha256": sha256_bytes(
                    before_source_layout.read_bytes()
                ),
            },
        )
        write_json(
            lane_root / "raw/layout/after.json",
            {
                "schema_version": 1,
                "lane_id": lane_id,
                "checkpoint": "after",
                "orientation": "landscape",
                "probe_token": token,
                "token_visible": after_token_visible,
                "text_input_observation": text_input_observation(
                    after_token_visible
                ),
                "nodes": after_nodes,
                "source_screenshot_path": "artifacts/after-event-0/screen.png",
                "source_screenshot_sha256": sha256_bytes(
                    after_source_screen.read_bytes()
                ),
                "source_layout_path": "artifacts/after-event-0/layout.json",
                "source_layout_sha256": sha256_bytes(
                    after_source_layout.read_bytes()
                ),
            },
        )
        (lane_root / "raw/logcat").mkdir(parents=True, exist_ok=True)
        lifecycle_logcat = (
            f"I/am_on_create_called: [0,{ACTIVITY},performCreate]\n"
            f"I/am_on_destroy_called: [0,{ACTIVITY},performDestroy]\n"
            f"I/am_on_create_called: [0,{ACTIVITY},performCreate]\n"
        )
        write_json(
            lane_root / "raw/logcat/events-command.json",
            {
                "command": [
                    "adb",
                    "-s",
                    DEVICE,
                    "logcat",
                    "-b",
                    "events",
                    "-d",
                    "-v",
                    "threadtime",
                ],
                "cwd": None,
                "returncode": 0,
                "duration_seconds": 0.1,
                "stdout": lifecycle_logcat,
                "stderr": "",
            },
        )
        (lane_root / "raw/logcat/rotation.txt").write_text(
            "# activity lifecycle event buffer\n"
            + lifecycle_logcat.strip()
            + "\n# after-rotation checkpoint buffers\n"
            + after_checkpoint_logcat,
            encoding="utf-8",
        )
        write_json(
            lane_root / "rotation-event.json",
            {
                "schema_version": 1,
                "lane_id": lane_id,
                "status": "passed",
                "event": "rotate",
                "rotation_count": 1,
                "before": "user_rotation=0",
                "after": "user_rotation=1",
                "accelerometer_rotation": "0",
                "activity_recreation_observed": True,
                "retyped_after_boundary": False,
                "repaired_after_boundary": False,
                "source_event_path": "artifacts/system-event-0/event.json",
                "source_event_sha256": sha256_bytes(
                    event_source.read_bytes()
                ),
            },
        )

        production_identity_path = (
            lane_root
            / "production-identities"
            / "journey-driver-01.json"
        )
        journey_identity = codex_identity(
            role="journey_driver",
            thread_id=production_thread_id,
            turn_id=production_turn_id,
            workdir=source_workdir,
        )
        write_json(
            production_identity_path,
            journey_identity,
        )
        production_receipt_ref = artifact_ref(production_identity_path)
        effective_invocations = [
            {
                "role": "journey_driver",
                "invocation_id": production_invocation_id,
                "identity_sha256": production_receipt_ref["sha256"],
                "effective_model": "gpt-5.6-sol",
                "identity_receipt": production_receipt_ref,
            }
        ]
        provenance_journey_ref = {
            "path": production_identity_path.relative_to(lane_root).as_posix(),
            "sha256": production_receipt_ref["sha256"],
        }
        provenance_l3_refs: list[dict[str, str]] = []
        provenance_l3_ledgers: list[dict[str, str]] = []
        if roles[lane_id] == "control":
            l3_thread_id = f"production-l3-thread-{index}"
            l3_turn_id = f"production-l3-turn-{index}"
            l3_invocation_id = f"{l3_thread_id}:{l3_turn_id}"
            l3_identity_path = (
                lane_root
                / "production-identities"
                / "l3-semantic-judge-01.json"
            )
            l3_identity = codex_identity(
                role="l3_semantic_judge",
                thread_id=l3_thread_id,
                turn_id=l3_turn_id,
                workdir=source_workdir,
            )
            write_json(l3_identity_path, l3_identity)
            l3_receipt_ref = artifact_ref(l3_identity_path)
            effective_invocations.append(
                {
                    "role": "l3_semantic_judge",
                    "invocation_id": l3_invocation_id,
                    "identity_sha256": l3_receipt_ref["sha256"],
                    "effective_model": "gpt-5.6-sol",
                    "identity_receipt": l3_receipt_ref,
                }
            )
            provenance_l3_refs.append(
                {
                    "path": l3_identity_path.relative_to(
                        lane_root
                    ).as_posix(),
                    "sha256": l3_receipt_ref["sha256"],
                }
            )
            l3_ledger_path = (
                lane_root
                / "production-identities"
                / "l3-semantic-judge-01.invocation.json"
            )
            write_json(
                l3_ledger_path,
                {
                    "schema_version": 1,
                    "role": "l3_semantic_judge",
                    "call_index": 1,
                    "requested_model": None,
                    "argv_without_prompt": l3_identity["command"][
                        "argv_without_prompt"
                    ],
                    "prompt_sha256": l3_identity["command"][
                        "prompt_sha256"
                    ],
                },
            )
            provenance_l3_ledgers.append(
                {
                    "path": l3_ledger_path.relative_to(
                        lane_root
                    ).as_posix(),
                    "sha256": sha256_bytes(l3_ledger_path.read_bytes()),
                }
            )
        effective_identity = {
            "schema_version": 2,
            "status": "complete",
            "backend": BACKEND,
            "selection_policy": "codex_cli_default",
            "requested_model": None,
            "model_override_present": False,
            "execution_record_attempt_id": execution_record_attempt_id,
            "production_invocation_id": production_invocation_id,
            "invocations": effective_invocations,
        }
        write_json(
            lane_root / "effective-execution-identity.json",
            effective_identity,
        )
        production_identity_sha256 = sha256_bytes(
            (lane_root / "effective-execution-identity.json").read_bytes()
        )

        resolved_run_spec = yaml.safe_load(
            run_spec_path.read_text(encoding="utf-8")
        )
        resolved_run_spec["host_project"]["commit"] = expected_commit
        resolved_run_spec_path = (
            lane_root / "identity" / "resolved-run-spec.yaml"
        )
        resolved_run_spec_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_run_spec_path.write_text(
            yaml.safe_dump(
                resolved_run_spec,
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        resolved_run_spec_sha256 = sha256_bytes(
            resolved_run_spec_path.read_bytes()
        )
        run_spec_identity = bind_identity(
            {
                "invocation_path": str(resolved_run_spec_path),
                "consumed_sha256": resolved_run_spec_sha256,
                "snapshot_path": resolved_run_spec_path.relative_to(
                    lane_root
                ).as_posix(),
                "snapshot_sha256": resolved_run_spec_sha256,
                "scenario": lane_id,
                "host_project": source_workdir,
                "apk_glob": APK_GLOB,
                "package": PACKAGE,
                "activity": ACTIVITY,
                "host_locator": {
                    "root": resolved_run_spec["host_project"]["root"],
                    "resolution": "override",
                    "resolved_path": source_workdir,
                    "expected_origin": SOURCE_ORIGIN,
                    "expected_commit": expected_commit,
                },
                "frozen_source_sha256": sha256_bytes(
                    run_spec_path.read_bytes()
                ),
                "source_binding_ref": sealed_source_binding_ref(lane_id),
            }
        )
        host_patch_path = lane_root / "identity" / "host.patch"
        host_patch_path.write_bytes(b"")
        host_identity = bind_identity(
            {
                "repository_root": source_workdir,
                "origin": SOURCE_ORIGIN,
                "commit": expected_commit,
                "worktree": {
                    "clean": True,
                    "status": "",
                    "status_sha256": sha256_bytes(b""),
                    "patch_path": host_patch_path.relative_to(
                        lane_root
                    ).as_posix(),
                    "patch_sha256": sha256_bytes(b""),
                    "untracked_files": [],
                },
            }
        )
        apk_bytes, apk_sha256 = (
            (DEFECT_APK_BYTES, DEFECT_APK_SHA256)
            if roles[lane_id] == "defect"
            else (CONTROL_APK_BYTES, CONTROL_APK_SHA256)
        )
        apk_path = str(Path(source_workdir) / APK_GLOB)
        apk_identity = bind_identity(
            {
                "artifacts": [
                    {
                        "path": apk_path,
                        "bytes": apk_bytes,
                        "sha256": apk_sha256,
                    }
                ]
            }
        )
        device_identity = bind_identity(
            {
                "serial": DEVICE,
                "api_level": "35",
                "build_fingerprint": "google/test/fingerprint",
                "profile": {
                    "kind": "emulator",
                    "name": "aiverify_api35",
                    "model": "sdk_gphone64_arm64",
                    "device": "emu64a",
                },
            }
        )
        tool_identities = {
            "android_cli": bind_identity(
                {
                    "requested": "android",
                    "resolved_path": "/usr/local/bin/android",
                    "sha256": "b" * 64,
                    "version": "android-cli 1.0",
                }
            ),
            "adb": bind_identity(
                {
                    "requested": "adb",
                    "resolved_path": "/usr/local/bin/adb",
                    "sha256": "a" * 64,
                    "version": "Android Debug Bridge 1.0.41",
                }
            ),
            "codex_cli": bind_identity(
                {
                    "requested": "codex",
                    "resolved_path": "/usr/local/bin/codex",
                    "sha256": "c" * 64,
                    "version": "codex-cli 0.144.6",
                }
            ),
            "git": bind_identity(
                {
                    "requested": "git",
                    "resolved_path": "/usr/bin/git",
                    "sha256": "e" * 64,
                    "version": "git version 2.50.1",
                }
            ),
            "python": bind_identity(
                {
                    "requested": "python",
                    "resolved_path": "/usr/bin/python3",
                    "sha256": "f" * 64,
                    "version": "Python 3.11.15",
                }
            ),
        }
        deployment_process = bind_identity(
            {
                "args": [
                    "android",
                    "run",
                    f"--device={DEVICE}",
                    f"--apks={apk_path}",
                    f"--activity={ACTIVITY}",
                    "--type=ACTIVITY",
                ],
                "returncode": 0,
                "stdout": "installed\n",
                "stderr": "",
            }
        )
        deployment_identity = bind_identity(
            {
                "process": deployment_process,
                "installed_artifacts": [
                    {
                        "path": f"/data/app/{PACKAGE}/base.apk",
                        "sha256": apk_sha256,
                    }
                ],
                "target": {
                    "device": DEVICE,
                    "package": PACKAGE,
                    "component": f"{PACKAGE}/{ACTIVITY}",
                },
                "resolved_component": f"{PACKAGE}/{ACTIVITY}",
                "device": device_identity,
                "tools": {
                    "android_cli_sha256": tool_identities[
                        "android_cli"
                    ]["sha256"],
                    "adb_sha256": tool_identities["adb"]["sha256"],
                },
            }
        )
        provenance_roles = {
            "journey_driver": {
                "status": "invoked",
                "requested_model": None,
                "invocations": [provenance_journey_ref],
                "invocation_ledger": [],
            },
            "l3_semantic_judge": (
                {
                    "status": "invoked",
                    "requested_model": None,
                    "invocations": provenance_l3_refs,
                    "invocation_ledger": provenance_l3_ledgers,
                }
                if roles[lane_id] == "control"
                else {
                    "status": "not_applicable",
                    "reason": "gated_by_lower_oracle",
                    "requested_model": None,
                    "invocations": [],
                    "invocation_ledger": [],
                }
            ),
        }
        execution_provenance = {
            "schema_version": 1,
            "attempt_id": execution_record_attempt_id,
            "scenario": lane_id,
            "captured_at": "2026-08-07T12:00:00+00:00",
            "run_spec": run_spec_identity,
            "host": host_identity,
            "apk": apk_identity,
            "device": device_identity,
            "tools": tool_identities,
            "deployment": deployment_identity,
            "roles": provenance_roles,
        }
        provenance_path = lane_root / "execution-provenance.json"
        write_json(provenance_path, execution_provenance)
        execution_record = {
            "schema_version": 2,
            "attempt_id": execution_record_attempt_id,
            "scenario": lane_id,
            "lifecycle_state": "completed",
            "started_at": started_at,
            "finished_at": finished_at,
            "execution": {
                "status": "completed",
                "accounting_eligible": True,
                "reason": None,
                "message": None,
            },
            "process_outcome": {"exit_code": 0},
            "timing": {
                "started_at": started_at,
                "finished_at": finished_at,
                "total_seconds": 1.0,
                "phases": [],
            },
            "phase_errors": [],
            "evidence_refs": {
                "runner_setup": "runner-setup.json",
                "execution_provenance": {
                    "path": "execution-provenance.json",
                    "sha256": sha256_bytes(provenance_path.read_bytes()),
                },
            },
        }
        write_json(lane_root / "execution-record.json", execution_record)

        raw_ref_keys = (
            "screenshot_before",
            "screenshot_after",
            "layout_before",
            "layout_after",
            "filtered_logcat",
            "rotation_event",
        )
        raw_refs = {
            key: artifact_ref(lane_root / reference_files[key])
            for key in raw_ref_keys
        }
        oracle = {
            "schema_version": 2,
            "oracle_id": "m9-unsent-draft-config-recreation-v1",
            "status": "complete",
            "lane_id": lane_id,
            "accountable": True,
            "conclusion": finding_conclusion,
            "hypothesis_id": FORMAL_HYPOTHESIS_ID,
            "explored_fact_ids": list(formal_fact_ids),
            "probe_token": token,
            "sent": False,
            "retyped_after_boundary": False,
            "repaired_after_boundary": False,
            "evidence_refs": raw_refs,
        }
        write_json(lane_root / "oracle-receipt.json", oracle)

        finding = {
            "schema_version": 1,
            "finding_id": f"finding-{lane_id}",
            "target_id": PROJECT_TARGET_ID,
            "hypothesis_id": FORMAL_HYPOTHESIS_ID,
            "conclusion": (
                "supported"
                if finding_conclusion == "locally_supported"
                else "rejected"
            ),
            "evidence_refs": [
                "execution-record.json",
                "effective-execution-identity.json",
                "oracle-receipt.json",
                "raw/screenshots/before.png",
                "raw/screenshots/after.png",
                "raw/layout/before.json",
                "raw/layout/after.json",
                "raw/logcat/rotation.txt",
                "rotation-event.json",
            ],
            "impact": "an unsent draft may be lost across activity recreation",
            "claim_boundary": LOCAL_CLAIM_BOUNDARY,
            "rationale": "Derived from the terminal bound lane evidence.",
        }
        residual = {
            "schema_version": 1,
            "risk_id": f"residual-{lane_id}",
            "target_id": PROJECT_TARGET_ID,
            "hypothesis_id": FORMAL_HYPOTHESIS_ID,
            "reason": "The local probe does not establish broader behavior.",
            "evidence_gap": "Other devices and lifecycle boundaries are unexplored.",
            "scope": LOCAL_CLAIM_BOUNDARY,
            "basis_refs": [
                "execution-record.json",
                "oracle-receipt.json",
            ],
            "next_probe": "Any next probe requires a new approved contract.",
            "status": "accepted",
        }
        risk_map = {
            "schema_version": 1,
            "map_id": f"risk-map-{lane_id}",
            "target_id": PROJECT_TARGET_ID,
            "findings": [finding],
            "residual_risks": [residual],
            "explored_fact_ids": list(formal_fact_ids),
            "coverage_frontier": [
                "production, OEM, and physical-device behavior remains unexplored"
            ],
        }
        claim_boundary = {
            "schema_version": 2,
            "lane_id": lane_id,
            "scope": LOCAL_CLAIM_BOUNDARY,
            "local_only": True,
            "preserved_runtime_result": (
                "#137 remains Not Supported and is never rerun or rewritten"
            ),
            "excluded_claims": [
                "production",
                "upstream",
                "OEM",
                "ColorOS",
                "physical-device",
            ],
        }
        write_json(lane_root / "finding.json", finding)
        write_json(lane_root / "residual-risk.json", residual)
        write_json(lane_root / "project-risk-map.json", risk_map)
        write_json(lane_root / "claim-boundary.json", claim_boundary)

        review_input_sources = {
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
        review_root = Path(review_workdir)
        for review_name, source_name in review_input_sources.items():
            review_path = review_root / review_name
            review_path.parent.mkdir(parents=True, exist_ok=True)
            if source_name is None:
                write_json(
                    review_path,
                    _execution_review_summary(execution_record),
                )
            else:
                review_path.write_bytes(
                    (lane_root / source_name).read_bytes()
                )
        review_context = {
            "schema_version": 2,
            "lane_id": lane_id,
            "clean_context": True,
            "source_role_disclosed": False,
            "expected_result_disclosed": False,
            "production_oracle_path_used": False,
            "workdir": review_workdir,
            "input_artifacts": [
                artifact_ref(review_root / name)
                for name in review_input_sources
            ],
        }
        review_context_path = lane_root / "falsification-review-context.json"
        write_json(review_context_path, review_context)
        review_plan = prepare_falsification_review_invocation(
            lane_id=lane_id,
            repository_root=tmp_path,
        )
        assert isinstance(
            review_plan,
            FalsificationReviewInvocationPlan,
        )
        assert review_plan.workdir == review_root
        assert review_plan.prompt == _expected_review_prompt(
            tuple(review_input_sources)
        )
        review_prompt_path = review_plan.prompt_path
        review_identity_path = lane_root / "falsification-review-identity.json"
        write_json(
            review_identity_path,
            codex_identity(
                role="verification-agent-falsification-reviewer-v1",
                thread_id=review_thread_id,
                turn_id=review_turn_id,
                workdir=review_workdir,
                prompt_sha256=review_plan.prompt_sha256,
            ),
        )
        review_identity_payload = json.loads(
            review_identity_path.read_text(encoding="utf-8")
        )
        assert tuple(
            review_identity_payload["command"]["argv_without_prompt"]
        ) == review_plan.argv_without_prompt
        review_evidence_refs = list(review_input_sources)
        review_output_path = (
            lane_root / "falsification-review-output.json"
        )
        review_output = {
            "schema_version": 1,
            "status": "complete",
            "outcome": "survived",
            "dimensions": [
                {
                    "id": dimension,
                    "status": "supported",
                    "analysis": (
                        f"{dimension} is supported by the allowlisted "
                        "lane evidence."
                    ),
                    "evidence_refs": review_evidence_refs,
                }
                for dimension in (
                    "alternative_explanations",
                    "assumption_violations",
                    "evidence_integrity",
                    "causal_attribution",
                    "observation_consistency",
                    "claim_boundary",
                )
            ],
            "reasons": [],
            "claim_boundary": LOCAL_CLAIM_BOUNDARY,
            "source_role_disclosed": False,
            "expected_result_disclosed": False,
        }
        write_json(review_output_path, review_output)
        review_events_path = (
            lane_root / "falsification-review-events.jsonl"
        )
        review_events = (
            {
                "type": "thread.started",
                "thread_id": review_thread_id,
            },
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "text": review_output_path.read_text(
                        encoding="utf-8"
                    ).strip(),
                },
            },
            {
                "type": "turn.completed",
                "status": "completed",
            },
        )
        review_events_path.write_text(
            "".join(
                json.dumps(event, sort_keys=True) + "\n"
                for event in review_events
            ),
            encoding="utf-8",
        )
        review_payload = persist_falsification_review_receipt(
            lane_id=lane_id,
            repository_root=tmp_path,
            production_invocation_id=production_invocation_id,
            production_identity_sha256=production_identity_sha256,
        )
        assert review_payload == build_falsification_review_receipt(
            lane_id=lane_id,
            repository_root=tmp_path,
            production_invocation_id=production_invocation_id,
            production_identity_sha256=production_identity_sha256,
        )

        refs = {
            key: artifact_ref(lane_root / filename)
            for key, filename in reference_files.items()
            if key != "lane_ledger"
        }
        ledger_path = lane_root / reference_files["lane_ledger"]
        ledger_entries = sorted(
            path
            for path in lane_root.rglob("*")
            if path.is_file() and path != ledger_path
        )
        ledger_path.write_text(
            "".join(
                f"{sha256_bytes(path.read_bytes())}  "
                f"{path.relative_to(lane_root).as_posix()}\n"
                for path in ledger_entries
            ),
            encoding="utf-8",
        )
        refs["lane_ledger"] = artifact_ref(ledger_path)
        attempt_evidence = {
            "schema_version": 2,
            "validation_version": "m9-recovery-attempt-evidence-v2",
            "status": "validated",
            "lane_id": lane_id,
            "formal_attempt_id": FORMAL_ATTEMPT_ID,
            "terminal_lifecycle": "terminal",
            "execution_record_attempt_id": execution_record_attempt_id,
            "accountable": True,
            "finding_conclusion": finding_conclusion,
            "production_invocation_id": production_invocation_id,
            "production_identity_sha256": production_identity_sha256,
            "refs": refs,
            "evidence_refs_sha256": sha256_bytes(
                canonical_json_bytes(refs)
            ),
            "validator_checks": {
                "execution_record_terminal": True,
                "execution_record_attempt_bound": True,
                "execution_provenance_semantically_valid": True,
                "effective_identity_bound": True,
                "authoritative_production_identities_bound": True,
                "fresh_production_admission_bound": True,
                "runner_setup_bound": True,
                "raw_oracle_evidence_bound": True,
                "oracle_bound": True,
                "finding_evidence_refs_bound": True,
                "residual_risk_bound": True,
                "project_risk_map_bound": True,
                "claim_boundary_local": True,
                "falsification_review_bound": True,
                "falsification_review_output_bound": True,
                "authoritative_review_identity_bound": True,
                "clean_review_context_bound": True,
                "review_inputs_role_blind": True,
                "lane_ledger_exhaustive": True,
            },
        }
        validation_path = lane_root / "attempt-evidence-validation.json"
        write_json(validation_path, attempt_evidence)
        rows.append(
            {
                "lane_id": lane_id,
                "role": roles[lane_id],
                "accountable": True,
                "terminal": True,
                "formal_attempt_id": FORMAL_ATTEMPT_ID,
                "execution_record_attempt_id": execution_record_attempt_id,
                "lane_attempt_count": 1,
                "retry_count": 0,
                "replacement_count": 0,
                "discretionary_rerun_count": 0,
                "production_invocation_id": production_invocation_id,
                "production_identity_sha256": production_identity_sha256,
                "finding_conclusion": finding_conclusion,
                "attempt_evidence": attempt_evidence,
                "attempt_evidence_receipt": {
                    "path": (
                        f"{R4_ARTIFACT_ROOT}/{lane_id}/"
                        "attempt-evidence-validation.json"
                    ),
                    "sha256": sha256_bytes(validation_path.read_bytes()),
                },
                "falsification_review": {
                    "path": refs["falsification_review"]["path"],
                    "sha256": refs["falsification_review"]["sha256"],
                    **review_payload,
                },
            }
        )
    contradiction = manifest.document["contradiction_packet"]["audit"]
    execution_records = [
        {
            "lane_id": row["lane_id"],
            "execution_record_attempt_id": row[
                "execution_record_attempt_id"
            ],
            "path": row["attempt_evidence"]["refs"]["execution_record"][
                "path"
            ],
            "sha256": row["attempt_evidence"]["refs"]["execution_record"][
                "sha256"
            ],
        }
        for row in rows
    ]
    attempt_inventory = [
        {
            "formal_attempt_id": FORMAL_ATTEMPT_ID,
            "attempt_number": 1,
            "lane_order": list(LANE_IDS),
            "lane_count": 6,
            "terminal_lane_count": 6,
            "retry_count": 0,
            "replacement_count": 0,
            "discretionary_rerun_count": 0,
            "execution_records": execution_records,
        }
    ]
    inventory_path = tmp_path / R4_RUN_RECORD / "formal-attempt-inventory.json"
    write_json(
        inventory_path,
        {
            "schema_version": 2,
            "formal_attempts": attempt_inventory,
        },
    )
    _write_root_ledger(tmp_path)
    return {
        "manifest": manifest,
        "mapping": mapping,
        "mapping_commitment": released.canonical_sha256,
        "rows": rows,
        "contradiction": contradiction,
        "contradiction_commitment": sha256_bytes(
            canonical_json_bytes(contradiction)
        ),
        "attempt_inventory": attempt_inventory,
        "attempt_inventory_receipt": {
            "path": f"{R4_RUN_RECORD}/formal-attempt-inventory.json",
            "sha256": sha256_bytes(inventory_path.read_bytes()),
        },
        "evidence_repository_root": tmp_path,
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_root_ledger(repository_root: Path) -> None:
    attempt_root = repository_root / R4_RUN_RECORD
    ledger_path = attempt_root / "checksums.sha256"
    entries = sorted(
        path
        for path in attempt_root.rglob("*")
        if path.is_file() and path != ledger_path
    )
    ledger_path.write_text(
        "".join(
            f"{sha256_bytes(path.read_bytes())}  "
            f"{path.relative_to(attempt_root).as_posix()}\n"
            for path in entries
        ),
        encoding="utf-8",
    )


def _reseal_lane(
    repository_root: Path,
    row: dict[str, object],
    *,
    refresh_review_inputs: bool = True,
) -> None:
    lane_id = str(row["lane_id"])
    lane_root = repository_root / R4_ARTIFACT_ROOT / lane_id
    review_input_sources = {
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
    review_root = lane_root / "review-input"
    if refresh_review_inputs:
        execution_record = json.loads(
            (lane_root / "execution-record.json").read_text(
                encoding="utf-8"
            )
        )
        for review_name, source_name in review_input_sources.items():
            review_path = review_root / review_name
            review_path.parent.mkdir(parents=True, exist_ok=True)
            if source_name is None:
                _write_json(
                    review_path,
                    _execution_review_summary(execution_record),
                )
            else:
                review_path.write_bytes(
                    (lane_root / source_name).read_bytes()
                )
    review_context_path = lane_root / "falsification-review-context.json"
    review_context = json.loads(
        review_context_path.read_text(encoding="utf-8")
    )
    for reference in review_context["input_artifacts"]:
        path = repository_root / str(reference["path"])
        reference["sha256"] = sha256_bytes(path.read_bytes())
    _write_json(review_context_path, review_context)
    review_identity_path = lane_root / "falsification-review-identity.json"
    review_identity = json.loads(
        review_identity_path.read_text(encoding="utf-8")
    )
    review_prompt_path = lane_root / "falsification-review-prompt.md"
    review_prompt_path.write_text(
        _expected_review_prompt(tuple(review_input_sources)),
        encoding="utf-8",
    )
    review_output_schema_path = (
        lane_root / "falsification-review-output-schema.json"
    )
    review_identity["command"]["prompt_sha256"] = sha256_bytes(
        review_prompt_path.read_bytes()
    )
    _write_json(review_identity_path, review_identity)
    review_thread_id = review_identity["effective_model_source"]["thread_id"]
    review_turn_id = review_identity["effective_model_source"]["turn_id"]
    review_invocation_id = f"{review_thread_id}:{review_turn_id}"
    review_output_path = lane_root / "falsification-review-output.json"
    review_output = json.loads(
        review_output_path.read_text(encoding="utf-8")
    )
    _write_json(review_output_path, review_output)
    review_events_path = lane_root / "falsification-review-events.jsonl"
    review_events_path.write_text(
        "".join(
            json.dumps(event, sort_keys=True) + "\n"
            for event in (
                {
                    "type": "thread.started",
                    "thread_id": review_thread_id,
                },
                {
                    "type": "item.completed",
                    "item": {
                        "type": "agent_message",
                        "text": review_output_path.read_text(
                            encoding="utf-8"
                        ).strip(),
                    },
                },
                {
                    "type": "turn.completed",
                    "status": "completed",
                },
            )
        ),
        encoding="utf-8",
    )
    review_invocation_path = (
        lane_root / "falsification-review-invocation.json"
    )
    _write_json(
        review_invocation_path,
        {
            "schema_version": 2,
            "role": "verification-agent-falsification-reviewer-v1",
            "call_index": 1,
            "requested_model": None,
            "argv_without_prompt": review_identity["command"][
                "argv_without_prompt"
            ],
            "prompt_transport": "final_argv",
            "prompt_sha256": review_identity["command"]["prompt_sha256"],
            "output_schema_sha256": sha256_bytes(
                review_output_schema_path.read_bytes()
            ),
        },
    )

    evidence = row["attempt_evidence"]
    assert isinstance(evidence, dict)
    refs = evidence["refs"]
    assert isinstance(refs, dict)
    for key, reference in refs.items():
        if key in {"falsification_review", "lane_ledger"}:
            continue
        assert isinstance(reference, dict)
        path = repository_root / str(reference["path"])
        reference["sha256"] = sha256_bytes(path.read_bytes())
    review = row["falsification_review"]
    assert isinstance(review, dict)
    review["invocation_id"] = review_invocation_id
    review["outcome"] = review_output["outcome"]
    review["effective_model"] = review_identity["effective_model"]
    review["candidate_finding_sha256"] = sha256_bytes(
        (lane_root / "finding.json").read_bytes()
    )
    review["sha256"] = refs["falsification_review"]["sha256"]
    review["identity_sha256"] = refs[
        "falsification_review_identity"
    ]["sha256"]
    review["clean_context_sha256"] = refs["falsification_review_context"][
        "sha256"
    ]
    review["output_sha256"] = refs["falsification_review_output"]["sha256"]
    review["output_schema_sha256"] = refs[
        "falsification_review_output_schema"
    ]["sha256"]
    review["events_sha256"] = refs["falsification_review_events"]["sha256"]
    review["invocation_ledger_sha256"] = refs[
        "falsification_review_invocation"
    ]["sha256"]
    review["prompt_sha256"] = refs["falsification_review_prompt"]["sha256"]
    _write_json(
        lane_root / "falsification-review.json",
        {
            key: value
            for key, value in review.items()
            if key not in {"path", "sha256"}
        },
    )
    refs["falsification_review"]["sha256"] = sha256_bytes(
        (lane_root / "falsification-review.json").read_bytes()
    )
    review["sha256"] = refs["falsification_review"]["sha256"]

    ledger_path = lane_root / "checksums.sha256"
    validation_path = lane_root / "attempt-evidence-validation.json"
    ledger_entries = sorted(
        path
        for path in lane_root.rglob("*")
        if path.is_file()
        and path not in {ledger_path, validation_path}
    )
    ledger_path.write_text(
        "".join(
            f"{sha256_bytes(path.read_bytes())}  "
            f"{path.relative_to(lane_root).as_posix()}\n"
            for path in ledger_entries
        ),
        encoding="utf-8",
    )
    refs["lane_ledger"]["sha256"] = sha256_bytes(ledger_path.read_bytes())
    evidence["evidence_refs_sha256"] = sha256_bytes(
        canonical_json_bytes(refs)
    )
    _write_json(validation_path, evidence)
    receipt = row["attempt_evidence_receipt"]
    assert isinstance(receipt, dict)
    receipt["sha256"] = sha256_bytes(validation_path.read_bytes())
    _write_root_ledger(repository_root)


def _reconcile_fixture(fixture: dict[str, object]) -> dict[str, object]:
    return reconcile_formal_rows(
        fixture["rows"],
        fixture["contradiction"],
        auditor_mapping=fixture["mapping"],
        expected_mapping_commitment_sha256=fixture[
            "mapping_commitment"
        ],
        expected_contradiction_audit_sha256=fixture[
            "contradiction_commitment"
        ],
        formal_attempt_inventory=fixture["attempt_inventory"],
        formal_attempt_inventory_receipt=fixture[
            "attempt_inventory_receipt"
        ],
        evidence_repository_root=fixture["evidence_repository_root"],
    )


def test_candidate_manifest_is_valid_but_not_formally_frozen() -> None:
    if not MANIFEST.exists():
        pytest.skip("R3 generator has not materialized the candidate manifest")
    manifest = load_manifest(MANIFEST)
    assert manifest.status in {"awaiting_human_approval", "frozen"}
    assert manifest.packet_commitment_sha256 == freeze_payload_sha256(
        manifest.document
    )
    if manifest.status == "awaiting_human_approval":
        with pytest.raises(M9RecoveryQualificationError, match="requires frozen"):
            load_manifest(MANIFEST, require_frozen=True)


def test_built_apk_identity_receipts_hash_the_stored_output_bytes() -> None:
    manifest = load_manifest(MANIFEST)
    for role in ("defect", "control"):
        inspection = manifest.document["target"][role]["apk"]["inspection"]
        for command in ("package", "manifest"):
            receipt = inspection[command]
            assert receipt["returncode"] == 0
            assert receipt["stdout_sha256"] == sha256_bytes(
                receipt["stdout"].encode()
            )
            assert receipt["stderr_sha256"] == sha256_bytes(
                receipt["stderr"].encode()
            )


def test_admission_receipts_require_default_codex_selection_and_six_lanes() -> None:
    def receipt(lane_id: str, digest: str, commit: str) -> dict[str, object]:
        host_project = f"/private/tmp/{lane_id}"
        artifact_dir = f"/repo/{R4_ARTIFACT_ROOT}/{lane_id}/artifacts"
        return {
            "status": "admitted",
            "admitted": True,
            "run_spec": {
                "path": (
                    "/repo/bench/m9/recovery-v2/run-specs/"
                    f"{lane_id}.yaml"
                ),
                "sha256": digest,
                "scenario": lane_id,
            },
            "host": {
                "origin": SOURCE_ORIGIN,
                "commit": commit,
                "host_project": host_project,
                "repository_root": host_project,
                "worktree": {
                    "clean": True,
                    "status_sha256": sha256_bytes(b""),
                },
            },
            "artifact_namespace": {
                "artifact_dir": artifact_dir,
                "run_dir": f"/repo/{R4_ARTIFACT_ROOT}/{lane_id}",
                "formal_outputs_absent": True,
            },
            "runner_policy": {
                "backend": "codex_cli",
                "version": "m9-production-seam-v1",
                "options": {
                    "device": "emulator-5554",
                    "backend": "codex_cli",
                    "requested_driver_model": None,
                    "requested_l3_model": None,
                    "runner_policy_version": "m9-production-seam-v1",
                    "expected_source_commit": commit,
                    "launch": True,
                    "allow_host_project_subdir": False,
                    "workdir": host_project,
                    "artifact_dir": artifact_dir,
                    "android_bin": "android",
                    "adb_bin": "adb",
                    "codex_bin": "codex",
                },
                "tools": {
                    name: {
                        "requested": name,
                        "resolved_path": f"/tools/{name}",
                        "sha256": sha256_bytes(name.encode()),
                    }
                    for name in ("android", "adb", "codex")
                }
                | {
                    "model_selection": {
                        role: {
                            "model_override_present": False,
                            "policy": "codex_cli_default",
                            "requested_model": None,
                        }
                        for role in (
                            "journey_driver",
                            "l3_semantic_judge",
                        )
                    }
                },
            },
            "side_effects": {
                "external": False,
                "build": False,
                "device": False,
                "agent": False,
            },
        }

    expected = {
        lane_id: {
            "run_spec_sha256": f"{index:064x}",
            "commit": "a" * 40,
        }
        for index, lane_id in enumerate(LANE_IDS, start=1)
    }
    receipts = [
        receipt(
            lane_id,
            str(expected[lane_id]["run_spec_sha256"]),
            str(expected[lane_id]["commit"]),
        )
        for lane_id in LANE_IDS
    ]
    assert (
        validate_admission_receipts(
            receipts,
            expected_run_specs=expected,
        )["status"]
        == "pass"
    )

    explicit_model = copy.deepcopy(receipts)
    explicit_model[0]["runner_policy"]["options"]["requested_driver_model"] = (
        "codex-default"
    )
    assert (
        validate_admission_receipts(
            explicit_model,
            expected_run_specs=expected,
        )["status"]
        == "fail"
    )

    wrong_namespace = copy.deepcopy(receipts)
    wrong_namespace[0]["runner_policy"]["options"]["artifact_dir"] = (
        "/repo/arbitrary/artifacts"
    )
    wrong_namespace[0]["artifact_namespace"]["artifact_dir"] = (
        "/repo/arbitrary/artifacts"
    )
    wrong_namespace[0]["artifact_namespace"]["run_dir"] = "/repo/arbitrary"
    assert (
        validate_admission_receipts(
            wrong_namespace,
            expected_run_specs=expected,
        )["status"]
        == "fail"
    )

    wrong_tool = copy.deepcopy(receipts)
    wrong_tool[0]["runner_policy"]["options"]["codex_bin"] = "other-codex"
    assert (
        validate_admission_receipts(
            wrong_tool,
            expected_run_specs=expected,
        )["status"]
        == "fail"
    )


def test_supported_requires_every_frozen_gate(tmp_path: Path) -> None:
    fixture = _formal_fixture(tmp_path)
    rows = fixture["rows"]
    result = reconcile_formal_rows(
        rows,
        fixture["contradiction"],
        auditor_mapping=fixture["mapping"],
        expected_mapping_commitment_sha256=fixture["mapping_commitment"],
        expected_contradiction_audit_sha256=fixture[
            "contradiction_commitment"
        ],
        formal_attempt_inventory=fixture["attempt_inventory"],
        formal_attempt_inventory_receipt=fixture[
            "attempt_inventory_receipt"
        ],
        evidence_repository_root=fixture["evidence_repository_root"],
    )
    assert result["aggregate_result"] == "Supported"
    assert result["counts"] == {
        "lane_count": 6,
        "accountable": 6,
        "attempt_evidence_validated": 6,
        "defect_supported": 3,
        "control_locally_rejected": 3,
        "falsification_review_survived": 6,
        "review_identities_unique": True,
        "production_identities_authoritative": True,
        "production_identities_unique": True,
        "review_production_identities_disjoint": True,
        "contradiction_packet_pre_side_effect": True,
        "lane_attempt_count": 6,
        "lane_retry_count": 0,
        "lane_replacement_count": 0,
        "lane_discretionary_rerun_count": 0,
        "formal_attempt_inventory_checksum_bound": True,
        "root_ledger_exhaustive": True,
        "lane_roots_exact": True,
        "execution_records_exhaustive": True,
        "execution_record_count": 6,
        "execution_record_attempt_ids_unique": True,
        "inventory_execution_records_bound": True,
    }
    assert result["formal_attempt_count"] == 1
    assert result["retry_count"] == 0
    assert result["replacement_count"] == 0
    assert result["mapping_assignment_verified"] is True
    assert result["discretionary_rerun_count"] == 0
    assert result["mapping_commitment_sha256"] == fixture["mapping_commitment"]
    assert all("role" not in lane for lane in result["lanes"])

    adverse = copy.deepcopy(rows)
    adverse[0]["falsification_review"]["outcome"] = "challenged"
    assert (
        reconcile_formal_rows(
            adverse,
            fixture["contradiction"],
            auditor_mapping=fixture["mapping"],
            expected_mapping_commitment_sha256=fixture[
                "mapping_commitment"
            ],
            expected_contradiction_audit_sha256=fixture[
                "contradiction_commitment"
            ],
            formal_attempt_inventory=fixture["attempt_inventory"],
            formal_attempt_inventory_receipt=fixture[
                "attempt_inventory_receipt"
            ],
            evidence_repository_root=fixture["evidence_repository_root"],
        )["aggregate_result"]
        == "Not Supported"
    )


def test_pre_runtime_rows_bind_inventory_without_claiming_runtime(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    minimal_rows: list[dict[str, object]] = []
    for original in fixture["rows"]:
        assert isinstance(original, dict)
        original_evidence = original["attempt_evidence"]
        assert isinstance(original_evidence, dict)
        original_refs = original_evidence["refs"]
        assert isinstance(original_refs, dict)
        minimal_rows.append(
            {
                "lane_id": original["lane_id"],
                "role": original["role"],
                "accountable": False,
                "execution_record_accountable": False,
                "terminal": True,
                "formal_attempt_id": FORMAL_ATTEMPT_ID,
                "execution_record_attempt_id": original[
                    "execution_record_attempt_id"
                ],
                "lane_attempt_count": 1,
                "retry_count": 0,
                "replacement_count": 0,
                "discretionary_rerun_count": 0,
                "production_invocation_id": None,
                "production_identity_sha256": None,
                "finding_conclusion": "inconclusive",
                "terminal_absence_receipt": {
                    "schema_version": 1,
                    "validation_version": "m9-recovery-terminal-absence-v1",
                    "status": "not_applicable",
                    "lane_id": original["lane_id"],
                    "formal_attempt_id": FORMAL_ATTEMPT_ID,
                    "execution_record_attempt_id": original[
                        "execution_record_attempt_id"
                    ],
                    "accountable": False,
                    "runtime_started": False,
                    "refs": {
                        "execution_record": original_refs[
                            "execution_record"
                        ],
                    },
                },
                "terminal_absence_receipt_ref": {},
                "attempt_evidence_validated": False,
                "runtime_started": False,
                "falsification_review": {
                    "status": "not_run",
                    "outcome": "inconclusive",
                },
            }
        )
    assert len(minimal_rows) == 6

    result = reconcile_formal_rows(
        minimal_rows,
        fixture["contradiction"],
        auditor_mapping=fixture["mapping"],
        expected_mapping_commitment_sha256=fixture["mapping_commitment"],
        expected_contradiction_audit_sha256=fixture[
            "contradiction_commitment"
        ],
        formal_attempt_inventory=fixture["attempt_inventory"],
        formal_attempt_inventory_receipt=fixture[
            "attempt_inventory_receipt"
        ],
        evidence_repository_root=fixture["evidence_repository_root"],
    )

    assert result["formal_attempt_reconciled"] is True
    assert all("attempt_evidence" not in row for row in minimal_rows)
    assert result["runtime_holdout_executed"] is False
    assert result["formal_holdout_executed"] is False
    assert result["counts"]["inventory_execution_records_bound"] is True
    assert result["counts"]["execution_records_exhaustive"] is True
    assert result["counts"]["execution_record_attempt_ids_unique"] is True
    assert result["retry_count"] == 0
    assert result["replacement_count"] == 0
    assert result["discretionary_rerun_count"] == 0
    assert result["supported_gate"][
        "one_formal_attempt_zero_retry_replacement"
    ] is True
    assert result["aggregate_result"] == "Not Supported"


def test_historical_r5_reconciliation_artifact_remains_checksum_bound() -> None:
    historical_root = (
        ROOT / "docs/runs/2026-08-08-issue-157-m9-r5-reconciliation"
    )
    ledger = historical_root / "checksums.sha256"
    entries = {}
    for line in ledger.read_text(encoding="utf-8").splitlines():
        digest, separator, name = line.partition("  ")
        assert separator == "  "
        entries[name] = digest
    assert entries["reconciliation.json"] == sha256_bytes(
        (historical_root / "reconciliation.json").read_bytes()
    )
    assert entries["interpretation.json"] == sha256_bytes(
        (historical_root / "interpretation.json").read_bytes()
    )


@pytest.mark.parametrize("mutation", ("missing", "tampered", "extra"))
def test_supported_requires_exhaustive_root_ledger(
    tmp_path: Path,
    mutation: str,
) -> None:
    fixture = _formal_fixture(tmp_path)
    attempt_root = tmp_path / R4_RUN_RECORD
    ledger_path = attempt_root / "checksums.sha256"
    if mutation == "missing":
        ledger_path.unlink()
    elif mutation == "tampered":
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
        lines[0] = "0" * 64 + lines[0][64:]
        ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        _write_json(attempt_root / "unlisted-root-artifact.json", {"extra": True})

    result = _reconcile_fixture(fixture)
    assert result["counts"]["root_ledger_exhaustive"] is False
    assert result["aggregate_result"] == "Not Supported"


def test_falsification_review_producer_uses_semantic_output_and_runner_envelope(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    row = fixture["rows"][0]
    assert isinstance(row, dict)
    lane_id = str(row["lane_id"])
    lane_root = tmp_path / R4_ARTIFACT_ROOT / lane_id

    prompt = (lane_root / "falsification-review-prompt.md").read_text(
        encoding="utf-8"
    )
    assert str(tmp_path) not in prompt
    assert "JSON Schema" in prompt
    for input_path in (
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
    ):
        assert f"- {input_path}" in prompt
    for dimension in (
        "alternative_explanations",
        "assumption_violations",
        "evidence_integrity",
        "causal_attribution",
        "observation_consistency",
        "claim_boundary",
    ):
        assert f'"{dimension}"' in prompt

    output = json.loads(
        (lane_root / "falsification-review-output.json").read_text(
            encoding="utf-8"
        )
    )
    output_schema = json.loads(
        (
            lane_root / "falsification-review-output-schema.json"
        ).read_text(encoding="utf-8")
    )
    jsonschema.validate(output, output_schema)
    assert set(output) == {
        "schema_version",
        "status",
        "outcome",
        "dimensions",
        "reasons",
        "claim_boundary",
        "source_role_disclosed",
        "expected_result_disclosed",
    }
    assert all(
        not reference.startswith("docs/")
        for dimension in output["dimensions"]
        for reference in dimension["evidence_refs"]
    )

    receipt = json.loads(
        (lane_root / "falsification-review.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["schema_version"] == 2
    assert receipt["invocation_id"].startswith("review-thread-")
    assert receipt["candidate_finding_sha256"] == sha256_bytes(
        (lane_root / "finding.json").read_bytes()
    )
    assert receipt["clean_context_sha256"] == sha256_bytes(
        (lane_root / "falsification-review-context.json").read_bytes()
    )
    invocation = json.loads(
        (lane_root / "falsification-review-invocation.json").read_text(
            encoding="utf-8"
        )
    )
    assert invocation["schema_version"] == 2
    assert invocation["prompt_transport"] == "final_argv"
    assert "--output-schema" in invocation["argv_without_prompt"]
    assert invocation["output_schema_sha256"] == sha256_bytes(
        (
            lane_root / "falsification-review-output-schema.json"
        ).read_bytes()
    )
    with pytest.raises(
        M9RecoveryQualificationError,
        match="review invocation namespace is not fresh",
    ):
        prepare_falsification_review_invocation(
            lane_id=lane_id,
            repository_root=tmp_path,
        )


def test_falsification_review_executes_through_injected_runner_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _formal_fixture(tmp_path)
    row = fixture["rows"][0]
    assert isinstance(row, dict)
    lane_id = str(row["lane_id"])
    lane_root = tmp_path / R4_ARTIFACT_ROOT / lane_id
    for name in (
        "falsification-review.json",
        "falsification-review-output.json",
        "falsification-review-output-schema.json",
        "falsification-review-events.jsonl",
        "falsification-review-invocation.json",
        "falsification-review-prompt.md",
        "falsification-review-identity.json",
    ):
        (lane_root / name).unlink()

    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    fake_codex.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    fake_codex.chmod(0o755)
    monkeypatch.setenv(
        "PATH",
        f"{fake_bin_dir}{os.pathsep}{os.environ['PATH']}",
    )
    session_root = tmp_path / "codex-sessions"

    class ReviewRunner(CommandRunner):
        def __init__(self) -> None:
            self.review_calls = 0
            self.version_calls = 0

        def run(
            self,
            args: list[str],
            *,
            cwd: Path | None = None,
            timeout_seconds: int | None = None,
            input_text: str | None = None,
        ) -> CommandResult:
            if args == ["codex", "--version"]:
                self.version_calls += 1
                return CommandResult(
                    args=args,
                    stdout="codex-cli 0.144.6\n",
                    stderr="",
                    returncode=0,
                )
            self.review_calls += 1
            assert self.review_calls == 1
            assert cwd == lane_root / "review-input"
            assert timeout_seconds == 123
            assert input_text == ""
            assert args[0:3] == ["codex", "exec", "--json"]
            prompt = args[-1]
            assert prompt == (
                lane_root / "falsification-review-prompt.md"
            ).read_text(encoding="utf-8")
            output_path = Path(
                args[args.index("--output-last-message") + 1]
            )
            schema_path = Path(args[args.index("--output-schema") + 1])
            evidence_refs = [
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
            ]
            output = {
                "schema_version": 1,
                "status": "complete",
                "outcome": "survived",
                "dimensions": [
                    {
                        "id": dimension,
                        "status": "supported",
                        "analysis": (
                            f"{dimension} survives the independent review."
                        ),
                        "evidence_refs": evidence_refs,
                    }
                    for dimension in (
                        "alternative_explanations",
                        "assumption_violations",
                        "evidence_integrity",
                        "causal_attribution",
                        "observation_consistency",
                        "claim_boundary",
                    )
                ],
                "reasons": [],
                "claim_boundary": LOCAL_CLAIM_BOUNDARY,
                "source_role_disclosed": False,
                "expected_result_disclosed": False,
            }
            jsonschema.validate(
                output,
                json.loads(schema_path.read_text(encoding="utf-8")),
            )
            _write_json(output_path, output)
            output_text = output_path.read_text(encoding="utf-8").strip()
            thread_id = "review-boundary-thread"
            turn_id = "review-boundary-turn"
            events = (
                {"type": "thread.started", "thread_id": thread_id},
                {
                    "type": "item.completed",
                    "item": {
                        "type": "agent_message",
                        "text": output_text,
                    },
                },
                {"type": "turn.completed", "status": "completed"},
            )
            session_path = (
                session_root
                / "2026/08/07"
                / f"rollout-2026-08-07-{thread_id}.jsonl"
            )
            session_path.parent.mkdir(parents=True, exist_ok=True)
            session_path.write_text(
                "".join(
                    json.dumps(event, sort_keys=True) + "\n"
                    for event in (
                        {
                            "type": "session_meta",
                            "payload": {
                                "id": thread_id,
                                "cwd": str(cwd),
                                "cli_version": "0.144.6",
                                "source": "exec",
                            },
                        },
                        {
                            "type": "turn_context",
                            "payload": {
                                "turn_id": turn_id,
                                "model": "gpt-5.6-sol",
                            },
                        },
                    )
                ),
                encoding="utf-8",
            )
            return CommandResult(
                args=args,
                stdout="".join(
                    json.dumps(event, sort_keys=True) + "\n"
                    for event in events
                ),
                stderr="",
                returncode=0,
            )

    runner = ReviewRunner()
    receipt = execute_falsification_review(
        lane_id=lane_id,
        repository_root=tmp_path,
        production_invocation_id=str(row["production_invocation_id"]),
        production_identity_sha256=str(
            row["production_identity_sha256"]
        ),
        runner=runner,
        session_root=session_root,
        timeout_seconds=123,
    )
    assert runner.review_calls == 1
    assert runner.version_calls == 1
    assert receipt["outcome"] == "survived"
    assert receipt["invocation_id"] == (
        "review-boundary-thread:review-boundary-turn"
    )
    assert json.loads(
        (lane_root / "falsification-review.json").read_text(
            encoding="utf-8"
        )
    ) == receipt


@pytest.mark.parametrize(
    ("mode", "expected_stage", "expected_returncode"),
    (
        ("nonzero", "process_exit", 73),
        ("timeout", "timeout", 124),
        ("missing_output", "missing_output", 0),
        ("identity_capture", "identity_capture", 0),
        ("final_binding", "final_binding", 0),
    ),
)
def test_falsification_review_failure_is_terminal_and_auditable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    expected_stage: str,
    expected_returncode: int,
) -> None:
    fixture = _formal_fixture(tmp_path)
    row = fixture["rows"][0]
    assert isinstance(row, dict)
    lane_id = str(row["lane_id"])
    lane_root = tmp_path / R4_ARTIFACT_ROOT / lane_id
    generated_names = (
        "falsification-review.json",
        "falsification-review-output.json",
        "falsification-review-output-schema.json",
        "falsification-review-events.jsonl",
        "falsification-review-invocation.json",
        "falsification-review-prompt.md",
        "falsification-review-identity.json",
    )
    for name in generated_names:
        (lane_root / name).unlink()

    fake_bin_dir = tmp_path / "fake-bin"
    fake_bin_dir.mkdir()
    fake_codex = fake_bin_dir / "codex"
    fake_codex.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    fake_codex.chmod(0o755)
    monkeypatch.setenv(
        "PATH",
        f"{fake_bin_dir}{os.pathsep}{os.environ['PATH']}",
    )
    session_root = tmp_path / "codex-sessions"

    class FailureRunner(CommandRunner):
        def __init__(self) -> None:
            self.review_calls = 0
            self.version_calls = 0

        def run(
            self,
            args: list[str],
            *,
            cwd: Path | None = None,
            timeout_seconds: int | None = None,
            input_text: str | None = None,
        ) -> CommandResult:
            if args == ["codex", "--version"]:
                self.version_calls += 1
                return CommandResult(
                    args=list(args),
                    stdout="codex-cli 0.144.6\n",
                    stderr="",
                    returncode=0,
                )
            self.review_calls += 1
            assert self.review_calls == 1
            assert cwd == lane_root / "review-input"
            assert timeout_seconds == 17
            assert input_text == ""
            thread_id = f"review-failure-{mode}"
            output_path = Path(
                args[args.index("--output-last-message") + 1]
            )
            if mode in {"identity_capture", "final_binding"}:
                _write_json(output_path, {})
            if mode == "final_binding":
                session_path = (
                    session_root
                    / "2026/08/07"
                    / f"rollout-2026-08-07-{thread_id}.jsonl"
                )
                session_path.parent.mkdir(parents=True, exist_ok=True)
                session_path.write_text(
                    "".join(
                        json.dumps(event, sort_keys=True) + "\n"
                        for event in (
                            {
                                "type": "session_meta",
                                "payload": {
                                    "id": thread_id,
                                    "cwd": str(cwd),
                                    "cli_version": "0.144.6",
                                    "source": "exec",
                                },
                            },
                            {
                                "type": "turn_context",
                                "payload": {
                                    "turn_id": "review-failure-turn",
                                    "model": "gpt-5.6-sol",
                                },
                            },
                        )
                    ),
                    encoding="utf-8",
                )
            events = [
                {"type": "thread.started", "thread_id": thread_id}
            ]
            if mode == "final_binding":
                events.extend(
                    (
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "agent_message",
                                "text": "{}",
                            },
                        },
                        {"type": "turn.completed", "status": "completed"},
                    )
                )
            stdout = "".join(
                json.dumps(event, sort_keys=True) + "\n"
                for event in events
            )
            return CommandResult(
                args=list(args),
                stdout=stdout,
                stderr=(
                    "review process timed out"
                    if mode == "timeout"
                    else (
                        "review process exited deliberately"
                        if mode == "nonzero"
                        else ""
                    )
                ),
                returncode=(
                    124
                    if mode == "timeout"
                    else 73 if mode == "nonzero" else 0
                ),
            )

    runner = FailureRunner()
    with pytest.raises(
        FalsificationReviewExecutionError,
        match="no retry is permitted",
    ) as raised:
        execute_falsification_review(
            lane_id=lane_id,
            repository_root=tmp_path,
            production_invocation_id=str(
                row["production_invocation_id"]
            ),
            production_identity_sha256=str(
                row["production_identity_sha256"]
            ),
            runner=runner,
            session_root=session_root,
            timeout_seconds=17,
        )

    receipt_path = lane_root / "falsification-review.json"
    assert raised.value.receipt_path == receipt_path
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == 2
    assert receipt["kind"] == "falsification_review_terminal_failure"
    assert receipt["status"] == "failed"
    assert receipt["outcome"] == "inconclusive"
    assert receipt["terminal"] is True
    assert receipt["failure_stage"] == expected_stage
    assert receipt["reason"]
    assert receipt["retry_permitted"] is False
    assert receipt["replacement_permitted"] is False
    assert receipt["discretionary_rerun_permitted"] is False
    assert receipt["invocation_attempt_count"] == 1
    assert receipt["production_binding"] == {
        "status": "validated_pre_invocation",
        "invocation_id": row["production_invocation_id"],
        "identity_path": (
            f"{R4_ARTIFACT_ROOT}/{lane_id}/"
            "effective-execution-identity.json"
        ),
        "identity_sha256": row["production_identity_sha256"],
    }
    assert receipt["command"]["timeout_seconds"] == 17
    assert receipt["command"]["prompt_transport"] == "final_argv"
    assert receipt["command"]["final_argv_sha256"] == sha256_bytes(
        canonical_json_bytes(receipt["process"]["reported_args"])
    )
    assert receipt["process"]["returncode"] == expected_returncode
    assert receipt["process"]["reported_args_sha256"] == sha256_bytes(
        canonical_json_bytes(receipt["process"]["reported_args"])
    )
    assert receipt["process"]["stdout"] == (
        lane_root / "falsification-review-events.jsonl"
    ).read_text(encoding="utf-8")
    assert receipt["process"]["stdout_sha256"] == sha256_bytes(
        receipt["process"]["stdout"].encode("utf-8")
    )
    assert receipt["process"]["stderr_sha256"] == sha256_bytes(
        receipt["process"]["stderr"].encode("utf-8")
    )
    assert receipt["process"]["stderr"] == (
        "review process timed out"
        if mode == "timeout"
        else (
            "review process exited deliberately"
            if mode == "nonzero"
            else ""
        )
    )
    assert receipt["checksum_seal"] == {
        "lane_ledger": "checksums.sha256",
        "required": True,
    }
    started_at = dt.datetime.fromisoformat(receipt["started_at"])
    finished_at = dt.datetime.fromisoformat(receipt["finished_at"])
    assert started_at.tzinfo is not None
    assert finished_at.tzinfo is not None
    assert finished_at >= started_at
    assert receipt["artifacts"]["context"] is not None
    assert receipt["artifacts"]["prompt"] is not None
    assert receipt["artifacts"]["output_schema"] is not None
    assert receipt["artifacts"]["invocation_ledger"] is not None
    assert receipt["artifacts"]["events"] is not None
    assert (
        receipt["artifacts"]["semantic_output"] is not None
    ) is (mode in {"identity_capture", "final_binding"})
    assert (
        receipt["artifacts"]["identity"] is not None
    ) is (mode == "final_binding")
    for reference in receipt["artifacts"].values():
        if reference is None:
            continue
        artifact_path = tmp_path / reference["path"]
        assert artifact_path.is_file()
        assert reference["sha256"] == sha256_bytes(
            artifact_path.read_bytes()
        )
    assert runner.review_calls == 1
    assert runner.version_calls == (1 if mode == "final_binding" else 0)

    with pytest.raises(
        M9RecoveryQualificationError,
        match="review invocation namespace is not fresh",
    ):
        execute_falsification_review(
            lane_id=lane_id,
            repository_root=tmp_path,
            production_invocation_id=str(
                row["production_invocation_id"]
            ),
            production_identity_sha256=str(
                row["production_identity_sha256"]
            ),
            runner=runner,
            session_root=session_root,
            timeout_seconds=17,
        )
    assert runner.review_calls == 1


@pytest.mark.parametrize("invalid_field", ("invocation_id", "identity_sha256"))
def test_falsification_review_rejects_production_binding_before_side_effects(
    tmp_path: Path,
    invalid_field: str,
) -> None:
    fixture = _formal_fixture(tmp_path)
    row = fixture["rows"][0]
    assert isinstance(row, dict)
    lane_id = str(row["lane_id"])
    lane_root = tmp_path / R4_ARTIFACT_ROOT / lane_id
    generated_names = (
        "falsification-review.json",
        "falsification-review-output.json",
        "falsification-review-output-schema.json",
        "falsification-review-events.jsonl",
        "falsification-review-invocation.json",
        "falsification-review-prompt.md",
        "falsification-review-identity.json",
    )
    for name in generated_names:
        (lane_root / name).unlink()

    class ForbiddenRunner(CommandRunner):
        def __init__(self) -> None:
            self.calls = 0

        def run(
            self,
            args: list[str],
            *,
            cwd: Path | None = None,
            timeout_seconds: int | None = None,
            input_text: str | None = None,
        ) -> CommandResult:
            self.calls += 1
            raise AssertionError("invalid binding must not reach the runner")

    production_invocation_id = str(row["production_invocation_id"])
    production_identity_sha256 = str(
        row["production_identity_sha256"]
    )
    if invalid_field == "invocation_id":
        production_invocation_id = "unbound-production:unbound-turn"
    else:
        production_identity_sha256 = "0" * 64
    runner = ForbiddenRunner()
    with pytest.raises(
        M9RecoveryQualificationError,
        match="does not match the bound lane",
    ):
        execute_falsification_review(
            lane_id=lane_id,
            repository_root=tmp_path,
            production_invocation_id=production_invocation_id,
            production_identity_sha256=production_identity_sha256,
            runner=runner,
        )
    assert runner.calls == 0
    assert all(not (lane_root / name).exists() for name in generated_names)


@pytest.mark.parametrize(
    "relative_path",
    (
        "runner-setup.json",
        "production-seam-admission.json",
        "raw/screenshots/before.png",
        "raw/layout/after.json",
        "raw/logcat/rotation.txt",
        "falsification-review-output.json",
        "falsification-review-output-schema.json",
        "falsification-review-events.jsonl",
        "falsification-review-invocation.json",
        "falsification-review-prompt.md",
    ),
)
def test_supported_rejects_missing_required_runner_or_raw_evidence(
    tmp_path: Path,
    relative_path: str,
) -> None:
    fixture = _formal_fixture(tmp_path)
    lane_root = tmp_path / R4_ARTIFACT_ROOT / LANE_IDS[0]
    (lane_root / relative_path).unlink()
    assert _reconcile_fixture(fixture)["aggregate_result"] == "Not Supported"


def test_supported_rejects_signature_only_png_after_reseal(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    row = fixture["rows"][0]
    assert isinstance(row, dict)
    screenshot = (
        tmp_path
        / R4_ARTIFACT_ROOT
        / LANE_IDS[0]
        / "raw/screenshots/before.png"
    )
    screenshot.write_bytes(b"\x89PNG\r\n\x1a\n" + b"not-a-complete-png")
    _reseal_lane(tmp_path, row)
    result = _reconcile_fixture(fixture)
    assert result["counts"]["attempt_evidence_validated"] == 5
    assert result["aggregate_result"] == "Not Supported"


def test_supported_recomputes_text_input_and_recreation_evidence(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    first = fixture["rows"][0]
    assert isinstance(first, dict)
    lane_root = tmp_path / R4_ARTIFACT_ROOT / LANE_IDS[0]
    layout_path = lane_root / "raw/layout/before.json"
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    layout["text_input_observation"]["exact_token_visible_in_input"] = False
    _write_json(layout_path, layout)
    _reseal_lane(tmp_path, first)
    result = _reconcile_fixture(fixture)
    assert result["counts"]["attempt_evidence_validated"] == 5
    assert result["aggregate_result"] == "Not Supported"

    fixture = _formal_fixture(tmp_path / "recreation")
    first = fixture["rows"][0]
    assert isinstance(first, dict)
    lane_root = (
        tmp_path / "recreation" / R4_ARTIFACT_ROOT / LANE_IDS[0]
    )
    (lane_root / "raw/logcat/rotation.txt").write_text(
        "rotation completed without lifecycle evidence\n",
        encoding="utf-8",
    )
    _reseal_lane(tmp_path / "recreation", first)
    result = _reconcile_fixture(fixture)
    assert result["counts"]["attempt_evidence_validated"] == 5
    assert result["aggregate_result"] == "Not Supported"


def test_supported_binds_lifecycle_to_adb_events_receipt(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    first = fixture["rows"][0]
    assert isinstance(first, dict)
    lane_root = tmp_path / R4_ARTIFACT_ROOT / LANE_IDS[0]
    receipt_path = lane_root / "raw/logcat/events-command.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["stdout"] = "no activity lifecycle evidence\n"
    _write_json(receipt_path, receipt)
    _reseal_lane(tmp_path, first)
    result = _reconcile_fixture(fixture)
    assert result["counts"]["attempt_evidence_validated"] == 5
    assert result["aggregate_result"] == "Not Supported"


@pytest.mark.parametrize(
    "mutation",
    ("missing_checkpoint", "tampered_checkpoint", "derived_suffix"),
)
def test_supported_reconstructs_normalized_logcat_from_raw_sources(
    tmp_path: Path,
    mutation: str,
) -> None:
    fixture = _formal_fixture(tmp_path)
    first = fixture["rows"][0]
    assert isinstance(first, dict)
    lane_root = tmp_path / R4_ARTIFACT_ROOT / LANE_IDS[0]
    checkpoint_path = lane_root / "artifacts/after-event-0/logcat.txt"
    if mutation == "missing_checkpoint":
        checkpoint_path.unlink()
    elif mutation == "tampered_checkpoint":
        checkpoint_path.write_text(
            "I/ActivityTaskManager: different checkpoint bytes\n",
            encoding="utf-8",
        )
    else:
        normalized_path = lane_root / "raw/logcat/rotation.txt"
        normalized_path.write_text(
            normalized_path.read_text(encoding="utf-8")
            + "fabricated trailing evidence\n",
            encoding="utf-8",
        )
    _reseal_lane(tmp_path, first)
    result = _reconcile_fixture(fixture)
    assert result["counts"]["attempt_evidence_validated"] == 5
    assert result["aggregate_result"] == "Not Supported"


def test_supported_binds_rotation_to_runner_event_receipt(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    first = fixture["rows"][0]
    assert isinstance(first, dict)
    lane_root = tmp_path / R4_ARTIFACT_ROOT / LANE_IDS[0]
    event_path = lane_root / "artifacts/system-event-0/event.json"
    event = json.loads(event_path.read_text(encoding="utf-8"))
    event["evidence"]["user_rotation"] = "0"
    _write_json(event_path, event)
    _reseal_lane(tmp_path, first)
    result = _reconcile_fixture(fixture)
    assert result["counts"]["attempt_evidence_validated"] == 5
    assert result["aggregate_result"] == "Not Supported"


@pytest.mark.parametrize(
    "field",
    (
        "android_bin",
        "adb_bin",
        "codex_bin",
        "allow_host_project_subdir",
    ),
)
def test_supported_rejects_incomplete_formal_admission_options(
    tmp_path: Path,
    field: str,
) -> None:
    fixture = _formal_fixture(tmp_path)
    row = fixture["rows"][0]
    assert isinstance(row, dict)
    admission_path = (
        tmp_path
        / R4_ARTIFACT_ROOT
        / LANE_IDS[0]
        / "production-seam-admission.json"
    )
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    del admission["runner_policy"]["options"][field]
    _write_json(admission_path, admission)
    _reseal_lane(tmp_path, row)
    result = _reconcile_fixture(fixture)
    assert result["counts"]["attempt_evidence_validated"] == 5
    assert result["aggregate_result"] == "Not Supported"


def test_supported_rejects_semantically_empty_execution_provenance(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    row = fixture["rows"][0]
    assert isinstance(row, dict)
    lane_root = tmp_path / R4_ARTIFACT_ROOT / LANE_IDS[0]
    provenance_path = lane_root / "execution-provenance.json"
    _write_json(provenance_path, {})
    record_path = lane_root / "execution-record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["evidence_refs"]["execution_provenance"]["sha256"] = (
        sha256_bytes(provenance_path.read_bytes())
    )
    _write_json(record_path, record)
    _reseal_lane(tmp_path, row)
    result = _reconcile_fixture(fixture)
    assert result["counts"]["attempt_evidence_validated"] == 5
    assert result["aggregate_result"] == "Not Supported"


def test_supported_rejects_execution_time_apk_identity_drift(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    row = fixture["rows"][0]
    assert isinstance(row, dict)
    lane_root = tmp_path / R4_ARTIFACT_ROOT / LANE_IDS[0]
    provenance_path = lane_root / "execution-provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    drifted_sha256 = "0" * 64
    provenance["apk"]["artifacts"][0]["sha256"] = drifted_sha256
    provenance["deployment"]["installed_artifacts"][0][
        "sha256"
    ] = drifted_sha256

    for key in ("apk", "deployment"):
        identity = provenance[key]
        identity["identity_sha256"] = sha256_bytes(
            canonical_json_bytes(
                {
                    name: value
                    for name, value in identity.items()
                    if name != "identity_sha256"
                }
            )
        )
    _write_json(provenance_path, provenance)
    record_path = lane_root / "execution-record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["evidence_refs"]["execution_provenance"]["sha256"] = (
        sha256_bytes(provenance_path.read_bytes())
    )
    _write_json(record_path, record)
    _reseal_lane(tmp_path, row)

    result = _reconcile_fixture(fixture)
    assert result["counts"]["attempt_evidence_validated"] == 5
    assert result["aggregate_result"] == "Not Supported"


def test_supported_rejects_role_or_expected_result_in_review_input(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    row = fixture["rows"][0]
    assert isinstance(row, dict)
    lane_root = tmp_path / R4_ARTIFACT_ROOT / LANE_IDS[0]
    finding_path = lane_root / "finding.json"
    finding = json.loads(finding_path.read_text(encoding="utf-8"))
    finding["rationale"] = (
        "Auditor gold role: control; expected result: locally_rejected."
    )
    _write_json(finding_path, finding)
    risk_map_path = lane_root / "project-risk-map.json"
    risk_map = json.loads(risk_map_path.read_text(encoding="utf-8"))
    risk_map["findings"] = [finding]
    _write_json(risk_map_path, risk_map)
    _reseal_lane(tmp_path, row)
    result = _reconcile_fixture(fixture)
    assert result["counts"]["attempt_evidence_validated"] == 5
    assert result["aggregate_result"] == "Not Supported"


def test_supported_rejects_unallowlisted_review_workspace_file(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    row = fixture["rows"][0]
    assert isinstance(row, dict)
    extra = (
        tmp_path
        / R4_ARTIFACT_ROOT
        / LANE_IDS[0]
        / "review-input"
        / "extra.json"
    )
    _write_json(extra, {"unexpected": "material"})
    _reseal_lane(tmp_path, row, refresh_review_inputs=False)
    result = _reconcile_fixture(fixture)
    assert result["counts"]["attempt_evidence_validated"] == 5
    assert result["aggregate_result"] == "Not Supported"


def test_supported_rejects_challenged_structured_review_after_reseal(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    row = fixture["rows"][0]
    assert isinstance(row, dict)
    output_path = (
        tmp_path
        / R4_ARTIFACT_ROOT
        / LANE_IDS[0]
        / "falsification-review-output.json"
    )
    output = json.loads(output_path.read_text(encoding="utf-8"))
    output["outcome"] = "challenged"
    output["dimensions"][0]["status"] = "challenged"
    output["reasons"] = ["An alternative explanation survives."]
    _write_json(output_path, output)
    _reseal_lane(tmp_path, row)
    challenged_receipt = build_falsification_review_receipt(
        lane_id=LANE_IDS[0],
        repository_root=tmp_path,
        production_invocation_id=str(row["production_invocation_id"]),
        production_identity_sha256=str(
            row["production_identity_sha256"]
        ),
    )
    assert challenged_receipt["outcome"] == "challenged"
    result = _reconcile_fixture(fixture)
    assert result["counts"]["attempt_evidence_validated"] == 5
    assert result["aggregate_result"] == "Not Supported"


def test_supported_rejects_runner_metadata_in_semantic_review_output(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    row = fixture["rows"][0]
    assert isinstance(row, dict)
    output_path = (
        tmp_path
        / R4_ARTIFACT_ROOT
        / LANE_IDS[0]
        / "falsification-review-output.json"
    )
    output = json.loads(output_path.read_text(encoding="utf-8"))
    output["invocation_id"] = "model-invented-runtime-id"
    _write_json(output_path, output)
    _reseal_lane(tmp_path, row)
    result = _reconcile_fixture(fixture)
    assert result["counts"]["attempt_evidence_validated"] == 5
    assert result["aggregate_result"] == "Not Supported"


def test_supported_rejects_semantically_empty_residual_risk(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    row = fixture["rows"][0]
    assert isinstance(row, dict)
    _write_json(
        tmp_path / R4_ARTIFACT_ROOT / LANE_IDS[0] / "residual-risk.json",
        {},
    )
    _reseal_lane(tmp_path, row)
    result = _reconcile_fixture(fixture)
    assert result["aggregate_result"] == "Not Supported"
    assert result["counts"]["attempt_evidence_validated"] == 5


def test_supported_requires_authoritative_review_identity_event(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    row = fixture["rows"][0]
    assert isinstance(row, dict)
    identity_path = (
        tmp_path
        / R4_ARTIFACT_ROOT
        / LANE_IDS[0]
        / "falsification-review-identity.json"
    )
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["command"]["argv_without_prompt"].extend(
        ["--model", "forbidden-explicit-model"]
    )
    _write_json(identity_path, identity)
    _reseal_lane(tmp_path, row)
    result = _reconcile_fixture(fixture)
    assert result["aggregate_result"] == "Not Supported"
    assert result["counts"]["attempt_evidence_validated"] == 5


@pytest.mark.parametrize(
    "override",
    (
        ["-c", 'model="forbidden-model"'],
        ["--config=model=forbidden-model"],
        ["-cmodel=forbidden-model"],
        ["-c=model=forbidden-model"],
    ),
)
def test_supported_rejects_review_config_model_override(
    tmp_path: Path,
    override: list[str],
) -> None:
    fixture = _formal_fixture(tmp_path)
    row = fixture["rows"][0]
    assert isinstance(row, dict)
    identity_path = (
        tmp_path
        / R4_ARTIFACT_ROOT
        / LANE_IDS[0]
        / "falsification-review-identity.json"
    )
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["command"]["argv_without_prompt"].extend(override)
    identity["effective_model"] = "forbidden-model"
    observation = identity["source_observation"]
    observation["turn_context"]["model"] = "forbidden-model"
    identity["effective_model_source"]["observation_sha256"] = sha256_bytes(
        json.dumps(
            observation,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    _write_json(identity_path, identity)
    review = row["falsification_review"]
    assert isinstance(review, dict)
    review["effective_model"] = "forbidden-model"
    _reseal_lane(tmp_path, row)
    result = _reconcile_fixture(fixture)
    assert result["counts"]["attempt_evidence_validated"] == 5
    assert result["aggregate_result"] == "Not Supported"


def test_supported_rejects_resumed_production_session_as_review(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    row = fixture["rows"][0]
    assert isinstance(row, dict)
    production_thread, _ = str(
        row["production_invocation_id"]
    ).split(":", 1)
    review_turn = "resumed-review-turn"
    identity_path = (
        tmp_path
        / R4_ARTIFACT_ROOT
        / LANE_IDS[0]
        / "falsification-review-identity.json"
    )
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["effective_model_source"]["thread_id"] = production_thread
    identity["effective_model_source"]["turn_id"] = review_turn
    observation = identity["source_observation"]
    observation["session_meta"]["id"] = production_thread
    observation["turn_context"]["turn_id"] = review_turn
    identity["effective_model_source"]["observation_sha256"] = sha256_bytes(
        json.dumps(
            observation,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    identity["command"]["argv_without_prompt"].extend(
        ["resume", production_thread]
    )
    _write_json(identity_path, identity)
    review = row["falsification_review"]
    assert isinstance(review, dict)
    review["invocation_id"] = f"{production_thread}:{review_turn}"
    _reseal_lane(tmp_path, row)
    result = _reconcile_fixture(fixture)
    assert result["counts"]["attempt_evidence_validated"] == 5
    assert result["aggregate_result"] == "Not Supported"


def test_supported_rejects_review_command_with_extra_directory(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    row = fixture["rows"][0]
    assert isinstance(row, dict)
    identity_path = (
        tmp_path
        / R4_ARTIFACT_ROOT
        / LANE_IDS[0]
        / "falsification-review-identity.json"
    )
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["command"]["argv_without_prompt"].extend(
        ["--add-dir", str(tmp_path)]
    )
    _write_json(identity_path, identity)
    _reseal_lane(tmp_path, row)
    result = _reconcile_fixture(fixture)
    assert result["counts"]["attempt_evidence_validated"] == 5
    assert result["aggregate_result"] == "Not Supported"


def test_supported_rejects_reused_production_thread_with_new_review_turn(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    row = fixture["rows"][0]
    assert isinstance(row, dict)
    production_thread, _ = str(
        row["production_invocation_id"]
    ).split(":", 1)
    review_turn = "fresh-looking-review-turn"
    identity_path = (
        tmp_path
        / R4_ARTIFACT_ROOT
        / LANE_IDS[0]
        / "falsification-review-identity.json"
    )
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["effective_model_source"]["thread_id"] = production_thread
    identity["effective_model_source"]["turn_id"] = review_turn
    observation = identity["source_observation"]
    observation["session_meta"]["id"] = production_thread
    observation["turn_context"]["turn_id"] = review_turn
    identity["effective_model_source"]["observation_sha256"] = sha256_bytes(
        json.dumps(
            observation,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    _write_json(identity_path, identity)
    review = row["falsification_review"]
    assert isinstance(review, dict)
    review["invocation_id"] = f"{production_thread}:{review_turn}"
    _reseal_lane(tmp_path, row)
    result = _reconcile_fixture(fixture)
    assert result["counts"]["attempt_evidence_validated"] == 6
    assert result["counts"]["review_production_identities_disjoint"] is False
    assert result["aggregate_result"] == "Not Supported"


def test_supported_requires_review_and_all_production_identities_disjoint(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    rows = fixture["rows"]
    assert isinstance(rows, list)
    for index, row in enumerate(rows):
        assert isinstance(row, dict)
        next_row = rows[(index + 1) % len(rows)]
        assert isinstance(next_row, dict)
        production_invocation_id = str(
            next_row["production_invocation_id"]
        )
        thread_id, turn_id = production_invocation_id.split(":", 1)
        identity_path = (
            tmp_path
            / R4_ARTIFACT_ROOT
            / str(row["lane_id"])
            / "falsification-review-identity.json"
        )
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
        identity["effective_model_source"]["thread_id"] = thread_id
        identity["effective_model_source"]["turn_id"] = turn_id
        observation = identity["source_observation"]
        observation["session_meta"]["id"] = thread_id
        observation["turn_context"]["turn_id"] = turn_id
        identity["effective_model_source"]["observation_sha256"] = (
            sha256_bytes(
                json.dumps(
                    observation,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
        )
        _write_json(identity_path, identity)
        review = row["falsification_review"]
        assert isinstance(review, dict)
        review["invocation_id"] = production_invocation_id
        _reseal_lane(tmp_path, row)
    result = _reconcile_fixture(fixture)
    assert result["counts"]["attempt_evidence_validated"] == 6
    assert result["counts"]["falsification_review_survived"] == 6
    assert result["counts"]["review_identities_unique"] is True
    assert result["counts"]["review_production_identities_disjoint"] is False
    assert result["aggregate_result"] == "Not Supported"


def test_supported_rejects_uninventoried_second_execution_record(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    row = fixture["rows"][0]
    assert isinstance(row, dict)
    lane_root = tmp_path / R4_ARTIFACT_ROOT / LANE_IDS[0]
    record = json.loads(
        (lane_root / "execution-record.json").read_text(encoding="utf-8")
    )
    record["attempt_id"] = "runner-attempt-uninventoried-retry"
    _write_json(lane_root / "retry/execution-record.json", record)
    _reseal_lane(tmp_path, row)
    result = _reconcile_fixture(fixture)
    assert result["counts"]["attempt_evidence_validated"] == 6
    assert result["counts"]["execution_record_count"] == 7
    assert result["counts"]["execution_records_exhaustive"] is False
    assert result["aggregate_result"] == "Not Supported"


def test_supported_rejects_execution_record_with_backup_suffix(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    row = fixture["rows"][0]
    assert isinstance(row, dict)
    lane_root = tmp_path / R4_ARTIFACT_ROOT / LANE_IDS[0]
    record = json.loads(
        (lane_root / "execution-record.json").read_text(encoding="utf-8")
    )
    record["attempt_id"] = "runner-attempt-hidden-backup"
    _write_json(
        lane_root / "hidden-retry/execution-record.json.bak",
        record,
    )
    _reseal_lane(tmp_path, row)
    result = _reconcile_fixture(fixture)
    assert result["counts"]["attempt_evidence_validated"] == 6
    assert result["counts"]["execution_record_count"] == 7
    assert result["counts"]["execution_records_exhaustive"] is False
    assert result["aggregate_result"] == "Not Supported"


def test_supported_rejects_duplicate_or_unbound_review_identity(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    duplicate = copy.deepcopy(fixture["rows"])
    duplicate[1]["falsification_review"]["invocation_id"] = duplicate[0][
        "falsification_review"
    ]["invocation_id"]
    assert (
        reconcile_formal_rows(
            duplicate,
            fixture["contradiction"],
            auditor_mapping=fixture["mapping"],
            expected_mapping_commitment_sha256=fixture[
                "mapping_commitment"
            ],
            expected_contradiction_audit_sha256=fixture[
                "contradiction_commitment"
            ],
            formal_attempt_inventory=fixture["attempt_inventory"],
            formal_attempt_inventory_receipt=fixture[
                "attempt_inventory_receipt"
            ],
            evidence_repository_root=fixture["evidence_repository_root"],
        )["aggregate_result"]
        == "Not Supported"
    )

    unblinded = copy.deepcopy(fixture["rows"])
    unblinded[0]["falsification_review"]["source_role_disclosed"] = True
    assert (
        reconcile_formal_rows(
            unblinded,
            fixture["contradiction"],
            auditor_mapping=fixture["mapping"],
            expected_mapping_commitment_sha256=fixture[
                "mapping_commitment"
            ],
            expected_contradiction_audit_sha256=fixture[
                "contradiction_commitment"
            ],
            formal_attempt_inventory=fixture["attempt_inventory"],
            formal_attempt_inventory_receipt=fixture[
                "attempt_inventory_receipt"
            ],
            evidence_repository_root=fixture["evidence_repository_root"],
        )["aggregate_result"]
        == "Not Supported"
    )

    reused_production = copy.deepcopy(fixture["rows"])
    reused_production[0]["falsification_review"]["invocation_id"] = (
        reused_production[0]["production_invocation_id"]
    )
    reused_production[0]["falsification_review"]["identity_sha256"] = (
        reused_production[0]["production_identity_sha256"]
    )
    assert (
        reconcile_formal_rows(
            reused_production,
            fixture["contradiction"],
            auditor_mapping=fixture["mapping"],
            expected_mapping_commitment_sha256=fixture[
                "mapping_commitment"
            ],
            expected_contradiction_audit_sha256=fixture[
                "contradiction_commitment"
            ],
            formal_attempt_inventory=fixture["attempt_inventory"],
            formal_attempt_inventory_receipt=fixture[
                "attempt_inventory_receipt"
            ],
            evidence_repository_root=fixture["evidence_repository_root"],
        )["aggregate_result"]
        == "Not Supported"
    )


def test_supported_rejects_retry_or_unbound_contradiction(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    retried = copy.deepcopy(fixture["rows"])
    retried[0]["lane_attempt_count"] = 2
    retried[0]["retry_count"] = 1
    inventory = copy.deepcopy(fixture["attempt_inventory"])
    inventory[0]["retry_count"] = 1
    assert (
        reconcile_formal_rows(
            retried,
            fixture["contradiction"],
            auditor_mapping=fixture["mapping"],
            expected_mapping_commitment_sha256=fixture[
                "mapping_commitment"
            ],
            expected_contradiction_audit_sha256=fixture[
                "contradiction_commitment"
            ],
            formal_attempt_inventory=inventory,
            formal_attempt_inventory_receipt=fixture[
                "attempt_inventory_receipt"
            ],
            evidence_repository_root=fixture["evidence_repository_root"],
        )["aggregate_result"]
        == "Not Supported"
    )

    minimal_contradiction = {
        "status": "pass",
        "pre_side_effect_rejection": True,
    }
    assert (
        reconcile_formal_rows(
            fixture["rows"],
            minimal_contradiction,
            auditor_mapping=fixture["mapping"],
            expected_mapping_commitment_sha256=fixture[
                "mapping_commitment"
            ],
            expected_contradiction_audit_sha256=sha256_bytes(
                canonical_json_bytes(minimal_contradiction)
            ),
            formal_attempt_inventory=fixture["attempt_inventory"],
            formal_attempt_inventory_receipt=fixture[
                "attempt_inventory_receipt"
            ],
            evidence_repository_root=fixture["evidence_repository_root"],
        )["aggregate_result"]
        == "Not Supported"
    )


def test_supported_rejects_missing_or_tampered_attempt_evidence_ref(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    missing = copy.deepcopy(fixture["rows"])
    del missing[0]["attempt_evidence"]["refs"]["finding"]["sha256"]
    assert (
        reconcile_formal_rows(
            missing,
            fixture["contradiction"],
            auditor_mapping=fixture["mapping"],
            expected_mapping_commitment_sha256=fixture[
                "mapping_commitment"
            ],
            expected_contradiction_audit_sha256=fixture[
                "contradiction_commitment"
            ],
            formal_attempt_inventory=fixture["attempt_inventory"],
            formal_attempt_inventory_receipt=fixture[
                "attempt_inventory_receipt"
            ],
            evidence_repository_root=fixture["evidence_repository_root"],
        )["aggregate_result"]
        == "Not Supported"
    )

    tampered = copy.deepcopy(fixture["rows"])
    tampered[0]["attempt_evidence"]["refs"]["finding"]["sha256"] = "0" * 64
    tampered[0]["attempt_evidence"]["evidence_refs_sha256"] = sha256_bytes(
        canonical_json_bytes(tampered[0]["attempt_evidence"]["refs"])
    )
    validation_path = (
        tmp_path / tampered[0]["attempt_evidence_receipt"]["path"]
    )
    validation_path.write_text(
        json.dumps(
            tampered[0]["attempt_evidence"],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    tampered[0]["attempt_evidence_receipt"]["sha256"] = sha256_bytes(
        validation_path.read_bytes()
    )
    assert (
        reconcile_formal_rows(
            tampered,
            fixture["contradiction"],
            auditor_mapping=fixture["mapping"],
            expected_mapping_commitment_sha256=fixture[
                "mapping_commitment"
            ],
            expected_contradiction_audit_sha256=fixture[
                "contradiction_commitment"
            ],
            formal_attempt_inventory=fixture["attempt_inventory"],
            formal_attempt_inventory_receipt=fixture[
                "attempt_inventory_receipt"
            ],
            evidence_repository_root=fixture["evidence_repository_root"],
        )["aggregate_result"]
        == "Not Supported"
    )


def test_reconciliation_rejects_population_or_order_changes(
    tmp_path: Path,
) -> None:
    fixture = _formal_fixture(tmp_path)
    mapping = fixture["mapping"]
    mapping_commitment = fixture["mapping_commitment"]
    rows = fixture["rows"]
    with pytest.raises(M9RecoveryQualificationError, match="lane order"):
        reconcile_formal_rows(
            list(reversed(rows)),
            fixture["contradiction"],
            auditor_mapping=mapping,
            expected_mapping_commitment_sha256=mapping_commitment,
            expected_contradiction_audit_sha256=fixture[
                "contradiction_commitment"
            ],
            formal_attempt_inventory=fixture["attempt_inventory"],
            formal_attempt_inventory_receipt=fixture[
                "attempt_inventory_receipt"
            ],
            evidence_repository_root=fixture["evidence_repository_root"],
        )

    relabeled = copy.deepcopy(rows)
    relabeled[0]["role"], relabeled[1]["role"] = (
        relabeled[1]["role"],
        relabeled[0]["role"],
    )
    with pytest.raises(
        M9RecoveryQualificationError,
        match="committed mapping",
    ):
        reconcile_formal_rows(
            relabeled,
            fixture["contradiction"],
            auditor_mapping=mapping,
            expected_mapping_commitment_sha256=mapping_commitment,
            expected_contradiction_audit_sha256=fixture[
                "contradiction_commitment"
            ],
            formal_attempt_inventory=fixture["attempt_inventory"],
            formal_attempt_inventory_receipt=fixture[
                "attempt_inventory_receipt"
            ],
            evidence_repository_root=fixture["evidence_repository_root"],
        )

    with pytest.raises(
        M9RecoveryQualificationError,
        match="frozen commitment",
    ):
        reconcile_formal_rows(
            rows,
            fixture["contradiction"],
            auditor_mapping=mapping,
            expected_mapping_commitment_sha256="0" * 64,
            expected_contradiction_audit_sha256=fixture[
                "contradiction_commitment"
            ],
            formal_attempt_inventory=fixture["attempt_inventory"],
            formal_attempt_inventory_receipt=fixture[
                "attempt_inventory_receipt"
            ],
            evidence_repository_root=fixture["evidence_repository_root"],
        )

    with pytest.raises(
        M9RecoveryQualificationError,
        match="raw bytes",
    ):
        load_auditor_mapping(
            MAPPING,
            expected_raw_sha256="0" * 64,
            expected_canonical_sha256=mapping_commitment,
        )


def test_auditor_mapping_rejects_an_unbalanced_existing_population(
    tmp_path: Path,
) -> None:
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    for assignment in mapping["assignments"]:
        assignment["role"] = "defect"
    path = tmp_path / "unbalanced-mapping.json"
    raw = (json.dumps(mapping, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    with pytest.raises(
        M9RecoveryQualificationError,
        match="blocked 3\\+3 design",
    ):
        load_auditor_mapping(
            path,
            expected_raw_sha256=sha256_bytes(raw),
            expected_canonical_sha256=sha256_bytes(
                canonical_json_bytes(mapping)
            ),
        )


def test_manifest_packet_commitment_detects_target_tampering(
    tmp_path: Path,
) -> None:
    if not MANIFEST.exists():
        pytest.skip("R3 generator has not materialized the candidate manifest")
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    document["target"]["package"] = "com.example.drift"
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(M9RecoveryQualificationError):
        load_manifest(tampered)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("pre_invocation_production_binding_required", False),
        ("terminal_failure_receipt_required", False),
        ("terminal_failure_receipt_schema_version", 1),
        ("terminal_failure_receipt_lane_ledger_required", False),
        ("terminal_failure_stages", ["process_exit"]),
    ),
)
def test_manifest_rejects_weakened_review_failure_contract_after_recommit(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    document["falsification_review"][field] = value
    document["packet_commitment"]["sha256"] = freeze_payload_sha256(document)
    tampered = tmp_path / f"weakened-review-{field}.json"
    tampered.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(
        M9RecoveryQualificationError,
        match="Falsification Review identity/blinding policy drifted",
    ):
        load_manifest(tampered)


@pytest.mark.parametrize(
    "field",
    [
        "context_acquisition",
        "portfolio",
        "attack_plan",
        "oracle",
        "evidence",
        "exploration_stop_rule",
        "admission",
        "contradiction_packet",
        "leakage_audit",
    ],
)
def test_manifest_rejects_deleted_approval_bound_section_after_recommit(
    field: str,
    tmp_path: Path,
) -> None:
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    document.pop(field)
    document["packet_commitment"]["sha256"] = freeze_payload_sha256(document)
    tampered = tmp_path / f"missing-{field}.json"
    tampered.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(
        M9RecoveryQualificationError,
        match=f"approval-bound {field}",
    ):
        load_manifest(tampered)


def test_frozen_manifest_cannot_regenerate_candidate_or_ledger(
    tmp_path: Path,
) -> None:
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    document["status"] = "frozen"
    document["frozen_at"] = "2026-08-07T12:00:00+00:00"
    document["approval"] = {
        **document["approval"],
        "status": "approved",
        "approved_by": "human-reviewer",
        "approved_at": "2026-08-07T12:00:00+00:00",
        "comment_url": "https://github.com/yangliang2/ai_verification/issues/152#issuecomment-1",
    }
    frozen = tmp_path / "frozen.json"
    frozen.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(
        M9RecoveryQualificationError,
        match="immutable",
    ):
        ensure_candidate_regeneration_allowed(frozen)
    with pytest.raises(
        M9RecoveryQualificationError,
        match="immutable",
    ):
        ensure_evidence_ledger_regeneration_allowed(frozen)


def test_frozen_manifest_requires_auditable_human_approval(
    tmp_path: Path,
) -> None:
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    document["status"] = "frozen"
    document["frozen_at"] = "not-a-timestamp"
    document["approval"] = {
        **document["approval"],
        "status": "approved",
        "approved_by": " ",
        "approved_at": "not-a-timestamp",
        "comment_url": "x",
    }
    frozen = tmp_path / "forged-approval.json"
    frozen.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(
        M9RecoveryQualificationError,
        match="auditable human approval",
    ):
        load_manifest(frozen, require_frozen=True)
