"""Deterministic M0.1 tests for disposable Injection Lab materialization."""

from __future__ import annotations

from dataclasses import replace
import difflib
import json
from pathlib import Path
import subprocess

import pytest

from aiverify.injection import (
    FaultOperator,
    InjectionCandidate,
    InjectionCleanupError,
    InjectionMaterializer,
    InjectionMaterializerError,
    InjectionReceipt,
    SourceDelta,
    capture_baseline_provenance,
    source_tree_sha256_from_worktree,
)


def _git(
    repository: Path,
    *arguments: str,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        input=input_text,
        text=True,
        capture_output=True,
        check=check,
    )


def _init_repository(base: Path, name: str = "caller") -> Path:
    repository = base / name
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.email", "test@example.invalid")
    _git(repository, "config", "user.name", "Injection Lab Test")
    _git(repository, "remote", "add", "origin", "https://example.invalid/injection-fixture.git")
    (repository / "source.txt").write_text("baseline\n", encoding="utf-8")
    (repository / "nested").mkdir()
    (repository / "nested" / "keep.txt").write_text("keep\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "baseline")
    return repository


def _candidate(repository: Path, *, patch_text: str | None = None) -> InjectionCandidate:
    commit = _git(repository, "rev-parse", "HEAD").stdout.strip()
    if patch_text is None:
        patch_text = "".join(
            difflib.unified_diff(
                ["baseline\n"],
                ["candidate\n"],
                fromfile="a/source.txt",
                tofile="b/source.txt",
            )
        )
    return InjectionCandidate(
        candidate_id="curated-fixture-candidate",
        baseline=capture_baseline_provenance(repository, commit),
        source_delta=SourceDelta.from_patch(
            delta_id="curated-fixture-delta",
            patch_text=patch_text,
            source_ref="fixtures/curated-fixture.patch",
        ),
        operator=FaultOperator(
            operator_id="curated-unified-diff",
            version="v1",
            applicability="declared fixture source only",
            safety_boundary="one detached disposable worktree",
        ),
    )


def _dirty_caller(repository: Path) -> None:
    (repository / "source.txt").write_text("staged caller content\n", encoding="utf-8")
    _git(repository, "add", "source.txt")
    (repository / "source.txt").write_text("unstaged caller content\n", encoding="utf-8")
    (repository / "caller-untracked.txt").write_text("do not touch\n", encoding="utf-8")


def _caller_snapshot(repository: Path) -> dict[str, str]:
    return {
        "head": _git(repository, "rev-parse", "HEAD").stdout,
        "status": _git(repository, "status", "--porcelain=v1", "-z").stdout,
        "index_tree": _git(repository, "write-tree").stdout,
        "source": (repository / "source.txt").read_text(encoding="utf-8"),
        "untracked": (repository / "caller-untracked.txt").read_text(encoding="utf-8"),
    }


def test_materializes_one_delta_in_a_detached_owned_worktree_without_touching_caller(
    tmp_path: Path,
) -> None:
    repository = _init_repository(tmp_path)
    candidate = _candidate(repository)
    _dirty_caller(repository)
    before = _caller_snapshot(repository)
    materializer = InjectionMaterializer(repository, tmp_path / "owned-worktrees")

    receipt = materializer.materialize(candidate)

    assert receipt.outcome == "materialized"
    assert receipt.rejection_code is None
    assert receipt.candidate_identity_sha256 == candidate.identity_sha256
    assert receipt.baseline_identity_sha256 == candidate.baseline.identity_sha256
    assert receipt.patch_identity_sha256 == candidate.source_delta.identity_sha256
    assert receipt.worktree is not None
    worktree = Path(receipt.worktree.path)
    assert worktree.parent == (tmp_path / "owned-worktrees").resolve()
    assert (worktree / "source.txt").read_text(encoding="utf-8") == "candidate\n"
    assert _git(worktree, "rev-parse", "HEAD").stdout.strip() == candidate.baseline.commit
    assert _git(worktree, "symbolic-ref", "-q", "HEAD", check=False).returncode != 0
    assert source_tree_sha256_from_worktree(worktree) == receipt.result_source_tree_sha256
    assert InjectionReceipt.from_dict(receipt.to_dict()) == receipt
    assert _caller_snapshot(repository) == before

    materializer.cleanup(receipt)

    assert not worktree.exists()
    assert _caller_snapshot(repository) == before

    regenerated = materializer.materialize(candidate)
    assert regenerated.outcome == "materialized"
    assert regenerated.receipt_identity_sha256 == receipt.receipt_identity_sha256
    assert regenerated.result_identity_sha256 == receipt.result_identity_sha256
    assert regenerated.worktree is not None
    assert regenerated.worktree.path != receipt.worktree.path
    materializer.cleanup(regenerated)


def test_non_applicable_patch_returns_a_stable_rejection_and_leaves_no_worktree(
    tmp_path: Path,
) -> None:
    repository = _init_repository(tmp_path)
    candidate = _candidate(
        repository,
        patch_text=(
            "--- a/source.txt\n"
            "+++ b/source.txt\n"
            "@@ -1 +1 @@\n"
            "-not-the-baseline\n"
            "+candidate\n"
        ),
    )
    _dirty_caller(repository)
    before = _caller_snapshot(repository)
    root = tmp_path / "owned-worktrees"
    materializer = InjectionMaterializer(repository, root)

    first = materializer.materialize(candidate)
    second = materializer.materialize(candidate)

    assert first.outcome == "rejected"
    assert first.rejection_code == "patch_not_applicable"
    assert first.worktree is None
    assert first.to_dict() == second.to_dict()
    assert not any(root.iterdir())
    assert _caller_snapshot(repository) == before


def test_provenance_mismatch_rejects_before_creating_a_worktree(tmp_path: Path) -> None:
    repository = _init_repository(tmp_path)
    candidate = _candidate(repository)
    mismatched = replace(
        candidate,
        baseline=replace(candidate.baseline, source_tree_sha256="0" * 64),
    )
    _dirty_caller(repository)
    before = _caller_snapshot(repository)
    root = tmp_path / "owned-worktrees"

    receipt = InjectionMaterializer(repository, root).materialize(mismatched)

    assert receipt.outcome == "rejected"
    assert receipt.rejection_code == "baseline_tree_mismatch"
    assert receipt.worktree is None
    assert not root.exists()
    assert _caller_snapshot(repository) == before


def test_malformed_candidate_mapping_returns_a_stable_rejection(tmp_path: Path) -> None:
    repository = _init_repository(tmp_path)
    materializer = InjectionMaterializer(repository, tmp_path / "owned-worktrees")

    first = materializer.materialize({"schema_version": 1})
    second = materializer.materialize({"schema_version": 1})

    assert first.outcome == "rejected"
    assert first.rejection_code == "invalid_candidate"
    assert first.candidate_identity_sha256 is None
    assert first.to_dict() == second.to_dict()


def test_cleanup_refuses_a_tampered_receipt_pointing_at_an_existing_checkout(
    tmp_path: Path,
) -> None:
    repository = _init_repository(tmp_path)
    root = tmp_path / "owned-worktrees"
    root.mkdir()
    foreign = _init_repository(root, "foreign")
    materializer = InjectionMaterializer(repository, root)
    receipt = materializer.materialize(_candidate(repository))
    assert receipt.worktree is not None
    foreign_head = _git(foreign, "rev-parse", "HEAD").stdout
    tampered_worktree = replace(receipt.worktree, path=str(foreign.resolve()))
    tampered_receipt = replace(receipt, worktree=tampered_worktree)

    with pytest.raises(InjectionCleanupError, match="owned worktree marker"):
        materializer.cleanup(tampered_receipt)

    assert foreign.is_dir()
    assert _git(foreign, "rev-parse", "HEAD").stdout == foreign_head
    materializer.cleanup(receipt)


def test_cleanup_refuses_a_forged_receipt_for_an_existing_linked_worktree(
    tmp_path: Path,
) -> None:
    repository = _init_repository(tmp_path)
    root = tmp_path / "owned-worktrees"
    materializer = InjectionMaterializer(repository, root)
    candidate = _candidate(repository)
    receipt = materializer.materialize(candidate)
    assert receipt.worktree is not None

    foreign = root / "existing-linked-worktree"
    _git(repository, "worktree", "add", "--detach", str(foreign), candidate.baseline.commit)
    _git(
        foreign,
        "apply",
        "--whitespace=nowarn",
        "-",
        input_text=candidate.source_delta.patch_text,
    )
    forged_worktree = replace(receipt.worktree, path=str(foreign.resolve()))
    forged_receipt = replace(receipt, worktree=forged_worktree)
    (foreign / ".aiverify-injection-ownership.json").write_bytes(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "aiverify-injection-owned-worktree",
                "ownership_token": forged_worktree.ownership_token,
                "candidate_identity_sha256": forged_worktree.candidate_identity_sha256,
                "baseline_commit": forged_worktree.baseline_commit,
                "result_identity_sha256": forged_worktree.result_identity_sha256,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )

    with pytest.raises(InjectionCleanupError, match="created by this materializer"):
        materializer.cleanup(forged_receipt)

    assert foreign.is_dir()
    assert (foreign / "source.txt").read_text(encoding="utf-8") == "candidate\n"
    materializer.cleanup(receipt)
    _git(repository, "worktree", "remove", "--force", str(foreign))


def test_cleanup_refuses_a_materialized_worktree_whose_source_has_changed(
    tmp_path: Path,
) -> None:
    repository = _init_repository(tmp_path)
    materializer = InjectionMaterializer(repository, tmp_path / "owned-worktrees")
    receipt = materializer.materialize(_candidate(repository))
    assert receipt.worktree is not None
    worktree = Path(receipt.worktree.path)
    source = worktree / "source.txt"
    source.write_text("changed after receipt\n", encoding="utf-8")

    with pytest.raises(InjectionCleanupError, match="source identity has changed"):
        materializer.cleanup(receipt)

    assert worktree.is_dir()
    source.write_text("candidate\n", encoding="utf-8")
    materializer.cleanup(receipt)


def test_materializer_refuses_to_place_disposable_worktrees_inside_the_caller_checkout(
    tmp_path: Path,
) -> None:
    repository = _init_repository(tmp_path)

    with pytest.raises(InjectionMaterializerError, match="outside the caller checkout"):
        InjectionMaterializer(repository, repository / "unsafe-owned-worktrees")
