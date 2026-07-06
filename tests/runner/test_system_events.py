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


def test_inject_process_death_home_kill_relaunch() -> None:
    injector, fake = _injector()

    injector.inject(
        SystemEventSpec(
            step_index=0,
            event="process_death",
            args={"background_wait": "0", "kill_wait": "0", "restore_wait": "0"},
        )
    )

    assert fake.commands[-3:] == [
        ["-s", "emulator-5554", "shell", "input", "keyevent", "HOME"],
        ["-s", "emulator-5554", "shell", "am", "kill", "org.example"],
        [
            "-s", "emulator-5554", "shell", "monkey", "-p", "org.example",
            "-c", "android.intent.category.LAUNCHER", "1",
        ],
    ]


def test_inject_process_death_relaunches_via_explicit_launcher_activity() -> None:
    # debug 构建常有多个 LAUNCHER activity（如 LeakCanary），monkey 拉起不确定；
    # 注入器携带 run spec 的 activity 时必须走显式 launcher intent。
    fake = FakeAdbRunner()
    device = DeviceController(serial="emulator-5554", runner=fake)
    injector = DeviceSystemEventInjector(
        device=device, package="org.example", activity="org.example.DefaultIcon"
    )

    injector.inject(
        SystemEventSpec(
            step_index=0,
            event="process_death",
            args={"background_wait": "0", "kill_wait": "0", "restore_wait": "0"},
        )
    )

    assert fake.commands[-1] == [
        "-s", "emulator-5554", "shell", "am", "start",
        "-a", "android.intent.action.MAIN",
        "-c", "android.intent.category.LAUNCHER",
        "-n", "org.example/org.example.DefaultIcon",
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


def test_inject_dark_mode_defaults_to_night_on() -> None:
    injector, fake = _injector()

    injector.inject(SystemEventSpec(step_index=0, event="dark_mode"))

    assert fake.commands[-1] == [
        "-s", "emulator-5554", "shell", "cmd", "uimode", "night", "yes",
    ]


def test_inject_dark_mode_night_off_via_args() -> None:
    injector, fake = _injector()

    injector.inject(SystemEventSpec(step_index=0, event="dark_mode", args={"night": "no"}))

    assert fake.commands[-1] == [
        "-s", "emulator-5554", "shell", "cmd", "uimode", "night", "no",
    ]
