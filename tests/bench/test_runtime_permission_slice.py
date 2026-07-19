"""Contract tests for GitHub #70's bounded runtime-permission slice."""

from __future__ import annotations

from pathlib import Path

from aiverify.agent.oracle import L1Oracle
from aiverify.runner.run_spec import load_run_spec
from aiverify.runner.verdict import judge_l2_from_android_layout


_ROOT = Path(__file__).resolve().parents[2] / "bench" / "runtime-permission"
_FIXTURES = _ROOT / "fixtures"


def _layout(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def _assertion(resource_id: str, expected: str) -> list:
    from aiverify.runner.run_spec import AssertionSpec

    return [AssertionSpec(resource_id=resource_id, attr="text", expected=expected)]


def test_baseline_and_candidate_run_matched_permission_journeys() -> None:
    baseline = load_run_spec(
        _ROOT / "run-specs" / "wikipedia-location-permission-baseline.yaml",
        environ={"WIKIPEDIA_SOURCE": "/tmp/wikipedia"},
    )
    candidate = load_run_spec(
        _ROOT / "run-specs" / "wikipedia-location-permission-candidate.yaml",
        environ={"WIKIPEDIA_SOURCE": "/tmp/wikipedia"},
    )

    assert baseline.scenario.user_actions == candidate.scenario.user_actions
    assert baseline.scenario.system_events == candidate.scenario.system_events
    assert baseline.scenario.assertions == candidate.scenario.assertions
    assert baseline.scenario.l3_spec == candidate.scenario.l3_spec
    assert baseline.scenario.metric_context.seed_kind == "unspecified"
    assert candidate.scenario.metric_context.seed_kind == "unspecified"
    assert [event.event for event in baseline.scenario.system_events] == [
        "reset_permission",
        "reset_permission",
        "observe_permission",
        "observe_permission",
        "grant_permission",
        "open_app_settings",
        "observe_permission",
    ]


def test_first_denial_baseline_passes_but_blocked_candidate_fails() -> None:
    assertions = _assertion(
        "permission_status",
        "FIRST_DENIED: Continue without location; retry is optional.",
    )
    baseline = judge_l2_from_android_layout(
        _layout("first-denied-baseline-layout.json"),
        _layout("first-denied-baseline-layout.json"),
        assertions,
    )
    candidate = judge_l2_from_android_layout(
        _layout("first-denied-baseline-layout.json"),
        _layout("first-denied-candidate-layout.json"),
        assertions,
    )

    assert baseline["outcome"] == "pass"
    assert candidate["outcome"] == "fail"


def test_missing_fallback_is_detected_after_denial() -> None:
    verdict = judge_l2_from_android_layout(
        _layout("first-denied-baseline-layout.json"),
        _layout("first-denied-candidate-layout.json"),
        _assertion("continue_without_location", "CONTINUE WITHOUT LOCATION"),
    )

    assert verdict["outcome"] == "fail"
    assert "节点消失" in verdict["evidence"][0]["ref"]


def test_permanent_denial_exposes_settings_fallback() -> None:
    layout = _layout("permanently-denied-baseline-layout.json")
    verdict = judge_l2_from_android_layout(
        layout,
        layout,
        _assertion("open_permission_settings", "OPEN APP SETTINGS"),
    )

    assert verdict["outcome"] == "pass"
    assert "RATIONALE: false" in layout


def test_revocation_gracefully_degrades_and_remains_usable() -> None:
    layout = _layout("revoked-baseline-layout.json")
    verdict = judge_l2_from_android_layout(
        _layout("permanently-denied-baseline-layout.json"),
        layout,
        _assertion(
            "permission_status",
            "REVOKED: Location unavailable. Continuing without location.",
        ),
    )

    assert verdict["outcome"] == "pass"
    assert "continue_without_location" in layout
    assert "use_location_feature" in layout


def test_security_exception_is_detected_as_crash_stability() -> None:
    logcat = (_FIXTURES / "security-exception-logcat.txt").read_text(
        encoding="utf-8"
    )

    verdict = L1Oracle().judge(logcat)

    assert verdict["outcome"] == "fail"
    assert verdict["defect_class_hypothesis"] == "crash_stability"


def test_fixture_patches_are_debug_only_and_model_the_expected_difference() -> None:
    baseline = (
        _ROOT / "patches" / "wikipedia-location-permission-baseline.patch"
    ).read_text(encoding="utf-8")
    candidate = (
        _ROOT / "patches" / "wikipedia-location-permission-candidate.patch"
    ).read_text(encoding="utf-8")

    for patch in (baseline, candidate):
        assert "app/src/debug/AndroidManifest.xml" in patch
        assert "Manifest.permission.ACCESS_FINE_LOCATION" in patch
        assert "shouldShowRequestPermissionRationale" in patch
    assert "REVOKED: Location unavailable. Continuing without location." in baseline
    assert "PERMANENTLY_DENIED: Continue without location or open Settings." in baseline
    assert "BLOCKED: Location permission is required." in candidate
    assert "checkSelfPermission(PERMISSION) != PackageManager.PERMISSION_GRANTED" not in candidate
