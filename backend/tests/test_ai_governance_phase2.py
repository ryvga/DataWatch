import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from app.services.ai_governance import (
    ControlResult,
    evaluate_data_quality,
    evaluate_evidence_age,
    evaluate_sensitivity,
    governance_risk_summary,
)


def _data_use(**overrides):
    values = {
        "id": uuid.uuid4(),
        "fields": ["customer_id", "body"],
        "sensitivity_ceiling": "internal",
        "vector_contract": {"maximum_freshness_seconds": 3600},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_unavailable_stale_and_incomplete_evidence_never_passes():
    use = _data_use()
    now = datetime(2026, 8, 21, 16, tzinfo=UTC)
    stale = SimpleNamespace(
        id=uuid.uuid4(),
        collected_at=now - timedelta(hours=2),
        error=None,
        row_count=10,
        profile_provenance={"mode": "exact"},
    )

    assert evaluate_evidence_age(use, None, maximum_age_seconds=3600, now=now).status == "unknown"
    assert evaluate_evidence_age(use, stale, maximum_age_seconds=3600, now=now).status == "fail"
    assert evaluate_data_quality(use, None).status == "unknown"
    assert evaluate_sensitivity(use, {"customer_id": "internal"}).status == "unknown"
    assert evaluate_sensitivity(
        use, {"customer_id": "restricted", "body": "internal"}
    ).status == "fail"


def test_risk_summary_is_explainable_and_evidence_gaps_raise_the_headline():
    system = SimpleNamespace(
        autonomy_level="semi_autonomous",
        lifecycle_status="production",
        affected_population="support customers",
    )
    use = _data_use(sensitivity_ceiling="confidential")
    results = [
        ControlResult(
            "ownership-assertion",
            "pass",
            "customer_assertion",
            "ownership_complete",
            {"allPresent": True},
            {"allRequired": True},
        ),
        ControlResult(
            "sensitivity-boundary",
            "unknown",
            "customer_assertion",
            "field_classification_incomplete",
            {"missingFields": ["body"]},
            {"ceiling": "confidential"},
            str(use.id),
        ),
    ]
    summary = governance_risk_summary(system, [use], results)
    assert summary["headlineStatus"] == "evidence_gap"
    assert summary["inherentRisk"] == {
        "score": 80,
        "components": {
            "autonomy": 40,
            "production": 20,
            "affectedPopulation": 10,
            "dataSensitivity": 10,
        },
    }
    assert summary["controlCoveragePercent"] == 50.0
    assert summary["evidenceConfidencePercent"] == 50.0
    assert summary["reasons"] == [
        {
            "controlId": "sensitivity-boundary",
            "status": "unknown",
            "reasonCode": "field_classification_incomplete",
        }
    ]


def test_phase_two_migration_and_monitoring_cadence_are_explicit():
    root = Path(__file__).parents[1]
    path = root / "alembic" / "versions" / "015_ai_governance_evidence_ledger.py"
    spec = importlib.util.spec_from_file_location("aigov_migration_015", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "014"
    migration_source = path.read_text()
    assert '"ai_evidence"' in migration_source
    assert "ai_evidence_append_only" in migration_source
    assert "fk_ai_control_evaluations_evidence_owner" in migration_source

    task_source = (root / "app" / "tasks.py").read_text()
    profile_section = task_source[task_source.index("async def _profile_table_async") :]
    assert "evaluate_ai_governance_for_table.delay(table_id, str(profile.id))" in profile_section
    assert "profile-" in task_source
