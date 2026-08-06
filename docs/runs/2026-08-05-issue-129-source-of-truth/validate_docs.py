"""Validate the M9-0 source-of-truth vocabulary and claim boundary.

This is intentionally a read-only, standard-library-only check. It validates the
living Markdown documents that define the M9 boundary; it does not import or run
any M9 implementation and does not access a host project, device, backend, or
formal cohort.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LIVING_DOCS = (
    ROOT / "CONTEXT.md",
    ROOT / "README.md",
    ROOT / "HANDOFF.md",
    ROOT / "docs/current-capability-claim-matrix.md",
)
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def check(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    texts = {path: path.read_text(encoding="utf-8") for path in LIVING_DOCS}
    combined = "\n".join(texts.values())

    glossary_terms = (
        "Context Acquisition",
        "Hypothesis Portfolio",
        "Exploration Stop Rule",
        "Falsification Review",
        "Context Fact",
        "Quality Context Graph",
        "Risk Hypothesis",
        "Attack Plan",
        "Finding",
        "Residual Risk",
        "Project Risk Map",
        "ExecutionRecord",
        "Effective Execution Identity",
    )
    for term in glossary_terms:
        check(f"**{term}**:" in texts[ROOT / "CONTEXT.md"], f"missing glossary term: {term}", failures)

    m8_facts = (
        "0/12 accountable",
        "inconclusive",
        "execution-identity-capture",
        "22af9b2",
        "#117",
        "#118–#122",
        "#127",
        "不可重跑",
    )
    for fact in m8_facts:
        check(fact in combined, f"missing immutable M8 fact: {fact}", failures)

    m9_facts = (
        "ProjectTarget",
        "ChangeTarget",
        "regression-only",
        "synchronous critical-path",
        "state-evolution compatibility",
        "lifetime/ownership drift",
        "project-defect",
        "project-control",
        "contradictory",
        "local-only",
        "尚未度量",
    )
    for fact in m9_facts:
        check(fact in combined, f"missing M9 boundary fact: {fact}", failures)

    check("#129" in texts[ROOT / "CONTEXT.md"], "CONTEXT lacks ADR assessment", failures)
    check("不新增 ADR" in combined, "living docs lack explicit no-new-ADR decision", failures)
    check(
        "docs/adr/0003-discovery-campaign-above-run-spec.md" in texts[ROOT / "README.md"],
        "README does not link ADR-0003",
        failures,
    )
    check(
        "尚未进入正式 holdout" in texts[ROOT / "README.md"],
        "README does not state that the M9 holdout has not started",
        failures,
    )

    for document, text in texts.items():
        for target in MARKDOWN_LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            local_target = target.split("#", maxsplit=1)[0]
            check(
                (document.parent / local_target).resolve().exists(),
                f"{document.relative_to(ROOT)}: broken local link {target}",
                failures,
            )

    result = {
        "check": "issue-129-source-of-truth",
        "documents": [str(path.relative_to(ROOT)) for path in LIVING_DOCS],
        "glossary_terms_checked": len(glossary_terms),
        "m8_facts_checked": len(m8_facts),
        "m9_boundary_facts_checked": len(m9_facts),
        "relative_links_checked": sum(
            1
            for document, text in texts.items()
            for target in MARKDOWN_LINK.findall(text)
            if not target.startswith(("http://", "https://", "mailto:", "#"))
        ),
        "status": "passed" if not failures else "failed",
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
