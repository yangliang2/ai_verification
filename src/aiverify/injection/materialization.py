"""Safe materialization of one declared source delta in an owned Git worktree."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
from typing import Any, Iterable, Mapping
from uuid import uuid4

from aiverify.injection.models import (
    BaselineProvenance,
    InjectionCandidate,
    InjectionContractError,
    InjectionReceipt,
    MaterializedWorktree,
    canonical_json_bytes,
    result_identity_sha256,
    sha256_hex,
)


_OWNERSHIP_MARKER = ".aiverify-injection-ownership.json"
_GIT_TIMEOUT_SECONDS = 30


class InjectionMaterializerError(RuntimeError):
    """Raised when a materializer cannot be safely configured."""


class InjectionCleanupError(RuntimeError):
    """Raised when an alleged owned worktree cannot be safely removed."""


def _run_git(
    repository: Path,
    arguments: list[str],
    *,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run Git without a shell or an interactive credential prompt."""
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ["git", "-C", os.fspath(repository), *arguments],
        input=input_bytes,
        capture_output=True,
        check=False,
        env=environment,
        timeout=_GIT_TIMEOUT_SECONDS,
    )


def _git_stdout(repository: Path, arguments: list[str]) -> bytes:
    result = _run_git(repository, arguments)
    if result.returncode != 0:
        raise InjectionMaterializerError("Git inspection failed")
    return result.stdout.rstrip(b"\n")


def _repository_root(path: str | Path) -> Path:
    candidate = Path(path).expanduser().resolve()
    try:
        root = _git_stdout(candidate, ["rev-parse", "--show-toplevel"])
    except (OSError, subprocess.TimeoutExpired, InjectionMaterializerError) as error:
        raise InjectionMaterializerError("caller_checkout must be a Git worktree") from error
    if not root:
        raise InjectionMaterializerError("caller_checkout must be a Git worktree")
    return Path(os.fsdecode(root)).resolve()


def _origin(repository: Path) -> str:
    try:
        origin = _git_stdout(repository, ["config", "--get", "remote.origin.url"])
    except (OSError, subprocess.TimeoutExpired, InjectionMaterializerError) as error:
        raise InjectionMaterializerError(
            "caller checkout must declare remote.origin.url"
        ) from error
    if not origin:
        raise InjectionMaterializerError(
            "caller checkout must declare remote.origin.url"
        )
    return os.fsdecode(origin)


def _resolved_commit(repository: Path, commit: str) -> str:
    try:
        resolved = _git_stdout(repository, ["rev-parse", "--verify", f"{commit}^{{commit}}"])
    except (OSError, subprocess.TimeoutExpired, InjectionMaterializerError) as error:
        raise InjectionMaterializerError("declared baseline commit is unavailable") from error
    text = os.fsdecode(resolved)
    if not text:
        raise InjectionMaterializerError("declared baseline commit is unavailable")
    return text


def _hash_source_entries(
    entries: Iterable[tuple[bytes, bytes, bool, bytes]],
) -> str:
    """Hash a sorted source manifest without relying on Git object hash format."""
    digest = sha256()
    digest.update(b"aiverify.source-tree.v1\0")
    for path, kind, executable, payload in sorted(entries, key=lambda item: item[0]):
        for part in (path, kind, b"1" if executable else b"0", payload):
            digest.update(len(part).to_bytes(8, "big"))
            digest.update(part)
    return digest.hexdigest()


def source_tree_sha256_for_commit(repository: str | Path, commit: str) -> str:
    """Hash tracked source content at one immutable commit.

    The digest is independent of Git's SHA-1/SHA-256 object format and aligns
    with :func:`source_tree_sha256_from_worktree` for a clean checkout.
    """
    root = _repository_root(repository)
    resolved = _resolved_commit(root, commit)
    try:
        listing = _git_stdout(root, ["ls-tree", "-r", "-z", "--full-tree", resolved])
    except (OSError, subprocess.TimeoutExpired, InjectionMaterializerError) as error:
        raise InjectionMaterializerError("baseline tree cannot be read") from error

    entries: list[tuple[bytes, bytes, bool, bytes]] = []
    for record in (item for item in listing.split(b"\0") if item):
        try:
            header, path = record.split(b"\t", 1)
            mode, object_type, object_id = header.split(b" ", 2)
        except ValueError as error:
            raise InjectionMaterializerError("Git tree output is malformed") from error
        if object_type == b"blob":
            blob = _run_git(root, ["cat-file", "blob", os.fsdecode(object_id)])
            if blob.returncode != 0:
                raise InjectionMaterializerError("baseline blob cannot be read")
            if mode == b"120000":
                entries.append((path, b"symlink", False, blob.stdout))
            elif mode in {b"100644", b"100755"}:
                entries.append((path, b"file", mode == b"100755", blob.stdout))
            else:
                raise InjectionMaterializerError("baseline tree has unsupported file mode")
        elif object_type == b"commit":
            # A submodule cannot be faithfully materialized as source in M0.1.
            raise InjectionMaterializerError("baseline tree has unsupported gitlink")
        else:
            raise InjectionMaterializerError("baseline tree has unsupported entry")
    return _hash_source_entries(entries)


def _relative_bytes(root: Path, path: Path) -> bytes:
    return os.fsencode(path.relative_to(root).as_posix())


def source_tree_sha256_from_worktree(
    worktree: str | Path,
    *,
    ignore_ownership_marker: bool = True,
) -> str:
    """Hash source files present in a worktree, excluding its Git control file."""
    root = Path(worktree).resolve()
    if not root.is_dir():
        raise InjectionMaterializerError("worktree source root is unavailable")

    entries: list[tuple[bytes, bytes, bool, bytes]] = []
    for current, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        directory_names.sort(key=os.fsencode)
        file_names.sort(key=os.fsencode)

        retained_directories: list[str] = []
        for name in directory_names:
            child = current_path / name
            if current_path == root and name == ".git":
                continue
            child_stat = child.lstat()
            if stat.S_ISLNK(child_stat.st_mode):
                entries.append(
                    (
                        _relative_bytes(root, child),
                        b"symlink",
                        False,
                        os.fsencode(os.readlink(child)),
                    )
                )
            elif stat.S_ISDIR(child_stat.st_mode):
                retained_directories.append(name)
            else:
                raise InjectionMaterializerError("worktree contains an unsupported directory entry")
        directory_names[:] = retained_directories

        for name in file_names:
            if current_path == root and name == ".git":
                continue
            if (
                ignore_ownership_marker
                and current_path == root
                and name == _OWNERSHIP_MARKER
            ):
                continue
            child = current_path / name
            child_stat = child.lstat()
            if stat.S_ISREG(child_stat.st_mode):
                entries.append(
                    (
                        _relative_bytes(root, child),
                        b"file",
                        bool(child_stat.st_mode & stat.S_IXUSR),
                        child.read_bytes(),
                    )
                )
            elif stat.S_ISLNK(child_stat.st_mode):
                entries.append(
                    (
                        _relative_bytes(root, child),
                        b"symlink",
                        False,
                        os.fsencode(os.readlink(child)),
                    )
                )
            else:
                raise InjectionMaterializerError("worktree contains an unsupported file entry")
    return _hash_source_entries(entries)


def capture_baseline_provenance(
    repository: str | Path,
    commit: str,
) -> BaselineProvenance:
    """Capture the complete immutable baseline identity for a candidate request."""
    root = _repository_root(repository)
    resolved = _resolved_commit(root, commit)
    return BaselineProvenance(
        source_origin=_origin(root),
        commit=resolved,
        source_tree_sha256=source_tree_sha256_for_commit(root, resolved),
    )


def _path_is_within(path: Path, ancestor: Path) -> bool:
    try:
        path.relative_to(ancestor)
    except ValueError:
        return False
    return True


class InjectionMaterializer:
    """Create and clean only fresh, detached, materializer-owned worktrees."""

    def __init__(self, caller_checkout: str | Path, worktree_root: str | Path) -> None:
        self._caller_checkout = _repository_root(caller_checkout)
        self._worktree_root = Path(worktree_root).expanduser().resolve()
        if _path_is_within(self._worktree_root, self._caller_checkout):
            raise InjectionMaterializerError(
                "worktree_root must be outside the caller checkout"
            )

    @property
    def caller_checkout(self) -> Path:
        """Resolved, read-only caller checkout used to create linked worktrees."""
        return self._caller_checkout

    @property
    def worktree_root(self) -> Path:
        """Parent directory under which only fresh owned children are created."""
        return self._worktree_root

    def materialize(
        self,
        candidate_input: InjectionCandidate | Mapping[str, Any],
    ) -> InjectionReceipt:
        """Materialize exactly one candidate or return a stable rejected receipt.

        Every mutation happens after baseline provenance checks and only inside a
        fresh linked worktree.  The caller worktree is never checked out, reset,
        patched, or otherwise modified.
        """
        try:
            candidate = (
                candidate_input
                if isinstance(candidate_input, InjectionCandidate)
                else InjectionCandidate.from_dict(candidate_input)
            )
        except (InjectionContractError, TypeError, ValueError):
            return InjectionReceipt.rejected(None, "invalid_candidate")

        try:
            return self._materialize_candidate(candidate)
        except (OSError, subprocess.TimeoutExpired):
            return InjectionReceipt.rejected(candidate, "caller_checkout_unavailable")

    def _materialize_candidate(self, candidate: InjectionCandidate) -> InjectionReceipt:
        try:
            if _origin(self._caller_checkout) != candidate.baseline.source_origin:
                return InjectionReceipt.rejected(candidate, "repository_origin_mismatch")
        except InjectionMaterializerError:
            return InjectionReceipt.rejected(candidate, "caller_checkout_unavailable")

        try:
            resolved_commit = _resolved_commit(
                self._caller_checkout, candidate.baseline.commit
            )
        except InjectionMaterializerError:
            return InjectionReceipt.rejected(candidate, "baseline_commit_unavailable")
        if resolved_commit != candidate.baseline.commit:
            return InjectionReceipt.rejected(candidate, "baseline_commit_unavailable")

        try:
            baseline_tree_sha256 = source_tree_sha256_for_commit(
                self._caller_checkout, resolved_commit
            )
        except InjectionMaterializerError:
            return InjectionReceipt.rejected(candidate, "baseline_tree_unreadable")
        if baseline_tree_sha256 != candidate.baseline.source_tree_sha256:
            return InjectionReceipt.rejected(candidate, "baseline_tree_mismatch")

        if _path_is_within(self._worktree_root, self._caller_checkout):
            return InjectionReceipt.rejected(candidate, "worktree_root_unsafe")
        try:
            self._worktree_root.mkdir(parents=True, exist_ok=True)
        except OSError:
            return InjectionReceipt.rejected(candidate, "worktree_root_unavailable")
        if not self._worktree_root.is_dir():
            return InjectionReceipt.rejected(candidate, "worktree_root_unavailable")

        worktree_path = self._fresh_worktree_path(candidate)
        created = _run_git(
            self._caller_checkout,
            ["worktree", "add", "--detach", os.fspath(worktree_path), resolved_commit],
        )
        if created.returncode != 0:
            return InjectionReceipt.rejected(candidate, "worktree_creation_failed")

        try:
            return self._apply_in_fresh_worktree(candidate, worktree_path, resolved_commit)
        except (OSError, subprocess.TimeoutExpired, InjectionMaterializerError):
            if not self._discard_fresh_worktree(worktree_path):
                return InjectionReceipt.rejected(candidate, "worktree_cleanup_failed")
            return InjectionReceipt.rejected(candidate, "result_identity_failed")

    def _fresh_worktree_path(self, candidate: InjectionCandidate) -> Path:
        # Do not derive a path from user-controlled candidate_id; use its digest.
        return self._worktree_root / (
            f"aiverify-injection-{candidate.identity_sha256[:16]}-{uuid4().hex}"
        )

    def _apply_in_fresh_worktree(
        self,
        candidate: InjectionCandidate,
        worktree_path: Path,
        resolved_commit: str,
    ) -> InjectionReceipt:
        if not worktree_path.is_dir() or worktree_path.is_symlink():
            return self._reject_and_discard(candidate, worktree_path, "worktree_provenance_mismatch")
        current_head = _git_stdout(worktree_path, ["rev-parse", "HEAD"])
        if os.fsdecode(current_head) != resolved_commit:
            return self._reject_and_discard(candidate, worktree_path, "worktree_provenance_mismatch")
        detached = _run_git(worktree_path, ["symbolic-ref", "-q", "HEAD"])
        if detached.returncode == 0:
            return self._reject_and_discard(candidate, worktree_path, "worktree_provenance_mismatch")
        current_tree = source_tree_sha256_from_worktree(
            worktree_path, ignore_ownership_marker=False
        )
        if current_tree != candidate.baseline.source_tree_sha256:
            return self._reject_and_discard(candidate, worktree_path, "worktree_provenance_mismatch")

        patch_bytes = candidate.source_delta.patch_text.encode("utf-8")
        check = _run_git(
            worktree_path,
            ["apply", "--check", "--whitespace=nowarn", "-"],
            input_bytes=patch_bytes,
        )
        if check.returncode != 0:
            return self._reject_and_discard(candidate, worktree_path, "patch_not_applicable")
        applied = _run_git(
            worktree_path,
            ["apply", "--whitespace=nowarn", "-"],
            input_bytes=patch_bytes,
        )
        if applied.returncode != 0:
            return self._reject_and_discard(candidate, worktree_path, "patch_apply_failed")

        marker_path = worktree_path / _OWNERSHIP_MARKER
        if marker_path.exists() or marker_path.is_symlink():
            return self._reject_and_discard(candidate, worktree_path, "reserved_ownership_path")
        diff = _run_git(
            worktree_path,
            ["diff", "--binary", "--full-index", "--no-ext-diff", resolved_commit],
        )
        if diff.returncode != 0:
            return self._reject_and_discard(candidate, worktree_path, "result_identity_failed")
        if not diff.stdout:
            return self._reject_and_discard(candidate, worktree_path, "patch_did_not_change_source")
        result_tree_sha256 = source_tree_sha256_from_worktree(
            worktree_path, ignore_ownership_marker=False
        )
        if result_tree_sha256 == candidate.baseline.source_tree_sha256:
            return self._reject_and_discard(candidate, worktree_path, "patch_did_not_change_source")
        diff_sha256 = sha256(diff.stdout).hexdigest()
        result_sha256 = result_identity_sha256(
            baseline_identity_sha256=candidate.baseline.identity_sha256,
            patch_identity_sha256=candidate.source_delta.identity_sha256,
            result_source_tree_sha256=result_tree_sha256,
            result_diff_sha256=diff_sha256,
        )
        owned_worktree = MaterializedWorktree(
            path=os.fspath(worktree_path.resolve()),
            ownership_token=uuid4().hex,
            candidate_identity_sha256=candidate.identity_sha256,
            baseline_commit=resolved_commit,
            result_identity_sha256=result_sha256,
        )
        marker_path.write_bytes(self._marker_bytes(owned_worktree))
        return InjectionReceipt(
            outcome="materialized",
            candidate_identity_sha256=candidate.identity_sha256,
            baseline_identity_sha256=candidate.baseline.identity_sha256,
            patch_identity_sha256=candidate.source_delta.identity_sha256,
            result_source_tree_sha256=result_tree_sha256,
            result_diff_sha256=diff_sha256,
            result_identity_sha256=result_sha256,
            worktree=owned_worktree,
        )

    def _reject_and_discard(
        self,
        candidate: InjectionCandidate,
        worktree_path: Path,
        rejection_code: str,
    ) -> InjectionReceipt:
        if not self._discard_fresh_worktree(worktree_path):
            return InjectionReceipt.rejected(candidate, "worktree_cleanup_failed")
        return InjectionReceipt.rejected(candidate, rejection_code)

    def _discard_fresh_worktree(self, worktree_path: Path) -> bool:
        """Discard only the path just created by this materializer invocation."""
        if not _path_is_within(worktree_path.resolve(), self._worktree_root):
            return False
        result = _run_git(
            self._caller_checkout,
            ["worktree", "remove", "--force", os.fspath(worktree_path)],
        )
        return result.returncode == 0 and not worktree_path.exists()

    def _marker_document(self, worktree: MaterializedWorktree) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "kind": "aiverify-injection-owned-worktree",
            "ownership_token": worktree.ownership_token,
            "candidate_identity_sha256": worktree.candidate_identity_sha256,
            "baseline_commit": worktree.baseline_commit,
            "result_identity_sha256": worktree.result_identity_sha256,
        }

    def _marker_bytes(self, worktree: MaterializedWorktree) -> bytes:
        return canonical_json_bytes(self._marker_document(worktree)) + b"\n"

    def cleanup(self, receipt: InjectionReceipt) -> None:
        """Remove only the exact, verified worktree created by this materializer."""
        if not isinstance(receipt, InjectionReceipt) or receipt.outcome != "materialized":
            raise InjectionCleanupError("cleanup requires a materialized receipt")
        worktree = receipt.worktree
        if worktree is None:
            raise InjectionCleanupError("cleanup requires an owned worktree")
        path = Path(worktree.path).resolve()
        if path.parent != self._worktree_root or not path.is_dir() or path.is_symlink():
            raise InjectionCleanupError("cleanup path is not a materializer-owned child")
        marker_path = path / _OWNERSHIP_MARKER
        try:
            marker_bytes = marker_path.read_bytes()
        except OSError as error:
            raise InjectionCleanupError("owned worktree marker is unavailable") from error
        if marker_bytes != self._marker_bytes(worktree):
            raise InjectionCleanupError("owned worktree marker does not match receipt")
        if worktree.candidate_identity_sha256 != receipt.candidate_identity_sha256:
            raise InjectionCleanupError("owned worktree candidate identity does not match")
        if worktree.result_identity_sha256 != receipt.result_identity_sha256:
            raise InjectionCleanupError("owned worktree result identity does not match")
        if _git_common_dir(path) != _git_common_dir(self._caller_checkout):
            raise InjectionCleanupError("owned worktree belongs to a different repository")
        registered_paths = self._registered_worktree_paths()
        if path not in registered_paths:
            raise InjectionCleanupError("owned worktree is not registered with caller repository")
        head = _git_stdout(path, ["rev-parse", "HEAD"])
        if os.fsdecode(head) != worktree.baseline_commit:
            raise InjectionCleanupError("owned worktree baseline commit has changed")
        if _run_git(path, ["symbolic-ref", "-q", "HEAD"]).returncode == 0:
            raise InjectionCleanupError("owned worktree is no longer detached")
        try:
            current_result_tree = source_tree_sha256_from_worktree(path)
        except InjectionMaterializerError as error:
            raise InjectionCleanupError("owned worktree source cannot be verified") from error
        if current_result_tree != receipt.result_source_tree_sha256:
            raise InjectionCleanupError("owned worktree source identity has changed")

        removed = _run_git(
            self._caller_checkout,
            ["worktree", "remove", "--force", os.fspath(path)],
        )
        if removed.returncode != 0 or path.exists():
            raise InjectionCleanupError("owned worktree removal failed")

    def _registered_worktree_paths(self) -> set[Path]:
        listing = _git_stdout(self._caller_checkout, ["worktree", "list", "--porcelain"])
        paths: set[Path] = set()
        for line in listing.splitlines():
            if line.startswith(b"worktree "):
                paths.add(Path(os.fsdecode(line[len(b"worktree ") :])).resolve())
        return paths


def _git_common_dir(repository: Path) -> Path:
    raw = _git_stdout(repository, ["rev-parse", "--git-common-dir"])
    path = Path(os.fsdecode(raw))
    return path.resolve() if path.is_absolute() else (repository / path).resolve()


__all__ = [
    "InjectionCleanupError",
    "InjectionMaterializer",
    "InjectionMaterializerError",
    "capture_baseline_provenance",
    "source_tree_sha256_for_commit",
    "source_tree_sha256_from_worktree",
]
