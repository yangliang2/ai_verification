"""M2-beta benchmark slice aggregation."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from aiverify.runner.run_spec import load_run_spec


_DEFAULT_MANIFEST = Path("bench/goldset/m2-beta-slice.yaml")
_ACCOUNTING_STATES = frozenset({"included", "blocked", "candidate", "excluded"})
_DEFECT_OUTCOMES = frozenset({"caught", "missed"})
_CONTROL_OUTCOMES = frozenset({"passed_control", "false_positive"})


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
    repeatability_packages = tuple(_load_repeatability(row) for row in raw_repeatability)
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
        "Generated from `bench/goldset/m2-beta-slice.yaml` and run-spec",
        "`scenario.metric_context` metadata.",
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
    defect_outcome = _optional_choice(row, "defect_outcome", _DEFECT_OUTCOMES)
    control_outcome = _optional_choice(row, "control_outcome", _CONTROL_OUTCOMES)
    if accounting_state == "included" and defect_outcome is None:
        raise ValueError(f"{seed_id} included seeds require defect_outcome")

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
        reason=_optional_str(row, "reason"),
    )


def _load_repeatability(row: object) -> RepeatabilityRecord:
    if not isinstance(row, dict):
        raise ValueError("m2-beta repeatability rows must be mappings")
    return RepeatabilityRecord(
        package_id=_required_str(row, "id"),
        seed_id=_required_str(row, "seed_id"),
        run_record=_required_str(row, "run_record"),
        total_calls=_required_int(row, "total_calls"),
        baseline_passes=_required_int(row, "baseline_passes"),
        defect_fails=_required_int(row, "defect_fails"),
        errors=_required_int(row, "errors"),
        source_issues=tuple(_str_list(row.get("source_issues", []), "source_issues")),
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a mapping")
    return data


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


def _optional_choice(
    row: dict[str, Any],
    key: str,
    allowed: frozenset[str],
) -> str | None:
    value = _optional_str(row, key)
    if value is not None and value not in allowed:
        expected = ", ".join(sorted(allowed))
        raise ValueError(f"m2-beta manifest {key} must be one of: {expected}")
    return value


def _required_int(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if not isinstance(value, int):
        raise ValueError(f"m2-beta manifest requires integer {key}")
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
