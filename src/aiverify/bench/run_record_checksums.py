"""Generate and verify deterministic SHA-256 run-record inventories."""

from __future__ import annotations

import argparse
import hashlib
import re
from collections import Counter
from pathlib import Path


_MANIFEST = "checksums.sha256"


def write_manifest(run_record: Path) -> Path:
    """Write checksums for every file below a run record except the manifest."""
    run_record = Path(run_record)
    manifest = run_record / _MANIFEST
    lines = [
        f"{_sha256(path)}  {path.relative_to(run_record).as_posix()}"
        for path in sorted(run_record.rglob("*"))
        if path.is_file() and path != manifest
    ]
    manifest.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return manifest


def verify_manifest(run_record: Path) -> list[str]:
    """Return human-readable inventory verification errors."""
    run_record = Path(run_record)
    manifest = run_record / _MANIFEST
    if not manifest.is_file():
        return [f"missing manifest: {_MANIFEST}"]
    errors: list[str] = []
    listed: list[str] = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            errors.append(f"malformed manifest entry: {line}")
            continue
        digest, relative = match.groups()
        listed.append(relative)
        candidate = Path(relative)
        path = (run_record / candidate).resolve()
        if candidate.is_absolute() or not path.is_relative_to(run_record.resolve()):
            errors.append(f"artifact outside run record: {relative}")
            continue
        if not path.is_file():
            errors.append(f"missing artifact: {relative}")
        elif _sha256(path) != digest:
            errors.append(f"checksum mismatch: {relative}")
    errors.extend(
        f"duplicate manifest entry: {relative}"
        for relative, count in sorted(Counter(listed).items())
        if count > 1
    )
    actual = {
        path.relative_to(run_record).as_posix()
        for path in run_record.rglob("*")
        if path.is_file() and path != manifest
    }
    errors.extend(
        f"unlisted artifact: {relative}" for relative in sorted(actual - set(listed))
    )
    return errors


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_record", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if args.verify:
        errors = verify_manifest(args.run_record)
        if errors:
            print("\n".join(errors))
            return 1
        print("checksum inventory verified")
        return 0
    print(write_manifest(args.run_record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
