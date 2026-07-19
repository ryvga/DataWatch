"""Fail-closed execution contract for internally compiled monitor plans."""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from sqlglot import exp, parse

from app.connectors.base import BaseConnector
from app.services.monitor_compiler import RelationalMonitorPlan
from app.services.monitor_dsl import Policy, Predicate
from app.services.monitor_evaluator import (
    PolicyState,
    evaluate_breach,
    evaluate_policy,
)


class MonitorExecutionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _finite_number(value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise MonitorExecutionError(
            "result_type_invalid",
            "Compiled monitor outputs must be numeric or null",
        )
    numeric = float(value)
    if not math.isfinite(numeric):
        raise MonitorExecutionError(
            "result_not_finite",
            "Compiled monitor outputs must be finite",
        )
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    return numeric


def _validate_execution_plan(
    connector: BaseConnector,
    plan: RelationalMonitorPlan,
) -> None:
    """Re-check the execution envelope independently from compilation."""
    if connector.profile_dialect != plan.dialect:
        raise MonitorExecutionError(
            "connector_plan_mismatch",
            "Compiled monitor dialect does not match the connector",
        )
    if not 1 <= plan.timeout_seconds <= 120:
        raise MonitorExecutionError(
            "execution_contract_invalid",
            "Compiled monitor timeout is outside the supported bounds",
        )
    try:
        statements = parse(plan.statement, dialect=plan.dialect)
    except Exception as exc:
        raise MonitorExecutionError(
            "statement_invalid",
            "Compiled monitor statement could not be parsed",
        ) from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise MonitorExecutionError(
            "statement_not_read_only",
            "Compiled monitor execution requires exactly one SELECT statement",
        )
    if any(
        isinstance(node, (exp.DDL, exp.DML))
        for node in statements[0].walk()
    ):
        raise MonitorExecutionError(
            "statement_not_read_only",
            "Compiled monitor statement contains a write operation",
        )

    tables = list(statements[0].find_all(exp.Table))
    if len(tables) != 1 or (
        tables[0].name != plan.relation.table_name
        or tables[0].db != plan.relation.schema_name
    ):
        raise MonitorExecutionError(
            "relation_contract_invalid",
            "Compiled monitor statement is not bound to its declared relation",
        )

    expected_parameters = [parameter.name for parameter in plan.parameters]
    if len(expected_parameters) != len(set(expected_parameters)):
        raise MonitorExecutionError(
            "parameter_contract_invalid",
            "Compiled monitor parameter names must be unique",
        )
    placeholders = list(
        dict.fromkeys(
            placeholder.name
            for placeholder in statements[0].find_all(exp.Placeholder)
        )
    )
    if placeholders != expected_parameters:
        raise MonitorExecutionError(
            "parameter_contract_invalid",
            "Compiled monitor placeholders do not match its bound parameters",
        )

    output_columns = [output.column for output in plan.outputs]
    output_references = [output.reference for output in plan.outputs]
    if (
        not output_columns
        or len(output_columns) != len(set(output_columns))
        or len(output_references) != len(set(output_references))
        or [projection.alias for projection in statements[0].expressions]
        != output_columns
    ):
        raise MonitorExecutionError(
            "result_contract_invalid",
            "Compiled monitor output columns must be present and unique",
        )


async def execute_compiled_plan(
    connector: BaseConnector,
    plan: RelationalMonitorPlan,
) -> dict:
    """Execute a trusted plan and map physical columns to logical references."""
    _validate_execution_plan(connector, plan)
    parameters = {parameter.name: parameter.value for parameter in plan.parameters}
    try:
        row = await connector.execute_compiled_monitor(
            plan.statement,
            parameters,
            timeout_seconds=plan.timeout_seconds,
        )
    except TimeoutError as exc:
        raise MonitorExecutionError(
            "execution_timeout",
            "Compiled monitor exceeded its timeout",
        ) from exc
    except NotImplementedError as exc:
        raise MonitorExecutionError(
            "connector_execution_not_supported",
            "Connector has no compiled monitor execution adapter",
        ) from exc
    except Exception as exc:
        raise MonitorExecutionError(
            "execution_failed",
            f"Compiled monitor execution failed: {type(exc).__name__}",
        ) from exc

    expected = [output.column for output in plan.outputs]
    if list(row) != expected:
        raise MonitorExecutionError(
            "result_shape_invalid",
            "Compiled monitor returned unexpected result columns",
        )
    measurements = {}
    for output in plan.outputs:
        value = row[output.column]
        if value is None and not output.nullable:
            raise MonitorExecutionError(
                "result_null_invalid",
                f"Compiled monitor output cannot be null: {output.reference}",
            )
        measurements[output.reference] = None if value is None else _finite_number(value)
    return measurements


async def execute_and_evaluate_compiled_plan(
    connector: BaseConnector,
    plan: RelationalMonitorPlan,
    *,
    previous_policy_state: PolicyState | None = None,
) -> dict:
    """Execute one internal plan and return its deterministic policy decision."""
    measurements = await execute_compiled_plan(connector, plan)
    breach_when = Predicate.model_validate(plan.breach_when)
    policy = Policy.model_validate(plan.policy)
    breached = evaluate_breach(breach_when, measurements)
    decision = evaluate_policy(
        breached=breached,
        policy=policy,
        previous=previous_policy_state,
    )
    return {
        "measurements": measurements,
        "decision": decision.payload(),
    }
