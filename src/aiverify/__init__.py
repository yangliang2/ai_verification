"""aiverify — AI 行为层验证 Agent + 缺陷注入评测系统。

子包：
- harness.device  adb 设备编排层（系统事件原语、采集）
- harness.build   批量构建管线（patch/分批/构建/缓存）
- agent.planner   验证计划生成器
- agent.oracle    分层判定（L1 crash/ANR、L2 状态断言、L3 LLM 语义）
- bench.taxonomy  行为层缺陷分类法
- providers       LLM provider 抽象（异源约束的代码落点）
"""

__version__ = "0.1.0"
