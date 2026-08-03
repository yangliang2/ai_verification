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


def test_living_docs_point_to_m6_without_merging_track_denominators() -> None:
    for path in (_ROOT / "README.md", _ROOT / "HANDOFF.md", _MATRIX, _GAP_REGISTER):
        text = path.read_text(encoding="utf-8")
        assert "#82" in text
        assert "#83" in text
        assert "#84" in text
        assert "#85" in text
        assert "#86" in text
        assert "#87" in text
        assert "#88" in text
        assert "historical" in text
        assert "prospective" in text

    combined = "\n".join(path.read_text(encoding="utf-8") for path in _LIVING_DOCS)
    assert "denominator" in combined
    assert "不能合并" in combined or "保持分离" in combined
    assert "不得启动 formal M6 lane" in combined


def test_all_relative_links_in_living_docs_resolve() -> None:
    for document in _LIVING_DOCS:
        text = document.read_text(encoding="utf-8")
        for target in _MARKDOWN_LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            local_target = target.split("#", maxsplit=1)[0]
            resolved = (document.parent / local_target).resolve()
            assert resolved.exists(), f"{document}: broken local link {target}"
