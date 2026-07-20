import copy
import json
from pathlib import Path

import pytest

from aiverify.bench.accessibility_slice import contrast_ratio, judge_accessibility, load_uiautomator_layout
from aiverify.runner.run_spec import load_run_spec


CONTRACT = Path("bench/capability-slices/accessibility/contract.json")


def _node(resource_id, name, top, *, actionable=False):
    node = {
        "resource-id": resource_id,
        "text": name,
        "content-desc": name,
        "bounds": f"[0,{top}][200,{top + 100}]",
    }
    if actionable:
        node["interactions"] = ["clickable", "focusable"]
    return node


def _layouts():
    return {
        "main": [
            _node("accessibility_title", "Accessibility verification fixture", 0),
            _node("accessibility_dynamic", "Status: ready", 100),
            _node("accessibility_dialog", "Open details", 200, actionable=True),
            _node("accessibility_navigate", "Continue", 300, actionable=True),
        ],
        "dialog": [
            _node("accessibility_dialog_title", "Verification details", 0),
            _node("accessibility_dialog_message", "Dynamic status is ready", 100),
            _node("accessibility_dialog_close", "Close", 200, actionable=True),
        ],
        "navigation": [
            _node("accessibility_destination", "Destination reached", 0),
            _node("accessibility_back", "Back", 100, actionable=True),
        ],
    }


def _judge(layouts=None, density=2):
    return judge_accessibility(contract_path=CONTRACT, checkpoints=layouts or _layouts(), density=density)


def test_preregistered_baseline_passes_all_checkpoints():
    result = _judge()
    assert result["conclusion"] == "locally_supported"
    assert [item["checkpoint_id"] for item in result["checkpoints"]] == ["main", "dialog", "navigation"]


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda layouts: layouts["main"][3].update(**{"content-desc": ""}), "missing_or_wrong_accessible_name"),
        (lambda layouts: layouts["main"][3].update(**{"content-desc": "Wrong"}), "missing_or_wrong_accessible_name"),
        (lambda layouts: layouts["main"].reverse(), "incorrect_traversal_order"),
        (lambda layouts: layouts["main"][3].pop("interactions"), "inaccessible_actionable_control"),
        (lambda layouts: layouts["main"][3].update(bounds="[0,0][80,80]"), "undersized_touch_target"),
    ],
)
def test_semantic_and_geometry_defects_are_rejected(mutation, reason):
    layouts = _layouts()
    mutation(layouts)
    result = _judge(layouts)
    assert result["conclusion"] == "locally_rejected"
    assert result["checkpoints"][0]["reason"] == reason


def test_accessible_node_removed_by_candidate_is_rejected():
    layouts = _layouts()
    layouts["main"].pop()
    result = _judge(layouts)
    assert result["conclusion"] == "locally_rejected"
    assert result["checkpoints"][0]["reason"] == "missing_accessible_node"


def test_duplicate_accessible_names_are_rejected(tmp_path):
    contract = json.loads(CONTRACT.read_text())
    contract["checkpoints"][0]["nodes"][3]["accessible_name"] = "Open details"
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract))
    layouts = _layouts()
    layouts["main"][3]["content-desc"] = "Open details"
    result = judge_accessibility(contract_path=path, checkpoints=layouts, density=2)
    assert result["checkpoints"][0]["reason"] == "duplicate_accessible_name"


def test_contrast_formula_and_violation(tmp_path):
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21)
    contract = json.loads(CONTRACT.read_text())
    contract["checkpoints"][0]["contrast"][0]["foreground"] = "#777777"
    contract["checkpoints"][0]["contrast"][0]["background"] = "#888888"
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract))
    result = judge_accessibility(contract_path=path, checkpoints=_layouts(), density=2)
    assert result["checkpoints"][0]["reason"] == "contrast_violation"


def test_missing_extra_and_unobservable_evidence_fail_closed():
    layouts = _layouts()
    layouts.pop("dialog")
    assert _judge(layouts)["conclusion"] == "non_accountable"
    layouts = _layouts()
    layouts["extra"] = []
    assert _judge(layouts)["reason"] == "undeclared_checkpoints"
    layouts = _layouts()
    layouts["main"][3].pop("bounds")
    assert _judge(layouts)["checkpoints"][0]["reason"] == "target_geometry_unobservable"
    assert _judge(density=0)["reason"] == "density_unobservable"


def test_duplicate_checkpoint_contract_is_invalid(tmp_path):
    contract = json.loads(CONTRACT.read_text())
    contract["checkpoints"].append(copy.deepcopy(contract["checkpoints"][0]))
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract))
    with pytest.raises(ValueError, match="unique"):
        judge_accessibility(contract_path=path, checkpoints=_layouts(), density=2)


def test_uiautomator_xml_is_normalized_in_accessibility_order(tmp_path):
    path = tmp_path / "layout.xml"
    path.write_text('''<?xml version="1.0"?><hierarchy><node resource-id="dev.fixture:id/first" text="First" content-desc="" bounds="[0,0][100,100]" clickable="false" focusable="false"><node resource-id="dev.fixture:id/second" text="" content-desc="Second" bounds="[0,100][100,200]" clickable="true" focusable="true" /></node></hierarchy>''')
    assert load_uiautomator_layout(path) == [
        {"resource-id": "first", "text": "First", "content-desc": "", "bounds": "[0,0][100,100]", "interactions": []},
        {"resource-id": "second", "text": "", "content-desc": "Second", "bounds": "[0,100][100,200]", "interactions": ["clickable", "focusable"]},
    ]


def test_matched_run_specs_and_frozen_candidate_patch():
    root = Path("bench/capability-slices/accessibility/run-specs")
    baseline = load_run_spec(root / "baseline.yaml")
    candidate = load_run_spec(root / "candidate.yaml")
    assert baseline.scenario.user_actions == candidate.scenario.user_actions
    assert baseline.scenario.system_events == candidate.scenario.system_events == []
    assert baseline.scenario.assertions == candidate.scenario.assertions
    assert baseline.scenario.expected_behavior == candidate.scenario.expected_behavior
    assert baseline.scenario.metric_context.seed_kind == "baseline_control"
    assert candidate.scenario.metric_context.seed_kind == "injected_defect"
    assert candidate.diff and candidate.diff.name == "missing-continue-label.patch"
    patch = candidate.diff.read_text()
    assert patch.count("navigate.setContentDescription(\"Continue\")") == 1
    assert patch.count("navigate.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO)") == 1
