"""Extract the failed-case set of one pytest junitxml report as sorted lines."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: extract_failures.py <junitxml> <output.txt>", file=sys.stderr)
        return 2
    report = Path(sys.argv[1])
    output = Path(sys.argv[2])
    root = ET.parse(report).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    lines: list[str] = []
    for suite in suites:
        for case in suite.iter("testcase"):
            outcomes = [
                child
                for child in case
                if child.tag in {"failure", "error"}
            ]
            if not outcomes:
                continue
            classname = case.get("classname") or ""
            name = case.get("name") or ""
            lines.append(f"{classname}::{name}")
    output.write_text("\n".join(sorted(lines)) + ("\n" if lines else ""), encoding="utf-8")
    print(f"{report.name}: {len(lines)} failed cases -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
