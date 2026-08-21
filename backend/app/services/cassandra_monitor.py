"""Immutable partition-bound Cassandra plans and bounded in-process evaluation."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from app.services.monitor_compiler import MonitorPlanError, OutputBinding
from app.services.monitor_dsl import Measurement, MonitorDefinition, Predicate, ValueExpression
from app.services.schema_binding import LogicalType, RelationBinding

CASSANDRA_PLANNER_VERSION = "datawatch-v1alpha1-cassandra-1"
MAX_ROWS_SCANNED = 10_000


@dataclass(frozen=True)
class CassandraMonitorPlan:
    relation: RelationBinding
    statement: str
    partition_keys: tuple[str, ...]
    partition_values: tuple[Any, ...]
    selected_fields: tuple[str, ...]
    definition_json: str
    outputs: tuple[OutputBinding, ...]
    breach_when: dict[str, Any]
    policy: dict[str, Any]
    timeout_seconds: int
    max_rows_scanned: int

    @property
    def planner_version(self) -> str:
        return CASSANDRA_PLANNER_VERSION

    def definition(self) -> MonitorDefinition:
        return MonitorDefinition.model_validate(json.loads(self.definition_json))

    def payload(self) -> dict[str, Any]:
        body = {
            "plannerVersion": self.planner_version,
            "kind": "cassandra_partition_scan",
            "sourceType": self.relation.source_type,
            "relation": {
                "assetId": str(self.relation.asset_id),
                "keyspace": self.relation.schema_name,
                "table": self.relation.table_name,
                "schemaFingerprint": self.relation.schema_fingerprint,
                "partitionKeys": list(self.partition_keys),
            },
            "statement": self.statement,
            "statementMode": "internal_prepared_only",
            "parameters": [
                {"name": key, "value": value} for key, value in zip(self.partition_keys, self.partition_values)
            ],
            "selectedFields": list(self.selected_fields),
            "outputs": [output.payload() for output in self.outputs],
            "resultContract": {
                "sourceRows": f"at_most_{self.max_rows_scanned}",
                "columns": [output.column for output in self.outputs],
                "values": "finite_number_or_null",
            },
            "evaluation": {"breachWhen": self.breach_when, "policy": self.policy},
            "readOnly": True,
            "execution": {
                "timeoutSeconds": self.timeout_seconds,
                "maxRowsScanned": self.max_rows_scanned,
                "prepared": True,
            },
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return {**body, "planHash": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


def quote_cql_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def cassandra_partition_keys(ddl: str, relation: RelationBinding) -> tuple[str, ...]:
    keys = []
    for column in relation.columns:
        quoted = re.escape(quote_cql_identifier(column.name))
        unquoted = re.escape(column.name)
        pattern = rf"(?:{quoted}|(?<![\w\"]){unquoted}(?![\w\"]))[^,\n]*\bis_partition_key\s*=\s*true\b"
        if re.search(pattern, ddl, flags=re.IGNORECASE):
            keys.append(column.name)
    return tuple(keys)


def render_cassandra_statement(
    relation: RelationBinding,
    selected_fields: tuple[str, ...],
    partition_keys: tuple[str, ...],
    max_rows_scanned: int,
) -> str:
    selected = ", ".join(quote_cql_identifier(field) for field in selected_fields)
    predicates = " AND ".join(f"{quote_cql_identifier(key)} = ?" for key in partition_keys)
    return (
        f"SELECT {selected} FROM {quote_cql_identifier(relation.schema_name)}."
        f"{quote_cql_identifier(relation.table_name)} WHERE {predicates} "
        f"LIMIT {max_rows_scanned + 1}"
    )


def _collect_value_fields(value: ValueExpression | None, fields: set[str]) -> None:
    if value and value.field:
        fields.add(value.field)


def _collect_predicate_fields(predicate: Predicate | None, fields: set[str]) -> None:
    if predicate is None:
        return
    if predicate.op == "is_missing":
        raise MonitorPlanError(
            "predicate_not_supported",
            "Cassandra has a fixed column schema; is_missing is unsupported",
        )
    _collect_value_fields(predicate.left, fields)
    _collect_value_fields(predicate.right, fields)
    _collect_value_fields(predicate.value, fields)
    for child in predicate.children():
        _collect_predicate_fields(child, fields)


def _validate_fields(definition: MonitorDefinition, relation: RelationBinding) -> tuple[str, ...]:
    fields: set[str] = set()
    for measurement in definition.spec.measurements:
        if measurement.field:
            fields.add(measurement.field)
        _collect_predicate_fields(measurement.filter_when, fields)
        _collect_predicate_fields(measurement.violation_when, fields)
    for field in fields:
        if relation.column(field) is None:
            raise MonitorPlanError("field_not_found", f"Field does not exist in the current schema: {field}")
    numeric_metrics = {
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
    string_metrics = {
        "empty_string_count",
        "empty_string_rate",
        "whitespace_count",
        "whitespace_rate",
        "text_length_min",
        "text_length_max",
        "text_length_mean",
    }
    boolean_metrics = {"true_count", "true_rate", "false_count", "false_rate"}
    for measurement in definition.spec.measurements:
        if measurement.type != "metric" or not measurement.field:
            continue
        column = relation.column(measurement.field)
        if measurement.metric in numeric_metrics and column.logical_type not in {
            LogicalType.INTEGER,
            LogicalType.NUMBER,
        }:
            raise MonitorPlanError(
                "field_type_not_supported",
                f"{measurement.metric} does not support {column.name} ({column.logical_type.value})",
            )
        if measurement.metric in string_metrics and column.logical_type != LogicalType.STRING:
            raise MonitorPlanError(
                "field_type_not_supported",
                f"{measurement.metric} does not support {column.name} ({column.logical_type.value})",
            )
        if measurement.metric in boolean_metrics and column.logical_type != LogicalType.BOOLEAN:
            raise MonitorPlanError(
                "field_type_not_supported",
                f"{measurement.metric} does not support {column.name} ({column.logical_type.value})",
            )
        if measurement.metric == "freshness_seconds" and column.logical_type not in {
            LogicalType.DATE,
            LogicalType.TIMESTAMP,
        }:
            raise MonitorPlanError(
                "field_type_not_supported",
                f"freshness_seconds does not support {column.name} ({column.logical_type.value})",
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
                "true_count",
                "false_count",
            }
            outputs.append(OutputBinding(measurement.id, f"dw_m{index}", nullable))
        else:
            for output in measurement.output or []:
                outputs.append(
                    OutputBinding(
                        f"{measurement.id}.{output}",
                        f"dw_m{index}_{output}",
                        output == "rate",
                    )
                )
    return tuple(outputs)


def compile_cassandra_plan(
    definition: MonitorDefinition,
    *,
    relation: RelationBinding,
    ddl: str,
) -> CassandraMonitorPlan:
    if relation.asset_id != definition.spec.target.asset_id:
        raise MonitorPlanError("asset_binding_mismatch", "Compiled relation does not match the monitor target asset")
    if relation.source_type != "cassandra":
        raise MonitorPlanError(
            "cassandra_compiler_not_supported",
            f"No Cassandra compiler is available for {relation.source_type}",
        )
    max_rows = definition.spec.execution.max_rows_scanned
    if max_rows is None:
        raise MonitorPlanError(
            "max_rows_scanned_required",
            "Cassandra monitors require maxRowsScanned",
            path="spec.execution.maxRowsScanned",
        )
    if max_rows > MAX_ROWS_SCANNED:
        raise MonitorPlanError(
            "max_rows_scanned_too_large",
            f"Cassandra maxRowsScanned cannot exceed {MAX_ROWS_SCANNED}",
            path="spec.execution.maxRowsScanned",
        )
    if (
        definition.spec.execution.max_bytes_scanned is not None
        or definition.spec.execution.max_documents_scanned is not None
    ):
        raise MonitorPlanError(
            "cassandra_cost_bound_conflict",
            "Cassandra plans use maxRowsScanned only",
            path="spec.execution",
        )
    partition_keys = cassandra_partition_keys(ddl, relation)
    if not partition_keys:
        raise MonitorPlanError(
            "partition_metadata_missing",
            "Cassandra schema snapshot does not declare partition keys",
        )
    bindings = definition.spec.execution.partition_bindings
    if set(bindings) != set(partition_keys):
        raise MonitorPlanError(
            "partition_bindings_incomplete",
            "partitionBindings must bind every partition key and no other fields",
            path="spec.execution.partitionBindings",
        )
    for key in partition_keys:
        column = relation.column(key)
        value = bindings[key]
        if column.logical_type in {LogicalType.INTEGER, LogicalType.NUMBER} and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            raise MonitorPlanError("partition_binding_type_mismatch", f"Partition binding does not match {key}")
        if column.logical_type == LogicalType.BOOLEAN and not isinstance(value, bool):
            raise MonitorPlanError("partition_binding_type_mismatch", f"Partition binding does not match {key}")
        if column.logical_type == LogicalType.STRING and not isinstance(value, str):
            raise MonitorPlanError("partition_binding_type_mismatch", f"Partition binding does not match {key}")
    selected_fields = _validate_fields(definition, relation)
    if not selected_fields:
        selected_fields = partition_keys
    statement = render_cassandra_statement(relation, selected_fields, partition_keys, max_rows)
    definition_json = json.dumps(
        definition.model_dump(mode="json", by_alias=True, exclude_unset=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return CassandraMonitorPlan(
        relation=relation,
        statement=statement,
        partition_keys=partition_keys,
        partition_values=tuple(bindings[key] for key in partition_keys),
        selected_fields=selected_fields,
        definition_json=definition_json,
        outputs=_outputs(definition),
        breach_when=definition.spec.breach_when.model_dump(mode="json", by_alias=True, exclude_unset=True),
        policy=definition.spec.policy.model_dump(mode="json", by_alias=True),
        timeout_seconds=definition.spec.execution.timeout_seconds,
        max_rows_scanned=max_rows,
    )


def analyze_cassandra_support(
    definition: MonitorDefinition,
    *,
    relation: RelationBinding,
    ddl: str,
) -> tuple[dict[str, Any], CassandraMonitorPlan | None]:
    try:
        plan = compile_cassandra_plan(definition, relation=relation, ddl=ddl)
    except MonitorPlanError as exc:
        return {
            "compilationSupported": False,
            "plannerVersion": CASSANDRA_PLANNER_VERSION,
            "issues": [exc.payload()],
        }, None
    return {
        "compilationSupported": True,
        "plannerVersion": CASSANDRA_PLANNER_VERSION,
        "issues": [],
    }, plan


def _row_value(row: dict[str, Any], field: str) -> Any:
    return row.get(field)


def _value(expression: ValueExpression | None, row: dict[str, Any]) -> Any:
    if expression is None:
        return None
    if expression.field is not None:
        return _row_value(row, expression.field)
    return expression.literal


def _matches(predicate: Predicate, row: dict[str, Any], now: datetime) -> bool:
    if predicate.all_ is not None:
        return all(_matches(child, row, now) for child in predicate.all_)
    if predicate.any_ is not None:
        return any(_matches(child, row, now) for child in predicate.any_)
    if predicate.not_ is not None:
        return not _matches(predicate.not_, row, now)
    if predicate.op == "is_missing":
        raise ValueError("Cassandra has fixed columns; is_missing is unsupported")
    target = _value(predicate.value, row)
    unary = {
        "is_null": lambda value: value is None,
        "is_not_null": lambda value: value is not None,
        "is_nan": lambda value: isinstance(value, float) and math.isnan(value),
        "is_zero": lambda value: value == 0,
        "is_negative": lambda value: value is not None and value < 0,
        "is_empty": lambda value: value == "",
        "is_whitespace": lambda value: isinstance(value, str) and value.strip() == "",
        "is_true": lambda value: value is True,
        "is_false": lambda value: value is False,
        "is_future": lambda value: isinstance(value, (date, datetime)) and _as_datetime(value) > now,
        "is_past": lambda value: isinstance(value, (date, datetime)) and _as_datetime(value) < now,
    }
    if predicate.op in unary:
        return unary[predicate.op](target)
    left = _value(predicate.left, row)
    right = _value(predicate.right, row)
    if predicate.op == "eq":
        return left == right
    if predicate.op == "ne":
        return left != right
    if predicate.op in {"gt", "gte", "lt", "lte"}:
        if left is None or right is None:
            return False
        return {"gt": left > right, "gte": left >= right, "lt": left < right, "lte": left <= right}[predicate.op]
    if predicate.op in {"between", "not_between"}:
        inside = left is not None and right[0] <= left <= right[1]
        return not inside if predicate.op == "not_between" else inside
    if predicate.op in {"in", "not_in"}:
        inside = left in right
        return not inside if predicate.op == "not_in" else inside
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    matched = {
        "contains": right in left,
        "starts_with": left.startswith(right),
        "ends_with": left.endswith(right),
    }[predicate.op]
    return matched


def _as_datetime(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)


def _metric(measurement: Measurement, rows: list[dict[str, Any]], now: datetime) -> int | float | None:
    scoped = rows
    if measurement.filter_when is not None:
        scoped = [row for row in rows if _matches(measurement.filter_when, row, now)]
    metric = measurement.metric
    if metric == "row_count":
        return len(scoped)
    values = [_row_value(row, measurement.field or "") for row in scoped]
    non_null = [value for value in values if value is not None]
    count_conditions = {
        "null_count": lambda value: value is None,
        "non_null_count": lambda value: value is not None,
        "empty_string_count": lambda value: value == "",
        "whitespace_count": lambda value: isinstance(value, str) and value.strip() == "",
        "zero_count": lambda value: value == 0,
        "negative_count": lambda value: value is not None and value < 0,
        "true_count": lambda value: value is True,
        "false_count": lambda value: value is False,
    }
    rate_metric = metric.removesuffix("_rate") + "_count" if metric and metric.endswith("_rate") else None
    if metric in count_conditions or rate_metric in count_conditions:
        count = sum(count_conditions[metric if metric in count_conditions else rate_metric](value) for value in values)
        return count / len(scoped) if rate_metric and scoped else None if rate_metric else count
    if metric == "distinct_count":
        return len(set(non_null))
    if metric == "distinct_rate":
        return len(set(non_null)) / len(scoped) if scoped else None
    if metric == "duplicate_count":
        return len(non_null) - len(set(non_null))
    if metric == "text_length_min":
        return min((len(value) for value in non_null), default=None)
    if metric == "text_length_max":
        return max((len(value) for value in non_null), default=None)
    if metric == "text_length_mean":
        return sum(len(value) for value in non_null) / len(non_null) if non_null else None
    if metric == "min":
        return min(non_null, default=None)
    if metric == "max":
        return max(non_null, default=None)
    if metric == "sum":
        return sum(non_null) if non_null else None
    if metric == "mean":
        return sum(non_null) / len(non_null) if non_null else None
    if metric == "stddev":
        if not non_null:
            return None
        mean = sum(non_null) / len(non_null)
        return math.sqrt(sum((value - mean) ** 2 for value in non_null) / len(non_null))
    if metric == "freshness_seconds":
        dates = [_as_datetime(value) for value in non_null]
        return (now - max(dates)).total_seconds() if dates else None
    raise ValueError(f"Unsupported Cassandra metric: {metric}")


def evaluate_bounded_rows(
    definition: MonitorDefinition,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate a typed definition over a connector-bounded metadata row set."""
    now = datetime.now(timezone.utc)
    measurements: dict[str, Any] = {}
    for measurement in definition.spec.measurements:
        if measurement.type == "metric":
            measurements[measurement.id] = _metric(measurement, rows, now)
            continue
        count = sum(_matches(measurement.violation_when, row, now) for row in rows)
        for output in measurement.output or []:
            measurements[f"{measurement.id}.{output}"] = (
                count if output == "count" else count / len(rows) if rows else None
            )
    return measurements


def evaluate_cassandra_rows(plan: CassandraMonitorPlan, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return evaluate_bounded_rows(plan.definition(), rows)
