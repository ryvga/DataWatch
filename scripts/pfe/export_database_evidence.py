from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
OUTPUT = ROOT / "docs/pfe/database_evidence.json"

sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://datawatch:datawatch@localhost:5433/datawatch")

import app.models  # noqa: E402,F401
from app.database import Base  # noqa: E402


RESPONSIBILITIES = {
    "organizations": "Espaces clients, offre et état d'abonnement",
    "users": "Comptes humains rattachés à une organisation",
    "staff_users": "Comptes séparés du personnel DataWatch",
    "api_keys": "Empreintes des clés d'accès programmatiques",
    "invites": "Invitations temporaires des membres",
    "teams": "Équipes opérationnelles d'une organisation",
    "team_members": "Appartenance et rôle d'un utilisateur dans une équipe",
    "user_notification_prefs": "Préférences individuelles de notification",
    "oncall_schedules": "Créneaux d'astreinte des équipes",
    "data_sources": "Sources de données et configuration chiffrée",
    "monitored_tables": "Tables inscrites au cycle de surveillance",
    "table_profiles": "Instantanés de profilage et provenance",
    "check_results": "Résultats unitaires des contrôles de qualité",
    "incidents": "Anomalies regroupées et cycle de traitement",
    "alert_configs": "Routes Slack, e-mail ou PagerDuty",
    "custom_monitors": "Moniteurs SQL historiques restreints",
    "monitors": "Identité et cycle de vie des moniteurs typés",
    "monitor_revisions": "Révisions immuables des définitions DSL",
    "monitor_runs": "Exécutions idempotentes liées à une révision",
    "monitor_evaluation_states": "État de brèche, reprise et temporisation",
    "ai_systems": "Registre des systèmes IA et responsabilités",
    "ai_system_versions": "Versions immuables des systèmes IA",
    "ai_data_use_revisions": "Déclarations versionnées des usages de données",
    "ai_release_manifests": "Manifestes de mise en production adressés par contenu",
    "ai_deployments": "Déploiements et manifeste actif",
    "ai_approvals": "Avis humains append-only sur un manifeste",
    "ai_evidence": "Descripteurs de preuves immuables et sans données brutes",
    "ai_control_evaluations": "Résultats typés des contrôles de gouvernance",
    "ai_governance_incidents": "Incidents de gouvernance dédupliqués en observation",
}


def psql_json(sql: str):
    command = [
        "docker", "compose", "exec", "-T", "postgres",
        "psql", "-U", "datawatch", "-d", "datawatch", "-Atc", sql,
    ]
    result = subprocess.run(command, cwd=ROOT, check=True, text=True, capture_output=True)
    value = result.stdout.strip()
    return json.loads(value) if value else None


def column_record(column):
    foreign_keys = sorted(f"{fk.column.table.name}.{fk.column.name}" for fk in column.foreign_keys)
    return {
        "name": column.name,
        "type": str(column.type),
        "primary_key": bool(column.primary_key),
        "nullable": bool(column.nullable),
        "foreign_keys": foreign_keys,
    }


def build_schema():
    tables = []
    for table in sorted(Base.metadata.tables.values(), key=lambda item: item.name):
        tables.append({
            "name": table.name,
            "responsibility": RESPONSIBILITIES[table.name],
            "columns": [column_record(column) for column in table.columns],
            "unique_constraints": sorted(
                sorted(column.name for column in constraint.columns)
                for constraint in table.constraints
                if constraint.__class__.__name__ == "UniqueConstraint"
            ),
        })
    assert len(tables) == 29, f"Expected 29 application tables, found {len(tables)}"
    assert {table["name"] for table in tables} == set(RESPONSIBILITIES)
    return tables


def fetch_counts(table_names):
    pieces = [
        f"SELECT '{name}' AS table_name, count(*)::int AS row_count FROM {name}"
        for name in table_names
    ]
    union = " UNION ALL ".join(pieces)
    return psql_json(
        "SELECT jsonb_object_agg(table_name, row_count) FROM (" + union + ") counts;"
    )


def fetch_samples():
    return {
        "organizations": psql_json(
            "SELECT coalesce(jsonb_agg(jsonb_build_object('name',name,'slug',slug,'plan',plan,'subscription_status',subscription_status) ORDER BY slug),'[]'::jsonb) FROM organizations;"
        ),
        "acme_users": psql_json(
            "SELECT coalesce(jsonb_agg(jsonb_build_object('full_name',u.full_name,'role',u.role,'is_active',u.is_active) ORDER BY u.full_name),'[]'::jsonb) FROM users u JOIN organizations o ON o.id=u.org_id WHERE o.slug='acme-corp';"
        ),
        "acme_teams": psql_json(
            "SELECT coalesce(jsonb_agg(jsonb_build_object('name',t.name,'description',t.description) ORDER BY t.name),'[]'::jsonb) FROM teams t JOIN organizations o ON o.id=t.org_id WHERE o.slug='acme-corp';"
        ),
        "acme_sources": psql_json(
            "SELECT coalesce(jsonb_agg(jsonb_build_object('name',s.name,'type',s.type,'status',s.status) ORDER BY s.name),'[]'::jsonb) FROM data_sources s JOIN organizations o ON o.id=s.org_id WHERE o.slug='acme-corp';"
        ),
        "acme_tables": psql_json(
            "SELECT coalesce(jsonb_agg(jsonb_build_object('schema',m.schema_name,'table',m.table_name,'interval_minutes',m.check_interval_minutes,'sensitivity',m.sensitivity,'active',m.is_active) ORDER BY m.table_name),'[]'::jsonb) FROM monitored_tables m JOIN data_sources s ON s.id=m.source_id JOIN organizations o ON o.id=s.org_id WHERE o.slug='acme-corp';"
        ),
        "acme_incidents": psql_json(
            "SELECT coalesce(jsonb_agg(jsonb_build_object('severity',i.severity,'status',i.status,'title',i.title) ORDER BY i.severity,i.title),'[]'::jsonb) FROM incidents i JOIN organizations o ON o.id=i.org_id WHERE o.slug='acme-corp';"
        ),
        "acme_ai_systems": psql_json(
            "SELECT coalesce(jsonb_agg(jsonb_build_object('name',a.name,'lifecycle_status',a.lifecycle_status,'autonomy_level',a.autonomy_level) ORDER BY a.name),'[]'::jsonb) FROM ai_systems a JOIN organizations o ON o.id=a.org_id WHERE o.slug='acme-corp';"
        ),
    }


def main():
    schema = build_schema()
    table_names = [table["name"] for table in schema]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": "PostgreSQL 16",
        "application_table_count": len(schema),
        "migration_table_excluded": "alembic_version",
        "tables": schema,
        "seeded_row_counts": fetch_counts(table_names),
        "non_sensitive_seed_samples": fetch_samples(),
        "redaction_policy": [
            "password_hash",
            "key_hash",
            "tokens",
            "connection_config",
            "llm_api_key_encrypted",
            "raw prompts, outputs, rows and embeddings",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {OUTPUT} with {len(schema)} tables")


if __name__ == "__main__":
    main()
