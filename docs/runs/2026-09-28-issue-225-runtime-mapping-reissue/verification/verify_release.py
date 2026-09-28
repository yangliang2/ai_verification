"""Issue #225 release verification: capture independent evidence for the reissue.

Run from the repository root:

    env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python \
        docs/runs/2026-09-28-issue-225-runtime-mapping-reissue/verification/verify_release.py
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess

from aiverify.bench import runtime_family_preparation, runtime_mapping as rm

RUN = pathlib.Path("docs/runs/2026-09-28-issue-225-runtime-mapping-reissue")
STAGE = RUN / "verification/family-stage-final"
CANDIDATE = "bench/runtime-calibration/opencalc-input-save-enabled-v1"
V1_STAGE = (
    pathlib.Path("docs/runs/2026-08-29-issue-206-runtime-mapping-release")
    / "verification/family-stage-final"
)


def git(root: pathlib.Path | str, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> None:
    release_path = STAGE / "mapping-release.json"
    raw = release_path.read_bytes()
    release = rm.load_runtime_mapping_release(release_path)

    worktrees = [lane.source_request.worktree_path for lane in release.lanes]
    pairwise_independent = all(
        not runtime_family_preparation._is_overlapping(
            pathlib.Path(first), pathlib.Path(second)
        )
        for index, first in enumerate(worktrees)
        for second in worktrees[index + 1 :]
    )
    old_release = rm.load_runtime_mapping_release(V1_STAGE / "mapping-release.json")
    old_worktrees = [
        lane.source_request.worktree_path for lane in old_release.lanes
    ]
    lanes: dict[str, dict[str, str]] = {}
    for lane in release.lanes:
        request = lane.source_request
        worktree = pathlib.Path(request.worktree_path)
        lanes[lane.lane_id] = {
            "worktree": str(worktree),
            "materialization_kind": request.materialization_kind,
            "source_commit": request.source_commit,
            "baseline_commit": request.baseline_commit,
            "baseline_tree_sha256": request.baseline_tree_sha256,
            "materialized_tree_sha256": request.materialized_tree_sha256,
            "materialization_receipt_identity_sha256": (
                request.materialization_receipt_identity_sha256 or ""
            ),
            "result_diff_sha256": request.result_diff_sha256 or "",
            "head": git(worktree, "rev-parse", "HEAD"),
            "tree": git(worktree, "rev-parse", "HEAD^{tree}"),
            "origin": git(worktree, "remote", "get-url", "origin"),
            "status": git(
                worktree, "status", "--porcelain=v1", "--untracked-files=all"
            ),
            "request_id": request.request_id,
        }

    evidence = {
        "issue": 225,
        "release_id": release.release_id,
        "release_identity_sha256": release.identity_sha256,
        "release_file_sha256": hashlib.sha256(raw).hexdigest(),
        "stage_status": rm.stage_status(STAGE),
        "verify_runtime_mapping_release_against_candidate": (
            rm.verify_runtime_mapping_release(release, candidate_root=CANDIDATE)
        ),
        "lane_ids": list(release.lane_ids),
        "distinct_worktree_count": len(set(worktrees)),
        "change_worktrees": worktrees[:2],
        "v2_pairwise_independent_under_family_gate": pairwise_independent,
        "v1_release_id": old_release.release_id,
        "v1_lane_01_02_worktrees": old_worktrees[:2],
        "v1_lane_01_02_overlapping_under_family_gate": (
            runtime_family_preparation._is_overlapping(
                pathlib.Path(old_worktrees[0]),
                pathlib.Path(old_worktrees[1]),
            )
        ),
        "lanes": lanes,
        "documented_host_checkout_status": git(
            pathlib.Path.home() / "hosts/opencalc-calibration",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ),
        "repository_head": git(".", "rev-parse", "HEAD"),
        "repository_dirty_entries": git(".", "status", "--porcelain=v1"),
    }
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
