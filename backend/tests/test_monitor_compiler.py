from copy import deepcopy

import pytest
from pydantic import ValidationError
from sqlglot import exp, parse_one

from app.services.monitor_compiler import (
    PLANNER_VERSION,
    MonitorPlanError,
    compile_relational_plan,
)
from app.services.monitor_dsl import MonitorDefinition, canonical_json
from app.services.schema_binding import build_relation_binding
from tests.test_monitor_dsl import valid_definition


DEFAULT_DDL = """CREATE TABLE analytics.orders (
  id integer NOT NULL,
  status text NULL,
  payment_reference text NULL,
  amount numeric(12, 2) NULL,
  other_amount numeric(12, 2) NULL,
  email text NULL,
  user_id bigint NULL,
  created_at timestamp NULL
);"""


def _relation(
    *,
    source_type="postgres",
    schema_name="analytics",
    table_name="orders",
    ddl=DEFAULT_DDL,
    asset_id=None,
):
    definition = valid_definition()
    return build_relation_binding(
        asset_id=asset_id or MonitorDefinition.model_validate(definition).spec.target.asset_id,
        source_type=source_type,
        schema_name=schema_name,
        table_name=table_name,
        ddl=ddl,
        latest_schema_fingerprint=None,
    )


def _metric_definition(metric: str, field: str | None = None) -> MonitorDefinition:
    definition = valid_definition()
    measurement = {"id": "value", "type": "metric", "metric": metric}
    if field is not None:
        measurement["field"] = field
    definition["spec"]["measurements"] = [measurement]
    definition["spec"]["breachWhen"] = {
        "op": "gt",
        "left": {"ref": "value"},
        "right": {"literal": 0},
    }
    return MonitorDefinition.model_validate(definition)


def test_postgres_plan_quotes_identifiers_and_parameterizes_hostile_literals():
    definition = valid_definition()
    hostile = "paid' OR 1=1 --"
    definition["spec"]["measurements"][0]["violationWhen"]["all"][0]["right"] = {
        "literal": hostile
    }
    model = MonitorDefinition.model_validate(definition)

    payload = compile_relational_plan(
        model,
        relation=_relation(
            schema_name='sales"; DROP SCHEMA public; --',
            table_name='order items"; DELETE FROM users; --',
        ),
    ).payload()

    assert payload["plannerVersion"] == PLANNER_VERSION
    assert hostile not in payload["statement"]
    assert "DROP SCHEMA" in payload["statement"]
    assert '"sales""; DROP SCHEMA public; --"' in payload["statement"]
    assert '"order items""; DELETE FROM users; --"' in payload["statement"]
    assert payload["parameters"] == [
        {"name": "p0", "type": "string", "value": hostile}
    ]
    assert payload["resultContract"]["columns"] == [
        "dw_m0_count",
        "dw_m0_rate",
    ]
    assert [output["reference"] for output in payload["outputs"]] == [
        "invalid_orders.count",
        "invalid_orders.rate",
    ]
    assert len(payload["planHash"]) == 64
    parsed = parse_one(payload["statement"], dialect="postgres")
    assert isinstance(parsed, exp.Select)
    assert len(list(parsed.find_all(exp.Table))) == 1
    assert not list(parsed.find_all(exp.Drop))
    assert not list(parsed.find_all(exp.Delete))


@pytest.mark.parametrize(
    ("source_type", "placeholder", "quoted_table"),
    [
        ("postgres", "%(p0)s", '"analytics"."orders"'),
        ("duckdb", "$p0", '"analytics"."orders"'),
        ("sqlite", ":p0", '"analytics"."orders"'),
    ],
)
def test_relational_compiler_has_deterministic_dialect_snapshots(
    source_type, placeholder, quoted_table
):
    model = MonitorDefinition.model_validate(valid_definition())
    first = compile_relational_plan(
        model,
        relation=_relation(source_type=source_type),
    ).payload()
    second = compile_relational_plan(
        model,
        relation=_relation(source_type=source_type),
    ).payload()

    assert first == second
    assert placeholder in first["statement"]
    assert quoted_table in first["statement"]
    assert first["readOnly"] is True
    assert first["statementMode"] == "preview_only"
    assert first["driverBindingRequired"] is True


def test_nested_violation_sql_snapshots_are_pinned_per_dialect():
    model = MonitorDefinition.model_validate(valid_definition())
    expected = {
        "postgres": 'SELECT COUNT(CASE WHEN "status" = %(p0)s AND "payment_reference" IS NULL THEN 1 END) AS "dw_m0_count", CAST(COUNT(CASE WHEN "status" = %(p0)s AND "payment_reference" IS NULL THEN 1 END) * 1.0 AS DOUBLE PRECISION) / NULLIF(COUNT(*), 0) AS "dw_m0_rate" FROM "analytics"."orders"',
        "duckdb": 'SELECT COUNT(CASE WHEN "status" = $p0 AND "payment_reference" IS NULL THEN 1 END) AS "dw_m0_count", COUNT(CASE WHEN "status" = $p0 AND "payment_reference" IS NULL THEN 1 END) * 1.0 / NULLIF(COUNT(*), 0) AS "dw_m0_rate" FROM "analytics"."orders"',
        "sqlite": 'SELECT COUNT(CASE WHEN "status" = :p0 AND "payment_reference" IS NULL THEN 1 END) AS "dw_m0_count", CAST(COUNT(CASE WHEN "status" = :p0 AND "payment_reference" IS NULL THEN 1 END) * 1.0 AS REAL) / NULLIF(COUNT(*), 0) AS "dw_m0_rate" FROM "analytics"."orders"',
    }
    for source_type, statement in expected.items():
        plan = compile_relational_plan(
            model,
            relation=_relation(source_type=source_type),
        )
        assert plan.statement == statement


def test_portable_metrics_batch_into_one_aggregate_select():
    definition = valid_definition()
    definition["spec"]["measurements"] = [
        {"id": "rows", "type": "metric", "metric": "row_count"},
        {"id": "nulls", "type": "metric", "metric": "null_count", "field": "email"},
        {"id": "null_rate", "type": "metric", "metric": "null_rate", "field": "email"},
        {
            "id": "distinct_users",
            "type": "metric",
            "metric": "distinct_count",
            "field": "user_id",
        },
        {
            "id": "distinct_rate",
            "type": "metric",
            "metric": "distinct_rate",
            "field": "user_id",
        },
    ]
    definition["spec"]["breachWhen"] = {
        "op": "eq",
        "left": {"ref": "rows"},
        "right": {"literal": 0},
    }
    payload = compile_relational_plan(
        MonitorDefinition.model_validate(definition),
        relation=_relation(),
    ).payload()

    parsed = parse_one(payload["statement"], dialect="postgres")
    assert isinstance(parsed, exp.Select)
    assert len(parsed.expressions) == 5
    assert len(list(parsed.find_all(exp.Table))) == 1
    assert payload["parameters"] == []
    assert payload["resultContract"]["columns"] == [
        "dw_m0",
        "dw_m1",
        "dw_m2",
        "dw_m3",
        "dw_m4",
    ]
    assert payload["outputs"][0]["nullable"] is False
    assert all(output["nullable"] for output in payload["outputs"][1:])


def test_quality_metrics_and_filtered_measurements_compile_in_one_plan():
    definition = valid_definition()
    definition["spec"]["measurements"] = [
        {
            "id": "duplicate_emails",
            "type": "metric",
            "metric": "duplicate_count",
            "field": "email",
        },
        {
            "id": "paid_nulls",
            "type": "metric",
            "metric": "null_rate",
            "field": "email",
            "filterWhen": {
                "op": "eq",
                "left": {"field": "status"},
                "right": {"literal": "paid"},
            },
        },
        {
            "id": "negative_amounts",
            "type": "metric",
            "metric": "negative_rate",
            "field": "amount",
        },
        {
            "id": "short_status",
            "type": "metric",
            "metric": "text_length_max",
            "field": "status",
        },
    ]
    definition["spec"]["breachWhen"] = {
        "op": "gt",
        "left": {"ref": "paid_nulls"},
        "right": {"literal": 0.1},
    }
    payload = compile_relational_plan(
        MonitorDefinition.model_validate(definition),
        relation=_relation(),
    ).payload()

    assert 'COUNT("email") - COUNT(DISTINCT "email")' in payload["statement"]
    assert '"status" = %(p0)s' in payload["statement"]
    assert '"amount" < 0' in payload["statement"]
    assert 'MAX(LENGTH("status"))' in payload["statement"]
    assert payload["parameters"] == [{"name": "p0", "type": "string", "value": "paid"}]


@pytest.mark.parametrize(
    ("operator", "expected"),
    [
        ("not_between", 'NOT "amount" BETWEEN %(p0)s AND %(p1)s'),
        ("is_empty", '"status" = \'\''),
        ("is_whitespace", 'TRIM("status") = \'\''),
    ],
)
def test_extended_validation_predicates_compile(operator, expected):
    definition = valid_definition()
    if operator == "not_between":
        predicate = {"op": operator, "left": {"field": "amount"}, "right": {"literal": [1, 10]}}
    else:
        predicate = {"op": operator, "value": {"field": "status"}}
    definition["spec"]["measurements"][0]["violationWhen"] = predicate
    payload = compile_relational_plan(
        MonitorDefinition.model_validate(definition),
        relation=_relation(),
    ).payload()
    assert expected in payload["statement"]


def test_sqlite_rejects_stddev_without_emitting_a_statement():
    definition = _metric_definition("stddev", "amount")
    with pytest.raises(MonitorPlanError, match="not available") as exc:
        compile_relational_plan(
            definition,
            relation=_relation(source_type="sqlite", schema_name="main"),
        )
    assert exc.value.code == "metric_not_supported"


def test_output_aliases_are_short_and_cannot_collide_after_suffixing():
    definition = valid_definition()
    definition["spec"]["measurements"][0]["id"] = "a" * 63
    definition["spec"]["breachWhen"]["left"]["ref"] = f"{'a' * 63}.rate"
    payload = compile_relational_plan(
        MonitorDefinition.model_validate(definition),
        relation=_relation(),
    ).payload()

    assert payload["resultContract"]["columns"] == ["dw_m0_count", "dw_m0_rate"]
    assert payload["outputs"][1]["reference"] == f"{'a' * 63}.rate"


def test_membership_parameters_are_ordered_and_must_be_homogeneous():
    definition = valid_definition()
    definition["spec"]["measurements"][0]["violationWhen"] = {
        "op": "in",
        "left": {"field": "status"},
        "right": {"literal": ["paid", "pending"]},
    }
    payload = compile_relational_plan(
        MonitorDefinition.model_validate(definition),
        relation=_relation(),
    ).payload()
    assert payload["parameters"] == [
        {"name": "p0", "type": "string", "value": "paid"},
        {"name": "p1", "type": "string", "value": "pending"},
    ]

    definition["spec"]["measurements"][0]["violationWhen"]["right"] = {
        "literal": ["paid", 1]
    }
    with pytest.raises(MonitorPlanError, match="homogeneous"):
        compile_relational_plan(
            MonitorDefinition.model_validate(definition),
            relation=_relation(),
        )


@pytest.mark.parametrize(
    "predicate",
    [
        {
            "op": "eq",
            "left": {"field": "amount"},
            "right": {"literal": "not-a-number"},
        },
        {"op": "gt", "left": {"field": "status"}, "right": {"literal": "paid"}},
        {"op": "is_missing", "value": {"field": "status"}},
        {"op": "is_nan", "value": {"field": "amount"}},
        {"op": "eq", "left": {"field": "missing"}, "right": {"literal": 1}},
    ],
)
def test_non_portable_or_untyped_predicates_are_deferred(predicate):
    definition = valid_definition()
    definition["spec"]["measurements"][0]["violationWhen"] = predicate
    with pytest.raises(MonitorPlanError):
        compile_relational_plan(
            MonitorDefinition.model_validate(definition),
            relation=_relation(),
        )


def test_compilation_does_not_mutate_canonical_definition():
    model = MonitorDefinition.model_validate(valid_definition())
    before = canonical_json(model)
    compile_relational_plan(
        model,
        relation=_relation(),
    )
    assert canonical_json(model) == before


def test_non_relational_source_is_explicitly_unsupported():
    definition = _metric_definition("row_count")
    with pytest.raises(MonitorPlanError, match="mongodb") as exc:
        compile_relational_plan(
            definition,
            relation=_relation(source_type="mongodb", schema_name="db"),
        )
    assert exc.value.code == "relational_compiler_not_supported"


@pytest.mark.parametrize(
    "measurement",
    [
        {"id": "rows", "type": "metric", "metric": "row_count", "field": "id"},
        {"id": "nulls", "type": "metric", "metric": "null_count"},
    ],
)
def test_metric_field_contract_is_validated_before_compilation(measurement):
    definition = valid_definition()
    definition["spec"]["measurements"] = [measurement]
    definition["spec"]["breachWhen"] = {
        "op": "eq",
        "left": {"literal": 1},
        "right": {"literal": 1},
    }
    with pytest.raises(ValidationError):
        MonitorDefinition.model_validate(definition)


def test_predicate_literal_shapes_are_validated_before_compilation():
    for op, value in (("between", [1]), ("in", []), ("contains", 1)):
        definition = deepcopy(valid_definition())
        definition["spec"]["measurements"][0]["violationWhen"] = {
            "op": op,
            "left": {"field": "amount"},
            "right": {"literal": value},
        }
        with pytest.raises(ValidationError):
            MonitorDefinition.model_validate(definition)


def test_typed_numeric_string_and_field_comparisons_compile_safely():
    definition = valid_definition()
    definition["spec"]["measurements"][0]["violationWhen"] = {
        "all": [
            {"op": "between", "left": {"field": "amount"}, "right": {"literal": [1, 10]}},
            {"op": "gte", "left": {"field": "amount"}, "right": {"field": "other_amount"}},
            {"op": "contains", "left": {"field": "status"}, "right": {"literal": "50%_off!"}},
            {"op": "is_negative", "value": {"field": "amount"}},
        ]
    }
    payload = compile_relational_plan(
        MonitorDefinition.model_validate(definition),
        relation=_relation(),
    ).payload()

    assert '"amount" BETWEEN %(p0)s AND %(p1)s' in payload["statement"]
    assert '"amount" >= "other_amount"' in payload["statement"]
    assert '"status" LIKE %(p2)s ESCAPE \'!\'' in payload["statement"]
    assert payload["parameters"][2]["value"] == "%50!%!_off!!%"
    assert '"amount" < 0' in payload["statement"]


def test_typed_numeric_and_freshness_metrics_compile_per_dialect():
    definition = valid_definition()
    definition["spec"]["measurements"] = [
        {"id": "minimum", "type": "metric", "metric": "min", "field": "amount"},
        {"id": "maximum", "type": "metric", "metric": "max", "field": "amount"},
        {"id": "average", "type": "metric", "metric": "mean", "field": "amount"},
        {"id": "total", "type": "metric", "metric": "sum", "field": "amount"},
        {"id": "spread", "type": "metric", "metric": "stddev", "field": "amount"},
        {
            "id": "freshness",
            "type": "metric",
            "metric": "freshness_seconds",
            "field": "created_at",
        },
    ]
    definition["spec"]["breachWhen"] = {
        "op": "gt",
        "left": {"ref": "average"},
        "right": {"literal": 100},
    }
    postgres = compile_relational_plan(
        MonitorDefinition.model_validate(definition),
        relation=_relation(),
    ).statement
    assert 'MIN("amount")' in postgres
    assert 'MAX("amount")' in postgres
    assert 'AVG("amount")' in postgres
    assert 'SUM("amount")' in postgres
    assert 'STDDEV("amount")' in postgres
    assert 'EXTRACT(EPOCH FROM CURRENT_TIMESTAMP - MAX("created_at"))' in postgres

    definition["spec"]["measurements"] = [definition["spec"]["measurements"][-1]]
    definition["spec"]["breachWhen"] = {
        "op": "gt",
        "left": {"ref": "freshness"},
        "right": {"literal": 3600},
    }
    sqlite = compile_relational_plan(
        MonitorDefinition.model_validate(definition),
        relation=_relation(source_type="sqlite", schema_name="main"),
    ).statement
    assert "JULIANDAY('now')" in sqlite
    assert 'JULIANDAY(MAX("created_at"))' in sqlite
    assert "86400.0" in sqlite


def test_asset_binding_must_match_definition_target():
    import uuid

    with pytest.raises(MonitorPlanError, match="target asset") as exc:
        compile_relational_plan(
            MonitorDefinition.model_validate(valid_definition()),
            relation=_relation(asset_id=uuid.uuid4()),
        )
    assert exc.value.code == "asset_binding_mismatch"
