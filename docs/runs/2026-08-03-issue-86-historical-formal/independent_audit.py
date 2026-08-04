"""Independent, deterministic audit for the formal historical packages."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from aiverify.bench.m6_case_package import load_case_package


ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / "docs/runs/2026-08-03-issue-86-historical-formal"
PACKAGE_ROOT = RUN / "packages"


def main() -> None:
    checks: list[dict[str, object]] = []
    packages = [
        load_case_package(path, repo_root=ROOT, verify_references=True)
        for path in sorted(PACKAGE_ROOT.glob("m6-h-*.json"))
    ]
    checks.append({"name": "three_historical_packages", "status": "pass" if len(packages) == 3 else "fail", "actual": len(packages), "expected": 3})
    total_attempts = 0
    accountable = 0
    state_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    raw_tests: Counter[str] = Counter()
    raw_failures: Counter[str] = Counter()
    revision_bindings: list[dict[str, str]] = []
    for package in packages:
        attempts = list(package.attempts)
        total_attempts += len(attempts)
        accountable += sum(attempt["accountability"] == "accountable" for attempt in attempts)
        state_counts.update(str(attempt["source_state"]) for attempt in attempts)
        for attempt in attempts:
            verdict_path = ROOT / attempt["verdict"]["path"]
            verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
            outcome_counts[str(verdict["outcome"])] += 1
            provenance = json.loads((ROOT / attempt["provenance"]["path"]).read_text(encoding="utf-8"))
            revision_bindings.append({"attempt_id": attempt["attempt_id"], "source_state": attempt["source_state"], "source_revision": provenance["source_revision"]})
            raw_path = ROOT / provenance["raw_instrumentation"]["path"]
            raw_text = raw_path.read_text(encoding="utf-8")
            counts = re.search(r"Tests run:\s*(\d+),\s*Failures:\s*(\d+)", raw_text)
            if counts:
                tests, failures = (int(counts.group(1)), int(counts.group(2)))
            else:
                ok = re.search(r"OK \((\d+) tests?\)", raw_text)
                if not ok:
                    raise AssertionError(f"unparseable raw instrumentation: {raw_path}")
                tests, failures = int(ok.group(1)), 0
            raw_tests[str(attempt["source_state"])] += tests
            raw_failures[str(attempt["source_state"])] += failures
        checks.append({"name": f"{package.slot_id}_six_attempts", "status": "pass" if len(attempts) == 6 else "fail", "actual": len(attempts), "expected": 6})
        checks.append({"name": f"{package.slot_id}_independent_adjudication", "status": "pass" if package.document["verification"]["agent"]["id"] != package.document["adjudication"]["agent"]["id"] and package.document["adjudication"]["agreement"] else "fail"})
    checks.extend(
        [
            {"name": "eighteen_accountable_attempts", "status": "pass" if total_attempts == accountable == 18 else "fail", "actual": accountable, "expected": 18},
            {"name": "three_pre_fix_fail_observations", "status": "pass" if state_counts["pre_fix"] == outcome_counts["fail"] == 9 else "fail", "actual": outcome_counts["fail"], "expected": 9},
            {"name": "three_fixed_pass_observations", "status": "pass" if state_counts["fixed"] == outcome_counts["pass"] == 9 else "fail", "actual": outcome_counts["pass"], "expected": 9},
            {"name": "raw_pre_fix_assertion_failures", "status": "pass" if raw_failures["pre_fix"] == 15 else "fail", "actual": raw_failures["pre_fix"], "expected": 15},
            {"name": "raw_fixed_failures", "status": "pass" if raw_failures["fixed"] == 0 else "fail", "actual": raw_failures["fixed"], "expected": 0},
            {"name": "no_non_accountable_attempts", "status": "pass" if total_attempts == accountable else "fail"},
            {"name": "local_only_boundary", "status": "pass" if all(package.document["claim_boundary"]["local_only"] for package in packages) else "fail"},
        ]
    )
    status = "pass" if all(check["status"] == "pass" for check in checks) else "fail"
    report = {
        "schema_version": 1,
        "audit_id": "m6-historical-independent-audit-2026-08-03",
        "auditor": {"id": "independent-auditor-m6-historical", "role": "final-auditor", "backend": "deterministic-package-audit", "model": "package-contract-v1", "session_id": "audit-session-m6-historical-2026-08-03"},
        "status": status,
        "scope": {"track": "historical", "package_count": len(packages), "attempt_count": total_attempts, "source_repository": "https://github.com/wikimedia/apps-android-wikipedia"},
        "counts": {"source_states": dict(sorted(state_counts.items())), "outcomes": dict(sorted(outcome_counts.items())), "raw_tests": dict(sorted(raw_tests.items())), "raw_failures": dict(sorted(raw_failures.items())), "accountable_attempts": accountable},
        "checks": checks,
        "revision_bindings": revision_bindings,
        "claim_boundary": {"local_only": True, "note": "This audit records local matched observations and package integrity only."},
    }
    (RUN / "independent-audit.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Independent audit — historical M6 formal packages",
        "",
        f"Status: **{status.upper()}**",
        "",
        "Auditor: `independent-auditor-m6-historical` (separate from all verification agents).",
        "",
        "| Check | Status | Actual | Expected |",
        "|---|---|---:|---:|",
    ]
    for check in checks:
        lines.append(f"| {check['name']} | {check['status']} | {check.get('actual', '')} | {check.get('expected', '')} |")
    lines.extend(["", "The report is local-only and does not make an upstream or generalized coverage claim.", ""])
    (RUN / "independent-audit.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
