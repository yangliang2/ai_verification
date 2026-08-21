"""Provenance-bound, disposable source-delta materialization.

The Injection Lab intentionally sits before Discovery Campaign and Run Spec.
Its M0.1 surface prepares source variants only; it never builds, installs, or
executes an Android application.
"""

from aiverify.injection.materialization import (
    InjectionCleanupError,
    InjectionMaterializer,
    InjectionMaterializerError,
    capture_baseline_provenance,
    source_tree_sha256_for_commit,
    source_tree_sha256_from_worktree,
)
from aiverify.injection.models import (
    BaselineProvenance,
    FaultOperator,
    InjectionCandidate,
    InjectionContractError,
    InjectionReceipt,
    MaterializedWorktree,
    SourceDelta,
)

__all__ = [
    "BaselineProvenance",
    "FaultOperator",
    "InjectionCandidate",
    "InjectionCleanupError",
    "InjectionContractError",
    "InjectionMaterializer",
    "InjectionMaterializerError",
    "InjectionReceipt",
    "MaterializedWorktree",
    "SourceDelta",
    "capture_baseline_provenance",
    "source_tree_sha256_for_commit",
    "source_tree_sha256_from_worktree",
]
