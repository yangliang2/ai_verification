from __future__ import annotations

from pathlib import Path

import pytest

from aiverify.runner.run_spec import RunSpecError, load_run_spec, parse_run_spec


def _valid_spec() -> dict:
    return {
        "host_project": "/hosts/wiki",
        "apk_glob": "app/build/**/*.apk",
        "package": "org.wikipedia.dev",
        "activity": "org.wikipedia.main.MainActivity",
        "diff": "patches/smoke.patch",
        "spec": "specs/smoke.md",
        "scenario": {
            "id": "smoke-search-rotation",
            "user_actions": ["Open search", "Type aiverify-smoke-1739"],
            "system_events": [{"step_index": 1, "event": "rotate"}],
            "assertions": [
                {
                    "resource_id": "org.wikipedia.dev:id/search_src_text",
                    "attr": "text",
                    "expected": "aiverify-smoke-1739",
                }
            ],
        },
    }


def test_parse_valid_run_spec_normalizes_paths(tmp_path: Path) -> None:
    spec = parse_run_spec(_valid_spec(), base_dir=tmp_path)

    assert spec.host_project == Path("/hosts/wiki")
    assert spec.diff == tmp_path / "patches/smoke.patch"
    assert spec.spec == tmp_path / "specs/smoke.md"
    assert spec.scenario.system_events[0].event == "rotate"
    assert spec.scenario.assertions[0].expected == "aiverify-smoke-1739"
    assert spec.scenario.metric_context.seed_kind == "unspecified"


def test_parse_run_spec_metric_context(tmp_path: Path) -> None:
    data = _valid_spec()
    data["scenario"]["metric_context"] = {
        "seed_kind": "injected_defect",
        "taxonomy_category": "navigation",
        "taxonomy_pattern_id": "navigation-02",
        "expected_oracle_level": "L2",
        "expected_oracle_defect_class": "state_loss",
    }

    spec = parse_run_spec(data, base_dir=tmp_path)

    assert spec.scenario.metric_context.seed_kind == "injected_defect"
    assert spec.scenario.metric_context.taxonomy_category == "navigation"
    assert spec.scenario.metric_context.taxonomy_pattern_id == "navigation-02"
    assert spec.scenario.metric_context.expected_oracle_level == "L2"
    assert spec.scenario.metric_context.expected_oracle_defect_class == "state_loss"


def test_parse_run_spec_l2_boundary_selection(tmp_path: Path) -> None:
    data = _valid_spec()
    data["scenario"]["l2_boundary_index"] = 0

    spec = parse_run_spec(data, base_dir=tmp_path)

    assert spec.scenario.l2_boundary_index == 0


def test_parse_run_spec_live_validation_app_smoke(tmp_path: Path) -> None:
    data = _valid_spec()
    data["package"] = "com.example.host"
    data["activity"] = "com.example.host.MainActivity"
    data["live_validation"] = {
        "timeout_seconds": 11,
        "snippet_chars": 123,
        "android_bin": "/opt/android",
        "adb_bin": "/opt/adb",
        "app_smoke": {
            "target_resource_id": "main_button",
            "target_text": "Dashboard",
            "target_content_desc": "Main dashboard",
            "app_settle_seconds": 0,
        },
    }

    spec = parse_run_spec(data, base_dir=tmp_path)

    assert spec.live_validation.timeout_seconds == 11
    assert spec.live_validation.snippet_chars == 123
    assert spec.live_validation.android_bin == "/opt/android"
    assert spec.live_validation.adb_bin == "/opt/adb"
    assert spec.live_validation.app_smoke is not None
    assert spec.live_validation.app_smoke.package is None
    assert spec.live_validation.app_smoke.activity is None
    assert spec.live_validation.app_smoke.target_resource_id == "main_button"
    assert spec.live_validation.app_smoke.target_text == "Dashboard"
    assert spec.live_validation.app_smoke.target_content_desc == "Main dashboard"
    assert spec.live_validation.app_smoke.app_settle_seconds == 0


def test_app_smoke_requires_activity_from_config_or_run_spec() -> None:
    data = _valid_spec()
    data["activity"] = None
    data["live_validation"] = {
        "app_smoke": {"target_resource_id": "main_button"},
    }

    with pytest.raises(RunSpecError, match="app_smoke.activity"):
        parse_run_spec(data)


def test_app_smoke_requires_target_surface() -> None:
    data = _valid_spec()
    data["live_validation"] = {"app_smoke": {}}

    with pytest.raises(RunSpecError, match="target surface"):
        parse_run_spec(data)


def test_invalid_l2_boundary_selection_fails() -> None:
    data = _valid_spec()
    data["scenario"]["l2_boundary_index"] = -1

    with pytest.raises(RunSpecError, match="l2_boundary_index"):
        parse_run_spec(data)


def test_out_of_range_l2_boundary_selection_fails() -> None:
    data = _valid_spec()
    data["scenario"]["l2_boundary_index"] = 1

    with pytest.raises(RunSpecError, match="does not select"):
        parse_run_spec(data)


def test_l2_boundary_selection_uses_step_index_order_not_yaml_order(tmp_path: Path) -> None:
    data = _valid_spec()
    data["scenario"]["system_events"] = [
        {"step_index": 1, "event": "dark_mode"},
        {"step_index": 0, "event": "rotate"},
    ]
    data["scenario"]["l2_boundary_index"] = 0

    spec = parse_run_spec(data, base_dir=tmp_path)

    assert [event.event for event in spec.scenario.system_events] == ["rotate", "dark_mode"]


def test_invalid_metric_context_fails() -> None:
    data = _valid_spec()
    data["scenario"]["metric_context"] = {
        "seed_kind": "injected_defect",
        "expected_oracle_level": "L4",
    }

    with pytest.raises(RunSpecError, match="expected_oracle_level"):
        parse_run_spec(data)


def test_load_run_spec_from_yaml(tmp_path: Path) -> None:
    src = tmp_path / "run-spec.yaml"
    src.write_text(
        """
host_project: /hosts/wiki
apk_glob: app/build/**/*.apk
package: org.wikipedia.dev
scenario:
  id: smoke
  assertions: []
""",
        encoding="utf-8",
    )

    spec = load_run_spec(src)

    assert spec.scenario.id == "smoke"
    assert spec.activity is None


def test_missing_required_field_fails() -> None:
    data = _valid_spec()
    del data["package"]

    with pytest.raises(RunSpecError, match="package"):
        parse_run_spec(data)


def test_invalid_system_event_fails() -> None:
    data = _valid_spec()
    data["scenario"]["system_events"][0]["event"] = "explode"

    with pytest.raises(RunSpecError, match="不支持"):
        parse_run_spec(data)


def test_dry_run_plan_does_not_touch_device(tmp_path: Path) -> None:
    spec = parse_run_spec(_valid_spec(), base_dir=tmp_path)

    plan = spec.dry_run_plan(tmp_path / "artifacts")

    assert plan.run_id == "smoke-search-rotation"
    assert plan.artifact_dir == tmp_path / "artifacts/smoke-search-rotation"
    assert any("deploy package org.wikipedia.dev" in action for action in plan.actions)
