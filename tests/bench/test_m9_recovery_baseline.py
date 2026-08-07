from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "docs/runs/2026-08-07-issue-148-m9-r1-recovery-baseline"


def _load(name: str) -> dict:
    return json.loads((RUN / name).read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_recovery_baseline_is_explicitly_canary_only() -> None:
    baseline = _load("recovery-baseline.json")

    assert baseline["status"] == "passed"
    assert baseline["boundary"] == {
        "classification": "historical_fixture_recovered_for_non_holdout_canary_only",
        "canary_eligible": True,
        "formal_qualification_eligible": False,
        "frozen_136_137_cohort_rerun": False,
        "permitted_next_use": "R2 full-chain canary only",
        "forbidden_uses": [
            "R3 qualification packet",
            "R4 formal lanes",
            "M9 Supported conclusion",
        ],
    }


def test_recovery_recipe_is_bound_to_committed_source_and_patch() -> None:
    baseline = _load("recovery-baseline.json")
    source = ROOT / baseline["source_contract"]["path"]
    patch = ROOT / baseline["recovery_recipe"]["patch"]["path"]

    assert _sha256(source) == baseline["source_contract"]["sha256"]
    assert _sha256(patch) == baseline["recovery_recipe"]["patch"]["sha256"]
    assert baseline["target"]["base_commit"] == (
        "ee66e1526b84c026615df032c705842b7d2a521f"
    )
    assert baseline["target"]["base_tree"] == (
        "19455e693ec8c96c37a56aec55059a220826c5a3"
    )
    assert baseline["variants"]["defect"]["index_tree"] == (
        "34998af23aed59aa17eaf915d848ab1b916a63e2"
    )


def test_rebuilt_canary_apk_identities_match_the_frozen_historical_values() -> None:
    baseline = _load("recovery-baseline.json")

    assert baseline["variants"]["control"]["apk"] == {
        "path": (
            "/private/tmp/m9-r1-canary-recovery/control/"
            "app/build/outputs/apk/debug/app-debug.apk"
        ),
        "bytes": 24681606,
        "sha256": "d38b30f17010da114b5585dadec8326eb76b04dfbae4a175f7cb2840a0093c66",
        "matches_frozen_canary_identity": True,
    }
    assert baseline["variants"]["defect"]["apk"] == {
        "path": (
            "/private/tmp/m9-r1-canary-recovery/defect/"
            "app/build/outputs/apk/debug/app-debug.apk"
        ),
        "bytes": 24681461,
        "sha256": "61063a0fd247eb03d1bd251b0d9359c3c2a5ea07cb8abe4b38d3daae57c153ac",
        "matches_frozen_canary_identity": True,
    }


def test_diagnosis_preserves_the_frozen_failed_population() -> None:
    diagnosis = _load("diagnosis.json")
    live = _load("package-reset-live.json")

    assert diagnosis["historical_failure"]["accountable_lanes"] == 0
    assert diagnosis["frozen_136_137_evidence_modified"] is False
    assert diagnosis["frozen_cohort_rerun"] is False
    assert live["status"] == "already_absent"
    assert live["clear_performed"] is False
    assert live["presence_query"]["returncode"] == 1
    assert live["presence_query"]["stdout"] == ""
    assert live["presence_query"]["stderr"] == ""


def test_run_record_checksum_inventory_is_complete_and_verifies() -> None:
    checksum_path = RUN / "checksums.sha256"
    entries: dict[str, str] = {}
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ", 1)
        entries[relative] = digest

    expected = {
        path.name
        for path in RUN.iterdir()
        if path.is_file() and path.name != "checksums.sha256"
    }
    assert set(entries) == expected
    assert all(_sha256(RUN / relative) == digest for relative, digest in entries.items())
