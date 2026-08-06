"""Schema loading and fail-closed validation for discovery contracts."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any, Mapping

from jsonschema import Draft202012Validator, ValidationError

from aiverify.discovery.models import DiscoveryContractError


_SCHEMA_RESOURCE = "discovery_schema.json"
_CONTRACT_DEFINITIONS = {
    "target": "target",
    "discovery_target": "target",
    "change_target": "changeTarget",
    "project_target": "projectTarget",
    "context_fact": "contextFact",
    "context_graph": "contextGraph",
    "context_acquisition_request": "contextAcquisitionRequest",
    "context_acquisition_adapter": "contextAcquisitionAdapter",
    "context_acquisition_receipt": "contextAcquisitionReceipt",
    "context_acquisition_result": "contextAcquisitionResult",
    "quality_contract": "qualityContract",
    "contract_drift": "contractDrift",
    "behavior_delta": "behaviorDelta",
    "risk_priority": "riskPriority",
    "risk_prior": "riskPrior",
    "risk_derivation_strategy": "riskDerivationStrategy",
    "attack_operator": "attackOperator",
    "failure_chain": "failureChain",
    "risk_hypothesis": "riskHypothesis",
    "hypothesis_generator_identity": "hypothesisGeneratorIdentity",
    "hypothesis_generation_request": "hypothesisGenerationRequest",
    "hypothesis_candidate": "hypothesisCandidate",
    "candidate_rejection": "candidateRejection",
    "hypothesis_generation_response": "hypothesisGenerationResponse",
    "hypothesis_portfolio_item": "hypothesisPortfolioItem",
    "hypothesis_portfolio": "hypothesisPortfolio",
    "planner_identity": "plannerIdentity",
    "validated_evidence_ref": "validatedEvidenceRef",
    "plan_element": "planElement",
    "oracle_contract": "oracleContract",
    "attack_plan_proposal": "attackPlanProposal",
    "attack_plan_generation_request": "attackPlanGenerationRequest",
    "attack_plan_admission": "attackPlanAdmission",
    "attack_plan_generation_result": "attackPlanGenerationResult",
    "immutable_artifact_ref": "immutableArtifactRef",
    "falsification_reviewer_identity": "falsificationReviewerIdentity",
    "review_reason": "reviewReason",
    "review_dimension": "reviewDimension",
    "falsification_review_context": "falsificationReviewContext",
    "falsification_review": "falsificationReview",
    "falsification_review_result": "falsificationReviewResult",
    "falsification_reconciliation": "falsificationReconciliation",
    "attack_plan": "attackPlan",
    "finding": "finding",
    "residual_risk": "residualRisk",
    "project_risk_map": "projectRiskMap",
    "discovery_campaign": "discoveryCampaign",
    "context_expansion_request": "contextExpansionRequest",
    "context_expansion_result": "contextExpansionResult",
    "hypothesis_selection_entry": "hypothesisSelectionEntry",
    "hypothesis_selection_ledger": "hypothesisSelectionLedger",
    "attempt_evidence": "attemptEvidence",
    "discovery_campaign_package": "discoveryCampaignPackage",
    "exploration_event": "explorationEvent",
    "exploration_stop": "explorationStop",
    "next_probe": "nextProbe",
    "exploration_campaign": "explorationCampaign",
    "admission_result": "admissionResult",
}


def load_schema() -> dict[str, Any]:
    """Load the checked-in v1 schema rather than constructing it at runtime."""

    resource = resources.files("aiverify.discovery").joinpath(_SCHEMA_RESOURCE)
    return json.loads(resource.read_text(encoding="utf-8"))


def self_validate_schema() -> None:
    """Validate the schema itself, failing before any document is trusted."""

    try:
        Draft202012Validator.check_schema(load_schema())
    except Exception as error:  # jsonschema exposes several schema error types
        raise DiscoveryContractError(f"discovery schema is invalid: {error}") from error


def validate_contract(document: Mapping[str, Any], contract: str) -> None:
    """Validate one serialized contract against its named versioned definition."""

    if not isinstance(document, Mapping):
        raise DiscoveryContractError("contract document must be an object")
    try:
        definition = _CONTRACT_DEFINITIONS[contract]
    except KeyError as error:
        raise DiscoveryContractError(f"unknown discovery contract: {contract}") from error
    schema = load_schema()
    self_validate_schema()
    fragment = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": f"#/$defs/{definition}",
    }
    try:
        Draft202012Validator(fragment).validate(dict(document))
    except ValidationError as error:
        path = ".".join(str(part) for part in error.absolute_path)
        location = f" at {path}" if path else ""
        raise DiscoveryContractError(
            f"invalid {contract} contract{location}: {error.message}"
        ) from error


def validate_discovery_document(document: Mapping[str, Any], contract: str) -> None:
    """Descriptive alias for callers validating JSON documents at the boundary."""

    validate_contract(document, contract)
