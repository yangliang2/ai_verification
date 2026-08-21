"""Deterministic M0.1 tests for disposable Injection Lab materialization."""

from __future__ import annotations

from dataclasses import replace
import difflib
from hashlib import sha256
import json
import shlex
from pathlib import Path
import subprocess

import pytest

import aiverify.injection.materialization as materialization_module
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


def test_materializes_when_caller_configures_autocrlf(tmp_path: Path) -> None:
    repository = _init_repository(tmp_path)
    _git(repository, "config", "core.autocrlf", "true")
    candidate = _candidate(repository)
    materializer = InjectionMaterializer(repository, tmp_path / "owned-worktrees")

    receipt = materializer.materialize(candidate)

    assert receipt.outcome == "materialized"
    assert receipt.worktree is not None
    worktree = Path(receipt.worktree.path)
    assert (worktree / "source.txt").read_text(encoding="utf-8") == "candidate\n"
    assert source_tree_sha256_from_worktree(worktree) == receipt.result_source_tree_sha256
    materializer.cleanup(receipt)


def test_materializes_when_attributes_convert_checkout_line_endings(
    tmp_path: Path,
) -> None:
    repository = _init_repository(tmp_path)
    (repository / ".gitattributes").write_text("source.txt text eol=crlf\n", encoding="utf-8")
    _git(repository, "add", ".gitattributes")
    _git(repository, "commit", "-m", "set source checkout eol")
    candidate = _candidate(repository)
    materializer = InjectionMaterializer(repository, tmp_path / "owned-worktrees")

    receipt = materializer.materialize(candidate)

    assert receipt.outcome == "materialized"
    assert receipt.worktree is not None
    assert (Path(receipt.worktree.path) / "source.txt").read_text(encoding="utf-8") == "candidate\n"
    materializer.cleanup(receipt)


def test_materialization_disables_caller_checkout_hooks(tmp_path: Path) -> None:
    repository = _init_repository(tmp_path)
    _dirty_caller(repository)
    before = _caller_snapshot(repository)
    hook_output = repository / "post-checkout-hook-output.txt"
    hook = repository / ".git" / "hooks" / "post-checkout"
    hook.write_text(
        "#!/bin/sh\n"
        f"printf hook > {shlex.quote(str(hook_output))}\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    materializer = InjectionMaterializer(repository, tmp_path / "owned-worktrees")

    receipt = materializer.materialize(_candidate(repository))

    assert receipt.outcome == "materialized"
    assert not hook_output.exists()
    assert _caller_snapshot(repository) == before
    materializer.cleanup(receipt)
    assert _caller_snapshot(repository) == before


def test_materialization_ignores_an_ambient_git_index_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _init_repository(tmp_path)
    candidate = _candidate(repository)
    _dirty_caller(repository)
    before = _caller_snapshot(repository)
    monkeypatch.setenv("GIT_INDEX_FILE", str(repository / ".git" / "index"))
    materializer = InjectionMaterializer(repository, tmp_path / "owned-worktrees")

    receipt = materializer.materialize(candidate)

    assert receipt.outcome == "materialized"
    assert _caller_snapshot(repository) == before
    materializer.cleanup(receipt)
    assert _caller_snapshot(repository) == before


def test_materialization_identities_ignore_caller_diff_configuration(
    tmp_path: Path,
) -> None:
    repository = _init_repository(tmp_path)
    candidate = _candidate(
        repository,
        patch_text=(
            "--- a/source.txt\n"
            "+++ b/source.txt\n"
            "@@ -1 +1 @@\n"
            "-baseline\n"
            "+candidate\n"
            "--- /dev/null\n"
            "+++ b/added.txt\n"
            "@@ -0,0 +1 @@\n"
            "+added source\n"
        ),
    )
    first_materializer = InjectionMaterializer(repository, tmp_path / "first-worktrees")

    first = first_materializer.materialize(candidate)

    assert first.outcome == "materialized"
    first_materializer.cleanup(first)
    _git(repository, "config", "diff.noprefix", "true")
    _git(repository, "config", "diff.mnemonicPrefix", "true")
    _git(repository, "config", "diff.renames", "true")
    _git(repository, "config", "diff.algorithm", "patience")
    _git(repository, "config", "color.ui", "always")
    order_file = tmp_path / "reverse-diff-order"
    order_file.write_text("source.txt\nadded.txt\n", encoding="utf-8")
    _git(repository, "config", "diff.orderFile", str(order_file))
    second_materializer = InjectionMaterializer(repository, tmp_path / "second-worktrees")

    second = second_materializer.materialize(candidate)

    assert second.outcome == "materialized"
    assert second.result_diff_sha256 == first.result_diff_sha256
    assert second.result_identity_sha256 == first.result_identity_sha256
    assert second.receipt_identity_sha256 == first.receipt_identity_sha256
    second_materializer.cleanup(second)


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


def test_rejection_refuses_to_remove_a_worktree_replaced_after_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    materializer = InjectionMaterializer(repository, tmp_path / "owned-worktrees")
    original_run_git = materialization_module._run_git
    replaced = False

    def replace_fresh_worktree(
        worktree: Path,
        arguments: list[str],
        *,
        input_bytes: bytes | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        nonlocal replaced
        result = original_run_git(worktree, arguments, input_bytes=input_bytes)
        if (
            not replaced
            and arguments[:2] == ["apply", "--check"]
            and result.returncode != 0
        ):
            removed = original_run_git(
                repository,
                ["worktree", "remove", "--force", str(worktree)],
            )
            assert removed.returncode == 0
            replacement = original_run_git(
                repository,
                [
                    "worktree",
                    "add",
                    "--detach",
                    str(worktree),
                    candidate.baseline.commit,
                ],
            )
            assert replacement.returncode == 0
            replaced = True
        return result

    monkeypatch.setattr(materialization_module, "_run_git", replace_fresh_worktree)

    receipt = materializer.materialize(candidate)

    assert replaced
    assert receipt.outcome == "rejected"
    assert receipt.rejection_code == "worktree_cleanup_failed"
    worktree = next((tmp_path / "owned-worktrees").iterdir())
    assert worktree.is_dir()
    assert _git(worktree, "rev-parse", "HEAD").stdout.strip() == candidate.baseline.commit
    _git(repository, "worktree", "remove", "--force", str(worktree))


def test_materializes_added_source_files_in_the_canonical_result_diff(
    tmp_path: Path,
) -> None:
    repository = _init_repository(tmp_path)
    candidate = _candidate(
        repository,
        patch_text=(
            "--- a/source.txt\n"
            "+++ b/source.txt\n"
            "@@ -1 +1 @@\n"
            "-baseline\n"
            "+candidate\n"
            "--- /dev/null\n"
            "+++ b/added.txt\n"
            "@@ -0,0 +1 @@\n"
            "+added source\n"
        ),
    )
    materializer = InjectionMaterializer(repository, tmp_path / "owned-worktrees")

    receipt = materializer.materialize(candidate)

    assert receipt.outcome == "materialized"
    assert receipt.worktree is not None
    worktree = Path(receipt.worktree.path)
    assert (worktree / "added.txt").read_text(encoding="utf-8") == "added source\n"
    _git(worktree, "add", "source.txt", "added.txt")
    canonical_result_diff = _git(
        worktree,
        "diff",
        "--cached",
        "--binary",
        "--full-index",
        "--no-ext-diff",
        candidate.baseline.commit,
    ).stdout.encode("utf-8")
    assert b"added.txt" in canonical_result_diff
    assert receipt.result_diff_sha256 == sha256(canonical_result_diff).hexdigest()

    materializer.cleanup(receipt)


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


def test_direct_candidate_with_an_unencodable_identity_returns_stable_rejection(
    tmp_path: Path,
) -> None:
    repository = _init_repository(tmp_path)
    candidate = _candidate(repository)
    malformed = replace(
        candidate,
        candidate_id="\ud800",
        baseline=replace(
            candidate.baseline,
            source_origin="https://example.invalid/other-fixture.git",
        ),
    )
    root = tmp_path / "owned-worktrees"
    materializer = InjectionMaterializer(repository, root)

    first = materializer.materialize(malformed)
    second = materializer.materialize(malformed)

    assert first.outcome == "rejected"
    assert first.rejection_code == "invalid_candidate"
    assert first.candidate_identity_sha256 is None
    assert first.to_dict() == second.to_dict()
    assert not root.exists()


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
