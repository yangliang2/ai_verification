"""Regression tests for the oversized saved-state crash seed (#23).

The seed models Tusky #419: putting image-sized data into Activity saved state
crashes only when Android saves that state. The expected detector is L1 logcat
crash evidence, not an L2 UI state diff.
"""

from __future__ import annotations

from pathlib import Path

from aiverify.agent.oracle import L1Oracle
from aiverify.agent.oracle.schema import validate_verdict
from aiverify.runner.run_spec import load_run_spec

_GOLDSET = Path(__file__).resolve().parents[2] / "bench" / "goldset"
_RUN_SPEC = (
    _GOLDSET
    / "run-specs"
    / "wikipedia-process-death-03-oversized-saved-state.yaml"
)
_PATCH = (
    _GOLDSET
    / "patches"
    / "wikipedia-process-death-03-oversized-saved-state.patch"
)
_FIXTURES = _GOLDSET / "fixtures" / "wikipedia-process-death-03-oversized-saved-state"

_CLEAN_LOGCAT = """\
07-08 22:40:00.000 100 100 I ActivityTaskManager: Config changes=200 for org.wikipedia.dev
07-08 22:40:00.100 100 100 I org.wikipedia.dev: SearchActivity onSaveInstanceState
07-08 22:40:00.300 100 100 I ActivityTaskManager: Displayed org.wikipedia.dev/.search.SearchActivity
"""


def test_run_spec_parses_with_dark_mode_boundary_patch_and_metric_context() -> None:
    spec = load_run_spec(_RUN_SPEC)

    assert spec.package == "org.wikipedia.dev"
    assert spec.activity == "org.wikipedia.DefaultIcon"
    assert spec.scenario.id == "wikipedia-process-death-03-oversized-saved-state"
    assert spec.spec is not None and spec.spec.name.endswith(
        "wikipedia-process-death-03-oversized-saved-state.md"
    )
    assert spec.diff is not None and spec.diff.name.endswith(
        "wikipedia-process-death-03-oversized-saved-state.patch"
    )
    event = spec.scenario.system_events[0]
    assert event.event == "dark_mode"
    assert event.args == {"night": "yes"}
    assert "zzoversizeqx" in spec.scenario.user_actions[1]
    assert [(a.resource_id, a.attr, a.expected) for a in spec.scenario.assertions] == [
        ("search_src_text", "text", "zzoversizeqx")
    ]
    assert spec.scenario.metric_context.seed_kind == "injected_defect"
    assert spec.scenario.metric_context.taxonomy_category == "process-death"
    assert spec.scenario.metric_context.taxonomy_pattern_id == "process-death-03"
    assert spec.scenario.metric_context.expected_oracle_level == "L1"
    assert spec.scenario.metric_context.expected_oracle_defect_class == "crash_stability"


def test_l1_flags_transaction_too_large_crash_fixture() -> None:
    crash_logcat = (_FIXTURES / "crash-logcat.txt").read_text(encoding="utf-8")

    verdict = L1Oracle().judge(
        crash_logcat,
        trigger_steps=["type sentinel", "[boundary] dark-mode save-state"],
    )

    validate_verdict(verdict)
    assert verdict["outcome"] == "fail"
    assert verdict["defect_class_hypothesis"] == "crash_stability"
    refs = " ".join(e["ref"] for e in verdict["evidence"])
    assert "FATAL EXCEPTION" in refs
    assert "TransactionTooLargeException" in crash_logcat
    assert "org.wikipedia.dev" in crash_logcat


def test_baseline_clean_logcat_is_l1_inconclusive() -> None:
    verdict = L1Oracle().judge(_CLEAN_LOGCAT)

    validate_verdict(verdict)
    assert verdict["outcome"] == "inconclusive"
    assert verdict["defect_class_hypothesis"] is None
    assert verdict["evidence"] == []


def test_patch_injects_oversized_saved_state_into_search_activity_only() -> None:
    patch_text = _PATCH.read_text(encoding="utf-8")

    assert "app/src/main/java/org/wikipedia/search/SearchActivity.kt" in patch_text
    assert "override fun onSaveInstanceState(outState: Bundle)" in patch_text
    assert "outState.putByteArray" in patch_text
    assert "AIVERIFY_OVERSIZED_STATE_BYTES" in patch_text
    assert "2 * 1024 * 1024" in patch_text
