"""Final evidence-derived audit for the bounded M3 reliability slice."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from aiverify.bench.m3_reliability import (
    ReliabilityManifest,
    ReliabilityLane,
    ReliabilitySummary,
    attempt_directories,
    build_summary,
    failure_class,
    is_accountable,
    lane_outcome,
    load_manifest,
    load_verified_attempt,
    summary_to_dict,
)
from aiverify.bench.run_record_checksums import verify_manifest
from aiverify.runner.run_spec import load_run_spec

_LANE_ROLES = frozenset({"baseline", "defect"})
_ORACLE_LEVELS = frozenset({"L1", "L2", "L3"})


@dataclass(frozen=True)
class AuditedReliabilityReport:
    """Final M3 audit rendered identically as structured data and Markdown."""

    schema_version: int
    slice_id: str
    inventory: dict[str, int]
    summary: ReliabilitySummary
    criteria: dict[str, dict]
    oracle_breakdown: dict[str, dict[str, int]]
    lane_results: list[dict]
    execution_identity: dict
    evidence_packages: list[dict]
    scope_limitations: list[str]
    comparison: dict | None = None


def build_audited_report(
    manifest: ReliabilityManifest, *, environment_path: Path
) -> AuditedReliabilityReport:
    """Build the final five-seed M3 audit exclusively from retained evidence."""
    _validate_final_inventory(manifest)
    summary = build_summary(manifest)
    environment = _load_audit_environment(environment_path)
    if environment["schema_version"] != manifest.schema_version:
        raise ValueError("audit environment schema does not match reliability manifest")
    evidence_packages = _verified_evidence_packages(manifest)
    is_rebaseline = manifest.schema_version == 2
    package_contexts: dict[Path, dict] = {}
    repo_root: Path | None = None
    if is_rebaseline:
        repo_root = _repository_root(Path(environment_path))
        _validate_rebaseline_manifest_identity(
            manifest,
            environment=environment,
            repo_root=repo_root,
        )
        package_contexts = _load_package_contexts(
            manifest,
            environment=environment,
            repo_root=repo_root,
        )

    devices: set[str] = set()
    preflight_statuses: Counter[str] = Counter()
    lane_results: list[dict] = []
    oracle_rows = {
        level: {
            "planned": 0,
            "eventual_accountable": 0,
            "passed_controls": 0,
            "caught_defects": 0,
            "non_accountable": 0,
        }
        for level in sorted(_ORACLE_LEVELS)
    }
    formal_attempts = 0
    package_attempts: Counter[Path] = Counter()

    for lane in manifest.lanes:
        attempts = attempt_directories(lane)
        package = lane.evidence_dir.parent.parent
        package_context = package_contexts.get(package)
        loaded: list[dict] = []
        attempt_lineage: list[dict] = []
        for number, attempt_dir in enumerate(attempts, start=1):
            metadata, verdict = load_verified_attempt(
                attempt_dir, lane=lane, attempt_number=number
            )
            gate = _load_json(
                attempt_dir / "live-validation-gate.json",
                label="live-validation gate",
            )
            gate_device = gate.get("device")
            gate_status = gate.get("status")
            if not isinstance(gate_device, str) or not gate_device:
                raise ValueError(f"lane {lane.lane_id} gate device is invalid")
            if gate_status not in {"passed", "failed"}:
                raise ValueError(f"lane {lane.lane_id} gate status is invalid")
            _validate_gate_verdict_consistency(
                gate_status=gate_status,
                verdict=verdict,
                lane=lane,
            )
            if package_context is not None:
                _validate_attempt_package_identity(
                    metadata=metadata,
                    gate_device=gate_device,
                    lane=lane,
                    attempt_dir=attempt_dir,
                    package_environment=package_context["environment"],
                )
            devices.add(gate_device)
            preflight_statuses[gate_status] += 1
            formal_attempts += 1
            package_attempts[package] += 1
            loaded.append(verdict)
            if is_rebaseline:
                attempt_failure_class = (
                    None if is_accountable(verdict) else failure_class(verdict)
                )
                attempt_lineage.append(
                    {
                        "attempt_number": number,
                        "path": _stable_evidence_path(attempt_dir),
                        "started_at": metadata["started_at"],
                        "finished_at": metadata["finished_at"],
                        "runner_exit_code": metadata["runner_exit_code"],
                        "operational_interventions": metadata.get(
                            "operational_interventions", []
                        ),
                        "gate_status": gate_status,
                        "device": gate_device,
                        "execution_status": verdict["execution"]["status"],
                        "accountable": is_accountable(verdict),
                        "failure_class": attempt_failure_class,
                        "total_seconds": verdict["timing"]["total_seconds"],
                        "judge_seconds": _attempt_judge_seconds(verdict),
                        "checksum_status": "verified",
                    }
                )

        eventual = loaded[-1]
        accountable = is_accountable(eventual)
        outcome = lane_outcome(lane, eventual) if accountable else "non_accountable"
        lane_failure_class = None if accountable else failure_class(eventual)
        lane_result = {
            "lane_id": lane.lane_id,
            "seed_id": lane.seed_id,
            "role": lane.role,
            "repetition": lane.repetition,
            "expected_oracle_level": lane.expected_oracle_level,
            "expected_oracle_defect_class": lane.expected_oracle_defect_class,
            "attempts": len(attempts),
            "first_attempt_accountable": is_accountable(loaded[0]),
            "eventual_accountable": accountable,
            "outcome": outcome,
            "failure_class": lane_failure_class,
        }
        if is_rebaseline:
            assert repo_root is not None
            lane_result.update(
                {
                    "evidence_dir": _stable_evidence_path(lane.evidence_dir),
                    "run_spec": _stable_repo_path(lane.run_spec, repo_root=repo_root),
                    "run_spec_sha256": _sha256_file(lane.run_spec),
                    "final_status": (
                        "accountable" if accountable else "non_accountable"
                    ),
                    "attempt_lineage": attempt_lineage,
                }
            )
        lane_results.append(lane_result)
        oracle = oracle_rows[lane.expected_oracle_level]
        oracle["planned"] += 1
        if not accountable:
            oracle["non_accountable"] += 1
        else:
            oracle["eventual_accountable"] += 1
            if outcome == "passed_control":
                oracle["passed_controls"] += 1
            elif outcome == "caught":
                oracle["caught_defects"] += 1

    if not is_rebaseline:
        device_serial = environment["device"]["serial"]
        if sorted(devices) != [device_serial]:
            raise ValueError(
                "audit environment device does not match committed attempt gates"
            )

    criteria = _build_criteria(summary, lane_results=lane_results)
    inventory = {
        "selected_seeds": len({lane.seed_id for lane in manifest.lanes}),
        "lane_roles": len({lane.role for lane in manifest.lanes}),
        "repetitions_per_role": 3,
        "planned_lanes": len(manifest.lanes),
        "formal_attempts": formal_attempts,
        "evidence_packages": len(evidence_packages),
    }
    package_environments: list[dict] = []
    identity_coverage: dict[str, str] | None = None
    comparison: dict | None = None
    if is_rebaseline:
        assert repo_root is not None
        package_environments, identity_coverage = _package_execution_identities(
            manifest,
            package_contexts=package_contexts,
            package_attempts=package_attempts,
        )
        comparison = _build_historical_comparison(
            manifest,
            environment=environment,
            repo_root=repo_root,
            inventory=inventory,
            summary=summary,
            criteria=criteria,
            oracle_breakdown=oracle_rows,
            preflight_statuses=dict(sorted(preflight_statuses.items())),
        )

    execution_identity = {
        "devices": sorted(devices),
        "preflight_statuses": dict(sorted(preflight_statuses.items())),
        "audit_environment": environment,
    }
    if is_rebaseline:
        execution_identity.update(
            {
                "package_environments": package_environments,
                "identity_coverage": identity_coverage,
            }
        )

    return AuditedReliabilityReport(
        schema_version=manifest.schema_version,
        slice_id=manifest.slice_id,
        inventory=inventory,
        summary=summary,
        criteria=criteria,
        oracle_breakdown=oracle_rows,
        lane_results=lane_results,
        execution_identity=execution_identity,
        evidence_packages=evidence_packages,
        scope_limitations=(
            [
                "Wikipedia host only",
                "Codex CLI Verification Agent Backend only",
                "Android CLI across the two declared package environments: "
                "Android 16/API 36 medium_phone and Android 15/API 35 "
                "aiverify_api35 emulators",
                "versioned five-seed, 30-lane live v2 slice only",
                "mixed host/device environments prevent causal timing comparisons",
                "not a fully unattended Journey measurement",
                "not a benchmark-wide detection or false-positive rate",
                "not a physical-device, ColorOS, or visual-only/multimodal claim",
            ]
            if is_rebaseline
            else [
                "Wikipedia host only",
                "Codex CLI Verification Agent Backend only",
                "Android CLI on one API 35 emulator only",
                "five-seed, 30-lane live slice only",
                "not a fully unattended Journey measurement",
                "not a benchmark-wide detection or false-positive rate",
                "not a cross-host, physical-device, ColorOS, or visual-only/multimodal claim",
            ]
        ),
        comparison=comparison,
    )


def audited_report_to_dict(report: AuditedReliabilityReport) -> dict:
    """Return the stable structured payload for the final M3 audit."""
    payload = asdict(report)
    if report.comparison is None:
        payload.pop("comparison")
    return payload


def _build_criteria(
    summary: ReliabilitySummary, *, lane_results: list[dict]
) -> dict[str, dict]:
    false_positives = summary.control_outcomes.get("false_positive", 0)
    accountable_defects = sum(
        row["eventual_accountable"]
        for row in lane_results
        if row["role"] == "defect"
    )
    caught_defects = summary.defect_outcomes.get("caught", 0)
    criteria = {
        "eventual_accountability": {
            "status": "passed" if summary.eventual_accountable >= 29 else "failed",
            "actual": summary.eventual_accountable,
            "required_minimum": 29,
        },
        "zero_accountable_baseline_false_positives": {
            "status": "passed" if false_positives == 0 else "failed",
            "actual": false_positives,
            "required_maximum": 0,
        },
        "accountable_defect_consistency": {
            "status": "passed" if caught_defects == accountable_defects else "failed",
            "actual": caught_defects,
            "required": accountable_defects,
        },
    }
    criteria["m3_overall"] = {
        "status": (
            "passed"
            if all(row["status"] == "passed" for row in criteria.values())
            else "failed"
        )
    }
    return criteria


def _repository_root(environment_path: Path) -> Path:
    resolved = environment_path.resolve()
    for parent in resolved.parents:
        if (parent / "bench" / "goldset").is_dir() and (parent / "docs").is_dir():
            return parent
    raise ValueError(f"cannot resolve repository root from {environment_path}")


def _validate_rebaseline_manifest_identity(
    manifest: ReliabilityManifest, *, environment: dict, repo_root: Path
) -> None:
    identity = environment["rebaseline_manifest"]
    manifest_path = repo_root / identity["path"]
    if _sha256_file(manifest_path) != identity["sha256"]:
        raise ValueError("rebaseline manifest checksum mismatch")
    loaded = load_manifest(manifest_path, repo_root=repo_root)
    if asdict(loaded) != asdict(manifest):
        raise ValueError("rebaseline manifest identity does not match audit input")


def _load_package_contexts(
    manifest: ReliabilityManifest, *, environment: dict, repo_root: Path
) -> dict[Path, dict]:
    packages = sorted({lane.evidence_dir.parent.parent for lane in manifest.lanes})
    configured_models = environment["package_model_identity"]
    stable_packages = {_stable_evidence_path(package) for package in packages}
    if set(configured_models) != stable_packages:
        raise ValueError("package model identity inventory does not match evidence packages")

    manifest_sha256 = environment["rebaseline_manifest"]["sha256"]
    contexts: dict[Path, dict] = {}
    for package in packages:
        stable_package = _stable_evidence_path(package)
        package_environment_path = package / "environment.json"
        package_environment = _load_json(
            package_environment_path,
            label=f"package environment for {stable_package}",
        )
        _validate_package_environment(
            package_environment,
            package=stable_package,
        )
        package_lanes = [
            lane
            for lane in manifest.lanes
            if lane.evidence_dir.parent.parent == package
        ]
        if len(package_lanes) != 6:
            raise ValueError(f"package {stable_package} must contain exactly six lanes")
        run_specs = sorted({lane.run_spec for lane in package_lanes})
        if len(run_specs) != 1:
            raise ValueError(f"package {stable_package} must use exactly one Run Spec")
        run_spec = run_specs[0]
        run_spec_sha256 = _sha256_file(run_spec)
        inputs = package_environment.get("inputs")
        inputs = inputs if isinstance(inputs, dict) else {}
        retained_run_spec_sha256 = inputs.get("run_spec_sha256")
        if (
            retained_run_spec_sha256 is not None
            and retained_run_spec_sha256 != run_spec_sha256
        ):
            raise ValueError(f"package {stable_package} Run Spec checksum mismatch")
        retained_manifest_sha256 = inputs.get("manifest_sha256")
        if (
            retained_manifest_sha256 is not None
            and retained_manifest_sha256 != manifest_sha256
        ):
            raise ValueError(f"package {stable_package} manifest checksum mismatch")

        expected_package = package_environment["application"]["package"]
        for lane in package_lanes:
            if load_run_spec(lane.run_spec).package != expected_package:
                raise ValueError(
                    f"package {stable_package} Run Spec application mismatch"
                )

        model_identity = configured_models[stable_package]
        _validate_package_model_identity(
            model_identity,
            package_environment=package_environment,
            package=stable_package,
        )
        contexts[package] = {
            "path": stable_package,
            "environment_path": package_environment_path,
            "environment": package_environment,
            "model_identity": model_identity,
            "run_specs": [
                {
                    "path": _stable_repo_path(run_spec, repo_root=repo_root),
                    "sha256": run_spec_sha256,
                    "retained_sha256": retained_run_spec_sha256,
                    "status": (
                        "matched"
                        if retained_run_spec_sha256 is not None
                        else "not_retained"
                    ),
                }
            ],
            "manifest_identity": {
                "path": environment["rebaseline_manifest"]["path"],
                "sha256": manifest_sha256,
                "retained_sha256": retained_manifest_sha256,
                "status": (
                    "matched"
                    if retained_manifest_sha256 is not None
                    else "not_retained"
                ),
            },
        }
    return contexts


def _validate_package_environment(environment: dict, *, package: str) -> None:
    required = {
        "host": ("workspace", "wikipedia_source"),
        "device": ("serial", "avd", "model", "android_release", "api_level"),
        "tools": ("android_cli", "adb", "python", "pytest", "java"),
        "application": ("package", "version_code", "baseline_apk", "defect_apk"),
    }
    for section, keys in required.items():
        values = environment.get(section)
        if not isinstance(values, dict):
            raise ValueError(f"package {package} environment {section} is invalid")
        for key in keys:
            value = values.get(key)
            if value is None or isinstance(value, bool) or (
                isinstance(value, str) and not value
            ):
                raise ValueError(
                    f"package {package} environment {section}.{key} is invalid"
                )
    for artifact in ("baseline_apk", "defect_apk"):
        value = environment["application"][artifact]
        if not isinstance(value, dict) or not all(
            value.get(key) for key in ("path", "bytes", "sha256")
        ):
            raise ValueError(f"package {package} {artifact} identity is invalid")


def _validate_package_model_identity(
    identity: dict, *, package_environment: dict, package: str
) -> None:
    if not isinstance(identity, dict):
        raise ValueError(f"package {package} model identity is invalid")
    status = identity.get("status")
    if status not in {"retained", "not_retained"}:
        raise ValueError(f"package {package} model identity status is invalid")
    if not isinstance(identity.get("source"), str) or not identity["source"]:
        raise ValueError(f"package {package} model identity source is invalid")
    retained_models = package_environment.get("models")
    if status == "not_retained":
        if retained_models is not None or any(
            identity.get(key) is not None for key in ("journey_driver", "l3_judge")
        ):
            raise ValueError(f"package {package} unretained model identity contradicts evidence")
        return
    if not isinstance(retained_models, dict):
        raise ValueError(f"package {package} retained model identity is missing")
    for role in ("journey_driver", "l3_judge"):
        retained_role = retained_models.get(role)
        if not isinstance(retained_role, dict):
            raise ValueError(f"package {package} retained model identity is invalid")
        explicit_override = retained_role.get("explicit_override")
        if explicit_override is not None and (
            not isinstance(explicit_override, str) or not explicit_override
        ):
            raise ValueError(f"package {package} model override identity is invalid")
    expected = {
        "journey_driver": retained_models.get("journey_driver", {}).get(
            "effective_codex_default"
        ),
        "l3_judge": retained_models.get("l3_judge", {}).get(
            "effective_codex_default"
        ),
    }
    if any(not isinstance(value, str) or not value for value in expected.values()):
        raise ValueError(f"package {package} retained model identity is invalid")
    if any(identity.get(key) != value for key, value in expected.items()):
        raise ValueError(f"package {package} model identity mismatch")


def _validate_attempt_package_identity(
    *,
    metadata: dict,
    gate_device: str,
    lane: ReliabilityLane,
    attempt_dir: Path,
    package_environment: dict,
) -> None:
    command = metadata.get("runner_command")
    if (
        not isinstance(command, list)
        or not command
        or any(not isinstance(value, str) or not value for value in command)
    ):
        raise ValueError(f"lane {lane.lane_id} runner command is invalid")
    for key in ("started_at", "finished_at"):
        if not isinstance(metadata.get(key), str) or not metadata[key]:
            raise ValueError(f"lane {lane.lane_id} {key} is invalid")

    device = package_environment["device"]
    if gate_device != device["serial"]:
        raise ValueError(
            f"lane {lane.lane_id} package environment device does not match gate"
        )
    if _command_value(command, "--device", lane=lane) != gate_device:
        raise ValueError(f"lane {lane.lane_id} runner device does not match gate")
    if _command_value(command, "--workdir", lane=lane) != package_environment[
        "host"
    ]["wikipedia_source"]:
        raise ValueError(
            f"lane {lane.lane_id} runner host path does not match package environment"
        )
    workspace = Path(package_environment["host"]["workspace"])
    try:
        Path(command[0]).relative_to(workspace)
    except ValueError as error:
        raise ValueError(
            f"lane {lane.lane_id} runner executable does not match package workspace"
        ) from error

    try:
        module_index = command.index("aiverify.runner")
        command_run_spec = Path(command[module_index + 1])
    except (ValueError, IndexError) as error:
        raise ValueError(f"lane {lane.lane_id} runner Run Spec is invalid") from error
    if _path_from_anchor(command_run_spec, "bench") != _path_from_anchor(
        lane.run_spec, "bench"
    ):
        raise ValueError(f"lane {lane.lane_id} runner Run Spec does not match manifest")

    artifact_dir = Path(_command_value(command, "--artifact-dir", lane=lane))
    if _stable_evidence_path(artifact_dir) != _stable_evidence_path(
        attempt_dir / "artifacts"
    ):
        raise ValueError(
            f"lane {lane.lane_id} runner artifact path does not match attempt"
        )
    _validate_model_overrides(
        command,
        lane=lane,
        package_environment=package_environment,
    )


def _command_value(command: list[str], flag: str, *, lane: ReliabilityLane) -> str:
    if command.count(flag) != 1:
        raise ValueError(f"lane {lane.lane_id} runner command {flag} is invalid")
    index = command.index(flag)
    if index + 1 >= len(command):
        raise ValueError(f"lane {lane.lane_id} runner command {flag} is incomplete")
    return command[index + 1]


def _validate_model_overrides(
    command: list[str], *, lane: ReliabilityLane, package_environment: dict
) -> None:
    models = package_environment.get("models")
    if not isinstance(models, dict):
        return
    for flag, role in (
        ("--model", "journey_driver"),
        ("--l3-model", "l3_judge"),
    ):
        explicit_override = models[role]["explicit_override"]
        occurrences = command.count(flag)
        if explicit_override is None:
            if occurrences:
                raise ValueError(
                    f"lane {lane.lane_id} runner {flag} contradicts retained "
                    "no-override model identity"
                )
            continue
        if occurrences != 1 or _command_value(command, flag, lane=lane) != (
            explicit_override
        ):
            raise ValueError(
                f"lane {lane.lane_id} runner {flag} contradicts retained model override"
            )


def _path_from_anchor(path: Path, anchor: str) -> Path:
    try:
        index = path.parts.index(anchor)
    except ValueError as error:
        raise ValueError(f"path has no {anchor}/ anchor: {path}") from error
    return Path(*path.parts[index:])


def _attempt_judge_seconds(verdict: dict) -> float:
    phases = verdict["timing"]["phases"]
    return round(
        sum(
            float(phase["seconds"])
            for phase in phases
            if phase.get("phase") == "l3-judge"
        ),
        3,
    )


def _package_execution_identities(
    manifest: ReliabilityManifest,
    *,
    package_contexts: dict[Path, dict],
    package_attempts: Counter[Path],
) -> tuple[list[dict], dict[str, str]]:
    rows: list[dict] = []
    for package, context in sorted(
        package_contexts.items(), key=lambda item: item[1]["path"]
    ):
        package_environment = context["environment"]
        tools = package_environment["tools"]
        host = package_environment["host"]
        package_lanes = [
            lane
            for lane in manifest.lanes
            if lane.evidence_dir.parent.parent == package
        ]
        rows.append(
            {
                "path": context["path"],
                "environment_path": _stable_evidence_path(
                    context["environment_path"]
                ),
                "environment_sha256": _sha256_file(context["environment_path"]),
                "environment_checksum_status": "verified",
                "lane_count": len(package_lanes),
                "formal_attempts": package_attempts[package],
                "host": host,
                "host_commit_status": (
                    "retained" if host.get("wikipedia_commit") else "not_retained"
                ),
                "device": package_environment["device"],
                "tools": tools,
                "backend": {
                    "name": "Codex CLI",
                    "version": tools.get("codex_cli"),
                    "version_status": (
                        "retained" if tools.get("codex_cli") else "not_retained"
                    ),
                },
                "model_identity": context["model_identity"],
                "inputs": {
                    "manifest": context["manifest_identity"],
                    "run_specs": context["run_specs"],
                },
                "application": package_environment["application"],
            }
        )

    package_count = len(rows)
    formal_attempts = sum(row["formal_attempts"] for row in rows)
    model_attempts = sum(
        row["formal_attempts"]
        for row in rows
        if row["model_identity"]["status"] == "retained"
    )
    coverage = {
        "package_environment": f"{package_count}/{package_count}",
        "device_serial_crosscheck": f"{formal_attempts}/{formal_attempts}",
        "host_path_crosscheck": f"{formal_attempts}/{formal_attempts}",
        "run_spec_command_crosscheck": f"{formal_attempts}/{formal_attempts}",
        "run_spec_sha256_retained": (
            f"{sum(row['inputs']['run_specs'][0]['status'] == 'matched' for row in rows)}"
            f"/{package_count}"
        ),
        "manifest_sha256_retained": (
            f"{sum(row['inputs']['manifest']['status'] == 'matched' for row in rows)}"
            f"/{package_count}"
        ),
        "host_commit_retained": (
            f"{sum(row['host_commit_status'] == 'retained' for row in rows)}"
            f"/{package_count}"
        ),
        "backend_version_retained": (
            f"{sum(row['backend']['version_status'] == 'retained' for row in rows)}"
            f"/{package_count}"
        ),
        "model_identity_retained": (
            f"{sum(row['model_identity']['status'] == 'retained' for row in rows)}"
            f"/{package_count}"
        ),
        "model_override_crosscheck": f"{model_attempts}/{model_attempts}",
    }
    return rows, coverage


def _build_historical_comparison(
    manifest: ReliabilityManifest,
    *,
    environment: dict,
    repo_root: Path,
    inventory: dict,
    summary: ReliabilitySummary,
    criteria: dict,
    oracle_breakdown: dict,
    preflight_statuses: dict[str, int],
) -> dict:
    if manifest.comparison_manifest is None:
        raise ValueError("v2 final audit requires a historical comparison manifest")
    comparison_config = environment["comparison"]
    comparison_manifest = manifest.comparison_manifest
    if _sha256_file(comparison_manifest) != comparison_config["manifest_sha256"]:
        raise ValueError("historical comparison manifest checksum mismatch")

    historical_root = repo_root / comparison_config["run_record"]
    errors = verify_manifest(historical_root)
    if errors:
        raise ValueError(
            "artifact_integrity for historical comparison record: "
            + "; ".join(errors)
        )
    expected_artifacts = comparison_config["artifact_sha256"]
    if set(expected_artifacts) != {
        "README.md",
        "checksums.sha256",
        "environment.json",
        "report.md",
        "summary.json",
    }:
        raise ValueError("historical comparison artifact inventory is invalid")
    for relative_path, expected_sha256 in expected_artifacts.items():
        if _sha256_file(historical_root / relative_path) != expected_sha256:
            raise ValueError(
                f"historical comparison artifact checksum mismatch: {relative_path}"
            )

    historical_manifest = load_manifest(comparison_manifest, repo_root=repo_root)
    expected_package_checksums = comparison_config[
        "evidence_package_checksum_sha256"
    ]
    historical_packages = sorted(
        {lane.evidence_dir.parent.parent for lane in historical_manifest.lanes}
    )
    if set(expected_package_checksums) != {
        _stable_evidence_path(package) for package in historical_packages
    }:
        raise ValueError("historical evidence package inventory is invalid")
    for package in historical_packages:
        stable_package = _stable_evidence_path(package)
        if (
            _sha256_file(package / "checksums.sha256")
            != expected_package_checksums[stable_package]
        ):
            raise ValueError(
                f"historical evidence package checksum anchor mismatch: {stable_package}"
            )

    historical_report = build_audited_report(
        historical_manifest,
        environment_path=historical_root / "environment.json",
    )
    historical_payload = audited_report_to_dict(historical_report)
    if _load_json(
        historical_root / "summary.json", label="historical audited summary"
    ) != historical_payload:
        raise ValueError("historical audited summary contradicts retained evidence")
    if (historical_root / "report.md").read_text(
        encoding="utf-8"
    ) != render_audited_markdown(historical_report):
        raise ValueError("historical audited Markdown contradicts retained evidence")

    historical = _comparison_snapshot(
        slice_id=historical_report.slice_id,
        inventory=historical_report.inventory,
        summary=historical_report.summary,
        criteria=historical_report.criteria,
        oracle_breakdown=historical_report.oracle_breakdown,
        preflight_statuses=historical_report.execution_identity[
            "preflight_statuses"
        ],
    )
    rebaseline = _comparison_snapshot(
        slice_id=manifest.slice_id,
        inventory=inventory,
        summary=summary,
        criteria=criteria,
        oracle_breakdown=oracle_breakdown,
        preflight_statuses=preflight_statuses,
    )
    historical_summary = historical["summary"]
    rebaseline_summary = rebaseline["summary"]
    return {
        "denominators_combined": False,
        "selective_lane_replacement": False,
        "historical": historical,
        "rebaseline": rebaseline,
        "descriptive_delta": {
            key: (
                round(rebaseline_summary[key] - historical_summary[key], 3)
                if key in {"total_seconds", "judge_seconds"}
                else rebaseline_summary[key] - historical_summary[key]
            )
            for key in (
                "first_attempt_accountable",
                "eventual_accountable",
                "retry_count",
                "total_seconds",
                "judge_seconds",
                "operational_interventions",
            )
        },
        "historical_integrity": {
            "status": "verified",
            "manifest": {
                "path": _stable_repo_path(comparison_manifest, repo_root=repo_root),
                "sha256": comparison_config["manifest_sha256"],
            },
            "run_record": comparison_config["run_record"],
            "artifact_sha256": expected_artifacts,
            "evidence_package_checksum_sha256": expected_package_checksums,
        },
        "interpretation": (
            "The original and v2 slices are two distinct 30-lane populations. "
            "Their denominators and lane outcomes are never merged or selectively replaced."
        ),
    }


def _comparison_snapshot(
    *,
    slice_id: str,
    inventory: dict,
    summary: ReliabilitySummary,
    criteria: dict,
    oracle_breakdown: dict,
    preflight_statuses: dict[str, int],
) -> dict:
    return {
        "slice_id": slice_id,
        "inventory": inventory,
        "summary": summary_to_dict(summary),
        "criteria": criteria,
        "oracle_breakdown": oracle_breakdown,
        "preflight_statuses": preflight_statuses,
        "non_accountable_lanes": summary.planned_lanes
        - summary.eventual_accountable,
        "accountable_controls": sum(summary.control_outcomes.values()),
        "accountable_defects": sum(summary.defect_outcomes.values()),
    }


def _stable_repo_path(path: Path, *, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as error:
        raise ValueError(f"path is outside repository: {path}") from error


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"missing checksum input: {path}")
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_audited_markdown(report: AuditedReliabilityReport) -> str:
    """Render the final audited report from the exact structured report model."""
    if report.comparison is not None:
        return _render_rebaseline_markdown(report)

    summary = report.summary
    overall_status = report.criteria["m3_overall"]["status"]
    overall_evidence = (
        "All required M3 criteria passed"
        if overall_status == "passed"
        else "One or more required M3 criteria failed"
    )
    accountability = report.criteria["eventual_accountability"]
    failed_reasons = _failed_criterion_reasons(report)
    decision_sentence = (
        "All required M3 criteria passed for this bounded slice."
        if overall_status == "passed"
        else "M3 is unmet because these criteria failed: "
        + "; ".join(failed_reasons)
        + "."
    )
    lines = [
        "# M3 Verification Agent Audited Reliability Baseline",
        "",
        f"Slice: `{report.slice_id}`",
        "",
        "## Decision",
        "",
        "| Criterion | Result | Evidence |",
        "|---|---|---|",
        (
            "| M3 overall | **"
            + overall_status.upper()
            + f"** | {overall_evidence} |"
        ),
        (
            "| Eventual accountability | **"
            + accountability["status"].upper()
            + "** | "
            + f"{accountability['actual']} / {summary.planned_lanes}; required "
            + f">={accountability['required_minimum']} / {summary.planned_lanes} |"
        ),
        (
            "| Accountable baseline false positives | **"
            + report.criteria["zero_accountable_baseline_false_positives"][
                "status"
            ].upper()
            + "** | "
            + str(
                report.criteria["zero_accountable_baseline_false_positives"][
                    "actual"
                ]
            )
            + " observed; required 0 |"
        ),
        (
            "| Accountable defect consistency | **"
            + report.criteria["accountable_defect_consistency"]["status"].upper()
            + "** | "
            + f"{report.criteria['accountable_defect_consistency']['actual']} / "
            + str(report.criteria["accountable_defect_consistency"]["required"])
            + " caught at expected level/class |"
        ),
        "",
        decision_sentence,
        "Non-accountable lanes remain execution-reliability failures and are not",
        "reclassified as oracle misses, catches, passed controls, or false positives.",
        "",
        "## Aggregate",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Planned lanes | {summary.planned_lanes} |",
        f"| First-attempt accountable | {summary.first_attempt_accountable} |",
        f"| Eventual accountable | {summary.eventual_accountable} |",
        f"| Retries | {summary.retry_count} |",
        f"| Passed controls | {summary.control_outcomes.get('passed_control', 0)} |",
        f"| Caught defects | {summary.defect_outcomes.get('caught', 0)} |",
        f"| Operational interventions | {summary.operational_interventions} |",
        f"| Total attempt time (seconds) | {summary.total_seconds} |",
        f"| L3 judge time (seconds) | {summary.judge_seconds} |",
        "",
        "## Per-Oracle Breakdown",
        "",
        "| Oracle | Planned | Accountable | Passed controls | Caught defects | Non-accountable |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for level, row in report.oracle_breakdown.items():
        lines.append(
            f"| {level} | {row['planned']} | {row['eventual_accountable']} | "
            f"{row['passed_controls']} | {row['caught_defects']} | "
            f"{row['non_accountable']} |"
        )
    lines.extend(
        [
            "",
            "## Non-Accountable Failure Classes",
            "",
            _count_table(summary.failure_classes),
            "",
            "## Lane Resolution",
            "",
            "| Lane | Role | Oracle | Attempts | First accountable | Eventual result |",
            "|---|---|---|---:|---|---|",
        ]
    )
    for row in report.lane_results:
        result = row["outcome"]
        if row["failure_class"] is not None:
            result += f" / {row['failure_class']}"
        lines.append(
            f"| `{row['lane_id']}` | {row['role']} | "
            f"{row['expected_oracle_level']} | {row['attempts']} | "
            f"{str(row['first_attempt_accountable']).lower()} | {result} |"
        )
    environment = report.execution_identity["audit_environment"]
    lines.extend(
        [
            "",
            "## Execution Identity",
            "",
            f"- Host: Wikipedia at `{environment['host']['git_commit']}`; "
            "clean audit worktree.",
            f"- Device: `{environment['device']['serial']}` / "
            f"`{environment['device']['avd']}`, "
            f"Android {environment['device']['android_version']} "
            f"API {environment['device']['api_level']}, "
            f"model `{environment['device']['model']}`.",
            f"- Verification Agent Backend: {environment['backend']['name']} "
            f"`{environment['backend']['version']}`.",
            f"- Android CLI `{environment['tools']['android_cli']}`; "
            f"adb `{environment['tools']['adb']}`; "
            f"OpenJDK `{environment['tools']['openjdk']}`; "
            f"Python `{environment['tools']['python']}`; "
            f"pytest `{environment['tools']['pytest']}`.",
            "- Runner gates: "
            f"{report.execution_identity['preflight_statuses'].get('passed', 0)} "
            "passed, "
            f"{report.execution_identity['preflight_statuses'].get('failed', 0)} "
            "failed.",
            "",
            "## Evidence Packages",
            "",
            "| Package | Checksum entries | Status |",
            "|---|---:|---|",
        ]
    )
    lines.extend(
        f"| `{row['path']}` | {row['checksum_entries']} | {row['checksum_status']} |"
        for row in report.evidence_packages
    )
    lines.extend(["", "## Scope and Claim Boundary", ""])
    lines.extend(f"- {limitation}" for limitation in report.scope_limitations)
    lines.append("")
    return "\n".join(lines)


def _render_rebaseline_markdown(report: AuditedReliabilityReport) -> str:
    comparison = report.comparison
    assert comparison is not None
    historical = comparison["historical"]
    old_summary = historical["summary"]
    new_summary = summary_to_dict(report.summary)
    overall_status = report.criteria["m3_overall"]["status"]
    failed_reasons = _failed_criterion_reasons(report)
    accountability = report.criteria["eventual_accountability"]
    if overall_status == "passed":
        accountability_margin = (
            accountability["actual"] - accountability["required_minimum"]
        )
        margin_sentence = (
            "meets the threshold exactly, with no margin"
            if accountability_margin == 0
            else f"exceeds the threshold by {accountability_margin} lane(s)"
        )
        decision_sentence = (
            "All unchanged M3 criteria passed for the bounded v2 slice. The "
            f"{accountability['actual']}/{report.summary.planned_lanes} "
            f"accountability result {margin_sentence}."
        )
    else:
        decision_sentence = (
            "M3 is unmet because these criteria failed: "
            + "; ".join(failed_reasons)
            + "."
        )

    false_positives = report.criteria[
        "zero_accountable_baseline_false_positives"
    ]
    defects = report.criteria["accountable_defect_consistency"]
    lines = [
        "# M3 Verification Agent Audited Re-Baseline Comparison",
        "",
        f"Slice: `{report.slice_id}`",
        "",
        "## Decision",
        "",
        "| Criterion | Result | Evidence |",
        "|---|---|---|",
        (
            f"| M3 overall | **{overall_status.upper()}** | "
            + (
                "All unchanged criteria passed"
                if overall_status == "passed"
                else "One or more unchanged criteria failed"
            )
            + " |"
        ),
        (
            f"| Eventual accountability | **{accountability['status'].upper()}** | "
            f"{accountability['actual']} / {report.summary.planned_lanes}; required "
            f">={accountability['required_minimum']} / {report.summary.planned_lanes} |"
        ),
        (
            "| Accountable baseline false positives | **"
            f"{false_positives['status'].upper()}** | {false_positives['actual']} "
            "observed; required 0 |"
        ),
        (
            "| Accountable defect consistency | **"
            f"{defects['status'].upper()}** | {defects['actual']} / "
            f"{defects['required']} caught at expected level/class |"
        ),
        "",
        decision_sentence,
        "",
        "The original and v2 runs remain distinct populations: **30 + 30**, not "
        "a combined 60-lane denominator. No historical lane was replaced.",
        "Non-accountable lanes remain execution-reliability failures and are not "
        "reclassified as oracle outcomes.",
        "",
        "## Immutable Original vs Fresh V2",
        "",
        "| Metric | Original (distinct 30) | V2 (distinct 30) |",
        "|---|---:|---:|",
        (
            "| M3 decision | **"
            f"{historical['criteria']['m3_overall']['status'].upper()}** | **"
            f"{overall_status.upper()}** |"
        ),
        (
            f"| Formal attempts | {historical['inventory']['formal_attempts']} | "
            f"{report.inventory['formal_attempts']} |"
        ),
        (
            "| First-attempt accountable | "
            f"{old_summary['first_attempt_accountable']} / 30 | "
            f"{new_summary['first_attempt_accountable']} / 30 |"
        ),
        (
            f"| Eventual accountable | {old_summary['eventual_accountable']} / 30 | "
            f"{new_summary['eventual_accountable']} / 30 |"
        ),
        (
            f"| Non-accountable lanes | {historical['non_accountable_lanes']} | "
            f"{report.summary.planned_lanes - report.summary.eventual_accountable} |"
        ),
        f"| Retries | {old_summary['retry_count']} | {new_summary['retry_count']} |",
        (
            "| Accountable controls passed | "
            f"{old_summary['control_outcomes'].get('passed_control', 0)} / "
            f"{historical['accountable_controls']} | "
            f"{new_summary['control_outcomes'].get('passed_control', 0)} / "
            f"{sum(report.summary.control_outcomes.values())} |"
        ),
        (
            "| Accountable baseline false positives | "
            f"{old_summary['control_outcomes'].get('false_positive', 0)} | "
            f"{new_summary['control_outcomes'].get('false_positive', 0)} |"
        ),
        (
            "| Accountable defects caught | "
            f"{old_summary['defect_outcomes'].get('caught', 0)} / "
            f"{historical['accountable_defects']} | "
            f"{new_summary['defect_outcomes'].get('caught', 0)} / "
            f"{sum(report.summary.defect_outcomes.values())} |"
        ),
        (
            "| Operational interventions | "
            f"{old_summary['operational_interventions']} | "
            f"{new_summary['operational_interventions']} |"
        ),
        (
            f"| Total attempt time (seconds) | {old_summary['total_seconds']} | "
            f"{new_summary['total_seconds']} |"
        ),
        (
            f"| L3 judge time (seconds) | {old_summary['judge_seconds']} | "
            f"{new_summary['judge_seconds']} |"
        ),
        (
            "| Runner gates | "
            f"{historical['preflight_statuses'].get('passed', 0)} passed / "
            f"{historical['preflight_statuses'].get('failed', 0)} failed | "
            f"{report.execution_identity['preflight_statuses'].get('passed', 0)} "
            "passed / "
            f"{report.execution_identity['preflight_statuses'].get('failed', 0)} "
            "failed |"
        ),
        "",
        "Timing and intervention differences are descriptive only because v2 used "
        "mixed retained host/device environments.",
        "",
        "## V2 Per-Oracle Breakdown",
        "",
        "| Oracle | Planned | Accountable | Passed controls | Caught defects | Non-accountable |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for level, row in report.oracle_breakdown.items():
        lines.append(
            f"| {level} | {row['planned']} | {row['eventual_accountable']} | "
            f"{row['passed_controls']} | {row['caught_defects']} | "
            f"{row['non_accountable']} |"
        )
    lines.extend(
        [
            "",
            "## V2 Attempt Failure Classes",
            "",
            _count_table(report.summary.failure_classes),
            "",
            "Failure classes count non-accountable attempts; "
            f"{sum(report.summary.failure_classes.values())} failed attempt(s) "
            "resolve to "
            f"{report.summary.planned_lanes - report.summary.eventual_accountable} "
            "non-accountable lane(s).",
            "",
            "## V2 Lane Resolution",
            "",
            "| Lane | Role | Oracle | Attempts | First accountable | Final status | Outcome |",
            "|---|---|---|---:|---|---|---|",
        ]
    )
    for row in report.lane_results:
        result = row["outcome"]
        if row["failure_class"] is not None:
            result += f" / {row['failure_class']}"
        lines.append(
            f"| `{row['lane_id']}` | {row['role']} | "
            f"{row['expected_oracle_level']} | {row['attempts']} | "
            f"{str(row['first_attempt_accountable']).lower()} | "
            f"{row['final_status']} | {result} |"
        )
    lines.extend(
        [
            "",
            "## V2 Bounded Attempt Lineage",
            "",
            "| Lane | Attempt | Gate | Accountable | Exit | Seconds | Judge seconds "
            "| Interventions | Checksum |",
            "|---|---:|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in report.lane_results:
        for attempt in row["attempt_lineage"]:
            lines.append(
                f"| `{row['lane_id']}` | {attempt['attempt_number']} | "
                f"{attempt['gate_status']} | "
                f"{str(attempt['accountable']).lower()} | "
                f"{attempt['runner_exit_code']} | {attempt['total_seconds']} | "
                f"{attempt['judge_seconds']} | "
                f"{len(attempt['operational_interventions'])} | "
                f"{attempt['checksum_status']} |"
            )

    audit_environment = report.execution_identity["audit_environment"]
    lines.extend(
        [
            "",
            "## Execution and Evidence Identity",
            "",
            f"Audit host: `{audit_environment['audit_host']['workspace']}` at "
            f"`{audit_environment['audit_host']['generated_from_revision']}`; "
            f"Codex CLI `{audit_environment['backend']['version']}`, Python "
            f"`{audit_environment['tools']['python']}`, pytest "
            f"`{audit_environment['tools']['pytest']}`.",
            "",
            "Each lane is cross-checked against its own checksummed package "
            "environment; the reused serial alone is not treated as a homogeneous "
            "device identity.",
            "",
            "| Package | Lanes / attempts | Host workspace | Wikipedia commit | "
            "Device | Android | Codex | Model |",
            "|---|---:|---|---|---|---|---|---|",
        ]
    )
    for row in report.execution_identity["package_environments"]:
        host_commit = row["host"].get("wikipedia_commit", "not retained")
        codex_version = row["backend"]["version"] or "not retained"
        model = (
            row["model_identity"]["journey_driver"]
            if row["model_identity"]["status"] == "retained"
            else "not retained"
        )
        lines.append(
            f"| `{row['path']}` | {row['lane_count']} / "
            f"{row['formal_attempts']} | `{row['host']['workspace']}` | "
            f"`{host_commit}` | `{row['device']['serial']}` / "
            f"`{row['device']['avd']}` | API {row['device']['api_level']} / "
            f"Android {row['device']['android_release']} | `{codex_version}` | "
            f"`{model}` |"
        )
    coverage = report.execution_identity["identity_coverage"]
    coverage_labels = {
        "package_environment": "Package environment retained",
        "device_serial_crosscheck": "Attempt device serial cross-check",
        "host_path_crosscheck": "Attempt host path cross-check",
        "run_spec_command_crosscheck": "Attempt Run Spec command cross-check",
        "run_spec_sha256_retained": "Run Spec SHA-256 retained",
        "manifest_sha256_retained": "Manifest SHA-256 retained",
        "host_commit_retained": "Wikipedia commit retained",
        "backend_version_retained": "Codex CLI version retained",
        "model_identity_retained": "Model identity retained",
        "model_override_crosscheck": "Retained model override cross-check",
    }
    lines.extend(
        [
            "",
            "| Identity check | Coverage |",
            "|---|---:|",
        ]
    )
    lines.extend(
        f"| {coverage_labels[key]} | {value} |" for key, value in coverage.items()
    )
    package_environments = report.execution_identity["package_environments"]
    retained_model_rows = [
        row
        for row in package_environments
        if row["model_identity"]["status"] == "retained"
    ]
    retained_models = sorted(
        {
            model
            for row in retained_model_rows
            for model in (
                row["model_identity"]["journey_driver"],
                row["model_identity"]["l3_judge"],
            )
        }
    )
    model_packages = ", ".join(
        f"`{Path(row['path']).name}`" for row in retained_model_rows
    )
    missing_model_count = len(package_environments) - len(retained_model_rows)
    missing_run_spec_count = sum(
        row["inputs"]["run_specs"][0]["status"] == "not_retained"
        for row in package_environments
    )
    missing_commit_count = sum(
        row["host_commit_status"] == "not_retained"
        for row in package_environments
    )
    lines.extend(
        [
            "",
            f"{model_packages} explicitly retain(s) effective model(s) "
            f"{', '.join(f'`{model}`' for model in retained_models)}. "
            f"The other {missing_model_count} package model identities are "
            "reported as unavailable, not backfilled from current configuration.",
            f"{missing_run_spec_count} package(s) omit contemporaneous Run Spec "
            f"hashes and {missing_commit_count} omit Wikipedia commits; current "
            "Run Spec hashes are shown in JSON as repository cross-checks with "
            "`not_retained` status.",
            "",
            "## V2 Evidence Packages",
            "",
            "| Package | Checksum entries | Status |",
            "|---|---:|---|",
        ]
    )
    lines.extend(
        f"| `{row['path']}` | {row['checksum_entries']} | {row['checksum_status']} |"
        for row in report.evidence_packages
    )
    integrity = comparison["historical_integrity"]
    lines.extend(
        [
            "",
            "## Historical Integrity",
            "",
            f"- Status: **{integrity['status'].upper()}**.",
            f"- Manifest: `{integrity['manifest']['path']}` / "
            f"`{integrity['manifest']['sha256']}`.",
            f"- Final record: `{integrity['run_record']}`.",
            "- The retained historical JSON and Markdown were regenerated from "
            "their evidence and matched byte-for-model; all five historical package "
            "checksum anchors also matched.",
            "- Original and v2 denominators are not combined, and no original lane "
            "is selectively replaced.",
            "",
            "## Scope and Claim Boundary",
            "",
        ]
    )
    lines.extend(f"- {limitation}" for limitation in report.scope_limitations)
    lines.append("")
    return "\n".join(lines)


def _failed_criterion_reasons(report: AuditedReliabilityReport) -> list[str]:
    criteria = report.criteria
    summary = report.summary
    reasons: list[str] = []
    accountability = criteria["eventual_accountability"]
    if accountability["status"] == "failed":
        reasons.append(
            "eventual accountability "
            f"({accountability['actual']} / {summary.planned_lanes}; required "
            f">={accountability['required_minimum']} / {summary.planned_lanes})"
        )
    false_positives = criteria["zero_accountable_baseline_false_positives"]
    if false_positives["status"] == "failed":
        reasons.append(
            "accountable baseline false positives "
            f"({false_positives['actual']}; required 0)"
        )
    defects = criteria["accountable_defect_consistency"]
    if defects["status"] == "failed":
        reasons.append(
            "accountable defect consistency "
            f"({defects['actual']} / {defects['required']})"
        )
    return reasons


def _validate_final_inventory(manifest: ReliabilityManifest) -> None:
    seeds = {lane.seed_id for lane in manifest.lanes}
    if len(manifest.lanes) != 30 or len(seeds) != 5:
        raise ValueError("final M3 audit requires exactly five seeds and 30 lanes")
    identities = {
        (lane.seed_id, lane.role, lane.repetition) for lane in manifest.lanes
    }
    if len(identities) != 30 or len({lane.lane_id for lane in manifest.lanes}) != 30:
        raise ValueError("final M3 audit requires 30 unique lane identities")
    if {lane.role for lane in manifest.lanes} != _LANE_ROLES:
        raise ValueError("final M3 audit requires baseline and defect roles")
    for seed_id in seeds:
        for role in _LANE_ROLES:
            repetitions = {
                lane.repetition
                for lane in manifest.lanes
                if lane.seed_id == seed_id and lane.role == role
            }
            if repetitions != {1, 2, 3}:
                raise ValueError(
                    "final M3 audit requires repetitions 1, 2, and 3 for every role"
                )


def _load_audit_environment(path: Path) -> dict:
    environment = _load_json(Path(path), label="audit environment")
    schema_version = environment.get("schema_version")
    if schema_version == 1:
        required = {
            "host": ("name", "path", "git_commit", "worktree_clean"),
            "device": ("serial", "avd", "android_version", "api_level", "model"),
            "backend": ("name", "version"),
            "tools": ("android_cli", "adb", "openjdk", "python", "pytest"),
        }
    elif schema_version == 2:
        required = {
            "audit_host": (
                "os",
                "arch",
                "workspace",
                "generated_from_revision",
            ),
            "backend": ("name", "version"),
            "tools": (
                "android_cli",
                "adb",
                "openjdk",
                "python",
                "pytest",
                "git",
            ),
            "rebaseline_manifest": ("path", "sha256"),
        }
    else:
        raise ValueError("audit environment schema_version must be 1 or 2")
    for section, keys in required.items():
        values = environment.get(section)
        if not isinstance(values, dict):
            raise ValueError(f"audit environment {section} is invalid")
        for key in keys:
            value = values.get(key)
            if key == "worktree_clean":
                if value is not True:
                    raise ValueError("audit environment host worktree must be clean")
            elif (
                not isinstance(value, (str, int))
                or isinstance(value, bool)
                or str(value) == ""
            ):
                raise ValueError(f"audit environment {section}.{key} is invalid")
    if schema_version == 2:
        comparison = environment.get("comparison")
        if not isinstance(comparison, dict):
            raise ValueError("audit environment comparison is invalid")
        for key in (
            "manifest_sha256",
            "run_record",
            "artifact_sha256",
            "evidence_package_checksum_sha256",
        ):
            if key not in comparison:
                raise ValueError(f"audit environment comparison.{key} is invalid")
        if not isinstance(comparison["artifact_sha256"], dict) or not isinstance(
            comparison["evidence_package_checksum_sha256"], dict
        ):
            raise ValueError("audit environment comparison checksum maps are invalid")
        if not isinstance(environment.get("package_model_identity"), dict):
            raise ValueError("audit environment package_model_identity is invalid")
    return environment


def _verified_evidence_packages(manifest: ReliabilityManifest) -> list[dict]:
    packages = sorted({lane.evidence_dir.parent.parent for lane in manifest.lanes})
    rows: list[dict] = []
    for package in packages:
        errors = verify_manifest(package)
        if errors:
            raise ValueError(
                f"artifact_integrity for evidence package {package}: "
                + "; ".join(errors)
            )
        checksum_path = package / "checksums.sha256"
        entries = sum(
            1
            for line in checksum_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        rows.append(
            {
                "path": _stable_evidence_path(package),
                "checksum_entries": entries,
                "checksum_status": "verified",
            }
        )
    if len(rows) != 5:
        raise ValueError("final M3 audit requires exactly five evidence packages")
    return rows


def _stable_evidence_path(path: Path) -> str:
    parts = path.parts
    try:
        docs_index = parts.index("docs")
    except ValueError as error:
        raise ValueError(f"evidence package is outside docs/: {path}") from error
    return Path(*parts[docs_index:]).as_posix()


def _validate_gate_verdict_consistency(
    *, gate_status: str, verdict: dict, lane: ReliabilityLane
) -> None:
    preflight = verdict.get("preflight")
    gate_result = (
        preflight.get("live_validation_gate")
        if isinstance(preflight, dict)
        else None
    )
    verdict_gate_status = (
        gate_result.get("status") if isinstance(gate_result, dict) else None
    )
    if verdict_gate_status != gate_status:
        raise ValueError(f"lane {lane.lane_id} gate/verdict status mismatch")

    execution = verdict["execution"]
    if gate_status == "failed" and is_accountable(verdict):
        raise ValueError(
            f"lane {lane.lane_id} failed gate cannot have accountable verdict"
        )
    preflight_failure = execution.get("reason") == "live_validation_preflight_failed"
    if (gate_status == "failed") != preflight_failure:
        raise ValueError(f"lane {lane.lane_id} preflight reason mismatch")



def _load_json(path: Path, *, label: str) -> dict:
    if not path.is_file():
        raise ValueError(f"missing {label}: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise ValueError(f"invalid {label}: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"invalid {label}: {path} must contain an object")
    return value


def _count_table(counts: dict[str, int]) -> str:
    lines = ["| Outcome | Count |", "|---|---:|"]
    if not counts:
        lines.append("| None | 0 |")
    else:
        lines.extend(f"| \u0060{key}\u0060 | {value} |" for key, value in sorted(counts.items()))
    return "\n".join(lines)
