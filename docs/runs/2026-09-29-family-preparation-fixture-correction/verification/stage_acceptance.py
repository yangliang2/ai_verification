"""Record why the committed issue-206 stage cannot be a local predecessor.

Prints, for both committed ``admit-family`` staging roots, the structural
verdict of ``runtime_mapping.stage_status`` (the check
``runtime_family_preparation._load_mapping_predecessor`` applies), the
``candidate_root`` each terminal records, and whether it equals the local
candidate root the gates compare against.
"""

from __future__ import annotations

import json
from pathlib import Path

from aiverify.bench import runtime_mapping

REPO = Path(__file__).resolve().parents[4]
CANDIDATE = REPO / "bench/runtime-calibration/opencalc-input-save-enabled-v1"
STAGES = {
    "issue-206-v1": (
        REPO
        / "docs/runs/2026-08-29-issue-206-runtime-mapping-release"
        / "verification/family-stage-final"
    ),
    "issue-225-v2": (
        REPO
        / "docs/runs/2026-09-28-issue-225-runtime-mapping-reissue"
        / "verification/family-stage-final"
    ),
}


def main() -> int:
    print(f"local candidate_root: {CANDIDATE}")
    for name, root in STAGES.items():
        terminal = json.loads(
            (root / "stage-terminal.json").read_text(encoding="utf-8")
        )
        release = json.loads(
            (root / "mapping-release.json").read_text(encoding="utf-8")
        )
        print(f"{name}: stage_status={runtime_mapping.stage_status(root)}")
        print(f"  recorded candidate_root: {terminal.get('candidate_root')}")
        print(
            "  candidate_root matches local: "
            f"{terminal.get('candidate_root') == str(CANDIDATE)}"
        )
        print(f"  release_id: {release.get('release_id')}")
        print(f"  release identity_sha256: {release.get('identity_sha256')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
