"""LLM provider 接口与异源约束校验。

定标评测跑（AC4/AC7/AC8 口径）必须满足：注入侧 provider != 验证侧 provider。
日常自用允许同源，但其结果不作为对外可信数字（计划原则 6 取舍）。
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field


class Role(enum.Enum):
    """LLM 在系统中承担的角色，用于异源约束判定。"""

    INJECTOR = "injector"  # 缺陷注入方（bench/injector）
    PLANNER = "planner"  # 验证计划生成（agent/planner，验证侧）
    ORACLE_L3 = "oracle_l3"  # L3 语义判定（agent/oracle，验证侧）


#: 验证侧角色集合——与注入侧异源的约束对象
VERIFICATION_ROLES = frozenset({Role.PLANNER, Role.ORACLE_L3})


class CrossSourceViolation(Exception):
    """定标跑中注入侧与验证侧共用同一 provider 时抛出。"""


@dataclass
class CompletionResult:
    """一次 LLM 调用的结果。"""

    text: str
    model: str = ""
    raw: dict = field(default_factory=dict)


class LLMProvider(abc.ABC):
    """供应商抽象。provider_id 即模型族判据（计划原则 6：按供应商谱系）。"""

    #: 供应商谱系标识，如 "anthropic" / "openai" / "google"。
    provider_id: str = ""

    @abc.abstractmethod
    def complete(self, prompt: str, *, system: str = "") -> CompletionResult:
        """同步补全调用。真实实现需要 API key，接线见 HANDOFF.md。"""


def check_cross_source(
    assignments: dict[Role, LLMProvider], *, calibration_run: bool
) -> None:
    """校验角色-provider 分配是否满足异源约束。

    calibration_run=True（定标评测跑）时强制：INJECTOR 的 provider_id
    不得与任何验证侧角色相同，违反抛 CrossSourceViolation。
    calibration_run=False（日常自用）不强制，直接通过。
    """
    if not calibration_run:
        return
    injector = assignments.get(Role.INJECTOR)
    if injector is None:
        return
    for role in VERIFICATION_ROLES:
        verifier = assignments.get(role)
        if verifier is not None and verifier.provider_id == injector.provider_id:
            raise CrossSourceViolation(
                f"定标跑违反异源约束：注入侧与 {role.value} 共用 provider "
                f"'{injector.provider_id}'（模型族判据：provider 谱系相同即同族）"
            )


class MockProvider(LLMProvider):
    """无 key 测试用 provider：按 FIFO 返回预置响应。"""

    def __init__(self, responses: list[str], provider_id: str = "mock") -> None:
        self.provider_id = provider_id
        self._responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, prompt: str, *, system: str = "") -> CompletionResult:
        self.calls.append({"prompt": prompt, "system": system})
        if not self._responses:
            raise RuntimeError("MockProvider 预置响应已耗尽")
        return CompletionResult(text=self._responses.pop(0), model="mock")
