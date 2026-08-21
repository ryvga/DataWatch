"""Deterministic phase-one AI governance contracts and evaluators."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

EVALUATOR_VERSION = "aigov-phase1/1.0.0"
MANIFEST_SCHEMA_VERSION = "datawatch.io/aigov-manifest/v1"
TERMINAL_STATUSES = {"pass", "fail", "unknown", "unsupported", "not_applicable", "error"}

_FORBIDDEN_KEY = re.compile(
    r"(^|_)(password|secret|api_?key|access_?token|refresh_?token|prompt|prompts|output|outputs|embedding|embeddings|raw_?(row|rows|prompt|prompts|output|outputs|embedding|embeddings))($|_)",
    re.IGNORECASE,
)


class GovernanceContractError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def reject_sensitive_payload(value: Any, path: str = "payload") -> None:
    """Reject fields that could turn governance metadata into a raw-data store."""
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            safe_metadata_suffix = key_text.lower().endswith(("hash", "field", "field_id"))
            if _FORBIDDEN_KEY.search(key_text) and not safe_metadata_suffix:
                raise GovernanceContractError(
                    "sensitive_payload_forbidden",
                    f"{path}.{key_text} is not accepted; store only hashes and bounded metadata",
                )
            reject_sensitive_payload(child, f"{path}.{key_text}")
    elif isinstance(value, list):
        if len(value) > 250:
            raise GovernanceContractError("payload_too_large", f"{path} exceeds 250 entries")
        for index, child in enumerate(value):
            reject_sensitive_payload(child, f"{path}[{index}]")
    elif isinstance(value, str) and len(value) > 10_000:
        raise GovernanceContractError("payload_too_large", f"{path} exceeds 10,000 characters")


def canonical_json(value: Any) -> str:
    reject_sensitive_payload(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def build_version_definition(payload: dict) -> tuple[dict, str]:
    allowed = {
        "provider": payload.get("provider"),
        "model": payload.get("model"),
        "artifactHash": payload.get("artifact_hash"),
        "promptConfigHash": payload.get("prompt_config_hash"),
        "evaluationSuiteHash": payload.get("evaluation_suite_hash"),
        "capabilities": sorted(set(payload.get("capabilities") or [])),
        "limitations": payload.get("limitations") or [],
        "fallback": payload.get("fallback"),
        "humanOversightProcedure": payload.get("human_oversight_procedure"),
        "riskSnapshot": payload.get("risk_snapshot") or {},
    }
    return allowed, canonical_hash(allowed)


def build_data_use_definition(payload: dict, *, schema_fingerprint: str) -> tuple[dict, str]:
    fields = sorted(set(payload["fields"]))
    definition = {
        "useKind": payload["use_kind"],
        "assetId": str(payload["table_id"]),
        "fields": fields,
        "purpose": payload["purpose"],
        "necessity": payload["necessity"],
        "steward": payload["steward"],
        "sensitivityCeiling": payload["sensitivity_ceiling"],
        "retentionDays": payload.get("retention_days"),
        "residency": sorted(set(payload.get("residency") or [])),
        "allowedTransformations": sorted(set(payload.get("allowed_transformations") or [])),
        "expectedDbRoles": sorted(set(payload.get("expected_db_roles") or [])),
        "vectorContract": payload.get("vector_contract"),
        "schemaFingerprint": schema_fingerprint,
        "evidenceClass": "customer_assertion",
    }
    return definition, canonical_hash(definition)


def build_release_manifest(
    *,
    system_id: str,
    version_id: str,
    version_hash: str,
    data_uses: list[tuple[str, str]],
    evidence_cutoff: datetime,
) -> tuple[dict, str]:
    manifest = {
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "systemId": system_id,
        "version": {"id": version_id, "definitionHash": version_hash},
        "dataUses": [
            {"id": item_id, "definitionHash": item_hash}
            for item_id, item_hash in sorted(data_uses)
        ],
        "policyRevisions": [],
        "evaluationSuites": [],
        "evidenceCutoff": evidence_cutoff.astimezone(UTC).isoformat(),
        "normalization": "rfc8785-compatible-sorted-json-v1",
        "hashAlgorithm": "sha256",
        "mode": "observe",
    }
    return manifest, canonical_hash(manifest)


@dataclass(frozen=True)
class ControlResult:
    control_id: str
    status: str
    evidence_class: str
    reason_code: str
    observed: dict
    expected: dict
    data_use_revision_id: str | None = None

    def __post_init__(self) -> None:
        if self.status not in TERMINAL_STATUSES:
            raise ValueError(f"Invalid control status: {self.status}")
        reject_sensitive_payload(self.observed, "observed")
        reject_sensitive_payload(self.expected, "expected")

    @property
    def input_hash(self) -> str:
        return canonical_hash(
            {
                "controlId": self.control_id,
                "observed": self.observed,
                "expected": self.expected,
                "evaluatorVersion": EVALUATOR_VERSION,
            }
        )


def evaluate_ownership(system) -> ControlResult:
    present = {
        "businessOwner": bool(system.business_owner_id),
        "technicalOwner": bool(system.technical_owner_id),
        "riskOwner": bool(system.risk_owner_id),
        "humanOversight": bool(system.human_oversight.strip()),
    }
    passed = all(present.values())
    return ControlResult(
        control_id="ownership-assertion",
        status="pass" if passed else "fail",
        evidence_class="customer_assertion",
        reason_code="ownership_complete" if passed else "ownership_incomplete",
        observed=present,
        expected={"allRequired": True},
    )


def evaluate_schema_freshness(data_use, profile, *, maximum_age_seconds: int) -> ControlResult:
    if profile is None:
        return ControlResult(
            control_id="schema-freshness-observation",
            status="unknown",
            evidence_class="connector_observation",
            reason_code="profile_missing",
            observed={"profileAvailable": False},
            expected={"schemaFingerprint": data_use.schema_fingerprint, "maximumAgeSeconds": maximum_age_seconds},
            data_use_revision_id=str(data_use.id),
        )
    schema_matches = profile.schema_fingerprint == data_use.schema_fingerprint
    freshness_known = profile.freshness_seconds is not None
    fresh = freshness_known and profile.freshness_seconds <= maximum_age_seconds
    return ControlResult(
        control_id="schema-freshness-observation",
        status="pass" if schema_matches and fresh else "fail",
        evidence_class="connector_observation",
        reason_code=(
            "schema_and_freshness_match"
            if schema_matches and fresh
            else "schema_drift" if not schema_matches else "source_stale"
        ),
        observed={
            "profileId": str(profile.id),
            "schemaFingerprint": profile.schema_fingerprint,
            "freshnessSeconds": profile.freshness_seconds,
            "collectedAt": profile.collected_at.isoformat(),
        },
        expected={"schemaFingerprint": data_use.schema_fingerprint, "maximumAgeSeconds": maximum_age_seconds},
        data_use_revision_id=str(data_use.id),
    )


def evaluate_privileges(data_use, observation: dict | None, *, supported: bool) -> ControlResult:
    expected_roles = sorted(set(data_use.expected_db_roles or []))
    observed: dict[str, Any]
    if not supported:
        status, reason, observed = "unsupported", "connector_privilege_observation_unsupported", {}
    elif observation is None:
        status, reason, observed = "unknown", "connector_observation_missing", {}
    else:
        roles = sorted(set(observation.get("effective_roles") or []))
        unexpected = sorted(set(roles) - set(expected_roles))
        grants = sorted(
            observation.get("effective_grants") or [],
            key=lambda item: (str(item.get("role")), str(item.get("privilege"))),
        )
        unsafe_grants = [
            item for item in grants
            if str(item.get("privilege", "")).upper() != "SELECT"
        ]
        status = "fail" if unexpected or unsafe_grants else "pass"
        reason = (
            "unexpected_effective_role" if unexpected
            else "write_privilege_detected" if unsafe_grants
            else "effective_roles_and_grants_match"
        )
        observed = {
            "effectiveRoles": roles,
            "unexpectedRoles": unexpected,
            "effectiveGrants": grants,
            "unsafeGrants": unsafe_grants,
        }
    return ControlResult(
        control_id="effective-db-role-drift",
        status=status,
        evidence_class="connector_observation",
        reason_code=reason,
        observed=observed,
        expected={"allowedRoles": expected_roles, "allowedPrivileges": ["SELECT"]},
        data_use_revision_id=str(data_use.id),
    )


def evaluate_vector_consistency(data_use, observation: dict | None, *, supported: bool) -> ControlResult:
    if data_use.use_kind != "rag" or not data_use.vector_contract:
        return ControlResult(
            control_id="vector-consistency",
            status="not_applicable",
            evidence_class="connector_observation",
            reason_code="not_rag_vector_use",
            observed={},
            expected={},
            data_use_revision_id=str(data_use.id),
        )
    observed: dict[str, Any]
    if not supported:
        status, reason, observed = "unsupported", "connector_vector_observation_unsupported", {}
    elif observation is None:
        status, reason, observed = "unknown", "connector_observation_missing", {}
    else:
        observed = {
            "missingEmbeddings": int(observation.get("missing_embeddings") or 0),
            "orphanEmbeddings": int(observation.get("orphan_embeddings") or 0),
            "staleEmbeddings": int(observation.get("stale_embeddings") or 0),
            "deletionPropagationFailures": int(observation.get("deletion_propagation_failures") or 0),
        }
        status = "pass" if not any(observed.values()) else "fail"
        reason = "vector_consistent" if status == "pass" else "vector_consistency_violation"
    return ControlResult(
        control_id="vector-consistency",
        status=status,
        evidence_class="connector_observation",
        reason_code=reason,
        observed=observed,
        expected={
            "missingEmbeddings": 0,
            "orphanEmbeddings": 0,
            "staleEmbeddings": 0,
            "deletionPropagationFailures": 0,
        },
        data_use_revision_id=str(data_use.id),
    )
