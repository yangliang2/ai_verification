"""M8 state-evolution qualification freeze and side-effect-free preflight.

The M8 qualification contract is deliberately a boundary object.  It freezes
the population and every decision rule before a device lane can run, while the
preflight exercises the public discovery lifecycle with neutral inputs.  No
APK is built, installed, launched, or interpreted here; those actions belong to
the formal consumer in issue #122.

The auditor mapping is intentionally not loaded by this module.  It is an
auditor-only artifact and is released only after the campaign hypothesis and
attack plan have been frozen and admitted.  Verifier-facing packets,
context, campaign packages, and compiled Run Specs are checked for hidden
variant/outcome leakage before the preflight can be accepted.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from aiverify.bench.state_evolution import (
    StateEvolutionContractError,
    load_state_evolution_context,
    load_state_evolution_contract,
    verify_change_target_diff,
)
from aiverify.discovery import (
    AttemptEvidence,
    BehaviorDelta,
    ChangeTarget,
    ContextExpansionRequest,
    ContextExpansionResult,
    ContractDrift,
    DiscoveryCampaignPackage,
    DiscoveryContractError,
    ProjectTarget,
    admit_campaign_plan,
    apply_context_expansion,
    compile_attack_plan_to_run_spec,
    create_campaign,
    freeze_campaign_hypothesis,
    make_historical_state_replay_operator,
    make_state_evolution_operator,
    make_state_evolution_prior,
    make_state_evolution_strategy,
    reduce_attempt_evidence,
    seed_project_campaign,
)
from aiverify.runner.run_spec import ScenarioSpec, SystemEventSpec

_SCHEMA_PATH = Path(__file__).with_name("m8_qualification_schema.json")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_FROZEN_SOURCE_COMMIT = "1dd4b080f61437d8019958ea01954deb025f36c7"
CELL_IDS = (
    "change-defect",
    "change-control",
    "project-defect",
    "project-control",
)
_MODES = frozenset({"change", "project"})
_VARIANTS = frozenset({"defect", "control"})
_HIDDEN_VALUE_TERMS = (
    "defect",
    "control",
    "variant",
    "verdict",
    "locally_supported",
    "locally_rejected",
    "inconclusive",
    "non_accountable",
    "journey",
)
_EXPECTED_LABEL = re.compile(r"expected(?:[_ -](?:outcome|evidence|oracle|verdict))")


class M8QualificationError(ValueError):
    """Raised when a frozen M8 manifest or preflight is invalid."""

    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(dict.fromkeys(str(error) for error in errors))
        detail = "\n".join(f"- {error}" for error in self.errors)
        super().__init__(f"M8 qualification is invalid:\n{detail}")


@dataclass(frozen=True)
class M8QualificationManifest:
    """The exact manifest bytes and canonical identity consumed by #122."""

    source_path: Path
    source_sha256: str
    canonical_sha256: str
    document: Mapping[str, Any]

    @property
    def qualification_id(self) -> str:
        return str(self.document["qualification_id"])

    @property
    def cells(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.document["cells"])

    @property
    def lanes(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.document["lanes"])


@dataclass(frozen=True)
class M8VerificationPacket:
    """Neutral verifier input; no cell variant or expected result is present."""

    packet_id: str
    lane_id: str
    target_mode: str
    target_id: str
    source_origin: str
    source_commit: str
    worktree: str
    scope: tuple[str, ...]
    context_manifest_ref: str
    context_manifest_sha256: str
    diff_ref: str | None
    diff_sha256: str | None
    scenario_id: str
    discovery_budget: int

    def __post_init__(self) -> None:
        for field in (
            "packet_id",
            "lane_id",
            "target_id",
            "source_origin",
            "source_commit",
            "worktree",
            "context_manifest_ref",
            "scenario_id",
        ):
            _required_text(getattr(self, field), field)
        if self.target_mode not in _MODES:
            raise M8QualificationError(("packet target_mode is invalid",))
        _required_text(self.context_manifest_sha256, "context_manifest_sha256")
        if not _SHA256.fullmatch(self.context_manifest_sha256):
            raise M8QualificationError(
                ("context_manifest_sha256 is not a SHA-256 digest",)
            )
        if not self.scope or any(
            not isinstance(item, str) or not item.strip() for item in self.scope
        ):
            raise M8QualificationError(("packet scope must be non-empty",))
        if self.target_mode == "change":
            if (
                not self.diff_ref
                or not self.diff_sha256
                or not _SHA256.fullmatch(self.diff_sha256)
            ):
                raise M8QualificationError(("change packet requires diff identity",))
        elif self.diff_ref is not None or self.diff_sha256 is not None:
            raise M8QualificationError(("project packet must not carry a diff",))
        if (
            not isinstance(self.discovery_budget, int)
            or isinstance(self.discovery_budget, bool)
            or self.discovery_budget < 1
        ):
            raise M8QualificationError(("packet discovery_budget must be positive",))
        leakage = _leakage_terms(self.to_dict())
        if leakage:
            raise M8QualificationError(
                ("verifier packet leaks hidden fields: " + ", ".join(leakage),)
            )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": 1,
            "packet_id": self.packet_id,
            "lane_id": self.lane_id,
            "target_mode": self.target_mode,
            "target_id": self.target_id,
            "source_origin": self.source_origin,
            "source_commit": self.source_commit,
            "worktree": self.worktree,
            "scope": list(self.scope),
            "context_manifest_ref": self.context_manifest_ref,
            "context_manifest_sha256": self.context_manifest_sha256,
            "scenario_id": self.scenario_id,
            "discovery_budget": self.discovery_budget,
        }
        if self.diff_ref is not None:
            result["diff_ref"] = self.diff_ref
            result["diff_sha256"] = self.diff_sha256
        return result


@dataclass(frozen=True)
class M8QualificationPreflight:
    """Deterministic admission receipt with no formal device side effects."""

    manifest: M8QualificationManifest
    admitted: bool
    side_effects: bool
    formal_execution_started: bool
    checks: tuple[Mapping[str, Any], ...]
    lanes: tuple[Mapping[str, Any], ...]
    leakage_audit: Mapping[str, Any]
    contradiction_audit: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "qualification_id": self.manifest.qualification_id,
            "manifest_sha256": self.manifest.source_sha256,
            "canonical_manifest_sha256": self.manifest.canonical_sha256,
            "admitted": self.admitted,
            "side_effects": self.side_effects,
            "formal_execution_started": self.formal_execution_started,
            "checks": [dict(item) for item in self.checks],
            "lanes": [dict(item) for item in self.lanes],
            "leakage_audit": dict(self.leakage_audit),
            "contradiction_audit": dict(self.contradiction_audit),
            "claim_boundary": dict(self.manifest.document["claim_boundary"]),
        }


def load_schema() -> dict[str, Any]:
    """Load the strict M8 manifest schema."""

    try:
        data = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M8QualificationError(
            (f"manifest schema cannot be read: {error}",)
        ) from error
    if not isinstance(data, dict):
        raise M8QualificationError(("manifest schema root must be an object",))
    return data


def self_validate_schema() -> None:
    """Validate the schema itself before using it as an admission gate."""

    Draft202012Validator.check_schema(load_schema())


def load_manifest(path: str | Path) -> M8QualificationManifest:
    """Load a frozen, ordered, checksum-bound M8 manifest fail-closed."""

    source_path = Path(path).resolve()
    try:
        raw = source_path.read_bytes()
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        M8QualificationError,
    ) as error:
        raise M8QualificationError((f"manifest cannot be read: {error}",)) from error
    if not isinstance(document, dict):
        raise M8QualificationError(("manifest root must be an object",))
    schema = load_schema()
    try:
        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
                document
            ),
            key=lambda error: (
                tuple(str(item) for item in error.absolute_path),
                error.message,
            ),
        )
    except (
        M8QualificationError,
        DiscoveryContractError,
        StateEvolutionContractError,
        ValueError,
        OSError,
        TypeError,
        KeyError,
        AttributeError,
    ) as error:
        raise M8QualificationError((f"manifest schema is invalid: {error}",)) from error
    if errors:
        raise M8QualificationError(
            tuple(_render_schema_error(error) for error in errors)
        )
    semantic_errors = _manifest_errors(document)
    if semantic_errors:
        raise M8QualificationError(semantic_errors)
    canonical = _canonical_bytes(document)
    return M8QualificationManifest(
        source_path=source_path,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        canonical_sha256=hashlib.sha256(canonical).hexdigest(),
        document=document,
    )


def audit_packet(packet: M8VerificationPacket) -> dict[str, Any]:
    """Audit one packet for hidden variant/outcome values."""

    leakage = _leakage_terms(packet.to_dict())
    return {
        "packet_id": packet.packet_id,
        "status": "pass" if not leakage else "fail",
        "forbidden_terms": leakage,
        "variant_withheld": True,
        "expected_evidence_withheld": True,
        "oracle_conclusion_withheld": True,
        "verdict_withheld": True,
    }


def admit_qualification(
    manifest_path: str | Path,
    *,
    repo_root: str | Path | None = None,
) -> M8QualificationPreflight:
    """Run the complete side-effect-free M8 admission/preflight.

    This is the authoritative hand-off to #122.  It verifies source identity,
    runs both target modes through Context Expansion → hypothesis freeze → plan
    admission → neutral Run Spec compilation, performs the leakage audit, and
    exercises contradiction gates.  No command runner, build, device, or
    external project is touched.
    """

    manifest = load_manifest(manifest_path)
    root = (
        Path(repo_root).resolve()
        if repo_root is not None
        else manifest.source_path.parents[2]
    )
    checks: list[Mapping[str, Any]] = []
    failures: list[str] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append(
            {"name": name, "status": "pass" if passed else "fail", "detail": detail}
        )
        if not passed:
            failures.append(name)

    source = manifest.document["source_identity"]
    source_identity_ok, source_identity_detail = _verify_source_identity(source, root)
    check("source_identity", source_identity_ok, source_identity_detail)
    for artifact in source["artifacts"]:
        path = root / str(artifact["path"])
        actual = _sha256_file(path) if path.is_file() else None
        check(
            f"sha256:{artifact['path']}",
            actual == artifact["sha256"],
            f"expected={artifact['sha256']} actual={actual}",
        )
    change_input = source["change_input"]
    diff_path = root / str(change_input["path"])
    check(
        "change_target_diff_provenance",
        _sha256_file(diff_path) == change_input["sha256"]
        and verify_change_target_diff(
            ChangeTarget(
                target_id="m8-preflight-change",
                source_origin=source["source_origin"],
                source_commit=source["source_commit"],
                worktree=source["worktree"],
                diff_ref=str(diff_path),
                diff_sha256=change_input["sha256"],
            ),
            repo_root=root,
        ).valid,
        "ChangeTarget diff is bound to the frozen patch",
    )

    contract_path = root / str(manifest.document["fixture"]["contract"]["path"])
    context_path = root / str(manifest.document["fixture"]["context"]["path"])
    try:
        contract = load_state_evolution_contract(contract_path)
        check("fixture_contract", True, contract.contract_id)
    except (
        M8QualificationError,
        DiscoveryContractError,
        StateEvolutionContractError,
        ValueError,
        OSError,
        TypeError,
        KeyError,
        AttributeError,
    ) as error:
        contract = None
        check("fixture_contract", False, str(error))
    check(
        "fixture_contract_identity",
        contract is not None
        and contract.contract_id == manifest.document["fixture"]["contract_id"],
        "contract id",
    )
    build = manifest.document["build"]
    check(
        "fixture_pair_identity",
        contract is not None
        and contract.fixture_pair_id == manifest.document["fixture"]["pair_id"],
        "matched-pair identity is bound to the public contract",
    )
    try:
        protocol = json.loads(
            (root / str(manifest.document["fixture"]["protocol"]["path"])).read_text(
                encoding="utf-8"
            )
        )
        recipe = json.loads(
            (
                root / str(manifest.document["fixture"]["build_recipe"]["path"])
            ).read_text(encoding="utf-8")
        )
        metadata = json.loads(
            (
                root / "bench/discovery-fixtures/state-evolution/build-metadata.json"
            ).read_text(encoding="utf-8")
        )
        check(
            "protocol_identity",
            isinstance(protocol, Mapping)
            and protocol.get("package") == build["package"]
            and protocol.get("activity") == build["activity"]
            and tuple(protocol.get("events", ()))
            == ("rotate", "process_death", "backup_restore"),
            "protocol package/activity/events",
        )
        check(
            "build_recipe_identity",
            isinstance(recipe, Mapping)
            and recipe.get("host_project") == build["host_project"]
            and recipe.get("gradle_wrapper") == build["gradle_wrapper"]
            and tuple(recipe.get("gradle_tasks", ()))
            == tuple(manifest.document["build"]["gradle_tasks"])
            and recipe.get("apk_relative_path") == build["apk_relative_path"]
            and recipe.get("package") == build["package"]
            and recipe.get("activity") == build["activity"],
            "build recipe/package/activity",
        )
        check(
            "build_metadata_identity",
            isinstance(metadata, Mapping)
            and metadata.get("package") == build["package"]
            and metadata.get("activity") == build["activity"],
            "build metadata package/activity",
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        AttributeError,
    ) as error:
        check("protocol_identity", False, str(error))
        check("build_recipe_identity", False, str(error))
        check("build_metadata_identity", False, str(error))
    mapping = manifest.document["auditor_mapping"]["artifact"]
    check(
        "auditor_mapping_checksum",
        _sha256_file(root / str(mapping["path"])) == mapping["sha256"],
        "mapping bytes are bound but not interpreted",
    )

    strategy = make_state_evolution_strategy(
        prior=make_state_evolution_prior(),
        operator=make_historical_state_replay_operator(),
    )
    packets: list[M8VerificationPacket] = []
    lane_receipts: list[Mapping[str, Any]] = []
    leakage_checks: list[Mapping[str, Any]] = []
    campaign_packages: list[DiscoveryCampaignPackage] = []

    for lane in manifest.lanes:
        mode = str(lane["target_mode"])
        lane_id = str(lane["lane_id"])
        target_id = str(lane["target_id"])
        packet = M8VerificationPacket(
            packet_id=str(lane["packet_id"]),
            lane_id=lane_id,
            target_mode=mode,
            target_id=target_id,
            source_origin=str(source["source_origin"]),
            source_commit=str(source["source_commit"]),
            worktree=str(source["worktree"]),
            scope=tuple(manifest.document["target_profiles"][mode]["scope"]),
            context_manifest_ref=str(manifest.document["fixture"]["context"]["path"]),
            context_manifest_sha256=str(
                manifest.document["fixture"]["context"]["sha256"]
            ),
            diff_ref=str(change_input["path"]) if mode == "change" else None,
            diff_sha256=str(change_input["sha256"]) if mode == "change" else None,
            scenario_id=str(lane["scenario_id"]),
            discovery_budget=int(manifest.document["policy"]["discovery_budget"]),
        )
        packets.append(packet)
        leakage_checks.append(audit_packet(packet))
        try:
            receipt, package = _admit_lane(
                manifest=manifest,
                lane=lane,
                root=root,
                context_path=context_path,
                diff_path=diff_path,
                strategy=strategy,
                contract=contract,
            )
            lane_receipts.append(receipt)
            campaign_packages.append(package)
            check(
                f"lane:{lane_id}:admitted", True, "plan-admitted and Run Spec compiled"
            )
        except (
            M8QualificationError,
            DiscoveryContractError,
            StateEvolutionContractError,
            ValueError,
            OSError,
            TypeError,
            KeyError,
            AttributeError,
        ) as error:
            check(f"lane:{lane_id}:admitted", False, str(error))

    leakage_failures = [item for item in leakage_checks if item["status"] != "pass"]
    check(
        "leakage_audit",
        not leakage_failures
        and _audit_preexecution_artifacts(
            packets=packets,
            packages=campaign_packages,
            lane_receipts=lane_receipts,
            context_path=context_path,
        ),
        f"{len(leakage_checks) - len(leakage_failures)}/{len(leakage_checks)} packets pass",
    )
    check(
        "ordered_population",
        tuple(item["lane_id"] for item in lane_receipts)
        == tuple(item["lane_id"] for item in manifest.lanes),
        "lane order remains manifest order",
    )
    reduction = _evidence_reduction_check(
        campaign_packages[0] if campaign_packages else None
    )
    check(
        "attempt_evidence_reduction",
        reduction["status"] == "pass",
        "accountable terminal evidence creates Finding; non-accountable evidence creates Residual Risk",
    )
    contradiction_audit = _contradiction_audit(
        manifest, root, context_path, diff_path, strategy
    )
    check(
        "contradiction_preflight",
        contradiction_audit["status"] == "pass",
        f"{contradiction_audit['passed']}/{contradiction_audit['total']} fail-closed checks",
    )
    admitted = (
        not failures
        and not leakage_failures
        and all(item["status"] == "pass" for item in checks)
    )
    return M8QualificationPreflight(
        manifest=manifest,
        admitted=admitted,
        side_effects=False,
        formal_execution_started=False,
        checks=tuple(checks),
        lanes=tuple(lane_receipts),
        leakage_audit={
            "status": "pass"
            if not leakage_failures and checks[-3]["status"] == "pass"
            else "fail",
            "packet_count": len(leakage_checks),
            "checks": leakage_checks,
            "pre_execution_artifacts": [
                "context",
                "selection_ledger",
                "hypothesis",
                "failure_chain",
                "attack_plan",
                "run_spec",
            ],
            "mapping_released": False,
        },
        contradiction_audit=contradiction_audit,
    )


def run_preflight(
    manifest_path: str | Path,
    *,
    repo_root: str | Path | None = None,
) -> M8QualificationPreflight:
    """Descriptive alias for :func:`admit_qualification`."""

    return admit_qualification(manifest_path, repo_root=repo_root)


def _admit_lane(
    *,
    manifest: M8QualificationManifest,
    lane: Mapping[str, Any],
    root: Path,
    context_path: Path,
    diff_path: Path,
    strategy: Any,
    contract: Any,
) -> tuple[dict[str, Any], DiscoveryCampaignPackage]:
    mode = str(lane["target_mode"])
    target_id = str(lane["target_id"])
    profile = manifest.document["target_profiles"][mode]
    source = manifest.document["source_identity"]
    target: ChangeTarget | ProjectTarget
    if mode == "change":
        target = ChangeTarget(
            target_id=target_id,
            source_origin=str(source["source_origin"]),
            source_commit=str(source["source_commit"]),
            worktree=str(source["worktree"]),
            diff_ref=str(diff_path),
            diff_sha256=str(source["change_input"]["sha256"]),
        )
    else:
        target = ProjectTarget(
            target_id=target_id,
            source_origin=str(source["source_origin"]),
            source_commit=str(source["source_commit"]),
            worktree=str(source["worktree"]),
            scope=tuple(profile["scope"]),
            discovery_budget=int(manifest.document["policy"]["discovery_budget"]),
        )
    graph = load_state_evolution_context(
        context_path,
        target,
        contract_path=root / str(manifest.document["fixture"]["contract"]["path"]),
        repo_root=root,
    ).graph
    request = ContextExpansionRequest(
        request_id=f"request-{lane['lane_id']}",
        campaign_id=str(lane["campaign_id"]),
        target_id=target_id,
        required_predicates=(
            "writes_legacy_state",
            "stores_durable_state",
            "schema_version",
            "migrates_to_schema",
            "reads_current_state",
            "crosses_recovery_boundary",
            "quality_contract",
        ),
        probe_refs=("probe:state-runtime-identity",),
        budget=int(manifest.document["policy"]["context_expansion_budget"]),
        unresolved_questions=(
            "runtime process, APK, and transport identity remain unknown before execution",
        ),
    )
    created = create_campaign(
        str(lane["campaign_id"]), target, graph, expansion_request=request
    )
    expanded = apply_context_expansion(
        created,
        ContextExpansionResult(
            request_id=request.request_id,
            target_id=target_id,
            graph=graph,
            resolved_fact_ids=tuple(
                fact.fact_id for fact in graph.facts if fact.status == "known"
            ),
            unresolved_questions=request.unresolved_questions,
            probe_refs=request.probe_refs,
            budget_used=0,
            status="partial",
        ),
    )
    if mode == "change":
        delta, drift = _change_inputs(target)
        frozen = freeze_campaign_hypothesis(
            expanded,
            behavior_delta=delta,
            contract_drift=drift,
            prior=make_state_evolution_prior(),
            operator=make_historical_state_replay_operator(),
            strategy=strategy,
        )
    else:
        frozen = freeze_campaign_hypothesis(
            expanded,
            prior=make_state_evolution_prior(),
            operator=make_historical_state_replay_operator(),
            strategy=strategy,
        )
    admission = admit_campaign_plan(frozen)
    if not admission.admission.admitted:
        raise M8QualificationError(
            (
                "attack plan admission rejected: "
                + "; ".join(admission.admission.errors),
            )
        )
    admitted = admission.package
    scenario = ScenarioSpec(
        id=str(lane["scenario_id"]),
        user_actions=[
            "Launch the bounded state fixture and observe the recorded state boundary.",
            "Record state identity, migration, and recovery observations without classification.",
        ],
        system_events=[
            SystemEventSpec(step_index=index, event=event)
            for index, event in enumerate(("rotate", "process_death", "backup_restore"))
        ],
        l2_boundary_index=2,
    )
    compiled = compile_attack_plan_to_run_spec(
        admitted,
        host_project=root / str(manifest.document["build"]["host_project"]),
        apk_glob="app/build/outputs/**/*.apk",
        package_name=str(manifest.document["build"]["package"]),
        activity=str(manifest.document["build"]["activity"]),
        scenario=scenario,
        diff=diff_path if mode == "change" else None,
    )
    run_spec = _run_spec_dict(compiled.run_spec, root=root)
    hypothesis = admitted.campaign.hypotheses[0]
    chain = admitted.campaign.failure_chains[0]
    plan = admitted.campaign.attack_plans[0]
    if plan.status != "admitted" or hypothesis.status != "frozen":
        raise M8QualificationError(("campaign did not reach frozen/admitted state",))
    expected = {
        "hypothesis_id": hypothesis.hypothesis_id,
        "failure_chain_id": chain.chain_id,
        "plan_id": plan.plan_id,
        "experiment_ref": compiled.experiment_ref,
        "input_digest": compiled.input_digest,
        "campaign_status": compiled.package.campaign.status,
        "run_spec": run_spec,
    }
    for key in (
        "hypothesis_id",
        "failure_chain_id",
        "plan_id",
        "experiment_ref",
        "scenario_id",
    ):
        if key == "scenario_id":
            actual = str(lane["scenario_id"])
        else:
            actual = expected[key]
        if str(lane[key]) != actual:
            raise M8QualificationError(
                (f"lane {lane['lane_id']} {key} identity differs from manifest",)
            )
    package_sha = _canonical_sha256(compiled.package.to_dict())
    receipt = {
        "lane_id": str(lane["lane_id"]),
        "packet_id": str(lane["packet_id"]),
        "target_mode": mode,
        "target_id": target_id,
        "campaign_id": str(lane["campaign_id"]),
        "context_status": "partial",
        "hypothesis_status": hypothesis.status,
        "hypothesis_id": hypothesis.hypothesis_id,
        "failure_chain_id": chain.chain_id,
        "plan_status": plan.status,
        "plan_id": plan.plan_id,
        "experiment_ref": compiled.experiment_ref,
        "input_digest": compiled.input_digest,
        "campaign_status_after_compile": compiled.package.campaign.status,
        "behavior_delta_bound": compiled.package.behavior_delta is not None,
        "contract_drift_bound": bool(compiled.package.campaign.contract_drifts),
        "project_diff_absent": compiled.package.campaign.target.kind == "project"
        and compiled.package.behavior_delta is None
        and not compiled.package.campaign.contract_drifts,
        "run_spec": run_spec,
        "package_sha256": package_sha,
        "formal_execution_started": False,
    }
    return receipt, compiled.package


def _change_inputs(target: ChangeTarget) -> tuple[BehaviorDelta, ContractDrift]:
    drift_id = "drift-state-continuity-" + _short_digest(target.target_id)
    return (
        BehaviorDelta(
            delta_id="delta-state-transition-" + _short_digest(target.target_id),
            target_id=target.target_id,
            subject="StateStoreV2.migrate",
            before="historical state follows the recorded transition",
            after="the changed transition may alter compatibility across recovery",
            source_fact_ids=("fact-schema-migration",),
            confidence=0.84,
            contract_drift_id=drift_id,
            rationale="Bounded ChangeTarget input records the changed state transition without an execution outcome.",
        ),
        ContractDrift(
            drift_id=drift_id,
            contract_id="durable-state-continuity-v1",
            before="historical state remains compatible across recovery",
            after="the transition may alter compatibility across recovery",
            delta="state transition compatibility changed",
            source_fact_ids=("fact-quality-contract",),
            rationale="Separate contract drift keeps ChangeTarget semantics explicit.",
        ),
    )


def _audit_preexecution_artifacts(
    *,
    packets: list[M8VerificationPacket],
    packages: list[DiscoveryCampaignPackage],
    lane_receipts: list[Mapping[str, Any]],
    context_path: Path,
) -> bool:
    if len(packets) != len(packages) or len(packages) != len(lane_receipts):
        return False
    try:
        context = json.loads(context_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    values: list[Any] = [context]
    for packet, package, receipt in zip(packets, packages, lane_receipts):
        values.extend((packet.to_dict(), package.to_dict(), receipt["run_spec"]))
        values.extend(
            (
                package.campaign.context_graph.to_dict(),
                package.selection_ledger.to_dict(),
                package.campaign.hypotheses[0].to_dict(),
                package.campaign.failure_chains[0].to_dict(),
                package.campaign.attack_plans[0].to_dict(),
            )
        )
    return not any(_leakage_terms(value) for value in values)


def _evidence_reduction_check(
    package: DiscoveryCampaignPackage | None,
) -> dict[str, Any]:
    """Exercise the immutable AttemptEvidence accountability boundary.

    The receipts are synthetic preflight probes, not formal observations.  The
    check exists so the frozen manifest's reduction rule is verified before a
    device lane can begin.
    """

    if package is None or not package.campaign.hypotheses:
        return {"status": "fail", "finding": False, "residual_risk": False}
    hypothesis = package.campaign.hypotheses[0]
    non_accountable = AttemptEvidence(
        evidence_id="preflight-non-accountable",
        target_id=package.campaign.target.target_id,
        hypothesis_id=hypothesis.hypothesis_id,
        attempt_ref="preflight-attempt-1",
        execution_record_ref="preflight/execution-record-missing.json",
        outcome="non_accountable",
        evidence_refs=(),
        claim_boundary="preflight contract probe only",
        rationale="Synthetic receipt omits terminal execution identity.",
        accountable=False,
    )
    residual_package, residual = reduce_attempt_evidence(package, non_accountable)
    accountable = AttemptEvidence(
        evidence_id="preflight-accountable",
        target_id=package.campaign.target.target_id,
        hypothesis_id=hypothesis.hypothesis_id,
        attempt_ref="preflight-attempt-2",
        execution_record_ref="preflight/execution-record-complete.json",
        outcome="inconclusive",
        evidence_refs=("preflight/evidence/state.json",),
        claim_boundary="preflight contract probe only",
        rationale="Synthetic terminal receipt exercises the accountable reducer path.",
        accountable=True,
        execution_identity_sha256="0" * 64,
    )
    finding_package, finding = reduce_attempt_evidence(residual_package, accountable)
    try:
        reduce_attempt_evidence(
            finding_package,
            AttemptEvidence(
                evidence_id="preflight-accountable-retry",
                target_id=package.campaign.target.target_id,
                hypothesis_id=hypothesis.hypothesis_id,
                attempt_ref="preflight-attempt-3",
                execution_record_ref="preflight/execution-record-retry.json",
                outcome="inconclusive",
                evidence_refs=("preflight/evidence/retry.json",),
                claim_boundary="preflight contract probe only",
                rationale="Synthetic retry must be rejected after accountability.",
                accountable=True,
                execution_identity_sha256="0" * 64,
            ),
        )
    except DiscoveryContractError:
        retry_rejected = True
    else:
        retry_rejected = False
    return {
        "status": "pass"
        if residual.residual_risk is not None
        and residual.finding is None
        and finding.finding is not None
        and finding.residual_risk is None
        and len(finding_package.attempts) == 2
        and retry_rejected
        else "fail",
        "finding": finding.finding is not None,
        "residual_risk": residual.residual_risk is not None,
        "retry_rejected": retry_rejected,
        "synthetic": True,
    }


def _contradiction_audit(
    manifest: M8QualificationManifest,
    root: Path,
    context_path: Path,
    diff_path: Path,
    strategy: Any,
) -> dict[str, Any]:
    """Exercise representative identity/contract gates before any side effect."""

    checks: list[dict[str, Any]] = []

    def rejected(name: str, operation: Any) -> None:
        try:
            operation()
        except (
            M8QualificationError,
            DiscoveryContractError,
            StateEvolutionContractError,
            ValueError,
            OSError,
            TypeError,
            KeyError,
            AttributeError,
        ) as error:
            checks.append(
                {
                    "name": name,
                    "status": "pass",
                    "side_effects": False,
                    "reason": str(error),
                }
            )
        else:
            checks.append(
                {
                    "name": name,
                    "status": "fail",
                    "side_effects": False,
                    "reason": "contradiction was accepted",
                }
            )

    source = manifest.document["source_identity"]
    rejected(
        "source_identity",
        lambda: _assert_source_identity(
            root,
            {
                **source,
                "source_commit": "0" * 40,
            },
        ),
    )
    target = ProjectTarget(
        target_id="m8-contradictory-target",
        source_origin=str(source["source_origin"]),
        source_commit=str(source["source_commit"]),
        worktree=str(source["worktree"]),
        scope=("state-evolution",),
        discovery_budget=int(manifest.document["policy"]["discovery_budget"]),
    )
    graph = load_state_evolution_context(
        context_path,
        target,
        contract_path=root / str(manifest.document["fixture"]["contract"]["path"]),
    ).graph
    rejected(
        "target_context_identity",
        lambda: create_campaign(
            "m8-contradictory-campaign",
            target,
            graph,
            expansion_request=ContextExpansionRequest(
                request_id="wrong-request",
                campaign_id="different-campaign",
                target_id=target.target_id,
                required_predicates=("quality_contract",),
                probe_refs=(),
                budget=1,
            ),
        ),
    )
    rejected(
        "prior_operator_identity",
        lambda: seed_project_campaign(
            "m8-contradictory-strategy",
            target,
            graph,
            prior=make_state_evolution_prior(),
            operator=make_state_evolution_operator("wrong-operator"),
            strategy=strategy,
        ),
    )
    rejected(
        "run_spec_identity",
        lambda: compile_attack_plan_to_run_spec(
            create_campaign("not-admitted", target, graph),
            host_project=root,
            apk_glob="**/*.apk",
            package_name="",
            activity="MainActivity",
            scenario=ScenarioSpec(id="m8-contradiction"),
        ),
    )
    rejected(
        "fixture_state_input",
        lambda: load_state_evolution_contract(
            root / str(manifest.document["fixture"]["contract"]["path"])
        ).migration.__class__(
            edge_id="bad",
            from_schema=2,
            to_schema=2,
            from_revision=42,
            to_revision=41,
            operation="bad",
        ),
    )
    for name, mutation in (
        (
            "retry_policy",
            lambda doc: doc["policy"].__setitem__("max_attempts_per_lane", 2),
        ),
        (
            "evidence_policy",
            lambda doc: doc["evidence"].__setitem__("checksums_required", False),
        ),
        (
            "adjudication_policy",
            lambda doc: doc["adjudication"].__setitem__("independent", False),
        ),
        (
            "claim_boundary",
            lambda doc: doc["claim_boundary"].__setitem__("local_only", False),
        ),
        (
            "change_target_profile",
            lambda doc: doc["target_profiles"]["change"].__setitem__(
                "requires_behavior_delta", False
            ),
        ),
    ):
        rejected(
            name,
            lambda mutation=mutation: _mutated_manifest_rejected(manifest, mutation),
        )
    passed = sum(item["status"] == "pass" for item in checks)
    return {
        "status": "pass" if passed == len(checks) else "fail",
        "total": len(checks),
        "passed": passed,
        "checks": checks,
        "side_effects": False,
        "formal_denominator": False,
        "route": "exclude_before_formal_invocation",
    }


def _mutated_manifest_rejected(
    manifest: M8QualificationManifest, mutation: Any
) -> None:
    import copy

    doc = copy.deepcopy(manifest.document)
    mutation(doc)
    errors = _manifest_errors(doc)
    if errors:
        raise M8QualificationError(
            ("mutation rejected before formal side effects: " + "; ".join(errors),)
        )


def _assert_artifact_sha(path: Path, expected: str) -> None:
    if _sha256_file(path) != expected:
        raise M8QualificationError((f"artifact checksum mismatch: {path}",))


def _verify_source_identity(source: Mapping[str, Any], root: Path) -> tuple[bool, str]:
    try:
        _assert_source_identity(root, source)
    except (M8QualificationError, OSError, subprocess.SubprocessError) as error:
        return False, str(error)
    return (
        True,
        "frozen source commit exists, is an ancestor of HEAD, and binds the declared worktree",
    )


def _assert_source_identity(root: Path, source: Mapping[str, Any]) -> None:
    source_commit = source.get("source_commit")
    worktree = source.get("worktree")
    if not isinstance(source_commit, str) or not _GIT_COMMIT.fullmatch(source_commit):
        raise M8QualificationError(("source_commit must be a 40-character git commit",))
    if source_commit != _FROZEN_SOURCE_COMMIT:
        raise M8QualificationError(
            (f"source_commit must remain {_FROZEN_SOURCE_COMMIT}",)
        )
    if not isinstance(worktree, str) or not worktree.strip():
        raise M8QualificationError(("source worktree must be non-empty",))
    declared = (
        (root / worktree).resolve()
        if not Path(worktree).is_absolute()
        else Path(worktree).resolve()
    )
    if declared != root.resolve():
        raise M8QualificationError(
            (
                f"source worktree {declared} is not the preflight repository root {root.resolve()}",
            )
        )
    try:
        top_level = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
        subprocess.check_call(
            ["git", "-C", str(root), "cat-file", "-e", f"{source_commit}^{{commit}}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        subprocess.check_call(
            [
                "git",
                "-C",
                str(root),
                "merge-base",
                "--is-ancestor",
                source_commit,
                "HEAD",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise M8QualificationError(
            (
                f"source commit {source_commit} is not an available ancestor of HEAD: {error}",
            )
        ) from error
    if Path(top_level).resolve() != root.resolve():
        raise M8QualificationError(
            (
                f"git repository root {top_level} does not match preflight root {root.resolve()}",
            )
        )


def _run_spec_dict(run_spec: Any, *, root: Path) -> dict[str, Any]:
    host = _relative_or_posix(Path(run_spec.host_project), root)
    diff = _relative_or_posix(Path(run_spec.diff), root) if run_spec.diff else None
    scenario = run_spec.scenario
    result: dict[str, Any] = {
        "host_project": host,
        "apk_glob": run_spec.apk_glob,
        "package": run_spec.package,
        "activity": run_spec.activity,
        "diff": diff,
        "scenario": {
            "id": scenario.id,
            "user_actions": list(scenario.user_actions),
            "system_events": [
                {
                    "step_index": event.step_index,
                    "event": event.event,
                    "args": dict(event.args),
                }
                for event in scenario.system_events
            ],
            "assertions": [],
            "l2_boundary_index": scenario.l2_boundary_index,
            "metric_context": {
                "seed_kind": scenario.metric_context.seed_kind,
                "taxonomy_category": None,
                "taxonomy_pattern_id": None,
            },
            "l3_spec": "",
        },
    }
    if result["diff"] is None:
        result.pop("diff")
    return result


def _manifest_errors(document: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if document.get("status") != "frozen":
        errors.append("manifest status must be frozen")
    if document.get("qualification_id") != "m8-state-evolution-qualification-v1":
        errors.append("qualification_id must identify M8 state-evolution v1")
    cells = document.get("cells", [])
    ids = tuple(str(item.get("cell_id")) for item in cells)
    if ids != CELL_IDS:
        errors.append(
            "cells must be exactly change/project defect/control in frozen order"
        )
    if len(set(ids)) != len(ids):
        errors.append("cell ids must be unique")
    expected = {
        "change-defect": ("change", "defect"),
        "change-control": ("change", "control"),
        "project-defect": ("project", "defect"),
        "project-control": ("project", "control"),
    }
    for cell in cells:
        cell_id = str(cell.get("cell_id"))
        if expected.get(cell_id) != (cell.get("target_mode"), cell.get("variant")):
            errors.append(f"cell {cell_id} mode/variant mismatch")
        if cell.get("repetitions") != 3:
            errors.append(f"cell {cell_id} must have three repetitions")
    lanes = document.get("lanes", [])
    if len(lanes) != 12:
        errors.append("manifest must freeze exactly twelve lanes")
    lane_ids = tuple(str(item.get("lane_id")) for item in lanes)
    expected_lanes = tuple(f"lane-{number:02d}" for number in range(1, 13))
    if lane_ids != expected_lanes:
        errors.append("lanes must be ordered lane-01 through lane-12")
    lane_index = 0
    for cell in cells:
        for repetition in range(1, 4):
            if lane_index >= len(lanes):
                break
            lane = lanes[lane_index]
            if (
                lane.get("cell_id") != cell.get("cell_id")
                or lane.get("repetition") != repetition
            ):
                errors.append(f"lane {lane.get('lane_id')} is not ordered membership")
            if lane.get("target_mode") != cell.get("target_mode"):
                errors.append(f"lane {lane.get('lane_id')} mode differs from cell")
            lane_index += 1
    policy = document.get("policy", {})
    if policy.get("planned_lanes") != 12 or policy.get("repetitions_per_cell") != 3:
        errors.append("policy must freeze 12 lanes and three repetitions per cell")
    if policy.get("max_attempts_per_lane") != 1:
        errors.append("policy permits exactly one attempt per lane")
    retry = policy.get("retry", {})
    if (
        retry.get("max_attempts_per_lane") != 1
        or retry.get("no_retry_after_accountable") is not True
        or retry.get("replacement_allowed") is not False
    ):
        errors.append("retry/replacement policy is not frozen to one attempt")
    blinding = policy.get("blinding", {})
    for field in (
        "withhold_variant",
        "withhold_expected_evidence",
        "withhold_expected_oracle",
        "withhold_verdict",
        "network_disabled",
    ):
        if blinding.get(field) is not True:
            errors.append(f"blinding policy must set {field}=true")
    if document.get("environment", {}).get("android_execution") is not False:
        errors.append("#121 preflight must not claim Android execution")
    profiles = document.get("target_profiles", {})
    if profiles.get("change", {}).get("kind") != "ChangeTarget":
        errors.append("change target profile must be ChangeTarget")
    if profiles.get("project", {}).get("kind") != "ProjectTarget":
        errors.append("project target profile must be ProjectTarget")
    if profiles.get("change", {}).get("requires_diff") is not True:
        errors.append("ChangeTarget profile must require a diff")
    for field in ("requires_behavior_delta", "requires_contract_drift"):
        if profiles.get("change", {}).get(field) is not True:
            errors.append(
                f"ChangeTarget profile must require {field.removeprefix('requires_')}"
            )
    if any(
        profiles.get("project", {}).get(field) is not False
        for field in (
            "requires_diff",
            "requires_behavior_delta",
            "requires_contract_drift",
        )
    ):
        errors.append("ProjectTarget profile must not invent diff/delta/drift")
    if document.get("evidence", {}).get("checksums_required") is not True:
        errors.append("evidence policy requires checksums")
    reduction = document.get("evidence", {}).get("reduction_rules", {})
    if reduction.get("accountable_terminal") != "Finding":
        errors.append("accountable terminal evidence must reduce to Finding")
    if reduction.get("non_accountable_terminal") != "Residual Risk":
        errors.append("non-accountable evidence must reduce to Residual Risk")
    if reduction.get("retry_after_accountability") is not False:
        errors.append("evidence reduction must forbid retry after accountability")
    if document.get("adjudication", {}).get("independent") is not True:
        errors.append("adjudication must remain independent")
    claim = document.get("claim_boundary", {})
    if claim.get("local_only") is not True:
        errors.append("claim boundary must remain local-only")
    if (
        any(
            "combined" in str(item).lower() or "rate" in str(item).lower()
            for item in claim.get("exclusions", [])
        )
        is False
    ):
        errors.append("claim boundary must exclude combined/rate claims")
    source = document.get("source_identity", {})
    if source.get("source_commit") != _FROZEN_SOURCE_COMMIT:
        errors.append(f"source_commit must remain {_FROZEN_SOURCE_COMMIT}")
    if source.get("worktree") != ".":
        errors.append("source worktree must be repository root '.'")
    if not isinstance(source.get("context"), Mapping):
        errors.append("source identity must include context artifact")
    for artifact in source.get("artifacts", []):
        if Path(str(artifact.get("path", ""))).is_absolute():
            errors.append("source artifact paths must be repository-relative")
        if not _SHA256.fullmatch(str(artifact.get("sha256", ""))):
            errors.append(f"source artifact {artifact.get('path')} must have SHA-256")
    if source.get("change_input", {}).get("path") not in [
        item.get("path") for item in source.get("artifacts", [])
    ]:
        errors.append("change input must be included in source artifact inventory")
    approved = document.get("maintainer_approval", {})
    if _parse_datetime(approved.get("approved_at")) > _parse_datetime(
        document.get("frozen_at")
    ):
        errors.append("maintainer approval cannot occur after frozen_at")
    mapping = document.get("auditor_mapping", {})
    if mapping.get("release_after") != "hypothesis_freeze_and_plan_admission":
        errors.append("auditor mapping must remain withheld until admission")
    if mapping.get("artifact", {}).get("path") in [
        item.get("path") for item in source.get("artifacts", [])
    ]:
        errors.append("auditor mapping must not be verifier source inventory")
    return sorted(set(errors))


def _parse_datetime(value: Any) -> float:
    import datetime as _datetime

    if not isinstance(value, str):
        return float("inf")
    try:
        parsed = _datetime.datetime.fromisoformat(value)
    except ValueError:
        return float("inf")
    return parsed.timestamp()


def _required_text(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise M8QualificationError((f"{field} must be a non-empty string",))


def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    except OSError:
        return None


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _short_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _relative_or_posix(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _leakage_terms(value: Any) -> tuple[str, ...]:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True).lower()
    found = [term for term in _HIDDEN_VALUE_TERMS if term in text]
    if _EXPECTED_LABEL.search(text):
        found.append("expected-outcome/evidence label")
    return tuple(dict.fromkeys(found))


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise M8QualificationError((f"duplicate manifest key: {key}",))
        result[key] = value
    return result


def _render_schema_error(error: Any) -> str:
    path = ".".join(str(part) for part in error.absolute_path) or "<root>"
    return f"schema {path}: {error.message}"


__all__ = [
    "CELL_IDS",
    "M8QualificationError",
    "M8QualificationManifest",
    "M8QualificationPreflight",
    "M8VerificationPacket",
    "admit_qualification",
    "audit_packet",
    "load_manifest",
    "load_schema",
    "run_preflight",
    "self_validate_schema",
]
