"""Reproduce side-effect-free admission for the frozen M8 manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from aiverify.bench.m8_qualification import admit_qualification


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args()
    result = admit_qualification(args.manifest, repo_root=args.repo_root)
    print(
        json.dumps(
            {
                "admitted": result.admitted,
                "check_count": len(result.checks),
                "lane_count": len(result.lanes),
                "lane_ids": [lane["lane_id"] for lane in result.lanes],
                "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
            },
            sort_keys=True,
        )
    )
    return 0 if result.admitted else 1


if __name__ == "__main__":
    raise SystemExit(main())
