import importlib.util
from pathlib import Path

from sqlalchemy import BigInteger

from app.models.monitor import Monitor, MonitorEvaluationState, MonitorRevision, MonitorRun
from app.models.table_profile import TableProfile


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
        "uq_monitors_org_id",
        "uq_monitors_id_table",
        "fk_monitors_active_revision_owner",
        "ck_monitors_mode",
        "ck_monitors_status",
        "ck_monitors_active_revision",
    }
    assert _index_names(monitor) >= {"ix_monitors_org_status", "ix_monitors_table_id"}

    assert _constraint_names(revision) >= {
        "uq_monitor_revisions_number",
        "uq_monitor_revisions_monitor_id",
        "ck_monitor_revisions_positive",
    }
    assert "updated_at" not in revision.c
    assert revision.c.definition_hash.type.length == 64
    assert revision.c.definition.nullable is False

    assert _constraint_names(run) >= {
        "uq_monitor_runs_idempotency",
        "uq_monitor_runs_monitor_id",
        "fk_monitor_runs_monitor_owner",
        "fk_monitor_runs_revision_owner",
        "fk_monitor_runs_table_owner",
        "ck_monitor_runs_status",
    }
    assert "updated_at" not in run.c
    assert run.c.revision_id.foreign_keys
    assert run.c.idempotency_key.nullable is False


def test_monitor_runtime_metadata_separates_activation_audit_and_policy_state():
    monitor = Monitor.__table__
    run = MonitorRun.__table__
    state = MonitorEvaluationState.__table__

    assert monitor.c.active_revision_id.nullable is True
    assert monitor.c.active_revision_id.foreign_keys
    assert _constraint_names(run) >= {
        "ck_monitor_runs_trigger_profile",
        "ck_monitor_runs_attempt_positive",
        "ck_monitor_runs_lifecycle",
        "ck_monitor_runs_terminal_result",
        "ck_monitor_runs_error_payload",
    }
    assert _index_names(run) >= {
        "uq_monitor_runs_profile_trigger",
        "uq_monitor_runs_one_running",
    }
    assert run.c.started_at.nullable is True
    for column in (
        "trigger_type",
        "sequence_at",
        "queued_at",
        "plan_hash",
        "planner_version",
        "definition_hash",
        "attempt",
    ):
        assert run.c[column].nullable is False

    assert state.c.monitor_id.primary_key is True
    assert state.c.org_id.nullable is False
    assert _constraint_names(state) >= {
        "fk_monitor_eval_monitor_owner",
        "fk_monitor_eval_revision_owner",
        "fk_monitor_eval_last_run_owner",
        "ck_monitor_eval_phase",
        "ck_monitor_eval_streaks_nonnegative",
        "ck_monitor_eval_version_positive",
    }
    assert "ix_monitor_evaluation_states_org_id" in _index_names(state)
    assert state.c.last_idempotency_key.nullable is True


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


def test_monitor_runtime_migration_is_single_successor_of_persistence_head():
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "012_monitor_runtime_state.py"
    )
    spec = importlib.util.spec_from_file_location("monitor_migration_012", migration_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module.revision == "012"
    assert module.down_revision == "011"
    assert callable(module.upgrade)
    assert callable(module.downgrade)

    source = migration_path.read_text()
    assert "trg_monitor_revisions_append_only" in source
    assert "trg_monitor_runs_terminal_immutable" in source
    assert "pg_trigger_depth() > 1" in source


def test_profile_provenance_metadata_and_migration_follow_runtime_head():
    profile = TableProfile.__table__
    assert isinstance(profile.c.row_count.type, BigInteger)
    assert profile.c.profile_provenance.nullable is True

    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "013_profile_provenance.py"
    )
    spec = importlib.util.spec_from_file_location("profile_provenance_013", migration_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module.revision == "013"
    assert module.down_revision == "012"
    assert "2147483647" in migration_path.read_text()
