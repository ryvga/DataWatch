"""Strict, non-executable runtime model for datawatch.io/v1alpha1 monitors."""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_DEFINITION_BYTES = 65_536
MAX_PREDICATE_NODES = 100
MAX_PREDICATE_DEPTH = 10
_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ValueExpression(StrictModel):
    field: str | None = Field(default=None, min_length=1, max_length=255)
    literal: Any = None
    ref: str | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def exactly_one_value_kind(self):
        keys = self.model_fields_set & {"field", "literal", "ref"}
        if len(keys) != 1:
            raise ValueError("value must contain exactly one of field, literal, or ref")
        if "field" in keys and not self.field:
            raise ValueError("field must be a non-empty string")
        if "ref" in keys and not self.ref:
            raise ValueError("ref must be a non-empty string")
        if "literal" in keys:
            value = self.literal
            values = value if isinstance(value, list) else [value]
            if isinstance(value, list) and len(value) > 100:
                raise ValueError("literal lists may contain at most 100 values")
            if any(
                isinstance(item, (dict, list, tuple, set))
                or not isinstance(item, (str, int, float, bool, type(None)))
                for item in values
            ):
                raise ValueError("literals must be JSON scalar values or a flat scalar list")
            if any(isinstance(item, float) and not math.isfinite(item) for item in values):
                raise ValueError("literal numbers must be finite")
            if any(isinstance(item, str) and len(item) > 2_048 for item in values):
                raise ValueError("literal strings may contain at most 2048 characters")
        if self.field and "\x00" in self.field:
            raise ValueError("field must not contain NUL bytes")
        return self


class Predicate(StrictModel):
    op: Literal[
        "eq", "ne", "gt", "gte", "lt", "lte", "between", "in", "not_in",
        "contains", "starts_with", "ends_with", "is_null", "is_not_null",
        "is_missing", "is_nan", "is_zero", "is_negative",
    ] | None = None
    left: ValueExpression | None = None
    right: ValueExpression | None = None
    value: ValueExpression | None = None
    all_: list["Predicate"] | None = Field(default=None, alias="all", min_length=1, max_length=50)
    any_: list["Predicate"] | None = Field(default=None, alias="any", min_length=1, max_length=50)
    not_: "Predicate | None" = Field(default=None, alias="not")

    @model_validator(mode="after")
    def valid_shape(self):
        group_fields = [self.all_ is not None, self.any_ is not None, self.not_ is not None]
        if sum(group_fields):
            if sum(group_fields) != 1 or self.op or self.left or self.right or self.value:
                raise ValueError("predicate group must contain exactly one of all, any, or not")
            return self
        if not self.op:
            raise ValueError("predicate must contain an operator or group")
        unary = {"is_null", "is_not_null", "is_missing", "is_nan", "is_zero", "is_negative"}
        if self.op in unary:
            if self.value is None or self.left is not None or self.right is not None:
                raise ValueError(f"{self.op} requires value only")
        elif self.left is None or self.right is None or self.value is not None:
            raise ValueError(f"{self.op} requires left and right")
        return self

    def children(self) -> list["Predicate"]:
        return self.all_ or self.any_ or ([self.not_] if self.not_ else [])


class Measurement(StrictModel):
    id: str = Field(min_length=1, max_length=63)
    type: Literal["metric", "violations"]
    metric: Literal[
        "row_count", "null_count", "null_rate", "distinct_count", "distinct_rate",
        "min", "max", "mean", "stddev", "sum", "freshness_seconds",
    ] | None = None
    field: str | None = Field(default=None, min_length=1, max_length=255)
    violation_when: Predicate | None = Field(default=None, alias="violationWhen")
    output: list[Literal["count", "rate"]] | None = Field(default=None, min_length=1, max_length=2)

    @model_validator(mode="after")
    def type_contract(self):
        if not _ID_RE.fullmatch(self.id):
            raise ValueError("measurement id must be lower snake_case")
        if self.type == "metric":
            if not self.metric or self.violation_when is not None or self.output is not None:
                raise ValueError("metric measurement requires metric and no violation fields")
        elif self.violation_when is None or not self.output or self.metric is not None:
            raise ValueError("violations measurement requires violationWhen and output")
        if self.output and len(set(self.output)) != len(self.output):
            raise ValueError("measurement output values must be unique")
        return self


class Target(StrictModel):
    asset_id: UUID = Field(alias="assetId")


class Trigger(StrictModel):
    type: Literal["on_profile", "manual"] = "on_profile"


class Policy(StrictModel):
    severity: Literal["P1", "P2", "P3"] = "P3"
    consecutive_breaches: int = Field(default=1, alias="consecutiveBreaches", ge=1, le=20)
    recovery_passes: int = Field(default=1, alias="recoveryPasses", ge=1, le=20)
    cooldown_minutes: int = Field(default=60, alias="cooldownMinutes", ge=0, le=43_200)
    notify_on_execution_error: bool = Field(default=True, alias="notifyOnExecutionError")


class Sampling(StrictModel):
    mode: Literal["auto", "off"] = "auto"


class Execution(StrictModel):
    timeout_seconds: int = Field(default=30, alias="timeoutSeconds", ge=1, le=120)
    max_bytes_scanned: int | None = Field(default=None, alias="maxBytesScanned", ge=1)
    max_documents_scanned: int | None = Field(default=None, alias="maxDocumentsScanned", ge=1)
    sampling: Sampling = Field(default_factory=Sampling)


class Metadata(StrictModel):
    name: str = Field(min_length=1, max_length=63)
    labels: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def metadata_bounds(self):
        if not _NAME_RE.fullmatch(self.name):
            raise ValueError("metadata.name must be lowercase kebab-case")
        if len(self.labels) > 20:
            raise ValueError("metadata.labels may contain at most 20 entries")
        if any(len(key) > 63 or len(value) > 255 for key, value in self.labels.items()):
            raise ValueError("metadata label key/value is too long")
        return self


class MonitorSpec(StrictModel):
    target: Target
    trigger: Trigger = Field(default_factory=Trigger)
    measurements: list[Measurement] = Field(min_length=1, max_length=20)
    breach_when: Predicate = Field(alias="breachWhen")
    policy: Policy = Field(default_factory=Policy)
    execution: Execution = Field(default_factory=Execution)

    @model_validator(mode="after")
    def semantic_contract(self):
        ids = [measurement.id for measurement in self.measurements]
        if len(set(ids)) != len(ids):
            raise ValueError("measurement ids must be unique")

        nodes: list[tuple[Predicate, int, bool]] = [(self.breach_when, 1, False)]
        nodes.extend(
            (measurement.violation_when, 1, True)
            for measurement in self.measurements
            if measurement.violation_when is not None
        )
        seen_nodes = 0
        references: set[str] = set()
        while nodes:
            predicate, depth, inside_measurement = nodes.pop()
            seen_nodes += 1
            if seen_nodes > MAX_PREDICATE_NODES:
                raise ValueError(f"predicate tree exceeds {MAX_PREDICATE_NODES} nodes")
            if depth > MAX_PREDICATE_DEPTH:
                raise ValueError(f"predicate tree exceeds depth {MAX_PREDICATE_DEPTH}")
            for value in (predicate.left, predicate.right, predicate.value):
                if value and value.ref:
                    if inside_measurement:
                        raise ValueError("measurement predicates cannot reference measurements")
                    references.add(value.ref)
            nodes.extend(
                (child, depth + 1, inside_measurement)
                for child in predicate.children()
            )
        declared_references = set()
        for measurement in self.measurements:
            if measurement.type == "metric":
                declared_references.add(measurement.id)
            else:
                declared_references.update(
                    f"{measurement.id}.{output}" for output in measurement.output or []
                )
        unknown = sorted(references - declared_references)
        if unknown:
            raise ValueError(f"unknown measurement reference: {unknown[0]}")
        return self


class MonitorDefinition(StrictModel):
    api_version: Literal["datawatch.io/v1alpha1"] = Field(alias="apiVersion")
    kind: Literal["Monitor"]
    metadata: Metadata
    spec: MonitorSpec

    @model_validator(mode="after")
    def definition_size(self):
        if len(canonical_json(self).encode("utf-8")) > MAX_DEFINITION_BYTES:
            raise ValueError(f"definition exceeds {MAX_DEFINITION_BYTES} bytes")
        return self


def canonical_json(definition: MonitorDefinition) -> str:
    return json.dumps(
        definition.model_dump(mode="json", by_alias=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def definition_hash(definition: MonitorDefinition) -> str:
    return hashlib.sha256(canonical_json(definition).encode("utf-8")).hexdigest()


def predicate_stats(definition: MonitorDefinition) -> dict[str, int]:
    stack = [(definition.spec.breach_when, 1)]
    stack.extend(
        (measurement.violation_when, 1)
        for measurement in definition.spec.measurements
        if measurement.violation_when is not None
    )
    count = 0
    max_depth = 0
    while stack:
        predicate, depth = stack.pop()
        count += 1
        max_depth = max(max_depth, depth)
        stack.extend((child, depth + 1) for child in predicate.children())
    return {"predicateNodes": count, "predicateDepth": max_depth}


Predicate.model_rebuild()
