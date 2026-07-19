"""Android CLI evidence checkpoint capture."""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from aiverify.runner.command import CommandResult, CommandRunner, SubprocessCommandRunner


class EvidenceCaptureError(RuntimeError):
    """Raised when checkpoint evidence cannot be captured."""

    def __init__(
        self,
        message: str,
        *,
        checkpoint: EvidenceCheckpoint | None = None,
    ) -> None:
        super().__init__(message)
        self.checkpoint = checkpoint


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
        # Android CLI 1.0.15498356 exposes no device selector for `screen capture`.
        # In a multi-device environment an unscoped call can capture the wrong device
        # or return success without an artifact. Device-scoped captures therefore use
        # adb directly; annotation remains available only for an unambiguous default
        # device invocation.
        annotated_path = (
            checkpoint_dir / "screen-annotated.png"
            if annotated and device is None
            else None
        )
        logcat_path = checkpoint_dir / "logcat.txt"
        commands_path = checkpoint_dir / "commands.json"
        manifest_path = checkpoint_dir / "capture-manifest.json"
        owned_artifacts = [
            layout_path,
            screenshot_path,
            checkpoint_dir / "screen-annotated.png",
            logcat_path,
            commands_path,
            manifest_path,
        ]
        existing_artifacts = [path for path in owned_artifacts if path.exists()]
        if existing_artifacts:
            paths = ", ".join(str(path) for path in existing_artifacts)
            raise EvidenceCaptureError(
                "Checkpoint contains existing capture artifacts; refusing to "
                f"overwrite contradictory evidence: {paths}"
            )
        checkpoint = EvidenceCheckpoint(
            name=name,
            directory=checkpoint_dir,
            layout_path=layout_path,
            screenshot_path=screenshot_path,
            annotated_screenshot_path=annotated_path,
            logcat_path=logcat_path,
            commands_path=commands_path,
            manifest_path=manifest_path,
        )
        command_results: list[dict[str, object]] = []
        phase_errors: list[tuple[str, EvidenceCaptureError]] = []
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
                evidence=checkpoint,
                status=status,
                failed_phase=failed_phase,
                error=error,
                command_count=len(command_results),
                phase_errors=[
                    {
                        "phase": phase,
                        "type": type(exc).__name__,
                        "message": str(exc),
                    }
                    for phase, exc in phase_errors
                ],
            )
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        def _capture_phase_best_effort(phase: str, operation):
            nonlocal failed_phase
            failed_phase = phase
            try:
                return operation()
            except EvidenceCaptureError as exc:
                phase_errors.append((phase, exc))
                return None

        layout_cmd = [self.android_bin, "layout", "--pretty"]
        if device:
            layout_cmd += ["--device", device]
        layout = _capture_phase_best_effort(
            "layout",
            lambda: self._capture_layout(
                layout_cmd,
                command_results=command_results,
            ),
        )
        if layout is not None:
            layout_path.write_text(layout.stdout, encoding="utf-8")

        if device is not None:
            _capture_phase_best_effort(
                "screenshot",
                lambda: self._capture_device_screenshot(
                    device=device,
                    checkpoint_name=name,
                    output_path=screenshot_path,
                    command_results=command_results,
                ),
            )
        else:
            screenshot_cmd = [
                self.android_bin,
                "screen",
                "capture",
                "-o",
                str(screenshot_path),
            ]
            _capture_phase_best_effort(
                "screenshot",
                lambda: self._run_checkpoint_command(
                    screenshot_cmd,
                    phase="screenshot",
                    command_results=command_results,
                    timeout_seconds=self.screen_capture_timeout_seconds,
                ),
            )
        self._record_missing_artifact(
            phase="screenshot",
            path=screenshot_path,
            command_results=command_results,
            phase_errors=phase_errors,
        )

        if annotated_path is not None:
            annotated_cmd = [
                self.android_bin,
                "screen",
                "capture",
                "--annotate",
                "-o",
                str(annotated_path),
            ]
            _capture_phase_best_effort(
                "annotated_screenshot",
                lambda: self._run_checkpoint_command(
                    annotated_cmd,
                    phase="annotated_screenshot",
                    command_results=command_results,
                    timeout_seconds=self.screen_capture_timeout_seconds,
                ),
            )
            self._record_missing_artifact(
                phase="annotated_screenshot",
                path=annotated_path,
                command_results=command_results,
                phase_errors=phase_errors,
            )

        logcat_cmd = [self.adb_bin]
        if device:
            logcat_cmd += ["-s", device]
        logcat_cmd += ["logcat", "-d"]
        logcat = _capture_phase_best_effort(
            "logcat",
            lambda: self._run_checkpoint_command(
                logcat_cmd,
                phase="logcat",
                command_results=command_results,
                timeout_seconds=self.logcat_timeout_seconds,
            ),
        )
        if logcat is not None:
            logcat_path.write_text(logcat.stdout, encoding="utf-8")

        if phase_errors:
            failed_phase = phase_errors[0][0]
            message = "; ".join(
                f"{phase}: {exc}" for phase, exc in phase_errors
            )
            error = EvidenceCaptureError(message, checkpoint=checkpoint)
            _write_metadata(
                "failed",
                error={"type": type(error).__name__, "message": str(error)},
            )
            raise error from phase_errors[0][1]

        failed_phase = None
        _write_metadata("passed")

        return checkpoint

    def _capture_device_screenshot(
        self,
        *,
        device: str,
        checkpoint_name: str,
        output_path: Path,
        command_results: list[dict[str, object]],
    ) -> None:
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "-", checkpoint_name)
        remote_path = f"/data/local/tmp/aiverify-{safe_name}-screen.png"
        prefix = [self.adb_bin, "-s", device]
        self._run_checkpoint_command(
            [*prefix, "shell", "screencap", "-p", remote_path],
            phase="screenshot",
            command_results=command_results,
            timeout_seconds=self.screen_capture_timeout_seconds,
        )
        try:
            self._run_checkpoint_command(
                [*prefix, "pull", remote_path, str(output_path)],
                phase="screenshot",
                command_results=command_results,
                timeout_seconds=self.screen_capture_timeout_seconds,
            )
        finally:
            self._run_checkpoint_command(
                [*prefix, "shell", "rm", "-f", remote_path],
                phase="screenshot",
                command_results=command_results,
                timeout_seconds=self.screen_capture_timeout_seconds,
            )

    @staticmethod
    def _record_missing_artifact(
        *,
        phase: str,
        path: Path,
        command_results: list[dict[str, object]],
        phase_errors: list[tuple[str, EvidenceCaptureError]],
    ) -> None:
        matching_commands = [
            entry for entry in command_results if entry["phase"] == phase
        ]
        if not matching_commands or matching_commands[-1]["status"] != "passed":
            return
        if path.is_file() and path.stat().st_size > 0:
            return

        message = f"{phase} command did not create a non-empty artifact: {path}"
        matching_commands[-1]["status"] = "missing_artifact"
        matching_commands[-1]["error"] = message
        phase_errors.append((phase, EvidenceCaptureError(message)))

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
    evidence: EvidenceCheckpoint,
    status: str,
    failed_phase: str | None,
    error: dict[str, str] | None,
    command_count: int,
    phase_errors: list[dict[str, str]],
) -> dict[str, object]:
    artifacts = {
        "layout": str(evidence.layout_path),
        "screen": str(evidence.screenshot_path),
        "screen_annotated": (
            str(evidence.annotated_screenshot_path)
            if evidence.annotated_screenshot_path is not None
            else None
        ),
        "logcat": str(evidence.logcat_path),
        "commands": str(evidence.commands_path),
    }
    artifact_exists = {
        key: Path(value).exists() if value is not None else False
        for key, value in artifacts.items()
    }
    return {
        "checkpoint": evidence.name,
        "status": status,
        "failed_phase": failed_phase,
        "error": error,
        "phase_errors": phase_errors,
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
