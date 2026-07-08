from __future__ import annotations

import json
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_SUMMARY_DOC = _ROOT / "docs" / "M2-l3-text-layout-summary.md"
_RUNS = {
    "ui-rendering-01": _ROOT / "docs/runs/2026-07-07-l3-repeatability-ui-rendering-01/summary.json",
    "ui-rendering-02": _ROOT / "docs/runs/2026-07-08-l3-repeatability-ui-rendering-02/summary.json",
}


def _load_summary(seed: str) -> dict:
    return json.loads(_RUNS[seed].read_text(encoding="utf-8"))


def _confidence_text(confidence: dict) -> str:
    return f"{confidence['min']} / {confidence['median']} / {confidence['max']}"


def test_m2_l3_text_layout_summary_matches_repeatability_json() -> None:
    text = _SUMMARY_DOC.read_text(encoding="utf-8")

    for seed in ("ui-rendering-01", "ui-rendering-02"):
        summary = _load_summary(seed)
        assert f"`{seed}`" in text
        assert summary["total_iterations"] == 10
        assert summary["total_errors"] == 0

        for half in ("baseline", "defect"):
            data = summary["by_half"][half]
            expected_row_parts = [
                f"| `{seed}` | {half} |",
                f"| {data['iterations']} | {data['valid_verdicts']} | {data['error_count']} |",
                _confidence_text(data["confidence"]),
                f"{data['timing_seconds']['total']}s |",
            ]
            for part in expected_row_parts:
                assert part in text

            for outcome, count in data["outcomes"].items():
                assert f"`{outcome}: {count}`" in text
            for defect_class, count in data["defect_class_hypotheses"].items():
                assert f"`{defect_class}: {count}`" in text


def test_m2_l3_text_layout_summary_preserves_boundaries() -> None:
    text = _SUMMARY_DOC.read_text(encoding="utf-8")

    assert "does not receive" in text
    assert "`expected_behavior`" in text
    assert "the injected patch" in text
    assert "visual-only or multimodal L3 reliability" in text
    assert "benchmark-wide detection rate" in text
    assert "benchmark-wide false-positive rate" in text
