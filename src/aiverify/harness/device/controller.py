"""DeviceController：封装所有 ADB 操作的设备编排层。

设计原则：
- 所有 ADB 调用均通过注入的 ``AdbRunner`` 接口执行，不直接调用 subprocess。
- 支持多设备场景：通过构造函数的 ``serial`` 参数指定目标设备（adb -s）。
- 系统事件原语均为确定性操作，由 harness 控制时机，不依赖 LLM 判断。

屏幕旋转方案选择：
使用 ``settings put system`` 方案（accelerometer_rotation + user_rotation），
而非 ``wm rotation``。原因：``wm rotation`` 在部分 Android 版本（API<28）不可用，
且 wm 方案在某些厂商 ROM 上行为不一致；``settings put system`` 方案
自 Android 4.0 起稳定支持，兼容性更好，适合跨版本验证场景。

kill_background vs force_stop 语义区分：
- ``kill_background``：``am kill <pkg>``，仅终止后台进程，前台进程不受影响。
  适用于模拟系统内存回收触发的后台恢复缺陷。
- ``force_stop``：``am force-stop <pkg>``，强制终止所有进程（含前台），清除活动记录。
  适用于彻底复位应用状态、触发冷启动路径缺陷。
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field

from .adb import AdbResult, AdbRunner, SubprocessAdbRunner
from .logcat import LogcatAnalyzer, LogEvent


@dataclass
class LogcatSession:
    """一次 logcat 捕获会话的状态记录（当前实现为同步 dump 模式）。"""

    output: str = ""
    events: list[LogEvent] = field(default_factory=list)


class DeviceController:
    """ADB 设备编排层：封装安装、启动、系统事件、日志捕获等全套操作。

    Args:
        serial: 目标设备序列号（adb -s）；None 表示使用默认唯一连接设备。
        runner: ADB 命令执行器；默认使用 ``SubprocessAdbRunner``。
    """

    def __init__(
        self,
        serial: str | None = None,
        runner: AdbRunner | None = None,
    ) -> None:
        self._serial = serial
        self._runner: AdbRunner = runner if runner is not None else SubprocessAdbRunner()
        self._logcat_analyzer = LogcatAnalyzer()

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _run(self, args: list[str]) -> AdbResult:
        """以当前 serial 执行 adb 命令。"""
        return self._runner.run(args, serial=self._serial)

    def _pull(self, remote: str, local: str) -> AdbResult:
        """以当前 serial 执行 adb pull。"""
        return self._runner.pull(remote, local, serial=self._serial)

    def _shell(self, cmd: list[str]) -> AdbResult:
        """执行 ``adb shell <cmd>``。"""
        return self._run(["shell"] + cmd)

    # ------------------------------------------------------------------
    # 应用生命周期
    # ------------------------------------------------------------------

    def install(self, apk_path: str, *, replace: bool = True) -> AdbResult:
        """安装 APK 到设备。

        Args:
            apk_path: 本地 APK 文件路径。
            replace: True 时使用 ``-r`` 覆盖安装已有版本（保留数据）。

        Returns:
            AdbResult。
        """
        args = ["install"]
        if replace:
            args.append("-r")
        args.append(apk_path)
        return self._run(args)

    def uninstall(self, package: str, *, keep_data: bool = False) -> AdbResult:
        """卸载应用。

        Args:
            package: 应用包名。
            keep_data: True 时使用 ``-k`` 保留数据目录（沙箱数据）。

        Returns:
            AdbResult。
        """
        args = ["uninstall"]
        if keep_data:
            args.append("-k")
        args.append(package)
        return self._run(args)

    def launch(self, package: str, activity: str | None = None) -> AdbResult:
        """启动应用。

        Args:
            package: 应用包名。
            activity: 完整 Activity 类名（含包名前缀）；None 时使用
                ``monkey -p <pkg> -c android.intent.category.LAUNCHER 1`` 启动。

        Returns:
            AdbResult。
        """
        if activity:
            return self._shell([
                "am", "start", "-n", f"{package}/{activity}",
            ])
        return self._shell([
            "monkey", "-p", package,
            "-c", "android.intent.category.LAUNCHER", "1",
        ])

    def force_stop(self, package: str) -> AdbResult:
        """强制终止应用所有进程（含前台），清除活动记录。

        语义：彻底复位应用状态，适用于触发冷启动路径缺陷。
        对应 adb shell am force-stop <package>。

        Args:
            package: 应用包名。

        Returns:
            AdbResult。
        """
        return self._shell(["am", "force-stop", package])

    def kill_background(self, package: str) -> AdbResult:
        """仅终止后台进程，不影响前台进程。

        语义：模拟系统内存回收，适用于触发后台恢复相关缺陷（onRestart/onResume 路径）。
        对应 adb shell am kill <package>。

        Args:
            package: 应用包名。

        Returns:
            AdbResult。
        """
        return self._shell(["am", "kill", package])

    def clear_data(self, package: str) -> AdbResult:
        """清除应用数据（等同用户在设置中"清除数据"）。

        Args:
            package: 应用包名。

        Returns:
            AdbResult。
        """
        return self._shell(["pm", "clear", package])

    def press_home(self) -> AdbResult:
        """按下 Home 键，将当前前台应用送入后台。"""
        return self._shell(["input", "keyevent", "HOME"])

    # ------------------------------------------------------------------
    # 权限管理
    # ------------------------------------------------------------------

    def grant_permission(self, package: str, permission: str) -> AdbResult:
        """授予应用运行时权限。

        Args:
            package: 应用包名。
            permission: 完整权限名，如 ``android.permission.CAMERA``。

        Returns:
            AdbResult。
        """
        return self._shell(["pm", "grant", package, permission])

    def revoke_permission(self, package: str, permission: str) -> AdbResult:
        """撤销应用运行时权限。

        Args:
            package: 应用包名。
            permission: 完整权限名，如 ``android.permission.CAMERA``。

        Returns:
            AdbResult。
        """
        return self._shell(["pm", "revoke", package, permission])

    # ------------------------------------------------------------------
    # 系统设置
    # ------------------------------------------------------------------

    def rotate(self, rotation: int) -> tuple[AdbResult, AdbResult]:
        """设置屏幕旋转方向（禁用自动旋转并强制指定方向）。

        方案选择：使用 ``settings put system`` 方案，兼容 Android 4.0+，
        在厂商 ROM 上比 ``wm rotation`` 更稳定（详见模块文档）。

        Args:
            rotation: 旋转值，0=竖屏、1=横屏(90°)、2=反转竖屏(180°)、3=反转横屏(270°)。

        Returns:
            两次 adb 调用的结果元组：(禁用自动旋转结果, 设置旋转角度结果)。
        """
        r1 = self._shell(["settings", "put", "system", "accelerometer_rotation", "0"])
        r2 = self._shell(["settings", "put", "system", "user_rotation", str(rotation)])
        return r1, r2

    def set_wifi(self, *, enabled: bool) -> AdbResult:
        """开启或关闭 Wi-Fi。

        Args:
            enabled: True 开启，False 关闭。

        Returns:
            AdbResult。
        """
        state = "enable" if enabled else "disable"
        return self._shell(["svc", "wifi", state])

    def set_mobile_data(self, *, enabled: bool) -> AdbResult:
        """开启或关闭移动数据。

        Args:
            enabled: True 开启，False 关闭。

        Returns:
            AdbResult。
        """
        state = "enable" if enabled else "disable"
        return self._shell(["svc", "data", state])

    def set_night_mode(self, *, enabled: bool) -> AdbResult:
        """开启或关闭系统深色模式（uiMode night 配置变更）。

        深色模式属于 taxonomy config-change 类的配置变更之一。当被测 Activity 的
        ``android:configChanges`` 未声明 ``uiMode`` 时，切换深色模式会强制 Activity
        重建，从而真正走 save/restore 路径——这是在"声明了 orientation|screenSize
        因而旋转不重建"的 Activity 上仍能验证配置变更状态保留的关键手段。

        对应 adb shell cmd uimode night yes|no。

        Args:
            enabled: True 开启深色模式，False 关闭。

        Returns:
            AdbResult。
        """
        state = "yes" if enabled else "no"
        return self._shell(["cmd", "uimode", "night", state])

    # ------------------------------------------------------------------
    # 截图
    # ------------------------------------------------------------------

    def screenshot(self, local_path: str) -> AdbResult:
        """截取当前屏幕并保存到本地路径。

        流程：在设备上执行 ``screencap -p``，将输出通过 pull 拉取到本地。
        实际使用 ``screencap -p /sdcard/_aiverify_screen.png`` 后 pull。

        Args:
            local_path: 截图保存的本地文件路径。

        Returns:
            pull 操作的 AdbResult。
        """
        remote_path = "/sdcard/_aiverify_screen.png"
        self._shell(["screencap", "-p", remote_path])
        return self._pull(remote_path, local_path)

    # ------------------------------------------------------------------
    # Accessibility Tree Dump
    # ------------------------------------------------------------------

    def dump_ui(self) -> str:
        """转储当前界面的 Accessibility Tree（UI 层级 XML）。

        流程：执行 ``uiautomator dump /sdcard/_aiverify_ui.xml``，
        然后 pull 到本地临时文件并读取内容，返回 XML 字符串。

        Returns:
            uiautomator dump 输出的 XML 字符串内容。
        """
        remote_path = "/sdcard/_aiverify_ui.xml"
        self._shell(["uiautomator", "dump", remote_path])

        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            self._pull(remote_path, tmp_path)
            with open(tmp_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Logcat
    # ------------------------------------------------------------------

    def logcat_clear(self) -> AdbResult:
        """清空设备 logcat 缓冲区（下次捕获时从此刻起）。

        Returns:
            AdbResult。
        """
        return self._run(["logcat", "-c"])

    def logcat_dump(self) -> str:
        """一次性 dump 当前 logcat 缓冲区内容，返回原始字符串。

        Returns:
            logcat 原始文本。
        """
        result = self._run(["logcat", "-d"])
        return result.stdout

    def logcat_capture(
        self,
        *,
        tags: list[str] | None = None,
        size: str = "1M",
    ) -> str:
        """捕获 logcat 输出（同步 dump 模式）。

        Args:
            tags: 标签过滤列表，如 ``["AndroidRuntime:E", "*:S"]``；None 不过滤。
            size: 缓冲区大小提示（当前实现中不影响 -d 行为，保留参数供扩展）。

        Returns:
            logcat 原始文本。
        """
        args = ["logcat", "-d"]
        if tags:
            args += tags
        result = self._run(args)
        return result.stdout

    def analyze_logcat(self, logcat_text: str) -> list[LogEvent]:
        """对 logcat 文本进行结构化分析，提取 crash/ANR/未捕获异常事件。

        Args:
            logcat_text: 原始 logcat 字符串。

        Returns:
            ``LogEvent`` 列表，按出现顺序排列。
        """
        return self._logcat_analyzer.analyze(logcat_text)

    def capture_and_analyze(self) -> LogcatSession:
        """捕获当前 logcat 缓冲区并立即分析，返回完整会话结果。

        Returns:
            ``LogcatSession`` 包含原始 logcat 文本和提取的事件列表。
        """
        text = self.logcat_dump()
        events = self.analyze_logcat(text)
        return LogcatSession(output=text, events=events)
