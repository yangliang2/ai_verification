"""验证计划数据模型。

VerificationPlan 是 PlanGenerator 的输出结构，描述对一次代码变更的
验证场景簇、规格盲区猜想与改动理解摘要。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SystemEventStep:
    """系统事件编排点：在某个操作步骤索引处注入受控系统事件。

    Attributes:
        step_index: 在 user_actions 序列中对应的步骤索引（0-based）。
        event: 受控系统事件类型，如 rotate / kill_background / network_off 等。
    """

    step_index: int
    event: str


@dataclass
class ScenarioCluster:
    """验证场景簇：描述一组关联紧密的验证场景。

    Attributes:
        id: 场景簇唯一标识符。
        target_screens: 目标界面列表。
        user_actions: 操作意图序列（自然语言步骤列表）。
        system_events: 系统事件编排点列表，可为空列表。
        expected_behavior: 期望的系统行为描述。
        related_defect_patterns: 关联 taxonomy 模式 id 列表，可为空列表。
    """

    id: str
    target_screens: list[str]
    user_actions: list[str]
    system_events: list[SystemEventStep]
    expected_behavior: str
    related_defect_patterns: list[str] = field(default_factory=list)


@dataclass
class SpecBlindSpot:
    """规格盲区猜想：描述规格文档中可能遗漏或未覆盖的场景。

    Attributes:
        description: 规格盲区描述。
        rationale: 猜测该盲区存在的理由。
    """

    description: str
    rationale: str


@dataclass
class VerificationPlan:
    """验证计划：AI 对一次代码变更的完整验证规划。

    Attributes:
        change_summary: 对本次代码变更的理解摘要。
        scenario_clusters: 验证场景簇列表。
        spec_blind_spots: 规格盲区猜想列表。
    """

    change_summary: str
    scenario_clusters: list[ScenarioCluster]
    spec_blind_spots: list[SpecBlindSpot]
