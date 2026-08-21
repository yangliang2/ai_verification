"""Safe materialization of one declared source delta in an owned Git worktree."""

from __future__ import annotations

from dataclasses import dataclass
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
_GIT_IDENTITY_CONFIG = (
    "-c",
    "core.autocrlf=false",
    "-c",
    "core.eol=lf",
    "-c",
    f"core.hooksPath={os.devnull}",
    "-c",
    "core.quotePath=true",
    "-c",
    "color.ui=false",
    "-c",
    "diff.renames=false",
    "-c",
    "diff.mnemonicPrefix=false",
    "-c",
    "diff.noprefix=false",
    "-c",
    "diff.algorithm=myers",
    "-c",
    "diff.indentHeuristic=false",
    "-c",
    "diff.compactionHeuristic=false",
    "-c",
    "diff.context=3",
    "-c",
    "diff.interHunkContext=0",
)
_CANONICAL_STAGED_DIFF_OPTIONS = (
    "--cached",
    "--binary",
    "--full-index",
    "--no-ext-diff",
    "--no-textconv",
    "--no-color",
    "--no-renames",
    "--src-prefix=a/",
    "--dst-prefix=b/",
    "--diff-algorithm=myers",
    "--no-indent-heuristic",
    "--inter-hunk-context=0",
    "-U3",
    "--no-relative",
    f"-O{os.devnull}",
)


class InjectionMaterializerError(RuntimeError):
    """Raised when a materializer cannot be safely configured."""


class InjectionCleanupError(RuntimeError):
    """Raised when an alleged owned worktree cannot be safely removed."""


@dataclass(frozen=True)
class _DirectoryAuthority:
    """An opened directory plus its immutable filesystem identity."""

    path: Path
    device: int
    inode: int
    descriptor: int
    parent_descriptor: int


@dataclass(frozen=True)
class _OwnedWorktreeRegistration:
    """Non-serializable authority retained only by the creating materializer."""

    worktree: MaterializedWorktree
    directory: _DirectoryAuthority
    administrative_directory: _DirectoryAuthority


@dataclass(frozen=True)
class _FreshWorktreeRegistration:
    """Non-serializable authority for a worktree before materialization succeeds."""

    baseline_commit: str
    directory: _DirectoryAuthority
    administrative_directory: _DirectoryAuthority


def _run_git(
    repository: Path,
    arguments: list[str],
    *,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run Git without a shell or an interactive credential prompt."""
    # Ambient GIT_* variables can redirect an otherwise scoped command to the
    # caller's index, object database, or worktree.  Start with normal process
    # environment needed to locate Git, but replace all Git execution state.
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment.update(
        {
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return subprocess.run(
        ["git", *_GIT_IDENTITY_CONFIG, "-C", os.fspath(repository), *arguments],
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

    The digest is independent of Git's SHA-1/SHA-256 object format.  It uses
    Git blobs, so checkout filters cannot change the declared source identity.
    """
    root = _repository_root(repository)
    resolved = _resolved_commit(root, commit)
    return _source_tree_sha256_for_tree(root, resolved)


def _source_tree_sha256_for_tree(repository: Path, treeish: str) -> str:
    """Hash tracked Git blobs from a commit or tree object."""
    return _hash_source_entries(_source_tree_entries_for_tree(repository, treeish))


def _source_tree_entries_for_tree(
    repository: Path,
    treeish: str,
) -> list[tuple[bytes, bytes, bool, bytes]]:
    """Read supported source entries from a Git commit or tree object."""
    try:
        listing = _git_stdout(repository, ["ls-tree", "-r", "-z", "--full-tree", treeish])
    except (OSError, subprocess.TimeoutExpired, InjectionMaterializerError) as error:
        raise InjectionMaterializerError("source tree cannot be read") from error

    entries: list[tuple[bytes, bytes, bool, bytes]] = []
    for record in (item for item in listing.split(b"\0") if item):
        try:
            header, path = record.split(b"\t", 1)
            mode, object_type, object_id = header.split(b" ", 2)
        except ValueError as error:
            raise InjectionMaterializerError("Git tree output is malformed") from error
        if object_type == b"blob":
            blob = _run_git(repository, ["cat-file", "blob", os.fsdecode(object_id)])
            if blob.returncode != 0:
                raise InjectionMaterializerError("source blob cannot be read")
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
    return entries


def _index_treeish(worktree: Path) -> str:
    try:
        tree = _git_stdout(worktree, ["write-tree"])
    except (OSError, subprocess.TimeoutExpired, InjectionMaterializerError) as error:
        raise InjectionMaterializerError("worktree index cannot be read") from error
    if not tree:
        raise InjectionMaterializerError("worktree index cannot be read")
    return os.fsdecode(tree)


def _source_tree_sha256_from_index(worktree: Path) -> str:
    """Hash the exact tracked source tree staged in a worktree index."""
    return _source_tree_sha256_for_tree(worktree, _index_treeish(worktree))


def _populate_worktree_from_index(worktree: Path) -> None:
    """Write exact staged Git blobs without invoking checkout filters or hooks."""
    if any(child.name != ".git" for child in worktree.iterdir()):
        raise InjectionMaterializerError("fresh worktree contains unexpected source")

    for path, kind, executable, payload in _source_tree_entries_for_tree(
        worktree,
        _index_treeish(worktree),
    ):
        target = _source_entry_target(worktree, path)
        _create_source_parent_directories(worktree, target)
        try:
            target.lstat()
        except FileNotFoundError:
            pass
        else:
            raise InjectionMaterializerError("source tree contains colliding paths")
        if kind == b"file":
            descriptor = os.open(
                target,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o755 if executable else 0o644,
            )
            with os.fdopen(descriptor, "wb") as destination:
                destination.write(payload)
        elif kind == b"symlink":
            try:
                os.symlink(os.fsdecode(payload), target)
            except (OSError, ValueError) as error:
                raise InjectionMaterializerError("source tree has invalid symlink") from error
        else:
            raise InjectionMaterializerError("source tree has unsupported entry")


def _source_entry_target(worktree: Path, source_path: bytes) -> Path:
    components = source_path.split(b"/")
    if not components or any(
        component in {b"", b".", b".."} for component in components
    ):
        raise InjectionMaterializerError("source tree has unsafe path")
    if components[0] == b".git":
        raise InjectionMaterializerError("source tree reserves Git control path")
    return worktree.joinpath(*(os.fsdecode(component) for component in components))


def _create_source_parent_directories(worktree: Path, target: Path) -> None:
    relative_parent = target.parent.relative_to(worktree)
    directory = worktree
    for component in relative_parent.parts:
        directory /= component
        try:
            details = directory.lstat()
        except FileNotFoundError:
            directory.mkdir()
            continue
        if directory.is_symlink() or not stat.S_ISDIR(details.st_mode):
            raise InjectionMaterializerError("source tree has colliding paths")


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


def _open_directory_authority(path: Path) -> _DirectoryAuthority:
    """Open one non-symlink directory and bind it to its parent descriptor."""
    try:
        details = path.lstat()
    except OSError as error:
        raise InjectionMaterializerError("worktree directory is unavailable") from error
    if path.is_symlink() or not stat.S_ISDIR(details.st_mode):
        raise InjectionMaterializerError("worktree directory is unavailable")

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    parent_descriptor = os.open(path.parent, flags)
    try:
        descriptor = os.open(path.name, flags, dir_fd=parent_descriptor)
    except OSError:
        os.close(parent_descriptor)
        raise
    observed = os.fstat(descriptor)
    if (observed.st_dev, observed.st_ino) != (details.st_dev, details.st_ino):
        os.close(descriptor)
        os.close(parent_descriptor)
        raise InjectionMaterializerError("worktree directory identity has changed")
    return _DirectoryAuthority(
        path=path,
        device=details.st_dev,
        inode=details.st_ino,
        descriptor=descriptor,
        parent_descriptor=parent_descriptor,
    )


def _authority_matches_path(authority: _DirectoryAuthority) -> bool:
    """Check that a retained descriptor still names the original directory."""
    try:
        details = authority.path.lstat()
        observed = os.fstat(authority.descriptor)
    except OSError:
        return False
    return (
        not authority.path.is_symlink()
        and stat.S_ISDIR(details.st_mode)
        and stat.S_ISDIR(observed.st_mode)
        and (details.st_dev, details.st_ino) == (authority.device, authority.inode)
        and (observed.st_dev, observed.st_ino) == (authority.device, authority.inode)
    )


def _close_directory_authority(authority: _DirectoryAuthority) -> None:
    for descriptor in (authority.descriptor, authority.parent_descriptor):
        try:
            os.close(descriptor)
        except OSError:
            pass


def _remove_directory_contents(descriptor: int) -> None:
    """Remove children through an opened directory without following symlinks."""
    with os.scandir(descriptor) as entries:
        children = [(entry.name, entry.is_dir(follow_symlinks=False)) for entry in entries]
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    for name, is_directory in children:
        if not is_directory:
            os.unlink(name, dir_fd=descriptor)
            continue
        child_descriptor = os.open(name, flags, dir_fd=descriptor)
        try:
            _remove_directory_contents(child_descriptor)
        finally:
            os.close(child_descriptor)
        os.rmdir(name, dir_fd=descriptor)


def _remove_authorized_directory(authority: _DirectoryAuthority) -> bool:
    """Delete only the opened directory; a replacement must remain untouched."""
    try:
        _remove_directory_contents(authority.descriptor)
        if not _authority_matches_path(authority):
            return False
        os.rmdir(authority.path.name, dir_fd=authority.parent_descriptor)
    except OSError:
        return False
    return True


def _reserve_worktree_directory(path: Path) -> _DirectoryAuthority:
    """Create and bind the disposable directory before Git can populate it."""
    path.mkdir(mode=0o700)
    try:
        return _open_directory_authority(path)
    except (OSError, InjectionMaterializerError):
        try:
            path.rmdir()
        except OSError:
            pass
        raise


def _release_reserved_directory(authority: _DirectoryAuthority) -> bool:
    """Close and remove an unpopulated reservation if it remains ours."""
    try:
        return _remove_authorized_directory(authority)
    finally:
        _close_directory_authority(authority)


class InjectionMaterializer:
    """Create and clean only fresh, detached, materializer-owned worktrees."""

    def __init__(self, caller_checkout: str | Path, worktree_root: str | Path) -> None:
        self._caller_checkout = _repository_root(caller_checkout)
        self._worktree_root = Path(worktree_root).expanduser().resolve()
        self._fresh_worktrees: dict[Path, _FreshWorktreeRegistration] = {}
        self._owned_worktrees: dict[Path, _OwnedWorktreeRegistration] = {}
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
            # Direct dataclass input must be just as canonicalizable as a
            # mapping that passed the serialized contract parser.
            candidate.identity_sha256
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
        try:
            reserved_directory = _reserve_worktree_directory(worktree_path)
        except OSError:
            return InjectionReceipt.rejected(candidate, "worktree_creation_failed")
        except InjectionMaterializerError:
            return InjectionReceipt.rejected(candidate, "worktree_cleanup_failed")
        try:
            created = _run_git(
                self._caller_checkout,
                [
                    "worktree",
                    "add",
                    "--detach",
                    "--no-checkout",
                    os.fspath(worktree_path),
                    resolved_commit,
                ],
            )
        except (OSError, subprocess.TimeoutExpired):
            released_reservation = _release_reserved_directory(reserved_directory)
            return InjectionReceipt.rejected(
                candidate,
                "caller_checkout_unavailable"
                if released_reservation
                else "worktree_cleanup_failed",
            )
        if created.returncode != 0:
            removed_reservation = _release_reserved_directory(reserved_directory)
            return InjectionReceipt.rejected(
                candidate,
                "worktree_creation_failed"
                if removed_reservation
                else "worktree_cleanup_failed",
            )

        try:
            self._register_fresh_worktree(
                worktree_path,
                resolved_commit,
                reserved_directory,
            )
        except (OSError, subprocess.TimeoutExpired, InjectionMaterializerError):
            # Creation succeeded but ownership could not be established.  Do
            # not guess at cleanup authority for a linked worktree.
            return InjectionReceipt.rejected(candidate, "worktree_cleanup_failed")

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
        initialized = _run_git(worktree_path, ["read-tree", resolved_commit])
        if initialized.returncode != 0:
            return self._reject_and_discard(candidate, worktree_path, "worktree_provenance_mismatch")
        current_tree = _source_tree_sha256_from_index(worktree_path)
        if current_tree != candidate.baseline.source_tree_sha256:
            return self._reject_and_discard(candidate, worktree_path, "worktree_provenance_mismatch")
        if any(child.name != ".git" for child in worktree_path.iterdir()):
            return self._reject_and_discard(candidate, worktree_path, "worktree_provenance_mismatch")

        patch_bytes = candidate.source_delta.patch_text.encode("utf-8")
        # M0.1's executable applicability boundary is one delta against the
        # declared immutable baseline, not interpretation of operator metadata.
        check = _run_git(
            worktree_path,
            ["apply", "--cached", "--check", "--whitespace=nowarn", "-"],
            input_bytes=patch_bytes,
        )
        if check.returncode != 0:
            return self._reject_and_discard(candidate, worktree_path, "patch_not_applicable")
        applied = _run_git(
            worktree_path,
            ["apply", "--cached", "--whitespace=nowarn", "-"],
            input_bytes=patch_bytes,
        )
        if applied.returncode != 0:
            return self._reject_and_discard(candidate, worktree_path, "patch_apply_failed")

        diff = _run_git(
            worktree_path,
            [
                "diff",
                *_CANONICAL_STAGED_DIFF_OPTIONS,
                resolved_commit,
                "--",
            ],
        )
        if diff.returncode != 0:
            return self._reject_and_discard(candidate, worktree_path, "result_identity_failed")
        if not diff.stdout:
            return self._reject_and_discard(candidate, worktree_path, "patch_did_not_change_source")
        result_tree_sha256 = _source_tree_sha256_from_index(worktree_path)
        if result_tree_sha256 == candidate.baseline.source_tree_sha256:
            return self._reject_and_discard(candidate, worktree_path, "patch_did_not_change_source")
        _populate_worktree_from_index(worktree_path)
        marker_path = worktree_path / _OWNERSHIP_MARKER
        if marker_path.exists() or marker_path.is_symlink():
            return self._reject_and_discard(candidate, worktree_path, "reserved_ownership_path")
        if (
            source_tree_sha256_from_worktree(
                worktree_path,
                ignore_ownership_marker=False,
            )
            != result_tree_sha256
        ):
            return self._reject_and_discard(candidate, worktree_path, "result_identity_failed")
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
        receipt = InjectionReceipt(
            outcome="materialized",
            candidate_identity_sha256=candidate.identity_sha256,
            baseline_identity_sha256=candidate.baseline.identity_sha256,
            patch_identity_sha256=candidate.source_delta.identity_sha256,
            result_source_tree_sha256=result_tree_sha256,
            result_diff_sha256=diff_sha256,
            result_identity_sha256=result_sha256,
            worktree=owned_worktree,
        )
        try:
            self._promote_fresh_worktree(owned_worktree)
        except (OSError, InjectionMaterializerError):
            return self._reject_and_discard(candidate, worktree_path, "result_identity_failed")
        return receipt

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
        path = Path(worktree_path)
        registration = self._fresh_worktrees.get(path)
        if registration is None:
            return False
        if not self._is_verified_linked_worktree(
            path,
            registration.directory,
            registration.baseline_commit,
        ):
            return False
        if not self._dispose_owned_directories(
            registration.directory,
            registration.administrative_directory,
        ):
            return False
        self._fresh_worktrees.pop(path, None)
        _close_directory_authority(registration.directory)
        _close_directory_authority(registration.administrative_directory)
        return True

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

    def _register_fresh_worktree(
        self,
        worktree_path: Path,
        baseline_commit: str,
        directory: _DirectoryAuthority,
    ) -> None:
        """Record the exact fresh linked worktree before any failure cleanup."""
        path = Path(worktree_path)
        if path.parent != self._worktree_root:
            raise InjectionMaterializerError("fresh worktree is outside materializer root")
        administrative_directory: _DirectoryAuthority | None = None
        try:
            if not _authority_matches_path(directory):
                raise InjectionMaterializerError("fresh worktree directory identity has changed")
            administrative_path = _git_directory(path)
            if administrative_path.parent != _git_common_dir(path) / "worktrees":
                raise InjectionMaterializerError("fresh worktree administrative path is unsafe")
            administrative_directory = _open_directory_authority(administrative_path)
            if not self._is_verified_linked_worktree(path, directory, baseline_commit):
                raise InjectionMaterializerError("fresh worktree provenance cannot be verified")
        except Exception:
            _close_directory_authority(directory)
            if administrative_directory is not None:
                _close_directory_authority(administrative_directory)
            raise
        self._fresh_worktrees[path] = _FreshWorktreeRegistration(
            baseline_commit=baseline_commit,
            directory=directory,
            administrative_directory=administrative_directory,
        )

    def _promote_fresh_worktree(self, worktree: MaterializedWorktree) -> None:
        """Transfer verified fresh-worktree authority to the owned receipt."""
        path = Path(worktree.path)
        registration = self._fresh_worktrees.get(path)
        if registration is None:
            raise InjectionMaterializerError("fresh worktree was not created by this materializer")
        if registration.baseline_commit != worktree.baseline_commit:
            raise InjectionMaterializerError("fresh worktree baseline commit has changed")
        if not self._is_verified_linked_worktree(
            path,
            registration.directory,
            worktree.baseline_commit,
        ):
            raise InjectionMaterializerError("fresh worktree provenance cannot be verified")
        self._owned_worktrees[path] = _OwnedWorktreeRegistration(
            worktree=worktree,
            directory=registration.directory,
            administrative_directory=registration.administrative_directory,
        )
        self._fresh_worktrees.pop(path, None)

    def _is_verified_linked_worktree(
        self,
        path: Path,
        directory: _DirectoryAuthority,
        baseline_commit: str,
    ) -> bool:
        if not _authority_matches_path(directory):
            return False
        try:
            if _git_common_dir(path) != _git_common_dir(self._caller_checkout):
                return False
            if path not in self._registered_worktree_paths():
                return False
            head = _git_stdout(path, ["rev-parse", "HEAD"])
            if os.fsdecode(head) != baseline_commit:
                return False
            return _run_git(path, ["symbolic-ref", "-q", "HEAD"]).returncode != 0
        except (OSError, subprocess.TimeoutExpired, InjectionMaterializerError):
            return False

    def _dispose_owned_directories(
        self,
        directory: _DirectoryAuthority,
        administrative_directory: _DirectoryAuthority,
    ) -> bool:
        """Remove retained source and Git administrative directories by descriptor."""
        return _remove_authorized_directory(directory) and _remove_authorized_directory(
            administrative_directory
        )

    def cleanup(self, receipt: InjectionReceipt) -> None:
        """Remove only the exact, verified worktree created by this materializer."""
        if not isinstance(receipt, InjectionReceipt) or receipt.outcome != "materialized":
            raise InjectionCleanupError("cleanup requires a materialized receipt")
        worktree = receipt.worktree
        if worktree is None:
            raise InjectionCleanupError("cleanup requires an owned worktree")
        path = Path(worktree.path)
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
        registration = self._owned_worktrees.get(path)
        if registration is None or registration.worktree != worktree:
            raise InjectionCleanupError(
                "cleanup worktree was not created by this materializer"
            )
        if not _authority_matches_path(registration.directory):
            raise InjectionCleanupError("owned worktree directory identity has changed")
        if not self._is_verified_linked_worktree(
            path,
            registration.directory,
            worktree.baseline_commit,
        ):
            raise InjectionCleanupError("owned worktree provenance has changed")
        try:
            current_result_tree = _source_tree_sha256_from_index(path)
        except InjectionMaterializerError as error:
            raise InjectionCleanupError("owned worktree source cannot be verified") from error
        if current_result_tree != receipt.result_source_tree_sha256:
            raise InjectionCleanupError("owned worktree source identity has changed")
        try:
            current_worktree_tree = source_tree_sha256_from_worktree(path)
        except InjectionMaterializerError as error:
            raise InjectionCleanupError("owned worktree source cannot be verified") from error
        if current_worktree_tree != receipt.result_source_tree_sha256:
            raise InjectionCleanupError("owned worktree source identity has changed")

        if not self._dispose_owned_directories(
            registration.directory,
            registration.administrative_directory,
        ):
            raise InjectionCleanupError("owned worktree removal failed")
        self._owned_worktrees.pop(path, None)
        _close_directory_authority(registration.directory)
        _close_directory_authority(registration.administrative_directory)

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


def _git_directory(repository: Path) -> Path:
    raw = _git_stdout(repository, ["rev-parse", "--git-dir"])
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
