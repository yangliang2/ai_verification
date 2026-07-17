"""ADB 运行器抽象：真实 subprocess 实现与测试用假实现。

设计选择：
- `AdbRunner` 是纯抽象接口，`DeviceController` 仅依赖此接口，从不直接调 subprocess。
- `SubprocessAdbRunner` 是生产实现，封装 `subprocess.run`。
- `FakeAdbRunner` 是测试专用实现，记录所有调用命令并返回预置输出，绝不接触真实设备。
"""

from __future__ import annotations

import abc
import subprocess
from collections import deque
from dataclasses import dataclass


@dataclass
class AdbResult:
    """一次 adb 命令的执行结果。"""

    stdout: str
    stderr: str
    returncode: int


class AdbRunner(abc.ABC):
    """ADB 命令执行器抽象接口。

    所有方法均接受 `args` 作为 adb 子命令参数列表（不含 `adb` 本身），
    以及可选的 `serial` 用于 `adb -s <serial>` 多设备定向。
    """

    @abc.abstractmethod
    def run(self, args: list[str], *, serial: str | None = None) -> AdbResult:
        """执行一条 adb 命令并返回结果。

        Args:
            args: adb 子命令及参数，例如 ``["shell", "am", "force-stop", "com.example"]``。
            serial: 设备序列号；非 None 时在命令前插入 ``-s <serial>``。

        Returns:
            AdbResult 包含 stdout、stderr 和返回码。
        """

    @abc.abstractmethod
    def pull(self, remote: str, local: str, *, serial: str | None = None) -> AdbResult:
        """从设备拉取文件到本地（等同 ``adb pull``）。

        Args:
            remote: 设备上的源路径。
            local: 本地目标路径。
            serial: 设备序列号。
        """


class SubprocessAdbRunner(AdbRunner):
    """生产级 ADB 运行器，通过 subprocess 调用系统中的 ``adb`` 可执行文件。"""

    def __init__(self, adb_path: str = "adb", *, timeout_seconds: float = 30.0) -> None:
        """初始化。

        Args:
            adb_path: adb 可执行文件路径，默认从 PATH 中查找。
            timeout_seconds: 每条 adb 命令的最长运行时间。
        """
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._adb_path = adb_path
        self._timeout_seconds = timeout_seconds

    def _build_cmd(self, args: list[str], serial: str | None) -> list[str]:
        cmd = [self._adb_path]
        if serial:
            cmd += ["-s", serial]
        cmd += args
        return cmd

    def run(self, args: list[str], *, serial: str | None = None) -> AdbResult:
        """执行 adb 命令，捕获 stdout/stderr，不抛出异常（由调用方检查 returncode）。"""
        cmd = self._build_cmd(args, serial)
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self._timeout_seconds,
        )
        return AdbResult(stdout=proc.stdout, stderr=proc.stderr, returncode=proc.returncode)

    def pull(self, remote: str, local: str, *, serial: str | None = None) -> AdbResult:
        """执行 ``adb [−s serial] pull <remote> <local>``。"""
        return self.run(["pull", remote, local], serial=serial)


class FakeAdbRunner(AdbRunner):
    """测试专用假实现：记录所有调用并按预置队列返回结果，绝不执行真实命令。

    用法示例::

        fake = FakeAdbRunner()
        fake.enqueue(AdbResult(stdout="", stderr="", returncode=0))
        ctrl = DeviceController(serial="emulator-5554", runner=fake)
        ctrl.force_stop("com.example")
        assert fake.commands[-1] == ["shell", "am", "force-stop", "com.example"]
    """

    def __init__(self) -> None:
        #: 按调用顺序记录的完整命令列表（含 -s 前缀，若有 serial）
        self.commands: list[list[str]] = []
        #: 按调用顺序记录的完整 pull 调用 (remote, local) 对
        self.pulls: list[tuple[str, str]] = []
        self._queue: deque[AdbResult] = deque()
        #: 默认响应：队列耗尽时返回此值（默认成功空输出）
        self.default_result: AdbResult = AdbResult(stdout="", stderr="", returncode=0)

    def enqueue(self, result: AdbResult) -> None:
        """向返回队列末尾追加一个预置结果。"""
        self._queue.append(result)

    def enqueue_many(self, results: list[AdbResult]) -> None:
        """批量追加预置结果。"""
        for r in results:
            self._queue.append(r)

    def _next_result(self) -> AdbResult:
        if self._queue:
            return self._queue.popleft()
        return self.default_result

    def run(self, args: list[str], *, serial: str | None = None) -> AdbResult:
        """记录命令（含 serial 前缀）并返回下一个预置结果。"""
        cmd: list[str] = []
        if serial:
            cmd += ["-s", serial]
        cmd += args
        self.commands.append(cmd)
        return self._next_result()

    def pull(self, remote: str, local: str, *, serial: str | None = None) -> AdbResult:
        """记录 pull 调用并返回下一个预置结果。"""
        self.pulls.append((remote, local))
        cmd: list[str] = []
        if serial:
            cmd += ["-s", serial]
        cmd += ["pull", remote, local]
        self.commands.append(cmd)
        return self._next_result()
