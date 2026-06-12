"""Logcat 捕获与分析：开始/停止/dump，以及 crash/ANR/未捕获异常提取。

LogcatAnalyzer 使用正则从 logcat 文本中提取结构化事件，不依赖设备连接，
可对任意 logcat 字符串内容进行离线分析——这是 harness 确定性编排的基础：
缺陷触发时机由 harness 控制，分析结果由此类离线提取，LLM 不参与时机判断。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class LogEventType(str, Enum):
    """Logcat 事件类型。"""

    CRASH = "crash"          # FATAL EXCEPTION（Java/Kotlin 未捕获异常）
    ANR = "anr"              # ANR in <process>
    UNCAUGHT = "uncaught"    # 通用未捕获异常（非 FATAL EXCEPTION 行但含 UNCAUGHT EXCEPTION）


@dataclass
class LogEvent:
    """从 logcat 中提取的单个结构化事件。"""

    type: LogEventType
    process: str
    stacktrace: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        lines = len(self.stacktrace)
        return f"<LogEvent type={self.type.value} process={self.process!r} stacktrace_lines={lines}>"


# ---------------------------------------------------------------------------
# 正则模式
# ---------------------------------------------------------------------------

# FATAL EXCEPTION 块起始行，如：
#   E AndroidRuntime: FATAL EXCEPTION: main
_RE_FATAL = re.compile(
    r"(?:E\s+AndroidRuntime|FATAL EXCEPTION)[:\s]+"
    r".*?FATAL EXCEPTION"
    r"|\bFATAL EXCEPTION\b",
    re.IGNORECASE,
)

# 进程名提取：紧跟 FATAL EXCEPTION 块后的 "Process: <name>" 行
_RE_PROCESS_LINE = re.compile(r"Process:\s*(\S+)")

# ANR 行，如：
#   I am_anr  : ANR in com.example.app (com.example.app/.MainActivity)
#   Subject: ANR in com.example
_RE_ANR = re.compile(r"\bANR\s+in\s+(\S+)", re.IGNORECASE)

# 通用 UNCAUGHT EXCEPTION（非 FATAL 路径，如 NDK/JNI 层）
_RE_UNCAUGHT = re.compile(r"\bUNCAUGHT EXCEPTION\b", re.IGNORECASE)

# 栈帧行（at xxx.yyy.zzz(File.java:N) 或 Caused by:）
_RE_STACK_FRAME = re.compile(
    r"^\s*(?:at\s+[\w\.$<>]+\(|Caused by:|java\.|android\.|kotlin\.)",
    re.MULTILINE,
)


class LogcatAnalyzer:
    """从 logcat 文本中提取 crash、ANR 及未捕获异常事件。

    设计原则：
    - 纯函数式，无状态，不依赖设备连接。
    - ``analyze`` 方法可对任意来源的 logcat 字符串调用（从文件读取、从 adb 捕获等）。
    - 返回 ``LogEvent`` 列表，每个事件包含 type、process 和 stacktrace 行列表。

    FATAL EXCEPTION 识别策略：
    扫描所有行，发现含 "FATAL EXCEPTION" 的行后，向后收集栈帧行（含 "at "、
    "Caused by:"、"Process:" 等前缀），直到遇到空行或非栈帧行为止，
    形成一个完整事件块。
    """

    def analyze(self, logcat_text: str) -> list[LogEvent]:
        """解析 logcat 文本，返回所有提取到的结构化事件列表。

        Args:
            logcat_text: 原始 logcat 字符串（可来自 ``adb logcat -d`` 或文件）。

        Returns:
            按出现顺序排列的 ``LogEvent`` 列表。
        """
        events: list[LogEvent] = []
        lines = logcat_text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]

            # ------------------------------------------------------------------
            # 检测 FATAL EXCEPTION 块
            # ------------------------------------------------------------------
            if "FATAL EXCEPTION" in line:
                process = ""
                stacktrace: list[str] = [line]
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    # 提取进程名
                    m_proc = _RE_PROCESS_LINE.search(next_line)
                    if m_proc and not process:
                        process = m_proc.group(1)
                    # 收集属于该块的行：含 at/Caused by/Process/PID/java. 等
                    if self._is_stack_line(next_line):
                        stacktrace.append(next_line)
                        j += 1
                    else:
                        break
                events.append(LogEvent(
                    type=LogEventType.CRASH,
                    process=process,
                    stacktrace=stacktrace,
                ))
                i = j
                continue

            # ------------------------------------------------------------------
            # 检测 ANR
            # ------------------------------------------------------------------
            m_anr = _RE_ANR.search(line)
            if m_anr:
                process = m_anr.group(1)
                # 去掉尾部括号内内容（如包名/Activity）
                process = re.split(r"[\s(]", process)[0]
                stacktrace = [line]
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    if self._is_stack_line(next_line) or next_line.strip().startswith("at "):
                        stacktrace.append(next_line)
                        j += 1
                    else:
                        break
                events.append(LogEvent(
                    type=LogEventType.ANR,
                    process=process,
                    stacktrace=stacktrace,
                ))
                i = j
                continue

            # ------------------------------------------------------------------
            # 检测通用 UNCAUGHT EXCEPTION（非 FATAL 路径）
            # ------------------------------------------------------------------
            if _RE_UNCAUGHT.search(line) and "FATAL EXCEPTION" not in line:
                process = ""
                m_proc = _RE_PROCESS_LINE.search(line)
                if m_proc:
                    process = m_proc.group(1)
                stacktrace = [line]
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    if self._is_stack_line(next_line):
                        stacktrace.append(next_line)
                        j += 1
                    else:
                        break
                events.append(LogEvent(
                    type=LogEventType.UNCAUGHT,
                    process=process,
                    stacktrace=stacktrace,
                ))
                i = j
                continue

            i += 1

        return events

    @staticmethod
    def _is_stack_line(line: str) -> bool:
        """判断一行是否属于异常块（栈帧、Process:、PID: 等）。

        真实 logcat 行格式为：
            ``MM-DD HH:MM:SS.mmm  PID  TID  LEVEL TAG: <content>``
        栈帧标记（"at "、"Caused by:" 等）出现在行内容部分，而非行首。
        因此使用 ``in`` 检测。

        注意：logcat 采集工具有时将制表符输出为字面量 ``\\t``（反斜杠+t）
        而非真实制表符，两种形式均需处理。
        """
        # 真实制表符前缀（adb logcat 直接输出）
        real_tab = "\tat " in line or "\tCaused by:" in line
        # 字面量 \t 前缀（部分采集工具或测试 fixture）
        literal_tab = "\\tat " in line or "\\tCaused by:" in line
        return bool(
            real_tab
            or literal_tab
            or "Caused by:" in line
            or "Process:" in line
            or "PID:" in line
            or "at com." in line
            or "at java." in line
            or "at android." in line
            or "at kotlin." in line
            or "at org." in line
            or "java.lang." in line
            or "java.io." in line
            or "..." in line
        )
