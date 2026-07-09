from __future__ import annotations

from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_QUARANTINE = _ROOT / "docs" / "M2-beta-oversized-saved-state-quarantine.md"
_INCLUSION_RULES = _ROOT / "docs" / "M2-beta-inclusion-rules.md"


def test_oversized_saved_state_quarantine_records_accounting_status() -> None:
    text = _QUARANTINE.read_text(encoding="utf-8")
    normalized_text = " ".join(text.split())

    assert "#23" in text
    assert "#27" in text
    assert "quarantined from the M2-beta benchmark slice" in normalized_text
    assert "accounting state: `candidate` and `blocked`" in text
    assert "injected-defect denominator impact: `0`" in text
    assert "caught/missed outcome: none" in text


def test_oversized_saved_state_quarantine_links_blocking_evidence() -> None:
    text = _QUARANTINE.read_text(encoding="utf-8")

    assert (
        "docs/runs/2026-07-09-wikipedia-process-death-03-oversized-saved-state-live-retry/README.md"
        in text
    )
    assert "the app task closed before `nav_tab_search`" in text
    assert "Android CLI layout / UIAutomator remained unstable" in text
    assert "no defect lane was run" in text


def test_oversized_saved_state_quarantine_links_live_gate_evidence() -> None:
    text = _QUARANTINE.read_text(encoding="utf-8")
    normalized_text = " ".join(text.split())

    assert "docs/runs/2026-07-09-live-validation-gate-current-environment/README.md" in text
    assert "docs/runs/2026-07-09-wikipedia-app-smoke-gate/README.md" in text
    assert "ready for seed-specific matched-pair retry" in normalized_text
    assert "do not change M2-beta accounting by themselves" in text


def test_oversized_saved_state_quarantine_preserves_future_inclusion_path() -> None:
    text = _QUARANTINE.read_text(encoding="utf-8")
    normalized_text = " ".join(text.split())

    assert "valid baseline/defect matched pair" in text
    assert "passing generic live validation gate" in text
    assert "passing Wikipedia app-level smoke gate" in text
    assert "baseline/control run captures an interpretable oracle result" in text
    assert "defect run captures an interpretable L1/L2/L3 oracle result" in text
    assert "must remain outside M2-beta caught/missed accounting" in normalized_text


def test_inclusion_rules_link_the_quarantine_note() -> None:
    text = _INCLUSION_RULES.read_text(encoding="utf-8")

    assert "docs/M2-beta-oversized-saved-state-quarantine.md" in text
