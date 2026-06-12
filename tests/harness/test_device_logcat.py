"""LogcatAnalyzer 单测：使用真实格式的 logcat fixture 文本验证 crash/ANR/未捕获异常提取。"""


from aiverify.harness.device import LogcatAnalyzer, LogEvent, LogEventType


# ---------------------------------------------------------------------------
# Fixture 文本：真实 Android logcat 格式
# ---------------------------------------------------------------------------

# 典型 FATAL EXCEPTION 块（Java 未捕获异常）
FIXTURE_FATAL = """\
--------- beginning of crash
06-11 10:23:45.123  1234  1234 E AndroidRuntime: FATAL EXCEPTION: main
06-11 10:23:45.123  1234  1234 E AndroidRuntime: Process: com.example.myapp, PID: 1234
06-11 10:23:45.124  1234  1234 E AndroidRuntime: java.lang.NullPointerException: Attempt to invoke virtual method 'void android.widget.TextView.setText(java.lang.CharSequence)' on a null object reference
06-11 10:23:45.124  1234  1234 E AndroidRuntime: \tat com.example.myapp.MainActivity.onCreate(MainActivity.kt:42)
06-11 10:23:45.124  1234  1234 E AndroidRuntime: \tat android.app.Activity.performCreate(Activity.java:8051)
06-11 10:23:45.124  1234  1234 E AndroidRuntime: \tat android.app.Instrumentation.callActivityOnCreate(Instrumentation.java:1329)
06-11 10:23:45.125  1234  1234 E AndroidRuntime: \tCaused by: java.lang.RuntimeException: inner cause
06-11 10:23:45.125  1234  1234 E AndroidRuntime: \t\tat com.example.myapp.utils.Helper.doWork(Helper.kt:15)
06-11 10:23:46.000  1234  1234 I ActivityManager: Process com.example.myapp (pid 1234) has died
"""

# ANR 日志片段
FIXTURE_ANR = """\
06-11 11:00:00.000  1000  1000 I am_anr  : [0,1234,com.example.myapp,952113869,executing service com.example.myapp/.MyService]
06-11 11:00:00.001  1000  1000 E ActivityManager: ANR in com.example.myapp (com.example.myapp/.MyService)
06-11 11:00:00.002  1000  1000 E ActivityManager: PID: 1234
06-11 11:00:00.003  1000  1000 E ActivityManager: Reason: executing service
06-11 11:00:01.000  1234  1234 I MyApp   : normal log continues
"""

# 通用未捕获异常（非 FATAL 路径，例如来自非主线程）
FIXTURE_UNCAUGHT = """\
06-11 12:00:00.000  5678  5678 E MyThread: UNCAUGHT EXCEPTION in background thread
06-11 12:00:00.001  5678  5678 E MyThread: \tat com.example.myapp.worker.BgWorker.run(BgWorker.java:88)
06-11 12:00:00.002  5678  5678 E MyThread: \tat java.lang.Thread.run(Thread.java:923)
06-11 12:00:01.000  5678  5678 I MyApp   : recovered
"""

# 多事件混合日志
FIXTURE_MIXED = FIXTURE_FATAL + "\n" + FIXTURE_ANR + "\n" + FIXTURE_UNCAUGHT

# 正常日志（无异常）
FIXTURE_CLEAN = """\
06-11 09:00:00.000  1234  1234 I MyApp   : Application started
06-11 09:00:01.000  1234  1234 D MyApp   : onResume called
06-11 09:00:02.000  1234  1234 I MyApp   : User clicked button
"""


# ---------------------------------------------------------------------------
# 基础测试
# ---------------------------------------------------------------------------

class TestCleanLog:
    def test_no_events_in_clean_log(self):
        analyzer = LogcatAnalyzer()
        events = analyzer.analyze(FIXTURE_CLEAN)
        assert events == []

    def test_empty_string(self):
        analyzer = LogcatAnalyzer()
        assert analyzer.analyze("") == []


# ---------------------------------------------------------------------------
# FATAL EXCEPTION / Crash
# ---------------------------------------------------------------------------

class TestFatalException:
    def setup_method(self):
        self.analyzer = LogcatAnalyzer()
        self.events = self.analyzer.analyze(FIXTURE_FATAL)

    def test_detects_exactly_one_crash(self):
        crashes = [e for e in self.events if e.type == LogEventType.CRASH]
        assert len(crashes) == 1

    def test_crash_type_is_crash(self):
        crash = self.events[0]
        assert crash.type == LogEventType.CRASH

    def test_crash_process_extracted(self):
        crash = self.events[0]
        assert crash.process == "com.example.myapp,"  # 行末含逗号，与真实 logcat 一致

    def test_crash_stacktrace_contains_fatal_line(self):
        crash = self.events[0]
        assert any("FATAL EXCEPTION" in line for line in crash.stacktrace)

    def test_crash_stacktrace_contains_at_frames(self):
        crash = self.events[0]
        at_lines = [l for l in crash.stacktrace if "at com.example" in l]
        assert len(at_lines) >= 1

    def test_crash_stacktrace_contains_caused_by(self):
        crash = self.events[0]
        caused = [l for l in crash.stacktrace if "Caused by" in l]
        assert len(caused) >= 1

    def test_crash_stacktrace_is_list_of_strings(self):
        crash = self.events[0]
        assert isinstance(crash.stacktrace, list)
        assert all(isinstance(l, str) for l in crash.stacktrace)


# ---------------------------------------------------------------------------
# ANR
# ---------------------------------------------------------------------------

class TestAnr:
    def setup_method(self):
        self.analyzer = LogcatAnalyzer()
        self.events = self.analyzer.analyze(FIXTURE_ANR)

    def test_detects_anr(self):
        anrs = [e for e in self.events if e.type == LogEventType.ANR]
        assert len(anrs) >= 1

    def test_anr_process_extracted(self):
        anr = next(e for e in self.events if e.type == LogEventType.ANR)
        assert "com.example.myapp" in anr.process

    def test_anr_stacktrace_contains_trigger_line(self):
        anr = next(e for e in self.events if e.type == LogEventType.ANR)
        assert any("ANR in" in line for line in anr.stacktrace)

    def test_anr_type_is_anr(self):
        anr = next(e for e in self.events if e.type == LogEventType.ANR)
        assert anr.type == LogEventType.ANR


# ---------------------------------------------------------------------------
# 通用未捕获异常
# ---------------------------------------------------------------------------

class TestUncaughtException:
    def setup_method(self):
        self.analyzer = LogcatAnalyzer()
        self.events = self.analyzer.analyze(FIXTURE_UNCAUGHT)

    def test_detects_uncaught(self):
        uncaught = [e for e in self.events if e.type == LogEventType.UNCAUGHT]
        assert len(uncaught) == 1

    def test_uncaught_stacktrace_has_at_frames(self):
        evt = next(e for e in self.events if e.type == LogEventType.UNCAUGHT)
        at_lines = [l for l in evt.stacktrace if "at com.example" in l or "at java" in l]
        assert len(at_lines) >= 1

    def test_uncaught_does_not_duplicate_as_crash(self):
        crashes = [e for e in self.events if e.type == LogEventType.CRASH]
        assert len(crashes) == 0


# ---------------------------------------------------------------------------
# 混合日志多事件
# ---------------------------------------------------------------------------

class TestMixedLog:
    def setup_method(self):
        self.analyzer = LogcatAnalyzer()
        self.events = self.analyzer.analyze(FIXTURE_MIXED)

    def test_finds_crash(self):
        assert any(e.type == LogEventType.CRASH for e in self.events)

    def test_finds_anr(self):
        assert any(e.type == LogEventType.ANR for e in self.events)

    def test_finds_uncaught(self):
        assert any(e.type == LogEventType.UNCAUGHT for e in self.events)

    def test_events_in_order(self):
        """Crash 出现在 ANR 之前，ANR 出现在 Uncaught 之前。"""
        types = [e.type for e in self.events]
        crash_idx = next((i for i, t in enumerate(types) if t == LogEventType.CRASH), None)
        anr_idx = next((i for i, t in enumerate(types) if t == LogEventType.ANR), None)
        uncaught_idx = next((i for i, t in enumerate(types) if t == LogEventType.UNCAUGHT), None)
        assert crash_idx is not None
        assert anr_idx is not None
        assert uncaught_idx is not None
        assert crash_idx < anr_idx < uncaught_idx

    def test_total_events_count(self):
        # FATAL(1) + ANR(>=1) + UNCAUGHT(1)
        assert len(self.events) >= 3


# ---------------------------------------------------------------------------
# LogEvent repr
# ---------------------------------------------------------------------------

class TestLogEventRepr:
    def test_repr_contains_type_and_process(self):
        evt = LogEvent(
            type=LogEventType.CRASH,
            process="com.example",
            stacktrace=["line1", "line2"],
        )
        r = repr(evt)
        assert "crash" in r
        assert "com.example" in r
        assert "2" in r  # stacktrace_lines=2


# ---------------------------------------------------------------------------
# LogEventType 枚举值
# ---------------------------------------------------------------------------

class TestLogEventType:
    def test_values(self):
        assert LogEventType.CRASH == "crash"
        assert LogEventType.ANR == "anr"
        assert LogEventType.UNCAUGHT == "uncaught"


# ---------------------------------------------------------------------------
# 多个 crash 块在同一日志中
# ---------------------------------------------------------------------------

FIXTURE_TWO_CRASHES = """\
06-11 10:00:00.000  1111  1111 E AndroidRuntime: FATAL EXCEPTION: main
06-11 10:00:00.001  1111  1111 E AndroidRuntime: Process: com.first.app, PID: 1111
06-11 10:00:00.002  1111  1111 E AndroidRuntime: \tat com.first.app.Activity.onCreate(Activity.java:10)
06-11 10:00:01.000  2222  2222 I SomeTag : some normal line
06-11 10:00:02.000  2222  2222 E AndroidRuntime: FATAL EXCEPTION: async
06-11 10:00:02.001  2222  2222 E AndroidRuntime: Process: com.second.app, PID: 2222
06-11 10:00:02.002  2222  2222 E AndroidRuntime: \tat com.second.app.Worker.run(Worker.java:55)
"""


class TestMultipleCrashes:
    def test_detects_two_separate_crashes(self):
        analyzer = LogcatAnalyzer()
        events = analyzer.analyze(FIXTURE_TWO_CRASHES)
        crashes = [e for e in events if e.type == LogEventType.CRASH]
        assert len(crashes) == 2

    def test_each_crash_has_distinct_process(self):
        analyzer = LogcatAnalyzer()
        events = analyzer.analyze(FIXTURE_TWO_CRASHES)
        crashes = [e for e in events if e.type == LogEventType.CRASH]
        processes = {e.process for e in crashes}
        # 两个 crash 的进程名不同
        assert len(processes) == 2
