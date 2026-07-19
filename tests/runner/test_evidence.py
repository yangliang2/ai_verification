from __future__ import annotations

import json
import re
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
        omit_screen_output: bool = False,
    ) -> None:
        self.calls: list[list[str]] = []
        self.timeouts: list[int | None] = []
        self.fail_on = fail_on
        self.timeout_on = timeout_on
        self.bad_layouts_before_success = bad_layouts_before_success
        self.omit_screen_output = omit_screen_output

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
            if not self.omit_screen_output:
                out.write_bytes(b"png")
            return CommandResult(args=args, stdout=f"Screenshot written to {out}", stderr="", returncode=0)
        if "pull" in args:
            out = Path(args[-1])
            if not self.omit_screen_output:
                out.write_bytes(b"png")
            return CommandResult(args=args, stdout=f"pulled to {out}", stderr="", returncode=0)
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
    assert checkpoint.annotated_screenshot_path is None
    assert checkpoint.logcat_path.read_text(encoding="utf-8") == "log line\n"
    assert checkpoint.commands_path.is_file()
    assert checkpoint.manifest_path is not None
    manifest = json.loads(checkpoint.manifest_path.read_text(encoding="utf-8"))
    assert manifest["checkpoint"] == "before"
    assert manifest["status"] == "passed"
    assert manifest["failed_phase"] is None
    assert manifest["error"] is None
    assert manifest["command_count"] == 5
    assert manifest["artifacts"]["layout"] == str(checkpoint.layout_path)
    assert manifest["artifacts"]["screen"] == str(checkpoint.screenshot_path)
    assert manifest["artifacts"]["screen_annotated"] is None
    assert manifest["artifacts"]["logcat"] == str(checkpoint.logcat_path)
    assert ["adb", "-s", "emulator-5554", "logcat", "-d"] in runner.calls


def test_device_scoped_checkpoint_never_uses_unscoped_android_screenshot(
    tmp_path: Path,
) -> None:
    runner = FakeRunner()
    collector = AndroidEvidenceCollector(runner=runner)

    checkpoint = collector.capture_checkpoint(
        name="multi-device",
        output_dir=tmp_path,
        device="emulator-5554",
    )

    assert checkpoint.screenshot_path.read_bytes() == b"png"
    assert checkpoint.annotated_screenshot_path is None
    assert not any(call[:3] == ["android", "screen", "capture"] for call in runner.calls)
    assert [
        "adb",
        "-s",
        "emulator-5554",
        "shell",
        "screencap",
        "-p",
        "/data/local/tmp/aiverify-multi-device-screen.png",
    ] in runner.calls
    assert [
        "adb",
        "-s",
        "emulator-5554",
        "pull",
        "/data/local/tmp/aiverify-multi-device-screen.png",
        str(checkpoint.screenshot_path),
    ] in runner.calls


def test_device_scoped_fallback_uses_unique_remote_paths_for_overlapping_runs(
    tmp_path: Path,
) -> None:
    """Separate collectors may capture the same checkpoint on one device."""
    runner = FakeRunner(android_screen_has_multiple_devices=True)
    first = AndroidEvidenceCollector(runner=runner)
    second = AndroidEvidenceCollector(runner=runner)

    first.capture_checkpoint(
        name="after-event",
        output_dir=tmp_path / "first",
        device="emulator-5556",
    )
    second.capture_checkpoint(
        name="after-event",
        output_dir=tmp_path / "second",
        device="emulator-5556",
    )

    remote_paths = [
        call[-1]
        for call in runner.calls
        if call[:5] == ["adb", "-s", "emulator-5556", "shell", "screencap"]
    ]
    assert len(remote_paths) == 2
    assert len(set(remote_paths)) == 2
    assert all(
        re.fullmatch(r"/sdcard/aiverify-after-event-[0-9a-f]{32}\.png", path)
        for path in remote_paths
    )


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
    failed = next(item for item in commands if item["phase"] == "layout")
    assert failed["status"] == "failed"
    assert failed["returncode"] == 1
    assert failed["stderr"] == "failed"
    assert [item["phase"] for item in commands[1:]] == [
        "screenshot",
        "annotated_screenshot",
        "logcat",
    ]
    assert manifest["artifact_exists"]["logcat"] is True


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
    timed_out = next(
        item for item in commands if item["phase"] == "annotated_screenshot"
    )
    assert timed_out["status"] == "timeout"
    assert timed_out["timeout_seconds"] == 3
    assert "--annotate" in timed_out["args"]
    assert commands[-1]["phase"] == "logcat"
    assert commands[-1]["status"] == "passed"
    assert manifest["artifact_exists"]["logcat"] is True


def test_capture_checkpoint_fails_closed_when_screen_command_writes_no_artifact(
    tmp_path: Path,
) -> None:
    collector = AndroidEvidenceCollector(runner=FakeRunner(omit_screen_output=True))

    with pytest.raises(EvidenceCaptureError, match="did not create a non-empty artifact"):
        collector.capture_checkpoint(name="missing-screen", output_dir=tmp_path)

    checkpoint_dir = tmp_path / "missing-screen"
    commands = json.loads((checkpoint_dir / "commands.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (checkpoint_dir / "capture-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["status"] == "failed"
    assert manifest["failed_phase"] == "screenshot"
    assert [item["phase"] for item in manifest["phase_errors"]] == [
        "screenshot",
        "annotated_screenshot",
    ]
    assert [item["status"] for item in commands[1:3]] == [
        "missing_artifact",
        "missing_artifact",
    ]
    assert manifest["artifact_exists"]["screen"] is False
    assert manifest["artifact_exists"]["screen_annotated"] is False
    assert manifest["artifact_exists"]["logcat"] is True


def test_capture_checkpoint_refuses_contradictory_stale_artifacts(
    tmp_path: Path,
) -> None:
    checkpoint_dir = tmp_path / "reused"
    checkpoint_dir.mkdir()
    stale_layout = checkpoint_dir / "layout.json"
    stale_layout.write_text('[{"text":"stale"}]', encoding="utf-8")
    runner = FakeRunner()
    collector = AndroidEvidenceCollector(runner=runner)

    with pytest.raises(EvidenceCaptureError, match="refusing to overwrite"):
        collector.capture_checkpoint(name="reused", output_dir=tmp_path)

    assert runner.calls == []
    assert stale_layout.read_text(encoding="utf-8") == '[{"text":"stale"}]'
    assert not (checkpoint_dir / "commands.json").exists()
    assert not (checkpoint_dir / "capture-manifest.json").exists()
