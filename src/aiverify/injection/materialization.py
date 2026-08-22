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
)


_OWNERSHIP_MARKER = ".aiverify-injection-ownership.json"
_GIT_TIMEOUT_SECONDS = 30
_GIT_IDENTITY_CONFIG = (
    "-c",
    "core.autocrlf=false",
    "-c",
    "core.eol=lf",
    "-c",
    f"core.attributesFile={os.devnull}",
    "-c",
    f"core.hooksPath={os.devnull}",
    "-c",
    "core.fsmonitor=false",
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
    "diff.suppressBlankEmpty=false",
    "-c",
    "diff.context=3",
    "-c",
    "diff.interHunkContext=0",
)
_CANONICAL_STAGED_DIFF_OPTIONS = (
    "--cached",
    "--binary",
    "--text",
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
class _GitControlFileAuthority:
    """Identity of a linked worktree's `.git` control file."""

    device: int
    inode: int


@dataclass
class _OwnedWorktreeRegistration:
    """Non-serializable authority retained only by the creating materializer."""

    worktree: MaterializedWorktree
    directory: _DirectoryAuthority
    administrative_directory: _DirectoryAuthority
    git_control_file: _GitControlFileAuthority
    private_index: str
    administrative_cleared: bool = False
    source_cleared: bool = False


@dataclass(frozen=True)
class _FreshWorktreeRegistration:
    """Non-serializable authority for a worktree before materialization succeeds."""

    baseline_commit: str
    directory: _DirectoryAuthority
    administrative_directory: _DirectoryAuthority
    git_control_file: _GitControlFileAuthority
    private_index: str


def _run_git(
    repository: Path,
    arguments: list[str],
    *,
    input_bytes: bytes | None = None,
    git_directory: Path | None = None,
    index_file: Path | str | None = None,
    working_directory_descriptor: int | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run Git without a shell or an interactive credential prompt.

    A bound linked worktree runs with the retained administrative directory as
    its process working directory.  macOS cannot safely use an open directory
    through `/dev/fd/<n>` as a pathname, so the child changes directory through
    that descriptor immediately before exec.  Git then sees only relative
    `--git-dir=.` and `--work-tree=.` paths rooted at the held directory.
    """
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
    if index_file is not None:
        # This is deliberately the sole GIT_* variable we introduce.  A
        # private index prevents another process using the linked worktree's
        # normal index from adding an undeclared delta to this materialization.
        environment["GIT_INDEX_FILE"] = os.fspath(index_file)
    command = [
        "git",
        *_GIT_IDENTITY_CONFIG,
        "-c",
        "core.bare=false",
    ]
    if working_directory_descriptor is None:
        command.extend(["-C", os.fspath(repository)])
        command.append(f"--work-tree={os.fspath(repository)}")
    else:
        # Do not pass a caller-controlled worktree pathname after binding its
        # administrative directory.  The commands issued here are index/tree
        # operations; source population stays descriptor-relative below.
        command.append("--work-tree=.")
    if git_directory is not None:
        # Never discover a fresh worktree's Git directory through its mutable
        # `.git` control file after registration.
        command.append(f"--git-dir={os.fspath(git_directory)}")
    run_options: dict[str, Any] = {}
    if working_directory_descriptor is not None:
        descriptor = working_directory_descriptor

        def enter_bound_directory() -> None:
            os.fchdir(descriptor)

        # Keep the descriptor open across fork/exec.  `enter_bound_directory`
        # runs before Git can resolve either relative control path.
        run_options = {
            "preexec_fn": enter_bound_directory,
            "pass_fds": (descriptor,),
        }
    return subprocess.run(
        [*command, *arguments],
        input=input_bytes,
        capture_output=True,
        check=False,
        env=environment,
        timeout=_GIT_TIMEOUT_SECONDS,
        **run_options,
    )


def _git_stdout(
    repository: Path,
    arguments: list[str],
    *,
    git_directory: Path | None = None,
    index_file: Path | str | None = None,
    working_directory_descriptor: int | None = None,
) -> bytes:
    run_options: dict[str, Any] = {
        "git_directory": git_directory,
        "index_file": index_file,
    }
    if working_directory_descriptor is not None:
        run_options["working_directory_descriptor"] = working_directory_descriptor
    result = _run_git(
        repository,
        arguments,
        **run_options,
    )
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


def _source_tree_sha256_for_tree(
    repository: Path,
    treeish: str,
    *,
    git_directory: Path | None = None,
    working_directory_descriptor: int | None = None,
) -> str:
    """Hash tracked Git blobs from a commit or tree object."""
    return _hash_source_entries(
        _source_tree_entries_for_tree(
            repository,
            treeish,
            git_directory=git_directory,
            working_directory_descriptor=working_directory_descriptor,
        )
    )


def _source_tree_entries_for_tree(
    repository: Path,
    treeish: str,
    *,
    git_directory: Path | None = None,
    working_directory_descriptor: int | None = None,
) -> list[tuple[bytes, bytes, bool, bytes]]:
    """Read supported source entries from a Git commit or tree object."""
    try:
        listing = _git_stdout(
            repository,
            ["ls-tree", "-r", "-z", "--full-tree", treeish],
            git_directory=git_directory,
            working_directory_descriptor=working_directory_descriptor,
        )
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
            run_options: dict[str, Any] = {"git_directory": git_directory}
            if working_directory_descriptor is not None:
                run_options["working_directory_descriptor"] = working_directory_descriptor
            blob = _run_git(
                repository,
                ["cat-file", "blob", os.fsdecode(object_id)],
                **run_options,
            )
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


def _index_treeish(
    worktree: Path,
    *,
    git_directory: Path | None = None,
    index_file: Path | str | None = None,
    working_directory_descriptor: int | None = None,
) -> str:
    try:
        tree = _git_stdout(
            worktree,
            ["write-tree"],
            git_directory=git_directory,
            index_file=index_file,
            working_directory_descriptor=working_directory_descriptor,
        )
    except (OSError, subprocess.TimeoutExpired, InjectionMaterializerError) as error:
        raise InjectionMaterializerError("worktree index cannot be read") from error
    if not tree:
        raise InjectionMaterializerError("worktree index cannot be read")
    return os.fsdecode(tree)


def _source_tree_sha256_from_index(
    worktree: Path,
    *,
    git_directory: Path | None = None,
    index_file: Path | str | None = None,
    working_directory_descriptor: int | None = None,
) -> str:
    """Hash the exact tracked source tree staged in a worktree index."""
    return _source_tree_sha256_for_tree(
        worktree,
        _index_treeish(
            worktree,
            git_directory=git_directory,
            index_file=index_file,
            working_directory_descriptor=working_directory_descriptor,
        ),
        git_directory=git_directory,
        working_directory_descriptor=working_directory_descriptor,
    )


def _populate_worktree_from_tree(
    worktree: Path,
    worktree_descriptor: int,
    treeish: str,
    *,
    git_directory: Path,
    working_directory_descriptor: int | None = None,
) -> None:
    """Write an exact Git tree without checkout filters or path traversal."""
    if any(entry.name != ".git" for entry in os.scandir(worktree_descriptor)):
        raise InjectionMaterializerError("fresh worktree contains unexpected source")

    for path, kind, executable, payload in _source_tree_entries_for_tree(
        worktree,
        treeish,
        git_directory=git_directory,
        working_directory_descriptor=working_directory_descriptor,
    ):
        components = _source_entry_components(path)
        parent_descriptor = _open_source_parent_directory(
            worktree_descriptor,
            components[:-1],
        )
        try:
            _write_source_entry(
                parent_descriptor,
                components[-1],
                kind,
                executable,
                payload,
            )
        finally:
            os.close(parent_descriptor)


def _source_entry_components(source_path: bytes) -> tuple[str, ...]:
    components = source_path.split(b"/")
    if not components or any(
        component in {b"", b".", b".."} for component in components
    ):
        raise InjectionMaterializerError("source tree has unsafe path")
    if components[0] == b".git":
        raise InjectionMaterializerError("source tree reserves Git control path")
    return tuple(os.fsdecode(component) for component in components)


def _open_source_parent_directory(
    worktree_descriptor: int,
    components: tuple[str, ...],
) -> int:
    """Open or create a source parent through held directory descriptors."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_descriptor = os.dup(worktree_descriptor)
    try:
        for component in components:
            try:
                child_descriptor = os.open(component, flags, dir_fd=directory_descriptor)
            except FileNotFoundError:
                try:
                    os.mkdir(component, mode=0o755, dir_fd=directory_descriptor)
                except FileExistsError:
                    pass
                child_descriptor = os.open(component, flags, dir_fd=directory_descriptor)
            except OSError as error:
                raise InjectionMaterializerError(
                    "source tree has colliding paths"
                ) from error
            os.close(directory_descriptor)
            directory_descriptor = child_descriptor
    except Exception:
        os.close(directory_descriptor)
        raise
    return directory_descriptor


def _write_source_entry(
    parent_descriptor: int,
    name: str,
    kind: bytes,
    executable: bool,
    payload: bytes,
) -> None:
    if kind == b"file":
        try:
            descriptor = os.open(
                name,
                os.O_CREAT
                | os.O_EXCL
                | os.O_WRONLY
                | getattr(os, "O_NOFOLLOW", 0),
                0o755 if executable else 0o644,
                dir_fd=parent_descriptor,
            )
        except OSError as error:
            raise InjectionMaterializerError("source tree contains colliding paths") from error
        try:
            os.fchmod(descriptor, 0o755 if executable else 0o644)
            with os.fdopen(descriptor, "wb") as destination:
                destination.write(payload)
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise
    elif kind == b"symlink":
        try:
            os.symlink(os.fsdecode(payload), name, dir_fd=parent_descriptor)
        except (OSError, ValueError) as error:
            raise InjectionMaterializerError("source tree has invalid symlink") from error
    else:
        raise InjectionMaterializerError("source tree has unsupported entry")


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


def _absolute_lexical_path(path: Path) -> Path:
    """Normalize `.`/`..` without resolving any untrusted symlink."""
    return Path(os.path.abspath(os.fspath(path)))


def _read_regular_file_from_directory(
    directory: _DirectoryAuthority,
    name: str,
) -> tuple[os.stat_result, bytes]:
    """Read one non-symlink regular file through a retained directory FD."""
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory.descriptor,
        )
    except OSError as error:
        raise InjectionMaterializerError("linked worktree control file is unavailable") from error
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise InjectionMaterializerError("linked worktree control file is invalid")
        with os.fdopen(descriptor, "rb") as source:
            return details, source.read()
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def _gitdir_path_from_control_contents(contents: bytes, *, directory: Path) -> Path:
    """Parse the `gitdir: …` form used by a linked worktree's `.git` file."""
    first_line, separator, trailing = contents.partition(b"\n")
    if not separator or trailing or not first_line.startswith(b"gitdir: "):
        raise InjectionMaterializerError("linked worktree control file is invalid")
    value = first_line[len(b"gitdir: ") :]
    if not value or b"\0" in value:
        raise InjectionMaterializerError("linked worktree control file is invalid")
    target = Path(os.fsdecode(value))
    return _absolute_lexical_path(target if target.is_absolute() else directory / target)


def _gitdir_path_from_administrative_contents(
    contents: bytes,
    *,
    directory: Path,
) -> Path:
    """Parse an administrative worktree's `gitdir` backlink safely."""
    value = contents.rstrip(b"\n")
    if not value or b"\n" in value or b"\0" in value:
        raise InjectionMaterializerError("linked worktree administrative metadata is invalid")
    target = Path(os.fsdecode(value))
    return _absolute_lexical_path(target if target.is_absolute() else directory / target)


def _administrative_gitdir_target(directory: _DirectoryAuthority) -> Path:
    _, contents = _read_regular_file_from_directory(directory, "gitdir")
    return _gitdir_path_from_administrative_contents(
        contents,
        directory=directory.path,
    )


def _expected_control_file_path(directory: _DirectoryAuthority) -> Path:
    return _absolute_lexical_path(directory.path / ".git")


def _find_linked_worktree_administrative_directory(
    common_directory: Path,
    worktree_directory: _DirectoryAuthority,
) -> _DirectoryAuthority:
    """Bind the admin directory created for this held source directory.

    The scan uses the common Git directory's backlinks rather than the mutable
    `.git` file in the fresh worktree.  Consequently a post-creation control
    file swap cannot redirect registration to another linked worktree.
    """
    if not _authority_matches_path(worktree_directory):
        raise InjectionMaterializerError("fresh worktree directory identity has changed")
    administrative_root = common_directory / "worktrees"
    expected_control_path = _expected_control_file_path(worktree_directory)
    matches: list[_DirectoryAuthority] = []
    try:
        entries = list(os.scandir(administrative_root))
    except OSError as error:
        raise InjectionMaterializerError(
            "linked worktree administrative directory is unavailable"
        ) from error
    try:
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            try:
                authority = _open_directory_authority(Path(entry.path))
            except (OSError, InjectionMaterializerError):
                continue
            try:
                if _administrative_gitdir_target(authority) == expected_control_path:
                    matches.append(authority)
                else:
                    _close_directory_authority(authority)
            except InjectionMaterializerError:
                _close_directory_authority(authority)
        if len(matches) != 1:
            raise InjectionMaterializerError("fresh worktree administrative path is unsafe")
        return matches[0]
    except Exception:
        for authority in matches:
            _close_directory_authority(authority)
        raise


def _bind_git_control_file(
    directory: _DirectoryAuthority,
    administrative_directory: _DirectoryAuthority,
) -> _GitControlFileAuthority:
    """Bind `.git` to the independently discovered administrative directory."""
    if not _authority_matches_path(directory) or not _authority_matches_path(
        administrative_directory
    ):
        raise InjectionMaterializerError("fresh worktree directory identity has changed")
    details, contents = _read_regular_file_from_directory(directory, ".git")
    if _gitdir_path_from_control_contents(contents, directory=directory.path) != (
        administrative_directory.path
    ):
        raise InjectionMaterializerError("fresh worktree Git control path has changed")
    return _GitControlFileAuthority(device=details.st_dev, inode=details.st_ino)


def _git_control_file_matches(
    directory: _DirectoryAuthority,
    administrative_directory: _DirectoryAuthority,
    control_file: _GitControlFileAuthority,
) -> bool:
    """Ensure the worktree control file still names its retained admin directory."""
    if not _authority_matches_path(directory) or not _authority_matches_path(
        administrative_directory
    ):
        return False
    try:
        details, contents = _read_regular_file_from_directory(directory, ".git")
        return (
            (details.st_dev, details.st_ino)
            == (control_file.device, control_file.inode)
            and _gitdir_path_from_control_contents(contents, directory=directory.path)
            == administrative_directory.path
            and _administrative_gitdir_target(administrative_directory)
            == _expected_control_file_path(directory)
        )
    except InjectionMaterializerError:
        return False


def _write_ownership_marker(
    directory: _DirectoryAuthority,
    contents: bytes,
) -> None:
    """Create the ownership marker through the retained worktree descriptor."""
    if not _authority_matches_path(directory):
        raise InjectionMaterializerError("worktree directory identity has changed")
    try:
        os.stat(
            _OWNERSHIP_MARKER,
            dir_fd=directory.descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        pass
    except OSError as error:
        raise InjectionMaterializerError("ownership marker cannot be inspected") from error
    else:
        raise InjectionMaterializerError("reserved ownership path")

    try:
        descriptor = os.open(
            _OWNERSHIP_MARKER,
            os.O_CREAT
            | os.O_EXCL
            | os.O_WRONLY
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory.descriptor,
        )
    except OSError as error:
        raise InjectionMaterializerError("ownership marker cannot be written") from error
    try:
        with os.fdopen(descriptor, "wb") as marker:
            marker.write(contents)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


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
        # `rmdir(name, dir_fd=descriptor)` would resolve the child again after
        # its descriptor check, so a concurrent replacement could be deleted.
        # Empty source directories are inert once their files and Git metadata
        # are gone; retain them rather than target a pathname a second time.


def _clear_authorized_directory_contents(authority: _DirectoryAuthority) -> bool:
    """Clear only an opened directory's contents; retain its pathname safely."""
    try:
        _remove_directory_contents(authority.descriptor)
        if not _authority_matches_path(authority):
            return False
    except OSError:
        return False
    return True


def _reserve_worktree_directory(path: Path) -> _DirectoryAuthority:
    """Create and bind the disposable directory before Git can populate it."""
    path.mkdir(mode=0o700)
    try:
        return _open_directory_authority(path)
    except (OSError, InjectionMaterializerError):
        # Until a descriptor proves the fresh directory's identity, a pathname
        # cleanup could remove a concurrent replacement.  Preserve it and fail
        # closed instead.
        raise


def _release_reserved_directory(authority: _DirectoryAuthority) -> bool:
    """Clear an unpopulated reservation if its retained identity remains ours."""
    try:
        return _clear_authorized_directory_contents(authority)
    finally:
        _close_directory_authority(authority)


def _new_private_index_name(administrative_directory: _DirectoryAuthority) -> str:
    """Choose an unallocated relative index name in the retained admin directory."""
    if not _authority_matches_path(administrative_directory):
        raise InjectionMaterializerError("linked worktree administrative directory changed")
    for _ in range(8):
        name = f"aiverify-materialization-index-{uuid4().hex}"
        try:
            os.stat(name, dir_fd=administrative_directory.descriptor, follow_symlinks=False)
        except FileNotFoundError:
            # A relative name is resolved only after Git enters the retained
            # admin-directory descriptor; retaining an absolute pathname here
            # would reopen a replaceable path later.
            return name
        except OSError as error:
            raise InjectionMaterializerError(
                "linked worktree administrative directory is unavailable"
            ) from error
    raise InjectionMaterializerError("private worktree index name is unavailable")


class InjectionMaterializer:
    """Create and clean only fresh, detached, materializer-owned worktrees."""

    def __init__(self, caller_checkout: str | Path, worktree_root: str | Path) -> None:
        self._caller_checkout = _repository_root(caller_checkout)
        try:
            self._caller_common_directory = _git_common_dir(self._caller_checkout)
        except (OSError, subprocess.TimeoutExpired, InjectionMaterializerError) as error:
            raise InjectionMaterializerError("caller_checkout must be a Git worktree") from error
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
            recovered = self._recover_interrupted_worktree_add(
                worktree_path,
                resolved_commit,
                reserved_directory,
            )
            return InjectionReceipt.rejected(
                candidate,
                "caller_checkout_unavailable"
                if recovered
                else "worktree_cleanup_failed",
            )
        if created.returncode != 0:
            recovered = self._recover_interrupted_worktree_add(
                worktree_path,
                resolved_commit,
                reserved_directory,
            )
            return InjectionReceipt.rejected(
                candidate,
                "worktree_creation_failed"
                if recovered
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
            _close_directory_authority(reserved_directory)
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

    def _has_bound_worktree_controls(
        self,
        path: Path,
        directory: _DirectoryAuthority,
        administrative_directory: _DirectoryAuthority,
        control_file: _GitControlFileAuthority,
    ) -> bool:
        return (
            _absolute_lexical_path(path) == directory.path
            and _git_control_file_matches(
                directory,
                administrative_directory,
                control_file,
            )
        )

    def _run_bound_worktree_git(
        self,
        path: Path,
        directory: _DirectoryAuthority,
        administrative_directory: _DirectoryAuthority,
        control_file: _GitControlFileAuthority,
        arguments: list[str],
        *,
        input_bytes: bytes | None = None,
        private_index: str | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        """Run Git from the retained admin directory, never path discovery."""
        if not self._has_bound_worktree_controls(
            path,
            directory,
            administrative_directory,
            control_file,
        ):
            raise InjectionMaterializerError("fresh worktree Git control path has changed")
        return _run_git(
            path,
            arguments,
            input_bytes=input_bytes,
            git_directory=Path("."),
            index_file=private_index,
            working_directory_descriptor=administrative_directory.descriptor,
        )

    def _bound_worktree_git_stdout(
        self,
        path: Path,
        directory: _DirectoryAuthority,
        administrative_directory: _DirectoryAuthority,
        control_file: _GitControlFileAuthority,
        arguments: list[str],
        *,
        private_index: str | None = None,
    ) -> bytes:
        result = self._run_bound_worktree_git(
            path,
            directory,
            administrative_directory,
            control_file,
            arguments,
            private_index=private_index,
        )
        if result.returncode != 0:
            raise InjectionMaterializerError("Git inspection failed")
        return result.stdout.rstrip(b"\n")

    def _apply_in_fresh_worktree(
        self,
        candidate: InjectionCandidate,
        worktree_path: Path,
        resolved_commit: str,
    ) -> InjectionReceipt:
        registration = self._fresh_worktrees.get(worktree_path)
        if registration is None or not self._is_verified_linked_worktree(
            worktree_path,
            registration.directory,
            registration.administrative_directory,
            registration.git_control_file,
            resolved_commit,
        ):
            return self._reject_and_discard(
                candidate,
                worktree_path,
                "worktree_provenance_mismatch",
            )
        initialized = self._run_bound_worktree_git(
            worktree_path,
            registration.directory,
            registration.administrative_directory,
            registration.git_control_file,
            ["read-tree", resolved_commit],
            private_index=registration.private_index,
        )
        if initialized.returncode != 0:
            return self._reject_and_discard(
                candidate,
                worktree_path,
                "worktree_provenance_mismatch",
            )
        current_tree = _source_tree_sha256_from_index(
            worktree_path,
            git_directory=Path("."),
            index_file=registration.private_index,
            working_directory_descriptor=registration.administrative_directory.descriptor,
        )
        if current_tree != candidate.baseline.source_tree_sha256:
            return self._reject_and_discard(
                candidate,
                worktree_path,
                "worktree_provenance_mismatch",
            )
        if any(
            entry.name != ".git" for entry in os.scandir(registration.directory.descriptor)
        ):
            return self._reject_and_discard(
                candidate,
                worktree_path,
                "worktree_provenance_mismatch",
            )

        patch_bytes = candidate.source_delta.patch_text.encode("utf-8")
        # M0.1's executable applicability boundary is one delta against the
        # declared immutable baseline, not interpretation of operator metadata.
        check = self._run_bound_worktree_git(
            worktree_path,
            registration.directory,
            registration.administrative_directory,
            registration.git_control_file,
            [
                "apply",
                "--cached",
                "--check",
                "--no-ignore-whitespace",
                "--whitespace=nowarn",
                "-",
            ],
            input_bytes=patch_bytes,
            private_index=registration.private_index,
        )
        if check.returncode != 0:
            return self._reject_and_discard(candidate, worktree_path, "patch_not_applicable")
        applied = self._run_bound_worktree_git(
            worktree_path,
            registration.directory,
            registration.administrative_directory,
            registration.git_control_file,
            [
                "apply",
                "--cached",
                "--no-ignore-whitespace",
                "--whitespace=nowarn",
                "-",
            ],
            input_bytes=patch_bytes,
            private_index=registration.private_index,
        )
        if applied.returncode != 0:
            return self._reject_and_discard(candidate, worktree_path, "patch_apply_failed")

        result_tree = _index_treeish(
            worktree_path,
            git_directory=Path("."),
            index_file=registration.private_index,
            working_directory_descriptor=registration.administrative_directory.descriptor,
        )
        result_tree_sha256 = _source_tree_sha256_for_tree(
            worktree_path,
            result_tree,
            git_directory=Path("."),
            working_directory_descriptor=registration.administrative_directory.descriptor,
        )
        if result_tree_sha256 == candidate.baseline.source_tree_sha256:
            return self._reject_and_discard(candidate, worktree_path, "patch_did_not_change_source")
        diff = self._run_bound_worktree_git(
            worktree_path,
            registration.directory,
            registration.administrative_directory,
            registration.git_control_file,
            [
                "diff",
                *_CANONICAL_STAGED_DIFF_OPTIONS,
                resolved_commit,
                "--",
            ],
            private_index=registration.private_index,
        )
        if diff.returncode != 0:
            return self._reject_and_discard(candidate, worktree_path, "result_identity_failed")
        if not diff.stdout:
            return self._reject_and_discard(candidate, worktree_path, "patch_did_not_change_source")
        if (
            _index_treeish(
                worktree_path,
                git_directory=Path("."),
                index_file=registration.private_index,
                working_directory_descriptor=registration.administrative_directory.descriptor,
            )
            != result_tree
        ):
            return self._reject_and_discard(candidate, worktree_path, "result_identity_failed")
        _populate_worktree_from_tree(
            worktree_path,
            registration.directory.descriptor,
            result_tree,
            git_directory=Path("."),
            working_directory_descriptor=registration.administrative_directory.descriptor,
        )
        if (
            source_tree_sha256_from_worktree(
                worktree_path,
                ignore_ownership_marker=False,
            )
            != result_tree_sha256
        ):
            return self._reject_and_discard(candidate, worktree_path, "result_identity_failed")
        # The receipt trusts only the private index above, but a successful
        # materialized Git worktree should still expose that exact verified
        # tree through its normal Git index.  A concurrent later update to the
        # normal index cannot affect the receipt or cleanup verification.
        synchronized = self._run_bound_worktree_git(
            worktree_path,
            registration.directory,
            registration.administrative_directory,
            registration.git_control_file,
            ["read-tree", result_tree],
        )
        if synchronized.returncode != 0 or (
            _index_treeish(
                worktree_path,
                git_directory=Path("."),
                working_directory_descriptor=registration.administrative_directory.descriptor,
            )
            != result_tree
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
        if not self._has_bound_worktree_controls(
            worktree_path,
            registration.directory,
            registration.administrative_directory,
            registration.git_control_file,
        ):
            return self._reject_and_discard(candidate, worktree_path, "result_identity_failed")
        _write_ownership_marker(
            registration.directory,
            self._marker_bytes(owned_worktree),
        )
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
            self._promote_fresh_worktree(
                owned_worktree,
                result_tree,
                result_tree_sha256,
            )
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
        try:
            if not self._is_verified_linked_worktree(
                path,
                registration.directory,
                registration.administrative_directory,
                registration.git_control_file,
                registration.baseline_commit,
            ):
                return False
            return self._dispose_owned_directories(
                registration.directory,
                registration.administrative_directory,
            )
        finally:
            # A rejected receipt cannot expose this private authority for a
            # later retry.  Release its descriptors even when the filesystem
            # cleanup fails, leaving any unverified external state untouched.
            self._fresh_worktrees.pop(path, None)
            _close_directory_authority(registration.directory)
            _close_directory_authority(registration.administrative_directory)

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
            administrative_directory = _find_linked_worktree_administrative_directory(
                self._caller_common_directory,
                directory,
            )
            git_control_file = _bind_git_control_file(
                directory,
                administrative_directory,
            )
            private_index = _new_private_index_name(administrative_directory)
            if not self._is_verified_linked_worktree(
                path,
                directory,
                administrative_directory,
                git_control_file,
                baseline_commit,
            ):
                raise InjectionMaterializerError("fresh worktree provenance cannot be verified")
        except Exception:
            if administrative_directory is not None:
                _close_directory_authority(administrative_directory)
            raise
        self._fresh_worktrees[path] = _FreshWorktreeRegistration(
            baseline_commit=baseline_commit,
            directory=directory,
            administrative_directory=administrative_directory,
            git_control_file=git_control_file,
            private_index=private_index,
        )

    def _recover_interrupted_worktree_add(
        self,
        worktree_path: Path,
        baseline_commit: str,
        directory: _DirectoryAuthority,
    ) -> bool:
        """Recover only when an interrupted add can be verified and discarded."""
        try:
            self._register_fresh_worktree(worktree_path, baseline_commit, directory)
        except (OSError, subprocess.TimeoutExpired, InjectionMaterializerError):
            try:
                registered = worktree_path.resolve() in self._registered_worktree_paths()
            except (OSError, subprocess.TimeoutExpired, InjectionMaterializerError):
                _close_directory_authority(directory)
                return False
            if registered:
                _close_directory_authority(directory)
                return False
            return _release_reserved_directory(directory)
        return self._discard_fresh_worktree(worktree_path)

    def _promote_fresh_worktree(
        self,
        worktree: MaterializedWorktree,
        result_tree: str,
        result_source_tree_sha256: str,
    ) -> None:
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
            registration.administrative_directory,
            registration.git_control_file,
            worktree.baseline_commit,
        ):
            raise InjectionMaterializerError("fresh worktree provenance cannot be verified")
        if (
            _index_treeish(
                path,
                git_directory=Path("."),
                index_file=registration.private_index,
                working_directory_descriptor=registration.administrative_directory.descriptor,
            )
            != result_tree
        ):
            raise InjectionMaterializerError("fresh worktree source identity has changed")
        if (
            _source_tree_sha256_for_tree(
                path,
                result_tree,
                git_directory=Path("."),
                working_directory_descriptor=registration.administrative_directory.descriptor,
            )
            != result_source_tree_sha256
        ):
            raise InjectionMaterializerError("fresh worktree source identity has changed")
        if source_tree_sha256_from_worktree(path) != result_source_tree_sha256:
            raise InjectionMaterializerError("fresh worktree source identity has changed")
        try:
            marker_descriptor = os.open(
                _OWNERSHIP_MARKER,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=registration.directory.descriptor,
            )
        except OSError as error:
            raise InjectionMaterializerError("fresh worktree marker is unavailable") from error
        try:
            with os.fdopen(marker_descriptor, "rb") as marker:
                marker_bytes = marker.read()
        except Exception:
            try:
                os.close(marker_descriptor)
            except OSError:
                pass
            raise
        if marker_bytes != self._marker_bytes(worktree):
            raise InjectionMaterializerError("fresh worktree marker has changed")
        self._owned_worktrees[path] = _OwnedWorktreeRegistration(
            worktree=worktree,
            directory=registration.directory,
            administrative_directory=registration.administrative_directory,
            git_control_file=registration.git_control_file,
            private_index=registration.private_index,
        )
        self._fresh_worktrees.pop(path, None)

    def _is_verified_linked_worktree(
        self,
        path: Path,
        directory: _DirectoryAuthority,
        administrative_directory: _DirectoryAuthority,
        control_file: _GitControlFileAuthority,
        baseline_commit: str,
    ) -> bool:
        if not self._has_bound_worktree_controls(
            path,
            directory,
            administrative_directory,
            control_file,
        ):
            return False
        try:
            if (
                _git_common_dir(
                    path,
                    git_directory=Path("."),
                    working_directory_descriptor=administrative_directory.descriptor,
                    require_absolute=True,
                )
                != self._caller_common_directory
            ):
                return False
            if path not in self._registered_worktree_paths():
                return False
            head = self._bound_worktree_git_stdout(
                path,
                directory,
                administrative_directory,
                control_file,
                ["rev-parse", "HEAD"],
            )
            if os.fsdecode(head) != baseline_commit:
                return False
            return (
                self._run_bound_worktree_git(
                    path,
                    directory,
                    administrative_directory,
                    control_file,
                    ["symbolic-ref", "-q", "HEAD"],
                ).returncode
                != 0
            )
        except (OSError, subprocess.TimeoutExpired, InjectionMaterializerError):
            return False

    def _dispose_owned_directories(
        self,
        directory: _DirectoryAuthority,
        administrative_directory: _DirectoryAuthority,
    ) -> bool:
        """Clear fresh-only directories by descriptor, never by pathname."""
        return _clear_authorized_directory_contents(
            administrative_directory
        ) and _clear_authorized_directory_contents(directory)

    def _verify_visible_ownership_marker(
        self,
        path: Path,
        worktree: MaterializedWorktree,
    ) -> None:
        if path.parent != self._worktree_root or not path.is_dir() or path.is_symlink():
            raise InjectionCleanupError("cleanup path is not a materializer-owned child")
        marker_path = path / _OWNERSHIP_MARKER
        try:
            marker_bytes = marker_path.read_bytes()
        except OSError as error:
            raise InjectionCleanupError("owned worktree marker is unavailable") from error
        if marker_bytes != self._marker_bytes(worktree):
            raise InjectionCleanupError("owned worktree marker does not match receipt")

    def _verify_owned_worktree_for_initial_cleanup(
        self,
        receipt: InjectionReceipt,
        registration: _OwnedWorktreeRegistration,
    ) -> None:
        worktree = receipt.worktree
        assert worktree is not None
        path = Path(worktree.path)
        self._verify_visible_ownership_marker(path, worktree)
        if not _authority_matches_path(registration.directory):
            raise InjectionCleanupError("owned worktree directory identity has changed")
        if not self._is_verified_linked_worktree(
            path,
            registration.directory,
            registration.administrative_directory,
            registration.git_control_file,
            worktree.baseline_commit,
        ):
            raise InjectionCleanupError("owned worktree provenance has changed")
        try:
            current_result_tree = _source_tree_sha256_from_index(
                path,
                git_directory=Path("."),
                index_file=registration.private_index,
                working_directory_descriptor=registration.administrative_directory.descriptor,
            )
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

    def _continue_owned_cleanup(
        self,
        registration: _OwnedWorktreeRegistration,
    ) -> bool:
        """Finish descriptor-only cleanup, retaining enough state for retry."""
        if not registration.administrative_cleared:
            if not _clear_authorized_directory_contents(
                registration.administrative_directory
            ):
                return False
            registration.administrative_cleared = True
        if not registration.source_cleared:
            if not _clear_authorized_directory_contents(registration.directory):
                return False
            registration.source_cleared = True
        return True

    def cleanup(self, receipt: InjectionReceipt) -> None:
        """Remove only the exact, verified worktree created by this materializer."""
        if not isinstance(receipt, InjectionReceipt) or receipt.outcome != "materialized":
            raise InjectionCleanupError("cleanup requires a materialized receipt")
        worktree = receipt.worktree
        if worktree is None:
            raise InjectionCleanupError("cleanup requires an owned worktree")
        path = Path(worktree.path)
        if worktree.candidate_identity_sha256 != receipt.candidate_identity_sha256:
            raise InjectionCleanupError("owned worktree candidate identity does not match")
        if worktree.result_identity_sha256 != receipt.result_identity_sha256:
            raise InjectionCleanupError("owned worktree result identity does not match")
        registration = self._owned_worktrees.get(path)
        if registration is None or registration.worktree != worktree:
            # Preserve useful diagnostics for forged receipts without granting
            # them any descriptor authority.
            self._verify_visible_ownership_marker(path, worktree)
            raise InjectionCleanupError(
                "cleanup worktree was not created by this materializer"
            )
        if not (
            registration.administrative_cleared or registration.source_cleared
        ):
            self._verify_owned_worktree_for_initial_cleanup(receipt, registration)

        if not self._continue_owned_cleanup(registration):
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


def _git_common_dir(
    repository: Path,
    *,
    git_directory: Path | None = None,
    working_directory_descriptor: int | None = None,
    require_absolute: bool = False,
) -> Path:
    raw = _git_stdout(
        repository,
        ["rev-parse", "--git-common-dir"],
        git_directory=git_directory,
        working_directory_descriptor=working_directory_descriptor,
    )
    path = Path(os.fsdecode(raw))
    if require_absolute and not path.is_absolute():
        raise InjectionMaterializerError("bound Git common directory is unavailable")
    return path.resolve() if path.is_absolute() else (repository / path).resolve()


__all__ = [
    "InjectionCleanupError",
    "InjectionMaterializer",
    "InjectionMaterializerError",
    "capture_baseline_provenance",
    "source_tree_sha256_for_commit",
    "source_tree_sha256_from_worktree",
]
