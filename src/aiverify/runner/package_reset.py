"""Fail-closed Android package-data reset for pre-install runner setup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from aiverify.harness.device import AdbResult
from aiverify.harness.device.controller import DeviceController


PackageResetStatus = Literal[
    "already_absent",
    "cleared",
    "query_failed",
    "query_contradiction",
    "clear_failed",
]


def _command(
    device_serial: str,
    *args: str,
) -> list[str]:
    return ["adb", "-s", device_serial, "shell", *args]


def _command_result(command: list[str], result: AdbResult) -> dict[str, object]:
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


@dataclass(frozen=True)
class PackageResetResult:
    """Auditable result for one package-data reset decision."""

    device_serial: str
    package: str
    status: PackageResetStatus
    clear_performed: bool
    presence_query: AdbResult
    installed_paths: tuple[str, ...] = ()
    clear_result: AdbResult | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 1,
            "identity": {
                "device_serial": self.device_serial,
                "package": self.package,
            },
            "status": self.status,
            "clear_performed": self.clear_performed,
            "installed_paths": list(self.installed_paths),
            "presence_query": _command_result(
                _command(
                    self.device_serial,
                    "pm",
                    "path",
                    self.package,
                ),
                self.presence_query,
            ),
            "clear_result": None,
        }
        if self.clear_result is not None:
            payload["clear_result"] = _command_result(
                _command(
                    self.device_serial,
                    "pm",
                    "clear",
                    self.package,
                ),
                self.clear_result,
            )
        return payload


class PackageResetError(RuntimeError):
    """Raised with the terminal receipt when package reset cannot be trusted."""

    def __init__(self, message: str, result: PackageResetResult) -> None:
        super().__init__(message)
        self.result = result


def _installed_paths(query: AdbResult) -> tuple[str, ...] | None:
    if query.returncode != 0 or query.stderr.strip():
        return None
    lines = [line.strip() for line in query.stdout.splitlines() if line.strip()]
    if not lines:
        return None
    paths: list[str] = []
    for line in lines:
        if not line.startswith("package:"):
            return None
        path = line.removeprefix("package:").strip()
        if not path.startswith("/"):
            return None
        paths.append(path)
    if len(paths) != len(set(paths)):
        return None
    return tuple(paths)


def reset_package_data(
    *,
    controller: DeviceController,
    device_serial: str,
    package: str,
) -> PackageResetResult:
    """Clear installed app data or prove that the package is already absent.

    Android overloads ``pm clear``'s ``Failed`` response: it is expected for an
    absent package but can also describe a real clear failure.  This operation
    first queries the exact package identity, accepts only the observed API-35
    absent shape (empty stdout/stderr with exit code one), and otherwise
    requires an installed-path proof followed by an exact successful clear.
    """

    if not device_serial or any(character.isspace() for character in device_serial):
        raise ValueError("device_serial must be a non-empty token")
    if not package or any(character.isspace() for character in package):
        raise ValueError("package must be a non-empty token")
    if controller.serial != device_serial:
        raise ValueError(
            "controller serial contradicts the package-reset device identity"
        )

    query = controller.package_paths(package)
    if query.returncode == 1 and not query.stdout and not query.stderr:
        return PackageResetResult(
            device_serial=device_serial,
            package=package,
            status="already_absent",
            clear_performed=False,
            presence_query=query,
        )

    paths = _installed_paths(query)
    if paths is None:
        if query.stderr.strip() or query.returncode not in {0, 1}:
            status: PackageResetStatus = "query_failed"
            message = "package presence query failed"
        else:
            status = "query_contradiction"
            message = "package presence query was contradictory"
        result = PackageResetResult(
            device_serial=device_serial,
            package=package,
            status=status,
            clear_performed=False,
            presence_query=query,
        )
        raise PackageResetError(message, result)

    cleared = controller.clear_data(package)
    result = PackageResetResult(
        device_serial=device_serial,
        package=package,
        status=(
            "cleared"
            if (
                cleared.returncode == 0
                and cleared.stdout.strip() == "Success"
                and not cleared.stderr.strip()
            )
            else "clear_failed"
        ),
        clear_performed=True,
        presence_query=query,
        installed_paths=paths,
        clear_result=cleared,
    )
    if result.status != "cleared":
        raise PackageResetError("installed package data clear failed", result)
    return result
