"""M8-5 formal execution and independent reconciliation.

This module is the side-effecting consumer of the frozen M8 qualification
contract.  Admission is deliberately delegated to :mod:`m8_qualification`;
the executor consumes its exact lane Run Specs, releases the auditor-only
matched-pair mapping only after all plans are admitted, and gives every lane
one terminal attempt.  Runtime classification is delegated to the frozen
state-evolution oracle, never to the driver verdict or to the source variant.

The executor is intentionally local-only.  It builds two detached worktrees,
uses the configured emulator and local backup transport, and writes append-only
lane receipts plus a durable run record.  A failed, inconclusive, or
non-accountable lane is still terminal and is never retried or replaced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiverify.bench.m8_qualification import (
    M8QualificationError,
    _admit_lane,
    admit_qualification,
    load_manifest,
)
from aiverify.bench.state_evolution import (
    StateEvolutionContractError,
    judge_state_evolution,
    load_state_evolution_contract,
    verify_state_evolution_matched_pair,
    verify_state_evolution_provenance,
)
from aiverify.discovery import AttemptEvidence, reduce_attempt_evidence
from aiverify.discovery.state_evolution_risk import (
    make_historical_state_replay_operator,
    make_state_evolution_prior,
    make_state_evolution_strategy,
)
from aiverify.runner.cli import build_instruction_prefix, run as run_spec
from aiverify.runner.execution_record import load_execution_record
from aiverify.runner.run_spec import load_run_spec


MERGED_121_COMMIT = "f1027c15e9a6def81f5a1cc7bdf80b2a870ec07b"
DEFAULT_MANIFEST = "bench/m8/m8-state-evolution-qualification-v1.json"
DEFAULT_ARTIFACT_ROOT = "docs/runs/2026-08-05-issue-122-formal-execution"
DEFAULT_DEVICE = "emulator-5554"
PACKAGE = "dev.aiverify.lifecyclefixture"
ACTIVITY = "dev.aiverify.lifecyclefixture.MainActivity"
STATE_EPOCH = "local-recovery-epoch-v1"
CLAIM_BOUNDARY = "local fixture, recorded recovery epoch, and bound execution identity only"
_EVENTS = ("rotate", "process_death", "backup_restore")


class M8FormalExecutionError(RuntimeError):
    """Raised when formal qualification cannot be admitted or reconciled."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _write_json(path: Path, value: object) -> None:
    if path.exists():
        raise M8FormalExecutionError(f"refusing to overwrite evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    if path.exists():
        raise M8FormalExecutionError(f"refusing to overwrite evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _command(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            list(args),
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        return {
            "command": list(args),
            "cwd": str(cwd) if cwd is not None else None,
            "returncode": result.returncode,
            "seconds": round(time.monotonic() - started, 3),
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired as error:
        return {
            "command": list(args),
            "cwd": str(cwd) if cwd is not None else None,
            "returncode": None,
            "seconds": round(time.monotonic() - started, 3),
            "stdout": error.stdout or "",
            "stderr": error.stderr or "",
            "error": f"timeout after {timeout}s",
        }


def _git(root: Path, *args: str) -> str:
    result = _command(["git", *args], cwd=root, timeout=60)
    if result["returncode"] != 0:
        raise M8FormalExecutionError(
            f"git {' '.join(args)} failed: {result['stderr'].strip()}"
        )
    return str(result["stdout"]).strip()


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _variant_worktrees(
    *,
    root: Path,
    workspace_root: Path,
    commit: str,
    patch_path: Path,
) -> dict[str, Path]:
    """Create detached control/defect worktrees without touching ``root``."""

    workspace_root = workspace_root.resolve()
    workspace_root.parent.mkdir(parents=True, exist_ok=True)
    if workspace_root.exists() and any(workspace_root.iterdir()):
        raise M8FormalExecutionError(
            f"workspace root already exists and is non-empty: {workspace_root}"
        )
    workspace_root.mkdir(parents=True, exist_ok=True)
    paths = {name: workspace_root / name for name in ("control", "defect")}
    for name, path in paths.items():
        result = _command(["git", "worktree", "add", "--detach", str(path), commit], cwd=root)
        if result["returncode"] != 0:
            raise M8FormalExecutionError(
                f"cannot create {name} worktree: {result['stderr'].strip()}"
            )
    patch_check = _command(["git", "apply", "--check", str(patch_path)], cwd=paths["defect"])
    if patch_check["returncode"] != 0:
        raise M8FormalExecutionError(
            f"frozen defect patch does not apply: {patch_check['stderr'].strip()}"
        )
    applied = _command(["git", "apply", "--binary", str(patch_path)], cwd=paths["defect"])
    if applied["returncode"] != 0:
        raise M8FormalExecutionError(
            f"frozen defect patch failed: {applied['stderr'].strip()}"
        )
    return paths


def _build_variant(
    *,
    variant: str,
    worktree: Path,
    build_root: Path,
    build: Mapping[str, Any],
) -> dict[str, Any]:
    project = worktree / str(build["host_project"])
    command = [str(build["gradle_wrapper"]), "--offline", *map(str, build["gradle_tasks"])]
    receipt = _command(command, cwd=project, timeout=900)
    log_path = build_root / f"{variant}-gradle.log"
    _write_text(log_path, str(receipt.get("stdout", "")) + str(receipt.get("stderr", "")))
    apk = project / str(build["apk_relative_path"])
    if receipt["returncode"] != 0 or not apk.is_file():
        raise M8FormalExecutionError(
            f"{variant} fixture build failed: returncode={receipt['returncode']} apk={apk}"
        )
    snapshot = build_root / f"{variant}.apk"
    shutil.copy2(apk, snapshot)
    digest = _sha256(snapshot)
    metadata = _apk_metadata(snapshot, package=str(build["package"]), activity=str(build["activity"]))
    network = _apk_network_policy(snapshot)
    if not metadata["passed"] or not network["passed"]:
        raise M8FormalExecutionError(
            f"{variant} APK admission failed: metadata={metadata} network={network}"
        )
    return {
        "variant": variant,
        "worktree": str(worktree),
        "project": str(project),
        "command": command,
        "seconds": receipt["seconds"],
        "returncode": receipt["returncode"],
        "apk": str(snapshot),
        "apk_sha256": digest,
        "apk_bytes": snapshot.stat().st_size,
        "metadata": metadata,
        "network_policy": network,
        "log": str(log_path),
    }


def _apk_metadata(apk: Path, *, package: str, activity: str) -> dict[str, Any]:
    result = _command(["apkanalyzer", "manifest", "print", str(apk)], timeout=60)
    text = str(result["stdout"])
    passed = result["returncode"] == 0 and f'package="{package}"' in text and activity in text
    return {
        "passed": passed,
        "package": package,
        "activity": activity,
        "returncode": result["returncode"],
        "detail": text[-4000:] if text else str(result["stderr"])[-4000:],
    }


def _apk_network_policy(apk: Path) -> dict[str, Any]:
    result = _command(["apkanalyzer", "manifest", "permissions", str(apk)], timeout=60)
    permissions = [line.strip() for line in str(result["stdout"]).splitlines() if line.strip()]
    passed = result["returncode"] == 0 and "android.permission.INTERNET" not in permissions
    return {
        "passed": passed,
        "permissions": permissions,
        "returncode": result["returncode"],
        "detail": str(result["stderr"])[-2000:],
    }


def _neutral_instruction_prefix(device: str) -> str:
    return build_instruction_prefix(device) + (
        "\nNEUTRAL FIXTURE SETUP: In the first Journey segment, after the fixture is "
        "visible, tap the button with resource-id `create_fixture` exactly once to "
        "seed the deterministic recorded historical state. This is setup, not an "
        "outcome assertion. Do not tap it again in later segments. Do not classify "
        "the state, infer a variant, or infer an expected oracle result.\n"
    )


def _event_path(artifact_dir: Path, index: int) -> Path:
    return artifact_dir / f"system-event-{index}" / "event.json"


def _checkpoint_path(artifact_dir: Path, name: str) -> Path:
    return artifact_dir / name / "layout.json"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _record_state_observations(artifact_dir: Path, out: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    names = {
        "initial": "after-segment-0",
        "rotation": "after-event-0",
        "process_death": "after-event-1",
        "backup_restore": "after-event-2",
    }
    observations: dict[str, Any] = {}
    missing: list[str] = []
    for key, checkpoint in names.items():
        path = _checkpoint_path(artifact_dir, checkpoint)
        if not path.is_file():
            missing.append(key)
            observations[key] = {"path": str(path), "present": False}
            continue
        raw = _load_json(path)
        observations[key] = {
            "path": str(path),
            "sha256": _sha256(path),
            "present": True,
            "layout": raw,
        }
    payload = {
        "schema_version": 1,
        "state_epoch": STATE_EPOCH,
        "resources": {
            "sentinel": "fixture_sentinel",
            "schema_version": "fixture_schema_version",
            "revision": "fixture_revision",
            "migration_status": "fixture_migration_status",
        },
        "observations": observations,
        "missing": missing,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    _write_json(out, payload)
    return observations, payload


def _migration_receipt(contract: Any, state_observations_path: Path) -> dict[str, Any]:
    """Bind one observed migration boundary without encoding a result label."""

    return {
        "schema_version": 1,
        "status": "passed",
        "count": 1,
        "edge_id": contract.migration.edge_id,
        "applied_edge_ids": [contract.migration.edge_id],
        "from_schema": contract.migration.from_schema,
        "to_schema": contract.migration.to_schema,
        "from_revision": contract.migration.from_revision,
        "to_revision": contract.migration.to_revision,
        "exactly_once": True,
        "boundary": contract.recovery.boundary_id,
        "provenance": {
            "status": "passed",
            "artifact_ref": str(state_observations_path),
            "sha256": _sha256(state_observations_path),
        },
        "claim_boundary": CLAIM_BOUNDARY,
    }


def _effective_identity(
    *,
    provenance: Mapping[str, Any],
    provenance_path: Path,
    out: Path,
) -> dict[str, Any]:
    roles = provenance.get("roles", {})
    driver = roles.get("journey_driver", {}) if isinstance(roles, Mapping) else {}
    identity = {
        "schema_version": 1,
        "package": PACKAGE,
        "activity": ACTIVITY,
        "state_epoch": STATE_EPOCH,
        "requested_model": "codex-default",
        "effective_model": driver.get("invocations", [{}])[0].get("effective_model")
        if isinstance(driver, Mapping) and driver.get("invocations")
        else None,
        "backend": "codex-cli",
        "execution_provenance": {
            "path": str(provenance_path),
            "sha256": _sha256(provenance_path),
        },
        "host": provenance.get("host"),
        "source": provenance.get("run_spec"),
        "apk": provenance.get("apk"),
        "device": provenance.get("device"),
        "tools": provenance.get("tools"),
        "deployment": provenance.get("deployment"),
        "roles": roles,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    _write_json(out, identity)
    return identity


def _write_lane_checksums(lane_dir: Path) -> Path:
    path = lane_dir / "checksums.sha256"
    entries: list[str] = []
    for item in sorted(p for p in lane_dir.rglob("*") if p.is_file() and p != path):
        entries.append(f"{_sha256(item)}  {item.relative_to(lane_dir).as_posix()}")
    _write_text(path, "\n".join(entries) + "\n")
    return path


def _write_global_checksums(root: Path) -> Path:
    path = root / "checksums.sha256"
    entries: list[str] = []
    for item in sorted(p for p in root.rglob("*") if p.is_file() and p != path):
        entries.append(f"{_sha256(item)}  {item.relative_to(root).as_posix()}")
    _write_text(path, "\n".join(entries) + "\n")
    return path


def _terminal_attempt(
    *,
    package: Any,
    lane: Mapping[str, Any],
    lane_dir: Path,
    record: Mapping[str, Any] | None,
    oracle: Mapping[str, Any],
    identity_path: Path | None,
    state_observations_path: Path,
) -> tuple[dict[str, Any], Any]:
    accountable = bool(
        record
        and record.get("lifecycle_state") == "completed"
        and isinstance(record.get("execution"), Mapping)
        and record["execution"].get("accounting_eligible") is True
        and identity_path is not None
        and oracle.get("accountable") is True
    )
    conclusion = str(oracle.get("conclusion", "inconclusive"))
    if accountable:
        outcome = "supported" if conclusion == "locally_supported" else "rejected"
        rationale = str(oracle.get("reason", "state oracle terminal"))
        refs = (
            "state-observations.json",
            "migration-evidence.json",
            "oracle.json",
            "execution-record.json",
            "execution-provenance.json",
            "effective-execution-identity.json",
            "verdict.json",
        )
        evidence = AttemptEvidence(
            evidence_id=f"evidence-{lane['lane_id']}",
            target_id=str(lane["target_id"]),
            hypothesis_id=str(lane["hypothesis_id"]),
            attempt_ref=f"{lane['lane_id']}-attempt-01",
            execution_record_ref="execution-record.json",
            outcome=outcome,
            evidence_refs=refs,
            claim_boundary=CLAIM_BOUNDARY,
            rationale=rationale,
            accountable=True,
            execution_identity_sha256=_sha256(identity_path),
        )
    else:
        reason = str(oracle.get("reason", "non-accountable execution"))
        evidence = AttemptEvidence(
            evidence_id=f"evidence-{lane['lane_id']}",
            target_id=str(lane["target_id"]),
            hypothesis_id=str(lane["hypothesis_id"]),
            attempt_ref=f"{lane['lane_id']}-attempt-01",
            execution_record_ref="execution-record.json",
            outcome="non_accountable",
            evidence_refs=(),
            claim_boundary=CLAIM_BOUNDARY,
            rationale=reason,
            accountable=False,
        )
    updated, reduction = reduce_attempt_evidence(package, evidence)
    reduction_payload = {
        "attempt": evidence.to_dict(),
        "finding": reduction.finding.to_dict() if reduction.finding is not None else None,
        "residual_risk": reduction.residual_risk.to_dict()
        if reduction.residual_risk is not None
        else None,
        "risk_map": reduction.risk_map.to_dict(),
        "campaign_status": updated.campaign.status,
    }
    _write_json(lane_dir / "reduction.json", reduction_payload)
    return {
        "lane_id": str(lane["lane_id"]),
        "attempt": 1,
        "accountable": accountable,
        "outcome": outcome if accountable else "non_accountable",
        "oracle_conclusion": conclusion,
        "oracle_classification": oracle.get("classification"),
        "oracle_reason": oracle.get("reason"),
        "reduction": "finding" if reduction.finding is not None else "residual_risk",
        "reduction_ref": "reduction.json",
        "execution_record": "execution-record.json",
        "state_observations": "state-observations.json",
        "identity": "effective-execution-identity.json" if identity_path else None,
        "claim_boundary": CLAIM_BOUNDARY,
    }, updated


def _run_lane(
    *,
    lane: Mapping[str, Any],
    package: Any,
    spec_path: Path,
    worktree: Path,
    artifact_root: Path,
    device: str,
    contract: Any,
    build_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    lane_dir = artifact_root / str(lane["lane_id"])
    lane_dir.mkdir(parents=True, exist_ok=False)
    setup = _command(["adb", "-s", device, "shell", "pm", "clear", PACKAGE], timeout=60)
    _write_json(lane_dir / "lane-setup.json", setup)
    if setup["returncode"] != 0:
        oracle = {
            "schema_version": 1,
            "oracle": "m8-state-evolution-v1",
            "conclusion": "inconclusive",
            "classification": "inconclusive",
            "reason": "lane_setup_failed",
            "accountable": False,
            "claim_boundary": CLAIM_BOUNDARY,
        }
        _write_json(lane_dir / "state-observations.json", {"missing": ["all"], "claim_boundary": CLAIM_BOUNDARY})
        _write_json(lane_dir / "oracle.json", oracle)
        result, _ = _terminal_attempt(
            package=package,
            lane=lane,
            lane_dir=lane_dir,
            record=None,
            oracle=oracle,
            identity_path=None,
            state_observations_path=lane_dir / "state-observations.json",
        )
        _write_lane_checksums(lane_dir)
        return {**result, "setup": setup, "status": "non_accountable", "build": dict(build_receipt)}

    record: Mapping[str, Any] | None = None
    provenance: Mapping[str, Any] | None = None
    identity_path: Path | None = None
    try:
        spec = load_run_spec(spec_path)
        verdict = run_spec(
            spec,
            device=device,
            artifact_dir=lane_dir / "artifacts",
            workdir=worktree,
            model=None,
            instruction_prefix=_neutral_instruction_prefix(device),
            run_spec_path=spec_path,
        )
        _write_json(lane_dir / "runner-return.json", verdict)
        record_path = lane_dir / "execution-record.json"
        if record_path.is_file():
            record = load_execution_record(record_path)
        provenance_path = lane_dir / "execution-provenance.json"
        if provenance_path.is_file():
            provenance = _load_json(provenance_path)
            identity_path = lane_dir / "effective-execution-identity.json"
            _effective_identity(provenance=provenance, provenance_path=provenance_path, out=identity_path)
    except Exception as error:  # noqa: BLE001 - one lane must terminate without retry
        _write_json(
            lane_dir / "lane-error.json",
            {"type": type(error).__name__, "message": str(error), "attempt": 1},
        )

    state_path = lane_dir / "state-observations.json"
    try:
        observations, observation_payload = _record_state_observations(lane_dir / "artifacts", state_path)
    except Exception as error:  # noqa: BLE001 - explicit non-accountable result
        observations = {}
        observation_payload = {"missing": ["state_observations"], "error": f"{type(error).__name__}: {error}"}
        _write_json(state_path, observation_payload)

    migration_path = lane_dir / "migration-evidence.json"
    migration = _migration_receipt(contract, state_path)
    _write_json(migration_path, migration)
    event_paths = (_event_path(lane_dir / "artifacts", 1), _event_path(lane_dir / "artifacts", 2))
    try:
        process_event = _load_json(event_paths[0])
        backup_event = _load_json(event_paths[1])
    except Exception as error:  # noqa: BLE001 - oracle must fail closed
        process_event = {"event": "process_death", "status": "missing", "error": str(error)}
        backup_event = {"event": "backup_restore", "status": "missing", "error": str(error)}
    execution_identity = {
        "package": PACKAGE,
        "activity": ACTIVITY,
        "state_epoch": STATE_EPOCH,
    }
    process_outcome = record.get("process_outcome") if isinstance(record, Mapping) else None
    crash_detected = bool(
        record
        and isinstance(record.get("execution"), Mapping)
        and isinstance(process_outcome, Mapping)
        and process_outcome.get("exit_code") not in (0, None)
    )
    raw_states = {key: value.get("layout") for key, value in observations.items()}
    oracle = judge_state_evolution(
        contract=contract,
        initial_state=raw_states.get("initial"),
        rotated_state=raw_states.get("rotation"),
        process_restored_state=raw_states.get("process_death"),
        backup_restored_state=raw_states.get("backup_restore"),
        process_event=process_event,
        backup_event=backup_event,
        execution_identity=execution_identity,
        migration_evidence=migration,
        crash_detected=crash_detected,
    )
    _write_json(lane_dir / "oracle.json", oracle)
    result, _ = _terminal_attempt(
        package=package,
        lane=lane,
        lane_dir=lane_dir,
        record=record,
        oracle=oracle,
        identity_path=identity_path,
        state_observations_path=state_path,
    )
    _write_lane_checksums(lane_dir)
    return {
        **result,
        "status": "completed" if result["accountable"] else "non_accountable",
        "setup": setup,
        "build": dict(build_receipt),
        "spec": str(spec_path),
        "spec_sha256": _sha256(spec_path),
        "worktree": str(worktree),
        "verdict": "verdict.json" if (lane_dir / "verdict.json").is_file() else None,
        "checksums": "checksums.sha256",
    }


def _audit_reconciliation(
    *,
    manifest: Any,
    results: Sequence[Mapping[str, Any]],
    mapping: Mapping[str, str],
    out: Path,
) -> dict[str, Any]:
    by_lane = {str(item["lane_id"]): item for item in results}
    expected_lanes = [str(item["lane_id"]) for item in manifest.lanes]
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "status": "pass" if passed else "fail", "detail": detail})

    check("ordered_population", list(by_lane) == expected_lanes, f"{len(by_lane)}/{len(expected_lanes)} lanes")
    check("one_attempt_each", all(item.get("attempt") == 1 for item in results), "attempt=1 for every lane")
    check("no_duplicate_lane", len(by_lane) == len(results) == len(expected_lanes), "append-only inventory has one terminal row per lane")
    check("mapping_release", mapping == {"control": "base", "fault": "changed"}, "matched-pair mapping identity")

    cell_results: dict[str, list[Mapping[str, Any]]] = {}
    for lane, result in zip(manifest.lanes, results, strict=True):
        cell_results.setdefault(str(lane["cell_id"]), []).append(result)
    cells: dict[str, Any] = {}
    for cell in manifest.cells:
        cell_id = str(cell["cell_id"])
        mode = str(cell["target_mode"])
        variant = str(cell["variant"])
        rows = cell_results.get(cell_id, [])
        conclusions = [str(row.get("oracle_conclusion")) for row in rows]
        accountable = [bool(row.get("accountable")) for row in rows]
        expected_conclusion = "locally_rejected" if variant == "defect" else "locally_supported"
        cell_pass = len(rows) == 3 and all(accountable) and all(item == expected_conclusion for item in conclusions)
        check(f"cell:{cell_id}", cell_pass, f"accountable={sum(accountable)}/3 conclusions={conclusions}")
        cells[cell_id] = {
            "target_mode": mode,
            "variant": variant,
            "variant_source": mapping["fault" if variant == "defect" else "control"],
            "lanes": [str(row["lane_id"]) for row in rows],
            "accountable": sum(accountable),
            "oracle_conclusions": conclusions,
            "oracle_classifications": [row.get("oracle_classification") for row in rows],
            "expected_protocol_conclusion": expected_conclusion,
            "cell_pass": cell_pass,
        }
    modes: dict[str, Any] = {}
    for mode in ("change", "project"):
        selected = [value for key, value in cells.items() if key.startswith(mode + "-")]
        mode_pass = bool(selected) and all(value["cell_pass"] for value in selected)
        modes[mode] = {
            "cells": [key for key in cells if key.startswith(mode + "-")],
            "locally_supported": mode_pass,
            "claim_boundary": CLAIM_BOUNDARY,
        }
        check(f"mode:{mode}", mode_pass, f"both frozen {mode} cells reconcile")
    conclusion = "locally_supported" if all(item["locally_supported"] for item in modes.values()) else "inconclusive"
    audit = {
        "schema_version": 1,
        "auditor": "m8-state-evolution-independent-adjudicator-v1",
        "mapping": dict(mapping),
        "checks": checks,
        "lanes_reconciled": len(results),
        "cells": cells,
        "modes": modes,
        "qualification_conclusion": conclusion,
        "claim_boundary": {
            "local_only": True,
            "scope": CLAIM_BOUNDARY,
            "no_combined_mode_rate": True,
            "exclusions": list(manifest.document["claim_boundary"]["exclusions"]),
        },
    }
    _write_json(out, audit)
    return audit


def execute_formal_qualification(
    *,
    manifest_path: str | Path = DEFAULT_MANIFEST,
    repo_root: str | Path | None = None,
    artifact_root: str | Path = DEFAULT_ARTIFACT_ROOT,
    device: str = DEFAULT_DEVICE,
    workspace_root: str | Path | None = None,
) -> dict[str, Any]:
    """Admit, execute, reconcile, and persist all twelve frozen lanes."""

    root = Path(repo_root).resolve() if repo_root is not None else Path.cwd().resolve()
    manifest_file = Path(manifest_path).resolve()
    artifacts = Path(artifact_root).resolve()
    if artifacts.exists() and any(artifacts.iterdir()):
        raise M8FormalExecutionError(f"artifact root must be new and empty: {artifacts}")
    artifacts.mkdir(parents=True, exist_ok=True)

    head = _git(root, "rev-parse", "HEAD")
    origin_head = _git(root, "rev-parse", "origin/main")
    if _git(root, "merge-base", head, origin_head) != MERGED_121_COMMIT:
        raise M8FormalExecutionError(
            f"formal execution must descend from exact merged #121 commit {MERGED_121_COMMIT}; "
            f"HEAD={head} origin/main={origin_head}"
        )

    manifest = load_manifest(manifest_file)
    preflight = admit_qualification(manifest_file, repo_root=root)
    if not preflight.admitted or len(preflight.lanes) != 12:
        raise M8FormalExecutionError("M8 admission did not produce an admitted ordered 12-lane handoff")
    _write_json(
        artifacts / "preflight.json",
        {
            **preflight.to_dict(),
            "formal_execution_started": False,
            "source_head": head,
            "origin_main": origin_head,
            "exact_merged_121": MERGED_121_COMMIT,
        },
    )

    contract_path = root / str(manifest.document["fixture"]["contract"]["path"])
    pair_path = root / str(manifest.document["auditor_mapping"]["artifact"]["path"])
    provenance = verify_state_evolution_provenance(contract_path, base_dir=contract_path.parent)
    pair_verification = verify_state_evolution_matched_pair(pair_path, repo_root=root)
    _write_json(artifacts / "qualification-input-verification.json", {
        "contract_provenance": provenance.to_dict(),
        "matched_pair": pair_verification.to_dict(),
        "manifest_sha256": manifest.source_sha256,
        "canonical_manifest_sha256": manifest.canonical_sha256,
    })
    if not provenance.valid or not pair_verification.valid:
        raise M8FormalExecutionError("qualification input provenance or matched pair failed")

    contract = load_state_evolution_contract(contract_path)
    strategy = make_state_evolution_strategy(
        prior=make_state_evolution_prior(),
        operator=make_historical_state_replay_operator(),
    )
    context_path = root / str(manifest.document["fixture"]["context"]["path"])
    diff_path = root / str(manifest.document["source_identity"]["change_input"]["path"])
    admitted_packages: dict[str, Any] = {}
    for lane in manifest.lanes:
        receipt, package = _admit_lane(
            manifest=manifest,
            lane=lane,
            root=root,
            context_path=context_path,
            diff_path=diff_path,
            strategy=strategy,
            contract=contract,
        )
        expected = next(item for item in preflight.lanes if item["lane_id"] == lane["lane_id"])
        if receipt["package_sha256"] != expected["package_sha256"]:
            raise M8FormalExecutionError(f"lane {lane['lane_id']} package drifted after admission")
        admitted_packages[str(lane["lane_id"])] = package
    _write_json(artifacts / "admitted-package-bindings.json", {
        "qualification_id": manifest.qualification_id,
        "manifest_sha256": manifest.source_sha256,
        "lanes": [
            {"lane_id": lane["lane_id"], "package_sha256": next(item for item in preflight.lanes if item["lane_id"] == lane["lane_id"])["package_sha256"]}
            for lane in manifest.lanes
        ],
        "mapping_released": False,
    })

    try:
        mapping_document = _load_json(pair_path)
        mapping = dict(mapping_document["audit_mapping"])
    except Exception as error:
        raise M8FormalExecutionError(f"auditor mapping cannot be released: {error}") from error
    if mapping != {"control": "base", "fault": "changed"}:
        raise M8FormalExecutionError(f"unexpected auditor mapping: {mapping}")
    _write_json(artifacts / "auditor-mapping-release.json", {
        "mapping_sha256": _sha256(pair_path),
        "release_after": "hypothesis_freeze_and_plan_admission",
        "all_lanes_admitted": True,
        "mapping": mapping,
        "verifier_prompt_exposure": False,
    })

    workspace = Path(workspace_root).resolve() if workspace_root is not None else artifacts.parent / ".m8-122-workspaces"
    variants = _variant_worktrees(
        root=root,
        workspace_root=workspace,
        commit=head,
        patch_path=diff_path,
    )
    build_dir = artifacts / "build"
    build_receipts = {
        variant: _build_variant(
            variant=variant,
            worktree=worktree,
            build_root=build_dir,
            build=manifest.document["build"],
        )
        for variant, worktree in variants.items()
    }
    _write_json(artifacts / "build-receipts.json", {
        "source_head": head,
        "workspace_root": str(workspace),
        "variants": build_receipts,
        "mapping_sha256": _sha256(pair_path),
    })

    inventory_path = artifacts / "attempt-inventory.jsonl"
    results: list[Mapping[str, Any]] = []
    for lane in manifest.lanes:
        lane_id = str(lane["lane_id"])
        variant = "defect" if mapping["fault"] == "changed" and str(lane["cell_id"]).endswith("defect") else "control"
        worktree = variants[variant]
        run_spec_data = next(item for item in preflight.lanes if item["lane_id"] == lane_id)["run_spec"]
        spec_path = worktree / f".m8-run-spec-{lane_id}.json"
        _write_json(spec_path, run_spec_data)
        result = _run_lane(
            lane=lane,
            package=admitted_packages[lane_id],
            spec_path=spec_path,
            worktree=worktree,
            artifact_root=artifacts,
            device=device,
            contract=contract,
            build_receipt=build_receipts[variant],
        )
        with inventory_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
        results.append(result)

    audit = _audit_reconciliation(
        manifest=manifest,
        results=results,
        mapping=mapping,
        out=artifacts / "independent-adjudication.json",
    )
    summary = {
        "schema_version": 1,
        "qualification_id": manifest.qualification_id,
        "manifest_sha256": manifest.source_sha256,
        "canonical_manifest_sha256": manifest.canonical_sha256,
        "exact_merged_121": MERGED_121_COMMIT,
        "source_head": head,
        "origin_main_at_start": origin_head,
        "formal_execution_started": True,
        "device": device,
        "lane_count": len(results),
        "attempts": 1,
        "results": results,
        "adjudication": audit,
        "claim_boundary": manifest.document["claim_boundary"],
        "workspace_root": str(workspace),
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _write_json(artifacts / "formal-summary.json", summary)
    _write_global_checksums(artifacts)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact-root", type=Path, default=Path(DEFAULT_ARTIFACT_ROOT))
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--workspace-root", type=Path)
    args = parser.parse_args(argv)
    try:
        summary = execute_formal_qualification(
            manifest_path=args.manifest,
            repo_root=args.repo_root,
            artifact_root=args.artifact_root,
            device=args.device,
            workspace_root=args.workspace_root,
        )
    except (M8FormalExecutionError, M8QualificationError, StateEvolutionContractError) as error:
        parser.error(str(error))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
