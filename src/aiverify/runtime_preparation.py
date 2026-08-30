"""Source-authorized, non-runtime preparation for one runner handoff."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import time
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from subprocess import TimeoutExpired
from types import MappingProxyType

from aiverify.bench.runtime_mapping import (
    RuntimeMappingRelease,
    RuntimeSourceRequest,
    SourceAuthorityMapping,
    verify_runtime_mapping_release,
)
from aiverify.injection import (
    CuratedCatalogError,
    InjectionAdmission,
    InjectionContractError,
    InjectionMaterializerError,
    ProjectTargetPacket,
    VerifierPacket,
    inspect_materialized_receipt_source,
    load_curated_source_catalog,
    source_tree_sha256_for_commit,
)
from aiverify.runner.admission import (
    CleanCheckoutSourceAuthority,
    HostAuthority,
    HostWorktreeIdentity,
    PlannedRunnerOptions,
    ProductionSeamAdmissionError,
    SourceAuthority,
    SourceAuthorityBinding,
    admit_production_seam,
)
from aiverify.runner.command import (
    CommandResult,
    CommandRunner,
    SubprocessCommandRunner,
)
from aiverify.runner.run_spec import RunSpec, load_run_spec

_RUNTIME_VAULT_SCHEMA_VERSION = 1
_RUNTIME_VAULT_DOCUMENT_KIND = "runtime_input_vault_manifest"
_RUNTIME_VAULT_RETENTION_STATUS = "retained_through_evidence_review"
_RUNTIME_BUILD_TIMEOUT_SECONDS = 900
_RUNTIME_BUILD_OUTPUT_RELATIVE_PATH = "app/build/outputs/apk/debug/app-debug.apk"
_RUNTIME_BUILD_COMMAND = (
    "./gradlew",
    "--offline",
    "--no-daemon",
    "--no-build-cache",
    "--no-configuration-cache",
    "--max-workers=1",
    "--console=plain",
    "clean",
    ":app:assembleDebug",
)
_RUNTIME_ALLOWED_ENVIRONMENT_KEYS = frozenset(
    {
        "LANG",
        "LC_ALL",
        "TZ",
        "SOURCE_DATE_EPOCH",
        "PATH",
        "JAVA_HOME",
        "ANDROID_SDK_ROOT",
    }
)
_RUNTIME_PRIVATE_HOME_KEYS = (
    "HOME",
    "GRADLE_USER_HOME",
    "ANDROID_USER_HOME",
    "ANDROID_SDK_HOME",
    "TMPDIR",
)
_RUNTIME_SECRET_FIELD_NAMES = frozenset(
    {
        "credential",
        "credentials",
        "password",
        "private_key",
        "private_key_bytes",
        "secret",
        "secret_bytes",
    }
)
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


RUNTIME_PREPARATION_SCHEMA_VERSION = 1
RUNTIME_PREPARATION_CLAIM_BOUNDARY = "local_source_build_preparation_only"
_PROHIBITED_EXECUTABLES = frozenset(
    {
        "adb",
        "android",
        "bash",
        "cmd",
        "codex",
        "emulator",
        "fish",
        "powershell",
        "pwsh",
        "sh",
        "zsh",
    }
)
_GRADLE_EXECUTABLES = frozenset({"gradle", "gradlew", "gradlew.bat"})
_SAFE_GRADLE_FLAGS = frozenset(
    {
        "--build-cache",
        "--continue",
        "--no-build-cache",
        "--no-configuration-cache",
        "--no-daemon",
        "--no-parallel",
        "--no-scan",
        "--offline",
        "--parallel",
        "--quiet",
        "--rerun-tasks",
        "--stacktrace",
    }
)
_SAFE_GRADLE_FLAG_PREFIXES = (
    "--console=",
    "--max-workers=",
    "--warning-mode=",
)
_PACKAGE_LINE = re.compile(r"^package: name='([^']+)'", re.MULTILINE)
_PACKAGE_DETAILS_LINE = re.compile(
    r"^package: name='([^']+)' versionCode='([^']+)' versionName='([^']*)'",
    re.MULTILINE,
)
_ACTIVITY_LINE = re.compile(r"^launchable-activity: name='([^']+)'", re.MULTILINE)
_MIN_SDK_LINE = re.compile(r"^minSdkVersion:'([^']+)'", re.MULTILINE)
_TARGET_SDK_LINE = re.compile(r"^targetSdkVersion:'([^']+)'", re.MULTILINE)
_COMPILE_SDK_LINE = re.compile(r"(?:^|\s)compileSdkVersion='?([^'\s]+)", re.MULTILINE)
_SIGNER_COUNT_LINE = re.compile(r"^Signer #([0-9]+) certificate", re.MULTILINE)
_SIGNER_DIGEST_LINE = re.compile(
    r"^Signer #1 certificate SHA-256 digest:\s*([0-9A-Fa-f:]+)", re.MULTILINE
)
_V1_LINE = re.compile(
    r"^Verified using v1 scheme \(JAR signing\):\s*(true|false)",
    re.MULTILINE | re.IGNORECASE,
)
_V2_LINE = re.compile(
    r"^Verified using v2 scheme \(APK Signature Scheme v2\):\s*(true|false)",
    re.MULTILINE | re.IGNORECASE,
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _identity(value: Mapping[str, object]) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _required_digest(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def _relative_inventory_path(
    value: object, *, field_name: str = "relative_path"
) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} is invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or "\\" in value
        or not path.parts
        or any(part in {"", ".", "..", ".git"} for part in path.parts)
    ):
        raise ValueError(f"{field_name} is invalid")
    return value


def _reject_secret_fields(value: object) -> None:
    """Reject private material if it is accidentally attached to a manifest."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            if isinstance(key, str) and key.lower() in _RUNTIME_SECRET_FIELD_NAMES:
                raise ValueError("runtime input manifest contains private material")
            _reject_secret_fields(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_secret_fields(child)


def _lstat(path: Path) -> os.stat_result:
    return path.lstat()


def _has_symlink_component(path: Path) -> bool:
    """Return whether a path or any existing parent is a symbolic link."""
    candidate = path if path.is_absolute() else Path.cwd() / path
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
    return False


def _require_read_only_regular_file(path: Path, *, code: str) -> os.stat_result:
    if _has_symlink_component(path):
        raise ValueError(code)
    try:
        details = _lstat(path)
    except OSError as error:
        raise ValueError(code) from error
    if (
        stat.S_ISLNK(details.st_mode)
        or not stat.S_ISREG(details.st_mode)
        or details.st_nlink != 1
        or details.st_mode & 0o222
    ):
        raise ValueError(code)
    return details


def _require_executable_regular_file(path: Path, *, code: str) -> os.stat_result:
    if _has_symlink_component(path):
        raise ValueError(code)
    try:
        details = _lstat(path)
    except OSError as error:
        raise ValueError(code) from error
    if (
        stat.S_ISLNK(details.st_mode)
        or not stat.S_ISREG(details.st_mode)
        or details.st_nlink != 1
        or not os.access(path, os.X_OK)
    ):
        raise ValueError(code)
    return details


def _resolve_vault_path(root: Path, value: Path) -> Path:
    root = root.resolve()
    if value.is_absolute():
        candidate = value
    else:
        candidate = root.joinpath(*PurePosixPath(value.as_posix()).parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise ValueError("runtime input vault path escapes its root") from error
    return resolved


@dataclass(frozen=True)
class RuntimeToolIdentity:
    """One checksum-bound executable used by the offline build or inspection."""

    name: str
    path: Path
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("runtime tool name is required")
        if not isinstance(self.path, Path) or not self.path.is_absolute():
            raise ValueError("runtime tool path must be absolute")
        if str(self.path.resolve()) != str(self.path):
            raise ValueError("runtime tool path must be canonical")
        _required_digest(self.sha256, field_name="runtime tool sha256")

    @classmethod
    def from_path(cls, name: str, path: str | Path) -> RuntimeToolIdentity:
        raw_path = Path(path).expanduser()
        _require_executable_regular_file(
            raw_path,
            code="runtime tool must be a regular executable file",
        )
        resolved = raw_path.resolve(strict=True)
        details = _require_executable_regular_file(
            resolved,
            code="runtime tool must be a regular executable file",
        )
        del details
        return cls(name=name, path=resolved, sha256=_sha256_file(resolved))

    def verify(self) -> None:
        details = _require_executable_regular_file(
            self.path,
            code="runtime tool drifted",
        )
        if _sha256_file(self.path) != self.sha256:
            raise ValueError("runtime tool drifted")
        del details

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "path": str(self.path), "sha256": self.sha256}


@dataclass(frozen=True)
class RuntimeBuildEnvironment:
    """Explicit environment policy for a private, offline build invocation."""

    variables: tuple[tuple[str, str], ...] = ()
    allowlist: tuple[str, ...] = (
        "ANDROID_SDK_ROOT",
        "JAVA_HOME",
        "LANG",
        "LC_ALL",
        "PATH",
        "SOURCE_DATE_EPOCH",
        "TZ",
    )
    private_home_keys: tuple[str, ...] = _RUNTIME_PRIVATE_HOME_KEYS

    def __post_init__(self) -> None:
        if not isinstance(self.variables, tuple) or any(
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not item[0]
            or not isinstance(item[1], str)
            or item[0] not in _RUNTIME_ALLOWED_ENVIRONMENT_KEYS
            for item in self.variables
        ):
            raise ValueError("runtime build environment variables are invalid")
        if len({item[0] for item in self.variables}) != len(self.variables):
            raise ValueError("runtime build environment variables must be unique")
        if tuple(sorted(self.variables)) != self.variables:
            raise ValueError("runtime build environment variables must be sorted")
        if tuple(sorted(self.allowlist)) != self.allowlist or set(
            self.allowlist
        ) != set(_RUNTIME_ALLOWED_ENVIRONMENT_KEYS):
            raise ValueError("runtime build environment allowlist is invalid")
        if (
            not isinstance(self.private_home_keys, tuple)
            or tuple(self.private_home_keys) != _RUNTIME_PRIVATE_HOME_KEYS
        ):
            raise ValueError("runtime build private homes are incomplete")

    @classmethod
    def default(cls) -> RuntimeBuildEnvironment:
        return cls(
            variables=(
                ("LANG", "C.UTF-8"),
                ("LC_ALL", "C.UTF-8"),
                ("TZ", "UTC"),
                ("SOURCE_DATE_EPOCH", "1783693058"),
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "variables": {name: value for name, value in self.variables},
            "allowlist": list(self.allowlist),
            "private_home_keys": list(self.private_home_keys),
        }

    @classmethod
    def from_dict(cls, data: object) -> RuntimeBuildEnvironment:
        if not isinstance(data, Mapping) or set(data) != {
            "variables",
            "allowlist",
            "private_home_keys",
        }:
            raise ValueError("runtime build recipe environment is invalid")
        variables = data["variables"]
        allowlist = data["allowlist"]
        private_home_keys = data["private_home_keys"]
        if (
            not isinstance(variables, Mapping)
            or not isinstance(allowlist, list)
            or not isinstance(private_home_keys, list)
            or any(
                not isinstance(name, str) or not isinstance(value, str)
                for name, value in variables.items()
            )
            or any(not isinstance(value, str) for value in allowlist)
            or any(not isinstance(value, str) for value in private_home_keys)
        ):
            raise ValueError("runtime build recipe environment is invalid")
        return cls(
            variables=tuple(sorted(variables.items())),
            allowlist=tuple(allowlist),
            private_home_keys=tuple(private_home_keys),
        )

    def materialize(self, private_root: Path) -> dict[str, str]:
        private_root = private_root.resolve()
        private_root.mkdir(parents=True, exist_ok=True)
        private_root.chmod(0o700)
        environment = {name: value for name, value in self.variables}
        for key in self.private_home_keys:
            home = private_root / key.lower().replace("_", "-")
            home.mkdir(parents=True, exist_ok=True)
            home.chmod(0o700)
            environment[key] = str(home)
        if set(environment) - set(self.allowlist) - set(self.private_home_keys):
            raise ValueError("runtime build environment is outside its allowlist")
        return environment


@dataclass(frozen=True)
class RuntimeSigningIdentity:
    """Public binding for a non-production signer; never stores key bytes."""

    alias: str
    keystore_path: Path
    keystore_sha256: str
    certificate_path: Path | None = None
    certificate_sha256: str | None = None
    apksigner_path: Path | None = None
    apksigner_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.alias, str) or not self.alias.strip():
            raise ValueError("runtime signing alias is required")
        if not isinstance(self.keystore_path, Path):
            raise ValueError("runtime signing keystore path is required")
        if self.certificate_path is not None and not isinstance(
            self.certificate_path, Path
        ):
            raise ValueError("runtime signing certificate path is invalid")
        if self.apksigner_path is not None and not isinstance(
            self.apksigner_path, Path
        ):
            raise ValueError("runtime apksigner path is invalid")
        if self.apksigner_path is not None and (
            not self.apksigner_path.is_absolute()
            or self.apksigner_path.resolve() != self.apksigner_path
        ):
            raise ValueError("runtime apksigner path must be canonical")
        _required_digest(self.keystore_sha256, field_name="runtime keystore sha256")
        if (self.certificate_path is None) != (self.certificate_sha256 is None):
            raise ValueError(
                "runtime signing certificate path and digest must be paired"
            )
        if self.certificate_sha256 is not None:
            _required_digest(
                self.certificate_sha256,
                field_name="runtime certificate sha256",
            )
        if (self.apksigner_path is None) != (self.apksigner_sha256 is None):
            raise ValueError("runtime apksigner path and digest must be paired")
        if self.apksigner_sha256 is not None:
            _required_digest(
                self.apksigner_sha256,
                field_name="runtime apksigner sha256",
            )

    def _path(self, root: Path, value: Path) -> Path:
        if value.is_absolute():
            resolved = value.resolve(strict=True)
        else:
            resolved = _resolve_vault_path(root, value)
        return resolved

    def verify(self, root: Path) -> None:
        keystore = self._path(root, self.keystore_path)
        details = _require_read_only_regular_file(
            keystore,
            code="runtime signing keystore is missing, mutable, or linked",
        )
        if _sha256_file(keystore) != self.keystore_sha256:
            raise ValueError("runtime signing keystore drifted")
        del details
        if self.certificate_path is not None and self.certificate_sha256 is not None:
            certificate = self._path(root, self.certificate_path)
            _require_read_only_regular_file(
                certificate,
                code="runtime signing certificate is missing, mutable, or linked",
            )
            if _sha256_file(certificate) != self.certificate_sha256:
                raise ValueError("runtime signing certificate drifted")
        if self.apksigner_path is not None and self.apksigner_sha256 is not None:
            apksigner = self.apksigner_path.resolve(strict=True)
            _require_executable_regular_file(
                apksigner,
                code="runtime apksigner is missing, linked, or not executable",
            )
            if _sha256_file(apksigner) != self.apksigner_sha256:
                raise ValueError("runtime apksigner drifted")

    def to_dict(self) -> dict[str, object]:
        # Deliberately omit private key bytes, passwords, and credentials.
        return {
            "alias": self.alias,
            "keystore_path": str(self.keystore_path),
            "keystore_sha256": self.keystore_sha256,
            "certificate_path": (
                str(self.certificate_path)
                if self.certificate_path is not None
                else None
            ),
            "certificate_sha256": self.certificate_sha256,
            "apksigner_path": (
                str(self.apksigner_path) if self.apksigner_path is not None else None
            ),
            "apksigner_sha256": self.apksigner_sha256,
        }


@dataclass(frozen=True)
class RuntimeVaultEntry:
    """One exact read-only file in the external Runtime Input Vault."""

    relative_path: str
    size: int
    sha256: str
    role: str = "dependency"

    def __post_init__(self) -> None:
        _relative_inventory_path(self.relative_path)
        if (
            not isinstance(self.size, int)
            or isinstance(self.size, bool)
            or self.size < 0
        ):
            raise ValueError("runtime vault entry size is invalid")
        _required_digest(self.sha256, field_name="runtime vault entry sha256")
        if not isinstance(self.role, str) or not self.role.strip():
            raise ValueError("runtime vault entry role is required")
        if self.role not in {"dependency", "signing"}:
            raise ValueError("runtime vault entry role is invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "size": self.size,
            "sha256": self.sha256,
            "role": self.role,
        }


@dataclass(frozen=True)
class RuntimeInputVaultManifest:
    """Committed public inventory for private dependency and signing inputs."""

    family_id: str
    family_version: str
    vault_root: str
    entries: tuple[RuntimeVaultEntry, ...]
    aggregate_sha256: str
    signing_identity: RuntimeSigningIdentity
    retention: Mapping[str, str]
    schema_version: int = _RUNTIME_VAULT_SCHEMA_VERSION
    document_kind: str = _RUNTIME_VAULT_DOCUMENT_KIND

    def __post_init__(self) -> None:
        if not isinstance(self.family_id, str) or not self.family_id.strip():
            raise ValueError("runtime vault family_id is required")
        if not isinstance(self.family_version, str) or not self.family_version.strip():
            raise ValueError("runtime vault family_version is required")
        root = Path(self.vault_root)
        if not root.is_absolute() or str(root.resolve()) != self.vault_root:
            raise ValueError("runtime vault root must be an absolute canonical path")
        if not isinstance(self.entries, tuple) or not self.entries:
            raise ValueError("runtime vault inventory cannot be empty")
        if any(not isinstance(entry, RuntimeVaultEntry) for entry in self.entries):
            raise ValueError("runtime vault inventory entries are invalid")
        if not any(entry.role == "dependency" for entry in self.entries):
            raise ValueError("runtime vault dependency inventory is incomplete")
        if (
            tuple(sorted(self.entries, key=lambda entry: entry.relative_path))
            != self.entries
        ):
            raise ValueError("runtime vault inventory must be sorted")
        if len({entry.relative_path for entry in self.entries}) != len(self.entries):
            raise ValueError("runtime vault inventory contains duplicate paths")
        _required_digest(
            self.aggregate_sha256, field_name="runtime vault aggregate sha256"
        )
        if not isinstance(self.signing_identity, RuntimeSigningIdentity):
            raise ValueError("runtime vault signing identity is required")
        signing_paths = {str(self.signing_identity.keystore_path)}
        if self.signing_identity.certificate_path is not None:
            signing_paths.add(str(self.signing_identity.certificate_path))
        if any(Path(path).is_absolute() for path in signing_paths):
            raise ValueError("runtime signing inputs must be relative to the vault")
        for path in signing_paths:
            _relative_inventory_path(path, field_name="runtime signing path")
        entry_paths = {entry.relative_path for entry in self.entries}
        if not signing_paths.issubset(entry_paths):
            raise ValueError("runtime signing inventory is incomplete")
        for entry in self.entries:
            if (entry.relative_path in signing_paths) != (entry.role == "signing"):
                raise ValueError("runtime vault signing inventory is inconsistent")
        if not isinstance(self.retention, Mapping) or set(self.retention) != {
            "reason",
            "status",
        }:
            raise ValueError("runtime vault retention metadata is incomplete")
        if not all(
            isinstance(value, str) and value.strip()
            for value in self.retention.values()
        ):
            raise ValueError("runtime vault retention metadata is invalid")
        if self.retention["status"] != _RUNTIME_VAULT_RETENTION_STATUS:
            raise ValueError("runtime vault retention status is invalid")
        object.__setattr__(self, "retention", MappingProxyType(dict(self.retention)))
        if (
            isinstance(self.schema_version, bool)
            or self.schema_version != _RUNTIME_VAULT_SCHEMA_VERSION
        ):
            raise ValueError("runtime vault schema version is unsupported")
        if self.document_kind != _RUNTIME_VAULT_DOCUMENT_KIND:
            raise ValueError("runtime vault document kind is invalid")

    @property
    def identity_sha256(self) -> str:
        return _sha256_bytes(
            _canonical_json_bytes(self.to_dict(include_identity=False))
        )

    @property
    def manifest_sha256(self) -> str:
        return _sha256_bytes(_canonical_json_bytes(self.to_dict()))

    @staticmethod
    def _aggregate(entries: tuple[RuntimeVaultEntry, ...]) -> str:
        return _sha256_bytes(
            _canonical_json_bytes([entry.to_dict() for entry in entries])
        )

    @classmethod
    def from_directory(
        cls,
        root: str | Path,
        *,
        family_id: str,
        family_version: str,
        signing_identity: RuntimeSigningIdentity,
        retention_reason: str,
    ) -> RuntimeInputVaultManifest:
        raw_root = Path(root).expanduser()
        if _has_symlink_component(raw_root):
            raise ValueError("runtime input vault root cannot be a symlink")
        resolved_root = raw_root.resolve(strict=True)
        if not resolved_root.is_dir():
            raise ValueError("runtime input vault root must be a directory")
        entries: list[RuntimeVaultEntry] = []
        for current, directories, filenames in os.walk(
            resolved_root, followlinks=False
        ):
            current_path = Path(current)
            for directory in directories:
                if (current_path / directory).is_symlink():
                    raise ValueError("runtime input vault contains a symlink")
            for filename in filenames:
                path = current_path / filename
                details = _require_read_only_regular_file(
                    path,
                    code=(
                        "runtime input vault contains a mutable, linked, or "
                        "non-regular file"
                    ),
                )
                relative = path.relative_to(resolved_root).as_posix()
                role = (
                    "signing"
                    if relative
                    in {
                        Path(signing_identity.keystore_path).as_posix(),
                        (
                            Path(signing_identity.certificate_path).as_posix()
                            if signing_identity.certificate_path is not None
                            else ""
                        ),
                    }
                    else "dependency"
                )
                entries.append(
                    RuntimeVaultEntry(
                        relative_path=relative,
                        size=details.st_size,
                        sha256=_sha256_file(path),
                        role=role,
                    )
                )
        ordered = tuple(sorted(entries, key=lambda entry: entry.relative_path))
        manifest = cls(
            family_id=family_id,
            family_version=family_version,
            vault_root=str(resolved_root),
            entries=ordered,
            aggregate_sha256=cls._aggregate(ordered),
            signing_identity=signing_identity,
            retention={
                "reason": retention_reason,
                "status": _RUNTIME_VAULT_RETENTION_STATUS,
            },
        )
        manifest.signing_identity.verify(resolved_root)
        return manifest

    def to_dict(self, *, include_identity: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": self.schema_version,
            "document_kind": self.document_kind,
            "family_id": self.family_id,
            "family_version": self.family_version,
            "vault_root": self.vault_root,
            "entries": [entry.to_dict() for entry in self.entries],
            "aggregate_sha256": self.aggregate_sha256,
            "signing_identity": self.signing_identity.to_dict(),
            "retention": dict(self.retention),
        }
        if include_identity:
            result["identity_sha256"] = self.identity_sha256
        return result

    @property
    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.to_dict())

    def write(self, path: str | Path) -> None:
        raw_destination = Path(path).expanduser()
        if _has_symlink_component(raw_destination):
            raise ValueError("runtime vault manifest already exists")
        destination = raw_destination.resolve()
        if destination.exists():
            raise ValueError("runtime vault manifest already exists")
        if _has_symlink_component(destination.parent):
            raise ValueError("runtime vault manifest parent cannot be a symlink")
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("xb") as stream:
                stream.write(self.canonical_bytes)
                stream.flush()
                os.fsync(stream.fileno())
            destination.chmod(0o444)
            directory_fd = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as error:
            raise ValueError("runtime vault manifest could not be written") from error

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> RuntimeInputVaultManifest:
        _reject_secret_fields(data)
        expected = {
            "schema_version",
            "document_kind",
            "family_id",
            "family_version",
            "vault_root",
            "entries",
            "aggregate_sha256",
            "signing_identity",
            "retention",
            "identity_sha256",
        }
        if not isinstance(data, Mapping) or set(data) != expected:
            raise ValueError("runtime vault manifest schema is invalid")
        raw_entries = data["entries"]
        raw_signing = data["signing_identity"]
        raw_retention = data["retention"]
        if not isinstance(raw_entries, list) or not isinstance(raw_signing, Mapping):
            raise ValueError("runtime vault manifest schema is invalid")
        if not isinstance(raw_retention, Mapping):
            raise ValueError("runtime vault retention metadata is invalid")
        signing_fields = {
            "alias",
            "keystore_path",
            "keystore_sha256",
            "certificate_path",
            "certificate_sha256",
            "apksigner_path",
            "apksigner_sha256",
        }
        if set(raw_signing) != signing_fields:
            raise ValueError("runtime signing identity schema is invalid")
        identity = RuntimeSigningIdentity(
            alias=raw_signing["alias"],  # type: ignore[arg-type]
            keystore_path=Path(raw_signing["keystore_path"]),  # type: ignore[arg-type]
            keystore_sha256=raw_signing["keystore_sha256"],  # type: ignore[arg-type]
            certificate_path=(
                Path(raw_signing["certificate_path"])
                if raw_signing["certificate_path"] is not None
                else None
            ),
            certificate_sha256=raw_signing["certificate_sha256"],  # type: ignore[arg-type]
            apksigner_path=(
                Path(raw_signing["apksigner_path"])
                if raw_signing["apksigner_path"] is not None
                else None
            ),
            apksigner_sha256=raw_signing["apksigner_sha256"],  # type: ignore[arg-type]
        )
        entries = []
        for raw_entry in raw_entries:
            if not isinstance(raw_entry, Mapping) or set(raw_entry) != {
                "relative_path",
                "size",
                "sha256",
                "role",
            }:
                raise ValueError("runtime vault entry schema is invalid")
            entries.append(
                RuntimeVaultEntry(
                    relative_path=raw_entry["relative_path"],  # type: ignore[arg-type]
                    size=raw_entry["size"],  # type: ignore[arg-type]
                    sha256=raw_entry["sha256"],  # type: ignore[arg-type]
                    role=raw_entry["role"],  # type: ignore[arg-type]
                )
            )
        manifest = cls(
            family_id=data["family_id"],  # type: ignore[arg-type]
            family_version=data["family_version"],  # type: ignore[arg-type]
            vault_root=data["vault_root"],  # type: ignore[arg-type]
            entries=tuple(entries),
            aggregate_sha256=data["aggregate_sha256"],  # type: ignore[arg-type]
            signing_identity=identity,
            retention=dict(raw_retention),  # type: ignore[arg-type]
            schema_version=data["schema_version"],  # type: ignore[arg-type]
            document_kind=data["document_kind"],  # type: ignore[arg-type]
        )
        if data["identity_sha256"] != manifest.identity_sha256:
            raise ValueError("runtime vault manifest identity drifted")
        if manifest.aggregate_sha256 != manifest._aggregate(manifest.entries):
            raise ValueError("runtime vault aggregate identity drifted")
        return manifest


@dataclass(frozen=True)
class RuntimeInputVault:
    """An external vault plus its committed public manifest."""

    root: Path
    manifest: RuntimeInputVaultManifest
    manifest_path: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.root, Path) or not self.root.is_absolute():
            raise ValueError("runtime input vault root must be absolute")
        if str(self.root.resolve()) != str(self.root):
            raise ValueError("runtime input vault root must be canonical")
        if not isinstance(self.manifest, RuntimeInputVaultManifest):
            raise ValueError("runtime input vault manifest is required")
        if self.manifest.vault_root != str(self.root):
            raise ValueError("runtime input vault root contradicts its manifest")
        if self.manifest_path is not None:
            if not self.manifest_path.is_absolute() or str(
                self.manifest_path.resolve()
            ) != str(self.manifest_path):
                raise ValueError("runtime input vault manifest path must be canonical")

    @classmethod
    def from_directory(
        cls,
        root: str | Path,
        *,
        family_id: str,
        family_version: str,
        signing_identity: RuntimeSigningIdentity,
        retention_reason: str,
        manifest_path: str | Path | None = None,
    ) -> RuntimeInputVault:
        raw_root = Path(root).expanduser()
        if _has_symlink_component(raw_root):
            raise ValueError("runtime input vault root cannot be a symlink")
        resolved_root = raw_root.resolve(strict=True)
        manifest = RuntimeInputVaultManifest.from_directory(
            resolved_root,
            family_id=family_id,
            family_version=family_version,
            signing_identity=signing_identity,
            retention_reason=retention_reason,
        )
        if manifest_path is not None:
            raw_manifest_path = Path(manifest_path).expanduser()
            if _has_symlink_component(raw_manifest_path):
                raise ValueError("runtime vault manifest path cannot be a symlink")
            resolved_manifest_path = raw_manifest_path.resolve()
        else:
            resolved_manifest_path = None
        return cls(resolved_root, manifest, resolved_manifest_path)

    @classmethod
    def from_manifest(
        cls,
        manifest_path: str | Path,
        *,
        root: str | Path | None = None,
    ) -> RuntimeInputVault:
        raw_path = Path(manifest_path).expanduser()
        if _has_symlink_component(raw_path):
            raise ValueError("runtime vault manifest is unavailable")
        path = raw_path.resolve(strict=True)
        if not path.is_file():
            raise ValueError("runtime vault manifest is unavailable")
        try:
            raw_bytes = path.read_bytes()
            data = json.loads(raw_bytes.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("runtime vault manifest is unavailable") from error
        if not isinstance(data, Mapping):
            raise ValueError("runtime vault manifest is invalid")
        manifest = RuntimeInputVaultManifest.from_dict(data)
        if raw_bytes != manifest.canonical_bytes:
            raise ValueError("runtime vault manifest bytes drifted")
        if root is not None:
            raw_root = Path(root).expanduser()
            if _has_symlink_component(raw_root):
                raise ValueError("runtime input vault root cannot be a symlink")
            resolved_root = raw_root.resolve(strict=True)
        else:
            raw_root = Path(manifest.vault_root)
            if _has_symlink_component(raw_root):
                raise ValueError("runtime input vault root cannot be a symlink")
            resolved_root = raw_root.resolve(strict=True)
        return cls(resolved_root, manifest, path)

    def write_manifest(self, path: str | Path | None = None) -> RuntimeInputVault:
        destination: Path | None
        if path is not None:
            destination = Path(path).expanduser()
        else:
            destination = self.manifest_path
        if destination is None:
            raise ValueError("runtime vault manifest path is required")
        self.manifest.write(destination)
        return RuntimeInputVault(self.root, self.manifest, destination.resolve())

    @property
    def manifest_sha256(self) -> str:
        return self.manifest.manifest_sha256

    def receipt(self) -> dict[str, object]:
        return {
            "root": str(self.root),
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "manifest_sha256": self.manifest_sha256,
            "aggregate_sha256": self.manifest.aggregate_sha256,
            "entry_count": len(self.manifest.entries),
            "family_id": self.manifest.family_id,
            "family_version": self.manifest.family_version,
            "signing_identity": self.manifest.signing_identity.to_dict(),
            "retention": dict(self.manifest.retention),
        }

    def verify(self) -> None:
        root = self.root
        if _has_symlink_component(root):
            raise ValueError("runtime input vault root contains a symlink")
        try:
            details = _lstat(root)
        except OSError as error:
            raise ValueError("runtime input vault root is unavailable") from error
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
            raise ValueError("runtime input vault root is invalid")
        if self.manifest.vault_root != str(root):
            raise ValueError("runtime input vault root drifted")
        expected = {entry.relative_path: entry for entry in self.manifest.entries}
        observed: set[str] = set()
        for current, directories, filenames in os.walk(root, followlinks=False):
            current_path = Path(current)
            for directory in directories:
                directory_path = current_path / directory
                if directory_path.is_symlink():
                    raise ValueError("runtime input vault contains a symlink")
            for filename in filenames:
                path = current_path / filename
                relative = path.relative_to(root).as_posix()
                if relative not in expected:
                    raise ValueError("runtime input vault contains an extra file")
                entry = expected[relative]
                details = _require_read_only_regular_file(
                    path,
                    code=(
                        "runtime input vault file is missing, mutable, linked, "
                        "or non-regular"
                    ),
                )
                if details.st_size != entry.size or _sha256_file(path) != entry.sha256:
                    raise ValueError("runtime input vault file drifted")
                observed.add(relative)
        if observed != set(expected):
            raise ValueError("runtime input vault file is missing")
        if self.manifest.aggregate_sha256 != self.manifest._aggregate(
            self.manifest.entries
        ):
            raise ValueError("runtime input vault aggregate identity drifted")
        self.manifest.signing_identity.verify(root)

    def copy_to(self, destination: str | Path) -> Path:
        """Copy inputs into a fresh private build root without hard-linking them."""
        self.verify()
        target = Path(destination).expanduser()
        if target.exists() or target.is_symlink():
            raise ValueError("private runtime input copy already exists")
        if _has_symlink_component(target.parent):
            raise ValueError("private runtime input copy parent cannot be a symlink")
        target.mkdir(parents=True, exist_ok=False)
        target.chmod(0o700)
        try:
            for entry in self.manifest.entries:
                source = _resolve_vault_path(self.root, Path(entry.relative_path))
                destination_path = target.joinpath(
                    *PurePosixPath(entry.relative_path).parts
                )
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination_path)
                destination_path.chmod(0o444)
                with destination_path.open("rb") as stream:
                    os.fsync(stream.fileno())
                copied = _require_read_only_regular_file(
                    destination_path,
                    code="private runtime input copy is not immutable",
                )
                if (
                    copied.st_size != entry.size
                    or _sha256_file(destination_path) != entry.sha256
                ):
                    raise ValueError("private runtime input copy drifted")
        except (OSError, ValueError):
            shutil.rmtree(target, ignore_errors=True)
            raise
        return target.resolve()


def _verify_manifest_file(vault: RuntimeInputVault) -> None:
    path = vault.manifest_path
    if path is None:
        raise ValueError("runtime input vault manifest path is required")
    if _has_symlink_component(path):
        raise ValueError("runtime input vault manifest contains a symlink")
    details = _require_read_only_regular_file(
        path,
        code="runtime input vault manifest is missing, mutable, or linked",
    )
    if _sha256_file(path) != _sha256_bytes(vault.manifest.canonical_bytes):
        raise ValueError("runtime input vault manifest bytes drifted")
    del details


def _verify_private_vault_copy(
    vault: RuntimeInputVault,
    copied_root: Path,
) -> None:
    if _has_symlink_component(copied_root):
        raise ValueError("private runtime input copy contains a symlink")
    details = _lstat(copied_root)
    if (
        stat.S_ISLNK(details.st_mode)
        or not stat.S_ISDIR(details.st_mode)
        or details.st_mode & 0o077
    ):
        raise ValueError("private runtime input copy is unavailable")
    expected = {entry.relative_path: entry for entry in vault.manifest.entries}
    observed: set[str] = set()
    for current, directories, filenames in os.walk(copied_root, followlinks=False):
        current_path = Path(current)
        for directory in directories:
            if (current_path / directory).is_symlink():
                raise ValueError("private runtime input copy contains a symlink")
        for filename in filenames:
            path = current_path / filename
            relative = path.relative_to(copied_root).as_posix()
            entry = expected.get(relative)
            if entry is None:
                raise ValueError("private runtime input copy contains an extra file")
            details = _require_read_only_regular_file(
                path,
                code="private runtime input copy is mutable, linked, or non-regular",
            )
            if details.st_size != entry.size or _sha256_file(path) != entry.sha256:
                raise ValueError("private runtime input copy drifted")
            observed.add(relative)
    if observed != set(expected):
        raise ValueError("private runtime input copy is incomplete")


def _copy_read_only_file(
    source: Path,
    destination: Path,
    *,
    expected_sha256: str,
    code: str,
) -> os.stat_result:
    """Create a private, non-linked, checksum-bound copy of one vault file."""
    _require_read_only_regular_file(source, code=code)
    if destination.exists() or destination.is_symlink():
        raise ValueError(code)
    if _has_symlink_component(destination.parent):
        raise ValueError(code)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if _has_symlink_component(destination.parent):
        raise ValueError(code)
    destination.parent.chmod(0o700)
    try:
        shutil.copyfile(source, destination)
        destination.chmod(0o444)
        with destination.open("rb") as stream:
            os.fsync(stream.fileno())
        details = _require_read_only_regular_file(destination, code=code)
        if _sha256_file(destination) != expected_sha256:
            raise ValueError(code)
        return details
    except (OSError, ValueError):
        destination.unlink(missing_ok=True)
        raise


def _verify_private_dependency_inputs(
    vault: RuntimeInputVault,
    environment: Mapping[str, str],
) -> None:
    """Verify the vault's dependency entries remain bound in Gradle's private home."""
    gradle_home = Path(environment["GRADLE_USER_HOME"])
    for entry in vault.manifest.entries:
        if entry.role != "dependency":
            continue
        destination = gradle_home.joinpath(*PurePosixPath(entry.relative_path).parts)
        if _has_symlink_component(destination):
            raise ValueError("private runtime dependency input drifted")
        details = _require_read_only_regular_file(
            destination,
            code="private runtime dependency input drifted",
        )
        if details.st_size != entry.size or _sha256_file(destination) != entry.sha256:
            raise ValueError("private runtime dependency input drifted")


def _verify_private_signing_keystore(
    vault: RuntimeInputVault,
    environment: Mapping[str, str],
) -> Path:
    """Verify the private Android-home copy used for the debug signer."""
    destination = Path(environment["HOME"]) / ".android" / "debug.keystore"
    if _has_symlink_component(destination):
        raise ValueError("private runtime signing keystore drifted")
    _require_read_only_regular_file(
        destination,
        code="private runtime signing keystore drifted",
    )
    signer = vault.manifest.signing_identity
    if _sha256_file(destination) != signer.keystore_sha256:
        raise ValueError("private runtime signing keystore drifted")
    return destination


def _paths_overlap(first: Path, second: Path) -> bool:
    """Return whether either path contains the other."""
    return (
        first == second or first.is_relative_to(second) or second.is_relative_to(first)
    )


# Names used by the design documents and by callers that prefer the explicit
# "manifest" spelling remain available as aliases.
RuntimeVaultManifest = RuntimeInputVaultManifest


@dataclass(frozen=True)
class RuntimeBuildRecipe:
    """Canonical shell-free build request plus build/sealed APK locators."""

    args: tuple[str, ...]
    timeout_seconds: int
    apk_glob: str
    output_relative_path: str | None = None
    environment_policy: Mapping[str, object] = field(default_factory=dict)
    environment: RuntimeBuildEnvironment | None = None
    tool_identities: tuple[RuntimeToolIdentity, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.environment_policy, Mapping):
            raise ValueError("runtime build recipe environment policy is invalid")
        object.__setattr__(
            self,
            "environment_policy",
            MappingProxyType(dict(self.environment_policy)),
        )

    @property
    def strict(self) -> bool:
        """Whether this recipe opts into the sealed Runtime APK contract."""
        return bool(
            self.output_relative_path is not None
            or self.environment_policy
            or self.environment is not None
            or self.tool_identities
        )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "command": list(self.args),
            "timeout_seconds": self.timeout_seconds,
            "output_relative_path": self.output_relative_path or self.apk_glob,
            "environment_policy": dict(self.environment_policy),
        }
        if self.environment is not None:
            result["environment"] = self.environment.to_dict()
        if self.tool_identities:
            result["tools"] = [tool.to_dict() for tool in self.tool_identities]
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> RuntimeBuildRecipe:
        expected = {
            "command",
            "timeout_seconds",
            "output_relative_path",
            "environment_policy",
        }
        if not isinstance(data, Mapping) or not expected.issubset(data):
            raise ValueError("runtime build recipe schema is invalid")
        command = data["command"]
        output = data["output_relative_path"]
        policy = data["environment_policy"]
        if not isinstance(command, list) or not all(
            isinstance(item, str) for item in command
        ):
            raise ValueError("runtime build recipe command is invalid")
        if not isinstance(output, str) or not output:
            raise ValueError("runtime build recipe output is invalid")
        if not isinstance(policy, Mapping):
            raise ValueError("runtime build recipe environment policy is invalid")
        environment = None
        raw_environment = data.get("environment")
        if raw_environment is not None:
            environment = RuntimeBuildEnvironment.from_dict(raw_environment)
        tool_identities: tuple[RuntimeToolIdentity, ...] = ()
        raw_tools = data.get("tools")
        if raw_tools is not None:
            if not isinstance(raw_tools, list):
                raise ValueError("runtime build recipe tools are invalid")
            parsed_tools: list[RuntimeToolIdentity] = []
            for raw_tool in raw_tools:
                if not isinstance(raw_tool, Mapping) or set(raw_tool) != {
                    "name",
                    "path",
                    "sha256",
                }:
                    raise ValueError("runtime build recipe tools are invalid")
                parsed_tools.append(
                    RuntimeToolIdentity(
                        name=raw_tool["name"],  # type: ignore[arg-type]
                        path=Path(raw_tool["path"]),  # type: ignore[arg-type]
                        sha256=raw_tool["sha256"],  # type: ignore[arg-type]
                    )
                )
            tool_identities = tuple(parsed_tools)
        return cls(
            args=tuple(command),
            timeout_seconds=data["timeout_seconds"],  # type: ignore[arg-type]
            apk_glob=output,
            output_relative_path=output,
            environment_policy=dict(policy),
            environment=environment,
            tool_identities=tool_identities,
        )


@dataclass(frozen=True)
class ApkMetadata:
    """Manifest identities needed by the runner contract."""

    package: str
    launcher_activity: str
    version_code: int | None = None
    version_name: str | None = None
    min_sdk: int | None = None
    target_sdk: int | None = None
    compile_sdk: int | None = None
    debuggable: bool | None = None
    signer_sha256: str | None = None
    signer_count: int | None = None
    v1_verified: bool | None = None
    v2_verified: bool | None = None


class ApkInspector(ABC):
    """Inspect package and launcher identity without installing an APK."""

    @abstractmethod
    def inspect(self, apk_path: Path) -> ApkMetadata:
        """Return the manifest identity for one exact local APK."""


class ApkInspectionError(RuntimeError):
    """Raised when a local APK manifest cannot be inspected."""


class AaptApkInspector(ApkInspector):
    """Production APK inspector backed by ``aapt2 dump badging``."""

    def __init__(
        self,
        executable: str = "aapt2",
        *,
        command_runner: CommandRunner | None = None,
        apksigner_executable: str | None = None,
        signing_identity: RuntimeSigningIdentity | None = None,
        require_signature: bool = False,
    ) -> None:
        if command_runner is not None and not isinstance(command_runner, CommandRunner):
            raise ValueError(
                "APK inspector command runner must implement CommandRunner"
            )
        if signing_identity is not None and not isinstance(
            signing_identity, RuntimeSigningIdentity
        ):
            raise ValueError("APK inspector signing identity is invalid")
        if require_signature and signing_identity is None:
            raise ValueError("signature inspection requires a signing identity")
        if require_signature or signing_identity is not None:
            if not Path(executable).is_absolute():
                raise ValueError("signature inspection requires an absolute aapt2 path")
            if apksigner_executable is None and (
                signing_identity is None or signing_identity.apksigner_path is None
            ):
                raise ValueError(
                    "signature inspection requires an explicit apksigner path"
                )
            if (
                apksigner_executable is not None
                and not Path(apksigner_executable).is_absolute()
            ):
                raise ValueError(
                    "signature inspection requires an absolute apksigner path"
                )
            if (
                signing_identity is not None
                and signing_identity.apksigner_path is not None
            ):
                selected_apksigner = Path(
                    apksigner_executable or signing_identity.apksigner_path
                ).resolve()
                if selected_apksigner != signing_identity.apksigner_path:
                    raise ValueError("APK signer tool contradicts signing identity")
        self._executable = executable
        self._apksigner_executable = apksigner_executable or (
            str(signing_identity.apksigner_path)
            if signing_identity is not None
            and signing_identity.apksigner_path is not None
            else "apksigner"
        )
        self._signing_identity = signing_identity
        self._require_signature = require_signature or signing_identity is not None
        self._runner = command_runner or SubprocessCommandRunner()

    @property
    def executable_path(self) -> Path:
        """Return the exact aapt2 executable selected for inspection."""
        return Path(self._executable)

    @property
    def apksigner_path(self) -> Path | None:
        """Return the explicit apksigner path, if signature checks are enabled."""
        path = Path(self._apksigner_executable)
        return path if path.is_absolute() else None

    @property
    def command_runner(self) -> CommandRunner:
        return self._runner

    @property
    def signing_identity(self) -> RuntimeSigningIdentity | None:
        return self._signing_identity

    def bind_environment(self, environment: Mapping[str, str]) -> None:
        """Bind inspection commands to the same isolated environment as the build."""
        binder = getattr(self._runner, "bind_environment", None)
        if not callable(binder):
            raise ValueError("APK inspector command runner cannot bind its environment")
        binder(environment)

    def inspect(self, apk_path: Path) -> ApkMetadata:
        try:
            result = self._runner.run(
                [self._executable, "dump", "badging", str(Path(apk_path).resolve())],
                cwd=Path(apk_path).resolve().parent,
                timeout_seconds=30,
            )
        except (
            OSError,
            RuntimeError,
            TimeoutExpired,
            TypeError,
            ValueError,
        ) as error:
            raise ApkInspectionError("APK manifest inspection failed") from error
        if (
            not isinstance(result, CommandResult)
            or not isinstance(result.stdout, str)
            or result.returncode != 0
        ):
            raise ApkInspectionError("APK manifest inspection failed")
        package_match = _PACKAGE_LINE.search(result.stdout)
        activity_match = _ACTIVITY_LINE.search(result.stdout)
        if package_match is None or activity_match is None:
            raise ApkInspectionError("APK package or launcher activity is unavailable")
        package = package_match.group(1)
        activity = activity_match.group(1)
        if activity.startswith("."):
            activity = f"{package}{activity}"
        elif "." not in activity:
            activity = f"{package}.{activity}"
        details_match = _PACKAGE_DETAILS_LINE.search(result.stdout)
        version_code = None
        version_name = None
        if details_match is not None:
            version_code = _integer_or_none(details_match.group(2))
            version_name = details_match.group(3)
        min_match = _MIN_SDK_LINE.search(result.stdout)
        target_match = _TARGET_SDK_LINE.search(result.stdout)
        min_sdk = _integer_or_none(
            min_match.group(1) if min_match is not None else None
        )
        target_sdk = _integer_or_none(
            target_match.group(1) if target_match is not None else None
        )
        compile_match = _COMPILE_SDK_LINE.search(result.stdout)
        compile_sdk = _integer_or_none(
            compile_match.group(1) if compile_match else None
        )
        debuggable_match = re.search(
            r"(?:application-debuggable|debuggable=['\"](true|false)['\"])",
            result.stdout,
            re.IGNORECASE,
        )
        debuggable = (
            True
            if debuggable_match is not None and debuggable_match.group(1) is None
            else (
                debuggable_match.group(1).lower() == "true"
                if debuggable_match is not None
                else None
            )
        )
        metadata = ApkMetadata(
            package=package,
            launcher_activity=activity,
            version_code=version_code,
            version_name=version_name,
            min_sdk=min_sdk,
            target_sdk=target_sdk,
            compile_sdk=compile_sdk,
            debuggable=debuggable,
        )
        if self._require_signature:
            return self._with_signature(metadata, apk_path)
        return metadata

    def _with_signature(self, metadata: ApkMetadata, apk_path: Path) -> ApkMetadata:
        try:
            result = self._runner.run(
                [
                    self._apksigner_executable,
                    "verify",
                    "--verbose",
                    "--print-certs",
                    str(Path(apk_path).resolve()),
                ],
                cwd=Path(apk_path).resolve().parent,
                timeout_seconds=30,
            )
        except (
            OSError,
            RuntimeError,
            TimeoutExpired,
            TypeError,
            ValueError,
        ) as error:
            raise ApkInspectionError("APK signature inspection failed") from error
        if (
            not isinstance(result, CommandResult)
            or result.returncode != 0
            or not isinstance(result.stdout, str)
        ):
            raise ApkInspectionError("APK signature inspection failed")
        signer_matches = _SIGNER_COUNT_LINE.findall(result.stdout)
        digest_match = _SIGNER_DIGEST_LINE.search(result.stdout)
        v1_match = _V1_LINE.search(result.stdout)
        v2_match = _V2_LINE.search(result.stdout)
        signer_count = len(set(signer_matches))
        signer_digest = (
            digest_match.group(1).replace(":", "").lower()
            if digest_match is not None
            else None
        )
        expected_digest = (
            self._signing_identity.certificate_sha256.lower()
            if self._signing_identity is not None
            and self._signing_identity.certificate_sha256 is not None
            else None
        )
        v1_verified = v1_match is not None and v1_match.group(1).lower() == "true"
        v2_verified = v2_match is not None and v2_match.group(1).lower() == "true"
        if (
            signer_count != 1
            or signer_digest is None
            or expected_digest is None
            or signer_digest != expected_digest
            or not v1_verified
            or not v2_verified
        ):
            raise ApkInspectionError(
                "APK signature identity is not the authorized signer"
            )
        return ApkMetadata(
            package=metadata.package,
            launcher_activity=metadata.launcher_activity,
            version_code=metadata.version_code,
            version_name=metadata.version_name,
            min_sdk=metadata.min_sdk,
            target_sdk=metadata.target_sdk,
            compile_sdk=metadata.compile_sdk,
            debuggable=metadata.debuggable,
            signer_sha256=signer_digest,
            signer_count=signer_count,
            v1_verified=v1_verified,
            v2_verified=v2_verified,
        )


def _integer_or_none(value: object) -> int | None:
    if not isinstance(value, str) or not value.isdigit():
        return None
    return int(value)


def _recipe_binds_tool(
    recipe: RuntimeBuildRecipe,
    path: Path,
) -> bool:
    """Return whether the recipe contains the verified identity for one tool."""
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return False
    return any(
        tool.path == resolved and tool.sha256 == _sha256_file(resolved)
        for tool in recipe.tool_identities
    )


def _validate_production_apk_inspector(
    inspector: ApkInspector,
    *,
    recipe: RuntimeBuildRecipe,
    signer: RuntimeSigningIdentity,
) -> str | None:
    """Validate the non-substitute APK inspection toolchain before build."""
    if type(inspector) is not AaptApkInspector:
        return "apk_inspector_untrusted"
    assert isinstance(inspector, AaptApkInspector)
    if type(inspector.command_runner) is not SubprocessCommandRunner:
        return "apk_inspector_runner_untrusted"
    if inspector.signing_identity is None:
        return "apk_inspector_signing_identity_unavailable"
    if inspector.signing_identity.to_dict() != signer.to_dict():
        return "apk_inspector_signing_identity_mismatch"
    apksigner_path = signer.apksigner_path
    if apksigner_path is None or signer.apksigner_sha256 is None:
        return "apk_inspector_tool_identity_unavailable"
    if inspector.apksigner_path != apksigner_path:
        return "apk_inspector_tool_identity_mismatch"
    if not _recipe_binds_tool(recipe, inspector.executable_path):
        return "apk_inspector_tool_identity_unavailable"
    if not _recipe_binds_tool(recipe, apksigner_path):
        return "apk_inspector_tool_identity_unavailable"
    environment = recipe.environment
    if environment is None:
        return "build_recipe_environment_mismatch"
    variables = dict(environment.variables)
    if not {"JAVA_HOME", "ANDROID_SDK_ROOT"}.issubset(variables):
        return "build_recipe_environment_mismatch"
    java = Path(variables["JAVA_HOME"]) / "bin" / "java"
    if not _recipe_binds_tool(recipe, java):
        return "build_recipe_tool_mismatch"
    try:
        inspector.executable_path.resolve(strict=True).relative_to(
            Path(variables["ANDROID_SDK_ROOT"]).resolve(strict=True)
        )
    except (OSError, ValueError):
        return "apk_inspector_tool_identity_mismatch"
    return None


@dataclass(frozen=True)
class RuntimePreparationReceipt:
    """Checksum-bound prepared or stable rejected preparation outcome."""

    prepared: bool
    receipt_bytes: bytes
    receipt_sha256: str
    rejection_code: str | None

    @property
    def receipt(self) -> dict[str, object]:
        """Decode a fresh copy so callers cannot mutate the sealed outcome."""
        value = json.loads(self.receipt_bytes)
        if not isinstance(value, dict):
            raise RuntimeError("runtime preparation receipt bytes are invalid")
        return value


@dataclass(frozen=True)
class RuntimePreparationHandoff:
    """One mutually exclusive prepared-source handoff consumed by the runner."""

    receipt: RuntimePreparationReceipt
    source_authority: SourceAuthority
    apk_inspector: ApkInspector

    def __post_init__(self) -> None:
        if not isinstance(self.receipt, RuntimePreparationReceipt):
            raise ValueError("runtime handoff requires an immutable prepared receipt")
        if not isinstance(self.source_authority, SourceAuthority):
            raise ValueError("runtime handoff requires a source authority")
        if not isinstance(self.apk_inspector, ApkInspector):
            raise ValueError("runtime handoff requires an APK inspector")


class RuntimePreparationVerificationError(ValueError):
    """Raised when a prepared handoff no longer matches live local state."""


class SealedInjectionSourceAuthority(SourceAuthority):
    """Admit exactly one sealed injection and its matching blind-safe packet."""

    def __init__(
        self,
        admission: InjectionAdmission,
        packet: VerifierPacket | ProjectTargetPacket,
        catalog_path: str | Path,
    ) -> None:
        self._admission = admission
        self._packet = packet
        self._catalog_path = Path(catalog_path)

    @property
    def materialized_source_tree_sha256(self) -> str:
        return self._packet.materialized_source_tree_sha256

    @property
    def declares_injection(self) -> bool:
        return True

    def verify_runtime_source_request(self, request: RuntimeSourceRequest) -> None:
        """Check the mapping row's source-side identities against this packet."""
        if not isinstance(request, RuntimeSourceRequest):
            raise ProductionSeamAdmissionError("runtime source request is invalid")
        packet = self._packet
        if (
            request.target_kind != packet.target_kind
            or request.source_origin != packet.source_origin
            or request.baseline_commit != packet.source_commit
            or request.baseline_tree_sha256 != packet.baseline_source_tree_sha256
            or request.worktree_path != packet.worktree_path
        ):
            raise ProductionSeamAdmissionError(
                "runtime source request contradicts packet"
            )
        if isinstance(packet, VerifierPacket) and (
            request.source_commit != packet.source_commit
            or request.source_tree_sha256 != packet.baseline_source_tree_sha256
            or request.patch_sha256 != packet.patch_sha256
            or request.patch_format != packet.patch_format
        ):
            raise ProductionSeamAdmissionError(
                "runtime ChangeTarget request contradicts packet"
            )
        if isinstance(packet, ProjectTargetPacket) and (
            request.source_tree_sha256 != packet.materialized_source_tree_sha256
            or request.scope != packet.scope
            or request.discovery_budget != packet.discovery_budget
        ):
            raise ProductionSeamAdmissionError(
                "runtime ProjectTarget request contradicts packet"
            )

    def resolve_host(
        self,
        spec: RunSpec,
        options: PlannedRunnerOptions,
        runner: CommandRunner,
    ) -> HostAuthority:
        admission = self._admission
        packet = self._packet
        if (
            not isinstance(admission, InjectionAdmission)
            or admission.status != "sealed"
        ):
            raise ProductionSeamAdmissionError("sealed injection admission is required")
        if not isinstance(packet, (VerifierPacket, ProjectTargetPacket)):
            raise ProductionSeamAdmissionError(
                "blind-safe injection packet is required"
            )
        is_change_target = isinstance(packet, VerifierPacket)
        receipt = admission.receipt
        package = admission.package
        if receipt is None or receipt.worktree is None or package is None:
            raise ProductionSeamAdmissionError("sealed injection source is incomplete")
        try:
            catalog_path = self._catalog_path.resolve(strict=True)
            catalog = load_curated_source_catalog(catalog_path)
            entry = catalog.select(package.source_id)
            declared_patch_path = catalog_path.parent.joinpath(
                *PurePosixPath(entry.patch_path).parts
            ).resolve(strict=True)
            declared_patch_path.relative_to(catalog_path.parent)
            packet_patch_path = (
                Path(packet.patch_path).resolve(strict=True)
                if is_change_target
                else None
            )
        except (
            CuratedCatalogError,
            InjectionContractError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            raise ProductionSeamAdmissionError(
                "sealed injection catalog authority is unavailable"
            ) from error
        candidate = entry.candidate
        common_identity = (
            package.catalog_identity_sha256 == catalog.identity_sha256,
            package.catalog_source_sha256 == catalog.catalog_source_sha256,
            package.catalog_entry_identity_sha256 == entry.identity_sha256,
            package.candidate_identity_sha256 == candidate.identity_sha256,
            package.baseline_identity_sha256 == candidate.baseline.identity_sha256,
            package.patch_identity_sha256 == candidate.source_delta.identity_sha256,
            receipt.candidate_identity_sha256 == candidate.identity_sha256,
            receipt.baseline_identity_sha256 == candidate.baseline.identity_sha256,
            receipt.patch_identity_sha256 == candidate.source_delta.identity_sha256,
            packet.source_origin == candidate.baseline.source_origin,
            packet.baseline_source_tree_sha256 == candidate.baseline.source_tree_sha256,
        )
        packet_identity = (
            (
                packet.source_commit == candidate.baseline.commit,
                packet.patch_format == candidate.source_delta.format,
                packet.patch_text == candidate.source_delta.patch_text,
                packet.patch_sha256 == candidate.source_delta.patch_sha256,
                packet_patch_path == declared_patch_path,
            )
            if is_change_target
            else (packet.source_commit == candidate.baseline.commit,)
        )
        if not all((*common_identity, *packet_identity)):
            raise ProductionSeamAdmissionError(
                "sealed injection catalog identity mismatch"
            )
        try:
            receipt_path = Path(receipt.worktree.path).resolve(strict=True)
            packet_path = Path(packet.worktree_path).resolve(strict=True)
            host_project = spec.host_project.resolve(strict=True)
            workdir = Path(options.workdir).resolve(strict=True)
        except OSError as error:
            raise ProductionSeamAdmissionError(
                "sealed injection worktree is unavailable"
            ) from error
        if len({receipt_path, packet_path, host_project, workdir}) != 1:
            raise ProductionSeamAdmissionError(
                "sealed injection worktree path mismatch"
            )
        if (
            packet.receipt_identity_sha256 != receipt.receipt_identity_sha256
            or package.receipt_identity_sha256 != receipt.receipt_identity_sha256
            or packet.materialized_source_tree_sha256
            != receipt.result_source_tree_sha256
            or (
                is_change_target
                and packet.result_diff_sha256 != receipt.result_diff_sha256
            )
            or packet.source_commit != receipt.worktree.baseline_commit
            or receipt.worktree.candidate_identity_sha256
            != package.candidate_identity_sha256
            or (is_change_target and packet.packet_id != packet.canonical_packet_id)
        ):
            raise ProductionSeamAdmissionError("sealed injection identity mismatch")
        if is_change_target:
            try:
                declared_patch = declared_patch_path.read_bytes()
            except OSError as error:
                raise ProductionSeamAdmissionError(
                    "sealed injection packet material is unavailable"
                ) from error
            if declared_patch != packet.patch_text.encode("utf-8"):
                raise ProductionSeamAdmissionError(
                    "sealed injection packet material drifted"
                )
        locator = spec.host_locator
        if locator is None:
            raise ProductionSeamAdmissionError(
                "portable host origin and commit locator is required"
            )
        expected_commit = options.expected_source_commit or locator.expected_commit
        if (
            locator.expected_origin != packet.source_origin
            or expected_commit != packet.source_commit
        ):
            raise ProductionSeamAdmissionError(
                "Run Spec locator contradicts sealed injection"
            )
        origin = self._git(runner, workdir, "remote", "get-url", "origin")
        commit = self._git(runner, workdir, "rev-parse", "HEAD").lower()
        root = Path(
            self._git(runner, workdir, "rev-parse", "--show-toplevel")
        ).resolve()
        if (
            root != workdir
            or origin != packet.source_origin
            or commit != packet.source_commit
        ):
            raise ProductionSeamAdmissionError(
                "sealed injection Git provenance mismatch"
            )
        try:
            baseline_tree = source_tree_sha256_for_commit(workdir, commit)
            inspection = inspect_materialized_receipt_source(receipt)
        except (InjectionMaterializerError, OSError, RuntimeError, ValueError) as error:
            raise ProductionSeamAdmissionError(
                "sealed injection source identity is unavailable"
            ) from error
        if baseline_tree != packet.baseline_source_tree_sha256:
            raise ProductionSeamAdmissionError(
                "sealed injection baseline source identity mismatch"
            )
        authority = SourceAuthorityBinding(
            kind="sealed_injection",
            claims=tuple(
                sorted(
                    {
                        "admission_identity_sha256": admission.identity_sha256,
                        "catalog_entry_identity_sha256": entry.identity_sha256,
                        "catalog_identity_sha256": catalog.identity_sha256,
                        "catalog_source_sha256": catalog.catalog_source_sha256,
                        "candidate_identity_sha256": candidate.identity_sha256,
                        "materialized_source_tree_sha256": (
                            inspection.source_tree_sha256
                        ),
                        "patch_identity_sha256": candidate.source_delta.identity_sha256,
                        "patch_sha256": candidate.source_delta.patch_sha256,
                        "packet_identity_sha256": packet.identity_sha256,
                        "receipt_identity_sha256": receipt.receipt_identity_sha256,
                        "result_diff_sha256": inspection.result_diff_sha256,
                        "result_identity_sha256": receipt.result_identity_sha256,
                    }.items()
                )
            ),
        )
        return HostAuthority(
            repository_root=str(root),
            host_project=str(host_project),
            origin=origin,
            commit=commit,
            worktree=HostWorktreeIdentity(
                clean=False,
                status_sha256=inspection.status_sha256,
                source_tree_sha256=inspection.source_tree_sha256,
                complete_tree_sha256=inspection.complete_tree_sha256,
                declared_injection=True,
            ),
            host_project_within_repository=False,
            source_authority=authority,
        )

    @staticmethod
    def _git(runner: CommandRunner, workdir: Path, *arguments: str) -> str:
        result = runner.run(
            ["git", *arguments],
            cwd=workdir,
            timeout_seconds=30,
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise ProductionSeamAdmissionError(
                f"sealed injection Git identity failed ({' '.join(arguments)})"
            )
        return result.stdout.strip()


class MappedRuntimeSourceAuthority(SourceAuthority):
    """Bind one released opaque lane to an existing source authority.

    The mapping is consumed before the production seam is admitted.  The
    delegated authority still owns the actual source admission; this wrapper
    adds the candidate, lane, materialization, and checked-in input bindings
    that the build handoff needs.
    """

    def __init__(
        self,
        mapping: RuntimeMappingRelease | SourceAuthorityMapping,
        source_authority: SourceAuthority,
        lane_id: str,
        *,
        candidate_root: str | Path | None = None,
    ) -> None:
        if not isinstance(mapping, (RuntimeMappingRelease, SourceAuthorityMapping)):
            raise ValueError("released runtime mapping is required")
        if not isinstance(source_authority, SourceAuthority):
            raise ValueError("mapped runtime source authority is invalid")
        self._mapping_input = mapping
        self._delegate = source_authority
        self._lane_id = lane_id
        self._candidate_root = (
            Path(candidate_root).expanduser().resolve()
            if candidate_root is not None
            else None
        )
        if isinstance(mapping, RuntimeMappingRelease) and self._candidate_root is None:
            raise ValueError(
                "a released runtime mapping requires its candidate root "
                "for verification"
            )
        try:
            self._mapping = (
                mapping
                if isinstance(mapping, SourceAuthorityMapping)
                else mapping.for_source_authority(source_authority)
            )
            self._request = self._mapping.request_for_lane(lane_id)
        except Exception as error:
            raise ValueError("released runtime mapping lane is unavailable") from error

    @property
    def lane_id(self) -> str:
        return self._lane_id

    @property
    def mapping(self) -> RuntimeMappingRelease | SourceAuthorityMapping:
        return self._mapping_input

    @property
    def source_request(self) -> RuntimeSourceRequest:
        return self._request

    @property
    def delegate(self) -> SourceAuthority:
        return self._delegate

    @property
    def candidate_root(self) -> Path | None:
        return self._candidate_root

    @property
    def mapping_binding(self) -> dict[str, object]:
        """Return the selected lane's public mapping commitments."""
        binding: dict[str, object] = {
            "release_id": self._mapping.release_id,
            "release_identity_sha256": self._mapping.release_identity_sha256,
            "lane_id": self._lane_id,
            "source_request_identity_sha256": self._request.identity_sha256,
        }
        if isinstance(self._mapping_input, RuntimeMappingRelease):
            lane = next(
                lane
                for lane in self._mapping_input.lanes
                if lane.lane_id == self._lane_id
            )
            binding.update(
                {
                    "lane_identity_sha256": lane.identity_sha256,
                    "projection_raw_sha256": lane.projection_raw_sha256,
                    "driver_plan_raw_sha256": lane.driver_plan_raw_sha256,
                    "recipe_raw_sha256": lane.recipe_raw_sha256,
                    "run_spec_raw_sha256": lane.run_spec_raw_sha256,
                }
            )
        return binding

    def _verify_mapping(self) -> None:
        if isinstance(self._mapping_input, RuntimeMappingRelease):
            verify_runtime_mapping_release(
                self._mapping_input,
                candidate_root=self._candidate_root,
            )
        if self._candidate_root is not None:
            self._verify_candidate_lane_documents(self._candidate_root)

    def _verify_candidate_lane_documents(self, candidate_root: Path) -> None:
        if not isinstance(self._mapping_input, RuntimeMappingRelease):
            return
        lane = next(
            lane for lane in self._mapping_input.lanes if lane.lane_id == self._lane_id
        )
        for relative, expected in (
            (lane.projection_path, lane.projection_raw_sha256),
            (lane.driver_plan_path, lane.driver_plan_raw_sha256),
            (lane.recipe_path, lane.recipe_raw_sha256),
            (lane.run_spec_path, lane.run_spec_raw_sha256),
        ):
            raw_path = candidate_root.joinpath(*PurePosixPath(relative).parts)
            try:
                if _has_symlink_component(raw_path):
                    raise ValueError("mapped candidate input contains a symlink")
                resolved = raw_path.resolve(strict=True)
                resolved.relative_to(candidate_root)
                details = _lstat(raw_path)
                if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
                    raise ValueError("mapped candidate input is not a regular file")
                if _sha256_file(resolved) != expected:
                    raise ValueError("mapped candidate input digest drifted")
            except (OSError, ValueError) as error:
                raise ProductionSeamAdmissionError(
                    "released runtime candidate input identity mismatch"
                ) from error

    def verify_runtime_source_request(self, request: RuntimeSourceRequest) -> None:
        if request != self._request:
            raise ProductionSeamAdmissionError(
                "released runtime source request mismatch"
            )
        verifier = getattr(self._delegate, "verify_runtime_source_request", None)
        if callable(verifier):
            verifier(request)

    def verify_runtime_inputs(
        self,
        recipe: RuntimeBuildRecipe,
        spec: RunSpec,
    ) -> None:
        """Verify lane recipe and Run Spec identities immediately before build."""
        self._verify_mapping()
        request = self._request
        try:
            host = spec.host_project.resolve(strict=True)
            workdir = Path(spec.host_project).resolve(strict=True)
        except OSError as error:
            raise ProductionSeamAdmissionError(
                "mapped runtime worktree is unavailable"
            ) from error
        if str(host) != request.worktree_path or str(workdir) != request.worktree_path:
            raise ProductionSeamAdmissionError(
                "mapped runtime worktree identity mismatch"
            )
        locator = spec.host_locator
        if locator is not None and (
            locator.expected_origin != request.source_origin
            or locator.expected_commit != request.source_commit
        ):
            raise ProductionSeamAdmissionError(
                "mapped runtime locator identity mismatch"
            )
        if spec.package and request.target_kind not in {
            "ChangeTarget",
            "ProjectTarget",
        }:
            raise ProductionSeamAdmissionError(
                "mapped runtime target identity mismatch"
            )
        if not isinstance(recipe, RuntimeBuildRecipe):
            raise ProductionSeamAdmissionError("mapped runtime recipe is unavailable")
        if recipe.apk_glob != spec.apk_glob:
            raise ProductionSeamAdmissionError(
                "mapped runtime Run Spec output mismatch"
            )
        if self._candidate_root is None:
            return
        if not isinstance(self._mapping_input, RuntimeMappingRelease):
            return
        lane = next(
            lane for lane in self._mapping_input.lanes if lane.lane_id == self._lane_id
        )
        recipe_path = self._candidate_root.joinpath(
            *PurePosixPath(lane.recipe_path).parts
        )
        run_spec_path = self._candidate_root.joinpath(
            *PurePosixPath(lane.run_spec_path).parts
        )
        try:
            candidate_recipe = RuntimeBuildRecipe.from_dict(
                json.loads(recipe_path.read_text(encoding="utf-8"))
            )
            candidate_spec = load_run_spec(run_spec_path)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            raise ProductionSeamAdmissionError(
                "mapped runtime candidate recipe or Run Spec is unavailable"
            ) from error
        candidate_recipe_document = candidate_recipe.to_dict()
        actual_recipe_document = recipe.to_dict()
        if any(
            actual_recipe_document.get(key) != value
            for key, value in candidate_recipe_document.items()
        ):
            raise ProductionSeamAdmissionError(
                "mapped runtime recipe identity mismatch"
            )
        if (
            candidate_spec.apk_glob != spec.apk_glob
            or candidate_spec.package != spec.package
            or candidate_spec.activity != spec.activity
            or candidate_spec.scenario.id != spec.scenario.id
            or spec.source_sha256 != lane.run_spec_raw_sha256
            or candidate_spec.source_sha256 != lane.run_spec_raw_sha256
        ):
            raise ProductionSeamAdmissionError(
                "mapped runtime Run Spec identity mismatch"
            )

    def resolve_host(
        self,
        spec: RunSpec,
        options: PlannedRunnerOptions,
        runner: CommandRunner,
    ) -> HostAuthority:
        self._verify_mapping()
        self.verify_runtime_source_request(self._request)
        host = self._delegate.resolve_host(spec, options, runner)
        if not isinstance(host, HostAuthority):
            raise ProductionSeamAdmissionError(
                "mapped source authority returned no host"
            )
        expected = self._request
        delegate_tree = getattr(self._delegate, "materialized_source_tree_sha256", None)
        delegate_injection = getattr(self._delegate, "declares_injection", None)
        if not isinstance(delegate_tree, str) or not isinstance(
            delegate_injection, bool
        ):
            raise ProductionSeamAdmissionError(
                "mapped source authority lacks materialization identity"
            )
        if (
            host.host_project != expected.worktree_path
            or host.origin != expected.source_origin
            or host.commit != expected.source_commit
            or host.worktree.source_tree_sha256 != delegate_tree
            or host.worktree.declared_injection != delegate_injection
        ):
            raise ProductionSeamAdmissionError("mapped source host identity mismatch")
        return host


class MappedSealedInjectionSourceAuthority(MappedRuntimeSourceAuthority):
    """Convenience authority for one mapped lane backed by a sealed injection."""

    def __init__(
        self,
        mapping: RuntimeMappingRelease | SourceAuthorityMapping,
        admission: InjectionAdmission,
        packet: VerifierPacket | ProjectTargetPacket,
        catalog_path: str | Path,
        lane_id: str,
        *,
        candidate_root: str | Path | None = None,
    ) -> None:
        super().__init__(
            mapping,
            SealedInjectionSourceAuthority(admission, packet, catalog_path),
            lane_id,
            candidate_root=candidate_root,
        )


# Keep the vocabulary used by the runtime calibration design available to
# integrations that prefer either "mapping" or "mapped" in the type name.
RuntimeMappingSourceAuthority = MappedRuntimeSourceAuthority
SealedRuntimeSourceAuthority = MappedSealedInjectionSourceAuthority


def _rejected(code: str) -> RuntimePreparationReceipt:
    document: dict[str, object] = {
        "schema_version": RUNTIME_PREPARATION_SCHEMA_VERSION,
        "status": "rejected",
        "prepared": False,
        "rejection_code": code,
        "claim_boundary": RUNTIME_PREPARATION_CLAIM_BOUNDARY,
    }
    document["receipt_identity_sha256"] = _identity(document)
    encoded = _canonical_bytes(document)
    return RuntimePreparationReceipt(
        prepared=False,
        receipt_bytes=encoded,
        receipt_sha256=_sha256_bytes(encoded),
        rejection_code=code,
    )


def _validate_recipe(recipe: RuntimeBuildRecipe, spec: RunSpec) -> str | None:
    if not isinstance(recipe, RuntimeBuildRecipe):
        return "invalid_build_recipe"
    if (
        not isinstance(recipe.args, tuple)
        or not recipe.args
        or any(
            not isinstance(argument, str) or not argument for argument in recipe.args
        )
    ):
        return "invalid_build_recipe"
    if (
        not isinstance(recipe.timeout_seconds, int)
        or isinstance(recipe.timeout_seconds, bool)
        or not 1 <= recipe.timeout_seconds <= 3600
    ):
        return "invalid_build_recipe"
    locator = Path(recipe.apk_glob)
    if (
        not recipe.apk_glob
        or locator.is_absolute()
        or ".." in locator.parts
        or recipe.apk_glob != spec.apk_glob
    ):
        return "invalid_build_recipe"
    argument_basenames = {Path(argument).name.lower() for argument in recipe.args}
    if argument_basenames & _PROHIBITED_EXECUTABLES:
        return "prohibited_build_command"
    if Path(recipe.args[0]).name.lower() not in _GRADLE_EXECUTABLES:
        return "prohibited_build_command"
    for argument in recipe.args[1:]:
        normalized = argument.lower()
        if normalized.startswith("-"):
            if normalized in _SAFE_GRADLE_FLAGS or normalized.startswith(
                _SAFE_GRADLE_FLAG_PREFIXES
            ):
                continue
            return "prohibited_build_command"
        task_name = normalized.rsplit(":", 1)[-1]
        if task_name == "clean" or task_name.startswith("assemble"):
            continue
        return "prohibited_build_command"
    return None


def _validate_strict_recipe(recipe: RuntimeBuildRecipe, spec: RunSpec) -> str | None:
    """Validate the fixed offline build vector used by a sealed APK."""
    base_rejection = _validate_recipe(recipe, spec)
    if base_rejection is not None:
        return base_rejection
    output_relative_path = recipe.output_relative_path
    if not isinstance(output_relative_path, str):
        return "invalid_build_recipe"
    output = PurePosixPath(output_relative_path)
    if (
        output.is_absolute()
        or output.as_posix() != output_relative_path
        or any(part in {"", ".", "..", ".git"} for part in output.parts)
        or any(character in output_relative_path for character in "*?[]")
    ):
        return "invalid_build_recipe"
    if recipe.timeout_seconds != _RUNTIME_BUILD_TIMEOUT_SECONDS:
        return "invalid_build_recipe"
    if recipe.args != _RUNTIME_BUILD_COMMAND:
        return "build_recipe_vector_mismatch"
    if not isinstance(recipe.environment_policy, Mapping):
        return "build_recipe_policy_mismatch"
    expected_policy = {
        "mode": "private_allowlist",
        "dependency_resolution": "offline",
        "network_claim": "none",
        "retry": False,
    }
    if dict(recipe.environment_policy) != expected_policy:
        return "build_recipe_policy_mismatch"
    if not isinstance(recipe.environment, RuntimeBuildEnvironment):
        return "build_recipe_environment_mismatch"
    environment = recipe.environment
    try:
        variables = dict(environment.variables)
        required_variables = {
            "ANDROID_SDK_ROOT",
            "JAVA_HOME",
            "LANG",
            "LC_ALL",
            "PATH",
            "SOURCE_DATE_EPOCH",
            "TZ",
        }
        if set(variables) != required_variables or any(
            variables[key] != expected
            for key, expected in {
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "SOURCE_DATE_EPOCH": "1783693058",
                "TZ": "UTC",
            }.items()
        ):
            return "build_recipe_environment_mismatch"
        for key in ("JAVA_HOME", "ANDROID_SDK_ROOT"):
            value = Path(variables[key])
            if (
                not value.is_absolute()
                or value.resolve(strict=True) != value
                or not value.is_dir()
            ):
                return "build_recipe_environment_mismatch"
        for path_value in variables["PATH"].split(os.pathsep):
            path = Path(path_value)
            if (
                not path_value
                or not path.is_absolute()
                or path.resolve(strict=True) != path
                or not path.is_dir()
            ):
                return "build_recipe_environment_mismatch"
        environment.to_dict()
    except (OSError, RuntimeError, TypeError, ValueError):
        return "build_recipe_environment_mismatch"
    if not isinstance(recipe.tool_identities, tuple) or len(
        {
            tool.name
            for tool in recipe.tool_identities
            if isinstance(tool, RuntimeToolIdentity)
        }
    ) != len(recipe.tool_identities):
        return "build_recipe_tool_mismatch"
    if not recipe.tool_identities:
        return "build_recipe_tool_mismatch"
    try:
        for tool in recipe.tool_identities:
            if not isinstance(tool, RuntimeToolIdentity):
                return "build_recipe_tool_mismatch"
            tool.verify()
    except (OSError, RuntimeError, TypeError, ValueError):
        return "build_recipe_tool_mismatch"
    return None


def _strict_metadata_document(metadata: ApkMetadata) -> dict[str, object]:
    return {
        "package": metadata.package,
        "launcher_activity": metadata.launcher_activity,
        "version_code": metadata.version_code,
        "version_name": metadata.version_name,
        "min_sdk": metadata.min_sdk,
        "target_sdk": metadata.target_sdk,
        "compile_sdk": metadata.compile_sdk,
        "debuggable": metadata.debuggable,
        "signer_sha256": metadata.signer_sha256,
        "signer_count": metadata.signer_count,
        "v1_verified": metadata.v1_verified,
        "v2_verified": metadata.v2_verified,
    }


def _validate_strict_metadata(
    metadata: ApkMetadata,
    *,
    spec: RunSpec,
    signing_identity: RuntimeSigningIdentity,
    expected: ApkMetadata | None,
) -> str | None:
    if metadata.package != spec.package:
        return "apk_package_mismatch"
    if metadata.launcher_activity != spec.activity:
        return "apk_activity_mismatch"
    required = (
        metadata.version_code,
        metadata.version_name,
        metadata.min_sdk,
        metadata.target_sdk,
        metadata.compile_sdk,
        metadata.debuggable,
        metadata.signer_sha256,
        metadata.signer_count,
        metadata.v1_verified,
        metadata.v2_verified,
    )
    if any(value is None for value in required):
        return "apk_metadata_incomplete"
    signer_digest = metadata.signer_sha256
    certificate_digest = signing_identity.certificate_sha256
    if not isinstance(signer_digest, str) or not isinstance(certificate_digest, str):
        return "apk_signer_mismatch"
    if (
        metadata.signer_count != 1
        or metadata.v1_verified is not True
        or metadata.v2_verified is not True
        or signer_digest.lower() != certificate_digest.lower()
    ):
        return "apk_signer_mismatch"
    if expected is None:
        expected = ApkMetadata(
            package=spec.package,
            launcher_activity=spec.activity or "",
            version_code=54,
            version_name="3.2.1",
            min_sdk=21,
            target_sdk=35,
            compile_sdk=35,
            debuggable=True,
        )
    if expected is not None:
        for field_name in (
            "package",
            "launcher_activity",
            "version_code",
            "version_name",
            "min_sdk",
            "target_sdk",
            "compile_sdk",
            "debuggable",
            "signer_sha256",
            "signer_count",
            "v1_verified",
            "v2_verified",
        ):
            expected_value = getattr(expected, field_name)
            observed_value = getattr(metadata, field_name)
            if expected_value is not None and expected_value != observed_value:
                return "apk_metadata_mismatch"
    return None


def _strict_sealed_path(
    options: PlannedRunnerOptions,
    recipe: RuntimeBuildRecipe,
    requested: str | Path | None,
) -> Path:
    artifact_root = Path(options.artifact_dir).resolve()
    expected = artifact_root / "build" / "app-debug.apk"
    raw = (
        Path(requested).expanduser()
        if requested is not None
        else Path(recipe.output_relative_path or recipe.apk_glob)
    )
    destination = raw if raw.is_absolute() else artifact_root.joinpath(*raw.parts)
    if _has_symlink_component(destination):
        raise ValueError("sealed APK path cannot be a symlink")
    try:
        resolved = destination.resolve()
        resolved.relative_to(artifact_root)
    except (OSError, ValueError) as error:
        raise ValueError(
            "sealed APK path escapes the lane artifact directory"
        ) from error
    if resolved != expected:
        raise ValueError("sealed APK path must be the lane-local build/app-debug.apk")
    return resolved


def _seal_apk(
    apk_bytes: bytes,
    *,
    destination: Path,
) -> dict[str, object]:
    if destination.exists() or destination.is_symlink():
        raise ValueError("sealed APK already exists")
    if _has_symlink_component(destination.parent):
        raise ValueError("sealed APK parent is a symlink")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if _has_symlink_component(destination.parent):
        raise ValueError("sealed APK parent is a symlink")
    temporary = (
        destination.parent / f".{destination.name}.tmp-{os.getpid()}-{time.time_ns()}"
    )
    linked = False
    try:
        with temporary.open("xb") as stream:
            stream.write(apk_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o444)
        os.link(temporary, destination)
        linked = True
        temporary.unlink()
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except (OSError, ValueError) as error:
        temporary.unlink(missing_ok=True)
        if linked:
            destination.unlink(missing_ok=True)
        raise ValueError("sealed APK could not be committed atomically") from error
    try:
        details = _require_read_only_regular_file(
            destination,
            code="sealed APK is not immutable",
        )
        digest = _sha256_file(destination)
    except (OSError, ValueError) as error:
        destination.unlink(missing_ok=True)
        raise ValueError("sealed APK is not immutable") from error
    if details.st_size != len(apk_bytes) or digest != _sha256_bytes(apk_bytes):
        destination.unlink(missing_ok=True)
        raise ValueError("sealed APK drifted during commit")
    return {
        "path": str(destination),
        "bytes": details.st_size,
        "sha256": digest,
        "mode": f"{stat.S_IMODE(details.st_mode):04o}",
        "regular": True,
        "symlink": False,
        "hard_links": details.st_nlink,
    }


def _strict_vault_build_inputs(
    vault: RuntimeInputVault,
    *,
    options: PlannedRunnerOptions,
    environment: RuntimeBuildEnvironment,
) -> tuple[Path, dict[str, str], Path]:
    vault.verify()
    private_root = Path(tempfile.mkdtemp(prefix="aiverify-runtime-inputs-")).resolve()
    private_root.chmod(0o700)
    forbidden_roots = (
        Path(options.workdir).resolve(),
        Path(options.artifact_dir).resolve(),
        vault.root,
    )
    if any(_paths_overlap(private_root, root) for root in forbidden_roots):
        shutil.rmtree(private_root, ignore_errors=True)
        raise ValueError("private runtime input root overlaps a controlled path")
    try:
        copied_vault = vault.copy_to(private_root / "vault")
        effective_environment = environment.materialize(private_root / "homes")
        for entry in vault.manifest.entries:
            if entry.role != "dependency":
                continue
            source = _resolve_vault_path(
                copied_vault,
                Path(entry.relative_path),
            )
            destination = Path(effective_environment["GRADLE_USER_HOME"]).joinpath(
                *PurePosixPath(entry.relative_path).parts
            )
            _copy_read_only_file(
                source,
                destination,
                expected_sha256=entry.sha256,
                code="private runtime dependency input is not immutable",
            )
        signing = vault.manifest.signing_identity
        signing_source = _resolve_vault_path(
            copied_vault,
            signing.keystore_path,
        )
        private_signing_keystore = (
            Path(effective_environment["HOME"]) / ".android" / "debug.keystore"
        )
        _copy_read_only_file(
            signing_source,
            private_signing_keystore,
            expected_sha256=signing.keystore_sha256,
            code="private runtime signing keystore is not immutable",
        )
        return copied_vault, effective_environment, private_signing_keystore
    except (OSError, RuntimeError, TypeError, ValueError):
        shutil.rmtree(private_root, ignore_errors=True)
        raise


def _resolve_build_executable(command: str, host: Path) -> Path:
    candidate = Path(command).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
    elif "/" in command:
        resolved = (host / candidate).resolve()
        try:
            resolved.relative_to(host)
        except ValueError as error:
            raise OSError("relative build executable escapes host") from error
    else:
        found = shutil.which(command)
        if found is None:
            raise OSError("build executable is unavailable")
        resolved = Path(found).resolve()
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise OSError("build executable is unavailable")
    return resolved


def _locate_apk(
    host: Path,
    locator: str,
    *,
    strict: bool = False,
    expected_relative_path: str | None = None,
) -> tuple[Path | None, str | None]:
    if strict:
        return _locate_strict_apk(
            host,
            locator,
            expected_relative_path=expected_relative_path,
        )
    matches: list[Path] = []
    escaped = False
    for candidate in host.glob(locator):
        if not candidate.is_file():
            continue
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(host)
        except (OSError, ValueError):
            escaped = True
            continue
        matches.append(resolved)
    if escaped:
        return None, "apk_outside_host"
    ordered = sorted(matches, key=lambda path: path.as_posix())
    if not ordered:
        return None, "apk_missing"
    if len(ordered) != 1:
        return None, "apk_ambiguous"
    return ordered[0], None


def _locate_strict_apk(
    host: Path,
    locator: str,
    *,
    expected_relative_path: str | None = None,
) -> tuple[Path | None, str | None]:
    """Locate exactly one regular APK and reject aliases or extra outputs."""
    expected_path = host.joinpath(
        *PurePosixPath(expected_relative_path or locator).parts
    )
    try:
        expected_resolved = expected_path.resolve(strict=False)
        expected_resolved.relative_to(host)
    except (OSError, ValueError):
        return None, "apk_outside_host"
    matches: list[Path] = []
    try:
        candidates = sorted(host.rglob("*.apk"), key=lambda path: path.as_posix())
    except (OSError, RuntimeError):
        return None, "apk_locator_failed"
    for candidate in candidates:
        try:
            details = _lstat(candidate)
        except OSError:
            return None, "apk_locator_failed"
        if stat.S_ISLNK(details.st_mode):
            try:
                candidate.resolve(strict=True).relative_to(host)
            except (OSError, ValueError):
                return None, "apk_outside_host"
            return None, "apk_non_regular"
        if not stat.S_ISREG(details.st_mode):
            return None, "apk_non_regular"
        if details.st_nlink != 1:
            return None, "apk_non_immutable"
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(host)
        except (OSError, ValueError):
            return None, "apk_outside_host"
        matches.append(resolved)
    if len(matches) == 0:
        return None, "apk_missing"
    if len(matches) != 1:
        return None, "apk_extra_output"
    if matches[0] != expected_resolved:
        return None, "apk_output_mismatch"
    return matches[0], None


def _host_receipt(receipt: Mapping[str, object]) -> dict[str, object] | None:
    host = receipt.get("host")
    return dict(host) if isinstance(host, Mapping) else None


def _worktree_receipt(host: Mapping[str, object]) -> dict[str, object] | None:
    worktree = host.get("worktree")
    return dict(worktree) if isinstance(worktree, Mapping) else None


def _pristine_build_source(host: Mapping[str, object]) -> bool:
    worktree = _worktree_receipt(host)
    return bool(
        worktree
        and worktree.get("source_tree_sha256") == worktree.get("complete_tree_sha256")
    )


def _host_without_build_outputs(host: Mapping[str, object]) -> dict[str, object]:
    stable = dict(host)
    worktree = _worktree_receipt(host)
    if worktree is not None:
        worktree.pop("complete_tree_sha256", None)
        stable["worktree"] = worktree
    return stable


def _re_admit_built_source(
    initial: Mapping[str, object],
    *,
    spec: RunSpec,
    options: PlannedRunnerOptions,
    source_authority: SourceAuthority,
    command_runner: CommandRunner | None,
):
    """Re-admit unchanged source while allowing newly bound build outputs."""
    current = admit_production_seam(
        spec,
        options,
        command_runner=command_runner,
        source_authority=source_authority,
    )
    current.require_admitted()
    initial_host = _host_receipt(initial)
    current_host = _host_receipt(current.receipt)
    if initial_host is None or current_host is None:
        raise ProductionSeamAdmissionError("source host identity is unavailable")
    initial_context = dict(initial)
    current_context = dict(current.receipt)
    initial_context.pop("host", None)
    current_context.pop("host", None)
    if initial_context != current_context or _host_without_build_outputs(
        initial_host
    ) != _host_without_build_outputs(current_host):
        raise ProductionSeamAdmissionError("source identity changed during build")
    return current


def _apk_unchanged(
    host: Path,
    locator: str,
    expected_path: Path,
    expected_bytes: bytes,
    *,
    strict: bool = False,
    expected_relative_path: str | None = None,
) -> bool:
    try:
        observed_path, rejection = _locate_apk(
            host,
            locator,
            strict=strict,
            expected_relative_path=expected_relative_path,
        )
        return (
            rejection is None
            and observed_path == expected_path
            and observed_path.read_bytes() == expected_bytes
        )
    except (OSError, RuntimeError, ValueError):
        return False


def prepare_runtime_case(
    *,
    source_authority: SourceAuthority,
    build_recipe: RuntimeBuildRecipe,
    spec: RunSpec,
    options: PlannedRunnerOptions,
    build_runner: CommandRunner | None = None,
    apk_inspector: ApkInspector | None = None,
    admission_command_runner: CommandRunner | None = None,
    runtime_input_vault: RuntimeInputVault | None = None,
    runtime_signing_identity: RuntimeSigningIdentity | None = None,
    expected_apk_metadata: ApkMetadata | None = None,
    sealed_apk_path: str | Path | None = None,
    allow_test_substitutes: bool = False,
) -> RuntimePreparationReceipt:
    """Admit, build, inspect, and seal one local APK without runtime effects."""
    if not isinstance(spec, RunSpec):
        return _rejected("invalid_run_spec")
    if not isinstance(options, PlannedRunnerOptions):
        return _rejected("invalid_runner_options")
    if not isinstance(source_authority, SourceAuthority):
        return _rejected("invalid_source_authority")
    if expected_apk_metadata is not None and not isinstance(
        expected_apk_metadata, ApkMetadata
    ):
        return _rejected("invalid_expected_apk_metadata")
    if build_runner is not None and not isinstance(build_runner, CommandRunner):
        return _rejected("invalid_build_runner")
    if admission_command_runner is not None and not isinstance(
        admission_command_runner, CommandRunner
    ):
        return _rejected("invalid_admission_runner")
    recipe_rejection = _validate_recipe(build_recipe, spec)
    if recipe_rejection is not None:
        return _rejected(recipe_rejection)
    if not isinstance(apk_inspector, ApkInspector):
        return _rejected("apk_inspector_unavailable")

    strict_preparation = bool(
        build_recipe.strict
        or runtime_input_vault is not None
        or runtime_signing_identity is not None
        or sealed_apk_path is not None
    )
    if strict_preparation:
        strict_recipe_rejection = _validate_strict_recipe(build_recipe, spec)
        if strict_recipe_rejection is not None:
            return _rejected(strict_recipe_rejection)
        if not isinstance(runtime_input_vault, RuntimeInputVault):
            return _rejected("runtime_input_vault_unavailable")
        if runtime_input_vault.manifest_path is None:
            return _rejected("runtime_input_vault_manifest_unavailable")
        signer = (
            runtime_signing_identity or runtime_input_vault.manifest.signing_identity
        )
        if not isinstance(signer, RuntimeSigningIdentity):
            return _rejected("runtime_signing_identity_unavailable")
        if signer.to_dict() != runtime_input_vault.manifest.signing_identity.to_dict():
            return _rejected("runtime_signing_identity_mismatch")
        if os.environ.get("AIVERIFY_DEPLOYED_APK"):
            return _rejected("ambient_signing_fallback_forbidden")
        if any(
            _paths_overlap(
                runtime_input_vault.root,
                Path(controlled_root).resolve(),
            )
            for controlled_root in (options.workdir, options.artifact_dir)
        ):
            return _rejected("runtime_input_vault_location_invalid")
        try:
            sealed_destination = _strict_sealed_path(
                options,
                build_recipe,
                sealed_apk_path,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            return _rejected("sealed_apk_path_invalid")
        try:
            _verify_manifest_file(runtime_input_vault)
            runtime_input_vault.verify()
        except (OSError, RuntimeError, TypeError, ValueError):
            return _rejected("runtime_input_vault_rejected")
        if type(source_authority) not in {
            MappedRuntimeSourceAuthority,
            MappedSealedInjectionSourceAuthority,
        }:
            return _rejected("runtime_input_binding_unavailable")
        if not isinstance(allow_test_substitutes, bool):
            return _rejected("invalid_test_substitute_policy")
        if not allow_test_substitutes:
            if not isinstance(source_authority.mapping, RuntimeMappingRelease):
                return _rejected("runtime_input_mapping_unverified")
            if source_authority.candidate_root is None:
                return _rejected("runtime_input_mapping_unverified")
            if type(source_authority.delegate) is not SealedInjectionSourceAuthority:
                return _rejected("runtime_input_source_authority_untrusted")
            if (
                runtime_input_vault.manifest.family_id
                != source_authority.mapping.family_id
                or runtime_input_vault.manifest.family_version
                != source_authority.mapping.family_version
            ):
                return _rejected("runtime_input_vault_family_mismatch")
            if build_runner is not None and not isinstance(
                build_runner, SubprocessCommandRunner
            ):
                return _rejected("build_runner_untrusted")
            if (
                build_runner is not None
                and type(build_runner) is not SubprocessCommandRunner
            ):
                return _rejected("build_runner_untrusted")
            inspector_rejection = _validate_production_apk_inspector(
                apk_inspector,
                recipe=build_recipe,
                signer=signer,
            )
            if inspector_rejection is not None:
                return _rejected(inspector_rejection)
            if (
                admission_command_runner is not None
                and type(admission_command_runner) is not SubprocessCommandRunner
            ):
                return _rejected("admission_runner_untrusted")
        verify_inputs = getattr(source_authority, "verify_runtime_inputs", None)
        if callable(verify_inputs):
            try:
                verify_inputs(build_recipe, spec)
            except (OSError, RuntimeError, TypeError, ValueError):
                return _rejected("runtime_input_binding_rejected")
    else:
        signer = None
        sealed_destination = None

    private_vault_path: Path | None = None
    private_signing_keystore_path: Path | None = None
    effective_build_environment: dict[str, str] | None = None
    sealed_created = False

    def reject_after_private_inputs(code: str) -> RuntimePreparationReceipt:
        if private_vault_path is not None:
            shutil.rmtree(private_vault_path.parent, ignore_errors=True)
        if (
            sealed_created
            and sealed_destination is not None
            and sealed_destination.exists()
            and not sealed_destination.is_symlink()
        ):
            try:
                sealed_destination.unlink(missing_ok=True)
            except OSError:
                pass
        return _rejected(code)

    try:
        admission = admit_production_seam(
            spec,
            options,
            command_runner=admission_command_runner,
            source_authority=source_authority,
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        return _rejected("source_admission_unavailable")
    if not admission.admitted:
        checks = admission.receipt.get("checks")
        host_check = checks.get("host_identity") if isinstance(checks, dict) else None
        return _rejected(
            "source_admission_rejected"
            if isinstance(host_check, dict) and host_check.get("status") == "failed"
            else "production_admission_rejected"
        )
    initial_host_receipt = _host_receipt(admission.receipt)
    if initial_host_receipt is None or not _pristine_build_source(initial_host_receipt):
        return _rejected("source_worktree_not_pristine")

    if strict_preparation:
        assert runtime_input_vault is not None
        assert signer is not None
        assert sealed_destination is not None
        try:
            (
                private_vault_path,
                effective_build_environment,
                private_signing_keystore_path,
            ) = _strict_vault_build_inputs(
                runtime_input_vault,
                options=options,
                environment=build_recipe.environment
                or RuntimeBuildEnvironment.default(),
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            return reject_after_private_inputs("runtime_input_vault_rejected")
        if build_runner is not None:
            bind_environment = getattr(build_runner, "bind_environment", None)
            if not callable(bind_environment):
                return reject_after_private_inputs("build_environment_unbound")
            try:
                bind_environment(effective_build_environment)
            except (OSError, RuntimeError, TypeError, ValueError):
                return reject_after_private_inputs("build_environment_unbound")
        if not allow_test_substitutes:
            bind_environment = getattr(apk_inspector, "bind_environment", None)
            if not callable(bind_environment):
                return reject_after_private_inputs("apk_inspector_environment_unbound")
            try:
                bind_environment(effective_build_environment)
            except (OSError, RuntimeError, TypeError, ValueError):
                return reject_after_private_inputs("apk_inspector_environment_unbound")

    host = Path(spec.host_project).resolve()
    try:
        if strict_preparation:
            command_path = host.joinpath(*PurePosixPath(build_recipe.args[0]).parts)
            _require_executable_regular_file(
                command_path,
                code="build executable is unavailable",
            )
        build_executable = _resolve_build_executable(
            build_recipe.args[0],
            host,
        )
        build_executable_sha256 = _sha256_file(build_executable)
    except (OSError, RuntimeError, ValueError):
        return reject_after_private_inputs("build_executable_unavailable")
    if strict_preparation and not any(
        tool.path == build_executable and tool.sha256 == build_executable_sha256
        for tool in build_recipe.tool_identities
    ):
        return reject_after_private_inputs("build_tool_identity_mismatch")
    runner = build_runner or SubprocessCommandRunner(
        environment=effective_build_environment
    )
    started = time.monotonic()
    try:
        build_result = runner.run(
            list(build_recipe.args),
            cwd=host,
            timeout_seconds=build_recipe.timeout_seconds,
        )
    except TimeoutExpired:
        return reject_after_private_inputs("build_timeout")
    except (OSError, RuntimeError, TypeError, ValueError):
        return reject_after_private_inputs("build_unavailable")
    duration_seconds = round(max(0.0, time.monotonic() - started), 6)
    if strict_preparation and duration_seconds > _RUNTIME_BUILD_TIMEOUT_SECONDS:
        return reject_after_private_inputs("build_timeout")
    if (
        not isinstance(build_result, CommandResult)
        or not isinstance(build_result.args, list)
        or not isinstance(build_result.stdout, str)
        or not isinstance(build_result.stderr, str)
        or not isinstance(build_result.returncode, int)
        or isinstance(build_result.returncode, bool)
    ):
        return reject_after_private_inputs("build_unavailable")
    if build_result.args != list(build_recipe.args):
        return reject_after_private_inputs("build_command_mismatch")
    if build_result.returncode == 124:
        return reject_after_private_inputs("build_timeout")
    if build_result.returncode != 0:
        return reject_after_private_inputs("build_failed")
    if strict_preparation:
        assert runtime_input_vault is not None
        assert private_vault_path is not None
        try:
            _verify_manifest_file(runtime_input_vault)
            runtime_input_vault.verify()
            _verify_private_vault_copy(runtime_input_vault, private_vault_path)
            _verify_private_dependency_inputs(
                runtime_input_vault,
                effective_build_environment or {},
            )
            _verify_private_signing_keystore(
                runtime_input_vault,
                effective_build_environment or {},
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            return reject_after_private_inputs("runtime_input_vault_rejected")

    try:
        apk_path, apk_rejection = _locate_apk(
            host,
            build_recipe.apk_glob,
            strict=strict_preparation,
            expected_relative_path=(
                _RUNTIME_BUILD_OUTPUT_RELATIVE_PATH if strict_preparation else None
            ),
        )
    except (OSError, RuntimeError, ValueError):
        return reject_after_private_inputs("apk_locator_failed")
    if apk_rejection is not None or apk_path is None:
        return reject_after_private_inputs(apk_rejection or "apk_missing")
    try:
        apk_bytes = apk_path.read_bytes()
        metadata = apk_inspector.inspect(apk_path)
    except (
        ApkInspectionError,
        OSError,
        RuntimeError,
        TimeoutExpired,
        TypeError,
        ValueError,
    ):
        return reject_after_private_inputs("apk_inspection_failed")
    if not isinstance(metadata, ApkMetadata):
        return reject_after_private_inputs("apk_inspection_failed")
    if metadata.package != spec.package:
        return reject_after_private_inputs("apk_package_mismatch")
    if metadata.launcher_activity != spec.activity:
        return reject_after_private_inputs("apk_activity_mismatch")
    if strict_preparation:
        assert signer is not None
        strict_metadata_rejection = _validate_strict_metadata(
            metadata,
            spec=spec,
            signing_identity=signer,
            expected=expected_apk_metadata,
        )
        if strict_metadata_rejection is not None:
            return reject_after_private_inputs(strict_metadata_rejection)
    if not _apk_unchanged(
        host,
        build_recipe.apk_glob,
        apk_path,
        apk_bytes,
        strict=strict_preparation,
        expected_relative_path=(
            _RUNTIME_BUILD_OUTPUT_RELATIVE_PATH if strict_preparation else None
        ),
    ):
        return reject_after_private_inputs("apk_drift_during_inspection")
    try:
        post_build_admission = _re_admit_built_source(
            admission.receipt,
            spec=spec,
            options=options,
            source_authority=source_authority,
            command_runner=admission_command_runner,
        )
    except (OSError, ProductionSeamAdmissionError, RuntimeError, TypeError, ValueError):
        return reject_after_private_inputs("post_build_source_drift")
    if not _apk_unchanged(
        host,
        build_recipe.apk_glob,
        apk_path,
        apk_bytes,
        strict=strict_preparation,
        expected_relative_path=(
            _RUNTIME_BUILD_OUTPUT_RELATIVE_PATH if strict_preparation else None
        ),
    ):
        return reject_after_private_inputs("apk_drift_during_inspection")

    if strict_preparation:
        assert runtime_input_vault is not None
        assert sealed_destination is not None
        try:
            _verify_manifest_file(runtime_input_vault)
            runtime_input_vault.verify()
            sealed_apk = _seal_apk(apk_bytes, destination=sealed_destination)
            sealed_created = True
        except (OSError, RuntimeError, TypeError, ValueError):
            return reject_after_private_inputs("sealed_apk_rejected")
        if not _apk_unchanged(
            host,
            build_recipe.apk_glob,
            apk_path,
            apk_bytes,
            strict=True,
            expected_relative_path=_RUNTIME_BUILD_OUTPUT_RELATIVE_PATH,
        ):
            try:
                sealed_destination.unlink(missing_ok=True)
            except OSError:
                pass
            return reject_after_private_inputs("apk_drift_during_inspection")
    else:
        sealed_apk = None

    assert spec.source_path is not None
    try:
        source_bytes = spec.source_path.read_bytes()
    except OSError:
        return reject_after_private_inputs("post_build_run_spec_drift")
    if spec.source_sha256 != _sha256_bytes(source_bytes):
        return reject_after_private_inputs("post_build_run_spec_drift")
    build_identity: dict[str, object] = {
        "args": list(build_recipe.args),
        "apk_glob": build_recipe.apk_glob,
        "cwd": str(host),
        "timeout_seconds": build_recipe.timeout_seconds,
        "returncode": build_result.returncode,
        "duration_seconds": duration_seconds,
        "stdout_sha256": _sha256_bytes(build_result.stdout.encode("utf-8")),
        "stderr_sha256": _sha256_bytes(build_result.stderr.encode("utf-8")),
        "executable": {
            "path": str(build_executable),
            "sha256": build_executable_sha256,
        },
    }
    if strict_preparation:
        assert runtime_input_vault is not None
        assert signer is not None
        build_identity.update(
            {
                "build_output_relative_path": _RUNTIME_BUILD_OUTPUT_RELATIVE_PATH,
                "output_relative_path": build_recipe.output_relative_path,
                "timeout_bound_seconds": _RUNTIME_BUILD_TIMEOUT_SECONDS,
                "retry": False,
                "environment_policy": dict(build_recipe.environment_policy),
                "environment": (
                    build_recipe.environment or RuntimeBuildEnvironment.default()
                ).to_dict(),
                "effective_environment": dict(effective_build_environment or {}),
                "private_input_root": str(private_vault_path.parent)
                if private_vault_path
                else None,
                "private_signing_keystore": {
                    "path": str(private_signing_keystore_path),
                    "bytes": private_signing_keystore_path.stat().st_size,
                    "sha256": _sha256_file(private_signing_keystore_path),
                }
                if private_signing_keystore_path
                else None,
                "runtime_input_vault_manifest_sha256": (
                    runtime_input_vault.manifest_sha256
                ),
                "runtime_signing_identity": signer.to_dict(),
                "tool_identities": [
                    tool.to_dict() for tool in build_recipe.tool_identities
                ],
                "test_substitutes": allow_test_substitutes,
            }
        )
    build_identity["identity_sha256"] = _identity(build_identity)
    host_receipt = _host_receipt(admission.receipt)
    post_build_host_receipt = _host_receipt(post_build_admission.receipt)
    assert host_receipt is not None
    assert post_build_host_receipt is not None
    source_identity: dict[str, object] = {
        "authority_kind": type(source_authority).__name__,
        "before": host_receipt,
        "after": post_build_host_receipt,
    }
    mapping_binding = getattr(source_authority, "mapping_binding", None)
    if isinstance(mapping_binding, Mapping):
        source_identity["mapping_binding"] = dict(mapping_binding)
    source_identity["identity_sha256"] = _identity(source_identity)
    if strict_preparation:
        assert sealed_apk is not None
        apk_document: dict[str, object] = {
            "built_path": apk_path.relative_to(host).as_posix(),
            "path": sealed_apk["path"],
            "bytes": len(apk_bytes),
            "sha256": _sha256_bytes(apk_bytes),
            **_strict_metadata_document(metadata),
        }
    else:
        apk_document = {
            "path": apk_path.relative_to(host).as_posix(),
            "bytes": len(apk_bytes),
            "sha256": _sha256_bytes(apk_bytes),
            "package": metadata.package,
            "launcher_activity": metadata.launcher_activity,
        }
    document: dict[str, object] = {
        "schema_version": RUNTIME_PREPARATION_SCHEMA_VERSION,
        "status": "prepared",
        "prepared": True,
        "rejection_code": None,
        "claim_boundary": RUNTIME_PREPARATION_CLAIM_BOUNDARY,
        "run_spec": {
            "path": str(spec.source_path.resolve()),
            "bytes": len(source_bytes),
            "sha256": _sha256_bytes(source_bytes),
            "scenario": spec.scenario.id,
        },
        "source": source_identity,
        "production_admission": admission.receipt,
        "production_admission_sha256": admission.receipt_sha256,
        "build": build_identity,
        "apk": apk_document,
    }
    if strict_preparation:
        assert runtime_input_vault is not None
        assert sealed_apk is not None
        document["runtime_input_vault"] = runtime_input_vault.receipt()
        document["sealed_apk"] = sealed_apk
        document["runtime_effects"] = {
            "shell": False,
            "device": False,
            "android_deployment": False,
            "execution_record": False,
            "agent_or_model": False,
        }
    document["receipt_identity_sha256"] = _identity(document)
    encoded = _canonical_bytes(document)
    return RuntimePreparationReceipt(
        prepared=True,
        receipt_bytes=encoded,
        receipt_sha256=_sha256_bytes(encoded),
        rejection_code=None,
    )


def _verified_receipt_document(
    receipt: RuntimePreparationReceipt | Mapping[str, object],
) -> dict[str, object]:
    if isinstance(receipt, RuntimePreparationReceipt):
        document = receipt.receipt
        encoded = _canonical_bytes(document)
        if (
            encoded != receipt.receipt_bytes
            or _sha256_bytes(encoded) != receipt.receipt_sha256
        ):
            raise RuntimePreparationVerificationError(
                "runtime preparation receipt bytes drifted"
            )
    elif isinstance(receipt, Mapping):
        document = dict(receipt)
    else:
        raise RuntimePreparationVerificationError(
            "runtime preparation receipt is unavailable"
        )
    identity = document.get("receipt_identity_sha256")
    identity_document = dict(document)
    identity_document.pop("receipt_identity_sha256", None)
    if not isinstance(identity, str) or identity != _identity(identity_document):
        raise RuntimePreparationVerificationError(
            "runtime preparation receipt identity drifted"
        )
    if (
        document.get("schema_version") != RUNTIME_PREPARATION_SCHEMA_VERSION
        or document.get("status") != "prepared"
        or document.get("prepared") is not True
        or document.get("rejection_code") is not None
        or document.get("claim_boundary") != RUNTIME_PREPARATION_CLAIM_BOUNDARY
    ):
        raise RuntimePreparationVerificationError(
            "runtime preparation receipt is not prepared"
        )
    return document


def sealed_apk_binding_from_receipt(
    receipt: RuntimePreparationReceipt | Mapping[str, object],
) -> tuple[Path, int, str] | None:
    """Return the sealed artifact path and immutable bytes binding."""
    document = _verified_receipt_document(receipt)
    sealed = document.get("sealed_apk")
    if not isinstance(sealed, Mapping):
        return None
    path = sealed.get("path")
    size = sealed.get("bytes")
    digest = sealed.get("sha256")
    if (
        not isinstance(path, str)
        or not isinstance(size, int)
        or isinstance(size, bool)
        or size < 0
        or not isinstance(digest, str)
        or _HEX_64.fullmatch(digest) is None
    ):
        raise RuntimePreparationVerificationError(
            "runtime preparation sealed APK binding is unavailable"
        )
    sealed_path = Path(path)
    if not sealed_path.is_absolute() or str(sealed_path.resolve()) != path:
        raise RuntimePreparationVerificationError(
            "runtime preparation sealed APK path is not canonical"
        )
    return sealed_path, size, digest


def runtime_preparation_uses_test_substitutes(
    receipt: RuntimePreparationReceipt | Mapping[str, object],
) -> bool:
    """Return the explicit build/inspection substitute marker from a receipt."""
    document = _verified_receipt_document(receipt)
    build = document.get("build")
    if not isinstance(build, Mapping):
        return False
    value = build.get("test_substitutes", False)
    if not isinstance(value, bool):
        raise RuntimePreparationVerificationError(
            "runtime preparation test substitute policy is unavailable"
        )
    return value


def sealed_apk_path_from_receipt(
    receipt: RuntimePreparationReceipt | Mapping[str, object],
) -> Path | None:
    """Return the sole sealed artifact path from a previously verified receipt."""
    binding = sealed_apk_binding_from_receipt(receipt)
    return binding[0] if binding is not None else None


def verify_runtime_preparation_receipt(
    receipt: RuntimePreparationReceipt | Mapping[str, object],
    *,
    spec: RunSpec,
    options: PlannedRunnerOptions,
    source_authority: SourceAuthority,
    apk_inspector: ApkInspector,
    command_runner: CommandRunner | None = None,
    runtime_input_vault: RuntimeInputVault | None = None,
    runtime_signing_identity: RuntimeSigningIdentity | None = None,
    expected_apk_metadata: ApkMetadata | None = None,
) -> None:
    """Revalidate source, Run Spec, options, receipt, and APK before runtime."""
    document = _verified_receipt_document(receipt)
    if not isinstance(spec, RunSpec) or not isinstance(options, PlannedRunnerOptions):
        raise RuntimePreparationVerificationError(
            "runtime preparation contract is invalid"
        )
    if not isinstance(source_authority, SourceAuthority):
        raise RuntimePreparationVerificationError(
            "runtime preparation source authority is unavailable"
        )
    if not isinstance(apk_inspector, ApkInspector):
        raise RuntimePreparationVerificationError(
            "runtime preparation APK inspector is unavailable"
        )
    if expected_apk_metadata is not None and not isinstance(
        expected_apk_metadata, ApkMetadata
    ):
        raise RuntimePreparationVerificationError(
            "runtime preparation expected APK metadata is invalid"
        )
    if command_runner is not None and not isinstance(command_runner, CommandRunner):
        raise RuntimePreparationVerificationError(
            "runtime preparation admission runner is unavailable"
        )
    strict_receipt = "sealed_apk" in document
    verified_vault = runtime_input_vault
    verified_signer = runtime_signing_identity
    if strict_receipt:
        if os.environ.get("AIVERIFY_DEPLOYED_APK"):
            raise RuntimePreparationVerificationError(
                "runtime preparation ambient signing fallback is forbidden"
            )
        raw_vault = document.get("runtime_input_vault")
        if not isinstance(raw_vault, dict):
            raise RuntimePreparationVerificationError(
                "runtime preparation Runtime Input Vault is unavailable"
            )
        if verified_vault is None:
            manifest_path = raw_vault.get("manifest_path")
            root = raw_vault.get("root")
            if not isinstance(manifest_path, str) or not isinstance(root, str):
                raise RuntimePreparationVerificationError(
                    "runtime preparation Runtime Input Vault is unavailable"
                )
            try:
                verified_vault = RuntimeInputVault.from_manifest(
                    manifest_path,
                    root=root,
                )
            except (OSError, RuntimeError, TypeError, ValueError) as error:
                raise RuntimePreparationVerificationError(
                    "runtime preparation Runtime Input Vault is unavailable"
                ) from error
        if not isinstance(verified_vault, RuntimeInputVault):
            raise RuntimePreparationVerificationError(
                "runtime preparation Runtime Input Vault is unavailable"
            )
        if verified_vault.receipt() != raw_vault:
            raise RuntimePreparationVerificationError(
                "runtime preparation Runtime Input Vault identity drifted"
            )
        verified_signer = verified_signer or verified_vault.manifest.signing_identity
        if not isinstance(verified_signer, RuntimeSigningIdentity):
            raise RuntimePreparationVerificationError(
                "runtime preparation signing identity is unavailable"
            )
        if (
            verified_signer.to_dict()
            != verified_vault.manifest.signing_identity.to_dict()
        ):
            raise RuntimePreparationVerificationError(
                "runtime preparation signing identity drifted"
            )
        try:
            _verify_manifest_file(verified_vault)
            verified_vault.verify()
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            raise RuntimePreparationVerificationError(
                "runtime preparation Runtime Input Vault drifted"
            ) from error
        if document.get("runtime_effects") != {
            "shell": False,
            "device": False,
            "android_deployment": False,
            "execution_record": False,
            "agent_or_model": False,
        }:
            raise RuntimePreparationVerificationError(
                "runtime preparation claim boundary drifted"
            )
        if type(source_authority) not in {
            MappedRuntimeSourceAuthority,
            MappedSealedInjectionSourceAuthority,
        }:
            raise RuntimePreparationVerificationError(
                "runtime preparation mapped source authority is unavailable"
            )
    run_spec = document.get("run_spec")
    if not isinstance(run_spec, dict) or spec.source_path is None:
        raise RuntimePreparationVerificationError(
            "runtime preparation Run Spec is unavailable"
        )
    try:
        source_bytes = spec.source_path.resolve().read_bytes()
    except OSError as error:
        raise RuntimePreparationVerificationError(
            "runtime preparation Run Spec is unavailable"
        ) from error
    expected_run_spec = {
        "path": str(spec.source_path.resolve()),
        "bytes": len(source_bytes),
        "sha256": _sha256_bytes(source_bytes),
        "scenario": spec.scenario.id,
    }
    if run_spec != expected_run_spec:
        raise RuntimePreparationVerificationError(
            "runtime preparation Run Spec drifted"
        )

    admission = document.get("production_admission")
    if not isinstance(admission, dict):
        raise RuntimePreparationVerificationError(
            "runtime preparation admission is unavailable"
        )
    if document.get("production_admission_sha256") != _sha256_bytes(
        _canonical_bytes(admission)
    ):
        raise RuntimePreparationVerificationError(
            "runtime preparation admission identity drifted"
        )
    source = document.get("source")
    host = admission.get("host")
    source_body = dict(source) if isinstance(source, dict) else {}
    source_identity = source_body.pop("identity_sha256", None)
    source_after = source_body.get("after")
    if (
        not isinstance(source, dict)
        or not isinstance(host, dict)
        or source_body.get("authority_kind") != type(source_authority).__name__
        or source_body.get("before") != host
        or not isinstance(source_after, dict)
        or source_identity != _identity(source_body)
    ):
        raise RuntimePreparationVerificationError(
            "runtime preparation source receipt drifted"
        )
    recorded_mapping = source_body.get("mapping_binding")
    current_mapping = getattr(source_authority, "mapping_binding", None)
    if isinstance(recorded_mapping, Mapping):
        if not isinstance(current_mapping, Mapping) or dict(recorded_mapping) != dict(
            current_mapping
        ):
            raise RuntimePreparationVerificationError(
                "runtime preparation source mapping drifted"
            )
    elif isinstance(current_mapping, Mapping):
        raise RuntimePreparationVerificationError(
            "runtime preparation source mapping drifted"
        )

    build = document.get("build")
    if not isinstance(build, dict):
        raise RuntimePreparationVerificationError(
            "runtime preparation build identity is unavailable"
        )
    build_identity = build.get("identity_sha256")
    build_body = dict(build)
    build_body.pop("identity_sha256", None)
    args = build_body.get("args")
    timeout = build_body.get("timeout_seconds")
    duration = build_body.get("duration_seconds")
    apk_glob = build_body.get("apk_glob")
    executable = build_body.get("executable")
    host_path = spec.host_project.resolve()
    receipt_environment: RuntimeBuildEnvironment | None = None
    receipt_tools: tuple[RuntimeToolIdentity, ...] = ()
    receipt_test_substitutes = False
    if strict_receipt:
        try:
            receipt_environment = RuntimeBuildEnvironment.from_dict(
                build_body.get("environment")
            )
            raw_tools = build_body.get("tool_identities")
            if not isinstance(raw_tools, list):
                raise ValueError("runtime preparation tool identities are unavailable")
            parsed_tools: list[RuntimeToolIdentity] = []
            for raw_tool in raw_tools:
                if not isinstance(raw_tool, Mapping) or set(raw_tool) != {
                    "name",
                    "path",
                    "sha256",
                }:
                    raise ValueError("runtime preparation tool identities are invalid")
                parsed_tools.append(
                    RuntimeToolIdentity(
                        name=raw_tool["name"],  # type: ignore[arg-type]
                        path=Path(raw_tool["path"]),  # type: ignore[arg-type]
                        sha256=raw_tool["sha256"],  # type: ignore[arg-type]
                    )
                )
            receipt_tools = tuple(parsed_tools)
            raw_test_substitutes = build_body.get("test_substitutes")
            if not isinstance(raw_test_substitutes, bool):
                raise ValueError(
                    "runtime preparation test substitute policy is unavailable"
                )
            receipt_test_substitutes = raw_test_substitutes
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            raise RuntimePreparationVerificationError(
                "runtime preparation build identity drifted"
            ) from error
    raw_environment_policy = build_body.get("environment_policy")
    environment_policy = (
        dict(raw_environment_policy)
        if isinstance(raw_environment_policy, Mapping)
        else {}
    )
    verification_recipe = RuntimeBuildRecipe(
        args=tuple(args) if isinstance(args, list) else (),
        timeout_seconds=timeout if isinstance(timeout, int) else 0,
        apk_glob=apk_glob if isinstance(apk_glob, str) else "",
        output_relative_path=(
            build_body.get("output_relative_path")
            if isinstance(build_body.get("output_relative_path"), str)
            else None
        ),
        environment_policy=environment_policy,
        environment=receipt_environment,
        tool_identities=receipt_tools,
    )
    if strict_receipt and not receipt_test_substitutes:
        if type(source_authority) not in {
            MappedRuntimeSourceAuthority,
            MappedSealedInjectionSourceAuthority,
        }:
            raise RuntimePreparationVerificationError(
                "runtime preparation mapped source authority is unavailable"
            )
        if not isinstance(source_authority.mapping, RuntimeMappingRelease):
            raise RuntimePreparationVerificationError(
                "runtime preparation mapping release is unavailable"
            )
        if source_authority.candidate_root is None:
            raise RuntimePreparationVerificationError(
                "runtime preparation mapping candidate is unavailable"
            )
        if type(source_authority.delegate) is not SealedInjectionSourceAuthority:
            raise RuntimePreparationVerificationError(
                "runtime preparation source authority is untrusted"
            )
        if (
            verified_vault is None
            or verified_vault.manifest.family_id != source_authority.mapping.family_id
            or verified_vault.manifest.family_version
            != source_authority.mapping.family_version
        ):
            raise RuntimePreparationVerificationError(
                "runtime preparation Runtime Input Vault family drifted"
            )
        if verified_signer is None:
            raise RuntimePreparationVerificationError(
                "runtime preparation signing identity is unavailable"
            )
        inspector_rejection = _validate_production_apk_inspector(
            apk_inspector,
            recipe=verification_recipe,
            signer=verified_signer,
        )
        if inspector_rejection is not None:
            raise RuntimePreparationVerificationError(
                "runtime preparation APK inspector is untrusted"
            )
        if (
            command_runner is not None
            and type(command_runner) is not SubprocessCommandRunner
        ):
            raise RuntimePreparationVerificationError(
                "runtime preparation admission runner is untrusted"
            )
    recipe_rejection = (
        _validate_strict_recipe(verification_recipe, spec)
        if strict_receipt
        else _validate_recipe(verification_recipe, spec)
    )
    try:
        current_executable = _resolve_build_executable(
            args[0] if isinstance(args, list) and args else "",
            host_path,
        )
        executable_matches = (
            isinstance(executable, dict)
            and executable.get("path") == str(current_executable)
            and executable.get("sha256") == _sha256_file(current_executable)
        )
    except OSError:
        executable_matches = False
    if (
        not isinstance(build_identity, str)
        or build_identity != _identity(build_body)
        or not isinstance(args, list)
        or any(not isinstance(argument, str) for argument in args)
        or not isinstance(timeout, int)
        or isinstance(timeout, bool)
        or not isinstance(duration, (int, float))
        or isinstance(duration, bool)
        or duration < 0
        or (strict_receipt and duration > _RUNTIME_BUILD_TIMEOUT_SECONDS)
        or not executable_matches
        or build_body.get("cwd") != str(host_path)
        or build_body.get("returncode") != 0
        or recipe_rejection is not None
    ):
        raise RuntimePreparationVerificationError(
            "runtime preparation build identity drifted"
        )

    if strict_receipt:
        assert verified_vault is not None
        assert verified_signer is not None
        expected_environment = (
            verification_recipe.environment or RuntimeBuildEnvironment.default()
        )
        expected_tools = [
            tool.to_dict() for tool in verification_recipe.tool_identities
        ]
        if (
            build_body.get("build_output_relative_path")
            != _RUNTIME_BUILD_OUTPUT_RELATIVE_PATH
            or build_body.get("output_relative_path")
            != verification_recipe.output_relative_path
            or build_body.get("timeout_bound_seconds") != _RUNTIME_BUILD_TIMEOUT_SECONDS
            or build_body.get("retry") is not False
            or build_body.get("environment") != expected_environment.to_dict()
            or build_body.get("tool_identities") != expected_tools
            or build_body.get("environment_policy")
            != dict(verification_recipe.environment_policy)
            or build_body.get("runtime_input_vault_manifest_sha256")
            != verified_vault.manifest_sha256
            or build_body.get("runtime_signing_identity") != verified_signer.to_dict()
            or build_body.get("test_substitutes") is not receipt_test_substitutes
        ):
            raise RuntimePreparationVerificationError(
                "runtime preparation build policy drifted"
            )
        raw_private_vault_path = build_body.get("private_input_root")
        raw_private_signing = build_body.get("private_signing_keystore")
        raw_effective_environment = build_body.get("effective_environment")
        if (
            not isinstance(raw_private_vault_path, str)
            or not isinstance(raw_effective_environment, Mapping)
            or not isinstance(raw_private_signing, Mapping)
            or set(raw_private_signing)
            != {
                "path",
                "bytes",
                "sha256",
            }
        ):
            raise RuntimePreparationVerificationError(
                "runtime preparation private build inputs are unavailable"
            )
        private_root = Path(raw_private_vault_path)
        artifact_root = Path(options.artifact_dir).resolve()
        try:
            if (
                not private_root.is_absolute()
                or private_root.resolve() != private_root
                or _has_symlink_component(private_root)
            ):
                raise ValueError("private runtime input path is not canonical")
            if private_root == artifact_root or private_root.is_relative_to(
                artifact_root
            ):
                raise ValueError("private runtime input path is inside its lane")
            private_root_details = _lstat(private_root)
            if (
                stat.S_ISLNK(private_root_details.st_mode)
                or not stat.S_ISDIR(private_root_details.st_mode)
                or private_root_details.st_mode & 0o077
            ):
                raise ValueError("private runtime input root is unavailable")
            if set(os.listdir(private_root)) != {"vault", "homes"}:
                raise ValueError("private runtime input root is not isolated")
            private_vault_path = private_root / "vault"
            _verify_private_vault_copy(verified_vault, private_vault_path)
            homes_root = private_root / "homes"
            homes_details = _lstat(homes_root)
            if (
                stat.S_ISLNK(homes_details.st_mode)
                or not stat.S_ISDIR(homes_details.st_mode)
                or stat.S_IMODE(homes_details.st_mode) != 0o700
            ):
                raise ValueError("private runtime homes are unavailable")
            expected_effective_environment = {
                name: value for name, value in expected_environment.variables
            }
            expected_home_names = set()
            for key in expected_environment.private_home_keys:
                home = homes_root / key.lower().replace("_", "-")
                home_details = _lstat(home)
                if (
                    stat.S_ISLNK(home_details.st_mode)
                    or not stat.S_ISDIR(home_details.st_mode)
                    or stat.S_IMODE(home_details.st_mode) != 0o700
                ):
                    raise ValueError("private runtime home is unavailable")
                expected_effective_environment[key] = str(home)
                expected_home_names.add(home.name)
            if set(os.listdir(homes_root)) != expected_home_names:
                raise ValueError("private runtime homes are not isolated")
            if dict(raw_effective_environment) != expected_effective_environment:
                raise ValueError("runtime build environment drifted")
            _verify_private_dependency_inputs(
                verified_vault,
                raw_effective_environment,
            )
            private_signing_keystore = Path(raw_private_signing["path"])
            expected_private_signing_keystore = (
                homes_root / "home" / ".android" / "debug.keystore"
            )
            if (
                private_signing_keystore != expected_private_signing_keystore
                or not private_signing_keystore.is_absolute()
                or private_signing_keystore.resolve() != private_signing_keystore
                or _has_symlink_component(private_signing_keystore)
            ):
                raise ValueError("private runtime signing keystore path drifted")
            signing_details = _require_read_only_regular_file(
                private_signing_keystore,
                code="private runtime signing keystore is unavailable",
            )
            if (
                raw_private_signing["bytes"] != signing_details.st_size
                or raw_private_signing["sha256"]
                != _sha256_file(private_signing_keystore)
                or raw_private_signing["sha256"] != verified_signer.keystore_sha256
            ):
                raise ValueError("private runtime signing keystore drifted")
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            raise RuntimePreparationVerificationError(
                "runtime preparation private build inputs drifted"
            ) from error
        if not receipt_test_substitutes:
            bind_environment = getattr(apk_inspector, "bind_environment", None)
            if not callable(bind_environment):
                raise RuntimePreparationVerificationError(
                    "runtime preparation APK inspector environment is unbound"
                )
            try:
                bind_environment(dict(raw_effective_environment))
            except (OSError, RuntimeError, TypeError, ValueError) as error:
                raise RuntimePreparationVerificationError(
                    "runtime preparation APK inspector environment drifted"
                ) from error
        apk = document.get("apk")
        sealed = document.get("sealed_apk")
        if not isinstance(apk, dict) or not isinstance(sealed, dict):
            raise RuntimePreparationVerificationError(
                "runtime preparation sealed APK identity is unavailable"
            )
        raw_sealed_path = sealed.get("path")
        if not isinstance(raw_sealed_path, str):
            raise RuntimePreparationVerificationError(
                "runtime preparation sealed APK path drifted"
            )
        sealed_path = Path(raw_sealed_path)
        artifact_root = Path(options.artifact_dir).resolve()
        try:
            if not sealed_path.is_absolute() or sealed_path.resolve() != sealed_path:
                raise ValueError("sealed APK path is not canonical")
            sealed_path.relative_to(artifact_root)
            details = _require_read_only_regular_file(
                sealed_path,
                code="sealed APK is not immutable",
            )
            sealed_bytes = sealed_path.read_bytes()
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            raise RuntimePreparationVerificationError(
                "runtime preparation sealed APK is unavailable or mutable"
            ) from error
        sealed_digest = _sha256_bytes(sealed_bytes)
        if (
            apk.get("path") != str(sealed_path)
            or apk.get("built_path") != _RUNTIME_BUILD_OUTPUT_RELATIVE_PATH
            or apk.get("bytes") != len(sealed_bytes)
            or apk.get("sha256") != sealed_digest
            or sealed.get("bytes") != details.st_size
            or sealed.get("sha256") != sealed_digest
            or sealed.get("mode") != f"{stat.S_IMODE(details.st_mode):04o}"
            or sealed.get("regular") is not True
            or sealed.get("symlink") is not False
            or sealed.get("hard_links") != 1
        ):
            raise RuntimePreparationVerificationError(
                "runtime preparation sealed APK bytes drifted"
            )
        try:
            metadata = apk_inspector.inspect(sealed_path)
        except (
            ApkInspectionError,
            OSError,
            RuntimeError,
            TimeoutExpired,
            TypeError,
            ValueError,
        ) as error:
            raise RuntimePreparationVerificationError(
                "runtime preparation sealed APK inspection failed"
            ) from error
        if not isinstance(metadata, ApkMetadata) or verified_signer is None:
            raise RuntimePreparationVerificationError(
                "runtime preparation sealed APK inspection failed"
            )
        metadata_rejection = _validate_strict_metadata(
            metadata,
            spec=spec,
            signing_identity=verified_signer,
            expected=expected_apk_metadata,
        )
        if metadata_rejection is not None:
            raise RuntimePreparationVerificationError(
                "runtime preparation sealed APK manifest or signature drifted"
            )
        recorded_metadata = dict(apk)
        for key in ("built_path", "path", "bytes", "sha256"):
            recorded_metadata.pop(key, None)
        if recorded_metadata != _strict_metadata_document(metadata):
            raise RuntimePreparationVerificationError(
                "runtime preparation sealed APK manifest or signature drifted"
            )
        try:
            current_admission = _re_admit_built_source(
                admission,
                spec=spec,
                options=options,
                source_authority=source_authority,
                command_runner=command_runner,
            )
        except (
            OSError,
            ProductionSeamAdmissionError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            raise RuntimePreparationVerificationError(
                "runtime preparation source or runner policy drifted"
            ) from error
        current_host = _host_receipt(current_admission.receipt)
        if current_host != source_after:
            raise RuntimePreparationVerificationError(
                "runtime preparation source or runner policy drifted"
            )
        assert verified_vault is not None
        try:
            _verify_manifest_file(verified_vault)
            verified_vault.verify()
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            raise RuntimePreparationVerificationError(
                "runtime preparation Runtime Input Vault drifted"
            ) from error
        verify_inputs = getattr(source_authority, "verify_runtime_inputs", None)
        if callable(verify_inputs):
            try:
                verify_inputs(verification_recipe, spec)
            except (OSError, RuntimeError, TypeError, ValueError) as error:
                raise RuntimePreparationVerificationError(
                    "runtime preparation runtime input binding drifted"
                ) from error
        if sealed_path.read_bytes() != sealed_bytes:
            raise RuntimePreparationVerificationError(
                "runtime preparation sealed APK bytes drifted"
            )
        return

    apk = document.get("apk")
    if not isinstance(apk, dict):
        raise RuntimePreparationVerificationError(
            "runtime preparation APK identity is unavailable"
        )
    raw_path = apk.get("path")
    if not isinstance(raw_path, str):
        raise RuntimePreparationVerificationError(
            "runtime preparation APK path drifted"
        )
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimePreparationVerificationError(
            "runtime preparation APK path drifted"
        )
    try:
        apk_path = host_path.joinpath(*relative.parts).resolve(strict=True)
        apk_path.relative_to(host_path)
    except (OSError, ValueError) as error:
        raise RuntimePreparationVerificationError(
            "runtime preparation APK path drifted"
        ) from error
    located_apk, locator_error = _locate_apk(host_path, spec.apk_glob)
    if locator_error is not None or located_apk != apk_path:
        raise RuntimePreparationVerificationError("runtime preparation APK set drifted")
    try:
        apk_bytes = apk_path.read_bytes()
    except OSError as error:
        raise RuntimePreparationVerificationError(
            "runtime preparation APK bytes drifted"
        ) from error
    if apk.get("bytes") != len(apk_bytes) or apk.get("sha256") != _sha256_bytes(
        apk_bytes
    ):
        raise RuntimePreparationVerificationError(
            "runtime preparation APK bytes drifted"
        )
    try:
        metadata = apk_inspector.inspect(apk_path)
    except (
        ApkInspectionError,
        OSError,
        RuntimeError,
        TimeoutExpired,
        TypeError,
        ValueError,
    ) as error:
        raise RuntimePreparationVerificationError(
            "runtime preparation APK inspection failed"
        ) from error
    if not isinstance(metadata, ApkMetadata):
        raise RuntimePreparationVerificationError(
            "runtime preparation APK inspection failed"
        )
    if (
        metadata.package != apk.get("package")
        or metadata.package != spec.package
        or metadata.launcher_activity != apk.get("launcher_activity")
        or metadata.launcher_activity != spec.activity
    ):
        raise RuntimePreparationVerificationError(
            "runtime preparation APK manifest drifted"
        )
    if not _apk_unchanged(
        host_path,
        spec.apk_glob,
        apk_path,
        apk_bytes,
    ):
        raise RuntimePreparationVerificationError(
            "runtime preparation APK bytes drifted"
        )
    try:
        current_admission = _re_admit_built_source(
            admission,
            spec=spec,
            options=options,
            source_authority=source_authority,
            command_runner=command_runner,
        )
    except (
        OSError,
        ProductionSeamAdmissionError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        raise RuntimePreparationVerificationError(
            "runtime preparation source or runner policy drifted"
        ) from error
    current_host = _host_receipt(current_admission.receipt)
    if current_host != source_after:
        raise RuntimePreparationVerificationError(
            "runtime preparation source or runner policy drifted"
        )
    if not _apk_unchanged(
        host_path,
        spec.apk_glob,
        apk_path,
        apk_bytes,
    ):
        raise RuntimePreparationVerificationError(
            "runtime preparation APK bytes drifted"
        )


__all__ = [
    "AaptApkInspector",
    "ApkInspectionError",
    "ApkInspector",
    "ApkMetadata",
    "CleanCheckoutSourceAuthority",
    "MappedRuntimeSourceAuthority",
    "MappedSealedInjectionSourceAuthority",
    "RuntimeBuildEnvironment",
    "RuntimeBuildRecipe",
    "RuntimeInputVault",
    "RuntimeInputVaultManifest",
    "RuntimeMappingSourceAuthority",
    "RuntimePreparationHandoff",
    "RuntimePreparationReceipt",
    "RuntimePreparationVerificationError",
    "RuntimeSigningIdentity",
    "RuntimeToolIdentity",
    "RuntimeVaultEntry",
    "RuntimeVaultManifest",
    "SealedInjectionSourceAuthority",
    "SealedRuntimeSourceAuthority",
    "prepare_runtime_case",
    "sealed_apk_binding_from_receipt",
    "sealed_apk_path_from_receipt",
    "runtime_preparation_uses_test_substitutes",
    "verify_runtime_preparation_receipt",
]
