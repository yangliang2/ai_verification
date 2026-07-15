"""Manifest-driven M3 Verification Agent reliability tracing."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from aiverify.agent.oracle.schema import VerdictValidationError, validate_verdict
from aiverify.bench.run_record_checksums import verify_manifest, write_manifest
from aiverify.providers.parsing import extract_json_block
from aiverify.runner.command import CommandRunner, SubprocessCommandRunner
from aiverify.runner.run_spec import load_run_spec


_LANE_ROLES = frozenset({"baseline", "defect"})
_ORACLE_LEVELS = frozenset({"L1", "L2", "L3"})
_DEFAULT_MANIFEST = Path("bench/goldset/m3-reliability-slice.yaml")


@dataclass(frozen=True)
class ReliabilityLane:
    """One planned baseline or injected-defect repetition."""

    lane_id: str
    seed_id: str
    role: str
    repetition: int
    run_spec: Path
    evidence_dir: Path
    expected_oracle_level: str
    expected_oracle_defect_class: str


@dataclass(frozen=True)
class ReliabilityManifest:
    """Versioned inventory for a bounded M3 reliability slice."""

    schema_version: int
    slice_id: str
    max_attempts_per_lane: int
    lanes: tuple[ReliabilityLane, ...]
    comparison_manifest: Path | None = None


@dataclass(frozen=True)
class AttemptRecord:
    """One preserved invocation of the public Run Spec runner."""

    lane_id: str
    attempt_number: int
    directory: Path
    verdict_path: Path
    runner_exit_code: int


@dataclass(frozen=True)
class ReliabilitySummary:
    """Evidence-derived reliability counts for every planned lane."""

    planned_lanes: int
    first_attempt_accountable: int
    eventual_accountable: int
    retry_count: int
    control_outcomes: dict[str, int]
    defect_outcomes: dict[str, int]
    failure_classes: dict[str, int]
    total_seconds: float
    judge_seconds: float
    operational_interventions: int


@dataclass(frozen=True)
class ReliabilityProgress:
    """Partial aggregate that keeps unexecuted lanes outside attempt outcomes."""

    summary: ReliabilitySummary
    pending_lane_ids: tuple[str, ...]


@dataclass(frozen=True)
class _LaneComparisonMetadata:
    """Matched metadata that must remain stable across M3 slice versions."""

    run_spec: Path
    expected_oracle_level: str
    expected_oracle_defect_class: str



def load_manifest(path: Path, *, repo_root: Path) -> ReliabilityManifest:
    """Load and validate the public M3 reliability manifest contract."""
    path = Path(path)
    repo_root = Path(repo_root)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("M3 reliability manifest must be a mapping")

    schema_version = _required_int(raw, "schema_version")
    if schema_version not in {1, 2}:
        raise ValueError(f"unsupported M3 reliability schema_version: {schema_version}")
    slice_id = _required_str(raw, "slice_id")
    max_attempts = _required_int(raw, "max_attempts_per_lane")
    if max_attempts != 2:
        raise ValueError("M3 reliability max_attempts_per_lane must be 2")

    raw_lanes = raw.get("lanes")
    if not isinstance(raw_lanes, list) or not raw_lanes:
        raise ValueError("M3 reliability manifest lanes must be a non-empty list")

    lanes = tuple(_load_lane(row, repo_root=repo_root) for row in raw_lanes)
    lane_ids = [lane.lane_id for lane in lanes]
    if len(lane_ids) != len(set(lane_ids)):
        raise ValueError("M3 reliability manifest contains duplicate lane ids")
    identities = [(lane.seed_id, lane.role, lane.repetition) for lane in lanes]
    if len(identities) != len(set(identities)):
        raise ValueError("M3 reliability manifest contains duplicate lane identity")
    evidence_dirs = [lane.evidence_dir for lane in lanes]
    if len(evidence_dirs) != len(set(evidence_dirs)):
        raise ValueError("M3 reliability manifest contains duplicate evidence directories")

    comparison_manifest = None
    if schema_version == 2:
        comparison_manifest = repo_root / _required_str(raw, "comparison_manifest")
        if comparison_manifest.resolve() == path.resolve():
            raise ValueError("M3 reliability comparison manifest cannot reference itself")

    manifest = ReliabilityManifest(
        schema_version=schema_version,
        slice_id=slice_id,
        max_attempts_per_lane=max_attempts,
        lanes=lanes,
        comparison_manifest=comparison_manifest,
    )
    if comparison_manifest is not None:
        historical = load_manifest(comparison_manifest, repo_root=repo_root)
        if historical.schema_version != 1:
            raise ValueError("M3 reliability comparison manifest must be schema_version 1")
        _validate_version_separation(manifest, historical=historical)
    return manifest


def _validate_version_separation(
    manifest: ReliabilityManifest, *, historical: ReliabilityManifest
) -> None:
    """Require a comparable population with fresh slice, lane, and evidence identities."""
    if manifest.slice_id == historical.slice_id:
        raise ValueError("M3 re-baseline slice_id collides with comparison history")

    lane_ids = {lane.lane_id for lane in manifest.lanes}
    historical_lane_ids = {lane.lane_id for lane in historical.lanes}
    if not lane_ids.isdisjoint(historical_lane_ids):
        raise ValueError("M3 re-baseline contains stale lane identities")

    evidence_dirs = {lane.evidence_dir.resolve() for lane in manifest.lanes}
    historical_evidence_dirs = {
        lane.evidence_dir.resolve() for lane in historical.lanes
    }
    if any(
        current == prior
        or current in prior.parents
        or prior in current.parents
        for current in evidence_dirs
        for prior in historical_evidence_dirs
    ):
        raise ValueError("M3 re-baseline contains stale evidence directories")

    def comparable_rows(
        source: ReliabilityManifest,
    ) -> dict[tuple[str, str, int], _LaneComparisonMetadata]:
        return {
            (lane.seed_id, lane.role, lane.repetition): _LaneComparisonMetadata(
                run_spec=lane.run_spec.resolve(),
                expected_oracle_level=lane.expected_oracle_level,
                expected_oracle_defect_class=lane.expected_oracle_defect_class,
            )
            for lane in source.lanes
        }

    if comparable_rows(manifest) != comparable_rows(historical):
        raise ValueError("M3 re-baseline population or matched metadata changed")
    if manifest.max_attempts_per_lane != historical.max_attempts_per_lane:
        raise ValueError("M3 re-baseline bounded retry policy changed")


def run_lane(
    manifest: ReliabilityManifest,
    *,
    lane_id: str,
    device: str,
    workdir: Path,
    runner: CommandRunner | None = None,
    python_executable: str | None = None,
    operational_interventions: list[str] | None = None,
) -> AttemptRecord:
    """Invoke the public Run Spec runner for the next preserved lane attempt."""
    lane = _lane_by_id(manifest, lane_id)
    interventions = list(operational_interventions or [])
    if any(not isinstance(value, str) or not value.strip() for value in interventions):
        raise ValueError("operational interventions must be non-empty strings")
    attempt_number = _next_attempt_number(lane, manifest=manifest)
    attempt_dir = lane.evidence_dir / f"attempt-{attempt_number}"
    artifact_dir = attempt_dir / "artifacts"
    attempt_dir.mkdir(parents=True, exist_ok=False)

    command = [
        python_executable or sys.executable,
        "-m",
        "aiverify.runner",
        str(lane.run_spec),
        "--device",
        device,
        "--artifact-dir",
        str(artifact_dir),
        "--workdir",
        str(workdir),
    ]
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    command_result = (runner or SubprocessCommandRunner()).run(
        command,
        cwd=workdir,
    )
    finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (attempt_dir / "runner.stdout.txt").write_text(
        command_result.stdout, encoding="utf-8"
    )
    (attempt_dir / "runner.stderr.txt").write_text(
        command_result.stderr, encoding="utf-8"
    )
    verdict_path = attempt_dir / "verdict.json"
    metadata = {
        "schema_version": 1,
        "lane_id": lane.lane_id,
        "seed_id": lane.seed_id,
        "role": lane.role,
        "repetition": lane.repetition,
        "attempt_number": attempt_number,
        "started_at": started_at,
        "finished_at": finished_at,
        "runner_command": command,
        "runner_exit_code": command_result.returncode,
        "verdict": "verdict.json",
        "operational_interventions": interventions,
    }
    (attempt_dir / "attempt.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_manifest(attempt_dir)
    return AttemptRecord(
        lane_id=lane.lane_id,
        attempt_number=attempt_number,
        directory=attempt_dir,
        verdict_path=verdict_path,
        runner_exit_code=command_result.returncode,
    )


def plan_lanes(manifest: ReliabilityManifest) -> list[dict]:
    """Report the next valid action for every planned M3 lane."""
    plan: list[dict] = []
    for lane in manifest.lanes:
        raw_attempts = sorted(lane.evidence_dir.glob("attempt-*"))
        status = "pending"
        attempts = raw_attempts
        try:
            if lane.evidence_dir.exists():
                unexpected = sorted(
                    path
                    for path in lane.evidence_dir.iterdir()
                    if path not in raw_attempts
                )
                if unexpected:
                    raise ValueError(
                        f"lane {lane.lane_id} contains stale evidence: "
                        + ", ".join(path.name for path in unexpected)
                    )
            attempts = attempt_directories(lane)
            if attempts:
                _, verdict = load_verified_attempt(
                    attempts[-1], lane=lane, attempt_number=len(attempts)
                )
                if is_accountable(verdict):
                    status = "accountable_complete"
                elif len(attempts) < manifest.max_attempts_per_lane:
                    status = "retryable"
                else:
                    status = "non_accountable_exhausted"
        except ValueError as error:
            status = (
                "artifact_integrity_failure"
                if "artifact_integrity" in str(error)
                else "invalid_evidence"
            )
        plan.append(
            {
                "lane_id": lane.lane_id,
                "role": lane.role,
                "repetition": lane.repetition,
                "attempts": len(attempts),
                "status": status,
            }
        )
    return plan


def build_summary(manifest: ReliabilityManifest) -> ReliabilitySummary:
    """Derive reliability outcomes from checksummed runner attempts."""
    return _build_progress(manifest, allow_pending=False).summary


def build_progress(manifest: ReliabilityManifest) -> ReliabilityProgress:
    """Derive a partial aggregate while retaining explicit pending lane identities."""
    return _build_progress(manifest, allow_pending=True)


def _build_progress(
    manifest: ReliabilityManifest, *, allow_pending: bool
) -> ReliabilityProgress:
    first_accountable = 0
    eventual_accountable = 0
    retry_count = 0
    controls: Counter[str] = Counter()
    defects: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    total_seconds = 0.0
    judge_seconds = 0.0
    interventions = 0
    pending_lane_ids: list[str] = []

    for lane in manifest.lanes:
        attempts = attempt_directories(lane)
        if not attempts:
            if not allow_pending:
                raise ValueError(f"lane {lane.lane_id} has no attempt evidence")
            pending_lane_ids.append(lane.lane_id)
            continue
        if len(attempts) > manifest.max_attempts_per_lane:
            raise ValueError(f"lane {lane.lane_id} exceeds bounded retry policy")
        retry_count += len(attempts) - 1

        loaded: list[tuple[dict, dict]] = []
        for number, attempt_dir in enumerate(attempts, start=1):
            metadata, verdict = load_verified_attempt(
                attempt_dir, lane=lane, attempt_number=number
            )
            total_seconds += _timing_seconds(verdict, lane=lane)
            judge_seconds += _judge_timing_seconds(verdict, lane=lane)
            raw_interventions = metadata.get("operational_interventions", [])
            if not isinstance(raw_interventions, list):
                raise ValueError(f"lane {lane.lane_id} interventions must be a list")
            interventions += len(raw_interventions)
            loaded.append((metadata, verdict))

        if is_accountable(loaded[0][1]):
            first_accountable += 1
        if len(loaded) == 2 and is_accountable(loaded[0][1]):
            raise ValueError(f"lane {lane.lane_id} retries an accountable outcome")

        for _, verdict in loaded:
            if not is_accountable(verdict):
                failures[failure_class(verdict)] += 1

        eventual = loaded[-1][1]
        if not is_accountable(eventual):
            continue
        eventual_accountable += 1
        outcome = lane_outcome(lane, eventual)
        if lane.role == "baseline":
            controls[outcome] += 1
        else:
            defects[outcome] += 1

    return ReliabilityProgress(
        summary=ReliabilitySummary(
            planned_lanes=len(manifest.lanes),
            first_attempt_accountable=first_accountable,
            eventual_accountable=eventual_accountable,
            retry_count=retry_count,
            control_outcomes=dict(sorted(controls.items())),
            defect_outcomes=dict(sorted(defects.items())),
            failure_classes=dict(sorted(failures.items())),
            total_seconds=round(total_seconds, 3),
            judge_seconds=round(judge_seconds, 3),
            operational_interventions=interventions,
        ),
        pending_lane_ids=tuple(pending_lane_ids),
    )


def summary_to_dict(summary: ReliabilitySummary) -> dict:
    """Return the stable machine-readable M3 summary payload."""
    return asdict(summary)


def progress_to_dict(progress: ReliabilityProgress) -> dict:
    """Return a partial aggregate without merging pending lanes into outcomes."""
    return {
        **summary_to_dict(progress.summary),
        "pending_lanes": len(progress.pending_lane_ids),
        "pending_lane_ids": list(progress.pending_lane_ids),
    }


def render_markdown(summary: ReliabilitySummary, *, slice_id: str) -> str:
    """Render the audited human-readable view from the structured summary."""
    lines = [
        "# M3 Verification Agent Reliability Summary",
        "",
        f"Slice: `{slice_id}`",
        "",
        "## Accountability",
        "",
        "| Metric | Count |",
        "|---|---:|",
        f"| Planned lanes | {summary.planned_lanes} |",
        f"| First-attempt accountable | {summary.first_attempt_accountable} |",
        f"| Eventual accountable | {summary.eventual_accountable} |",
        f"| Retries | {summary.retry_count} |",
        f"| Operational interventions | {summary.operational_interventions} |",
        f"| Total attempt time (seconds) | {summary.total_seconds} |",
        f"| L3 judge time (seconds) | {summary.judge_seconds} |",
        "",
        "## Baseline Control Outcomes",
        "",
        _count_table(summary.control_outcomes),
        "",
        "## Injected-Defect Outcomes",
        "",
        _count_table(summary.defect_outcomes),
        "",
        "## Non-Accountable Failure Classes",
        "",
        _count_table(summary.failure_classes),
        "",
        "## Scope Boundary",
        "",
        "This bounded slice does not support a benchmark-wide detection-rate claim,",
        "benchmark-wide false-positive-rate claim, fully unattended Journey claim,",
        "cross-host claim, or visual-only/multimodal L3 claim.",
        "",
    ]
    return "\n".join(lines)



def main(argv: list[str] | None = None) -> int:
    """Plan, execute, or summarize the public M3 reliability seam."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    commands = parser.add_subparsers(dest="command", required=True)
    plan_parser = commands.add_parser("plan")
    plan_parser.add_argument("--json-output", type=Path)

    run_parser = commands.add_parser("run-lane")
    run_parser.add_argument("lane_id")
    run_parser.add_argument("--device", required=True)
    run_parser.add_argument("--workdir", type=Path, required=True)
    run_parser.add_argument("--python-executable", default=sys.executable)
    run_parser.add_argument("--intervention", action="append", default=[])

    summary_parser = commands.add_parser("summary")
    summary_parser.add_argument("--json-output", type=Path)
    summary_parser.add_argument("--markdown-output", type=Path)
    progress_parser = commands.add_parser("progress")
    progress_parser.add_argument("--json-output", type=Path)
    audit_parser = commands.add_parser("audit")
    audit_parser.add_argument("--environment", type=Path, required=True)
    audit_parser.add_argument("--json-output", type=Path)
    audit_parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    manifest_path = args.manifest
    if not manifest_path.is_absolute():
        manifest_path = repo_root / manifest_path
    manifest = load_manifest(manifest_path, repo_root=repo_root)

    if args.command == "plan":
        plan = plan_lanes(manifest)
        payload = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
        if args.json_output is None:
            print(payload, end="")
        else:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(payload, encoding="utf-8")
        return (
            2
            if any(
                row["status"] in {"artifact_integrity_failure", "invalid_evidence"}
                for row in plan
            )
            else 0
        )
    if args.command == "run-lane":
        attempt = run_lane(
            manifest,
            lane_id=args.lane_id,
            device=args.device,
            workdir=args.workdir,
            python_executable=args.python_executable,
            operational_interventions=args.intervention,
        )
        print(
            json.dumps(
                {
                    "lane_id": attempt.lane_id,
                    "attempt_number": attempt.attempt_number,
                    "directory": str(attempt.directory),
                    "verdict": str(attempt.verdict_path),
                    "runner_exit_code": attempt.runner_exit_code,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "progress":
        payload = progress_to_dict(build_progress(manifest))
        output = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if args.json_output is None:
            print(output, end="")
        else:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(output, encoding="utf-8")
        return 0

    if args.command == "audit":
        from aiverify.bench.m3_audit import (
            audited_report_to_dict,
            build_audited_report,
            render_audited_markdown,
        )

        environment_path = args.environment
        if not environment_path.is_absolute():
            environment_path = repo_root / environment_path
        report = build_audited_report(
            manifest,
            environment_path=environment_path,
        )
        payload = audited_report_to_dict(report)
        markdown = render_audited_markdown(report)
    else:
        summary = build_summary(manifest)
        payload = summary_to_dict(summary)
        markdown = render_markdown(summary, slice_id=manifest.slice_id)
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if args.markdown_output is not None:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown, encoding="utf-8")
    if args.json_output is None and args.markdown_output is None:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _count_table(counts: dict[str, int]) -> str:
    lines = ["| Outcome | Count |", "|---|---:|"]
    if not counts:
        lines.append("| None | 0 |")
    else:
        lines.extend(f"| `{key}` | {value} |" for key, value in sorted(counts.items()))
    return "\n".join(lines)


def _load_lane(raw: object, *, repo_root: Path) -> ReliabilityLane:
    if not isinstance(raw, dict):
        raise ValueError("M3 reliability lane must be a mapping")
    role = _required_str(raw, "role")
    if role not in _LANE_ROLES:
        raise ValueError(f"unsupported M3 reliability lane role: {role}")
    repetition = _required_int(raw, "repetition")
    if repetition < 1:
        raise ValueError("M3 reliability lane repetition must be positive")
    oracle_level = _required_str(raw, "expected_oracle_level")
    if oracle_level not in _ORACLE_LEVELS:
        raise ValueError(f"unsupported expected oracle level: {oracle_level}")

    return ReliabilityLane(
        lane_id=_required_str(raw, "id"),
        seed_id=_required_str(raw, "seed_id"),
        role=role,
        repetition=repetition,
        run_spec=repo_root / _required_str(raw, "run_spec"),
        evidence_dir=repo_root / _required_str(raw, "evidence_dir"),
        expected_oracle_level=oracle_level,
        expected_oracle_defect_class=_required_str(
            raw, "expected_oracle_defect_class"
        ),
    )


def _lane_by_id(manifest: ReliabilityManifest, lane_id: str) -> ReliabilityLane:
    for lane in manifest.lanes:
        if lane.lane_id == lane_id:
            return lane
    raise ValueError(f"unknown M3 reliability lane: {lane_id}")


def _next_attempt_number(
    lane: ReliabilityLane, *, manifest: ReliabilityManifest
) -> int:
    attempts = attempt_directories(lane)
    if not attempts:
        return 1
    if len(attempts) >= manifest.max_attempts_per_lane:
        raise ValueError(f"lane {lane.lane_id} exhausted its bounded retry")
    _, verdict = load_verified_attempt(
        attempts[-1], lane=lane, attempt_number=len(attempts)
    )
    execution = verdict["execution"]
    if execution.get("status") == "completed" or execution.get("accounting_eligible") is True:
        raise ValueError("accountable outcome must not be retried")
    if execution.get("status") != "non_accountable":
        raise ValueError(f"lane {lane.lane_id} previous attempt is not retryable")
    return len(attempts) + 1


def attempt_directories(lane: ReliabilityLane) -> list[Path]:
    """Return a lane's contiguous preserved attempt directories."""
    attempts = sorted(lane.evidence_dir.glob("attempt-*"))
    expected = [
        lane.evidence_dir / f"attempt-{number}"
        for number in range(1, len(attempts) + 1)
    ]
    if attempts != expected or any(not path.is_dir() for path in attempts):
        raise ValueError(f"lane {lane.lane_id} has invalid attempt lineage")
    return attempts


def load_verified_attempt(
    attempt_dir: Path, *, lane: ReliabilityLane, attempt_number: int
) -> tuple[dict, dict]:
    """Load one checksummed attempt after validating its authoritative contracts."""
    errors = verify_manifest(attempt_dir)
    if errors:
        raise ValueError(
            f"artifact_integrity for {lane.lane_id} attempt {attempt_number}: "
            + "; ".join(errors)
        )
    metadata = _load_json(attempt_dir / "attempt.json", label="attempt metadata")
    verdict = _load_json(attempt_dir / "verdict.json", label="runner verdict")
    _validate_attempt(metadata, lane=lane, attempt_number=attempt_number)
    _validate_verdict(verdict, lane=lane)
    _validate_l3_judge_artifacts(attempt_dir, verdict=verdict, lane=lane)
    _validate_runner_exit(metadata, verdict=verdict, lane=lane)
    return metadata, verdict


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


def _validate_attempt(
    metadata: dict, *, lane: ReliabilityLane, attempt_number: int
) -> None:
    expected = {
        "lane_id": lane.lane_id,
        "seed_id": lane.seed_id,
        "role": lane.role,
        "repetition": lane.repetition,
        "attempt_number": attempt_number,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise ValueError(
                f"lane {lane.lane_id} attempt metadata {key} mismatch: "
                f"{metadata.get(key)!r}"
            )


def _validate_verdict(verdict: dict, *, lane: ReliabilityLane) -> None:
    if verdict.get("scenario") != lane.seed_id:
        raise ValueError(f"lane {lane.lane_id} verdict scenario mismatch")
    execution = verdict.get("execution")
    if not isinstance(execution, dict):
        raise ValueError(f"lane {lane.lane_id} verdict is missing execution")
    status = execution.get("status")
    if status not in {"completed", "non_accountable"}:
        raise ValueError(f"lane {lane.lane_id} has unsupported execution status: {status}")
    accounting_eligible = execution.get("accounting_eligible")
    expected_eligible = status == "completed"
    if accounting_eligible is not expected_eligible:
        raise ValueError(
            f"lane {lane.lane_id} accountability metadata contradicts execution status"
        )

    metric_context = verdict.get("metric_context")
    if not isinstance(metric_context, dict):
        raise ValueError(f"lane {lane.lane_id} verdict is missing metric_context")
    if metric_context.get("seed_id") != lane.seed_id:
        raise ValueError(f"lane {lane.lane_id} metric_context seed_id mismatch")
    seed_outcome = metric_context.get("seed_outcome")
    if not isinstance(seed_outcome, str) or not seed_outcome:
        raise ValueError(f"lane {lane.lane_id} metric_context seed_outcome is invalid")

    if status == "non_accountable":
        if seed_outcome != "not_accountable":
            raise ValueError(
                f"lane {lane.lane_id} non-accountable verdict must use "
                "seed_outcome=not_accountable"
            )
        if any(isinstance(verdict.get(key), dict) for key in ("l1", "l2", "l3")):
            raise ValueError(
                f"lane {lane.lane_id} non-accountable verdict contains oracle outcome"
            )
        failure_class(verdict)
    elif seed_outcome == "not_accountable":
        raise ValueError(
            f"lane {lane.lane_id} accountable verdict cannot use "
            "seed_outcome=not_accountable"
        )

    _timing_seconds(verdict, lane=lane)


def _validate_runner_exit(
    metadata: dict, *, verdict: dict, lane: ReliabilityLane
) -> None:
    actual = metadata.get("runner_exit_code")
    if not isinstance(actual, int) or isinstance(actual, bool):
        raise ValueError(f"lane {lane.lane_id} runner exit code is invalid")
    if is_accountable(verdict):
        detected = any(
            isinstance(value, dict) and value.get("outcome") == "fail"
            for value in (verdict.get("l1"), verdict.get("l2"), verdict.get("l3"))
        )
        expected = 1 if detected else 0
    else:
        expected = 2
    if actual != expected:
        raise ValueError(
            f"lane {lane.lane_id} runner exit mismatch: expected {expected}, got {actual}"
        )


def _validate_l3_judge_artifacts(
    attempt_dir: Path, *, verdict: dict, lane: ReliabilityLane
) -> None:
    if lane.expected_oracle_level != "L3" or not is_accountable(verdict):
        return

    spec = load_run_spec(lane.run_spec)
    judge_dir = attempt_dir / "artifacts" / "l3-judge"
    prompts = sorted(judge_dir.glob("l3-judge-call-*.prompt.md"))
    outputs = sorted(
        path
        for path in judge_dir.glob("l3-judge-call-*.md")
        if not path.name.endswith(".prompt.md")
    )
    events = sorted(judge_dir.glob("l3-judge-call-*.events.jsonl"))
    prompt_ids = [
        path.name.removeprefix("l3-judge-call-").removesuffix(".prompt.md")
        for path in prompts
    ]
    output_ids = [
        path.name.removeprefix("l3-judge-call-").removesuffix(".md")
        for path in outputs
    ]
    event_ids = [
        path.name.removeprefix("l3-judge-call-").removesuffix(".events.jsonl")
        for path in events
    ]
    expected_ids = [str(index) for index in range(1, len(prompts) + 1)]
    if not 1 <= len(prompts) <= 2 or not (
        len(prompts) == len(outputs) == len(events)
        and prompt_ids == output_ids == event_ids == expected_ids
    ):
        raise ValueError(
            f"lane {lane.lane_id} L3 judge input/output inventory is invalid"
        )

    checkpoints = verdict.get("checkpoints")
    if (
        not isinstance(checkpoints, list)
        or not checkpoints
        or not isinstance(checkpoints[-1], str)
    ):
        raise ValueError(f"lane {lane.lane_id} L3 checkpoint lineage is invalid")
    layout_path = attempt_dir / "artifacts" / checkpoints[-1] / "layout.json"
    if not layout_path.is_file():
        raise ValueError(f"lane {lane.lane_id} L3 final layout is missing")
    layout_text = layout_path.read_text(encoding="utf-8")

    leaked_values = [spec.scenario.expected_behavior.strip()]
    if spec.diff is not None and spec.diff.is_file():
        leaked_values.append(spec.diff.read_text(encoding="utf-8").strip())

    for prompt_path, output_path, events_path in zip(prompts, outputs, events):
        prompt = prompt_path.read_text(encoding="utf-8")
        output = output_path.read_text(encoding="utf-8").strip()
        events_text = events_path.read_text(encoding="utf-8").strip()
        if spec.scenario.l3_spec not in prompt or layout_text not in prompt:
            raise ValueError(
                f"lane {lane.lane_id} L3 judge input omits spec or observed layout"
            )
        if any(value and value in prompt for value in leaked_values):
            raise ValueError(
                f"lane {lane.lane_id} L3 judge input leaks expected_behavior or patch"
            )
        if output and output in prompt:
            raise ValueError(
                f"lane {lane.lane_id} L3 judge input leaks a frozen answer"
            )
        if not output or not events_text:
            raise ValueError(
                f"lane {lane.lane_id} L3 judge output evidence is incomplete"
            )

    try:
        final_output = json.loads(
            extract_json_block(outputs[-1].read_text(encoding="utf-8"))
        )
        if not isinstance(final_output, dict):
            raise ValueError("final L3 judge output is not an object")
        validate_verdict(final_output)
    except (json.JSONDecodeError, VerdictValidationError, ValueError) as error:
        raise ValueError(
            f"lane {lane.lane_id} final L3 judge output is invalid: {error}"
        ) from error
    if final_output != verdict.get("l3"):
        raise ValueError(
            f"lane {lane.lane_id} final L3 judge output contradicts runner verdict"
        )


def is_accountable(verdict: dict) -> bool:
    """Return whether a runner verdict is eligible for oracle accounting."""
    execution = verdict["execution"]
    return execution.get("status") == "completed" and execution.get(
        "accounting_eligible"
    ) is True


def lane_outcome(lane: ReliabilityLane, verdict: dict) -> str:
    """Classify an accountable lane without hiding benchmark inconsistencies."""
    oracle_verdicts = [
        value for key in ("l1", "l2", "l3")
        if isinstance((value := verdict.get(key)), dict)
    ]
    failures = [value for value in oracle_verdicts if value.get("outcome") == "fail"]
    if lane.role == "baseline":
        return "false_positive" if failures else "passed_control"

    expected_key = lane.expected_oracle_level.lower()
    expected = verdict.get(expected_key)
    if not isinstance(expected, dict) or expected.get("outcome") != "fail":
        if failures:
            return "wrong_oracle"
        return "missed"
    actual_class = expected.get("defect_class_hypothesis")
    if actual_class != lane.expected_oracle_defect_class:
        return "wrong_defect_class"
    return "caught"


def failure_class(verdict: dict) -> str:
    """Map a non-accountable runner reason to its audited failure class."""
    reason = verdict["execution"].get("reason")
    mapping = {
        "live_validation_preflight_failed": "preflight_environment",
        "journey_backend_error": "verification_agent_journey",
        "journey_action_failed": "verification_agent_journey",
        "journey_action_incomplete": "verification_agent_journey",
        "checkpoint_capture_error": "evidence_capture",
        "system_event_error": "system_event",
        "oracle_execution_error": "oracle_execution",
    }
    failure_class = mapping.get(str(reason))
    if failure_class is None:
        raise ValueError(
            f"unsupported non-accountable failure reason: {reason!r}"
        )
    return failure_class


def _timing_seconds(verdict: dict, *, lane: ReliabilityLane) -> float:
    timing = verdict.get("timing")
    value = timing.get("total_seconds") if isinstance(timing, dict) else None
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(f"lane {lane.lane_id} timing.total_seconds is invalid")
    return float(value)


def _judge_timing_seconds(verdict: dict, *, lane: ReliabilityLane) -> float:
    timing = verdict.get("timing")
    phases = timing.get("phases") if isinstance(timing, dict) else None
    if not isinstance(phases, list):
        raise ValueError(f"lane {lane.lane_id} timing.phases is invalid")

    judge_phases = [
        phase
        for phase in phases
        if isinstance(phase, dict) and phase.get("phase") == "l3-judge"
    ]
    if lane.expected_oracle_level != "L3" and judge_phases:
        raise ValueError(f"lane {lane.lane_id} has contradictory L3 judge timing")
    if not is_accountable(verdict) and judge_phases:
        raise ValueError(
            f"lane {lane.lane_id} non-accountable attempt has L3 judge timing"
        )
    if (
        lane.expected_oracle_level == "L3"
        and is_accountable(verdict)
        and len(judge_phases) != 1
    ):
        raise ValueError(f"lane {lane.lane_id} L3 judge timing is missing or duplicated")

    total = 0.0
    for phase in judge_phases:
        value = phase.get("seconds")
        if (
            phase.get("kind") != "oracle"
            or not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError(f"lane {lane.lane_id} L3 judge timing is invalid")
        total += float(value)
    return total



def _required_str(raw: dict, key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"M3 reliability {key} must be a non-empty string")
    return value


def _required_int(raw: dict, key: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"M3 reliability {key} must be an integer")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
