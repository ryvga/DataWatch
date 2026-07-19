import importlib.util
from pathlib import Path

from app.models.monitor import Monitor, MonitorRevision, MonitorRun


def _constraint_names(table):
    return {constraint.name for constraint in table.constraints if constraint.name}


def _index_names(table):
    return {index.name for index in table.indexes}


def test_monitor_persistence_metadata_has_identity_revision_and_run_invariants():
    monitor = Monitor.__table__
    revision = MonitorRevision.__table__
    run = MonitorRun.__table__

    assert _constraint_names(monitor) >= {
        "uq_monitors_org_table_name",
        "ck_monitors_mode",
        "ck_monitors_status",
    }
    assert _index_names(monitor) >= {"ix_monitors_org_status", "ix_monitors_table_id"}

    assert _constraint_names(revision) >= {
        "uq_monitor_revisions_number",
        "ck_monitor_revisions_positive",
    }
    assert "updated_at" not in revision.c
    assert revision.c.definition_hash.type.length == 64
    assert revision.c.definition.nullable is False

    assert _constraint_names(run) >= {
        "uq_monitor_runs_idempotency",
        "ck_monitor_runs_status",
    }
    assert "updated_at" not in run.c
    assert run.c.revision_id.foreign_keys
    assert run.c.idempotency_key.nullable is False


def test_monitor_persistence_migration_is_single_successor_of_current_head():
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "011_monitor_dsl_persistence.py"
    )
    spec = importlib.util.spec_from_file_location("monitor_migration_011", migration_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module.revision == "011"
    assert module.down_revision == "010"
    assert callable(module.upgrade)
    assert callable(module.downgrade)
