from __future__ import annotations

import pytest

from aiverify.harness.device import FakeAdbRunner
from aiverify.harness.device.controller import DeviceController
from aiverify.runner.run_spec import SystemEventSpec
from aiverify.runner.system_events import (
    DeviceSystemEventInjector,
    SystemEventInjectionError,
)


def _injector() -> tuple[DeviceSystemEventInjector, FakeAdbRunner]:
    fake = FakeAdbRunner()
    device = DeviceController(serial="emulator-5554", runner=fake)
    return DeviceSystemEventInjector(device=device, package="org.example"), fake


def test_inject_rotate_uses_device_controller_rotation() -> None:
    injector, fake = _injector()

    injector.inject(SystemEventSpec(step_index=0, event="rotate", args={"rotation": "3"}))

    assert fake.commands[-2:] == [
        ["-s", "emulator-5554", "shell", "settings", "put", "system", "accelerometer_rotation", "0"],
        ["-s", "emulator-5554", "shell", "settings", "put", "system", "user_rotation", "3"],
    ]


def test_inject_network_off_toggles_wifi_and_data() -> None:
    injector, fake = _injector()

    injector.inject(SystemEventSpec(step_index=0, event="network_off"))

    assert fake.commands[-2:] == [
        ["-s", "emulator-5554", "shell", "svc", "wifi", "disable"],
        ["-s", "emulator-5554", "shell", "svc", "data", "disable"],
    ]


def test_inject_revoke_permission_requires_permission_arg() -> None:
    injector, _fake = _injector()

    with pytest.raises(SystemEventInjectionError, match="permission"):
        injector.inject(SystemEventSpec(step_index=0, event="revoke_permission"))


def test_inject_kill_background_uses_package() -> None:
    injector, fake = _injector()

    injector.inject(SystemEventSpec(step_index=0, event="kill_background"))

    assert fake.commands[-1] == [
        "-s",
        "emulator-5554",
        "shell",
        "am",
        "kill",
        "org.example",
    ]


def test_inject_app_to_background_presses_home() -> None:
    injector, fake = _injector()

    injector.inject(SystemEventSpec(step_index=0, event="app_to_background"))

    assert fake.commands[-1] == [
        "-s",
        "emulator-5554",
        "shell",
        "input",
        "keyevent",
        "HOME",
    ]
