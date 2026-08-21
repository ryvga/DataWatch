"""Immutable, bounded MongoDB aggregation plans for the typed monitor DSL."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.services.monitor_compiler import MonitorPlanError, OutputBinding
from app.services.monitor_dsl import Measurement, MonitorDefinition, Predicate, ValueExpression
from app.services.schema_binding import LogicalType, RelationBinding, SchemaColumn

DOCUMENT_PLANNER_VERSION = "datawatch-v1alpha1-mongodb-1"
MAX_DOCUMENTS_SCANNED = 100_000

_NUMERIC_TYPES = {LogicalType.INTEGER, LogicalType.NUMBER}
_ORDERED_TYPES = _NUMERIC_TYPES | {LogicalType.DATE, LogicalType.TIMESTAMP}


@dataclass(frozen=True)
class DocumentMonitorPlan:
    relation: RelationBinding
    pipeline_json: str
    outputs: tuple[OutputBinding, ...]
    breach_when: dict[str, Any]
    policy: dict[str, Any]
    timeout_seconds: int
    max_documents_scanned: int

    @property
    def planner_version(self) -> str:
        return DOCUMENT_PLANNER_VERSION

    def pipeline(self) -> list[dict[str, Any]]:
        """Return a fresh copy; the canonical plan itself remains immutable."""
        return json.loads(self.pipeline_json)

    def payload(self) -> dict[str, Any]:
        body = {
            "plannerVersion": self.planner_version,
            "kind": "mongodb_bounded_aggregate",
            "sourceType": self.relation.source_type,
            "relation": {
                "assetId": str(self.relation.asset_id),
                "database": self.relation.schema_name,
                "collection": self.relation.table_name,
                "schemaFingerprint": self.relation.schema_fingerprint,
            },
            "pipeline": self.pipeline(),
            "statementMode": "internal_generated_only",
            "parameters": [],
            "outputs": [output.payload() for output in self.outputs],
            "resultContract": {
                "documents": f"at_most_{self.max_documents_scanned}",
                "rows": "exactly_one",
                "columns": [output.column for output in self.outputs],
                "values": "finite_number_or_null",
            },
            "evaluation": {
                "breachWhen": self.breach_when,
                "policy": self.policy,
            },
            "readOnly": True,
            "execution": {
                "timeoutSeconds": self.timeout_seconds,
                "maxDocumentsScanned": self.max_documents_scanned,
                "allowDiskUse": False,
                "batchSize": 1,
            },
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return {**body, "planHash": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


def _field_path(name: str, relation: RelationBinding) -> tuple[str, SchemaColumn]:
    column = relation.column(name)
    if column is None:
        raise MonitorPlanError("field_not_found", f"Field does not exist in the current schema: {name}")
    segments = name.split(".")
    if "\\" in name or any(not segment or segment.startswith("$") for segment in segments):
        raise MonitorPlanError(
            "document_field_path_not_supported",
            f"MongoDB monitor field path is not safely addressable: {name}",
        )
    return f"${name}", column


def _require_type(column: SchemaColumn, allowed: set[LogicalType], operation: str) -> None:
    if column.logical_type not in allowed:
        raise MonitorPlanError(
            "field_type_not_supported",
            f"{operation} does not support {column.name} ({column.logical_type.value})",
        )


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


def _field_operand(expression: ValueExpression | None, relation: RelationBinding) -> tuple[str, SchemaColumn]:
    if expression is None or expression.field is None:
        raise MonitorPlanError(
            "predicate_operand_not_supported",
            "MongoDB document predicates require a field operand",
        )
    return _field_path(expression.field, relation)


def _literal_operand(expression: ValueExpression | None) -> Any:
    if expression is None or "literal" not in expression.model_fields_set:
        raise MonitorPlanError(
            "predicate_operand_not_supported",
            "MongoDB document predicates require a literal operand",
        )
    return expression.literal


def _predicate(predicate: Predicate, relation: RelationBinding) -> dict[str, Any]:
    if predicate.all_ is not None:
        return {"$and": [_predicate(child, relation) for child in predicate.all_]}
    if predicate.any_ is not None:
        return {"$or": [_predicate(child, relation) for child in predicate.any_]}
    if predicate.not_ is not None:
        return {"$not": [_predicate(predicate.not_, relation)]}

    if predicate.op in {"is_missing", "is_nan", "contains", "starts_with", "ends_with"}:
        raise MonitorPlanError(
            "predicate_not_supported",
            f"{predicate.op} is not supported by the bounded MongoDB planner",
        )
    if predicate.op in {
        "is_null",
        "is_not_null",
        "is_zero",
        "is_negative",
        "is_empty",
        "is_whitespace",
        "is_true",
        "is_false",
        "is_future",
        "is_past",
    }:
        field, column = _field_operand(predicate.value, relation)
        if predicate.op == "is_null":
            return {"$eq": [{"$ifNull": [field, None]}, None]}
        if predicate.op == "is_not_null":
            return {"$ne": [{"$ifNull": [field, None]}, None]}
        if predicate.op in {"is_empty", "is_whitespace"}:
            _require_type(column, {LogicalType.STRING}, predicate.op)
            target: Any = field
            if predicate.op == "is_whitespace":
                target = {"$trim": {"input": field}}
            return {"$eq": [target, ""]}
        if predicate.op in {"is_true", "is_false"}:
            _require_type(column, {LogicalType.BOOLEAN}, predicate.op)
            return {"$eq": [field, predicate.op == "is_true"]}
        if predicate.op in {"is_future", "is_past"}:
            _require_type(column, {LogicalType.DATE, LogicalType.TIMESTAMP}, predicate.op)
            return {"$gt" if predicate.op == "is_future" else "$lt": [field, "$$NOW"]}
        _require_type(column, _NUMERIC_TYPES, predicate.op)
        return {"$eq" if predicate.op == "is_zero" else "$lt": [field, 0]}

    left, column = _field_operand(predicate.left, relation)
    right = _literal_operand(predicate.right)
    if predicate.op in {"in", "not_in"}:
        if (
            any(value is None for value in right)
            or len({type(value) for value in right}) != 1
            or not _types_compatible(column.logical_type, _literal_type(right[0]))
        ):
            raise MonitorPlanError(
                "predicate_type_mismatch",
                f"{predicate.op} values do not match {column.name}",
            )
        expression = {"$in": [left, {"$literal": right}]}
        return {"$not": [expression]} if predicate.op == "not_in" else expression
    if predicate.op in {"between", "not_between"}:
        _require_type(column, _ORDERED_TYPES, predicate.op)
        low, high = right
        if any(value is None for value in (low, high)) or not all(
            _types_compatible(column.logical_type, _literal_type(value)) for value in (low, high)
        ):
            raise MonitorPlanError(
                "predicate_type_mismatch",
                f"{predicate.op} values do not match {column.name}",
            )
        expression = {
            "$and": [
                {"$gte": [left, {"$literal": low}]},
                {"$lte": [left, {"$literal": high}]},
            ]
        }
        return {"$not": [expression]} if predicate.op == "not_between" else expression
    if predicate.right and predicate.right.field is not None:
        right, right_column = _field_operand(predicate.right, relation)
        if column.logical_type != right_column.logical_type:
            raise MonitorPlanError("predicate_type_mismatch", "Predicate field types differ")
    else:
        if not _types_compatible(column.logical_type, _literal_type(right)):
            raise MonitorPlanError(
                "predicate_type_mismatch",
                f"{predicate.op} literal does not match {column.name}",
            )
        right = {"$literal": right}
    if predicate.op in {"gt", "gte", "lt", "lte"}:
        _require_type(column, _ORDERED_TYPES, predicate.op)
    operator = {"eq": "$eq", "ne": "$ne", "gt": "$gt", "gte": "$gte", "lt": "$lt", "lte": "$lte"}[predicate.op]
    return {operator: [left, right]}


def _conditional_count(condition: dict[str, Any]) -> dict[str, Any]:
    return {"$sum": {"$cond": [condition, 1, 0]}}


def _metric_accumulator(measurement: Measurement, relation: RelationBinding) -> tuple[dict[str, Any], bool]:
    if measurement.filter_when is not None:
        raise MonitorPlanError(
            "metric_filter_not_supported",
            "MongoDB metric filterWhen support is not implemented",
        )
    metric = measurement.metric
    if metric == "row_count":
        return {"$sum": 1}, False
    field, column = _field_path(measurement.field or "", relation)
    conditions = {
        "null_count": {"$eq": [{"$ifNull": [field, None]}, None]},
        "null_rate": {"$eq": [{"$ifNull": [field, None]}, None]},
        "non_null_count": {"$ne": [{"$ifNull": [field, None]}, None]},
        "non_null_rate": {"$ne": [{"$ifNull": [field, None]}, None]},
        "empty_string_count": {"$eq": [field, ""]},
        "empty_string_rate": {"$eq": [field, ""]},
        "whitespace_count": {"$eq": [{"$trim": {"input": field}}, ""]},
        "whitespace_rate": {"$eq": [{"$trim": {"input": field}}, ""]},
        "zero_count": {"$eq": [field, 0]},
        "zero_rate": {"$eq": [field, 0]},
        "negative_count": {"$lt": [field, 0]},
        "negative_rate": {"$lt": [field, 0]},
        "true_count": {"$eq": [field, True]},
        "true_rate": {"$eq": [field, True]},
        "false_count": {"$eq": [field, False]},
        "false_rate": {"$eq": [field, False]},
    }
    if metric in conditions:
        if metric.startswith(("empty", "whitespace")):
            _require_type(column, {LogicalType.STRING}, metric)
        elif metric.startswith(("zero", "negative")):
            _require_type(column, _NUMERIC_TYPES, metric)
        elif metric.startswith(("true", "false")):
            _require_type(column, {LogicalType.BOOLEAN}, metric)
        return _conditional_count(conditions[metric]), metric.endswith("_rate")
    if metric in {"min", "max", "mean", "sum", "stddev"}:
        _require_type(column, _NUMERIC_TYPES, metric)
        operator = {"min": "$min", "max": "$max", "mean": "$avg", "sum": "$sum", "stddev": "$stdDevPop"}[metric]
        return {operator: field}, True
    if metric in {"text_length_min", "text_length_max", "text_length_mean"}:
        _require_type(column, {LogicalType.STRING}, metric)
        operator = {"text_length_min": "$min", "text_length_max": "$max", "text_length_mean": "$avg"}[metric]
        return {operator: {"$strLenCP": field}}, True
    if metric == "freshness_seconds":
        _require_type(column, {LogicalType.DATE, LogicalType.TIMESTAMP}, metric)
        return {"$max": field}, True
    raise MonitorPlanError("metric_not_supported", f"MongoDB metric is not supported: {metric}")


def compile_document_plan(
    definition: MonitorDefinition,
    *,
    relation: RelationBinding,
) -> DocumentMonitorPlan:
    if relation.asset_id != definition.spec.target.asset_id:
        raise MonitorPlanError("asset_binding_mismatch", "Compiled relation does not match the monitor target asset")
    if relation.source_type != "mongodb":
        raise MonitorPlanError(
            "document_compiler_not_supported",
            f"No document compiler is available for {relation.source_type}",
        )
    max_documents = definition.spec.execution.max_documents_scanned
    if max_documents is None:
        raise MonitorPlanError(
            "max_documents_scanned_required",
            "MongoDB monitors require maxDocumentsScanned",
            path="spec.execution.maxDocumentsScanned",
        )
    if max_documents > MAX_DOCUMENTS_SCANNED:
        raise MonitorPlanError(
            "max_documents_scanned_too_large",
            f"MongoDB maxDocumentsScanned cannot exceed {MAX_DOCUMENTS_SCANNED}",
            path="spec.execution.maxDocumentsScanned",
        )
    if definition.spec.execution.max_bytes_scanned is not None:
        raise MonitorPlanError(
            "max_bytes_scanned_not_supported",
            "MongoDB plans enforce a document bound, not a byte billing bound",
            path="spec.execution.maxBytesScanned",
        )

    group: dict[str, Any] = {"_id": None, "dw_documents_scanned": {"$sum": 1}}
    project: dict[str, Any] = {"_id": 0, "dw_documents_scanned": 1}
    outputs: list[OutputBinding] = []
    for index, measurement in enumerate(definition.spec.measurements):
        if measurement.type == "violations":
            condition = _predicate(measurement.violation_when, relation)
            for output in measurement.output or []:
                alias = f"dw_m{index}_{output}"
                accumulator_alias = f"dw_a{index}_{output}"
                group[accumulator_alias] = _conditional_count(condition)
                project[alias] = (
                    f"${accumulator_alias}"
                    if output == "count"
                    else {
                        "$cond": [
                            {"$eq": ["$dw_documents_scanned", 0]},
                            None,
                            {"$divide": [f"${accumulator_alias}", "$dw_documents_scanned"]},
                        ]
                    }
                )
                outputs.append(OutputBinding(f"{measurement.id}.{output}", alias, output == "rate"))
            continue

        alias = f"dw_m{index}"
        accumulator, nullable = _metric_accumulator(measurement, relation)
        if measurement.metric == "row_count":
            project[alias] = "$dw_documents_scanned"
        elif measurement.metric and measurement.metric.endswith("_rate"):
            accumulator_alias = f"dw_a{index}"
            group[accumulator_alias] = accumulator
            project[alias] = {
                "$cond": [
                    {"$eq": ["$dw_documents_scanned", 0]},
                    None,
                    {"$divide": [f"${accumulator_alias}", "$dw_documents_scanned"]},
                ]
            }
        elif measurement.metric == "freshness_seconds":
            accumulator_alias = f"dw_a{index}"
            group[accumulator_alias] = accumulator
            project[alias] = {
                "$cond": [
                    {"$eq": [f"${accumulator_alias}", None]},
                    None,
                    {"$divide": [{"$subtract": ["$$NOW", f"${accumulator_alias}"]}, 1000]},
                ]
            }
        else:
            group[alias] = accumulator
            project[alias] = 1
        outputs.append(OutputBinding(measurement.id, alias, nullable))

    pipeline = [
        {"$limit": max_documents + 1},
        {"$group": group},
        {"$project": project},
    ]
    pipeline_json = json.dumps(pipeline, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return DocumentMonitorPlan(
        relation=relation,
        pipeline_json=pipeline_json,
        outputs=tuple(outputs),
        breach_when=definition.spec.breach_when.model_dump(mode="json", by_alias=True, exclude_unset=True),
        policy=definition.spec.policy.model_dump(mode="json", by_alias=True),
        timeout_seconds=definition.spec.execution.timeout_seconds,
        max_documents_scanned=max_documents,
    )


def analyze_document_support(
    definition: MonitorDefinition,
    *,
    relation: RelationBinding,
) -> tuple[dict[str, Any], DocumentMonitorPlan | None]:
    try:
        plan = compile_document_plan(definition, relation=relation)
    except MonitorPlanError as exc:
        return {
            "compilationSupported": False,
            "plannerVersion": DOCUMENT_PLANNER_VERSION,
            "issues": [exc.payload()],
        }, None
    return {
        "compilationSupported": True,
        "plannerVersion": DOCUMENT_PLANNER_VERSION,
        "issues": [],
    }, plan
