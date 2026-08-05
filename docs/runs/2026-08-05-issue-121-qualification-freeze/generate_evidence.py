"""Regenerate the committed M8 #121 admission and leakage evidence."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

RUN_ROOT = Path(__file__).resolve().parent
REPO_ROOT = RUN_ROOT.parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aiverify.bench.m8_qualification import (
    admit_qualification,
    load_manifest,
)

MANIFEST = REPO_ROOT / "bench/m8/m8-state-evolution-qualification-v1.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(name: str, value: object) -> None:
    (RUN_ROOT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def main() -> None:
    started = time.perf_counter()
    manifest = load_manifest(MANIFEST)
    preflight = admit_qualification(MANIFEST, repo_root=REPO_ROOT)
    if not preflight.admitted:
        raise SystemExit("M8 #121 preflight was not admitted")

    _write_json("preflight.json", preflight.to_dict())
    _write_json("leakage-audit.json", preflight.leakage_audit)
    _write_json("contradiction-audit.json", preflight.contradiction_audit)
    _write_json(
        "manifest-identity.json",
        {
            "manifest_path": "bench/m8/m8-state-evolution-qualification-v1.json",
            "manifest_sha256": manifest.source_sha256,
            "canonical_manifest_sha256": manifest.canonical_sha256,
            "source_commit": manifest.document["source_identity"]["source_commit"],
            "preflight_commit": _git("rev-parse", "HEAD"),
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "duration_seconds": round(time.perf_counter() - started, 6),
            "side_effects": False,
            "formal_execution_started": False,
        },
    )
    inventory = sorted(
        path
        for path in RUN_ROOT.rglob("*")
        if path.is_file() and path.name != "checksums.sha256"
    )
    (RUN_ROOT / "checksums.sha256").write_text(
        "".join(
            f"{_sha256(path)}  {path.relative_to(RUN_ROOT).as_posix()}\n"
            for path in inventory
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "admitted": preflight.admitted,
                "lanes": len(preflight.lanes),
                "leakage": preflight.leakage_audit["status"],
                "contradictions": preflight.contradiction_audit["status"],
                "duration_seconds": round(time.perf_counter() - started, 6),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
