"""Provenance-bound, disposable Injection Lab source preparation.

The Injection Lab intentionally sits before Discovery Campaign and Run Spec.
Its M0.1 through M0.6 surfaces materialize, structurally admit, review, and
compile source variants plus a four-cell audit-side family without building,
installing, or executing an Android application.
"""

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
    STALE_RESULT_DISCLOSURE_POLICY,
    CataloguedDisclosureReview,
    DisclosureFinding,
    DisclosurePolicy,
    DisclosureReview,
    review_catalogued_admission,
    review_visible_packet_material,
)
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
from aiverify.injection.packets import (
    AuditorCase,
    AuditorCaseFamily,
    AuditorMapping,
    AuditorMappingEntry,
    AuditorPair,
    PacketCompilationError,
    ProjectTargetPacket,
    VerifierPacket,
    VerifierPacketFamily,
    compile_change_target_packet,
    compile_four_cell_case_family,
    compile_project_target_packet,
)

__all__ = [
    "STALE_RESULT_DISCLOSURE_POLICY",
    "AdmissionLedger",
    "AdmissionLedgerEntry",
    "AuditorCase",
    "AuditorCaseFamily",
    "AuditorMapping",
    "AuditorMappingEntry",
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
    "InjectedCasePackage",
    "InjectionAdmission",
    "InjectionCandidate",
    "InjectionCleanupError",
    "InjectionContractError",
    "InjectionMaterializer",
    "InjectionMaterializerError",
    "InjectionReceipt",
    "MaterializedWorktree",
    "PacketCompilationError",
    "ProjectTargetPacket",
    "SourceDelta",
    "TaxonomyRelationship",
    "VerifierPacket",
    "VerifierPacketFamily",
    "admit_catalogued_candidate",
    "capture_baseline_provenance",
    "compile_change_target_packet",
    "compile_four_cell_case_family",
    "compile_project_target_packet",
    "load_curated_source_catalog",
    "review_catalogued_admission",
    "review_visible_packet_material",
    "source_tree_sha256_for_commit",
    "source_tree_sha256_from_worktree",
]
