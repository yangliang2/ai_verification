from __future__ import annotations

from pathlib import Path

import pytest

from aiverify.runner.command import CommandResult, CommandRunner
from aiverify.runner.evidence import AndroidEvidenceCollector, EvidenceCaptureError


class FakeRunner(CommandRunner):
    def __init__(self, *, fail_on: str = "") -> None:
        self.calls: list[list[str]] = []
        self.fail_on = fail_on

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        self.calls.append(args)
        joined = " ".join(args)
        if self.fail_on and self.fail_on in joined:
            return CommandResult(args=args, stdout="", stderr="failed", returncode=1)
        if args[:2] == ["android", "layout"]:
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
    assert ["adb", "-s", "emulator-5554", "logcat", "-d"] in runner.calls


def test_capture_checkpoint_raises_on_command_failure(tmp_path: Path) -> None:
    collector = AndroidEvidenceCollector(runner=FakeRunner(fail_on="layout"))

    with pytest.raises(EvidenceCaptureError, match="Command failed"):
        collector.capture_checkpoint(name="bad", output_dir=tmp_path)
