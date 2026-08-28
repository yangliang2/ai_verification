"""Runner-owned Journey backend identities and selection policy.

The Run Spec describes what should be executed.  This module describes which
admitted Journey implementation the runner uses to execute it.  Keeping the
choice here prevents a backend-specific option from becoming part of the
backend-neutral Run Spec.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

CODEX_CLI = "codex_cli"
DETERMINISTIC_ANDROID_V1 = "deterministic_android_v1"
DEFAULT_JOURNEY_BACKEND = CODEX_CLI
SUPPORTED_JOURNEY_BACKENDS = frozenset({CODEX_CLI, DETERMINISTIC_ANDROID_V1})


class JourneyBackendSelectionError(ValueError):
    """Raised when runner policy cannot select an admitted Journey backend."""


class JourneyBackendUnavailableError(JourneyBackendSelectionError):
    """Raised when a supported backend has no execution implementation yet."""


@dataclass(frozen=True)
class JourneyExecutionResult:
    """Backend-neutral Journey output plus normalized-evidence references."""

    data: dict[str, Any]
    result_path: Path
    events_path: Path
    command: list[str]
    metadata: dict[str, str] = field(default_factory=dict)
    backend: str = CODEX_CLI
    raw_result_path: Path | None = None
    raw_events_path: Path | None = None
    normalized_result_path: Path | None = None
    action_lineage_path: Path | None = None

    def __post_init__(self) -> None:
        """Backfill raw references for legacy backend fakes and callers."""
        if self.raw_result_path is None:
            object.__setattr__(self, "raw_result_path", self.result_path)
        if self.raw_events_path is None:
            object.__setattr__(self, "raw_events_path", self.events_path)


@dataclass(frozen=True)
class DriverPlanBinding:
    """The byte identity of a runner-owned deterministic Driver Plan."""

    path: Path
    sha256: str
    bytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "bytes": self.bytes,
        }


@dataclass(frozen=True)
class JourneyDriverSelection:
    """An explicit, runner-policy choice of Journey backend.

    ``driver_plan_path`` is deliberately a policy input rather than a Run Spec
    field.  The plan's strict action semantics are validated by the
    deterministic-driver slice; this object only enforces the selection
    boundary and binds its bytes during admission.
    """

    backend: str = DEFAULT_JOURNEY_BACKEND
    requested_model: str | None = None
    driver_plan_path: Path | None = None

    def validate(self) -> None:
        """Validate backend-specific policy combinations without side effects."""
        if not isinstance(self.backend, str) or not self.backend.strip():
            raise JourneyBackendSelectionError("Journey Driver backend is required")
        if self.backend not in SUPPORTED_JOURNEY_BACKENDS:
            raise JourneyBackendSelectionError(
                "unsupported Journey Driver backend "
                f"(unsupported Verification Agent Backend): {self.backend}"
            )
        if self.requested_model is not None and (
            not isinstance(self.requested_model, str)
            or not self.requested_model.strip()
        ):
            raise JourneyBackendSelectionError(
                "requested driver model cannot be empty"
            )
        if self.driver_plan_path is not None and not isinstance(
            self.driver_plan_path, Path
        ):
            raise JourneyBackendSelectionError("Driver Plan path is invalid")
        if self.backend == CODEX_CLI and self.driver_plan_path is not None:
            raise JourneyBackendSelectionError(
                "Codex CLI does not accept a Driver Plan"
            )
        if self.backend == DETERMINISTIC_ANDROID_V1:
            if self.requested_model is not None:
                raise JourneyBackendSelectionError(
                    "deterministic_android_v1 forbids a requested driver model"
                )
            if self.driver_plan_path is None:
                raise JourneyBackendSelectionError(
                    "deterministic_android_v1 requires a Driver Plan"
                )

    def bind_driver_plan(self) -> DriverPlanBinding | None:
        """Read and checksum the selected plan, if this backend uses one."""
        self.validate()
        if self.driver_plan_path is None:
            return None
        path = self.driver_plan_path.expanduser().resolve()
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise JourneyBackendSelectionError(
                f"Driver Plan cannot be read: {path}"
            ) from error
        return DriverPlanBinding(
            path=path,
            sha256=hashlib.sha256(raw).hexdigest(),
            bytes=len(raw),
        )

    def to_dict(self) -> dict[str, object]:
        """Return the stable policy representation used by receipts."""
        result: dict[str, object] = {
            "backend": self.backend,
            "requested_model": self.requested_model,
        }
        if self.driver_plan_path is not None:
            result["driver_plan_path"] = str(
                self.driver_plan_path.expanduser().resolve()
            )
        return result


class JourneyBackend(Protocol):
    """Minimal execution surface shared by selected Journey backends."""

    backend_id: str

    def execute(self, request: Any) -> JourneyExecutionResult:
        """Execute one backend-specific Journey request."""


def backend_id(backend: object) -> str:
    """Return a backend object's declared identity, defaulting legacy fakes."""
    value = getattr(backend, "backend_id", DEFAULT_JOURNEY_BACKEND)
    if not isinstance(value, str) or not value.strip():
        raise JourneyBackendSelectionError("Journey backend identity is invalid")
    return value


def create_journey_backend(
    selection: JourneyDriverSelection,
    *,
    codex_factory: Callable[[], JourneyBackend] | None = None,
    deterministic_backend: JourneyBackend | None = None,
    deterministic_factory: Callable[[], JourneyBackend] | None = None,
) -> JourneyBackend:
    """Create the selected backend without inferring it from Run Spec data.

    Deterministic implementations are injected by the runner or a caller;
    selection remains explicit and fail-closed rather than silently falling
    back to Codex.
    """
    selection.validate()
    if selection.backend == CODEX_CLI:
        if codex_factory is None:
            from aiverify.runner.codex_backend import CodexCliBackend

            codex_factory = CodexCliBackend
        backend = codex_factory()
    else:
        backend = deterministic_backend
        if backend is None and deterministic_factory is not None:
            backend = deterministic_factory()
        if backend is None:
            raise JourneyBackendUnavailableError(
                "deterministic_android_v1 backend implementation is unavailable"
            )
    selected_id = backend_id(backend)
    if selected_id != selection.backend:
        raise JourneyBackendSelectionError(
            "selected Journey backend identity contradicts runner policy"
        )
    return backend


__all__ = [
    "CODEX_CLI",
    "DEFAULT_JOURNEY_BACKEND",
    "DETERMINISTIC_ANDROID_V1",
    "SUPPORTED_JOURNEY_BACKENDS",
    "DriverPlanBinding",
    "JourneyBackend",
    "JourneyBackendSelectionError",
    "JourneyBackendUnavailableError",
    "JourneyDriverSelection",
    "JourneyExecutionResult",
    "backend_id",
    "create_journey_backend",
]
