from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from aiverify.bench import runtime_calibration

ROOT = Path(__file__).parents[2]
CANDIDATE = ROOT / "bench/runtime-calibration/opencalc-input-save-enabled-v1"


def _run_cli(output_root: Path, candidate_root: Path = CANDIDATE) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "aiverify.bench.runtime_calibration",
            "verify-candidate",
            "--candidate-root",
            str(candidate_root),
            "--output-root",
            str(output_root),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_verify_candidate_accepts_bundled_v1_through_public_command(tmp_path: Path) -> None:
    output_root = tmp_path / "verification"

    result = _run_cli(output_root)

    assert result.returncode == 0, result.stderr
    receipt = json.loads((output_root / "stage-terminal.json").read_text())
    assert receipt["stage"] == "verify-candidate"
    assert receipt["status"] == "accepted"
    assert receipt["family_id"] == "opencalc-runtime-calibration-v1"
    assert receipt["claim_boundary"] == "candidate_source_of_truth_only"
    assert receipt["artifact_count"] == len(runtime_calibration.EXPECTED_ARTIFACT_KINDS)
    assert [item["kind"] for item in receipt["artifacts"]] == list(
        runtime_calibration.EXPECTED_ARTIFACT_KINDS
    )
    assert all(
        len(item["sha256"]) == 64 and len(item["canonical_sha256"]) == 64
        for item in receipt["artifacts"]
    )
    assert (output_root / "stage-start.json").is_file()


def _copy_candidate(tmp_path: Path) -> Path:
    destination = tmp_path / "candidate-copy"
    shutil.copytree(CANDIDATE, destination)
    return destination


def _terminal(output_root: Path) -> dict[str, object]:
    return json.loads((output_root / "stage-terminal.json").read_text())


def _rebind_manifest(candidate: Path) -> None:
    manifest_path = candidate / "candidate-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for artifact in manifest["artifacts"]:
        artifact_path = candidate / artifact["path"]
        raw = artifact_path.read_bytes()
        artifact["sha256"] = hashlib.sha256(raw).hexdigest()
        artifact["canonical_sha256"] = runtime_calibration.canonical_sha256(
            json.loads(raw)
        )
    manifest["identity_sha256"] = runtime_calibration.canonical_sha256(
        {key: value for key, value in manifest.items() if key != "identity_sha256"}
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        ("missing", "candidate_missing_input"),
        ("extra", "candidate_extra_input"),
        ("drift", "candidate_artifact_digest_mismatch"),
    ),
)
def test_verify_candidate_rejects_incomplete_or_drifted_public_set(
    tmp_path: Path,
    mutation: str,
    reason: str,
) -> None:
    candidate = _copy_candidate(tmp_path)
    if mutation == "missing":
        (candidate / "source-pair.json").unlink()
    elif mutation == "extra":
        (candidate / "unexpected.json").write_text("{}")
    else:
        with (candidate / "claim-boundary.json").open("a") as stream:
            stream.write("\n")

    output_root = tmp_path / "verification"
    result = _run_cli(output_root, candidate)

    assert result.returncode == 1
    assert _terminal(output_root)["reason"] == reason
    assert runtime_calibration.stage_status(output_root) == "rejected"
    assert not runtime_calibration.is_candidate_accepted(output_root)


def test_verify_candidate_rejects_duplicate_manifest_keys_with_stable_reason(
    tmp_path: Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    path = candidate / "candidate-manifest.json"
    raw = path.read_text()
    path.write_text(raw.replace(
        '  "status": "candidate_frozen",',
        '  "status": "candidate_frozen",\n  "status": "candidate_frozen",',
        1,
    ))

    output_root = tmp_path / "verification"
    result = _run_cli(output_root, candidate)

    assert result.returncode == 1
    assert _terminal(output_root)["reason"] == "candidate_duplicate_key"


def test_verify_candidate_rejects_unknown_manifest_field(tmp_path: Path) -> None:
    candidate = _copy_candidate(tmp_path)
    path = candidate / "candidate-manifest.json"
    document = json.loads(path.read_text())
    document["unexpected"] = "not part of V1"
    path.write_text(json.dumps(document, indent=2) + "\n")

    output_root = tmp_path / "verification"
    result = _run_cli(output_root, candidate)

    assert result.returncode == 1
    assert _terminal(output_root)["reason"] == "candidate_unknown_field"


def test_verify_candidate_rejects_rebound_schema_contract(tmp_path: Path) -> None:
    candidate = _copy_candidate(tmp_path)
    path = candidate / "schemas" / "projection.schema.json"
    document = json.loads(path.read_text())
    document["json_schema"]["properties"]["family_id"]["const"] = "v2-family"
    path.write_text(json.dumps(document, indent=2) + "\n")
    _rebind_manifest(candidate)

    output_root = tmp_path / "verification"
    result = _run_cli(output_root, candidate)

    assert result.returncode == 1
    assert _terminal(output_root)["reason"] == "candidate_schema_contract_mismatch"


def test_verify_candidate_rejects_rebound_nested_schema_contract(
    tmp_path: Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    path = candidate / "schemas" / "claim_boundary.schema.json"
    document = json.loads(path.read_text())
    document["json_schema"]["properties"]["scope"]["const"] = "different V1 scope"
    path.write_text(json.dumps(document, indent=2) + "\n")
    _rebind_manifest(candidate)

    output_root = tmp_path / "verification"
    result = _run_cli(output_root, candidate)

    assert result.returncode == 1
    assert _terminal(output_root)["reason"] == "candidate_schema_contract_mismatch"


def test_verify_candidate_rejects_kind_path_rebinding_after_manifest_rebind(
    tmp_path: Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    path = candidate / "candidate-manifest.json"
    document = json.loads(path.read_text())
    document["artifacts"][0]["path"], document["artifacts"][1]["path"] = (
        document["artifacts"][1]["path"],
        document["artifacts"][0]["path"],
    )
    path.write_text(json.dumps(document, indent=2) + "\n")
    _rebind_manifest(candidate)

    output_root = tmp_path / "verification"
    result = _run_cli(output_root, candidate)

    assert result.returncode == 1
    assert _terminal(output_root)["reason"] == "candidate_artifact_set_mismatch"


def test_verify_candidate_rejects_unknown_source_pair_field_after_rebinding(
    tmp_path: Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    path = candidate / "source-pair.json"
    document = json.loads(path.read_text())
    document["unexpected"] = "not part of V1"
    path.write_text(json.dumps(document, indent=2) + "\n")
    _rebind_manifest(candidate)

    output_root = tmp_path / "verification"
    result = _run_cli(output_root, candidate)

    assert result.returncode == 1
    assert _terminal(output_root)["reason"] == "candidate_unknown_field"


def test_verify_candidate_rejects_extra_matched_pair_hunk_after_rebinding(
    tmp_path: Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    path = candidate / "source-pair.json"
    document = json.loads(path.read_text())
    for variant in document["variants"]:
        variant["patch_text"] += "diff --git a/extra b/extra\n"
        variant["patch_sha256"] = hashlib.sha256(
            variant["patch_text"].encode()
        ).hexdigest()
    path.write_text(json.dumps(document, indent=2) + "\n")
    _rebind_manifest(candidate)

    output_root = tmp_path / "verification"
    result = _run_cli(output_root, candidate)

    assert result.returncode == 1
    assert _terminal(output_root)["reason"] == "candidate_patch_context_mismatch"


def test_verify_candidate_rejects_rebound_claim_boundary_semantics(
    tmp_path: Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    path = candidate / "claim-boundary.json"
    document = json.loads(path.read_text())
    document["exclusions"][0] = "different V1 exclusion"
    path.write_text(json.dumps(document, indent=2) + "\n")
    _rebind_manifest(candidate)

    output_root = tmp_path / "verification"
    result = _run_cli(output_root, candidate)

    assert result.returncode == 1
    assert _terminal(output_root)["reason"] == "candidate_claim_boundary_mismatch"


def test_verify_candidate_rejects_reused_v1_contract_id_after_rebinding(
    tmp_path: Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    path = candidate / "family-manifest.json"
    document = json.loads(path.read_text())
    document["preparation_contract_id"] = "different-preparation-v1"
    path.write_text(json.dumps(document, indent=2) + "\n")
    _rebind_manifest(candidate)

    output_root = tmp_path / "verification"
    result = _run_cli(output_root, candidate)

    assert result.returncode == 1
    assert _terminal(output_root)["reason"] == "candidate_input_version_mismatch"


def test_verify_candidate_rejects_contradictory_family_state(tmp_path: Path) -> None:
    candidate = _copy_candidate(tmp_path)
    path = candidate / "candidate-manifest.json"
    document = json.loads(path.read_text())
    document["status"] = "mapping_released"
    document["identity_sha256"] = runtime_calibration.canonical_sha256(
        {key: value for key, value in document.items() if key != "identity_sha256"}
    )
    path.write_text(json.dumps(document, indent=2) + "\n")

    output_root = tmp_path / "verification"
    result = _run_cli(output_root, candidate)

    assert result.returncode == 1
    assert _terminal(output_root)["reason"] == "candidate_input_contradictory"


def test_verify_candidate_rejects_a_changed_family_version_after_identity_rebind(
    tmp_path: Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    path = candidate / "candidate-manifest.json"
    document = json.loads(path.read_text())
    document["family_version"] = "v2"
    document["identity_sha256"] = runtime_calibration.canonical_sha256(
        {key: value for key, value in document.items() if key != "identity_sha256"}
    )
    path.write_text(json.dumps(document, indent=2) + "\n")

    output_root = tmp_path / "verification"
    result = _run_cli(output_root, candidate)

    assert result.returncode == 1
    assert _terminal(output_root)["reason"] == "candidate_input_version_mismatch"


def test_verify_candidate_distinguishes_canonical_digest_drift(tmp_path: Path) -> None:
    candidate = _copy_candidate(tmp_path)
    child = candidate / "claim-boundary.json"
    child.write_text(child.read_text().replace('  "local_only": true,', '  "local_only": false,'))
    child_sha256 = hashlib.sha256(child.read_bytes()).hexdigest()
    manifest_path = candidate / "candidate-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for artifact in manifest["artifacts"]:
        if artifact["path"] == "claim-boundary.json":
            artifact["sha256"] = child_sha256
    manifest["identity_sha256"] = runtime_calibration.canonical_sha256(
        {key: value for key, value in manifest.items() if key != "identity_sha256"}
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    output_root = tmp_path / "verification"
    result = _run_cli(output_root, candidate)

    assert result.returncode == 1
    assert _terminal(output_root)["reason"] == "candidate_canonical_digest_mismatch"


def test_verify_candidate_requires_a_fresh_output_root(tmp_path: Path) -> None:
    output_root = tmp_path / "verification"
    output_root.mkdir()
    (output_root / "old-evidence.json").write_text("{}")

    result = _run_cli(output_root)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.strip() == "stage_output_root_not_empty"
    assert not (output_root / "stage-start.json").exists()


def test_interrupted_started_stage_is_abandoned_and_not_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "verification"

    def interrupt(_candidate_root: str | Path) -> object:
        raise KeyboardInterrupt

    monkeypatch.setattr(runtime_calibration, "verify_candidate_inputs", interrupt)

    with pytest.raises(KeyboardInterrupt):
        runtime_calibration.verify_candidate(CANDIDATE, output_root)

    assert (output_root / "stage-start.json").is_file()
    assert not (output_root / "stage-terminal.json").exists()
    assert runtime_calibration.is_stage_abandoned(output_root)
    assert not runtime_calibration.is_candidate_accepted(output_root)


def test_terminal_receipt_integrity_is_verified_without_accepting_tampering(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "verification"
    result = _run_cli(output_root)
    assert result.returncode == 0

    terminal_path = output_root / "stage-terminal.json"
    terminal = json.loads(terminal_path.read_text())
    terminal["artifact_count"] = 0
    terminal_path.write_text(json.dumps(terminal, indent=2) + "\n")

    assert runtime_calibration.stage_status(output_root) == "invalid"
    assert not runtime_calibration.is_candidate_accepted(output_root)


def test_terminal_receipt_rejects_semantically_rebound_tampering(tmp_path: Path) -> None:
    output_root = tmp_path / "verification"
    result = _run_cli(output_root)
    assert result.returncode == 0

    terminal_path = output_root / "stage-terminal.json"
    terminal = json.loads(terminal_path.read_text())
    terminal["artifact_count"] = 0
    terminal["terminal_identity_sha256"] = runtime_calibration.canonical_sha256(
        {key: value for key, value in terminal.items() if key != "terminal_identity_sha256"}
    )
    terminal_path.write_text(json.dumps(terminal, indent=2) + "\n")

    assert runtime_calibration.stage_status(output_root) == "invalid"
    assert not runtime_calibration.is_candidate_accepted(output_root)


def test_terminal_receipt_rejects_kind_path_rebinding(tmp_path: Path) -> None:
    output_root = tmp_path / "verification"
    result = _run_cli(output_root)
    assert result.returncode == 0

    terminal_path = output_root / "stage-terminal.json"
    terminal = json.loads(terminal_path.read_text())
    terminal["artifacts"][0]["path"], terminal["artifacts"][1]["path"] = (
        terminal["artifacts"][1]["path"],
        terminal["artifacts"][0]["path"],
    )
    terminal["terminal_identity_sha256"] = runtime_calibration.canonical_sha256(
        {key: value for key, value in terminal.items() if key != "terminal_identity_sha256"}
    )
    terminal_path.write_text(json.dumps(terminal, indent=2) + "\n")

    assert runtime_calibration.stage_status(output_root) == "invalid"
    assert not runtime_calibration.is_candidate_accepted(output_root)
