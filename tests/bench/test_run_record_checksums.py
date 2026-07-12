from pathlib import Path

from aiverify.bench.run_record_checksums import verify_manifest, write_manifest


def test_checksum_manifest_excludes_itself_and_verifies_intact_record(tmp_path: Path) -> None:
    (tmp_path / "artifact.txt").write_text("evidence", encoding="utf-8")
    manifest = write_manifest(tmp_path)

    assert "checksums.sha256" not in manifest.read_text(encoding="utf-8")
    assert verify_manifest(tmp_path) == []


def test_checksum_verification_reports_changed_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("evidence", encoding="utf-8")
    write_manifest(tmp_path)
    artifact.write_text("changed", encoding="utf-8")

    assert verify_manifest(tmp_path) == ["checksum mismatch: artifact.txt"]
