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
    assert "quarantine is resolved" in normalized_text
    assert "accounting state: `included`" in text
    assert "injected-defect denominator impact: `1`" in text
    assert "defect outcome: `caught`" in text
    assert "baseline-control outcome: `passed_control`" in text


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

    assert "docs/runs/2026-07-09-live-validation-gate-current-environment/README.md" in text
    assert "docs/runs/2026-07-09-wikipedia-app-smoke-gate/README.md" in text
    assert "The later live validation gate evidence proved the environment" in text


def test_oversized_saved_state_quarantine_records_successful_inclusion_path() -> None:
    text = _QUARANTINE.read_text(encoding="utf-8")
    normalized_text = " ".join(text.split())

    assert "valid baseline/defect matched pair" in text
    assert "baseline/control lane reached `SearchActivity`" in text
    assert "defect run captured an interpretable L1 `crash_stability` oracle result" in text
    assert "`caught` injected-defect seed with a `passed_control` baseline" in normalized_text


def test_inclusion_rules_link_the_quarantine_note() -> None:
    text = _INCLUSION_RULES.read_text(encoding="utf-8")

    assert "docs/M2-beta-oversized-saved-state-quarantine.md" in text
