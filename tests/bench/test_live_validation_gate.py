from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiverify.bench.live_validation_gate import main, run_live_validation_gate
from aiverify.runner.command import CommandResult, CommandRunner


class FakeRunner(CommandRunner):
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = list(responses)
        self.calls: list[list[str]] = []
        self.timeouts: list[int | None] = []

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        self.calls.append(args)
        self.timeouts.append(timeout_seconds)
        response = self.responses.pop(0)
        return CommandResult(
            args=args,
            stdout=str(response.get("stdout", "")),
            stderr=str(response.get("stderr", "")),
            returncode=int(response.get("returncode", 0)),
        )


def _passing_responses() -> list[dict[str, object]]:
    return [
        {"stdout": "List of devices attached\nemulator-5554 device product:sdk_gphone64_arm64\n"},
        {"stdout": "1\n"},
        {"stdout": "stopped\n"},
        {"stdout": '[{"resource-id":"launcher"}]'},
        {"stdout": "UI hierchary dumped to: /sdcard/window_dump.xml\n"},
    ]


def test_live_validation_gate_passes_when_all_checks_are_healthy() -> None:
    runner = FakeRunner(_passing_responses())

    result = run_live_validation_gate(device="emulator-5554", runner=runner)

    assert result.status == "passed"
    assert result.failed_checks == ()
    assert [check.name for check in result.checks] == [
        "adb-device-present",
        "boot-completed",
        "boot-animation-stopped",
        "android-layout-json",
        "uiautomator-dump",
    ]
    assert all(timeout == 30 for timeout in runner.timeouts)
    assert result.to_dict()["schema_version"] == 1


def test_live_validation_gate_fails_when_device_is_missing() -> None:
    responses = _passing_responses()
    responses[0] = {"stdout": "List of devices attached\n"}
    runner = FakeRunner(responses)

    result = run_live_validation_gate(device="emulator-5554", runner=runner)

    assert result.status == "failed"
    assert "adb-device-present" in result.failed_checks
    first_check = result.checks[0]
    assert first_check.error == "emulator-5554 was not listed by adb devices -l"


def test_live_validation_gate_fails_on_invalid_android_layout() -> None:
    responses = _passing_responses()
    responses[3] = {
        "stdout": "",
        "stderr": "Failed to retrieve UI dump: ERROR: null root node returned\n",
    }
    runner = FakeRunner(responses)

    result = run_live_validation_gate(device="emulator-5554", runner=runner)

    assert result.status == "failed"
    assert "android-layout-json" in result.failed_checks
    layout_check = result.checks[3]
    assert "layout stdout was not JSON" in (layout_check.error or "")


def test_live_validation_gate_validates_layout_before_snippet_truncation() -> None:
    runner = FakeRunner(_passing_responses())

    result = run_live_validation_gate(
        device="emulator-5554",
        runner=runner,
        snippet_chars=5,
    )

    assert result.status == "passed"
    layout_payload = result.to_dict()["checks"][3]
    assert layout_payload["stdout_snippet"] == '[{"re'
    assert layout_payload["stdout_truncated"] is True
    assert "raw_stdout" not in layout_payload


def test_live_validation_gate_fails_on_uiautomator_dump_failure() -> None:
    responses = _passing_responses()
    responses[4] = {
        "stderr": "ERROR: could not get idle state.\n",
        "returncode": 1,
    }
    runner = FakeRunner(responses)

    result = run_live_validation_gate(device="emulator-5554", runner=runner)

    assert result.status == "failed"
    assert "uiautomator-dump" in result.failed_checks
    assert result.checks[4].returncode == 1
    assert result.checks[4].stderr_snippet == "ERROR: could not get idle state.\n"


def test_live_validation_gate_app_smoke_passes_on_target_surface() -> None:
    runner = FakeRunner(
        _passing_responses()
        + [
            {
                "stdout": (
                    "Status: ok\n"
                    "Activity: org.wikipedia.dev/org.wikipedia.main.MainActivity\n"
                )
            },
            {"stdout": "mCurrentFocus=Window org.wikipedia.dev/org.wikipedia.main.MainActivity\n"},
            {"stdout": '[{"resource-id":"nav_tab_search","content-desc":"Search"}]'},
        ]
    )

    result = run_live_validation_gate(
        device="emulator-5554",
        runner=runner,
        app_package="org.wikipedia.dev",
        app_activity="org.wikipedia.DefaultIcon",
        target_resource_id="nav_tab_search",
        target_content_desc="Search",
        app_settle_seconds=0,
    )

    assert result.status == "passed"
    assert result.failed_checks == ()
    payload = result.to_dict()
    assert payload["app"] == {
        "package": "org.wikipedia.dev",
        "activity": "org.wikipedia.DefaultIcon",
        "target_surface": {
            "resource_id": "nav_tab_search",
            "content_desc": "Search",
        },
    }
    assert [check.name for check in result.checks[-3:]] == [
        "app-launch",
        "app-foreground-package",
        "app-target-surface",
    ]


def test_live_validation_gate_app_smoke_fails_when_target_surface_is_missing() -> None:
    runner = FakeRunner(
        _passing_responses()
        + [
            {"stdout": "Status: ok\n"},
            {"stdout": "mCurrentFocus=Window org.wikipedia.dev/org.wikipedia.main.MainActivity\n"},
            {"stdout": '[{"resource-id":"nav_tab_home","content-desc":"Home"}]'},
        ]
    )

    result = run_live_validation_gate(
        device="emulator-5554",
        runner=runner,
        app_package="org.wikipedia.dev",
        app_activity="org.wikipedia.DefaultIcon",
        target_resource_id="nav_tab_search",
        app_settle_seconds=0,
    )

    assert result.status == "failed"
    assert "app-target-surface" in result.failed_checks
    assert "target surface not found" in (result.checks[-1].error or "")


def test_live_validation_gate_requires_complete_app_smoke_arguments() -> None:
    with pytest.raises(ValueError, match="app_activity"):
        run_live_validation_gate(
            device="emulator-5554",
            runner=FakeRunner(_passing_responses()),
            app_package="org.wikipedia.dev",
            target_resource_id="nav_tab_search",
        )


def test_live_validation_gate_cli_writes_json_and_returns_failure(tmp_path: Path) -> None:
    responses = _passing_responses()
    responses[2] = {"stdout": "running\n"}
    runner = FakeRunner(responses)
    output = tmp_path / "gate.json"

    exit_code = main(
        ["--device", "emulator-5554", "--output", str(output), "--timeout-seconds", "7"],
        runner=runner,
    )

    assert exit_code == 2
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["failed_checks"] == ["boot-animation-stopped"]
    assert payload["checks"][2]["timeout_seconds"] == 7
