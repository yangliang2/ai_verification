"""Repeatability measurement for the L3 semantic oracle.

The module reuses fixed observed evidence from an existing run and repeats only the
L3 judge call. This keeps the measurement device-independent while still exercising
the real L3Oracle + provider boundary.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Callable, Any

from aiverify.agent.oracle.l3 import L3Oracle
from aiverify.providers.base import LLMProvider
from aiverify.providers.codex_cli import CodexCliProvider
from aiverify.runner.run_spec import load_run_spec


ProviderFactory = Callable[[str, int, Path], LLMProvider]


@dataclass(frozen=True)
class L3RepeatabilityCase:
    """One fixed-evidence half of an L3 repeatability run."""

    half: str
    layout_path: Path
    screenshot_refs: tuple[str, ...] = ()
    journey_result_path: Path | None = None


def confidence_stats(values: list[float]) -> dict[str, float | None]:
    """Return min/median/max confidence with stable rounding."""
    if not values:
        return {"min": None, "median": None, "max": None}
    return {
        "min": round(min(values), 3),
        "median": round(float(median(values)), 3),
        "max": round(max(values), 3),
    }


def _duration_stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "median": None, "max": None, "total": 0.0}
    return {
        "min": round(min(values), 3),
        "median": round(float(median(values)), 3),
        "max": round(max(values), 3),
        "total": round(sum(values), 3),
    }


def _counter_dict(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def summarize_repeatability(calls: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-call L3 results into benchmark-auditable summary data."""
    halves = sorted({str(c["half"]) for c in calls})
    by_half: dict[str, Any] = {}
    total_errors = 0

    for half in halves:
        half_calls = [c for c in calls if c["half"] == half]
        verdicts = [c["verdict"] for c in half_calls if c.get("verdict") is not None]
        errors = [c["error"] for c in half_calls if c.get("error") is not None]
        total_errors += len(errors)

        confidences = [float(v["confidence"]) for v in verdicts]
        durations = [float(c["duration_seconds"]) for c in half_calls]
        classes = [
            str(v["defect_class_hypothesis"])
            if v["defect_class_hypothesis"] is not None
            else "null"
            for v in verdicts
        ]
        by_half[half] = {
            "iterations": len(half_calls),
            "valid_verdicts": len(verdicts),
            "error_count": len(errors),
            "outcomes": _counter_dict([str(v["outcome"]) for v in verdicts]),
            "defect_class_hypotheses": _counter_dict(classes),
            "confidence": confidence_stats(confidences),
            "timing_seconds": _duration_stats(durations),
            "errors": errors,
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_iterations": len(calls),
        "total_errors": total_errors,
        "by_half": by_half,
        "calls": calls,
    }


def build_trace_summary(case: L3RepeatabilityCase) -> str:
    """Build the observed-evidence prompt section without expected defect leakage."""
    parts = [
        f"### Fixed evidence half\n{case.half}",
        f"### Final checkpoint layout JSON ({case.layout_path})",
        case.layout_path.read_text(encoding="utf-8"),
    ]
    if case.journey_result_path is not None and case.journey_result_path.is_file():
        parts.insert(
            1,
            "### Driver journey result JSON\n"
            + case.journey_result_path.read_text(encoding="utf-8"),
        )
    return "\n\n".join(parts)


def run_repeatability(
    *,
    cases: list[L3RepeatabilityCase],
    l3_spec: str,
    repetitions: int,
    artifact_dir: Path,
    provider_factory: ProviderFactory,
    trigger_steps: list[str],
) -> dict[str, Any]:
    """Run repeated L3 judgments and return an aggregate summary."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    calls: list[dict[str, Any]] = []

    for case in cases:
        trace_summary = build_trace_summary(case)
        for iteration in range(1, repetitions + 1):
            iteration_dir = artifact_dir / case.half / f"iteration-{iteration:02d}"
            iteration_dir.mkdir(parents=True, exist_ok=True)
            provider = provider_factory(case.half, iteration, iteration_dir)
            start = time.monotonic()
            verdict: dict[str, Any] | None = None
            error: dict[str, str] | None = None
            try:
                verdict = L3Oracle(provider).judge(
                    trace_summary,
                    l3_spec,
                    screenshot_refs=list(case.screenshot_refs),
                    trigger_steps=trigger_steps,
                )
            except Exception as exc:  # noqa: BLE001 - measurement must record failures.
                error = {"type": type(exc).__name__, "message": str(exc)[:1000]}

            calls.append(
                {
                    "half": case.half,
                    "iteration": iteration,
                    "duration_seconds": round(time.monotonic() - start, 3),
                    "artifact_dir": str(iteration_dir),
                    "verdict": verdict,
                    "error": error,
                    "trace_summary_preview": trace_summary[:500],
                }
            )

    return summarize_repeatability(calls)


def write_summary(summary: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown_report(summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# L3 Repeatability Summary",
        "",
        f"Generated at: `{summary['generated_at']}`",
        f"Total iterations: **{summary['total_iterations']}**",
        f"Total errors: **{summary['total_errors']}**",
        "",
        "| Half | Iterations | Valid | Errors | Outcomes | Defect classes | Confidence min/median/max | Timing total |",
        "|---|---:|---:|---:|---|---|---|---:|",
    ]
    for half, data in summary["by_half"].items():
        conf = data["confidence"]
        lines.append(
            "| "
            + " | ".join(
                [
                    half,
                    str(data["iterations"]),
                    str(data["valid_verdicts"]),
                    str(data["error_count"]),
                    json.dumps(data["outcomes"], ensure_ascii=False, sort_keys=True),
                    json.dumps(
                        data["defect_class_hypotheses"],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    f"{conf['min']}/{conf['median']}/{conf['max']}",
                    str(data["timing_seconds"]["total"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Calls",
            "",
            "| Half | Iteration | Duration | Outcome | Defect class | Confidence | Error |",
            "|---|---:|---:|---|---|---:|---|",
        ]
    )
    for call in summary["calls"]:
        verdict = call.get("verdict")
        error = call.get("error")
        lines.append(
            "| "
            + " | ".join(
                [
                    str(call["half"]),
                    str(call["iteration"]),
                    str(call["duration_seconds"]),
                    str(verdict["outcome"] if verdict else ""),
                    str(verdict["defect_class_hypothesis"] if verdict else ""),
                    str(verdict["confidence"] if verdict else ""),
                    str(error["type"] if error else ""),
                ]
            )
            + " |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _default_cases(source_run_dir: Path, scenario_id: str) -> list[L3RepeatabilityCase]:
    cases: list[L3RepeatabilityCase] = []
    for half in ("baseline", "defect"):
        half_dir = source_run_dir / half / "artifacts"
        checkpoint = half_dir / "after-segment-0"
        cases.append(
            L3RepeatabilityCase(
                half=half,
                layout_path=checkpoint / "layout.json",
                screenshot_refs=(str(checkpoint / "screen.png"),),
                journey_result_path=(
                    half_dir / f"{scenario_id}-segment-0" / "codex-journey-result.json"
                ),
            )
        )
    return cases


def _provider_factory(
    *, workdir: Path, model: str | None
) -> ProviderFactory:
    def make_provider(_half: str, _iteration: int, artifact_dir: Path) -> LLMProvider:
        return CodexCliProvider(
            workdir=workdir,
            artifact_dir=artifact_dir / "l3-judge",
            model=model,
        )

    return make_provider


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--run-spec",
        type=Path,
        default=Path("bench/goldset/run-specs/wikipedia-ui-rendering-01-nav-label-swap.yaml"),
    )
    ap.add_argument(
        "--source-run-dir",
        type=Path,
        default=Path("docs/runs/2026-07-06-wikipedia-ui-rendering-01-nav-label-swap"),
    )
    ap.add_argument("--artifact-dir", required=True, type=Path)
    ap.add_argument("--repetitions", type=int, default=5)
    ap.add_argument("--workdir", type=Path, default=Path.cwd())
    ap.add_argument("--model", default=None)
    args = ap.parse_args(argv)

    spec = load_run_spec(args.run_spec)
    summary = run_repeatability(
        cases=_default_cases(args.source_run_dir, spec.scenario.id),
        l3_spec=spec.scenario.l3_spec,
        repetitions=args.repetitions,
        artifact_dir=args.artifact_dir,
        provider_factory=_provider_factory(workdir=args.workdir, model=args.model),
        trigger_steps=list(spec.scenario.user_actions),
    )
    run_dir = args.artifact_dir.parent
    write_summary(summary, run_dir / "summary.json")
    write_markdown_report(summary, run_dir / "l3-repeatability-report.md")
    print(json.dumps(summary["by_half"], ensure_ascii=False, indent=2))
    return 1 if summary["total_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
