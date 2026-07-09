from __future__ import annotations

from pathlib import Path

import pytest

from aiverify.runner.run_spec import load_run_spec


_ROOT = Path(__file__).resolve().parents[2]
_RUN_SPECS = _ROOT / "bench" / "goldset" / "run-specs"
_METRIC_SCHEMA = _ROOT / "docs" / "M2-metric-schema.md"
_INCLUSION_RULES = _ROOT / "docs" / "M2-beta-inclusion-rules.md"


EXPECTED_M2_BETA_CONTEXT = {
    "wikipedia-config-change-01-defect.yaml": (
        "config-change",
        "config-change-01",
        "L2",
        "state_loss",
    ),
    "wikipedia-lifecycle-04-recreation-crash.yaml": (
        "lifecycle",
        "lifecycle-04",
        "L1",
        "crash_stability",
    ),
    "wikipedia-coroutine-concurrency-03-main-thread-anr.yaml": (
        "coroutine-concurrency",
        "coroutine-concurrency-03",
        "L1",
        "crash_stability",
    ),
    "wikipedia-navigation-01-double-open-crash.yaml": (
        "navigation",
        "navigation-01",
        "L1",
        "crash_stability",
    ),
    "wikipedia-process-death-02-tab-state-loss.yaml": (
        "process-death",
        "process-death-02",
        "L2",
        "state_loss",
    ),
    "wikipedia-config-change-02-query-duplication.yaml": (
        "config-change",
        "config-change-02",
        "L2",
        "state_loss",
    ),
    "wikipedia-navigation-02-back-button-swallowed.yaml": (
        "navigation",
        "navigation-02",
        "L2",
        "state_loss",
    ),
    "wikipedia-ui-rendering-01-nav-label-swap.yaml": (
        "ui-rendering",
        "ui-rendering-01",
        "L3",
        "ui_rendering",
    ),
    "wikipedia-ui-rendering-02-search-card-copy-mismatch.yaml": (
        "ui-rendering",
        "ui-rendering-02",
        "L3",
        "ui_rendering",
    ),
    "wikipedia-process-death-03-oversized-saved-state.yaml": (
        "process-death",
        "process-death-03",
        "L1",
        "crash_stability",
    ),
}


@pytest.mark.parametrize(
    ("filename", "expected"),
    sorted(EXPECTED_M2_BETA_CONTEXT.items()),
)
def test_m2_beta_run_specs_carry_metric_context(
    filename: str,
    expected: tuple[str, str, str, str],
) -> None:
    spec = load_run_spec(_RUN_SPECS / filename)
    metric = spec.scenario.metric_context
    taxonomy_category, taxonomy_pattern_id, oracle_level, oracle_class = expected

    assert metric.seed_kind == "injected_defect"
    assert metric.taxonomy_category == taxonomy_category
    assert metric.taxonomy_pattern_id == taxonomy_pattern_id
    assert metric.expected_oracle_level == oracle_level
    assert metric.expected_oracle_defect_class == oracle_class


def test_m2_beta_metric_schema_lists_backfilled_specs() -> None:
    text = _METRIC_SCHEMA.read_text(encoding="utf-8")

    for filename, expected in EXPECTED_M2_BETA_CONTEXT.items():
        run_id = filename.removesuffix(".yaml")
        taxonomy_category, taxonomy_pattern_id, oracle_level, oracle_class = expected

        assert f"`{run_id}`" in text
        assert f"`{taxonomy_category}`" in text
        assert f"`{taxonomy_pattern_id}`" in text
        assert f"`{oracle_level}/{oracle_class}`" in text


def test_candidate_metadata_does_not_override_inclusion_rules() -> None:
    schema_text = _METRIC_SCHEMA.read_text(encoding="utf-8")
    rules_text = _INCLUSION_RULES.read_text(encoding="utf-8")

    assert (
        "`wikipedia-process-death-03-oversized-saved-state` carries metric metadata"
        in schema_text
    )
    assert "It remains outside the M2-beta numerator and" in schema_text
    assert "denominator until a valid baseline/defect matched pair exists" in schema_text
    assert "not an M2-beta `included` seed today" in rules_text
