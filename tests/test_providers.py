"""providers 抽象与异源约束校验的单测。"""

import pytest

from aiverify.providers import (
    CrossSourceViolation,
    MockProvider,
    Role,
    check_cross_source,
)


def _assign(injector_id: str, planner_id: str, oracle_id: str):
    return {
        Role.INJECTOR: MockProvider([], provider_id=injector_id),
        Role.PLANNER: MockProvider([], provider_id=planner_id),
        Role.ORACLE_L3: MockProvider([], provider_id=oracle_id),
    }


def test_calibration_run_rejects_same_provider_for_injector_and_oracle():
    with pytest.raises(CrossSourceViolation):
        check_cross_source(
            _assign("anthropic", "openai", "anthropic"), calibration_run=True
        )


def test_calibration_run_rejects_same_provider_for_injector_and_planner():
    with pytest.raises(CrossSourceViolation):
        check_cross_source(
            _assign("openai", "openai", "anthropic"), calibration_run=True
        )


def test_calibration_run_accepts_cross_source_assignment():
    check_cross_source(_assign("anthropic", "openai", "openai"), calibration_run=True)


def test_daily_use_allows_same_source():
    check_cross_source(
        _assign("anthropic", "anthropic", "anthropic"), calibration_run=False
    )


def test_mock_provider_returns_responses_in_order_and_records_calls():
    p = MockProvider(["a", "b"])
    assert p.complete("p1", system="s1").text == "a"
    assert p.complete("p2").text == "b"
    assert p.calls[0] == {"prompt": "p1", "system": "s1"}
    with pytest.raises(RuntimeError):
        p.complete("p3")
