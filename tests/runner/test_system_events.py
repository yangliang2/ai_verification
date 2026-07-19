from __future__ import annotations

import pytest

from aiverify.harness.device import AdbResult, FakeAdbRunner
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
    fake.enqueue_many(
        [
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="0\n", stderr="", returncode=0),
            AdbResult(stdout="3\n", stderr="", returncode=0),
        ]
    )

    evidence = injector.inject(
        SystemEventSpec(step_index=0, event="rotate", args={"rotation": "3"})
    )

    assert evidence == {
        "accelerometer_rotation": "0",
        "user_rotation": "3",
    }

    assert fake.commands[-4:] == [
        ["-s", "emulator-5554", "shell", "settings", "put", "system", "accelerometer_rotation", "0"],
        ["-s", "emulator-5554", "shell", "settings", "put", "system", "user_rotation", "3"],
        ["-s", "emulator-5554", "shell", "settings", "get", "system", "accelerometer_rotation"],
        ["-s", "emulator-5554", "shell", "settings", "get", "system", "user_rotation"],
    ]


def test_inject_rotate_fails_closed_on_nonzero_process_exit() -> None:
    injector, fake = _injector()
    fake.enqueue(AdbResult(stdout="", stderr="permission denied", returncode=1))

    with pytest.raises(
        SystemEventInjectionError, match="rotate.*return code 1.*permission denied"
    ):
        injector.inject(
            SystemEventSpec(step_index=0, event="rotate", args={"rotation": "3"})
        )

    assert fake.commands == [
        [
            "-s",
            "emulator-5554",
            "shell",
            "settings",
            "put",
            "system",
            "accelerometer_rotation",
            "0",
        ],
        [
            "-s",
            "emulator-5554",
            "shell",
            "settings",
            "put",
            "system",
            "user_rotation",
            "3",
        ],
    ]


def test_inject_rotate_fails_closed_when_postcondition_does_not_match() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="0\n", stderr="", returncode=0),
            AdbResult(stdout="1\n", stderr="", returncode=0),
        ]
    )

    with pytest.raises(
        SystemEventInjectionError,
        match="rotate postcondition failed.*expected user_rotation=3.*observed '1'",
    ):
        injector.inject(
            SystemEventSpec(step_index=0, event="rotate", args={"rotation": "3"})
        )


def test_inject_rotate_fails_closed_when_auto_rotation_remains_enabled() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="1\n", stderr="", returncode=0),
        ]
    )

    with pytest.raises(
        SystemEventInjectionError,
        match="rotate postcondition failed.*expected accelerometer_rotation=0.*observed '1'",
    ):
        injector.inject(
            SystemEventSpec(step_index=0, event="rotate", args={"rotation": "3"})
        )


@pytest.mark.parametrize("rotation", ["-1", "4", "portrait"])
def test_inject_rotate_rejects_values_outside_android_rotation_domain(
    rotation: str,
) -> None:
    injector, fake = _injector()

    with pytest.raises(
        SystemEventInjectionError,
        match=rf"rotate requires args.rotation to be one of 0, 1, 2, 3; got {rotation!r}",
    ):
        injector.inject(
            SystemEventSpec(
                step_index=0,
                event="rotate",
                args={"rotation": rotation},
            )
        )

    assert fake.commands == []


def test_inject_process_death_home_kill_relaunch() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="111\n", stderr="", returncode=0),
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(
                stdout=(
                    "topResumedActivity=ActivityRecord{123 u0 "
                    "com.android.launcher3/.QuickstepLauncher t4}\n"
                ),
                stderr="",
                returncode=0,
            ),
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="", stderr="", returncode=1),
            AdbResult(stdout="Events injected: 1", stderr="", returncode=0),
            AdbResult(
                stdout=(
                    "topResumedActivity=ActivityRecord{456 u0 "
                    "org.example/.MainActivity t9}\n"
                ),
                stderr="",
                returncode=0,
            ),
            AdbResult(stdout="222\n", stderr="", returncode=0),
        ]
    )

    evidence = injector.inject(
        SystemEventSpec(
            step_index=0,
            event="process_death",
            args={"background_wait": "0", "kill_wait": "0", "restore_wait": "0"},
        )
    )

    assert evidence == {
        "before_pids": ["111"],
        "background_status": "success",
        "background_resumed_package": "com.android.launcher3",
        "target_resumed_after_home": False,
        "kill_status": "success",
        "process_absent_after_kill": True,
        "relaunch_status": "success",
        "foreground_resumed_package": "org.example",
        "target_resumed_after_relaunch": True,
        "after_pids": ["222"],
    }
    assert fake.commands[-8:] == [
        ["-s", "emulator-5554", "shell", "pidof", "org.example"],
        ["-s", "emulator-5554", "shell", "input", "keyevent", "HOME"],
        [
            "-s", "emulator-5554", "shell", "dumpsys", "activity", "activities",
        ],
        ["-s", "emulator-5554", "shell", "am", "kill", "org.example"],
        ["-s", "emulator-5554", "shell", "pidof", "org.example"],
        [
            "-s", "emulator-5554", "shell", "monkey", "-p", "org.example",
            "-c", "android.intent.category.LAUNCHER", "1",
        ],
        [
            "-s", "emulator-5554", "shell", "dumpsys", "activity", "activities",
        ],
        ["-s", "emulator-5554", "shell", "pidof", "org.example"],
    ]


def test_inject_process_death_relaunches_via_explicit_launcher_activity() -> None:
    # debug 构建常有多个 LAUNCHER activity（如 LeakCanary），monkey 拉起不确定；
    # 注入器携带 run spec 的 activity 时必须走显式 launcher intent。
    fake = FakeAdbRunner()
    device = DeviceController(serial="emulator-5554", runner=fake)
    injector = DeviceSystemEventInjector(
        device=device, package="org.example", activity="org.example.DefaultIcon"
    )
    fake.enqueue_many(
        [
            AdbResult(stdout="111\n", stderr="", returncode=0),
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(
                stdout=(
                    "topResumedActivity=ActivityRecord{123 u0 "
                    "com.android.launcher3/.QuickstepLauncher t4}\n"
                ),
                stderr="",
                returncode=0,
            ),
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="", stderr="", returncode=1),
            AdbResult(stdout="Starting: Intent", stderr="", returncode=0),
            AdbResult(
                stdout=(
                    "topResumedActivity=ActivityRecord{456 u0 "
                    "org.example/.MainActivity t9}\n"
                ),
                stderr="",
                returncode=0,
            ),
            AdbResult(stdout="222\n", stderr="", returncode=0),
        ]
    )

    injector.inject(
        SystemEventSpec(
            step_index=0,
            event="process_death",
            args={"background_wait": "0", "kill_wait": "0", "restore_wait": "0"},
        )
    )

    assert fake.commands[-3] == [
        "-s", "emulator-5554", "shell", "am", "start",
        "-a", "android.intent.action.MAIN",
        "-c", "android.intent.category.LAUNCHER",
        "-n", "org.example/org.example.DefaultIcon",
    ]


def test_inject_process_death_checks_every_phase_process_exit() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="111\n", stderr="", returncode=0),
            AdbResult(stdout="", stderr="HOME dispatch failed", returncode=3),
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="Events injected: 1", stderr="", returncode=0),
        ]
    )

    with pytest.raises(
        SystemEventInjectionError,
        match="process_death.*return code 3.*HOME dispatch failed",
    ):
        injector.inject(
            SystemEventSpec(
                step_index=0,
                event="process_death",
                args={
                    "background_wait": "0",
                    "kill_wait": "0",
                    "restore_wait": "0",
                },
            )
        )


def test_inject_process_death_fails_closed_when_process_identity_is_unchanged() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="4242\n", stderr="", returncode=0),
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(
                stdout=(
                    "topResumedActivity=ActivityRecord{123 u0 "
                    "com.android.launcher3/.QuickstepLauncher t4}\n"
                ),
                stderr="",
                returncode=0,
            ),
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="", stderr="", returncode=1),
            AdbResult(stdout="Events injected: 1", stderr="", returncode=0),
            AdbResult(
                stdout=(
                    "topResumedActivity=ActivityRecord{456 u0 "
                    "org.example/.MainActivity t9}\n"
                ),
                stderr="",
                returncode=0,
            ),
            AdbResult(stdout="4242\n", stderr="", returncode=0),
        ]
    )

    with pytest.raises(
        SystemEventInjectionError,
        match="process_death postcondition failed.*process 4242 survived",
    ):
        injector.inject(
            SystemEventSpec(
                step_index=0,
                event="process_death",
                args={
                    "background_wait": "0",
                    "kill_wait": "0",
                    "restore_wait": "0",
                },
            )
        )


def test_inject_backup_restore_records_transport_restore_and_process_evidence() -> None:
    fake = FakeAdbRunner()
    device = DeviceController(serial="emulator-5554", runner=fake)
    injector = DeviceSystemEventInjector(
        device=device,
        package="org.example",
        activity="org.example.MainActivity",
    )
    local = "com.android.localtransport/.LocalTransport"
    cloud = "com.google.android.gms/.backup.BackupTransportService"
    fake.enqueue_many(
        [
            AdbResult(
                stdout="Backup Manager currently disabled\n",
                stderr="",
                returncode=0,
            ),
            AdbResult(
                stdout=f"    {local}\n  * {cloud}\n",
                stderr="",
                returncode=0,
            ),
            AdbResult(stdout="Backup Manager now enabled\n", stderr="", returncode=0),
            AdbResult(stdout=f"Selected transport {local}\n", stderr="", returncode=0),
            AdbResult(
                stdout=f"  * {local}\n    {cloud}\n",
                stderr="",
                returncode=0,
            ),
            AdbResult(stdout="Wiped org.example\n", stderr="", returncode=0),
            AdbResult(
                stdout="Package org.example with result: Success\n",
                stderr="",
                returncode=0,
            ),
            AdbResult(stdout="1 : Local disk image\n", stderr="", returncode=0),
            AdbResult(stdout="Success\n", stderr="", returncode=0),
            AdbResult(
                stdout="restoreStarting: 1 packages\nrestoreFinished: 0\n",
                stderr="",
                returncode=0,
            ),
            AdbResult(stdout="Starting: Intent\n", stderr="", returncode=0),
            AdbResult(stdout="333\n", stderr="", returncode=0),
            AdbResult(stdout=f"Selected transport {cloud}\n", stderr="", returncode=0),
            AdbResult(stdout="Backup Manager now disabled\n", stderr="", returncode=0),
            AdbResult(
                stdout=f"    {local}\n  * {cloud}\n",
                stderr="",
                returncode=0,
            ),
            AdbResult(
                stdout="Backup Manager currently disabled\n",
                stderr="",
                returncode=0,
            ),
        ]
    )

    evidence = injector.inject(
        SystemEventSpec(
            step_index=0,
            event="backup_restore",
            args={"transport": local, "restore_wait": "0"},
        )
    )

    assert evidence == {
        "transport": local,
        "previous_transport": cloud,
        "backup_was_enabled": False,
        "backup_status": "success",
        "clear_data_status": "success",
        "clear_data_output": "Success",
        "restore_status": "success",
        "restore_token": "1",
        "post_restore_pids": ["333"],
        "backup_output": "Package org.example with result: Success",
        "restore_output": "restoreStarting: 1 packages\nrestoreFinished: 0",
        "cleanup_status": "success",
        "cleanup_transport": cloud,
        "cleanup_backup_enabled": False,
    }
    assert fake.commands == [
        ["-s", "emulator-5554", "shell", "bmgr", "enabled"],
        ["-s", "emulator-5554", "shell", "bmgr", "list", "transports"],
        ["-s", "emulator-5554", "shell", "bmgr", "enable", "true"],
        ["-s", "emulator-5554", "shell", "bmgr", "transport", local],
        ["-s", "emulator-5554", "shell", "bmgr", "list", "transports"],
        ["-s", "emulator-5554", "shell", "bmgr", "wipe", local, "org.example"],
        [
            "-s", "emulator-5554", "shell", "bmgr", "backupnow", "--monitor",
            "org.example",
        ],
        ["-s", "emulator-5554", "shell", "bmgr", "list", "sets"],
        ["-s", "emulator-5554", "shell", "pm", "clear", "org.example"],
        [
            "-s", "emulator-5554", "shell", "bmgr", "restore", "1",
            "org.example", "--monitor",
        ],
        [
            "-s", "emulator-5554", "shell", "am", "start", "-n",
            "org.example/org.example.MainActivity",
        ],
        ["-s", "emulator-5554", "shell", "pidof", "org.example"],
        ["-s", "emulator-5554", "shell", "bmgr", "transport", cloud],
        ["-s", "emulator-5554", "shell", "bmgr", "enable", "false"],
        ["-s", "emulator-5554", "shell", "bmgr", "list", "transports"],
        ["-s", "emulator-5554", "shell", "bmgr", "enabled"],
    ]


def test_inject_backup_restore_fails_closed_and_restores_backup_configuration() -> None:
    injector, fake = _injector()
    local = "com.android.localtransport/.LocalTransport"
    cloud = "com.google.android.gms/.backup.BackupTransportService"
    fake.enqueue_many(
        [
            AdbResult(
                stdout="Backup Manager currently disabled\n",
                stderr="",
                returncode=0,
            ),
            AdbResult(
                stdout=f"    {local}\n  * {cloud}\n",
                stderr="",
                returncode=0,
            ),
            AdbResult(stdout="Backup Manager now enabled\n", stderr="", returncode=0),
            AdbResult(stdout=f"Selected transport {local}\n", stderr="", returncode=0),
            AdbResult(
                stdout=f"  * {local}\n    {cloud}\n",
                stderr="",
                returncode=0,
            ),
            AdbResult(stdout="Wiped org.example\n", stderr="", returncode=0),
            AdbResult(
                stdout="Package org.example with result: Transport rejected\n",
                stderr="",
                returncode=0,
            ),
            AdbResult(stdout=f"Selected transport {cloud}\n", stderr="", returncode=0),
            AdbResult(stdout="Backup Manager now disabled\n", stderr="", returncode=0),
            AdbResult(
                stdout=f"    {local}\n  * {cloud}\n",
                stderr="",
                returncode=0,
            ),
            AdbResult(
                stdout="Backup Manager currently disabled\n",
                stderr="",
                returncode=0,
            ),
        ]
    )

    with pytest.raises(
        SystemEventInjectionError,
        match="backup postcondition failed.*success marker missing",
    ):
        injector.inject(
            SystemEventSpec(
                step_index=0,
                event="backup_restore",
                args={"transport": local, "restore_wait": "0"},
            )
        )

    assert fake.commands[-4:] == [
        ["-s", "emulator-5554", "shell", "bmgr", "transport", cloud],
        ["-s", "emulator-5554", "shell", "bmgr", "enable", "false"],
        ["-s", "emulator-5554", "shell", "bmgr", "list", "transports"],
        ["-s", "emulator-5554", "shell", "bmgr", "enabled"],
    ]


def test_inject_network_off_toggles_wifi_and_data() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="0\n", stderr="", returncode=0),
            AdbResult(stdout="0\n", stderr="", returncode=0),
        ]
    )

    injector.inject(SystemEventSpec(step_index=0, event="network_off"))

    assert fake.commands[-4:] == [
        ["-s", "emulator-5554", "shell", "svc", "wifi", "disable"],
        ["-s", "emulator-5554", "shell", "svc", "data", "disable"],
        ["-s", "emulator-5554", "shell", "settings", "get", "global", "wifi_on"],
        [
            "-s",
            "emulator-5554",
            "shell",
            "settings",
            "get",
            "global",
            "mobile_data",
        ],
    ]


def test_inject_network_on_confirms_wifi_and_mobile_data_settings() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="1\n", stderr="", returncode=0),
            AdbResult(stdout="1\n", stderr="", returncode=0),
        ]
    )

    injector.inject(SystemEventSpec(step_index=0, event="network_on"))

    assert fake.commands[-4:] == [
        ["-s", "emulator-5554", "shell", "svc", "wifi", "enable"],
        ["-s", "emulator-5554", "shell", "svc", "data", "enable"],
        ["-s", "emulator-5554", "shell", "settings", "get", "global", "wifi_on"],
        [
            "-s",
            "emulator-5554",
            "shell",
            "settings",
            "get",
            "global",
            "mobile_data",
        ],
    ]


def test_inject_network_off_fails_closed_when_wifi_remains_enabled() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="1\n", stderr="", returncode=0),
        ]
    )

    with pytest.raises(
        SystemEventInjectionError,
        match="network_off postcondition failed.*expected wifi_on=0.*observed '1'",
    ):
        injector.inject(SystemEventSpec(step_index=0, event="network_off"))


def test_inject_network_on_fails_closed_when_mobile_data_remains_disabled() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="1\n", stderr="", returncode=0),
            AdbResult(stdout="0\n", stderr="", returncode=0),
        ]
    )

    with pytest.raises(
        SystemEventInjectionError,
        match=(
            "network_on postcondition failed.*expected mobile_data=1.*observed '0'"
        ),
    ):
        injector.inject(SystemEventSpec(step_index=0, event="network_on"))


def test_inject_revoke_permission_requires_permission_arg() -> None:
    injector, _fake = _injector()

    with pytest.raises(SystemEventInjectionError, match="permission"):
        injector.inject(SystemEventSpec(step_index=0, event="revoke_permission"))


def test_inject_revoke_permission_fails_closed_when_permission_remains_granted() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(
                stdout=(
                    "runtime permissions:\n"
                    "  android.permission.CAMERA: granted=true, flags=[ USER_SET]\n"
                ),
                stderr="",
                returncode=0,
            ),
        ]
    )

    with pytest.raises(
        SystemEventInjectionError,
        match=(
            "revoke_permission postcondition failed.*"
            "android.permission.CAMERA remains granted"
        ),
    ):
        injector.inject(
            SystemEventSpec(
                step_index=0,
                event="revoke_permission",
                args={"permission": "android.permission.CAMERA"},
            )
        )


def test_inject_revoke_permission_confirms_runtime_grant_is_denied() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(
                stdout=(
                    "runtime permissions:\n"
                    "  android.permission.CAMERA: granted=false, flags=[ USER_SET]\n"
                ),
                stderr="",
                returncode=0,
            ),
        ]
    )

    injector.inject(
        SystemEventSpec(
            step_index=0,
            event="revoke_permission",
            args={"permission": "android.permission.CAMERA"},
        )
    )

    assert fake.commands[-2:] == [
        [
            "-s",
            "emulator-5554",
            "shell",
            "pm",
            "revoke",
            "org.example",
            "android.permission.CAMERA",
        ],
        [
            "-s",
            "emulator-5554",
            "shell",
            "dumpsys",
            "package",
            "org.example",
        ],
    ]


def test_inject_revoke_permission_fails_closed_when_state_is_unobservable() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="runtime permissions:\n", stderr="", returncode=0),
        ]
    )

    with pytest.raises(
        SystemEventInjectionError,
        match=(
            "revoke_permission postcondition failed.*could not find runtime permission "
            "android.permission.CAMERA"
        ),
    ):
        injector.inject(
            SystemEventSpec(
                step_index=0,
                event="revoke_permission",
                args={"permission": "android.permission.CAMERA"},
            )
        )


def test_inject_kill_background_uses_package() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="4242\n", stderr="", returncode=0),
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="", stderr="", returncode=1),
        ]
    )

    injector.inject(SystemEventSpec(step_index=0, event="kill_background"))

    assert fake.commands[-3:] == [
        ["-s", "emulator-5554", "shell", "pidof", "org.example"],
        [
            "-s",
            "emulator-5554",
            "shell",
            "am",
            "kill",
            "org.example",
        ],
        ["-s", "emulator-5554", "shell", "pidof", "org.example"],
    ]


def test_inject_kill_background_fails_closed_on_nonzero_process_exit() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="4242\n", stderr="", returncode=0),
            AdbResult(stdout="", stderr="device offline", returncode=1),
        ]
    )

    with pytest.raises(
        SystemEventInjectionError,
        match="kill_background.*return code 1.*device offline",
    ):
        injector.inject(SystemEventSpec(step_index=0, event="kill_background"))


def test_inject_kill_background_fails_closed_when_process_survives() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="4242\n", stderr="", returncode=0),
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="4242\n", stderr="", returncode=0),
        ]
    )

    with pytest.raises(
        SystemEventInjectionError,
        match="kill_background postcondition failed.*process remains running.*4242",
    ):
        injector.inject(SystemEventSpec(step_index=0, event="kill_background"))


def test_inject_app_to_background_waits_until_another_package_is_resumed() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(
                stdout=(
                    "topResumedActivity=ActivityRecord{123 u0 "
                    "com.android.launcher3/.QuickstepLauncher t4}\n"
                ),
                stderr="",
                returncode=0,
            ),
        ]
    )

    injector.inject(SystemEventSpec(step_index=0, event="app_to_background"))

    assert fake.commands[-2:] == [
        ["-s", "emulator-5554", "shell", "input", "keyevent", "HOME"],
        [
            "-s",
            "emulator-5554",
            "shell",
            "dumpsys",
            "activity",
            "activities",
        ],
    ]


def test_inject_app_to_background_polls_through_transient_resumed_state() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(
                stdout=(
                    "topResumedActivity=ActivityRecord{123 u0 "
                    "org.example/.MainActivity t9}\n"
                ),
                stderr="",
                returncode=0,
            ),
            AdbResult(
                stdout=(
                    "topResumedActivity=ActivityRecord{456 u0 "
                    "com.android.launcher3/.QuickstepLauncher t4}\n"
                ),
                stderr="",
                returncode=0,
            ),
        ]
    )

    injector.inject(
        SystemEventSpec(
            step_index=0,
            event="app_to_background",
            args={
                "postcondition_timeout_seconds": "0.05",
                "postcondition_poll_interval_seconds": "0.001",
            },
        )
    )

    assert sum("dumpsys" in command for command in fake.commands) == 2


def test_inject_app_to_foreground_uses_explicit_activity_and_confirms_resumed() -> None:
    fake = FakeAdbRunner()
    device = DeviceController(serial="emulator-5554", runner=fake)
    injector = DeviceSystemEventInjector(
        device=device,
        package="org.example",
        activity="org.example.DefaultIcon",
    )
    fake.enqueue_many(
        [
            AdbResult(stdout="Starting: Intent", stderr="", returncode=0),
            AdbResult(
                stdout=(
                    "  ResumedActivity: ActivityRecord{456 u0 "
                    "org.example/org.example.DefaultIcon t9}\n"
                ),
                stderr="",
                returncode=0,
            ),
        ]
    )

    injector.inject(SystemEventSpec(step_index=0, event="app_to_foreground"))

    assert fake.commands[-2:] == [
        [
            "-s",
            "emulator-5554",
            "shell",
            "am",
            "start",
            "-n",
            "org.example/org.example.DefaultIcon",
        ],
        [
            "-s",
            "emulator-5554",
            "shell",
            "dumpsys",
            "activity",
            "activities",
        ],
    ]


def test_app_to_foreground_prefers_api35_top_resumed_activity() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="Events injected: 1", stderr="", returncode=0),
            AdbResult(
                stdout=(
                    "mResumedActivity: ActivityRecord{123 u0 "
                    "com.android.launcher3/.QuickstepLauncher t4}\n"
                    "topResumedActivity=ActivityRecord{456 u0 "
                    "org.example/.MainActivity t9}\n"
                ),
                stderr="",
                returncode=0,
            ),
        ]
    )

    injector.inject(
        SystemEventSpec(
            step_index=0,
            event="app_to_foreground",
            args={"postcondition_timeout_seconds": "0"},
        )
    )


def test_inject_app_to_foreground_polls_through_transient_resumed_state() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="Events injected: 1", stderr="", returncode=0),
            AdbResult(
                stdout=(
                    "topResumedActivity=ActivityRecord{123 u0 "
                    "com.android.launcher3/.QuickstepLauncher t4}\n"
                ),
                stderr="",
                returncode=0,
            ),
            AdbResult(
                stdout=(
                    "topResumedActivity=ActivityRecord{456 u0 "
                    "org.example/.MainActivity t9}\n"
                ),
                stderr="",
                returncode=0,
            ),
        ]
    )

    injector.inject(
        SystemEventSpec(
            step_index=0,
            event="app_to_foreground",
            args={
                "postcondition_timeout_seconds": "0.05",
                "postcondition_poll_interval_seconds": "0.001",
            },
        )
    )

    assert [command[3:6] for command in fake.commands[-2:]] == [
        ["dumpsys", "activity", "activities"],
        ["dumpsys", "activity", "activities"],
    ]


def test_app_to_foreground_polls_through_transient_unobservable_state() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="Events injected: 1", stderr="", returncode=0),
            AdbResult(
                stdout="ACTIVITY MANAGER ACTIVITIES (dumpsys activity activities)\n",
                stderr="",
                returncode=0,
            ),
            AdbResult(
                stdout=(
                    "topResumedActivity=ActivityRecord{456 u0 "
                    "org.example/.MainActivity t9}\n"
                ),
                stderr="",
                returncode=0,
            ),
        ]
    )

    injector.inject(
        SystemEventSpec(
            step_index=0,
            event="app_to_foreground",
            args={
                "postcondition_timeout_seconds": "0.05",
                "postcondition_poll_interval_seconds": "0.001",
            },
        )
    )

    assert sum("dumpsys" in command for command in fake.commands) == 2


@pytest.mark.parametrize("event", ["app_to_background", "app_to_foreground"])
def test_app_lifecycle_events_fail_closed_when_resumed_activity_query_fails(
    event: str,
) -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="", stderr="activity service unavailable", returncode=9),
        ]
    )

    with pytest.raises(
        SystemEventInjectionError,
        match=rf"{event}.*return code 9.*activity service unavailable",
    ):
        injector.inject(
            SystemEventSpec(
                step_index=0,
                event=event,
                args={"postcondition_timeout_seconds": "0"},
            )
        )

    assert fake.commands[-1][3:6] == ["dumpsys", "activity", "activities"]


def test_app_to_background_fails_closed_when_resumed_activity_stays_unobservable() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(
                stdout="ACTIVITY MANAGER ACTIVITIES (dumpsys activity activities)\n",
                stderr="",
                returncode=0,
            ),
        ]
    )

    with pytest.raises(
        SystemEventInjectionError,
        match=(
            "app_to_background postcondition timed out: "
            "resumed activity remained unobservable"
        ),
    ):
        injector.inject(
            SystemEventSpec(
                step_index=0,
                event="app_to_background",
                args={"postcondition_timeout_seconds": "0"},
            )
        )


@pytest.mark.parametrize(
    ("event", "resumed_package", "expected_message"),
    [
        (
            "app_to_background",
            "org.example",
            "expected a resumed package other than org.example, observed org.example",
        ),
        (
            "app_to_foreground",
            "com.android.launcher3",
            "expected resumed package org.example, observed com.android.launcher3",
        ),
    ],
)
def test_app_lifecycle_events_fail_closed_on_postcondition_timeout(
    event: str,
    resumed_package: str,
    expected_message: str,
) -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(
                stdout=(
                    "topResumedActivity=ActivityRecord{123 u0 "
                    f"{resumed_package}/.MainActivity t4}}\n"
                ),
                stderr="",
                returncode=0,
            ),
        ]
    )

    with pytest.raises(
        SystemEventInjectionError,
        match=rf"{event} postcondition timed out: {expected_message}",
    ):
        injector.inject(
            SystemEventSpec(
                step_index=0,
                event=event,
                args={"postcondition_timeout_seconds": "0"},
            )
        )


@pytest.mark.parametrize(
    ("event", "args"),
    [
        ("app_to_background", {"postcondition_timeout_seconds": "forever"}),
        ("app_to_background", {"postcondition_timeout_seconds": "-1"}),
        (
            "app_to_foreground",
            {"postcondition_poll_interval_seconds": "0"},
        ),
        (
            "app_to_foreground",
            {"postcondition_poll_interval_seconds": "inf"},
        ),
    ],
)
def test_app_lifecycle_events_reject_invalid_polling_args_before_dispatch(
    event: str,
    args: dict[str, str],
) -> None:
    injector, fake = _injector()

    with pytest.raises(
        SystemEventInjectionError,
        match=(
            rf"{event} requires finite non-negative "
            "postcondition_timeout_seconds and positive "
            "postcondition_poll_interval_seconds"
        ),
    ):
        injector.inject(SystemEventSpec(step_index=0, event=event, args=args))

    assert fake.commands == []


def test_inject_dark_mode_defaults_to_night_on() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="Night mode: yes\n", stderr="", returncode=0),
        ]
    )

    injector.inject(SystemEventSpec(step_index=0, event="dark_mode"))

    assert fake.commands[-2:] == [
        ["-s", "emulator-5554", "shell", "cmd", "uimode", "night", "yes"],
        ["-s", "emulator-5554", "shell", "cmd", "uimode", "night"],
    ]


def test_inject_dark_mode_night_off_via_args() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="Night mode: no\n", stderr="", returncode=0),
        ]
    )

    injector.inject(SystemEventSpec(step_index=0, event="dark_mode", args={"night": "no"}))

    assert fake.commands[-2:] == [
        ["-s", "emulator-5554", "shell", "cmd", "uimode", "night", "no"],
        ["-s", "emulator-5554", "shell", "cmd", "uimode", "night"],
    ]


def test_inject_dark_mode_fails_closed_when_postcondition_does_not_match() -> None:
    injector, fake = _injector()
    fake.enqueue_many(
        [
            AdbResult(stdout="", stderr="", returncode=0),
            AdbResult(stdout="Night mode: no\n", stderr="", returncode=0),
        ]
    )

    with pytest.raises(
        SystemEventInjectionError,
        match="dark_mode postcondition failed.*expected night=yes.*Night mode: no",
    ):
        injector.inject(SystemEventSpec(step_index=0, event="dark_mode"))


def test_inject_dark_mode_rejects_unknown_night_value_before_dispatch() -> None:
    injector, fake = _injector()

    with pytest.raises(
        SystemEventInjectionError,
        match="dark_mode requires args.night to be 'yes' or 'no'; got 'maybe'",
    ):
        injector.inject(
            SystemEventSpec(
                step_index=0,
                event="dark_mode",
                args={"night": "maybe"},
            )
        )

    assert fake.commands == []


@pytest.mark.parametrize(
    ("event", "args"),
    [
        ("revoke_permission", {"permission": "android.permission.CAMERA"}),
        ("app_to_background", {}),
        ("app_to_foreground", {}),
        ("dark_mode", {"night": "yes"}),
    ],
)
def test_single_command_events_fail_closed_on_nonzero_process_exit(
    event: str, args: dict[str, str]
) -> None:
    injector, fake = _injector()
    fake.enqueue(AdbResult(stdout="", stderr="transport failure", returncode=17))

    with pytest.raises(
        SystemEventInjectionError,
        match=rf"{event}.*return code 17.*transport failure",
    ):
        injector.inject(SystemEventSpec(step_index=0, event=event, args=args))


@pytest.mark.parametrize("event", ["network_off", "network_on"])
def test_network_events_stop_after_the_first_nonzero_process_exit(event: str) -> None:
    injector, fake = _injector()
    fake.enqueue(AdbResult(stdout="", stderr="svc unavailable", returncode=9))

    with pytest.raises(
        SystemEventInjectionError,
        match=rf"{event}.*return code 9.*svc unavailable",
    ):
        injector.inject(SystemEventSpec(step_index=0, event=event))

    assert len(fake.commands) == 1
