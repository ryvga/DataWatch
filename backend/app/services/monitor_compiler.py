"""Deterministic, non-executing relational compiler for safe monitor definitions."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import reduce
from typing import Any

from sqlglot import exp

from app.services.monitor_dsl import (
    Measurement,
    MonitorDefinition,
    Predicate,
    ValueExpression,
)
from app.services.schema_binding import LogicalType, RelationBinding, SchemaColumn

PLANNER_VERSION = "datawatch-v1alpha1-relational-2"

SOURCE_DIALECTS = {
    "postgres": "postgres",
    "duckdb": "duckdb",
    "sqlite": "sqlite",
}

_NUMERIC_TYPES = {LogicalType.INTEGER, LogicalType.NUMBER}
_ORDERED_TYPES = _NUMERIC_TYPES | {LogicalType.DATE, LogicalType.TIMESTAMP}


class MonitorPlanError(ValueError):
    """A valid DSL definition cannot be represented by the selected planner."""

    def __init__(self, code: str, message: str, path: str = "spec"):
        super().__init__(message)
        self.code = code
        self.path = path

    def payload(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": str(self)}


@dataclass(frozen=True)
class PlanParameter:
    name: str
    logical_type: str
    value: Any

    def payload(self) -> dict[str, Any]:
        return {"name": self.name, "type": self.logical_type, "value": self.value}


@dataclass(frozen=True)
class OutputBinding:
    reference: str
    column: str
    nullable: bool

    def payload(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "column": self.column,
            "type": "number",
            "nullable": self.nullable,
        }


@dataclass(frozen=True)
class RelationalMonitorPlan:
    relation: RelationBinding
    dialect: str
    statement: str
    parameters: tuple[PlanParameter, ...]
    outputs: tuple[OutputBinding, ...]
    breach_when: dict[str, Any]
    policy: dict[str, Any]

    def payload(self) -> dict[str, Any]:
        body = {
            "plannerVersion": PLANNER_VERSION,
            "kind": "relational_aggregate",
            "sourceType": self.relation.source_type,
            "dialect": self.dialect,
            "relation": {
                "assetId": str(self.relation.asset_id),
                "schema": self.relation.schema_name,
                "table": self.relation.table_name,
                "schemaFingerprint": self.relation.schema_fingerprint,
            },
            "statement": self.statement,
            "statementMode": "preview_only",
            "driverBindingRequired": True,
            "parameters": [parameter.payload() for parameter in self.parameters],
            "outputs": [output.payload() for output in self.outputs],
            "resultContract": {
                "rows": "exactly_one",
                "columns": [output.column for output in self.outputs],
                "values": "finite_number_or_null",
            },
            "evaluation": {
                "breachWhen": self.breach_when,
                "policy": self.policy,
            },
            "readOnly": True,
        }
        canonical = json.dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return {**body, "planHash": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


class _ParameterBinder:
    def __init__(self):
        self.parameters: list[PlanParameter] = []

    def bind(self, value: Any) -> exp.Placeholder:
        name = f"p{len(self.parameters)}"
        logical_type = (
            "boolean"
            if isinstance(value, bool)
            else "integer"
            if isinstance(value, int)
            else "number"
            if isinstance(value, float)
            else "string"
        )
        self.parameters.append(
            PlanParameter(name=name, logical_type=logical_type, value=value)
        )
        return exp.Placeholder(this=name)


def _column(name: str) -> exp.Column:
    return exp.Column(this=exp.Identifier(this=name, quoted=True))


def _field_operand(
    expression: ValueExpression | None,
    relation: RelationBinding,
) -> tuple[exp.Column, SchemaColumn]:
    if expression is None or expression.field is None:
        raise MonitorPlanError(
            "predicate_operand_not_supported",
            "the relational v1 compiler requires a field on the left",
        )
    column = relation.column(expression.field)
    if column is None:
        raise MonitorPlanError(
            "field_not_found",
            f"Field does not exist in the current schema: {expression.field}",
        )
    return _column(expression.field), column


def _literal_operand(
    expression: ValueExpression | None,
    binder: _ParameterBinder,
) -> exp.Expression:
    if expression is None or "literal" not in expression.model_fields_set:
        raise MonitorPlanError(
            "predicate_operand_not_supported",
            "the relational v1 compiler requires a literal on the right",
        )
    if expression.literal is None or isinstance(expression.literal, list):
        raise MonitorPlanError(
            "invalid_literal_shape",
            "binary predicates require one non-null scalar literal",
        )
    return binder.bind(expression.literal)


def _literal_type(value: Any) -> LogicalType:
    if isinstance(value, bool):
        return LogicalType.BOOLEAN
    if isinstance(value, int):
        return LogicalType.INTEGER
    if isinstance(value, float):
        return LogicalType.NUMBER
    if isinstance(value, str):
        return LogicalType.STRING
    return LogicalType.UNKNOWN


def _types_compatible(left: LogicalType, right: LogicalType) -> bool:
    return left == right or left in _NUMERIC_TYPES and right in _NUMERIC_TYPES


def _require_type(
    column: SchemaColumn,
    allowed: set[LogicalType],
    operation: str,
) -> None:
    if column.logical_type not in allowed:
        raise MonitorPlanError(
            "field_type_not_supported",
            f"{operation} does not support {column.name} ({column.logical_type.value})",
        )


def _conditional_count(condition: exp.Expression) -> exp.Expression:
    case = exp.Case(
        ifs=[exp.If(this=condition, true=exp.Literal.number(1))],
    )
    return exp.Count(this=case)


def _rate(numerator: exp.Expression) -> exp.Expression:
    denominator = exp.func("NULLIF", exp.Count(this=exp.Star()), exp.Literal.number(0))
    return exp.Div(
        this=exp.Mul(this=numerator, expression=exp.Literal.number("1.0")),
        expression=denominator,
    )


def _predicate(
    predicate: Predicate,
    binder: _ParameterBinder,
    relation: RelationBinding,
) -> exp.Expression:
    if predicate.all_ is not None:
        return reduce(
            lambda left, right: exp.And(this=left, expression=right),
            (_predicate(child, binder, relation) for child in predicate.all_),
        )
    if predicate.any_ is not None:
        return reduce(
            lambda left, right: exp.Or(this=left, expression=right),
            (_predicate(child, binder, relation) for child in predicate.any_),
        )
    if predicate.not_ is not None:
        return exp.Not(this=_predicate(predicate.not_, binder, relation))

    if predicate.op in {"is_missing", "is_nan"}:
        raise MonitorPlanError(
            "predicate_not_supported",
            f"{predicate.op} has no portable relational v1 semantics",
        )
    if predicate.op in {"is_null", "is_not_null", "is_zero", "is_negative"}:
        target, column = _field_operand(predicate.value, relation)
        if predicate.op == "is_null":
            return exp.Is(this=target, expression=exp.Null())
        if predicate.op == "is_not_null":
            return exp.Not(this=exp.Is(this=target, expression=exp.Null()))
        _require_type(column, _NUMERIC_TYPES, predicate.op)
        operator = exp.EQ if predicate.op == "is_zero" else exp.LT
        return operator(this=target, expression=exp.Literal.number(0))

    left, left_column = _field_operand(predicate.left, relation)
    if predicate.op in {"in", "not_in"}:
        values = predicate.right.literal
        if any(value is None for value in values) or len({type(value) for value in values}) != 1:
            raise MonitorPlanError(
                "invalid_literal_shape",
                "membership lists must be non-null and homogeneous",
            )
        right_type = _literal_type(values[0])
        if not _types_compatible(left_column.logical_type, right_type):
            raise MonitorPlanError(
                "predicate_type_mismatch",
                f"{predicate.op} values do not match {left_column.name}",
            )
        expression = exp.In(
            this=left,
            expressions=[binder.bind(value) for value in values],
        )
        return exp.Not(this=expression) if predicate.op == "not_in" else expression
    if predicate.op == "between":
        _require_type(left_column, _ORDERED_TYPES, "between")
        low, high = predicate.right.literal
        if any(value is None for value in (low, high)):
            raise MonitorPlanError("invalid_literal_shape", "between values cannot be null")
        if not all(
            _types_compatible(left_column.logical_type, _literal_type(value))
            for value in (low, high)
        ):
            raise MonitorPlanError(
                "predicate_type_mismatch",
                f"between values do not match {left_column.name}",
            )
        return exp.Between(this=left, low=binder.bind(low), high=binder.bind(high))
    if predicate.op in {"contains", "starts_with", "ends_with"}:
        _require_type(left_column, {LogicalType.STRING}, predicate.op)
        value = predicate.right.literal
        escaped = value.replace("!", "!!").replace("%", "!%").replace("_", "!_")
        pattern = {
            "contains": f"%{escaped}%",
            "starts_with": f"{escaped}%",
            "ends_with": f"%{escaped}",
        }[predicate.op]
        like = exp.Like(this=left, expression=binder.bind(pattern))
        return exp.Escape(this=like, expression=exp.Literal.string("!"))

    if predicate.right.field is not None:
        right, right_column = _field_operand(predicate.right, relation)
        right_type = right_column.logical_type
    else:
        right = _literal_operand(predicate.right, binder)
        right_type = _literal_type(predicate.right.literal)
    if not _types_compatible(left_column.logical_type, right_type):
        raise MonitorPlanError(
            "predicate_type_mismatch",
            f"{predicate.op} operands have incompatible types",
        )
    if predicate.op in {"gt", "gte", "lt", "lte"}:
        _require_type(left_column, _ORDERED_TYPES, predicate.op)
    operators = {
        "eq": exp.EQ,
        "ne": exp.NEQ,
        "gt": exp.GT,
        "gte": exp.GTE,
        "lt": exp.LT,
        "lte": exp.LTE,
    }
    return operators[predicate.op](this=left, expression=right)


def _metric_expression(
    measurement: Measurement,
    relation: RelationBinding,
) -> exp.Expression:
    metric = measurement.metric
    if metric == "row_count":
        return exp.Count(this=exp.Star())

    column_binding = relation.column(measurement.field)
    if column_binding is None:
        raise MonitorPlanError(
            "field_not_found",
            f"Field does not exist in the current schema: {measurement.field}",
        )
    column = _column(column_binding.name)
    if metric == "null_count":
        return exp.Sub(
            this=exp.Count(this=exp.Star()),
            expression=exp.Count(this=column),
        )
    if metric == "null_rate":
        null_count = exp.Sub(
            this=exp.Count(this=exp.Star()),
            expression=exp.Count(this=column),
        )
        return _rate(null_count)
    if metric == "distinct_count":
        _require_type(
            column_binding,
            _NUMERIC_TYPES
            | {LogicalType.STRING, LogicalType.BOOLEAN, LogicalType.DATE, LogicalType.TIMESTAMP},
            metric,
        )
        return exp.Count(this=exp.Distinct(expressions=[column]))
    if metric == "distinct_rate":
        _require_type(
            column_binding,
            _NUMERIC_TYPES
            | {LogicalType.STRING, LogicalType.BOOLEAN, LogicalType.DATE, LogicalType.TIMESTAMP},
            metric,
        )
        denominator = exp.func(
            "NULLIF",
            exp.Count(this=column.copy()),
            exp.Literal.number(0),
        )
        return exp.Div(
            this=exp.Mul(
                this=exp.Count(this=exp.Distinct(expressions=[column])),
                expression=exp.Literal.number("1.0"),
            ),
            expression=denominator,
        )
    if metric in {"min", "max"}:
        _require_type(column_binding, _ORDERED_TYPES, metric)
        operator = exp.Min if metric == "min" else exp.Max
        return operator(this=column)
    if metric in {"mean", "sum", "stddev"}:
        _require_type(column_binding, _NUMERIC_TYPES, metric)
        if metric == "mean":
            return exp.Avg(this=column)
        if metric == "sum":
            return exp.Sum(this=column)
        if relation.source_type == "sqlite":
            raise MonitorPlanError(
                "metric_not_supported",
                "stddev is not available in the SQLite runtime",
            )
        return exp.func("STDDEV", column)
    if metric == "freshness_seconds":
        _require_type(
            column_binding,
            {LogicalType.DATE, LogicalType.TIMESTAMP},
            metric,
        )
        latest = exp.Max(this=column)
        if relation.source_type == "sqlite":
            return exp.Mul(
                this=exp.Sub(
                    this=exp.func("JULIANDAY", exp.Literal.string("now")),
                    expression=exp.func("JULIANDAY", latest),
                ),
                expression=exp.Literal.number("86400.0"),
            )
        elapsed = exp.Sub(this=exp.CurrentTimestamp(), expression=latest)
        return exp.Extract(this=exp.Var(this="EPOCH"), expression=elapsed)
    raise MonitorPlanError("metric_not_supported", f"Unknown metric: {metric}")


def compile_relational_plan(
    definition: MonitorDefinition,
    *,
    relation: RelationBinding,
) -> RelationalMonitorPlan:
    """Compile a definition into one read-only aggregate statement without executing it."""
    if relation.asset_id != definition.spec.target.asset_id:
        raise MonitorPlanError(
            "asset_binding_mismatch",
            "Compiled relation does not match the monitor target asset",
            path="spec.target.assetId",
        )
    normalized_source = relation.source_type.lower()
    dialect = SOURCE_DIALECTS.get(normalized_source)
    if not dialect:
        raise MonitorPlanError(
            "relational_compiler_not_supported",
            f"No safe relational compiler is available for {relation.source_type}",
        )

    binder = _ParameterBinder()
    projections: list[exp.Expression] = []
    outputs: list[OutputBinding] = []
    for index, measurement in enumerate(definition.spec.measurements):
        if measurement.type == "metric":
            column_alias = f"dw_m{index}"
            projections.append(
                exp.alias_(
                    _metric_expression(measurement, relation),
                    column_alias,
                    quoted=True,
                )
            )
            outputs.append(
                OutputBinding(
                    reference=measurement.id,
                    column=column_alias,
                    nullable=measurement.metric != "row_count",
                )
            )
            continue

        condition = _predicate(measurement.violation_when, binder, relation)
        count = _conditional_count(condition)
        for output in measurement.output:
            reference = f"{measurement.id}.{output}"
            alias = f"dw_m{index}_{output}"
            expression = count.copy() if output == "count" else _rate(count.copy())
            projections.append(exp.alias_(expression, alias, quoted=True))
            outputs.append(
                OutputBinding(
                    reference=reference,
                    column=alias,
                    nullable=output == "rate",
                )
            )

    table = exp.Table(
        this=exp.Identifier(this=relation.table_name, quoted=True),
        db=exp.Identifier(this=relation.schema_name, quoted=True),
    )
    statement = exp.select(*projections).from_(table).sql(dialect=dialect)
    return RelationalMonitorPlan(
        relation=relation,
        dialect=dialect,
        statement=statement,
        parameters=tuple(binder.parameters),
        outputs=tuple(outputs),
        breach_when=definition.spec.breach_when.model_dump(mode="json", by_alias=True),
        policy=definition.spec.policy.model_dump(mode="json", by_alias=True),
    )


def analyze_relational_support(
    definition: MonitorDefinition,
    *,
    relation: RelationBinding,
) -> tuple[dict[str, Any], RelationalMonitorPlan | None]:
    try:
        plan = compile_relational_plan(definition, relation=relation)
    except MonitorPlanError as exc:
        return (
            {
                "compilationSupported": False,
                "plannerVersion": PLANNER_VERSION,
                "issues": [exc.payload()],
            },
            None,
        )
    return (
        {
            "compilationSupported": True,
            "plannerVersion": PLANNER_VERSION,
            "issues": [],
        },
        plan,
    )
