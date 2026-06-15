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
