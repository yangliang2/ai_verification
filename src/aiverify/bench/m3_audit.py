"""Final evidence-derived audit for the bounded M3 reliability slice."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from aiverify.bench.m3_reliability import (
    ReliabilityManifest,
    ReliabilitySummary,
    attempt_directories,
    build_summary,
    failure_class,
    is_accountable,
    lane_outcome,
    load_verified_attempt,
)
from aiverify.bench.run_record_checksums import verify_manifest

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


def build_audited_report(
    manifest: ReliabilityManifest, *, environment_path: Path
) -> AuditedReliabilityReport:
    """Build the final five-seed M3 audit exclusively from retained evidence."""
    _validate_final_inventory(manifest)
    summary = build_summary(manifest)
    environment = _load_audit_environment(environment_path)
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

    for lane in manifest.lanes:
        attempts = attempt_directories(lane)
        loaded: list[dict] = []
        for number, attempt_dir in enumerate(attempts, start=1):
            _, verdict = load_verified_attempt(
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
            devices.add(gate_device)
            preflight_statuses[gate_status] += 1
            formal_attempts += 1
            loaded.append(verdict)

        eventual = loaded[-1]
        accountable = is_accountable(eventual)
        outcome = lane_outcome(lane, eventual) if accountable else "non_accountable"
        lane_failure_class = None if accountable else failure_class(eventual)
        lane_results.append(
            {
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
        )
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

    device_serial = environment["device"]["serial"]
    if sorted(devices) != [device_serial]:
        raise ValueError(
            "audit environment device does not match committed attempt gates"
        )

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

    evidence_packages = _verified_evidence_packages(manifest)
    return AuditedReliabilityReport(
        schema_version=1,
        slice_id=manifest.slice_id,
        inventory={
            "selected_seeds": len({lane.seed_id for lane in manifest.lanes}),
            "lane_roles": len({lane.role for lane in manifest.lanes}),
            "repetitions_per_role": 3,
            "planned_lanes": len(manifest.lanes),
            "formal_attempts": formal_attempts,
            "evidence_packages": len(evidence_packages),
        },
        summary=summary,
        criteria=criteria,
        oracle_breakdown=oracle_rows,
        lane_results=lane_results,
        execution_identity={
            "devices": sorted(devices),
            "preflight_statuses": dict(sorted(preflight_statuses.items())),
            "audit_environment": environment,
        },
        evidence_packages=evidence_packages,
        scope_limitations=[
            "Wikipedia host only",
            "Codex CLI Verification Agent Backend only",
            "Android CLI on one API 35 emulator only",
            "five-seed, 30-lane live slice only",
            "not a fully unattended Journey measurement",
            "not a benchmark-wide detection or false-positive rate",
            "not a cross-host, physical-device, ColorOS, or visual-only/multimodal claim",
        ],
    )


def audited_report_to_dict(report: AuditedReliabilityReport) -> dict:
    """Return the stable structured payload for the final M3 audit."""
    return asdict(report)


def render_audited_markdown(report: AuditedReliabilityReport) -> str:
    """Render the final audited report from the exact structured report model."""
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
    if environment.get("schema_version") != 1:
        raise ValueError("audit environment schema_version must be 1")
    required = {
        "host": ("name", "path", "git_commit", "worktree_clean"),
        "device": ("serial", "avd", "android_version", "api_level", "model"),
        "backend": ("name", "version"),
        "tools": ("android_cli", "adb", "openjdk", "python", "pytest"),
    }
    for section, keys in required.items():
        values = environment.get(section)
        if not isinstance(values, dict):
            raise ValueError(f"audit environment {section} is invalid")
        for key in keys:
            value = values.get(key)
            if key == "worktree_clean":
                if value is not True:
                    raise ValueError("audit environment host worktree must be clean")
            elif not isinstance(value, (str, int)) or isinstance(value, bool) or str(value) == "":
                raise ValueError(f"audit environment {section}.{key} is invalid")
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
