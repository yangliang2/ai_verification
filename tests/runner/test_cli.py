"""runner CLI 的 L3 门控与降级逻辑单测（不触真机）。"""

import json

import pytest

import aiverify.runner.cli as cli
from aiverify.providers.base import MockProvider
from aiverify.runner.codex_backend import JourneyExecutionResult
from aiverify.runner.evidence import EvidenceCheckpoint
from aiverify.runner.journey import JourneySegmentFlow
from aiverify.runner.run_spec import RunSpec, ScenarioSpec


def _spec(tmp_path, l3_spec: str) -> RunSpec:
    return RunSpec(
        host_project=tmp_path,
        apk_glob="*.apk",
        package="org.wikipedia.dev",
        activity=None,
        diff=None,
        spec=None,
        scenario=ScenarioSpec(
            id="ui-rendering-test",
            user_actions=["走完 onboarding 到主 feed，观察底部导航栏"],
            l3_spec=l3_spec,
        ),
    )


def _flow(tmp_path) -> JourneySegmentFlow:
    cp_dir = tmp_path / "after-segment-0"
    cp_dir.mkdir()
    layout = cp_dir / "layout.json"
    layout.write_text('[{"resource-id": "nav_tab_home", "content-desc": "Home"}]', encoding="utf-8")
    screenshot = cp_dir / "screen.png"
    screenshot.write_bytes(b"png")
    cp = EvidenceCheckpoint(
        name="after-segment-0", directory=cp_dir, layout_path=layout,
        screenshot_path=screenshot, annotated_screenshot_path=None,
        logcat_path=cp_dir / "logcat.txt", commands_path=cp_dir / "commands.json",
    )
    jr = JourneyExecutionResult(
        data={"journey": "seg-0", "results": [{"action": "a", "status": "PASSED"}]},
        result_path=cp_dir / "codex-journey-result.json",
        events_path=cp_dir / "codex-events.jsonl",
        command=["codex"],
    )
    return JourneySegmentFlow(journey_results=[jr], checkpoints=[cp])


def _oracle_verdict(outcome: str, level: str) -> dict:
    return {
        "verdict_id": f"{level}-test", "level": level, "outcome": outcome,
        "defect_class_hypothesis": None, "trigger_steps": [],
        "evidence": [], "confidence": 0.5,
    }


_VALID_L3_JSON = json.dumps({
    "verdict_id": "L3-deadbeef", "level": "L3", "outcome": "fail",
    "defect_class_hypothesis": "ui_rendering",
    "trigger_steps": ["observe bottom nav"],
    "evidence": [{"type": "llm_reasoning", "ref": "layout", "note": "labels swapped"}],
    "confidence": 0.9,
})


@pytest.fixture
def mock_provider_cls(monkeypatch):
    """把 cli.CodexCliProvider 换成返回预置响应的 MockProvider 工厂。"""
    holder: dict = {"provider": None, "responses": [], "init_kwargs": []}

    def factory(**kwargs):
        holder["init_kwargs"].append(kwargs)
        holder["provider"] = MockProvider(list(holder["responses"]))
        return holder["provider"]

    monkeypatch.setattr(cli, "CodexCliProvider", factory)
    return holder


def test_l3_skipped_without_l3_spec(tmp_path, mock_provider_cls):
    verdict = cli._judge_l3(
        _spec(tmp_path, l3_spec=""), _flow(tmp_path),
        l1=_oracle_verdict("inconclusive", "L1"), l2=_oracle_verdict("inconclusive", "L2"),
        steps=[], workdir=tmp_path, artifact_dir=tmp_path, model=None,
    )
    assert verdict is None
    assert mock_provider_cls["provider"] is None  # 未构造 provider，零成本


@pytest.mark.parametrize("l1_outcome,l2_outcome", [("fail", "inconclusive"), ("inconclusive", "fail")])
def test_l3_skipped_when_cheaper_oracle_already_failed(tmp_path, mock_provider_cls, l1_outcome, l2_outcome):
    verdict = cli._judge_l3(
        _spec(tmp_path, l3_spec="底部导航必须显示 Home/Saved/Search/Activity/More"), _flow(tmp_path),
        l1=_oracle_verdict(l1_outcome, "L1"), l2=_oracle_verdict(l2_outcome, "L2"),
        steps=[], workdir=tmp_path, artifact_dir=tmp_path, model=None,
    )
    assert verdict is None
    assert mock_provider_cls["provider"] is None


def test_l3_runs_when_gated_open_and_returns_judge_verdict(tmp_path, mock_provider_cls):
    mock_provider_cls["responses"] = [_VALID_L3_JSON]
    flow = _flow(tmp_path)
    spec = _spec(tmp_path, l3_spec="底部导航必须显示 Home/Saved/Search/Activity/More")
    verdict = cli._judge_l3(
        spec, flow,
        l1=_oracle_verdict("inconclusive", "L1"), l2=_oracle_verdict("inconclusive", "L2"),
        steps=["step-1"], workdir=tmp_path, artifact_dir=tmp_path, model=None,
    )
    assert verdict is not None
    assert verdict["outcome"] == "fail"
    assert verdict["defect_class_hypothesis"] == "ui_rendering"
    # judge 收到的 prompt 含轨迹事实：用户动作 + 最终 layout 全文
    prompt = mock_provider_cls["provider"].calls[0]["prompt"]
    assert "走完 onboarding" in prompt
    assert "nav_tab_home" in prompt
    assert "底部导航必须显示" in prompt
    # 且不含 expected_behavior 之类的泄题通道（spec 里本来就没设）
    # timing 增加 l3-judge phase
    assert flow.timings[-1]["phase"] == "l3-judge"
    assert flow.timings[-1]["kind"] == "oracle"


def test_l3_schema_failure_twice_degrades_to_inconclusive(tmp_path, mock_provider_cls):
    mock_provider_cls["responses"] = ['{"not": "a verdict"}', '{"still": "not"}']
    verdict = cli._judge_l3(
        _spec(tmp_path, l3_spec="spec"), _flow(tmp_path),
        l1=_oracle_verdict("inconclusive", "L1"), l2=_oracle_verdict("inconclusive", "L2"),
        steps=["s"], workdir=tmp_path, artifact_dir=tmp_path, model=None,
    )
    assert verdict is not None
    assert verdict["verdict_id"] == "L3-error"
    assert verdict["outcome"] == "inconclusive"
    assert "VerdictValidationError" in verdict["evidence"][0]["note"]


def test_l3_unparseable_json_degrades_to_inconclusive(tmp_path, mock_provider_cls):
    mock_provider_cls["responses"] = ["this is not json at all"]
    verdict = cli._judge_l3(
        _spec(tmp_path, l3_spec="spec"), _flow(tmp_path),
        l1=_oracle_verdict("inconclusive", "L1"), l2=_oracle_verdict("inconclusive", "L2"),
        steps=["s"], workdir=tmp_path, artifact_dir=tmp_path, model=None,
    )
    assert verdict is not None
    assert verdict["verdict_id"] == "L3-error"
    assert verdict["outcome"] == "inconclusive"
