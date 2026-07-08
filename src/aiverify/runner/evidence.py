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
    manifest_path: Path | None = None


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
        manifest_path = checkpoint_dir / "capture-manifest.json"
        command_results: list[dict[str, object]] = []
        failed_phase: str | None = None

        def _write_metadata(
            status: str,
            *,
            error: dict[str, str] | None = None,
        ) -> None:
            commands_path.write_text(
                json.dumps(command_results, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            manifest = _capture_manifest(
                checkpoint=name,
                status=status,
                failed_phase=failed_phase,
                error=error,
                layout_path=layout_path,
                screenshot_path=screenshot_path,
                annotated_path=annotated_path,
                logcat_path=logcat_path,
                commands_path=commands_path,
                command_count=len(command_results),
            )
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        try:
            failed_phase = "layout"
            layout_cmd = [self.android_bin, "layout", "--pretty"]
            if device:
                layout_cmd += ["--device", device]
            layout = self._capture_layout(layout_cmd, command_results=command_results)
            layout_path.write_text(layout.stdout, encoding="utf-8")

            failed_phase = "screenshot"
            screenshot_cmd = [
                self.android_bin,
                "screen",
                "capture",
                "-o",
                str(screenshot_path),
            ]
            self._run_checkpoint_command(
                screenshot_cmd,
                phase="screenshot",
                command_results=command_results,
                timeout_seconds=self.screen_capture_timeout_seconds,
            )

            if annotated_path is not None:
                failed_phase = "annotated_screenshot"
                annotated_cmd = [
                    self.android_bin,
                    "screen",
                    "capture",
                    "--annotate",
                    "-o",
                    str(annotated_path),
                ]
                self._run_checkpoint_command(
                    annotated_cmd,
                    phase="annotated_screenshot",
                    command_results=command_results,
                    timeout_seconds=self.screen_capture_timeout_seconds,
                )

            failed_phase = "logcat"
            logcat_cmd = [self.adb_bin]
            if device:
                logcat_cmd += ["-s", device]
            logcat_cmd += ["logcat", "-d"]
            logcat = self._run_checkpoint_command(
                logcat_cmd,
                phase="logcat",
                command_results=command_results,
                timeout_seconds=self.logcat_timeout_seconds,
            )
            logcat_path.write_text(logcat.stdout, encoding="utf-8")
        except EvidenceCaptureError as exc:
            _write_metadata(
                "failed",
                error={"type": type(exc).__name__, "message": str(exc)},
            )
            raise

        failed_phase = None
        _write_metadata("passed")

        return EvidenceCheckpoint(
            name=name,
            directory=checkpoint_dir,
            layout_path=layout_path,
            screenshot_path=screenshot_path,
            annotated_screenshot_path=annotated_path,
            logcat_path=logcat_path,
            commands_path=commands_path,
            manifest_path=manifest_path,
        )

    def _run_checkpoint_command(
        self,
        args: list[str],
        *,
        phase: str,
        command_results: list[dict[str, object]],
        timeout_seconds: int | None = None,
    ) -> CommandResult:
        try:
            result = self.runner.run(args, timeout_seconds=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            message = f"Command timed out after {exc.timeout}s: {' '.join(args)}"
            command_results.append(
                _command_entry(
                    args=args,
                    phase=phase,
                    status="timeout",
                    timeout_seconds=timeout_seconds,
                    error=message,
                )
            )
            raise EvidenceCaptureError(message) from exc

        status = "passed"
        error: str | None = None
        if result.returncode != 0:
            status = "failed"
            error = (
                f"Command failed ({result.returncode}): {' '.join(args)}\n"
                f"{result.stderr.strip()}"
            )
        command_results.append(
            _command_entry(
                result=result,
                phase=phase,
                status=status,
                timeout_seconds=timeout_seconds,
                error=error,
            )
        )
        if error is not None:
            raise EvidenceCaptureError(error)
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
            result = self._run_checkpoint_command(
                args,
                phase="layout",
                command_results=command_results,
            )
            if _is_json_list(result.stdout):
                return result
            command_results[-1]["status"] = "invalid_output"
            command_results[-1]["error"] = "layout stdout was not a JSON list"
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


def _capture_manifest(
    *,
    checkpoint: str,
    status: str,
    failed_phase: str | None,
    error: dict[str, str] | None,
    layout_path: Path,
    screenshot_path: Path,
    annotated_path: Path | None,
    logcat_path: Path,
    commands_path: Path,
    command_count: int,
) -> dict[str, object]:
    artifacts = {
        "layout": str(layout_path),
        "screen": str(screenshot_path),
        "screen_annotated": str(annotated_path) if annotated_path is not None else None,
        "logcat": str(logcat_path),
        "commands": str(commands_path),
    }
    artifact_exists = {
        key: Path(value).exists() if value is not None else False
        for key, value in artifacts.items()
    }
    return {
        "checkpoint": checkpoint,
        "status": status,
        "failed_phase": failed_phase,
        "error": error,
        "command_count": command_count,
        "artifacts": artifacts,
        "artifact_exists": artifact_exists,
    }


def _command_to_dict(result: CommandResult) -> dict[str, object]:
    return {
        "args": result.args,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _command_entry(
    *,
    phase: str,
    status: str,
    timeout_seconds: int | None,
    error: str | None,
    result: CommandResult | None = None,
    args: list[str] | None = None,
) -> dict[str, object]:
    if result is not None:
        entry = _command_to_dict(result)
    elif args is not None:
        entry = {"args": list(args), "returncode": None, "stdout": "", "stderr": ""}
    else:
        raise ValueError("result or args is required")

    entry.update(
        {
            "phase": phase,
            "status": status,
            "timeout_seconds": timeout_seconds,
            "error": error,
        }
    )
    return entry


def _is_json_list(text: str) -> bool:
    try:
        return isinstance(json.loads(text), list)
    except json.JSONDecodeError:
        return False
