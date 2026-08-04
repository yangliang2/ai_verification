"""Independent final audit of the committed M6 aggregate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from aiverify.bench.m6_case_package import (
    CasePackageValidationError,
    aggregate_packages,
    render_markdown,
    render_structured,
)


ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / "docs/runs/2026-08-03-issue-88-aggregate"
MANIFEST = ROOT / "bench/m6/m6-qualification-v1.yaml"
PACKAGES = tuple(
    ROOT / path
    for path in (
        "docs/runs/2026-08-03-issue-86-historical-formal/packages/m6-h-01.json",
        "docs/runs/2026-08-03-issue-86-historical-formal/packages/m6-h-02.json",
        "docs/runs/2026-08-03-issue-86-historical-formal/packages/m6-h-03.json",
        "docs/runs/2026-08-03-issue-87-prospective-formal/packages/m6-p-01.json",
        "docs/runs/2026-08-03-issue-87-prospective-formal/packages/m6-p-02.json",
        "docs/runs/2026-08-03-issue-87-prospective-formal/packages/m6-p-03.json",
    )
)
FORBIDDEN = (
    "detection_rate",
    "false_positive_rate",
    "confidence",
    "goldset",
    "general_android",
    "upstream_acceptance",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    checks: list[dict[str, object]] = []

    def check(name: str, condition: bool, actual: object = None, expected: object = None) -> None:
        checks.append(
            {
                "name": name,
                "status": "pass" if condition else "fail",
                "actual": actual,
                "expected": expected,
            }
        )

    try:
        aggregate = aggregate_packages(
            PACKAGES,
            manifest_path=MANIFEST,
            repo_root=ROOT,
            verify_references=True,
        )
    except (CasePackageValidationError, OSError, ValueError) as error:
        report = {
            "schema_version": 1,
            "audit_id": "m6-aggregate-independent-audit-2026-08-03",
            "auditor": {
                "id": "independent-verification-agent-m6-aggregate",
                "role": "final-auditor",
                "backend": "deterministic-package-audit",
                "model": "aggregate-contract-v1",
                "session_id": "audit-session-m6-aggregate-2026-08-03",
            },
            "status": "fail",
            "error": str(error),
            "claim_boundary": {"local_only": True},
        }
        (RUN / "independent-audit.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (RUN / "independent-audit.md").write_text(
            "# Independent aggregate audit\n\nStatus: **FAIL**\n\n" + str(error) + "\n",
            encoding="utf-8",
        )
        return 1

    model = aggregate.to_dict()
    json_path = RUN / "aggregate.json"
    markdown_path = RUN / "aggregate.md"
    regen_json = render_structured(aggregate)
    regen_markdown = render_markdown(aggregate)
    check("six_packages_loaded", len(aggregate.packages) == 6, len(aggregate.packages), 6)
    check("package_checksums_verified", model["checksums_verified"] is True)
    check("thirty_six_lanes", model["qualification"]["observed_lanes"] == 36, model["qualification"]["observed_lanes"], 36)
    check("eventual_accountability", model["qualification"]["eventual_accountable"] == 36, model["qualification"]["eventual_accountable"], 36)
    check("historical_pair_observations", model["historical"]["source_states"].get("pre_fix", {}).get("outcomes") == {"fail": 9} and model["historical"]["source_states"].get("fixed", {}).get("outcomes") == {"pass": 9})
    check("prospective_conclusions", model["prospective"]["conclusions"] == {"inconclusive": 1, "locally_supported": 2}, model["prospective"]["conclusions"], {"inconclusive": 1, "locally_supported": 2})
    check("adjudications_agree", model["qualification"]["adjudication_disagreements"] == 0)
    check("provenance_complete", model["qualification"]["complete_provenance"] is True)
    check("single_route", set(model["recommendation"]) >= {"route"} and model["recommendation"]["route"] in {
        "scale_historical_pair_cohort",
        "add_accountable_prospective_cases",
        "remediate_fixture_execution_oracle_adjudication_gaps",
        "stop_or_defer",
    })
    check("route_matches_frozen_gap", model["recommendation"]["route"] == "remediate_fixture_execution_oracle_adjudication_gaps")
    check("route_is_local_only", model["recommendation"]["local_only"] is True)
    check("json_regenerates_byte_for_byte", json_path.read_text(encoding="utf-8") == regen_json)
    check("markdown_regenerates_byte_for_byte", markdown_path.read_text(encoding="utf-8") == regen_markdown)
    rendered = regen_json + regen_markdown
    check("claim_boundary_is_clean", not any(term in rendered.lower() for term in FORBIDDEN))
    package_hashes = [sha256(path) for path in PACKAGES]
    report_hashes = [item["source_sha256"] for item in model["packages"]]
    check("package_hash_inventory", sorted(package_hashes) == sorted(report_hashes))
    attempt_ids = [attempt["attempt_id"] for package in aggregate.packages for attempt in package.attempts]
    lane_ids = [attempt["lane_id"] for package in aggregate.packages for attempt in package.attempts]
    check("attempt_ids_unique", len(attempt_ids) == len(set(attempt_ids)), len(attempt_ids), len(set(attempt_ids)))
    check("lane_ids_unique", len(lane_ids) == len(set(lane_ids)), len(lane_ids), len(set(lane_ids)))

    status = "pass" if all(item["status"] == "pass" for item in checks) else "fail"
    report = {
        "schema_version": 1,
        "audit_id": "m6-aggregate-independent-audit-2026-08-03",
        "auditor": {
            "id": "independent-verification-agent-m6-aggregate",
            "role": "final-auditor",
            "backend": "deterministic-package-audit",
            "model": "aggregate-contract-v1",
            "session_id": "audit-session-m6-aggregate-2026-08-03",
        },
        "status": status,
        "scope": {
            "manifest": MANIFEST.relative_to(ROOT).as_posix(),
            "packages": [path.relative_to(ROOT).as_posix() for path in PACKAGES],
            "lanes": model["qualification"]["observed_lanes"],
        },
        "checks": checks,
        "artifacts": {
            "aggregate_json_sha256": sha256(json_path),
            "aggregate_markdown_sha256": sha256(markdown_path),
            "package_sha256": {
                path.relative_to(ROOT).as_posix(): sha256(path) for path in PACKAGES
            },
        },
        "recommendation": model["recommendation"],
        "claim_boundary": {"local_only": True},
    }
    (RUN / "independent-audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Independent aggregate audit",
        "",
        f"Status: **{status.upper()}**",
        "",
        "Auditor: `independent-verification-agent-m6-aggregate`.",
        "",
        "| Check | Status | Actual | Expected |",
        "|---|---|---|---|",
    ]
    lines.extend(
        f"| {item['name']} | {item['status']} | {item.get('actual', '')} | {item.get('expected', '')} |"
        for item in checks
    )
    lines.extend(
        [
            "",
            "The aggregate is local-only. The selected route is remediation because P-03 is adjudicated inconclusive against its frozen oracle contract.",
            "",
        ]
    )
    (RUN / "independent-audit.md").write_text("\n".join(lines), encoding="utf-8")
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
