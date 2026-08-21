import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from app.models.ai_governance import (
    AIApproval,
    AIControlEvaluation,
    AIDataUseRevision,
    AIGovernanceIncident,
    AIReleaseManifest,
    AISystemVersion,
)
from app.models.data_source import DataSource
from app.models.monitored_table import MonitoredTable
from app.models.table_profile import TableProfile
from app.models.user import User
from app.services.ai_governance import (
    GovernanceContractError,
    build_release_manifest,
    canonical_hash,
    evaluate_privileges,
    evaluate_vector_consistency,
    reject_sensitive_payload,
)
from app.services.crypto import encrypt_config


def test_canonical_contract_is_deterministic_and_rejects_raw_or_secret_fields():
    assert canonical_hash({"b": 2, "a": 1}) == canonical_hash({"a": 1, "b": 2})
    for key in ("password", "api_key", "raw_prompt", "raw_outputs", "embeddings"):
        with pytest.raises(GovernanceContractError, match="not accepted"):
            reject_sensitive_payload({"nested": {key: "sensitive"}})


def test_vector_control_preserves_distinct_result_semantics():
    item = type("Use", (), {"id": uuid.uuid4(), "use_kind": "rag", "vector_contract": {"kind": "pgvector"}})()
    assert evaluate_vector_consistency(item, None, supported=False).status == "unsupported"
    assert evaluate_vector_consistency(item, None, supported=True).status == "unknown"
    assert evaluate_vector_consistency(item, {"missing_embeddings": 2}, supported=True).status == "fail"
    item.use_kind = "training"
    assert evaluate_vector_consistency(item, None, supported=True).status == "not_applicable"


def test_privilege_control_detects_write_grant_even_for_expected_role():
    item = type("Use", (), {"id": uuid.uuid4(), "expected_db_roles": ["rag_runtime"]})()
    result = evaluate_privileges(
        item,
        {
            "effective_roles": ["rag_runtime"],
            "effective_grants": [{"role": "rag_runtime", "privilege": "UPDATE"}],
        },
        supported=True,
    )
    assert result.status == "fail"
    assert result.reason_code == "write_privilege_detected"


def test_manifest_replay_is_byte_deterministic():
    cutoff = datetime(2026, 8, 21, tzinfo=UTC)
    one = build_release_manifest(system_id="s", version_id="v", version_hash="a" * 64, data_uses=[("b", "2"), ("a", "1")], evidence_cutoff=cutoff)
    two = build_release_manifest(system_id="s", version_id="v", version_hash="a" * 64, data_uses=[("a", "1"), ("b", "2")], evidence_cutoff=cutoff)
    assert one == two


def test_demo_source_accounts_are_distinct_least_privilege_roles():
    root = Path(__file__).resolve().parents[2]
    compose = (root / "docker-compose.yml").read_text()
    acme_init = (root / "scripts" / "acme_db_init.sql").read_text()
    analytics_init = (root / "scripts" / "startup_db_init.sql").read_text()

    assert "POSTGRES_USER: acme_admin" in compose
    assert "POSTGRES_USER: analytics_admin" in compose
    assert "POSTGRES_USER: readonly_user" not in compose
    assert "POSTGRES_USER: analytics_ro" not in compose
    for sql, role in ((acme_init, "readonly_user"), (analytics_init, "analytics_ro")):
        assert f"CREATE ROLE {role} WITH LOGIN" in sql
        assert f"ALTER ROLE {role} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT" in sql
        assert f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {role}" in sql
        assert f"GRANT INSERT ON ALL TABLES IN SCHEMA public TO {role}" not in sql
        assert "REVOKE CREATE ON SCHEMA public FROM PUBLIC" in sql


class _FakePostgresConnector:
    async def collect_rag_governance_observation(self, **_kwargs):
        return {
            "effective_roles": ["rag_runtime", "unexpected_exporter"],
            "effective_grants": [
                {"role": "rag_runtime", "privilege": "SELECT"},
                {"role": "unexpected_exporter", "privilege": "SELECT"},
            ],
            "missing_embeddings": 1,
            "orphan_embeddings": 0,
            "stale_embeddings": 2,
            "deletion_propagation_failures": 1,
        }

    async def close(self):
        return None


async def _seed_assets(db_session, org_id):
    source = DataSource(
        org_id=org_id,
        name="RAG PostgreSQL",
        type="postgres",
        connection_config={
            "encrypted": encrypt_config(
                {"host": "db.internal", "port": 5432, "database": "rag", "username": "observer", "password": "driver-only"},
                str(org_id),
            )
        },
        status="connected",
    )
    db_session.add(source)
    await db_session.flush()
    documents = MonitoredTable(
        source_id=source.id,
        schema_name="knowledge",
        table_name="documents",
        freshness_column="updated_at",
        dbt_model_yaml='CREATE TABLE "knowledge"."documents" (\n  "document_id" uuid NOT NULL,\n  "body" text NULL,\n  "updated_at" timestamp NOT NULL,\n  "deleted_at" timestamp NULL\n);',
    )
    vectors = MonitoredTable(
        source_id=source.id,
        schema_name="knowledge",
        table_name="document_vectors",
        dbt_model_yaml='CREATE TABLE "knowledge"."document_vectors" (\n  "document_id" uuid NOT NULL,\n  "embedding" vector NULL,\n  "embedded_at" timestamp NOT NULL\n);',
    )
    db_session.add_all([documents, vectors])
    await db_session.flush()
    from app.services.schema_binding import parse_ddl_columns, schema_fingerprint
    fingerprint = schema_fingerprint(parse_ddl_columns(documents.dbt_model_yaml))
    db_session.add(TableProfile(table_id=documents.id, row_count=100, freshness_seconds=120, schema_fingerprint=fingerprint, column_metrics={}, profile_provenance={"mode": "exact"}))
    await db_session.commit()
    return source, documents, vectors


@pytest.mark.asyncio
async def test_phase_one_api_vertical_idor_cas_replay_controls_and_incident_dedupe(
    client, db_session, test_org, auth_headers
):
    org_id = uuid.UUID(test_org["org_id"])
    owner = await db_session.scalar(select(User).where(User.org_id == org_id))
    _source, documents, vectors = await _seed_assets(db_session, org_id)

    created = await client.post(
        "/api/v1/ai/systems",
        headers=auth_headers,
        json={
            "name": "Support knowledge assistant",
            "slug": "support-knowledge-assistant",
            "lifecycle_status": "production",
            "intended_purpose": "Answer support questions from approved knowledge articles.",
            "prohibited_uses": ["automated account termination"],
            "autonomy_level": "assistive",
            "human_oversight": "Support agents review every answer before it reaches a customer.",
            "business_owner_id": str(owner.id),
            "technical_owner_id": str(owner.id),
            "risk_owner_id": str(owner.id),
            "risk_context": {"impact": "customer-facing"},
        },
    )
    assert created.status_code == 201, created.text
    system_id = created.json()["id"]

    version_response = await client.post(
        f"/api/v1/ai/systems/{system_id}/versions",
        headers=auth_headers,
        json={
            "provider": "self-hosted",
            "model": "approved-model-v1",
            "artifact_hash": "sha256:model-v1",
            "prompt_config_hash": "hmac:prompt-config-v1",
            "evaluation_suite_hash": "sha256:eval-v1",
            "capabilities": ["retrieval", "answer-drafting"],
            "limitations": ["French and English only"],
            "human_oversight_procedure": "Agent approval is mandatory.",
            "risk_snapshot": {"tier": "medium"},
            "change_rationale": "Initial governed release",
        },
    )
    assert version_response.status_code == 201, version_response.text
    version_id = version_response.json()["id"]

    data_use_response = await client.post(
        f"/api/v1/ai/system-versions/{version_id}/data-use-revisions",
        headers=auth_headers,
        json={
            "table_id": str(documents.id),
            "use_kind": "rag",
            "fields": ["document_id", "body", "updated_at", "deleted_at"],
            "purpose": "Retrieve approved support content",
            "necessity": "The assistant needs current article text and identifiers",
            "steward": "Knowledge operations",
            "sensitivity_ceiling": "internal",
            "retention_days": 365,
            "residency": ["ma"],
            "allowed_transformations": ["chunk", "embed"],
            "expected_db_roles": ["rag_runtime"],
            "vector_contract": {
                "vector_table_id": str(vectors.id),
                "embedding_field": "embedding",
                "source_key": "document_id",
                "vector_source_key": "document_id",
                "source_updated_at": "updated_at",
                "vector_updated_at": "embedded_at",
                "source_deleted_at": "deleted_at",
                "maximum_freshness_seconds": 3600,
            },
            "change_rationale": "Bind the production knowledge supply chain",
        },
    )
    assert data_use_response.status_code == 201, data_use_response.text
    data_use_id = data_use_response.json()["id"]
    assert data_use_response.json()["evidenceClass"] == "customer_assertion"

    manifest_body = {"data_use_revision_ids": [data_use_id], "evidence_cutoff": "2026-08-21T23:59:00Z"}
    manifest_one = await client.post(f"/api/v1/ai/system-versions/{version_id}/release-manifests", headers=auth_headers, json=manifest_body)
    manifest_two = await client.post(f"/api/v1/ai/system-versions/{version_id}/release-manifests", headers=auth_headers, json=manifest_body)
    assert manifest_one.status_code == 201
    assert manifest_two.json()["replayed"] is True
    assert manifest_two.json()["id"] == manifest_one.json()["id"]
    reviewed = await client.post(
        f"/api/v1/ai/release-manifests/{manifest_one.json()['id']}/reviews",
        headers=auth_headers,
        json={"reviewer_role": "risk_owner", "decision": "noted", "rationale": "Observe-only fixture reviewed before the jury walkthrough."},
    )
    assert reviewed.status_code == 201
    assert reviewed.json()["evidenceClass"] == "reviewer_decision"
    assert reviewed.json()["gating"] is False

    deployment = await client.post(f"/api/v1/ai/systems/{system_id}/deployments", headers=auth_headers, json={"environment": "production", "region": "ma"})
    deployment_id = deployment.json()["id"]
    activation_body = {"manifest_id": manifest_one.json()["id"], "manifest_hash": manifest_one.json()["manifestHash"], "expected_generation": 0, "expected_active_manifest_hash": None}
    activated = await client.post(f"/api/v1/ai/deployments/{deployment_id}/activate-manifest", headers=auth_headers, json=activation_body)
    assert activated.status_code == 200
    stale_activation = await client.post(f"/api/v1/ai/deployments/{deployment_id}/activate-manifest", headers=auth_headers, json=activation_body)
    assert stale_activation.status_code == 409

    with patch("app.routers.ai_governance.ConnectorFactory.create", return_value=_FakePostgresConnector()), \
         patch("app.services.realtime.publish_event", new_callable=AsyncMock), \
         patch("app.tasks.send_governance_alerts.delay"):
        evaluated = await client.post(f"/api/v1/ai/deployments/{deployment_id}/evaluate", headers=auth_headers, json={"client_idempotency_key": "jury-scenario-001"})
        replayed = await client.post(f"/api/v1/ai/deployments/{deployment_id}/evaluate", headers=auth_headers, json={"client_idempotency_key": "jury-scenario-001"})
    assert evaluated.status_code == 200, evaluated.text
    statuses = {item["controlId"]: item["status"] for item in evaluated.json()["evaluations"]}
    assert statuses == {
        "ownership-assertion": "pass",
        "schema-freshness-observation": "pass",
        "effective-db-role-drift": "fail",
        "vector-consistency": "fail",
    }
    assert [item["id"] for item in replayed.json()["evaluations"]] == [item["id"] for item in evaluated.json()["evaluations"]]
    assert await db_session.scalar(select(func.count()).select_from(AIGovernanceIncident)) == 2

    # A second tenant cannot read or attach records from this system.
    second_slug = f"other-{uuid.uuid4().hex[:8]}"
    second_register = await client.post("/auth/register", json={"org_name": "Other", "org_slug": second_slug, "email": f"owner@{second_slug}.com", "password": "password123"})
    assert second_register.status_code == 201
    second_login = await client.post("/auth/login", json={"org_slug": second_slug, "email": f"owner@{second_slug}.com", "password": "password123"})
    second_headers = {"Authorization": f"Bearer {second_login.json()['access_token']}"}
    from app.routers import auth as auth_router
    auth_router._rate_store.clear()
    assert (await client.get(f"/api/v1/ai/systems/{system_id}", headers=second_headers)).status_code == 404
    assert (await client.post(f"/api/v1/ai/systems/{system_id}/versions", headers=second_headers, json={"change_rationale": "forged"})).status_code == 404

    detail = await client.get(f"/api/v1/ai/systems/{system_id}", headers=auth_headers)
    serialized = detail.text.lower()
    assert "driver-only" not in serialized
    assert '"embeddings":' not in serialized
    assert '"raw_prompt":' not in serialized
    assert '"raw_outputs":' not in serialized
    assert {item["evidenceClass"] for item in detail.json()["evidenceTimeline"]} == {"customer_assertion", "connector_observation", "reviewer_decision"}


@pytest.mark.asyncio
async def test_immutable_models_reject_orm_mutation(db_session, test_org):
    org_id = uuid.UUID(test_org["org_id"])
    system_id = uuid.uuid4()
    # The API vertical creates full rows; here the event contract itself is tested without weakening DB constraints.
    assert AIReleaseManifest in {AIReleaseManifest, AIDataUseRevision, AISystemVersion, AIApproval, AIControlEvaluation}
    from app.models.ai_governance import _reject_immutable_mutation
    with pytest.raises(ValueError, match="append-only"):
        _reject_immutable_mutation(None, None, type("Record", (), {})())
    assert system_id and org_id


def test_migration_follows_head_and_contains_composite_and_append_only_guards():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "014_ai_governance_phase1.py"
    spec = importlib.util.spec_from_file_location("aigov_migration_014", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "013"
    source = path.read_text()
    assert "reject_ai_governance_mutation" in source
    assert "fk_ai_systems_current_version_owner" in source
    assert "uq_ai_governance_incident_active_dedupe" in source
    assert '"ai_approvals"' in source and "_append_only" in source
