from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from aiverify.runner.command import CommandResult, CommandRunner
from aiverify.runner.evidence import AndroidEvidenceCollector, EvidenceCaptureError


class FakeRunner(CommandRunner):
    def __init__(
        self,
        *,
        fail_on: str = "",
        timeout_on: str = "",
        bad_layouts_before_success: int = 0,
    ) -> None:
        self.calls: list[list[str]] = []
        self.timeouts: list[int | None] = []
        self.fail_on = fail_on
        self.timeout_on = timeout_on
        self.bad_layouts_before_success = bad_layouts_before_success

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
        joined = " ".join(args)
        if self.timeout_on and self.timeout_on in joined:
            raise subprocess.TimeoutExpired(args, timeout_seconds)
        if self.fail_on and self.fail_on in joined:
            return CommandResult(args=args, stdout="", stderr="failed", returncode=1)
        if args[:2] == ["android", "layout"]:
            if self.bad_layouts_before_success:
                self.bad_layouts_before_success -= 1
                return CommandResult(
                    args=args,
                    stdout="",
                    stderr=(
                        "Failed to retrieve UI dump: ERROR: null root node "
                        "returned by UiTestAutomationBridge.\n"
                    ),
                    returncode=0,
                )
            return CommandResult(args=args, stdout='[{"text":"Home"}]', stderr="", returncode=0)
        if args[:3] == ["android", "screen", "capture"]:
            out = Path(args[args.index("-o") + 1])
            out.write_bytes(b"png")
            return CommandResult(args=args, stdout=f"Screenshot written to {out}", stderr="", returncode=0)
        if args[-2:] == ["logcat", "-d"]:
            return CommandResult(args=args, stdout="log line\n", stderr="", returncode=0)
        return CommandResult(args=args, stdout="", stderr="", returncode=0)


def test_capture_checkpoint_writes_evidence_files(tmp_path: Path) -> None:
    runner = FakeRunner()
    collector = AndroidEvidenceCollector(runner=runner)

    checkpoint = collector.capture_checkpoint(
        name="before",
        output_dir=tmp_path,
        device="emulator-5554",
    )

    assert checkpoint.layout_path.read_text(encoding="utf-8") == '[{"text":"Home"}]'
    assert checkpoint.screenshot_path.read_bytes() == b"png"
    assert checkpoint.annotated_screenshot_path is not None
    assert checkpoint.annotated_screenshot_path.read_bytes() == b"png"
    assert checkpoint.logcat_path.read_text(encoding="utf-8") == "log line\n"
    assert checkpoint.commands_path.is_file()
    assert checkpoint.manifest_path is not None
    manifest = json.loads(checkpoint.manifest_path.read_text(encoding="utf-8"))
    assert manifest["checkpoint"] == "before"
    assert manifest["status"] == "passed"
    assert manifest["failed_phase"] is None
    assert manifest["error"] is None
    assert manifest["command_count"] == 4
    assert manifest["artifacts"]["layout"] == str(checkpoint.layout_path)
    assert manifest["artifacts"]["screen"] == str(checkpoint.screenshot_path)
    assert manifest["artifacts"]["screen_annotated"] == str(
        checkpoint.annotated_screenshot_path
    )
    assert manifest["artifacts"]["logcat"] == str(checkpoint.logcat_path)
    assert ["adb", "-s", "emulator-5554", "logcat", "-d"] in runner.calls


def test_capture_checkpoint_raises_on_command_failure(tmp_path: Path) -> None:
    collector = AndroidEvidenceCollector(runner=FakeRunner(fail_on="layout"))

    with pytest.raises(EvidenceCaptureError, match="Command failed"):
        collector.capture_checkpoint(name="bad", output_dir=tmp_path)

    checkpoint_dir = tmp_path / "bad"
    commands = json.loads((checkpoint_dir / "commands.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (checkpoint_dir / "capture-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["status"] == "failed"
    assert manifest["failed_phase"] == "layout"
    assert "Command failed" in manifest["error"]["message"]
    assert commands[-1]["phase"] == "layout"
    assert commands[-1]["status"] == "failed"
    assert commands[-1]["returncode"] == 1
    assert commands[-1]["stderr"] == "failed"


def test_capture_checkpoint_retries_transient_empty_layout(tmp_path: Path) -> None:
    runner = FakeRunner(bad_layouts_before_success=1)
    collector = AndroidEvidenceCollector(
        runner=runner,
        layout_attempts=2,
        layout_retry_sleep_seconds=0,
    )

    checkpoint = collector.capture_checkpoint(name="retry", output_dir=tmp_path)

    assert checkpoint.layout_path.read_text(encoding="utf-8") == '[{"text":"Home"}]'
    layout_calls = [call for call in runner.calls if call[:2] == ["android", "layout"]]
    assert len(layout_calls) == 2

    commands = json.loads(checkpoint.commands_path.read_text(encoding="utf-8"))
    layout_results = [
        item for item in commands
        if item["args"][:2] == ["android", "layout"]
    ]
    assert [item["stdout"] for item in layout_results] == ["", '[{"text":"Home"}]']
    assert [item["status"] for item in layout_results] == ["invalid_output", "passed"]


def test_capture_checkpoint_applies_timeouts_to_screens_and_logcat(tmp_path: Path) -> None:
    runner = FakeRunner()
    collector = AndroidEvidenceCollector(
        runner=runner,
        screen_capture_timeout_seconds=12,
        logcat_timeout_seconds=7,
    )

    collector.capture_checkpoint(name="timeouts", output_dir=tmp_path)

    timeout_by_call = {
        " ".join(args): timeout
        for args, timeout in zip(runner.calls, runner.timeouts, strict=True)
    }
    screen_timeouts = [
        timeout
        for command, timeout in timeout_by_call.items()
        if command.startswith("android screen capture")
    ]
    assert screen_timeouts == [12, 12]
    assert timeout_by_call["adb logcat -d"] == 7


def test_capture_checkpoint_wraps_command_timeout(tmp_path: Path) -> None:
    collector = AndroidEvidenceCollector(
        runner=FakeRunner(timeout_on="--annotate"),
        screen_capture_timeout_seconds=3,
    )

    with pytest.raises(EvidenceCaptureError, match="Command timed out after 3s"):
        collector.capture_checkpoint(name="timeout", output_dir=tmp_path)

    checkpoint_dir = tmp_path / "timeout"
    commands = json.loads((checkpoint_dir / "commands.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (checkpoint_dir / "capture-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["status"] == "failed"
    assert manifest["failed_phase"] == "annotated_screenshot"
    assert "timed out" in manifest["error"]["message"]
    assert commands[-1]["phase"] == "annotated_screenshot"
    assert commands[-1]["status"] == "timeout"
    assert commands[-1]["timeout_seconds"] == 3
    assert "--annotate" in commands[-1]["args"]
