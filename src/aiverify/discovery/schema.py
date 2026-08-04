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
    "quality_contract": "qualityContract",
    "contract_drift": "contractDrift",
    "risk_prior": "riskPrior",
    "attack_operator": "attackOperator",
    "failure_chain": "failureChain",
    "risk_hypothesis": "riskHypothesis",
    "attack_plan": "attackPlan",
    "finding": "finding",
    "residual_risk": "residualRisk",
    "project_risk_map": "projectRiskMap",
    "discovery_campaign": "discoveryCampaign",
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
