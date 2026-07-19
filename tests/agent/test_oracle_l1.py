"""L1Oracle 单测——基于 logcat 文本的 crash/ANR 检测。

覆盖三个案例：
1. FATAL EXCEPTION（JVM 崩溃）
2. ANR in（应用无响应）
3. 无信号（应返回 inconclusive，不得返回 pass）
"""


from aiverify.agent.oracle import L1Oracle, validate_verdict

# ---------------------------------------------------------------------------
# Fixtures：真实格式 logcat 片段
# ---------------------------------------------------------------------------

LOGCAT_CRASH = """\
--------- beginning of crash
06-10 14:23:01.234  1234  1234 E AndroidRuntime: FATAL EXCEPTION: main
06-10 14:23:01.234  1234  1234 E AndroidRuntime: Process: com.example.app, PID: 1234
06-10 14:23:01.234  1234  1234 E AndroidRuntime: java.lang.NullPointerException: Attempt to invoke virtual method
06-10 14:23:01.235  1234  1234 E AndroidRuntime: \tat com.example.app.MainActivity.onCreate(MainActivity.kt:42)
06-10 14:23:01.235  1234  1234 E AndroidRuntime: \tat android.app.Activity.performCreate(Activity.java:8290)
"""

LOGCAT_ANR = """\
06-10 15:01:00.000  2000  2000 E ActivityManager: ANR in com.example.app (com.example.app/.MainActivity)
06-10 15:01:00.001  2000  2000 E ActivityManager: PID: 2000
06-10 15:01:00.002  2000  2000 E ActivityManager: Reason: Input dispatching timed out (com.example.app/...
06-10 15:01:00.003  2000  2000 E ActivityManager: Load: 3.5 / 3.2 / 2.8
06-10 15:01:00.004  2000  2000 I ActivityManager: Killing 2000:com.example.app/u0a123 (adj 0): user request after error
"""

LOGCAT_CLEAN = """\
06-10 16:00:00.000  3000  3000 I MainActivity: onCreate called
06-10 16:00:00.100  3000  3000 D ViewModel: data loaded, items=42
06-10 16:00:00.200  3000  3001 I RecyclerView: onCreateViewHolder position=0
06-10 16:00:00.500  3000  3000 I MainActivity: onResume
"""

LOGCAT_COROUTINE_EXCEPTION = """\
06-10 17:00:00.000  4000  4000 E AndroidRuntime: FATAL EXCEPTION: DefaultDispatcher-worker-1
06-10 17:00:00.001  4000  4000 E AndroidRuntime: kotlinx.coroutines.internal.UnhandledCoroutineExceptionKt
06-10 17:00:00.002  4000  4000 E AndroidRuntime: \tat kotlinx.coroutines.CoroutineExceptionHandler unhandled exception
"""

LOGCAT_PERMISSION_CRASH = """\
07-19 12:00:00.000 5000 5000 E AndroidRuntime: FATAL EXCEPTION: main
07-19 12:00:00.001 5000 5000 E AndroidRuntime: Process: org.wikipedia.dev, PID: 5000
07-19 12:00:00.002 5000 5000 E AndroidRuntime: java.lang.SecurityException: uid 10234 does not have android.permission.ACCESS_FINE_LOCATION
07-19 12:00:00.003 5000 5000 E AndroidRuntime: at android.location.LocationManager.getLastKnownLocation(LocationManager.java:999)
"""

# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------

oracle = L1Oracle()


def test_l1_detects_fatal_exception():
    """FATAL EXCEPTION 行应触发 fail 判定，evidence 引用崩溃行。"""
    verdict = oracle.judge(LOGCAT_CRASH, trigger_steps=["启动 MainActivity"])

    assert verdict["level"] == "L1"
    assert verdict["outcome"] == "fail"
    assert verdict["defect_class_hypothesis"] == "crash_stability"
    assert verdict["confidence"] > 0.5

    # evidence 中应包含 logcat_line 类型，且 ref 包含崩溃关键词
    assert verdict["evidence"], "fail 判定必须有证据"
    types = {e["type"] for e in verdict["evidence"]}
    assert "logcat_line" in types

    refs = " ".join(e["ref"] for e in verdict["evidence"])
    assert "FATAL EXCEPTION" in refs

    # 触发步骤被透传
    assert "启动 MainActivity" in verdict["trigger_steps"]

    # schema 自验
    validate_verdict(verdict)


def test_l1_detects_anr():
    """ANR in 行应触发 fail 判定，evidence 引用 ANR 行。"""
    verdict = oracle.judge(LOGCAT_ANR, trigger_steps=["长按按钮触发耗时操作"])

    assert verdict["level"] == "L1"
    assert verdict["outcome"] == "fail"
    assert verdict["defect_class_hypothesis"] == "crash_stability"

    refs = " ".join(e["ref"] for e in verdict["evidence"])
    assert "ANR in" in refs

    validate_verdict(verdict)


def test_l1_inconclusive_on_clean_logcat():
    """无崩溃信号时 L1 必须返回 inconclusive，不得返回 pass。"""
    verdict = oracle.judge(LOGCAT_CLEAN)

    assert verdict["level"] == "L1"
    assert verdict["outcome"] == "inconclusive", (
        "L1 无信号时必须返回 inconclusive，不得返回 pass——L1 没有权力宣告通过"
    )
    assert verdict["defect_class_hypothesis"] is None
    assert verdict["confidence"] == 0.0
    assert verdict["evidence"] == []

    validate_verdict(verdict)


def test_l1_outcome_never_pass():
    """L1 的所有输出均不应包含 outcome=pass。"""
    for logcat in [LOGCAT_CRASH, LOGCAT_ANR, LOGCAT_CLEAN, LOGCAT_COROUTINE_EXCEPTION]:
        verdict = oracle.judge(logcat)
        assert verdict["outcome"] != "pass", (
            f"L1 不应产出 pass，实际得到：{verdict['outcome']}"
        )


def test_l1_verdict_id_format():
    """verdict_id 应以 'L1-' 开头。"""
    verdict = oracle.judge(LOGCAT_CLEAN)
    assert verdict["verdict_id"].startswith("L1-")


def test_l1_coroutine_exception_detected():
    """kotlinx.coroutines 未捕获异常也应触发 fail。"""
    verdict = oracle.judge(LOGCAT_COROUTINE_EXCEPTION)
    assert verdict["outcome"] == "fail"
    validate_verdict(verdict)


def test_l1_detects_uncaught_security_exception_as_crash_stability():
    verdict = oracle.judge(LOGCAT_PERMISSION_CRASH)

    assert verdict["outcome"] == "fail"
    assert verdict["defect_class_hypothesis"] == "crash_stability"
    assert any("SecurityException" in item["ref"] for item in verdict["evidence"])
    validate_verdict(verdict)


# 真实设备 logcat 里出现过的良性 exception 提及（非本应用崩溃）：
# - gRPC/GmsCore 的 "ManagedChannel allocation site" 诊断日志（tag=gclu）
# - 被 binder stub 捕获（Caught）的 NullPointerException（tag=Binder, W 级）
# 这些都不是本应用未捕获崩溃，L1 不得因此 fail（L1 有 fail 权，误报代价最高）。
LOGCAT_BENIGN_EXCEPTION_MENTIONS = """\
07-05 17:27:58.083  1479  3410 E gclu    : java.lang.RuntimeException: ManagedChannel allocation site
07-05 17:53:56.345 11442 11460 W Binder  : Caught a RuntimeException from the binder stub implementation.
07-05 17:53:56.345 11442 11460 W Binder  : java.lang.NullPointerException: Attempt to invoke virtual method 'android.view.InsetsController android.view.ViewRootImpl.getInsetsController()' on a null object reference
07-05 17:52:21.012  3000  3000 I MainActivity: onResume
07-05 17:52:22.012  3000  3000 W PermissionProbe: caught SecurityException and showed fallback
"""


def test_l1_ignores_benign_exception_mentions_from_other_tags():
    """非 AndroidRuntime tag 的 exception 提及不得触发 fail（避免真机 logcat 噪声误报）。"""
    verdict = oracle.judge(LOGCAT_BENIGN_EXCEPTION_MENTIONS)

    assert verdict["outcome"] == "inconclusive", (
        "gRPC 诊断日志与被捕获的 binder 异常不是崩溃，L1 应弃权而非误报 fail"
    )
    assert verdict["evidence"] == []
    validate_verdict(verdict)
