"""Android CLI evidence checkpoint capture."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from aiverify.runner.command import CommandResult, CommandRunner, SubprocessCommandRunner


class EvidenceCaptureError(RuntimeError):
    """Raised when checkpoint evidence cannot be captured."""


@dataclass(frozen=True)
class EvidenceCheckpoint:
    """Files captured at one point in a verification run."""

    name: str
    directory: Path
    layout_path: Path
    screenshot_path: Path
    annotated_screenshot_path: Path | None
    logcat_path: Path
    commands_path: Path


class AndroidEvidenceCollector:
    """Capture layout, screenshot, and logcat evidence."""

    def __init__(
        self,
        *,
        runner: CommandRunner | None = None,
        android_bin: str = "android",
        adb_bin: str = "adb",
        layout_attempts: int = 6,
        layout_retry_sleep_seconds: float = 3.0,
        screen_capture_timeout_seconds: int = 90,
        logcat_timeout_seconds: int = 60,
    ) -> None:
        self.runner = runner if runner is not None else SubprocessCommandRunner()
        self.android_bin = android_bin
        self.adb_bin = adb_bin
        self.layout_attempts = layout_attempts
        self.layout_retry_sleep_seconds = layout_retry_sleep_seconds
        self.screen_capture_timeout_seconds = screen_capture_timeout_seconds
        self.logcat_timeout_seconds = logcat_timeout_seconds

    def capture_checkpoint(
        self,
        *,
        name: str,
        output_dir: Path,
        device: str | None = None,
        annotated: bool = True,
    ) -> EvidenceCheckpoint:
        """Capture a checkpoint under output_dir/name."""
        checkpoint_dir = Path(output_dir) / name
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        layout_path = checkpoint_dir / "layout.json"
        screenshot_path = checkpoint_dir / "screen.png"
        annotated_path = checkpoint_dir / "screen-annotated.png" if annotated else None
        logcat_path = checkpoint_dir / "logcat.txt"
        commands_path = checkpoint_dir / "commands.json"
        command_results: list[dict[str, object]] = []

        layout_cmd = [self.android_bin, "layout", "--pretty"]
        if device:
            layout_cmd += ["--device", device]
        layout = self._capture_layout(layout_cmd, command_results=command_results)
        layout_path.write_text(layout.stdout, encoding="utf-8")

        screenshot_cmd = [self.android_bin, "screen", "capture", "-o", str(screenshot_path)]
        screenshot = self._run_required(
            screenshot_cmd,
            timeout_seconds=self.screen_capture_timeout_seconds,
        )
        command_results.append(_command_to_dict(screenshot))

        if annotated_path is not None:
            annotated_cmd = [
                self.android_bin,
                "screen",
                "capture",
                "--annotate",
                "-o",
                str(annotated_path),
            ]
            annotated_result = self._run_required(
                annotated_cmd,
                timeout_seconds=self.screen_capture_timeout_seconds,
            )
            command_results.append(_command_to_dict(annotated_result))

        logcat_cmd = [self.adb_bin]
        if device:
            logcat_cmd += ["-s", device]
        logcat_cmd += ["logcat", "-d"]
        logcat = self._run_required(
            logcat_cmd,
            timeout_seconds=self.logcat_timeout_seconds,
        )
        command_results.append(_command_to_dict(logcat))
        logcat_path.write_text(logcat.stdout, encoding="utf-8")

        commands_path.write_text(
            json.dumps(command_results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return EvidenceCheckpoint(
            name=name,
            directory=checkpoint_dir,
            layout_path=layout_path,
            screenshot_path=screenshot_path,
            annotated_screenshot_path=annotated_path,
            logcat_path=logcat_path,
            commands_path=commands_path,
        )

    def _run_required(
        self,
        args: list[str],
        *,
        timeout_seconds: int | None = None,
    ) -> CommandResult:
        try:
            result = self.runner.run(args, timeout_seconds=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            raise EvidenceCaptureError(
                f"Command timed out after {exc.timeout}s: {' '.join(args)}"
            ) from exc
        if result.returncode != 0:
            raise EvidenceCaptureError(
                f"Command failed ({result.returncode}): {' '.join(args)}\n{result.stderr.strip()}"
            )
        return result

    def _capture_layout(
        self,
        args: list[str],
        *,
        command_results: list[dict[str, object]],
    ) -> CommandResult:
        """Capture Android CLI layout, retrying transient empty/non-JSON dumps."""
        last_result: CommandResult | None = None
        attempts = max(1, self.layout_attempts)
        for attempt in range(1, attempts + 1):
            result = self._run_required(args)
            command_results.append(_command_to_dict(result))
            if _is_json_list(result.stdout):
                return result
            last_result = result
            if attempt < attempts:
                time.sleep(self.layout_retry_sleep_seconds)

        assert last_result is not None
        raise EvidenceCaptureError(
            "Android layout did not return a JSON list after "
            f"{attempts} attempt(s): {' '.join(args)}\n"
            f"stdout={last_result.stdout[:500]!r}\n"
            f"stderr={last_result.stderr[:500]!r}"
        )


def _command_to_dict(result: CommandResult) -> dict[str, object]:
    return {
        "args": result.args,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _is_json_list(text: str) -> bool:
    try:
        return isinstance(json.loads(text), list)
    except json.JSONDecodeError:
        return False
