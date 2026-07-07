from __future__ import annotations

import json
from pathlib import Path

from aiverify.bench.l3_repeatability import (
    L3RepeatabilityCase,
    confidence_stats,
    run_repeatability,
    summarize_repeatability,
    write_markdown_report,
)
from aiverify.providers.base import MockProvider


def _verdict(outcome: str, defect_class: str | None, confidence: float) -> str:
    return json.dumps(
        {
            "verdict_id": f"L3-{outcome[:4]}0000",
            "level": "L3",
            "outcome": outcome,
            "defect_class_hypothesis": defect_class,
            "trigger_steps": ["open app", "inspect nav labels"],
            "evidence": [
                {
                    "type": "llm_reasoning",
                    "ref": "fixture layout",
                    "note": "mocked semantic judgment",
                }
            ],
            "confidence": confidence,
        }
    )


def test_confidence_stats_handles_empty_and_orders_values() -> None:
    assert confidence_stats([]) == {"min": None, "median": None, "max": None}
    assert confidence_stats([0.9, 0.1, 0.7]) == {
        "min": 0.1,
        "median": 0.7,
        "max": 0.9,
    }


def test_summarize_repeatability_counts_outcomes_classes_confidence_and_errors() -> None:
    summary = summarize_repeatability(
        [
            {
                "half": "baseline",
                "iteration": 1,
                "duration_seconds": 1.0,
                "verdict": json.loads(_verdict("pass", None, 0.91)),
                "error": None,
            },
            {
                "half": "baseline",
                "iteration": 2,
                "duration_seconds": 2.0,
                "verdict": json.loads(_verdict("inconclusive", None, 0.2)),
                "error": None,
            },
            {
                "half": "defect",
                "iteration": 1,
                "duration_seconds": 3.0,
                "verdict": json.loads(_verdict("fail", "ui_rendering", 0.97)),
                "error": None,
            },
            {
                "half": "defect",
                "iteration": 2,
                "duration_seconds": 4.0,
                "verdict": None,
                "error": {"type": "RuntimeError", "message": "provider failed"},
            },
        ]
    )

    assert summary["total_iterations"] == 4
    assert summary["total_errors"] == 1

    baseline = summary["by_half"]["baseline"]
    assert baseline["outcomes"] == {"pass": 1, "inconclusive": 1}
    assert baseline["defect_class_hypotheses"] == {"null": 2}
    assert baseline["confidence"] == {"min": 0.2, "median": 0.555, "max": 0.91}
    assert baseline["timing_seconds"]["total"] == 3.0

    defect = summary["by_half"]["defect"]
    assert defect["outcomes"] == {"fail": 1}
    assert defect["defect_class_hypotheses"] == {"ui_rendering": 1}
    assert defect["errors"][0]["type"] == "RuntimeError"


def test_run_repeatability_uses_fixed_layout_evidence_and_records_artifact_dirs(
    tmp_path: Path,
) -> None:
    layout = tmp_path / "layout.json"
    layout.write_text('[{"resource-id":"nav_tab_search","content-desc":"Search"}]')
    case = L3RepeatabilityCase(
        half="baseline",
        layout_path=layout,
        screenshot_refs=("screen.png",),
    )

    calls: list[dict] = []

    def provider_factory(half: str, iteration: int, artifact_dir: Path):
        calls.append({"half": half, "iteration": iteration, "artifact_dir": artifact_dir})
        return MockProvider([_verdict("pass", None, 0.9)])

    summary = run_repeatability(
        cases=[case],
        l3_spec="nav_tab_search must show Search",
        repetitions=2,
        artifact_dir=tmp_path / "artifacts",
        provider_factory=provider_factory,
        trigger_steps=["inspect nav labels"],
    )

    assert summary["by_half"]["baseline"]["outcomes"] == {"pass": 2}
    assert [c["iteration"] for c in calls] == [1, 2]
    assert calls[0]["artifact_dir"].name == "iteration-01"
    assert "nav_tab_search" in summary["calls"][0]["trace_summary_preview"]


def test_write_markdown_report_renders_summary_table(tmp_path: Path) -> None:
    summary = summarize_repeatability(
        [
            {
                "half": "defect",
                "iteration": 1,
                "duration_seconds": 1.25,
                "verdict": json.loads(_verdict("fail", "ui_rendering", 0.98)),
                "error": None,
            }
        ]
    )

    report = tmp_path / "report.md"
    write_markdown_report(summary, report)

    text = report.read_text(encoding="utf-8")
    assert "# L3 Repeatability Summary" in text
    assert "| defect | 1 | 1 | 0 |" in text
    assert '"fail": 1' in text
