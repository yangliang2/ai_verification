"""DeviceController 单测：验证所有 adb 命令序列通过 FakeAdbRunner 正确生成。"""


from aiverify.harness.device import (
    AdbResult,
    DeviceController,
    FakeAdbRunner,
)


def _ok() -> AdbResult:
    """返回一个成功的空结果。"""
    return AdbResult(stdout="", stderr="", returncode=0)


def _ctrl(serial: str | None = None) -> tuple[DeviceController, FakeAdbRunner]:
    """创建带 FakeAdbRunner 的 DeviceController。"""
    fake = FakeAdbRunner()
    ctrl = DeviceController(serial=serial, runner=fake)
    return ctrl, fake


# ---------------------------------------------------------------------------
# 应用生命周期
# ---------------------------------------------------------------------------

class TestInstallUninstall:
    def test_install_default_replace(self):
        ctrl, fake = _ctrl()
        ctrl.install("/tmp/app.apk")
        assert fake.commands[-1] == ["install", "-r", "/tmp/app.apk"]

    def test_install_no_replace(self):
        ctrl, fake = _ctrl()
        ctrl.install("/tmp/app.apk", replace=False)
        assert fake.commands[-1] == ["install", "/tmp/app.apk"]

    def test_uninstall(self):
        ctrl, fake = _ctrl()
        ctrl.uninstall("com.example.app")
        assert fake.commands[-1] == ["uninstall", "com.example.app"]

    def test_uninstall_keep_data(self):
        ctrl, fake = _ctrl()
        ctrl.uninstall("com.example.app", keep_data=True)
        assert fake.commands[-1] == ["uninstall", "-k", "com.example.app"]

    def test_install_with_serial(self):
        ctrl, fake = _ctrl(serial="emulator-5554")
        ctrl.install("/tmp/app.apk")
        assert fake.commands[-1] == ["-s", "emulator-5554", "install", "-r", "/tmp/app.apk"]


class TestLaunch:
    def test_launch_with_activity(self):
        ctrl, fake = _ctrl()
        ctrl.launch("com.example.app", activity="com.example.app/.MainActivity")
        assert fake.commands[-1] == [
            "shell", "am", "start", "-n",
            "com.example.app/com.example.app/.MainActivity",
        ]

    def test_launch_without_activity_uses_monkey(self):
        ctrl, fake = _ctrl()
        ctrl.launch("com.example.app")
        assert fake.commands[-1] == [
            "shell", "monkey", "-p", "com.example.app",
            "-c", "android.intent.category.LAUNCHER", "1",
        ]

    def test_launch_with_serial(self):
        ctrl, fake = _ctrl(serial="emulator-5554")
        ctrl.launch("com.example.app")
        cmd = fake.commands[-1]
        assert cmd[0] == "-s"
        assert cmd[1] == "emulator-5554"
        assert "monkey" in cmd


class TestProcessDeath:
    def test_process_death_home_kill_relaunch_sequence(self):
        ctrl, fake = _ctrl()
        ctrl.process_death(
            "com.example.app", background_wait=0, kill_wait=0, restore_wait=0
        )
        assert fake.commands[-3:] == [
            ["shell", "input", "keyevent", "HOME"],
            ["shell", "am", "kill", "com.example.app"],
            [
                "shell", "monkey", "-p", "com.example.app",
                "-c", "android.intent.category.LAUNCHER", "1",
            ],
        ]

    def test_process_death_with_launcher_activity_uses_explicit_launcher_intent(self):
        ctrl, fake = _ctrl()
        ctrl.process_death(
            "com.example.app",
            "com.example.Launcher",
            background_wait=0, kill_wait=0, restore_wait=0,
        )
        assert fake.commands[-1] == [
            "shell", "am", "start",
            "-a", "android.intent.action.MAIN",
            "-c", "android.intent.category.LAUNCHER",
            "-n", "com.example.app/com.example.Launcher",
        ]

    def test_process_death_with_serial(self):
        ctrl, fake = _ctrl(serial="emulator-5554")
        ctrl.process_death(
            "com.example.app", background_wait=0, kill_wait=0, restore_wait=0
        )
        assert all(cmd[:2] == ["-s", "emulator-5554"] for cmd in fake.commands[-3:])


class TestForceStopAndKill:
    def test_force_stop(self):
        ctrl, fake = _ctrl()
        ctrl.force_stop("com.example.app")
        assert fake.commands[-1] == ["shell", "am", "force-stop", "com.example.app"]

    def test_kill_background(self):
        ctrl, fake = _ctrl()
        ctrl.kill_background("com.example.app")
        assert fake.commands[-1] == ["shell", "am", "kill", "com.example.app"]

    def test_force_stop_and_kill_differ(self):
        """force-stop 与 kill 产生不同的 adb 命令。"""
        ctrl, fake = _ctrl()
        ctrl.force_stop("com.example.app")
        ctrl.kill_background("com.example.app")
        assert fake.commands[-2] == ["shell", "am", "force-stop", "com.example.app"]
        assert fake.commands[-1] == ["shell", "am", "kill", "com.example.app"]

    def test_clear_data(self):
        ctrl, fake = _ctrl()
        ctrl.clear_data("com.example.app")
        assert fake.commands[-1] == ["shell", "pm", "clear", "com.example.app"]

    def test_press_home(self):
        ctrl, fake = _ctrl()
        ctrl.press_home()
        assert fake.commands[-1] == ["shell", "input", "keyevent", "HOME"]


# ---------------------------------------------------------------------------
# 权限管理
# ---------------------------------------------------------------------------

class TestPermissions:
    def test_grant_permission(self):
        ctrl, fake = _ctrl()
        ctrl.grant_permission("com.example.app", "android.permission.CAMERA")
        assert fake.commands[-1] == [
            "shell", "pm", "grant", "com.example.app", "android.permission.CAMERA",
        ]

    def test_revoke_permission(self):
        ctrl, fake = _ctrl()
        ctrl.revoke_permission("com.example.app", "android.permission.CAMERA")
        assert fake.commands[-1] == [
            "shell", "pm", "revoke", "com.example.app", "android.permission.CAMERA",
        ]

    def test_grant_and_revoke_differ(self):
        ctrl, fake = _ctrl()
        ctrl.grant_permission("com.example.app", "android.permission.LOCATION")
        ctrl.revoke_permission("com.example.app", "android.permission.LOCATION")
        assert "grant" in fake.commands[-2]
        assert "revoke" in fake.commands[-1]


# ---------------------------------------------------------------------------
# 系统设置
# ---------------------------------------------------------------------------

class TestRotate:
    def test_rotate_portrait(self):
        ctrl, fake = _ctrl()
        ctrl.rotate(0)
        assert len(fake.commands) == 2
        assert fake.commands[0] == [
            "shell", "settings", "put", "system", "accelerometer_rotation", "0",
        ]
        assert fake.commands[1] == [
            "shell", "settings", "put", "system", "user_rotation", "0",
        ]

    def test_rotate_landscape(self):
        ctrl, fake = _ctrl()
        ctrl.rotate(1)
        assert fake.commands[0][-1] == "0"   # accelerometer_rotation=0
        assert fake.commands[1][-1] == "1"   # user_rotation=1

    def test_rotate_180(self):
        ctrl, fake = _ctrl()
        ctrl.rotate(2)
        assert fake.commands[1][-1] == "2"

    def test_rotate_270(self):
        ctrl, fake = _ctrl()
        ctrl.rotate(3)
        assert fake.commands[1][-1] == "3"

    def test_rotate_disables_auto_rotation_first(self):
        """必须先禁用自动旋转，再设置方向。"""
        ctrl, fake = _ctrl()
        ctrl.rotate(1)
        assert "accelerometer_rotation" in fake.commands[0]
        assert "user_rotation" in fake.commands[1]


class TestNetwork:
    def test_wifi_enable(self):
        ctrl, fake = _ctrl()
        ctrl.set_wifi(enabled=True)
        assert fake.commands[-1] == ["shell", "svc", "wifi", "enable"]

    def test_wifi_disable(self):
        ctrl, fake = _ctrl()
        ctrl.set_wifi(enabled=False)
        assert fake.commands[-1] == ["shell", "svc", "wifi", "disable"]

    def test_mobile_data_enable(self):
        ctrl, fake = _ctrl()
        ctrl.set_mobile_data(enabled=True)
        assert fake.commands[-1] == ["shell", "svc", "data", "enable"]

    def test_mobile_data_disable(self):
        ctrl, fake = _ctrl()
        ctrl.set_mobile_data(enabled=False)
        assert fake.commands[-1] == ["shell", "svc", "data", "disable"]


class TestNightMode:
    def test_night_mode_on(self):
        ctrl, fake = _ctrl()
        ctrl.set_night_mode(enabled=True)
        assert fake.commands[-1] == ["shell", "cmd", "uimode", "night", "yes"]

    def test_night_mode_off(self):
        ctrl, fake = _ctrl()
        ctrl.set_night_mode(enabled=False)
        assert fake.commands[-1] == ["shell", "cmd", "uimode", "night", "no"]


# ---------------------------------------------------------------------------
# 截图
# ---------------------------------------------------------------------------

class TestScreenshot:
    def test_screenshot_screencap_then_pull(self):
        ctrl, fake = _ctrl()
        ctrl.screenshot("/tmp/screen.png")
        # 第一条命令：screencap
        assert fake.commands[0] == [
            "shell", "screencap", "-p", "/sdcard/_aiverify_screen.png",
        ]
        # 第二条命令：pull
        assert fake.commands[1] == [
            "pull", "/sdcard/_aiverify_screen.png", "/tmp/screen.png",
        ]

    def test_screenshot_with_serial(self):
        ctrl, fake = _ctrl(serial="device-001")
        ctrl.screenshot("/tmp/out.png")
        for cmd in fake.commands:
            assert cmd[0] == "-s"
            assert cmd[1] == "device-001"


# ---------------------------------------------------------------------------
# UI Dump
# ---------------------------------------------------------------------------

class TestDumpUi:
    def test_dump_ui_issues_uiautomator_then_pull(self, tmp_path):
        ctrl, fake = _ctrl()
        # 给 pull 返回一个假 XML 内容（通过 FakeAdbRunner 无法真正写文件，
        # 此处仅验证命令序列；文件读取在真实路径下会报错但命令序列已记录）
        fake.enqueue(_ok())  # uiautomator dump
        fake.enqueue(_ok())  # pull

        # 因为 FakeAdbRunner 不实际写文件，open() 会失败；捕获以验证命令顺序
        try:
            ctrl.dump_ui()
        except (FileNotFoundError, OSError):
            pass

        assert fake.commands[0] == [
            "shell", "uiautomator", "dump", "/sdcard/_aiverify_ui.xml",
        ]
        assert fake.commands[1] == [
            "pull", "/sdcard/_aiverify_ui.xml", fake.pulls[0][1],
        ]


# ---------------------------------------------------------------------------
# Logcat
# ---------------------------------------------------------------------------

class TestLogcat:
    def test_logcat_clear(self):
        ctrl, fake = _ctrl()
        ctrl.logcat_clear()
        assert fake.commands[-1] == ["logcat", "-c"]

    def test_logcat_dump(self):
        ctrl, fake = _ctrl()
        fake.enqueue(AdbResult(stdout="some log text\n", stderr="", returncode=0))
        result = ctrl.logcat_dump()
        assert result == "some log text\n"
        assert fake.commands[-1] == ["logcat", "-d"]

    def test_logcat_capture_no_tags(self):
        ctrl, fake = _ctrl()
        ctrl.logcat_capture()
        assert fake.commands[-1] == ["logcat", "-d"]

    def test_logcat_capture_with_tags(self):
        ctrl, fake = _ctrl()
        ctrl.logcat_capture(tags=["AndroidRuntime:E", "*:S"])
        assert fake.commands[-1] == ["logcat", "-d", "AndroidRuntime:E", "*:S"]

    def test_capture_and_analyze_returns_session(self):
        ctrl, fake = _ctrl()
        fake.enqueue(AdbResult(stdout="normal log line\n", stderr="", returncode=0))
        session = ctrl.capture_and_analyze()
        assert session.output == "normal log line\n"
        assert session.events == []

    def test_logcat_with_serial(self):
        ctrl, fake = _ctrl(serial="emulator-5554")
        ctrl.logcat_clear()
        assert fake.commands[-1] == ["-s", "emulator-5554", "logcat", "-c"]


# ---------------------------------------------------------------------------
# FakeAdbRunner 自身行为
# ---------------------------------------------------------------------------

class TestFakeAdbRunner:
    def test_records_commands_in_order(self):
        fake = FakeAdbRunner()
        fake.run(["shell", "am", "force-stop", "com.a"])
        fake.run(["install", "-r", "/tmp/a.apk"])
        assert fake.commands[0] == ["shell", "am", "force-stop", "com.a"]
        assert fake.commands[1] == ["install", "-r", "/tmp/a.apk"]

    def test_default_result_on_empty_queue(self):
        fake = FakeAdbRunner()
        result = fake.run(["shell", "ls"])
        assert result.returncode == 0
        assert result.stdout == ""

    def test_enqueue_fifo(self):
        fake = FakeAdbRunner()
        fake.enqueue(AdbResult(stdout="first", stderr="", returncode=0))
        fake.enqueue(AdbResult(stdout="second", stderr="", returncode=1))
        r1 = fake.run(["cmd1"])
        r2 = fake.run(["cmd2"])
        assert r1.stdout == "first"
        assert r2.stdout == "second"
        assert r2.returncode == 1

    def test_pull_records_remote_local(self):
        fake = FakeAdbRunner()
        fake.pull("/sdcard/file.xml", "/tmp/file.xml")
        assert fake.pulls[0] == ("/sdcard/file.xml", "/tmp/file.xml")

    def test_serial_prepended_to_all_commands(self):
        fake = FakeAdbRunner()
        fake.run(["shell", "ls"], serial="abc123")
        assert fake.commands[-1] == ["-s", "abc123", "shell", "ls"]

    def test_enqueue_many(self):
        fake = FakeAdbRunner()
        results = [AdbResult(stdout=str(i), stderr="", returncode=0) for i in range(3)]
        fake.enqueue_many(results)
        for i in range(3):
            assert fake.run(["x"]).stdout == str(i)
