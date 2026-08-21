"""Connector-aware dispatcher for immutable typed monitor plans."""

from __future__ import annotations

from typing import Any, TypeAlias

from app.services.cassandra_monitor import (
    CassandraMonitorPlan,
    analyze_cassandra_support,
    compile_cassandra_plan,
)
from app.services.document_monitor import (
    DocumentMonitorPlan,
    analyze_document_support,
    compile_document_plan,
)
from app.services.monitor_compiler import (
    RelationalMonitorPlan,
    analyze_relational_support,
    compile_relational_plan,
)
from app.services.monitor_dsl import MonitorDefinition
from app.services.schema_binding import RelationBinding

MonitorPlan: TypeAlias = RelationalMonitorPlan | DocumentMonitorPlan | CassandraMonitorPlan


def compile_monitor_plan(
    definition: MonitorDefinition,
    *,
    relation: RelationBinding,
    ddl: str | None = None,
) -> MonitorPlan:
    if relation.source_type == "mongodb":
        return compile_document_plan(definition, relation=relation)
    if relation.source_type == "cassandra":
        return compile_cassandra_plan(definition, relation=relation, ddl=ddl or "")
    return compile_relational_plan(definition, relation=relation)


def analyze_monitor_support(
    definition: MonitorDefinition,
    *,
    relation: RelationBinding,
    ddl: str | None = None,
) -> tuple[dict[str, Any], MonitorPlan | None]:
    if relation.source_type == "mongodb":
        return analyze_document_support(definition, relation=relation)
    if relation.source_type == "cassandra":
        return analyze_cassandra_support(definition, relation=relation, ddl=ddl or "")
    return analyze_relational_support(definition, relation=relation)
