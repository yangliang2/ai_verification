"""M0.4 public ChangeTarget packet contract tests.

The accepted public seam is ``compile_change_target_packet``: an auditor-side
paired, sealed input becomes one verifier-facing packet, or no packet at all.
The test fixture deliberately keeps every outcome label and audit explanation
outside the packet while proving that its source change is real and bounded.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
import difflib
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import traceback

import pytest

from aiverify.injection import (
    AuditorCase,
    AuditorPair,
    CuratedSourceCatalog,
    CuratedSourceEntry,
    DisclosurePolicy,
    FaultOperator,
    FixtureAnchor,
    InjectionCandidate,
    InjectionMaterializer,
    PacketCompilationError,
    SourceDelta,
    TaxonomyRelationship,
    VerifierPacket,
    admit_catalogued_candidate,
    capture_baseline_provenance,
    compile_change_target_packet,
    review_catalogued_admission,
    review_visible_packet_material,
)


def test_change_target_packet_rejects_a_missing_pair_with_a_stable_reason() -> None:
    with pytest.raises(PacketCompilationError) as raised:
        compile_change_target_packet(
            catalog_path="not-read-without-a-pair.json",
            pair=None,
            variant="defect",
            policy=DisclosurePolicy(
                policy_id="missing-pair-v1",
                forbidden_tokens=("HIDDEN_PAIR_91d3e7",),
            ),
        )

    assert raised.value.code == "pair_missing"


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def _write_catalog(
    repository: Path,
    *,
    incompatible_provenance: bool = False,
    incompatible_fixture_anchor: bool = False,
) -> Path:
    defect_baseline = capture_baseline_provenance(
        repository,
        _git(repository, "rev-parse", "HEAD"),
    )
    control_baseline = defect_baseline
    control_baseline_text = "baseline\n"
    if incompatible_provenance:
        (repository / "source.txt").write_text("alternate baseline\n", encoding="utf-8")
        _git(repository, "add", "source.txt")
        _git(repository, "commit", "-m", "control baseline")
        control_baseline = capture_baseline_provenance(
            repository,
            _git(repository, "rev-parse", "HEAD"),
        )
        control_baseline_text = "alternate baseline\n"
    if incompatible_fixture_anchor:
        (repository / "fixture-anchor-two.txt").write_text(
            "second fixture\n",
            encoding="utf-8",
        )
    entries = []
    for number, variant, baseline, baseline_text, replacement in (
        ("one", "defect", defect_baseline, "baseline\n", "candidate one\n"),
        (
            "two",
            "control",
            control_baseline,
            control_baseline_text,
            "candidate two\n",
        ),
    ):
        patch_text = "".join(
            difflib.unified_diff(
                [baseline_text],
                [replacement],
                fromfile="a/source.txt",
                tofile="b/source.txt",
            )
        )
        source_delta = SourceDelta.from_patch(
            delta_id=f"change-{number}",
            patch_text=patch_text,
            source_ref=f"patches/change-{number}.patch",
        )
        patch_path = repository / (source_delta.source_ref or "")
        patch_path.parent.mkdir(exist_ok=True)
        patch_path.write_text(source_delta.patch_text, encoding="utf-8")
        candidate = InjectionCandidate(
            candidate_id=f"candidate-{number}",
            baseline=baseline,
            source_delta=source_delta,
            operator=FaultOperator(
                operator_id="HIDDEN_OPERATOR_7f3a91c4",
                version="v1",
                applicability="HIDDEN_OPERATOR_SCOPE_5d8f2a",
                safety_boundary="HIDDEN_OPERATOR_BOUNDARY_82c6e1",
            ),
            variant=variant,
        )
        fixture_anchor_path = (
            "fixture-anchor-two.txt"
            if incompatible_fixture_anchor and number == "two"
            else "fixture-anchor.txt"
        )
        entries.append(
            CuratedSourceEntry(
                source_id=f"source-{number}",
                candidate=candidate,
                patch_path=source_delta.source_ref or "",
                fixture_anchor=FixtureAnchor(
                    path=fixture_anchor_path,
                    sha256=sha256(
                        (repository / fixture_anchor_path).read_bytes()
                    ).hexdigest(),
                ),
                population_classification="curated_controlled_injection",
                taxonomy_relationship=TaxonomyRelationship.known(
                    "HIDDEN_TAXONOMY_0c4e9b"
                ),
            )
        )
    catalog = CuratedSourceCatalog(entries=tuple(entries))
    catalog_path = repository / "curated-source-catalog.json"
    catalog_path.write_text(json.dumps(catalog.to_dict(), sort_keys=True), encoding="utf-8")
    return catalog_path


_HIDDEN_TOKENS = (
    "defect",
    "control",
    "HIDDEN_OPERATOR_7f3a91c4",
    "HIDDEN_TAXONOMY_0c4e9b",
    "HIDDEN_SYMPTOM_48a1de",
    "HIDDEN_ORACLE_b75c09",
    "HIDDEN_RATIONALE_d2f684",
)


def _policy(*extra_tokens: str) -> DisclosurePolicy:
    return DisclosurePolicy(
        policy_id="high-entropy-audit-only-v1",
        forbidden_tokens=(*_HIDDEN_TOKENS, *extra_tokens),
    )


@dataclass(frozen=True)
class _AuditedFixture:
    repository: Path
    catalog_path: Path
    materializer: InjectionMaterializer
    pair: AuditorPair
    policy: DisclosurePolicy

    def cleanup(self) -> None:
        for case in (self.pair.defect, self.pair.control):
            if case.admission.receipt is not None:
                self.materializer.cleanup(case.admission.receipt)


def _safe_audited_pair(
    tmp_path: Path,
    *,
    policy: DisclosurePolicy | None = None,
    worktree_root_name: str = "owned-worktrees",
    incompatible_provenance: bool = False,
    incompatible_fixture_anchor: bool = False,
) -> _AuditedFixture:
    repository = tmp_path / "fixture"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.email", "test@example.invalid")
    _git(repository, "config", "user.name", "Injection Lab Test")
    _git(repository, "remote", "add", "origin", "https://example.invalid/safe.git")
    (repository / "source.txt").write_text("baseline\n", encoding="utf-8")
    (repository / "fixture-anchor.txt").write_text("fixture\n", encoding="utf-8")
    _git(repository, "add", "source.txt", "fixture-anchor.txt")
    _git(repository, "commit", "-m", "baseline")
    catalog_path = _write_catalog(
        repository,
        incompatible_provenance=incompatible_provenance,
        incompatible_fixture_anchor=incompatible_fixture_anchor,
    )
    tracked_catalog_inputs = ["curated-source-catalog.json", "patches"]
    if incompatible_fixture_anchor:
        tracked_catalog_inputs.append("fixture-anchor-two.txt")
    _git(repository, "add", *tracked_catalog_inputs)
    _git(repository, "commit", "-m", "add safe pair catalog")

    actual_policy = policy or _policy()
    materializer = InjectionMaterializer(
        repository,
        tmp_path / worktree_root_name,
    )
    defect_admission = admit_catalogued_candidate(catalog_path, "source-one", materializer)
    control_admission = admit_catalogued_candidate(catalog_path, "source-two", materializer)
    assert defect_admission.status == "sealed", (
        defect_admission.rejection_code,
        defect_admission.receipt.rejection_code if defect_admission.receipt else None,
    )
    assert control_admission.status == "sealed", (
        control_admission.rejection_code,
        control_admission.receipt.rejection_code if control_admission.receipt else None,
    )
    defect_review = review_catalogued_admission(
        catalog_path,
        "source-one",
        defect_admission,
        actual_policy,
    )
    control_review = review_catalogued_admission(
        catalog_path,
        "source-two",
        control_admission,
        actual_policy,
    )
    pair = AuditorPair(
        defect=AuditorCase(
            admission=defect_admission,
            disclosure_review=defect_review,
            expected_symptom="HIDDEN_SYMPTOM_48a1de",
            oracle="HIDDEN_ORACLE_b75c09",
            admission_rationale="HIDDEN_RATIONALE_d2f684",
        ),
        control=AuditorCase(
            admission=control_admission,
            disclosure_review=control_review,
            expected_symptom="HIDDEN_SYMPTOM_48a1de",
            oracle="HIDDEN_ORACLE_b75c09",
            admission_rationale="HIDDEN_RATIONALE_d2f684",
        ),
    )
    return _AuditedFixture(
        repository=repository,
        catalog_path=catalog_path,
        materializer=materializer,
        pair=pair,
        policy=actual_policy,
    )


@contextmanager
def _prepared_audited_pair(
    tmp_path: Path,
    *,
    policy: DisclosurePolicy | None = None,
    worktree_root_name: str = "owned-worktrees",
    incompatible_provenance: bool = False,
    incompatible_fixture_anchor: bool = False,
) -> Iterator[_AuditedFixture]:
    fixture = _safe_audited_pair(
        tmp_path,
        policy=policy,
        worktree_root_name=worktree_root_name,
        incompatible_provenance=incompatible_provenance,
        incompatible_fixture_anchor=incompatible_fixture_anchor,
    )
    try:
        yield fixture
    finally:
        fixture.cleanup()


def test_safe_audited_pair_compiles_a_deterministic_blind_change_target_packet(
    tmp_path: Path,
) -> None:
    with _prepared_audited_pair(tmp_path) as fixture:
        packet = compile_change_target_packet(
            catalog_path=fixture.catalog_path,
            pair=fixture.pair,
            variant="defect",
            policy=fixture.policy,
        )
        repeated = compile_change_target_packet(
            catalog_path=fixture.catalog_path,
            pair=fixture.pair,
            variant="defect",
            policy=fixture.policy,
        )
        control_packet = compile_change_target_packet(
            catalog_path=fixture.catalog_path,
            pair=fixture.pair,
            variant="control",
            policy=fixture.policy,
        )

        assert packet.target_kind == "change_target"
        assert set(packet.to_dict()) == {
            "schema_version",
            "target_kind",
            "packet_id",
            "source_origin",
            "source_commit",
            "baseline_source_tree_sha256",
            "materialized_source_tree_sha256",
            "worktree_path",
            "patch_format",
            "patch_path",
            "patch_text",
            "patch_sha256",
            "result_diff_sha256",
            "receipt_identity_sha256",
            "claim_boundary",
            "identity_sha256",
        }
        assert packet.packet_id == repeated.packet_id
        assert packet.identity_sha256 == repeated.identity_sha256
        assert packet.canonical_bytes == repeated.canonical_bytes
        assert VerifierPacket.from_dict(packet.to_dict()) == packet
        relocated = replace(
            packet,
            worktree_path="/private/tmp/independently-materialized-source",
        )
        assert relocated.identity_sha256 == packet.identity_sha256
        assert relocated.canonical_bytes != packet.canonical_bytes
        assert packet.patch_text == (
            fixture.repository / "patches/change-one.patch"
        ).read_text(
            encoding="utf-8"
        )
        assert Path(packet.patch_path).read_text(encoding="utf-8") == packet.patch_text
        assert packet.patch_sha256 == sha256(packet.patch_text.encode("utf-8")).hexdigest()
        assert control_packet.packet_id != packet.packet_id
        assert control_packet.patch_text == (
            fixture.repository / "patches/change-two.patch"
        ).read_text(encoding="utf-8")
        assert Path(packet.worktree_path, "source.txt").read_text(encoding="utf-8") == (
            "candidate one\n"
        )
        assert review_visible_packet_material(
            fixture.policy,
            packet.to_dict(),
        ).status == "eligible"
        for token in fixture.policy.forbidden_tokens:
            assert token.encode("utf-8") not in packet.canonical_bytes


def test_change_target_packet_rejects_an_unsealed_pair_member(tmp_path: Path) -> None:
    with _prepared_audited_pair(tmp_path) as fixture:
        rejected_admission = admit_catalogued_candidate(
            fixture.catalog_path,
            "not-declared",
            fixture.materializer,
        )
        unsealed_pair = replace(
            fixture.pair,
            defect=replace(
                fixture.pair.defect,
                admission=rejected_admission,
            ),
        )

        with pytest.raises(PacketCompilationError) as raised:
            compile_change_target_packet(
                catalog_path=fixture.catalog_path,
                pair=unsealed_pair,
                variant="defect",
                policy=fixture.policy,
            )

        assert raised.value.code == "admission_not_sealed"


def test_change_target_packet_rejects_worktree_provenance_mismatch(
    tmp_path: Path,
) -> None:
    with _prepared_audited_pair(tmp_path) as fixture:
        receipt = fixture.pair.defect.admission.receipt
        assert receipt is not None
        assert receipt.worktree is not None
        contradictory_receipt = replace(
            receipt,
            worktree=replace(receipt.worktree, baseline_commit="f" * 40),
        )
        contradictory_pair = replace(
            fixture.pair,
            defect=replace(
                fixture.pair.defect,
                admission=replace(
                    fixture.pair.defect.admission,
                    receipt=contradictory_receipt,
                ),
            ),
        )

        with pytest.raises(PacketCompilationError) as raised:
            compile_change_target_packet(
                catalog_path=fixture.catalog_path,
                pair=contradictory_pair,
                variant="defect",
                policy=fixture.policy,
            )

        assert raised.value.code == "admission_provenance_mismatch"


def test_change_target_packet_rejects_incompatible_pair_provenance(
    tmp_path: Path,
) -> None:
    with _prepared_audited_pair(
        tmp_path,
        incompatible_provenance=True,
    ) as fixture:
        with pytest.raises(PacketCompilationError) as raised:
            compile_change_target_packet(
                catalog_path=fixture.catalog_path,
                pair=fixture.pair,
                variant="defect",
                policy=fixture.policy,
            )

        assert raised.value.code == "pair_provenance_mismatch"


def test_change_target_packet_rejects_a_pair_with_different_fixture_anchors(
    tmp_path: Path,
) -> None:
    with _prepared_audited_pair(
        tmp_path,
        incompatible_fixture_anchor=True,
    ) as fixture:
        with pytest.raises(PacketCompilationError) as raised:
            compile_change_target_packet(
                catalog_path=fixture.catalog_path,
                pair=fixture.pair,
                variant="defect",
                policy=fixture.policy,
            )

        assert raised.value.code == "pair_fixture_anchor_mismatch"


def test_change_target_packet_rejects_a_pair_that_fails_its_disclosure_policy(
    tmp_path: Path,
) -> None:
    with _prepared_audited_pair(tmp_path, policy=_policy("candidate")) as fixture:
        assert fixture.pair.defect.disclosure_review.status == "rejected"

        with pytest.raises(PacketCompilationError) as raised:
            compile_change_target_packet(
                catalog_path=fixture.catalog_path,
                pair=fixture.pair,
                variant="defect",
                policy=fixture.policy,
            )

        assert raised.value.code == "disclosure_policy_rejected"


def test_change_target_packet_rechecks_the_final_verifier_visible_path(
    tmp_path: Path,
) -> None:
    hidden_path = "HIDDEN_WORKTREE_PATH_8b1c4e"
    with _prepared_audited_pair(
        tmp_path,
        policy=_policy(hidden_path),
        worktree_root_name=hidden_path,
    ) as fixture:
        assert fixture.pair.defect.disclosure_review.status == "eligible"

        with pytest.raises(PacketCompilationError) as raised:
            compile_change_target_packet(
                catalog_path=fixture.catalog_path,
                pair=fixture.pair,
                variant="defect",
                policy=fixture.policy,
            )

        assert raised.value.code == "packet_disclosure_detected"


def test_change_target_packet_sanitizes_a_worktree_resolution_error(
    tmp_path: Path,
) -> None:
    hidden_path = "HIDDEN_ERROR_PATH_93a1f0"
    with _prepared_audited_pair(tmp_path, policy=_policy(hidden_path)) as fixture:
        symlink_loop = tmp_path / hidden_path
        symlink_loop.symlink_to(symlink_loop.name)
        receipt = fixture.pair.defect.admission.receipt
        assert receipt is not None
        assert receipt.worktree is not None
        forged_pair = replace(
            fixture.pair,
            defect=replace(
                fixture.pair.defect,
                admission=replace(
                    fixture.pair.defect.admission,
                    receipt=replace(
                        receipt,
                        worktree=replace(receipt.worktree, path=str(symlink_loop)),
                    ),
                ),
            ),
        )

        with pytest.raises(PacketCompilationError) as raised:
            compile_change_target_packet(
                catalog_path=fixture.catalog_path,
                pair=forged_pair,
                variant="defect",
                policy=fixture.policy,
            )

        assert raised.value.code == "materialized_source_unavailable"
        assert hidden_path not in str(raised.value)
        assert hidden_path not in "".join(traceback.format_exception(raised.value))
