"""L1 廉价信号判定器——基于 logcat 文本的 crash/ANR 检测。

设计原则
--------
L1 只有"报警"权，没有"宣告通过"权。
- 检测到崩溃/ANR 信号 → outcome=fail
- 无信号 → outcome=inconclusive（弃权，交由 L2/L3 继续判定）

这是分层设计的核心约定：L1 以极低开销覆盖最明确的失败信号，
无信号时不误判为 pass，避免掩盖需要更深层分析的缺陷。
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from aiverify.agent.oracle.schema import validate_verdict

# ---------------------------------------------------------------------------
# 检测规则：(pattern, note)
# ---------------------------------------------------------------------------
_ANDROID_SECURITY_EXCEPTION_PATTERN = re.compile(
    r"AndroidRuntime.*(?:java\.lang\.)?SecurityException",
    re.IGNORECASE,
)

_CRASH_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        _ANDROID_SECURITY_EXCEPTION_PATTERN,
        "检测到 AndroidRuntime 未捕获 SecurityException——运行时权限状态未可靠处理",
    ),
    (
        re.compile(r"FATAL EXCEPTION", re.IGNORECASE),
        "检测到 FATAL EXCEPTION——JVM 未捕获异常导致进程崩溃",
    ),
    (
        re.compile(r"ANR in\b", re.IGNORECASE),
        "检测到 ANR in——应用无响应（主线程阻塞超时）",
    ),
    (
        re.compile(
            r"kotlinx\.coroutines\..*[Uu]nhandled|CoroutineExceptionHandler.*unhandled",
        ),
        "检测到 kotlinx.coroutines 未捕获异常——协程顶层异常逃逸",
    ),
    (
        re.compile(r"Process:.*has died", re.IGNORECASE),
        "检测到进程崩溃（has died）",
    ),
    (
        # 必须带 AndroidRuntime tag：未捕获崩溃总是由 AndroidRuntime 记录。
        # 否则会误报——其它进程的诊断日志（如 gRPC "ManagedChannel allocation
        # site"）或被捕获的 binder 异常也会提到 java.lang.RuntimeException。
        re.compile(r"AndroidRuntime.*java\.lang\.(RuntimeException|NullPointerException|OutOfMemoryError)"),
        "检测到 AndroidRuntime 未捕获致命异常",
    ),
]


class L1Oracle:
    """基于 logcat 文本的廉价信号判定器（L1 层）。

    仅负责检测明确的崩溃/ANR 信号。无信号时返回 outcome=inconclusive，
    不宣告 pass——L1 没有权力断言应用正常，只有权力报警或弃权。
    """

    def judge(
        self,
        logcat_text: str,
        *,
        trigger_steps: list[str] | None = None,
    ) -> dict[str, Any]:
        """对 logcat 文本执行 L1 判定。

        参数
        ----
        logcat_text:
            完整 logcat 输出字符串（adb logcat 格式，按行扫描）。
        trigger_steps:
            触发本次判定的操作步骤列表，可选，用于归因追溯。

        返回
        ----
        符合 verdict_schema.json 的 verdict dict。
        - 检测到崩溃/ANR → outcome="fail"，evidence 引用具体 logcat 行
        - 无信号 → outcome="inconclusive"，evidence 为空列表

        注意：本方法不会返回 outcome="pass"。
        """
        if trigger_steps is None:
            trigger_steps = []

        matched_evidence: list[dict[str, str]] = []

        for line in logcat_text.splitlines():
            for pattern, note in _CRASH_PATTERNS:
                if pattern.search(line):
                    matched_evidence.append(
                        {
                            "type": "logcat_line",
                            "ref": line.strip(),
                            "note": note,
                        }
                    )
                    break  # 同一行只匹配一条规则，避免重复证据

        if matched_evidence:
            outcome = "fail"
            defect_class = "crash_stability"
            confidence = 0.95
        else:
            outcome = "inconclusive"
            defect_class = None
            confidence = 0.0

        verdict: dict[str, Any] = {
            "verdict_id": f"L1-{uuid.uuid4().hex[:8]}",
            "level": "L1",
            "outcome": outcome,
            "defect_class_hypothesis": defect_class,
            "trigger_steps": trigger_steps,
            "evidence": matched_evidence,
            "confidence": confidence,
        }
        validate_verdict(verdict)
        return verdict
