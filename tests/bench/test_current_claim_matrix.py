from __future__ import annotations

import re
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_MATRIX = _ROOT / "docs" / "current-capability-claim-matrix.md"
_GAP_REGISTER = (
    _ROOT / "docs" / "research" / "2026-07-19-verification-gap-register.md"
)
_LIVING_DOCS = (
    _ROOT / "README.md",
    _ROOT / "HANDOFF.md",
    _ROOT / "CONTEXT.md",
    _MATRIX,
    _GAP_REGISTER,
)
_CURRENT_SOURCE_OF_TRUTH_DOCS = (
    _ROOT / "README.md",
    _ROOT / "HANDOFF.md",
    _ROOT / "CONTEXT.md",
    _MATRIX,
)
_MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def test_claim_matrix_maps_execution_benchmark_and_capability_evidence() -> None:
    text = _MATRIX.read_text(encoding="utf-8")

    for trust_record in (
        "2026-06-15-afk-verification",
        "2026-07-17-issue-60-execution-record-system-event",
        "2026-07-17-issue-61-effective-execution-identity",
        "2026-07-18-issue-67-portable-host-locator",
        "2026-07-21-issue-80-m3-fresh",
    ):
        assert trust_record in text

    for population in (
        "M1 five-seed report",
        "M2-beta injected slice",
        "原 M3 population",
        "M3 v2 population",
        "#62 M3.1 v3 population",
        "#80 fresh M3.1 population",
        "M4 prospective pilot",
    ):
        assert population in text

    for gap in (f"G-0{number}" for number in range(1, 9)):
        assert gap in text


def test_claim_matrix_uses_explicit_statuses_and_claim_boundaries() -> None:
    text = _MATRIX.read_text(encoding="utf-8")

    for status in (
        "有界证据支持",
        "non_accountable",
        "尚未度量",
        "当前不声明",
    ):
        assert status in text

    for excluded_claim in (
        "benchmark-wide detection/false-positive rate",
        "physical/OEM/device-fleet",
        "fully unattended Journey reliability",
        "visual-only/general multimodal L3",
        "upstream acceptance",
    ):
        assert excluded_claim in text


def test_living_docs_preserve_m3_and_m4_audit_facts() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in _LIVING_DOCS)

    for result in (
        "30/30",
        "15/15",
        "0 retries",
        "两个 accountable",
        "一个 `non_accountable`",
        "chronology",
        "retrospective",
    ):
        assert result in combined

    assert "#58 已" in combined
    assert "#59 已" in combined
    assert "M4 早于后来有效的 #80 gate" in combined


def test_living_docs_point_to_m6_closeout_and_m7_boundary() -> None:
    for path in (_ROOT / "README.md", _ROOT / "HANDOFF.md", _MATRIX, _GAP_REGISTER):
        text = path.read_text(encoding="utf-8")
        assert "#82" in text
        assert "#84" in text
        assert "#97" in text
        assert "#98" in text
        assert "#99" in text
        assert "#100" in text
        assert "historical" in text
        assert "prospective" in text

    combined = "\n".join(path.read_text(encoding="utf-8") for path in _LIVING_DOCS)
    assert "denominator" in combined
    assert "不能合并" in combined or "保持分离" in combined
    assert "36/36" in combined
    assert "P-03" in combined
    assert "inconclusive" in combined
    assert "remediate_fixture_execution_oracle_adjudication_gaps" in combined
    assert "fail closed" in combined


def test_living_docs_do_not_present_m6_as_the_current_milestone() -> None:
    for path in _LIVING_DOCS:
        text = path.read_text(encoding="utf-8")
        assert "current milestone is M6" not in text
        assert "M6 计划" not in text


def test_current_source_of_truth_records_issue_158_as_completed() -> None:
    texts = {
        document: document.read_text(encoding="utf-8")
        for document in _CURRENT_SOURCE_OF_TRUTH_DOCS
    }
    combined = "\n".join(texts.values())

    for document, text in texts.items():
        assert "#158" in text, document
        assert "PR #160" in text, document
        assert "9dfb19e" in text, document

    for capability in (
        "target-specific preclaim",
        "terminal_absence_receipt",
        "formal_attempt_reconciled",
        "runtime_holdout_executed",
    ):
        assert capability in combined

    for stale_guidance in (
        "当前唯一明确的 forward work 是 #158",
        "剩余 #158",
        "Future-only hardening is tracked in #158",
    ):
        assert stale_guidance not in combined

    assert re.search(
        r"没有已批准\s*的新\s+formal population",
        texts[_ROOT / "HANDOFF.md"],
    )
    assert "不回填或重跑 #154" in combined


def test_all_relative_links_in_living_docs_resolve() -> None:
    for document in _LIVING_DOCS:
        text = document.read_text(encoding="utf-8")
        for target in _MARKDOWN_LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            local_target = target.split("#", maxsplit=1)[0]
            resolved = (document.parent / local_target).resolve()
            assert resolved.exists(), f"{document}: broken local link {target}"
