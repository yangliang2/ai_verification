"""Independent deterministic audit for prospective packages and blinding records."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from aiverify.bench.m6_case_package import load_case_package


ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / "docs/runs/2026-08-03-issue-87-prospective-formal"


def raw_counts(path: Path) -> tuple[int, int]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"Tests run:\s*(\d+),\s*Failures:\s*(\d+)", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.search(r"OK \((\d+) tests?\)", text)
    if match:
        return int(match.group(1)), 0
    raise AssertionError(f"unparseable raw instrumentation: {path}")


def main() -> None:
    packages = [load_case_package(path, repo_root=ROOT, verify_references=True) for path in sorted((RUN / "packages").glob("m6-p-0[123].json"))]
    checks: list[dict[str, object]] = []
    checks.append({"name": "three_prospective_packages", "status": "pass" if len(packages) == 3 else "fail", "actual": len(packages), "expected": 3})
    state_counts: Counter[str] = Counter()
    raw_failures: Counter[str] = Counter()
    raw_tests: Counter[str] = Counter()
    conclusions = Counter(package.conclusion for package in packages)
    accountable = 0
    total = 0
    for package in packages:
        attempts = list(package.attempts)
        total += len(attempts)
        accountable += sum(attempt["accountability"] == "accountable" for attempt in attempts)
        state_counts.update(str(attempt["source_state"]) for attempt in attempts)
        for attempt in attempts:
            provenance = json.loads((ROOT / attempt["provenance"]["path"]).read_text(encoding="utf-8"))
            tests, failures = raw_counts(ROOT / provenance["raw_instrumentation"]["path"])
            raw_tests[attempt["source_state"]] += tests
            raw_failures[attempt["source_state"]] += failures
        checks.append({"name": f"{package.slot_id}_six_attempts", "status": "pass" if len(attempts) == 6 else "fail", "actual": len(attempts), "expected": 6})
        checks.append({"name": f"{package.slot_id}_independent_adjudication", "status": "pass" if package.document["verification"]["agent"]["id"] != package.document["adjudication"]["agent"]["id"] and package.document["adjudication"]["agreement"] else "fail"})
    freeze = json.loads((RUN / "candidate-freeze.json").read_text(encoding="utf-8"))
    verifier_sessions = [json.loads((RUN / "verification" / slot / "session.json").read_text(encoding="utf-8")) for slot in ("p-01", "p-02", "p-03")]
    checks.extend([
        {"name": "eighteen_accountable_attempts", "status": "pass" if total == accountable == 18 else "fail", "actual": accountable, "expected": 18},
        {"name": "control_fail_observations", "status": "pass" if state_counts["control"] == 9 and raw_failures["control"] == 9 else "fail", "actual": raw_failures["control"], "expected": 9},
        {"name": "candidate_pass_observations", "status": "pass" if raw_failures["candidate"] == 3 and raw_tests["candidate"] == 9 else "fail", "actual": raw_tests["candidate"] - raw_failures["candidate"], "expected": 6},
        {"name": "candidate_freeze_has_three_commits", "status": "pass" if len(freeze["candidates"]) == 3 and freeze["candidate_access_after_freeze"] is False else "fail", "actual": len(freeze["candidates"]), "expected": 3},
        {"name": "verifier_task_identity_withheld", "status": "pass" if all(session["task_identity_provided"] is False and session["fix_history_provided"] is False and session["network_policy"] == "disabled" for session in verifier_sessions) else "fail"},
        {"name": "adjudicated_conclusions", "status": "pass" if conclusions["locally_supported"] == 2 and conclusions["inconclusive"] == 1 else "fail", "actual": dict(conclusions), "expected": {"locally_supported": 2, "inconclusive": 1}},
        {"name": "local_only_boundary", "status": "pass" if all(package.document["claim_boundary"]["local_only"] for package in packages) else "fail"},
    ])
    status = "pass" if all(check["status"] == "pass" for check in checks) else "fail"
    report = {"schema_version": 1, "audit_id": "m6-prospective-independent-audit-2026-08-03", "auditor": {"id": "independent-auditor-m6-prospective", "role": "final-auditor", "backend": "deterministic-package-audit", "model": "package-contract-v1", "session_id": "audit-session-m6-prospective-2026-08-03"}, "status": status, "scope": {"track": "prospective", "package_count": len(packages), "attempt_count": total}, "counts": {"source_states": dict(sorted(state_counts.items())), "raw_tests": dict(sorted(raw_tests.items())), "raw_failures": dict(sorted(raw_failures.items())), "conclusions": dict(sorted(conclusions.items())), "accountable_attempts": accountable}, "checks": checks, "claim_boundary": {"local_only": True, "note": "Observations are local, blinded-session and package-integrity evidence only."}}
    (RUN / "independent-audit.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# Independent audit — prospective M6 formal packages", "", f"Status: **{status.upper()}**", "", "Auditor: `independent-auditor-m6-prospective`.", "", "| Check | Status | Actual | Expected |", "|---|---|---:|---:|"]
    lines.extend(f"| {check['name']} | {check['status']} | {check.get('actual', '')} | {check.get('expected', '')} |" for check in checks)
    lines.extend(["", "The report is local-only; P-03 is explicitly adjudicated inconclusive because its frozen oracle contradicts its own dual-lifecycle precondition.", ""])
    (RUN / "independent-audit.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
