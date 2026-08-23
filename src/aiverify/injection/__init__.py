"""Provenance-bound, disposable Injection Lab source preparation.

The Injection Lab intentionally sits before Discovery Campaign and Run Spec.
Its M0.1/M0.2 surface materializes and structurally admits source variants
only; it never builds, installs, or executes an Android application.
"""

from aiverify.injection.materialization import (
    InjectionCleanupError,
    InjectionMaterializer,
    InjectionMaterializerError,
    capture_baseline_provenance,
    source_tree_sha256_for_commit,
    source_tree_sha256_from_worktree,
)
from aiverify.injection.admission import (
    AdmissionLedger,
    AdmissionLedgerEntry,
    InjectedCasePackage,
    InjectionAdmission,
    admit_catalogued_candidate,
)
from aiverify.injection.catalog import (
    CheckedInCuratedSourceCatalog,
    CuratedCatalogError,
    CuratedSourceCatalog,
    CuratedSourceEntry,
    DisclosureAuditArtifact,
    FixtureAnchor,
    TaxonomyRelationship,
    load_curated_source_catalog,
)
from aiverify.injection.disclosure import (
    CataloguedDisclosureReview,
    DisclosureFinding,
    DisclosurePolicy,
    DisclosureReview,
    review_visible_packet_material,
    review_catalogued_admission,
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
    "AdmissionLedger",
    "AdmissionLedgerEntry",
    "BaselineProvenance",
    "CataloguedDisclosureReview",
    "CheckedInCuratedSourceCatalog",
    "CuratedCatalogError",
    "CuratedSourceCatalog",
    "CuratedSourceEntry",
    "DisclosureAuditArtifact",
    "DisclosureFinding",
    "DisclosurePolicy",
    "DisclosureReview",
    "FaultOperator",
    "FixtureAnchor",
    "InjectionCandidate",
    "InjectionAdmission",
    "InjectionCleanupError",
    "InjectionContractError",
    "InjectedCasePackage",
    "InjectionMaterializer",
    "InjectionMaterializerError",
    "InjectionReceipt",
    "MaterializedWorktree",
    "SourceDelta",
    "TaxonomyRelationship",
    "admit_catalogued_candidate",
    "capture_baseline_provenance",
    "load_curated_source_catalog",
    "review_visible_packet_material",
    "review_catalogued_admission",
    "source_tree_sha256_for_commit",
    "source_tree_sha256_from_worktree",
]
