"""LLM provider 抽象层。

异源约束（计划原则 6）的代码落点：缺陷注入方与验证判定方（计划生成 + L3 oracle）
不得共享同一 provider。模型族按供应商谱系划分：provider 标识不同即合规。
"""

from aiverify.providers.base import (
    CrossSourceViolation,
    LLMProvider,
    MockProvider,
    Role,
    check_cross_source,
)

__all__ = [
    "CrossSourceViolation",
    "LLMProvider",
    "MockProvider",
    "Role",
    "check_cross_source",
]
