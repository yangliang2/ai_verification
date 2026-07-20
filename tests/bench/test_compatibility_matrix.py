import json
from pathlib import Path

from aiverify.bench.compatibility_matrix import judge_matrix, load_contract
from aiverify.runner.run_spec import load_run_spec


CONTRACT = Path("bench/capability-slices/compatibility-matrix/contract.json")


def _layout(cell_id: str, *, direction_override: str | None = None):
    cells, sentinel = load_contract(CONTRACT)
    cell = next(cell for cell in cells if cell.id == cell_id)
    rtl = cell.direction == "rtl"
    start_x, end_x = ((900, 200) if rtl else (200, 900))
    smallest = 720 if cell.form_factor == "tablet" else 411
    return [
        {"resource-id": "compatibility_title", "text": cell.title, "center": "[550,100]"},
        {"resource-id": "compatibility_start_anchor", "text": "start", "center": f"[{start_x},200]"},
        {"resource-id": "compatibility_end_anchor", "text": "end", "center": f"[{end_x},200]"},
        {"resource-id": "compatibility_state", "text": sentinel, "center": "[550,300]"},
        {"resource-id": "compatibility_direction", "text": f"DIRECTION_{(direction_override or cell.direction).upper()}", "center": "[550,400]"},
        {"resource-id": "compatibility_configuration", "text": f"locale={cell.locale};orientation={cell.orientation};width_dp={smallest};height_dp=800;smallest_width_dp={smallest}", "center": "[550,500]"},
    ]


def test_all_preregistered_cells_pass():
    cells, _ = load_contract(CONTRACT)
    result = judge_matrix(contract_path=CONTRACT, layouts={cell.id: _layout(cell.id) for cell in cells})
    assert result["conclusion"] == "locally_supported"
    assert len(result["cells"]) == 4


def test_forced_ltr_candidate_is_rejected():
    cells, _ = load_contract(CONTRACT)
    layouts = {cell.id: _layout(cell.id) for cell in cells}
    layouts["phone-ar-portrait"] = _layout("phone-ar-portrait", direction_override="ltr")
    result = judge_matrix(contract_path=CONTRACT, layouts=layouts)
    assert result["conclusion"] == "locally_rejected"
    assert result["cells"][1]["reason"] == "semantic_direction_drift"


def test_missing_cell_fails_closed_and_remains_listed():
    result = judge_matrix(contract_path=CONTRACT, layouts={"phone-en-portrait": _layout("phone-en-portrait")})
    assert result["conclusion"] == "non_accountable"
    assert [cell["cell_id"] for cell in result["cells"]] == [
        "phone-en-portrait", "phone-ar-portrait", "phone-ar-landscape", "tablet-ar-landscape"
    ]


def test_undeclared_cell_fails_closed():
    cells, _ = load_contract(CONTRACT)
    layouts = {cell.id: _layout(cell.id) for cell in cells}
    layouts["extra"] = []
    result = judge_matrix(contract_path=CONTRACT, layouts=layouts)
    assert result["conclusion"] == "non_accountable"
    assert result["undeclared_cells"] == ["extra"]


def test_off_screen_or_state_reset_is_rejected():
    cells, _ = load_contract(CONTRACT)
    layouts = {cell.id: _layout(cell.id) for cell in cells}
    layouts["phone-en-portrait"][0]["off-screen"] = True
    result = judge_matrix(contract_path=CONTRACT, layouts=layouts)
    assert result["cells"][0]["reason"] == "clipped_or_off_screen"


def test_preregistered_run_specs_match_contract():
    cells, _ = load_contract(CONTRACT)
    specs = [
        load_run_spec(
            Path("bench/capability-slices/compatibility-matrix/run-specs")
            / f"{cell.id}.yaml"
        )
        for cell in cells
    ]
    assert [spec.scenario.id for spec in specs] == [
        f"compatibility-{cell.id}" for cell in cells
    ]
    assert all(len(spec.scenario.system_events) == 2 for spec in specs)
    assert all(spec.scenario.system_events[0].event == "locale_change" for spec in specs)
