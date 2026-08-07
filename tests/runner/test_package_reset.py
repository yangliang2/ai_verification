from __future__ import annotations

import pytest

from aiverify.harness.device import AdbResult
from aiverify.harness.device.adb import FakeAdbRunner
from aiverify.harness.device.controller import DeviceController
from aiverify.runner.package_reset import (
    PackageResetError,
    reset_package_data,
)


DEVICE = "emulator-5554"
PACKAGE = "com.example.app"


def _controller(*results: AdbResult) -> tuple[DeviceController, FakeAdbRunner]:
    runner = FakeAdbRunner()
    runner.enqueue_many(list(results))
    return DeviceController(serial=DEVICE, runner=runner), runner


def test_absent_package_is_already_clean_without_clear() -> None:
    controller, runner = _controller(
        AdbResult(stdout="", stderr="", returncode=1),
    )

    result = reset_package_data(
        controller=controller,
        device_serial=DEVICE,
        package=PACKAGE,
    )

    assert result.status == "already_absent"
    assert result.clear_performed is False
    assert result.to_dict()["identity"] == {
        "device_serial": DEVICE,
        "package": PACKAGE,
    }
    assert runner.commands == [
        ["-s", DEVICE, "shell", "pm", "path", PACKAGE],
    ]


def test_controller_device_identity_must_match_the_receipt() -> None:
    controller, runner = _controller(
        AdbResult(stdout="", stderr="", returncode=1),
    )

    with pytest.raises(ValueError, match="controller serial contradicts"):
        reset_package_data(
            controller=controller,
            device_serial="emulator-5556",
            package=PACKAGE,
        )

    assert runner.commands == []


def test_installed_package_must_clear_successfully() -> None:
    controller, runner = _controller(
        AdbResult(
            stdout="package:/data/app/~~token/com.example.app/base.apk\n",
            stderr="",
            returncode=0,
        ),
        AdbResult(stdout="Success\n", stderr="", returncode=0),
    )

    result = reset_package_data(
        controller=controller,
        device_serial=DEVICE,
        package=PACKAGE,
    )

    assert result.status == "cleared"
    assert result.clear_performed is True
    assert result.installed_paths == (
        "/data/app/~~token/com.example.app/base.apk",
    )
    assert runner.commands == [
        ["-s", DEVICE, "shell", "pm", "path", PACKAGE],
        ["-s", DEVICE, "shell", "pm", "clear", PACKAGE],
    ]


def test_installed_package_clear_failure_is_not_treated_as_absent() -> None:
    controller, _runner = _controller(
        AdbResult(
            stdout="package:/data/app/com.example.app/base.apk\n",
            stderr="",
            returncode=0,
        ),
        AdbResult(stdout="Failed\n", stderr="", returncode=1),
    )

    with pytest.raises(PackageResetError, match="installed package data clear failed") as caught:
        reset_package_data(
            controller=controller,
            device_serial=DEVICE,
            package=PACKAGE,
        )

    assert caught.value.result.status == "clear_failed"
    assert caught.value.result.clear_performed is True


@pytest.mark.parametrize(
    ("query", "message"),
    [
        (
            AdbResult(stdout="", stderr="error: device offline\n", returncode=1),
            "package presence query failed",
        ),
        (
            AdbResult(stdout="Failed\n", stderr="", returncode=1),
            "package presence query was contradictory",
        ),
        (
            AdbResult(stdout="unexpected\n", stderr="", returncode=0),
            "package presence query was contradictory",
        ),
        (
            AdbResult(
                stdout=(
                    "package:/data/app/com.example.app/base.apk\n"
                    "package:/data/app/com.example.app/base.apk\n"
                ),
                stderr="",
                returncode=0,
            ),
            "package presence query was contradictory",
        ),
    ],
)
def test_query_failures_and_contradictions_fail_closed(
    query: AdbResult,
    message: str,
) -> None:
    controller, runner = _controller(query)

    with pytest.raises(PackageResetError, match=message) as caught:
        reset_package_data(
            controller=controller,
            device_serial=DEVICE,
            package=PACKAGE,
        )

    assert caught.value.result.status in {"query_failed", "query_contradiction"}
    assert caught.value.result.clear_performed is False
    assert runner.commands == [
        ["-s", DEVICE, "shell", "pm", "path", PACKAGE],
    ]
