"""Provenance-bound, disposable Injection Lab source preparation.

The Injection Lab intentionally sits before Discovery Campaign and Run Spec.
Its M0.1 through M0.4 surfaces materialize, structurally admit, review, and
compile source variants without building, installing, or executing an Android
application.
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
    STALE_RESULT_DISCLOSURE_POLICY,
    review_visible_packet_material,
    review_catalogued_admission,
)
from aiverify.injection.packets import (
    AuditorCase,
    AuditorPair,
    PacketCompilationError,
    VerifierPacket,
    compile_change_target_packet,
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
    "AuditorCase",
    "AuditorPair",
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
    "PacketCompilationError",
    "SourceDelta",
    "STALE_RESULT_DISCLOSURE_POLICY",
    "TaxonomyRelationship",
    "VerifierPacket",
    "admit_catalogued_candidate",
    "capture_baseline_provenance",
    "compile_change_target_packet",
    "load_curated_source_catalog",
    "review_visible_packet_material",
    "review_catalogued_admission",
    "source_tree_sha256_for_commit",
    "source_tree_sha256_from_worktree",
]
