"""Contemporaneous Codex CLI invocation identity receipts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

from aiverify.runner.command import CommandRunner
from aiverify.runner.execution_record import write_json_artifact


class CodexIdentityError(RuntimeError):
    """Raised when a Codex invocation cannot be bound to an effective model."""


def default_codex_session_root() -> Path:
    """Return the session directory used by the active Codex CLI installation."""
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return codex_home / "sessions"


def capture_codex_invocation_identity(
    *,
    role: str,
    requested_model: str | None,
    command: list[str],
    codex_bin: str,
    runner: CommandRunner,
    events_path: Path,
    receipt_path: Path,
    session_root: Path | None = None,
) -> dict:
    """Persist a create-only receipt derived from this invocation's session log."""
    thread_id = _thread_id(events_path)
    source_path, session_meta, turn_context = _session_observation(
        thread_id,
        session_root=session_root or default_codex_session_root(),
    )
    effective_model = turn_context.get("model")
    if not isinstance(effective_model, str) or not effective_model.strip():
        raise CodexIdentityError("Codex turn_context.model is missing or unknown")

    _validate_model_override(
        requested_model=requested_model,
        effective_model=effective_model,
        command=command,
    )
    version_result = runner.run([codex_bin, "--version"])
    if version_result.returncode != 0 or not version_result.stdout.strip():
        raise CodexIdentityError("Codex CLI version could not be observed")
    binary_path = _resolve_binary(codex_bin)
    source_version = session_meta.get("cli_version")
    if not isinstance(source_version, str) or not source_version.strip():
        raise CodexIdentityError("Codex session_meta.cli_version is missing")
    if _version_number(version_result.stdout) != _version_number(source_version):
        raise CodexIdentityError(
            "Codex binary version contradicts session_meta.cli_version"
        )

    prompt = command[-1] if command else ""
    receipt = {
        "schema_version": 1,
        "role": role,
        "backend": "codex_cli",
        "binary": {
            "requested": codex_bin,
            "resolved_path": str(binary_path),
            "sha256": _sha256_file(binary_path),
            "version": version_result.stdout.strip(),
        },
        "requested_model": requested_model,
        "effective_model": effective_model,
        "effective_model_source": {
            "kind": "codex_session_turn_context",
            "session_path": str(source_path),
            "session_sha256": _sha256_file(source_path),
            "thread_id": thread_id,
            "turn_id": turn_context.get("turn_id"),
        },
        "source_observation": {
            "session_meta": {
                "id": session_meta.get("id"),
                "cwd": session_meta.get("cwd"),
                "cli_version": source_version,
                "source": session_meta.get("source"),
            },
            "turn_context": {
                "turn_id": turn_context.get("turn_id"),
                "model": effective_model,
            },
        },
        "command": {
            "argv_without_prompt": command[:-1],
            "prompt_sha256": _sha256_bytes(prompt.encode("utf-8")),
        },
    }
    write_json_artifact(receipt_path, receipt)
    return receipt


def _thread_id(events_path: Path) -> str:
    try:
        lines = Path(events_path).read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise CodexIdentityError(f"cannot read Codex event stream: {error}") from error
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
            if isinstance(thread_id, str) and thread_id:
                return thread_id
    raise CodexIdentityError("Codex event stream has no thread.started identity")


def _session_observation(
    thread_id: str,
    *,
    session_root: Path,
) -> tuple[Path, dict, dict]:
    try:
        candidates = sorted(
            path
            for path in Path(session_root).rglob(f"*{thread_id}.jsonl")
            if path.name.endswith(f"-{thread_id}.jsonl")
        )
    except OSError as error:
        raise CodexIdentityError(f"cannot inspect Codex sessions: {error}") from error
    if len(candidates) != 1:
        raise CodexIdentityError(
            f"expected one Codex session for thread {thread_id}, found {len(candidates)}"
        )
    source_path = candidates[0]
    session_meta: dict | None = None
    turn_context: dict | None = None
    try:
        lines = source_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise CodexIdentityError(f"cannot read Codex session: {error}") from error
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise CodexIdentityError("Codex session contains invalid JSONL") from error
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        if event.get("type") == "session_meta" and payload.get("id") == thread_id:
            session_meta = payload
        elif event.get("type") == "turn_context" and turn_context is None:
            turn_context = payload
    if session_meta is None or turn_context is None:
        raise CodexIdentityError(
            "Codex session lacks matching session_meta or turn_context"
        )
    return source_path, session_meta, turn_context


def _validate_model_override(
    *,
    requested_model: str | None,
    effective_model: str,
    command: list[str],
) -> None:
    if requested_model is None:
        return
    try:
        command_model = command[command.index("--model") + 1]
    except (ValueError, IndexError) as error:
        raise CodexIdentityError(
            "requested model override did not reach the Codex command"
        ) from error
    if command_model != requested_model:
        raise CodexIdentityError("Codex command model contradicts requested model")
    if effective_model != requested_model:
        raise CodexIdentityError("Codex effective model contradicts requested model")


def _resolve_binary(binary: str) -> Path:
    resolved = shutil.which(binary)
    if resolved is None:
        candidate = Path(binary).expanduser()
        if candidate.is_file():
            resolved = str(candidate)
    if resolved is None:
        raise CodexIdentityError(f"Codex binary could not be resolved: {binary}")
    path = Path(resolved).resolve()
    if not path.is_file():
        raise CodexIdentityError(f"Codex binary is not a file: {path}")
    return path


def _version_number(value: str) -> str:
    return value.strip().split()[-1]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
