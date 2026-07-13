"""M2-beta benchmark slice aggregation."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from aiverify.runner.run_spec import load_run_spec


_DEFAULT_MANIFEST = Path("bench/goldset/m2-beta-slice.yaml")
_ACCOUNTING_STATES = frozenset({"included", "blocked", "candidate", "excluded"})
_CONTROL_OUTCOMES = frozenset({"passed_control", "false_positive"})
_ORACLE_KEYS = ("l1", "l2", "l3")
_LEVEL_TO_KEY = {"L1": "l1", "L2": "l2", "L3": "l3"}


@dataclass(frozen=True)
class SeedRecord:
    """One seed row in the M2-beta accounting manifest."""

    seed_id: str
    accounting_state: str
    candidate: bool
    evidence_type: str
    defect_outcome: str | None
    control_outcome: str | None
    taxonomy_category: str
    taxonomy_pattern_id: str
    expected_oracle_level: str
    expected_oracle_defect_class: str
    run_records: tuple[str, ...]
    source_issues: tuple[str, ...]
    evidence_contract: str
    evidence_notes: tuple[str, ...]
    reason: str | None = None


@dataclass(frozen=True)
class RepeatabilityRecord:
    """One fixed-evidence repeatability package."""

    package_id: str
    seed_id: str
    run_record: str
    total_calls: int
    baseline_passes: int
    defect_fails: int
    errors: int
    source_issues: tuple[str, ...]


@dataclass(frozen=True)
class M2BetaSummary:
    """Aggregated M2-beta benchmark slice counts."""

    seeds: tuple[SeedRecord, ...]
    repeatability_packages: tuple[RepeatabilityRecord, ...]
    state_counts: dict[str, int]
    candidate_count: int
    defect_outcomes: dict[str, int]
    control_outcomes: dict[str, int]
    expected_oracle_levels: dict[str, int]
    taxonomy_categories: dict[str, int]
    oracle_defect_classes: dict[str, int]
    evidence_contracts: dict[str, int]
    repeatability_totals: dict[str, int]


def build_summary(repo_root: Path) -> M2BetaSummary:
    """Build the M2-beta summary from committed manifest and run specs."""

    manifest = _load_yaml(repo_root / _DEFAULT_MANIFEST)
    raw_seeds = manifest.get("seeds", [])
    raw_repeatability = manifest.get("repeatability_packages", [])
    if not isinstance(raw_seeds, list):
        raise ValueError("m2-beta manifest seeds must be a list")
    if not isinstance(raw_repeatability, list):
        raise ValueError("m2-beta manifest repeatability_packages must be a list")

    seeds = tuple(_load_seed(repo_root, row) for row in raw_seeds)
    repeatability_packages = tuple(
        _load_repeatability(repo_root, row) for row in raw_repeatability
    )
    included = [seed for seed in seeds if seed.accounting_state == "included"]

    return M2BetaSummary(
        seeds=seeds,
        repeatability_packages=repeatability_packages,
        state_counts=_sorted_counter(seed.accounting_state for seed in seeds),
        candidate_count=sum(1 for seed in seeds if seed.candidate),
        defect_outcomes=_sorted_counter(
            seed.defect_outcome for seed in included if seed.defect_outcome
        ),
        control_outcomes=_sorted_counter(
            seed.control_outcome for seed in included if seed.control_outcome
        ),
        expected_oracle_levels=_sorted_counter(
            seed.expected_oracle_level for seed in included
        ),
        taxonomy_categories=_sorted_counter(seed.taxonomy_category for seed in included),
        oracle_defect_classes=_sorted_counter(
            seed.expected_oracle_defect_class for seed in included
        ),
        evidence_contracts=_sorted_counter(seed.evidence_contract for seed in included),
        repeatability_totals={
            "packages": len(repeatability_packages),
            "total_calls": sum(pkg.total_calls for pkg in repeatability_packages),
            "baseline_passes": sum(pkg.baseline_passes for pkg in repeatability_packages),
            "defect_fails": sum(pkg.defect_fails for pkg in repeatability_packages),
            "errors": sum(pkg.errors for pkg in repeatability_packages),
        },
    )


def render_markdown(summary: M2BetaSummary) -> str:
    """Render a deterministic Markdown summary for docs."""

    lines = [
        "# M2-beta Aggregate Summary",
        "",
        "Generated from `bench/goldset/m2-beta-slice.yaml`, run-spec",
        "`scenario.metric_context` metadata, committed lane verdicts, and",
        "fixed-evidence repeatability summaries.",
        "",
        "## Accounting Summary",
        "",
        "| Bucket | Count |",
        "|---|---:|",
        f"| Included injected-defect seeds | {summary.state_counts.get('included', 0)} |",
        f"| Blocked seeds | {summary.state_counts.get('blocked', 0)} |",
        f"| Candidate seeds | {summary.candidate_count} |",
        f"| Repeatability-only packages | {summary.repeatability_totals['packages']} |",
        "",
        "## Included Injected-Defect Outcomes",
        "",
        _table_from_counts(summary.defect_outcomes, "Outcome"),
        "",
        "## Baseline Control Outcomes",
        "",
        _table_from_counts(summary.control_outcomes, "Outcome"),
        "",
        "## Expected Oracle Levels",
        "",
        _table_from_counts(summary.expected_oracle_levels, "Oracle level"),
        "",
        "## Taxonomy Coverage",
        "",
        _table_from_counts(summary.taxonomy_categories, "Taxonomy category"),
        "",
        "## Oracle Defect-Class Coverage",
        "",
        _table_from_counts(summary.oracle_defect_classes, "Oracle defect class"),
        "",
        "## Evidence Contracts",
        "",
        _table_from_counts(summary.evidence_contracts, "Evidence contract"),
        "",
        "Standard `verdict` lanes derive caught/missed and control outcomes from",
        "committed baseline/defect `verdict.json` files. `legacy_control_document`",
        "marks pre-runner-contract control evidence that is explicitly documented",
        "but does not have a standalone control verdict; it remains a legacy",
        "historical classification.",
        "",
        "## Blocked And Candidate Seeds",
        "",
        "| Seed | State | Candidate | Reason |",
        "|---|---|---:|---|",
    ]

    blocked_or_candidate = [
        seed for seed in summary.seeds
        if seed.accounting_state != "included" or seed.candidate
    ]
    if blocked_or_candidate:
        for seed in blocked_or_candidate:
            lines.append(
                f"| `{seed.seed_id}` | `{seed.accounting_state}` | "
                f"{str(seed.candidate).lower()} | {seed.reason or ''} |"
            )
    else:
        lines.append("| None | - | - | - |")

    lines.extend([
        "",
        "## Fixed-Evidence L3 Repeatability",
        "",
        "| Package | Seed | Calls | Baseline passes | Defect fails | Errors |",
        "|---|---|---:|---:|---:|---:|",
    ])
    for package in summary.repeatability_packages:
        lines.append(
            f"| `{package.package_id}` | `{package.seed_id}` | "
            f"{package.total_calls} | {package.baseline_passes} | "
            f"{package.defect_fails} | {package.errors} |"
        )

    lines.extend([
        "",
        "Fixed-evidence repeatability supports the bounded L3 stability claim.",
        "It does not add extra caught, missed, or control outcomes.",
        "",
        "## Scope Boundary",
        "",
        "This is a small M2-beta benchmark slice summary. It is not a",
        "benchmark-wide detection-rate claim, benchmark-wide false-positive-rate",
        "claim, ColorOS migration claim, or fully unattended Journey reliability",
        "claim.",
        "",
    ])
    return "\n".join(lines)


def write_summary(repo_root: Path, output: Path) -> None:
    """Write the rendered M2-beta Markdown summary."""

    output.write_text(render_markdown(build_summary(repo_root)), encoding="utf-8")


def _load_seed(repo_root: Path, row: object) -> SeedRecord:
    if not isinstance(row, dict):
        raise ValueError("m2-beta seed rows must be mappings")

    seed_id = _required_str(row, "id")
    run_spec_path = _required_str(row, "run_spec")
    spec = load_run_spec(repo_root / "bench" / "goldset" / run_spec_path)
    metric = spec.scenario.metric_context
    if spec.scenario.id != seed_id:
        raise ValueError(f"seed id mismatch for {seed_id}: {spec.scenario.id}")
    if metric.seed_kind != "injected_defect":
        raise ValueError(f"{seed_id} must use metric_context.seed_kind=injected_defect")

    accounting_state = _required_choice(row, "accounting_state", _ACCOUNTING_STATES)
    if "defect_outcome" in row or "control_outcome" in row:
        raise ValueError(
            f"{seed_id} uses manual outcome fields; outcomes must be derived "
            "from committed evidence"
        )

    defect_outcome = None
    control_outcome = None
    evidence_contract = "not_accounted"
    evidence_notes: tuple[str, ...] = ()
    if accounting_state == "included":
        evidence = _required_mapping(row, "evidence")
        defect_outcome, defect_notes = _resolve_verdict_outcome(
            repo_root,
            seed_id=seed_id,
            role="defect",
            raw=_required_mapping(evidence, "defect"),
            metric=metric,
        )
        control_outcome, control_notes = _resolve_control_outcome(
            repo_root,
            seed_id=seed_id,
            raw=_required_mapping(evidence, "control"),
            metric=metric,
        )
        evidence_notes = (*defect_notes, *control_notes)
        evidence_contract = (
            "legacy_control_document"
            if any(note.startswith("legacy_control_document:") for note in evidence_notes)
            else "verdict"
        )

    return SeedRecord(
        seed_id=seed_id,
        accounting_state=accounting_state,
        candidate=bool(row.get("candidate", False)),
        evidence_type=_required_str(row, "evidence_type"),
        defect_outcome=defect_outcome,
        control_outcome=control_outcome,
        taxonomy_category=_require_metric(
            metric.taxonomy_category, seed_id, "taxonomy_category"
        ),
        taxonomy_pattern_id=_require_metric(
            metric.taxonomy_pattern_id, seed_id, "taxonomy_pattern_id"
        ),
        expected_oracle_level=_require_metric(
            metric.expected_oracle_level, seed_id, "expected_oracle_level"
        ),
        expected_oracle_defect_class=_require_metric(
            metric.expected_oracle_defect_class, seed_id, "expected_oracle_defect_class"
        ),
        run_records=tuple(_str_list(row.get("run_records", []), "run_records")),
        source_issues=tuple(_str_list(row.get("source_issues", []), "source_issues")),
        evidence_contract=evidence_contract,
        evidence_notes=evidence_notes,
        reason=_optional_str(row, "reason"),
    )


def _resolve_verdict_outcome(
    repo_root: Path,
    *,
    seed_id: str,
    role: str,
    raw: dict[str, Any],
    metric,
) -> tuple[str, tuple[str, ...]]:
    if "outcome" in raw:
        raise ValueError(
            f"{seed_id} {role} evidence uses manual outcome; outcomes must be "
            "derived from committed verdict evidence"
        )
    verdict_path = repo_root / _required_str(raw, "verdict")
    if not verdict_path.is_file():
        raise ValueError(f"{seed_id} missing {role} verdict: {verdict_path}")
    selector = _optional_str(raw, "selector") or "root"
    payload = _load_json(verdict_path)
    lane = _select_verdict_lane(payload, selector, seed_id=seed_id, role=role)
    notes = _validate_verdict_lane(
        lane,
        payload=payload,
        selector=selector,
        seed_id=seed_id,
        role=role,
        metric=metric,
        path=verdict_path,
    )
    failed = _failed_oracles(lane)
    if role == "defect":
        if failed:
            _validate_expected_defect_signal(
                lane,
                seed_id=seed_id,
                metric=metric,
                path=verdict_path,
            )
        return ("caught" if failed else "missed"), notes
    if role == "control":
        return ("false_positive" if failed else "passed_control"), notes
    raise ValueError(f"unsupported evidence role: {role}")


def _resolve_control_outcome(
    repo_root: Path,
    *,
    seed_id: str,
    raw: dict[str, Any],
    metric,
) -> tuple[str, tuple[str, ...]]:
    if "legacy_document" in raw:
        if "verdict" in raw:
            raise ValueError(f"{seed_id} control evidence cannot mix legacy and verdict")
        document = repo_root / _required_str(raw, "legacy_document")
        if not document.is_file():
            raise ValueError(f"{seed_id} missing legacy control document: {document}")
        outcome = _required_choice(raw, "outcome", _CONTROL_OUTCOMES)
        return outcome, (f"legacy_control_document:{document}",)
    return _resolve_verdict_outcome(
        repo_root,
        seed_id=seed_id,
        role="control",
        raw=raw,
        metric=metric,
    )


def _select_verdict_lane(
    payload: dict[str, Any],
    selector: str,
    *,
    seed_id: str,
    role: str,
) -> dict[str, Any]:
    if selector == "root":
        return payload
    selected = payload.get(selector)
    if not isinstance(selected, dict):
        raise ValueError(f"{seed_id} {role} verdict selector not found: {selector}")
    return selected


def _validate_verdict_lane(
    lane: dict[str, Any],
    *,
    payload: dict[str, Any],
    selector: str,
    seed_id: str,
    role: str,
    metric,
    path: Path,
) -> tuple[str, ...]:
    notes: list[str] = []
    scenario = lane.get("scenario") if selector != "root" else payload.get("scenario")
    if scenario is None:
        notes.append(f"legacy_no_scenario:{path}")
    elif scenario != seed_id:
        raise ValueError(
            f"{seed_id} {role} verdict scenario mismatch at {path}: {scenario}"
        )

    execution = lane.get("execution") if selector != "root" else payload.get("execution")
    if execution is None:
        notes.append(f"legacy_no_execution_contract:{path}")
    else:
        if not isinstance(execution, dict):
            raise ValueError(f"{seed_id} {role} verdict execution must be a mapping")
        if (
            execution.get("status") == "non_accountable"
            or execution.get("accounting_eligible") is False
        ):
            raise ValueError(f"{seed_id} {role} verdict is non-accountable: {path}")
        if execution.get("status") not in (None, "completed"):
            raise ValueError(
                f"{seed_id} {role} verdict has unsupported execution status "
                f"{execution.get('status')!r}: {path}"
            )

    metric_context = (
        lane.get("metric_context") if selector != "root" else payload.get("metric_context")
    )
    if metric_context is None:
        notes.append(f"legacy_no_metric_context:{path}")
    else:
        if not isinstance(metric_context, dict):
            raise ValueError(f"{seed_id} {role} metric_context must be a mapping")
        _validate_metric_context(metric_context, seed_id=seed_id, role=role, metric=metric)

    if not any(isinstance(lane.get(key), dict) for key in _ORACLE_KEYS):
        raise ValueError(f"{seed_id} {role} verdict has no oracle verdicts: {path}")
    return tuple(notes)


def _validate_metric_context(
    metric_context: dict[str, Any],
    *,
    seed_id: str,
    role: str,
    metric,
) -> None:
    if metric_context.get("seed_id") != seed_id:
        raise ValueError(
            f"{seed_id} {role} metric_context.seed_id mismatch: "
            f"{metric_context.get('seed_id')!r}"
        )
    expected = {
        "seed_kind": metric.seed_kind,
        "taxonomy_category": metric.taxonomy_category,
        "taxonomy_pattern_id": metric.taxonomy_pattern_id,
        "expected_oracle_level": metric.expected_oracle_level,
        "expected_oracle_defect_class": metric.expected_oracle_defect_class,
    }
    for key, value in expected.items():
        if metric_context.get(key) != value:
            raise ValueError(
                f"{seed_id} {role} metric_context.{key} mismatch: "
                f"{metric_context.get(key)!r}"
            )


def _failed_oracles(lane: dict[str, Any]) -> list[dict[str, Any]]:
    verdicts = []
    for key in _ORACLE_KEYS:
        verdict = lane.get(key)
        if isinstance(verdict, dict) and verdict.get("outcome") == "fail":
            verdicts.append(verdict)
    return verdicts


def _validate_expected_defect_signal(
    lane: dict[str, Any],
    *,
    seed_id: str,
    metric,
    path: Path,
) -> None:
    expected_level = _require_metric(
        metric.expected_oracle_level,
        seed_id,
        "expected_oracle_level",
    )
    level_key = _LEVEL_TO_KEY[expected_level]
    expected = lane.get(level_key)
    if not isinstance(expected, dict) or expected.get("outcome") != "fail":
        raise ValueError(
            f"{seed_id} defect verdict does not fail expected oracle "
            f"{metric.expected_oracle_level}: {path}"
        )
    if expected.get("defect_class_hypothesis") != metric.expected_oracle_defect_class:
        raise ValueError(
            f"{seed_id} defect verdict expected class mismatch at {path}: "
            f"{expected.get('defect_class_hypothesis')!r}"
        )


def _load_repeatability(repo_root: Path, row: object) -> RepeatabilityRecord:
    if not isinstance(row, dict):
        raise ValueError("m2-beta repeatability rows must be mappings")
    run_record = _required_str(row, "run_record")
    summary_path = repo_root / run_record / "summary.json"
    if not summary_path.is_file():
        raise ValueError(f"missing repeatability summary: {summary_path}")
    summary = _load_json(summary_path)
    return RepeatabilityRecord(
        package_id=_required_str(row, "id"),
        seed_id=_required_str(row, "seed_id"),
        run_record=run_record,
        total_calls=_required_int(summary, "total_iterations"),
        baseline_passes=_repeatability_outcome_count(summary, "baseline", "pass"),
        defect_fails=_repeatability_outcome_count(summary, "defect", "fail"),
        errors=_required_int(summary, "total_errors"),
        source_issues=tuple(_str_list(row.get("source_issues", []), "source_issues")),
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a mapping")
    return data


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a JSON object")
    return data


def _repeatability_outcome_count(
    summary: dict[str, Any],
    half: str,
    outcome: str,
) -> int:
    by_half = summary.get("by_half")
    if not isinstance(by_half, dict):
        raise ValueError("repeatability summary requires by_half mapping")
    half_summary = by_half.get(half)
    if not isinstance(half_summary, dict):
        raise ValueError(f"repeatability summary requires {half} half")
    outcomes = half_summary.get("outcomes")
    if not isinstance(outcomes, dict):
        raise ValueError(f"repeatability summary requires {half}.outcomes")
    value = outcomes.get(outcome, 0)
    if not isinstance(value, int):
        raise ValueError(f"repeatability {half}.{outcome} count must be integer")
    return value


def _sorted_counter(values) -> dict[str, int]:
    counts = Counter(values)
    return {key: counts[key] for key in sorted(counts)}


def _table_from_counts(counts: dict[str, int], label: str) -> str:
    lines = [f"| {label} | Count |", "|---|---:|"]
    if not counts:
        lines.append("| None | 0 |")
    else:
        for key, count in counts.items():
            lines.append(f"| `{key}` | {count} |")
    return "\n".join(lines)


def _required_str(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"m2-beta manifest requires non-empty string {key}")
    return value


def _optional_str(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"m2-beta manifest {key} must be a non-empty string or null")
    return value


def _required_choice(row: dict[str, Any], key: str, allowed: frozenset[str]) -> str:
    value = _required_str(row, key)
    if value not in allowed:
        expected = ", ".join(sorted(allowed))
        raise ValueError(f"m2-beta manifest {key} must be one of: {expected}")
    return value


def _required_int(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if not isinstance(value, int):
        raise ValueError(f"m2-beta manifest requires integer {key}")
    return value


def _required_mapping(row: dict[str, Any], key: str) -> dict[str, Any]:
    value = row.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"m2-beta manifest requires mapping {key}")
    return value


def _str_list(value: object, key: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"m2-beta manifest {key} must be a string list")
    return value


def _require_metric(value: str | None, seed_id: str, field: str) -> str:
    if not value:
        raise ValueError(f"{seed_id} is missing metric_context.{field}")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    rendered = render_markdown(build_summary(args.repo_root))
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
