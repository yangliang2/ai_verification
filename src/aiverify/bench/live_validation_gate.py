"""Live Android environment validation gate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from aiverify.runner.command import CommandResult, CommandRunner, SubprocessCommandRunner


_SCHEMA_VERSION = 1
_DEFAULT_TIMEOUT_SECONDS = 30
_DEFAULT_SNIPPET_CHARS = 4000


@dataclass(frozen=True)
class GateCheckResult:
    """Result for one live validation gate check."""

    name: str
    args: tuple[str, ...]
    status: str
    returncode: int | None
    stdout_snippet: str
    stderr_snippet: str
    timeout_seconds: int | None
    error: str | None = None
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    raw_stdout: str = ""
    raw_stderr: str = ""

    def to_dict(self) -> dict[str, object]:
        """Serialize this check into the gate JSON format."""

        return {
            "name": self.name,
            "args": list(self.args),
            "status": self.status,
            "returncode": self.returncode,
            "stdout_snippet": self.stdout_snippet,
            "stderr_snippet": self.stderr_snippet,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
            "timeout_seconds": self.timeout_seconds,
            "error": self.error,
        }


@dataclass(frozen=True)
class GateResult:
    """Overall live validation gate result."""

    device: str
    status: str
    checks: tuple[GateCheckResult, ...]
    app_package: str | None = None
    app_activity: str | None = None
    target_surface: dict[str, str] | None = None

    @property
    def failed_checks(self) -> tuple[str, ...]:
        """Names of checks that did not pass."""

        return tuple(check.name for check in self.checks if check.status != "passed")

    def to_dict(self) -> dict[str, object]:
        """Serialize this gate result into the committed JSON format."""

        payload: dict[str, object] = {
            "schema_version": _SCHEMA_VERSION,
            "status": self.status,
            "device": self.device,
            "failed_checks": list(self.failed_checks),
            "checks": [check.to_dict() for check in self.checks],
        }
        if self.app_package is not None:
            payload["app"] = {
                "package": self.app_package,
                "activity": self.app_activity,
                "target_surface": self.target_surface or {},
            }
        return payload


def run_live_validation_gate(
    *,
    device: str,
    runner: CommandRunner | None = None,
    android_bin: str = "android",
    adb_bin: str = "adb",
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    snippet_chars: int = _DEFAULT_SNIPPET_CHARS,
    app_package: str | None = None,
    app_activity: str | None = None,
    target_resource_id: str | None = None,
    target_text: str | None = None,
    target_content_desc: str | None = None,
    app_settle_seconds: float = 3.0,
) -> GateResult:
    """Run the required Android live environment checks."""

    target_surface = _target_surface(
        resource_id=target_resource_id,
        text=target_text,
        content_desc=target_content_desc,
    )
    if any([app_package, app_activity, target_surface]):
        _validate_app_smoke_args(
            app_package=app_package,
            app_activity=app_activity,
            target_surface=target_surface,
        )

    command_runner = runner if runner is not None else SubprocessCommandRunner()
    checks = [
        _check_adb_device_present(
            device=device,
            runner=command_runner,
            adb_bin=adb_bin,
            timeout_seconds=timeout_seconds,
            snippet_chars=snippet_chars,
        ),
        _check_stdout_equals(
            name="boot-completed",
            args=[adb_bin, "-s", device, "shell", "getprop", "sys.boot_completed"],
            expected="1",
            error_message="sys.boot_completed was not 1",
            runner=command_runner,
            timeout_seconds=timeout_seconds,
            snippet_chars=snippet_chars,
        ),
        _check_stdout_equals(
            name="boot-animation-stopped",
            args=[adb_bin, "-s", device, "shell", "getprop", "init.svc.bootanim"],
            expected="stopped",
            error_message="init.svc.bootanim was not stopped",
            runner=command_runner,
            timeout_seconds=timeout_seconds,
            snippet_chars=snippet_chars,
        ),
        _check_android_layout(
            args=[android_bin, "layout", "--pretty", "--device", device],
            runner=command_runner,
            timeout_seconds=timeout_seconds,
            snippet_chars=snippet_chars,
        ),
        _check_returncode_zero(
            name="uiautomator-dump",
            args=[
                adb_bin,
                "-s",
                device,
                "shell",
                "uiautomator",
                "dump",
                "/sdcard/window_dump.xml",
            ],
            error_message="direct UIAutomator dump failed",
            runner=command_runner,
            timeout_seconds=timeout_seconds,
            snippet_chars=snippet_chars,
        ),
    ]
    if (
        app_package is not None
        and app_activity is not None
        and all(check.status == "passed" for check in checks)
    ):
        checks.extend(
            _run_app_smoke_checks(
                device=device,
                app_package=app_package,
                app_activity=app_activity,
                target_surface=target_surface,
                runner=command_runner,
                android_bin=android_bin,
                adb_bin=adb_bin,
                timeout_seconds=timeout_seconds,
                snippet_chars=snippet_chars,
                app_settle_seconds=app_settle_seconds,
            )
        )
    status = "passed" if all(check.status == "passed" for check in checks) else "failed"
    return GateResult(
        device=device,
        status=status,
        checks=tuple(checks),
        app_package=app_package,
        app_activity=app_activity,
        target_surface=target_surface or None,
    )


def main(argv: list[str] | None = None, *, runner: CommandRunner | None = None) -> int:
    """CLI entrypoint for the live validation gate."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--device",
        required=True,
        help="adb device serial, for example emulator-5554",
    )
    parser.add_argument("--output", type=Path, help="optional JSON output path")
    parser.add_argument("--android-bin", default="android", help="Android CLI binary")
    parser.add_argument("--adb-bin", default="adb", help="adb binary")
    parser.add_argument("--app-package", help="optional app package for app-level smoke")
    parser.add_argument("--app-activity", help="optional launcher activity for app-level smoke")
    parser.add_argument("--target-resource-id", help="target resource-id required in app layout")
    parser.add_argument("--target-text", help="target text required in app layout")
    parser.add_argument("--target-content-desc", help="target content-desc required in app layout")
    parser.add_argument(
        "--app-settle-seconds",
        type=float,
        default=3.0,
        help="sleep after app launch before foreground/layout checks",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=_DEFAULT_TIMEOUT_SECONDS,
        help="timeout for each gate command",
    )
    parser.add_argument(
        "--snippet-chars",
        type=int,
        default=_DEFAULT_SNIPPET_CHARS,
        help="maximum stdout/stderr characters stored per check",
    )
    args = parser.parse_args(argv)

    try:
        result = run_live_validation_gate(
            device=args.device,
            runner=runner,
            android_bin=args.android_bin,
            adb_bin=args.adb_bin,
            timeout_seconds=args.timeout_seconds,
            snippet_chars=args.snippet_chars,
            app_package=args.app_package,
            app_activity=args.app_activity,
            target_resource_id=args.target_resource_id,
            target_text=args.target_text,
            target_content_desc=args.target_content_desc,
            app_settle_seconds=args.app_settle_seconds,
        )
    except ValueError as exc:
        parser.error(str(exc))
    payload = json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    sys.stdout.write(payload)
    return 0 if result.status == "passed" else 2


def _check_adb_device_present(
    *,
    device: str,
    runner: CommandRunner,
    adb_bin: str,
    timeout_seconds: int,
    snippet_chars: int,
) -> GateCheckResult:
    args = [adb_bin, "devices", "-l"]
    result = _run_gate_command(
        name="adb-device-present",
        args=args,
        runner=runner,
        timeout_seconds=timeout_seconds,
        snippet_chars=snippet_chars,
    )
    if result.status != "passed":
        return result

    state = _adb_device_state(result.raw_stdout, device)
    if state == "device":
        return result
    if state is None:
        error = f"{device} was not listed by adb devices -l"
    else:
        error = f"{device} was listed as {state!r}, not 'device'"
    return _replace_status(result, status="failed", error=error)


def _check_stdout_equals(
    *,
    name: str,
    args: list[str],
    expected: str,
    error_message: str,
    runner: CommandRunner,
    timeout_seconds: int,
    snippet_chars: int,
) -> GateCheckResult:
    result = _run_gate_command(
        name=name,
        args=args,
        runner=runner,
        timeout_seconds=timeout_seconds,
        snippet_chars=snippet_chars,
    )
    if result.status != "passed":
        return result
    actual = result.raw_stdout.strip()
    if actual == expected:
        return result
    return _replace_status(result, status="failed", error=f"{error_message}: {actual!r}")


def _check_android_layout(
    *,
    args: list[str],
    runner: CommandRunner,
    timeout_seconds: int,
    snippet_chars: int,
) -> GateCheckResult:
    result = _run_gate_command(
        name="android-layout-json",
        args=args,
        runner=runner,
        timeout_seconds=timeout_seconds,
        snippet_chars=snippet_chars,
    )
    if result.status != "passed":
        return result
    try:
        parsed = json.loads(result.raw_stdout)
    except json.JSONDecodeError as exc:
        return _replace_status(
            result,
            status="failed",
            error=f"layout stdout was not JSON: {exc}",
        )
    if not isinstance(parsed, list):
        return _replace_status(
            result,
            status="failed",
            error="layout stdout was not a JSON list",
        )
    return result


def _check_returncode_zero(
    *,
    name: str,
    args: list[str],
    error_message: str,
    runner: CommandRunner,
    timeout_seconds: int,
    snippet_chars: int,
) -> GateCheckResult:
    result = _run_gate_command(
        name=name,
        args=args,
        runner=runner,
        timeout_seconds=timeout_seconds,
        snippet_chars=snippet_chars,
    )
    if result.status == "passed":
        return result
    return _replace_status(
        result,
        error=error_message if result.error is None else result.error,
    )


def _run_app_smoke_checks(
    *,
    device: str,
    app_package: str,
    app_activity: str,
    target_surface: dict[str, str],
    runner: CommandRunner,
    android_bin: str,
    adb_bin: str,
    timeout_seconds: int,
    snippet_chars: int,
    app_settle_seconds: float,
) -> list[GateCheckResult]:
    launch = _check_app_launch(
        device=device,
        app_package=app_package,
        app_activity=app_activity,
        runner=runner,
        adb_bin=adb_bin,
        timeout_seconds=timeout_seconds,
        snippet_chars=snippet_chars,
    )
    if app_settle_seconds > 0:
        time.sleep(app_settle_seconds)
    return [
        launch,
        _check_foreground_package(
            device=device,
            app_package=app_package,
            runner=runner,
            adb_bin=adb_bin,
            timeout_seconds=timeout_seconds,
            snippet_chars=snippet_chars,
        ),
        _check_app_target_surface(
            device=device,
            target_surface=target_surface,
            runner=runner,
            android_bin=android_bin,
            timeout_seconds=timeout_seconds,
            snippet_chars=snippet_chars,
        ),
    ]


def _check_app_launch(
    *,
    device: str,
    app_package: str,
    app_activity: str,
    runner: CommandRunner,
    adb_bin: str,
    timeout_seconds: int,
    snippet_chars: int,
) -> GateCheckResult:
    result = _run_gate_command(
        name="app-launch",
        args=[
            adb_bin,
            "-s",
            device,
            "shell",
            "am",
            "start",
            "-W",
            "-a",
            "android.intent.action.MAIN",
            "-c",
            "android.intent.category.LAUNCHER",
            "-n",
            f"{app_package}/{app_activity}",
        ],
        runner=runner,
        timeout_seconds=timeout_seconds,
        snippet_chars=snippet_chars,
    )
    if result.status != "passed":
        return result
    if "Status: ok" in result.raw_stdout:
        return result
    return _replace_status(result, status="failed", error="app launch did not report Status: ok")


def _check_foreground_package(
    *,
    device: str,
    app_package: str,
    runner: CommandRunner,
    adb_bin: str,
    timeout_seconds: int,
    snippet_chars: int,
) -> GateCheckResult:
    result = _run_gate_command(
        name="app-foreground-package",
        args=[adb_bin, "-s", device, "shell", "dumpsys", "window"],
        runner=runner,
        timeout_seconds=timeout_seconds,
        snippet_chars=snippet_chars,
    )
    if result.status != "passed":
        return result
    if app_package in result.raw_stdout:
        return result
    return _replace_status(
        result,
        status="failed",
        error=f"{app_package} was not found in dumpsys window output",
    )


def _check_app_target_surface(
    *,
    device: str,
    target_surface: dict[str, str],
    runner: CommandRunner,
    android_bin: str,
    timeout_seconds: int,
    snippet_chars: int,
) -> GateCheckResult:
    result = _run_gate_command(
        name="app-target-surface",
        args=[android_bin, "layout", "--pretty", "--device", device],
        runner=runner,
        timeout_seconds=timeout_seconds,
        snippet_chars=snippet_chars,
    )
    if result.status != "passed":
        return result
    try:
        layout = json.loads(result.raw_stdout)
    except json.JSONDecodeError as exc:
        return _replace_status(
            result,
            status="failed",
            error=f"app layout stdout was not JSON: {exc}",
        )
    if not isinstance(layout, list):
        return _replace_status(result, status="failed", error="app layout was not a JSON list")
    if any(_node_matches_target(node, target_surface) for node in layout):
        return result
    return _replace_status(
        result,
        status="failed",
        error=f"target surface not found: {target_surface}",
    )


def _run_gate_command(
    *,
    name: str,
    args: list[str],
    runner: CommandRunner,
    timeout_seconds: int,
    snippet_chars: int,
) -> GateCheckResult:
    try:
        result = runner.run(args, timeout_seconds=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        stdout, stdout_truncated = _snippet("", snippet_chars)
        stderr, stderr_truncated = _snippet("", snippet_chars)
        return GateCheckResult(
            name=name,
            args=tuple(args),
            status="timeout",
            returncode=None,
            stdout_snippet=stdout,
            stderr_snippet=stderr,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            timeout_seconds=timeout_seconds,
            error=f"command timed out after {exc.timeout}s",
            raw_stdout="",
            raw_stderr="",
        )

    status = "passed" if result.returncode == 0 else "failed"
    stdout, stdout_truncated = _snippet(result.stdout, snippet_chars)
    stderr, stderr_truncated = _snippet(result.stderr, snippet_chars)
    error = None
    if result.returncode != 0:
        error = f"command failed with exit code {result.returncode}"
    return GateCheckResult(
        name=name,
        args=tuple(result.args),
        status=status,
        returncode=result.returncode,
        stdout_snippet=stdout,
        stderr_snippet=stderr,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        timeout_seconds=timeout_seconds,
        error=error,
        raw_stdout=result.stdout,
        raw_stderr=result.stderr,
    )


def _replace_status(
    result: GateCheckResult,
    *,
    status: str | None = None,
    error: str | None = None,
) -> GateCheckResult:
    return GateCheckResult(
        name=result.name,
        args=result.args,
        status=result.status if status is None else status,
        returncode=result.returncode,
        stdout_snippet=result.stdout_snippet,
        stderr_snippet=result.stderr_snippet,
        stdout_truncated=result.stdout_truncated,
        stderr_truncated=result.stderr_truncated,
        timeout_seconds=result.timeout_seconds,
        error=error,
        raw_stdout=result.raw_stdout,
        raw_stderr=result.raw_stderr,
    )


def _adb_device_state(devices_stdout: str, device: str) -> str | None:
    for line in devices_stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == device:
            return parts[1]
    return None


def _snippet(text: str, limit: int) -> tuple[str, bool]:
    if limit < 1:
        return "", bool(text)
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _target_surface(
    *,
    resource_id: str | None,
    text: str | None,
    content_desc: str | None,
) -> dict[str, str]:
    target: dict[str, str] = {}
    if resource_id:
        target["resource_id"] = resource_id
    if text:
        target["text"] = text
    if content_desc:
        target["content_desc"] = content_desc
    return target


def _validate_app_smoke_args(
    *,
    app_package: str | None,
    app_activity: str | None,
    target_surface: dict[str, str],
) -> None:
    if not app_package:
        raise ValueError("app smoke requires app_package")
    if not app_activity:
        raise ValueError("app smoke requires app_activity")
    if not target_surface:
        raise ValueError("app smoke requires at least one target surface criterion")


def _node_matches_target(node: object, target_surface: dict[str, str]) -> bool:
    if not isinstance(node, dict):
        return False
    resource_id = target_surface.get("resource_id")
    if resource_id and not _resource_id_matches(
        _first_str(node, "resource-id", "resourceId"),
        resource_id,
    ):
        return False
    text = target_surface.get("text")
    if text and _first_str(node, "text") != text:
        return False
    content_desc = target_surface.get("content_desc")
    if content_desc and _first_str(node, "content-desc", "contentDesc") != content_desc:
        return False
    return True


def _first_str(node: dict[object, object], *keys: str) -> str | None:
    for key in keys:
        value = node.get(key)
        if isinstance(value, str):
            return value
    return None


def _resource_id_matches(actual: str | None, expected: str) -> bool:
    if actual is None:
        return False
    return actual == expected or actual.endswith(f":id/{expected}")


if __name__ == "__main__":
    raise SystemExit(main())
