"""Immutable metadata-only Redis keyspace plans for the typed monitor DSL."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.services.cassandra_monitor import evaluate_bounded_rows
from app.services.monitor_compiler import MonitorPlanError, OutputBinding
from app.services.monitor_dsl import MonitorDefinition, Predicate, ValueExpression
from app.services.schema_binding import LogicalType, RelationBinding

REDIS_PLANNER_VERSION = "datawatch-v1alpha1-redis-1"
MAX_KEYS_SCANNED = 10_000

_NUMERIC_METRICS = {
    "null_count",
    "null_rate",
    "non_null_count",
    "non_null_rate",
    "distinct_count",
    "distinct_rate",
    "duplicate_count",
    "zero_count",
    "zero_rate",
    "negative_count",
    "negative_rate",
    "min",
    "max",
    "mean",
    "stddev",
    "sum",
}
_STRING_METRICS = {
    "null_count",
    "null_rate",
    "non_null_count",
    "non_null_rate",
    "distinct_count",
    "distinct_rate",
    "duplicate_count",
    "empty_string_count",
    "empty_string_rate",
    "whitespace_count",
    "whitespace_rate",
    "text_length_min",
    "text_length_max",
    "text_length_mean",
}


@dataclass(frozen=True)
class RedisMonitorPlan:
    relation: RelationBinding
    selected_fields: tuple[str, ...]
    definition_json: str
    outputs: tuple[OutputBinding, ...]
    breach_when: dict[str, Any]
    policy: dict[str, Any]
    timeout_seconds: int
    max_keys_scanned: int

    @property
    def planner_version(self) -> str:
        return REDIS_PLANNER_VERSION

    def definition(self) -> MonitorDefinition:
        return MonitorDefinition.model_validate(json.loads(self.definition_json))

    def payload(self) -> dict[str, Any]:
        body = {
            "plannerVersion": self.planner_version,
            "kind": "redis_bounded_metadata_scan",
            "sourceType": self.relation.source_type,
            "relation": self.relation.payload(),
            "scopeMode": "configured_key_pattern",
            "selectedFields": list(self.selected_fields),
            "commandAllowlist": [
                "SCAN",
                "TYPE",
                "PTTL",
                "MEMORY USAGE",
                "HLEN",
                "XLEN",
                "XINFO GROUPS",
            ],
            "outputs": [output.payload() for output in self.outputs],
            "resultContract": {
                "sourceKeys": f"at_most_{self.max_keys_scanned}",
                "columns": [output.column for output in self.outputs],
                "values": "finite_number_or_null",
                "storedValuesRead": False,
            },
            "evaluation": {"breachWhen": self.breach_when, "policy": self.policy},
            "readOnly": True,
            "execution": {
                "timeoutSeconds": self.timeout_seconds,
                "maxKeysScanned": self.max_keys_scanned,
                "failOnIncompleteScan": True,
            },
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return {**body, "planHash": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


def _literal_type(value: Any) -> LogicalType:
    if isinstance(value, bool):
        return LogicalType.BOOLEAN
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return LogicalType.NUMBER
    if isinstance(value, str):
        return LogicalType.STRING
    return LogicalType.UNKNOWN


def _value_type(expression: ValueExpression | None, relation: RelationBinding) -> LogicalType:
    if expression is None:
        return LogicalType.UNKNOWN
    if expression.field is not None:
        column = relation.column(expression.field)
        if column is None:
            raise MonitorPlanError("field_not_found", f"Field does not exist: {expression.field}")
        return column.logical_type
    return _literal_type(expression.literal)


def _predicate_fields(predicate: Predicate | None, relation: RelationBinding, fields: set[str]) -> None:
    if predicate is None:
        return
    if predicate.op == "is_missing":
        raise MonitorPlanError(
            "predicate_not_supported",
            "Redis metadata rows have a fixed schema; is_missing is unsupported",
        )
    for expression in (predicate.left, predicate.right, predicate.value):
        if expression and expression.field:
            if relation.column(expression.field) is None:
                raise MonitorPlanError("field_not_found", f"Field does not exist: {expression.field}")
            fields.add(expression.field)
    for child in predicate.children():
        _predicate_fields(child, relation, fields)

    if predicate.op is None:
        return
    if predicate.op in {"is_nan", "is_zero", "is_negative"}:
        if _value_type(predicate.value, relation) not in {LogicalType.INTEGER, LogicalType.NUMBER}:
            raise MonitorPlanError("predicate_type_mismatch", f"{predicate.op} requires numeric metadata")
    elif predicate.op in {"is_empty", "is_whitespace", "contains", "starts_with", "ends_with"}:
        expression = predicate.value if predicate.value is not None else predicate.left
        if _value_type(expression, relation) != LogicalType.STRING:
            raise MonitorPlanError("predicate_type_mismatch", f"{predicate.op} requires string metadata")
    elif predicate.op in {"is_future", "is_past"}:
        raise MonitorPlanError("predicate_not_supported", "Redis metadata has no date/time field")
    elif predicate.op in {"is_true", "is_false"}:
        if _value_type(predicate.value, relation) != LogicalType.BOOLEAN:
            raise MonitorPlanError("predicate_type_mismatch", f"{predicate.op} requires boolean metadata")
    elif predicate.op in {"gt", "gte", "lt", "lte", "between", "not_between"}:
        if _value_type(predicate.left, relation) not in {LogicalType.INTEGER, LogicalType.NUMBER}:
            raise MonitorPlanError("predicate_type_mismatch", f"{predicate.op} requires numeric metadata")
        right = predicate.right.literal if predicate.right else None
        right_values = right if isinstance(right, list) else [right]
        if not right_values or any(
            _literal_type(value) not in {LogicalType.INTEGER, LogicalType.NUMBER} for value in right_values
        ):
            raise MonitorPlanError("predicate_type_mismatch", f"{predicate.op} requires numeric bounds")
    elif predicate.op in {"eq", "ne", "in", "not_in"}:
        left_type = _value_type(predicate.left, relation)
        if predicate.right and predicate.right.field is not None:
            right_types = [_value_type(predicate.right, relation)]
        else:
            right = predicate.right.literal if predicate.right else None
            right_values = right if isinstance(right, list) else [right]
            right_types = [_literal_type(value) for value in right_values]
        if not right_types or any(
            not (left_type == right_type or {left_type, right_type} <= {LogicalType.INTEGER, LogicalType.NUMBER})
            for right_type in right_types
        ):
            raise MonitorPlanError("predicate_type_mismatch", f"{predicate.op} operand types differ")


def _validate_measurements(definition: MonitorDefinition, relation: RelationBinding) -> tuple[str, ...]:
    fields: set[str] = set()
    for measurement in definition.spec.measurements:
        _predicate_fields(measurement.filter_when, relation, fields)
        _predicate_fields(measurement.violation_when, relation, fields)
        if measurement.type == "violations":
            continue
        if measurement.metric == "row_count":
            continue
        if not measurement.field:
            raise MonitorPlanError("field_required", f"{measurement.metric} requires a metadata field")
        column = relation.column(measurement.field)
        if column is None:
            raise MonitorPlanError("field_not_found", f"Field does not exist: {measurement.field}")
        fields.add(measurement.field)
        allowed = _STRING_METRICS if column.logical_type == LogicalType.STRING else _NUMERIC_METRICS
        if measurement.metric not in allowed:
            raise MonitorPlanError(
                "metric_not_supported",
                f"{measurement.metric} is unsupported for Redis metadata field {measurement.field}",
            )
    return tuple(sorted(fields))


def _outputs(definition: MonitorDefinition) -> tuple[OutputBinding, ...]:
    outputs = []
    for index, measurement in enumerate(definition.spec.measurements):
        if measurement.type == "metric":
            nullable = measurement.metric not in {
                "row_count",
                "null_count",
                "non_null_count",
                "distinct_count",
                "duplicate_count",
                "empty_string_count",
                "whitespace_count",
                "zero_count",
                "negative_count",
            }
            outputs.append(OutputBinding(measurement.id, f"dw_m{index}", nullable))
        else:
            for output in measurement.output or []:
                outputs.append(OutputBinding(f"{measurement.id}.{output}", f"dw_m{index}_{output}", output == "rate"))
    return tuple(outputs)


def compile_redis_plan(
    definition: MonitorDefinition,
    *,
    relation: RelationBinding,
) -> RedisMonitorPlan:
    if relation.asset_id != definition.spec.target.asset_id:
        raise MonitorPlanError("asset_binding_mismatch", "Compiled relation does not match the monitor target asset")
    if relation.source_type != "redis":
        raise MonitorPlanError(
            "redis_compiler_not_supported", f"No Redis compiler is available for {relation.source_type}"
        )
    execution = definition.spec.execution
    max_keys = execution.max_keys_scanned
    if max_keys is None:
        raise MonitorPlanError(
            "max_keys_scanned_required",
            "Redis monitors require maxKeysScanned",
            path="spec.execution.maxKeysScanned",
        )
    if max_keys > MAX_KEYS_SCANNED:
        raise MonitorPlanError(
            "max_keys_scanned_too_large",
            f"Redis maxKeysScanned cannot exceed {MAX_KEYS_SCANNED}",
            path="spec.execution.maxKeysScanned",
        )
    if (
        any(
            bound is not None
            for bound in (
                execution.max_bytes_scanned,
                execution.max_documents_scanned,
                execution.max_rows_scanned,
            )
        )
        or execution.partition_bindings
    ):
        raise MonitorPlanError(
            "redis_cost_bound_conflict",
            "Redis plans use maxKeysScanned only",
            path="spec.execution",
        )
    if execution.sampling.mode != "off":
        raise MonitorPlanError(
            "redis_sampling_not_supported",
            "Redis monitor scans must set sampling.mode to off",
            path="spec.execution.sampling.mode",
        )
    selected_fields = _validate_measurements(definition, relation)
    definition_json = json.dumps(
        definition.model_dump(mode="json", by_alias=True, exclude_unset=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return RedisMonitorPlan(
        relation=relation,
        selected_fields=selected_fields,
        definition_json=definition_json,
        outputs=_outputs(definition),
        breach_when=definition.spec.breach_when.model_dump(mode="json", by_alias=True, exclude_unset=True),
        policy=definition.spec.policy.model_dump(mode="json", by_alias=True),
        timeout_seconds=execution.timeout_seconds,
        max_keys_scanned=max_keys,
    )


def analyze_redis_support(
    definition: MonitorDefinition,
    *,
    relation: RelationBinding,
) -> tuple[dict[str, Any], RedisMonitorPlan | None]:
    try:
        plan = compile_redis_plan(definition, relation=relation)
    except MonitorPlanError as exc:
        return {
            "compilationSupported": False,
            "plannerVersion": REDIS_PLANNER_VERSION,
            "issues": [exc.payload()],
        }, None
    return {
        "compilationSupported": True,
        "plannerVersion": REDIS_PLANNER_VERSION,
        "issues": [],
    }, plan


def evaluate_redis_rows(plan: RedisMonitorPlan, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return evaluate_bounded_rows(plan.definition(), rows)
