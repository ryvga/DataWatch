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

PLANNER_VERSION = "datawatch-v1alpha1-relational-1"

SOURCE_DIALECTS = {
    "postgres": "postgres",
    "duckdb": "duckdb",
    "sqlite": "sqlite",
}

_PORTABLE_METRICS = {
    "row_count",
    "null_count",
    "null_rate",
    "distinct_count",
    "distinct_rate",
}


class MonitorPlanError(ValueError):
    """A valid DSL definition cannot be represented by the selected planner."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


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
    source_type: str
    dialect: str
    asset_id: str
    statement: str
    parameters: tuple[PlanParameter, ...]
    outputs: tuple[OutputBinding, ...]
    breach_when: dict[str, Any]
    policy: dict[str, Any]

    def payload(self) -> dict[str, Any]:
        body = {
            "plannerVersion": PLANNER_VERSION,
            "kind": "relational_aggregate",
            "sourceType": self.source_type,
            "dialect": self.dialect,
            "assetId": self.asset_id,
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


def _field_operand(expression: ValueExpression | None) -> exp.Column:
    if expression is None or expression.field is None:
        raise MonitorPlanError(
            "predicate_operand_not_supported",
            "the relational v1 compiler requires a field on the left",
        )
    return _column(expression.field)


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


def _predicate(predicate: Predicate, binder: _ParameterBinder) -> exp.Expression:
    if predicate.all_ is not None:
        return reduce(
            lambda left, right: exp.And(this=left, expression=right),
            (_predicate(child, binder) for child in predicate.all_),
        )
    if predicate.any_ is not None:
        return reduce(
            lambda left, right: exp.Or(this=left, expression=right),
            (_predicate(child, binder) for child in predicate.any_),
        )
    if predicate.not_ is not None:
        return exp.Not(this=_predicate(predicate.not_, binder))

    if predicate.op in {
        "is_missing",
        "is_nan",
        "contains",
        "starts_with",
        "ends_with",
        "gt",
        "gte",
        "lt",
        "lte",
        "between",
        "is_zero",
        "is_negative",
    }:
        raise MonitorPlanError(
            "predicate_not_supported",
            f"{predicate.op} is deferred until typed field semantics are available",
        )
    if predicate.op in {"is_null", "is_not_null"}:
        target = _field_operand(predicate.value)
        if predicate.op == "is_null":
            return exp.Is(this=target, expression=exp.Null())
        return exp.Not(this=exp.Is(this=target, expression=exp.Null()))

    left = _field_operand(predicate.left)
    if predicate.op in {"in", "not_in"}:
        values = predicate.right.literal
        if any(value is None for value in values) or len({type(value) for value in values}) != 1:
            raise MonitorPlanError(
                "invalid_literal_shape",
                "membership lists must be non-null and homogeneous",
            )
        expression = exp.In(
            this=left,
            expressions=[binder.bind(value) for value in values],
        )
        return exp.Not(this=expression) if predicate.op == "not_in" else expression
    right = _literal_operand(predicate.right, binder)
    operators = {
        "eq": exp.EQ,
        "ne": exp.NEQ,
    }
    return operators[predicate.op](this=left, expression=right)


def _metric_expression(measurement: Measurement) -> exp.Expression:
    metric = measurement.metric
    if metric not in _PORTABLE_METRICS:
        raise MonitorPlanError(
            "metric_not_supported",
            f"{metric} is deferred until typed and dialect-specific semantics are available",
        )
    if metric == "row_count":
        return exp.Count(this=exp.Star())

    column = _column(measurement.field)
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
        return exp.Count(this=exp.Distinct(expressions=[column]))
    if metric == "distinct_rate":
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
    raise MonitorPlanError("metric_not_supported", f"Unknown metric: {metric}")


def compile_relational_plan(
    definition: MonitorDefinition,
    *,
    source_type: str,
    schema_name: str,
    table_name: str,
) -> RelationalMonitorPlan:
    """Compile a definition into one read-only aggregate statement without executing it."""
    normalized_source = source_type.lower()
    dialect = SOURCE_DIALECTS.get(normalized_source)
    if not dialect:
        raise MonitorPlanError(
            "relational_compiler_not_supported",
            f"No safe relational compiler is available for {source_type}",
        )

    binder = _ParameterBinder()
    projections: list[exp.Expression] = []
    outputs: list[OutputBinding] = []
    for index, measurement in enumerate(definition.spec.measurements):
        if measurement.type == "metric":
            column_alias = f"dw_m{index}"
            projections.append(
                exp.alias_(
                    _metric_expression(measurement),
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

        condition = _predicate(measurement.violation_when, binder)
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
        this=exp.Identifier(this=table_name, quoted=True),
        db=exp.Identifier(this=schema_name, quoted=True),
    )
    statement = exp.select(*projections).from_(table).sql(dialect=dialect)
    return RelationalMonitorPlan(
        source_type=normalized_source,
        dialect=dialect,
        asset_id=str(definition.spec.target.asset_id),
        statement=statement,
        parameters=tuple(binder.parameters),
        outputs=tuple(outputs),
        breach_when=definition.spec.breach_when.model_dump(mode="json", by_alias=True),
        policy=definition.spec.policy.model_dump(mode="json", by_alias=True),
    )
