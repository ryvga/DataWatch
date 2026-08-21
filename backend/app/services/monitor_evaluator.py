"""Deterministic, side-effect-free evaluation for compiled monitor measurements."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.services.monitor_dsl import Policy, Predicate, ValueExpression


class MonitorEvaluationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class TruthValue(StrEnum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PolicyState:
    phase: str = "healthy"
    breach_streak: int = 0
    recovery_streak: int = 0
    cooldown_until: datetime | None = None


@dataclass(frozen=True)
class PolicyDecision:
    breached: bool
    run_status: str
    phase: str
    transition: str
    incident_action: str
    breach_streak: int
    recovery_streak: int
    notification_eligible: bool
    cooldown_until: datetime | None

    def payload(self) -> dict[str, Any]:
        return {
            "version": "monitor-evaluation/v1",
            "rawState": "breached" if self.breached else "clear",
            "runStatus": self.run_status,
            "effectiveState": self.phase,
            "transition": self.transition,
            "incidentAction": self.incident_action,
            "breachStreak": self.breach_streak,
            "recoveryStreak": self.recovery_streak,
            "notificationEligible": self.notification_eligible,
            "cooldownUntil": self.cooldown_until.isoformat() if self.cooldown_until else None,
        }


def _value(expression: ValueExpression | None, measurements: dict[str, Any]) -> Any:
    if expression is None:
        raise MonitorEvaluationError("evaluation_operand_invalid", "Predicate operand is missing")
    if expression.ref is not None:
        if expression.ref not in measurements:
            raise MonitorEvaluationError("measurement_missing", f"Required measurement is missing: {expression.ref}")
        return measurements[expression.ref]
    if "literal" in expression.model_fields_set:
        return expression.literal
    raise MonitorEvaluationError("evaluation_operand_invalid", "Breach predicates may use only references and literals")


def _number(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MonitorEvaluationError("evaluation_type_invalid", "Breach predicate requires numeric operands")
    if not math.isfinite(value):
        raise MonitorEvaluationError("evaluation_not_finite", "Breach predicate operands must be finite")
    return Decimal(str(value))


def _truth(value: bool) -> TruthValue:
    return TruthValue.TRUE if value else TruthValue.FALSE


def _has_ref(predicate: Predicate) -> bool:
    if any(value and value.ref for value in (predicate.left, predicate.right, predicate.value)):
        return True
    return any(_has_ref(child) for child in predicate.children())


def _evaluate(predicate: Predicate, measurements: dict[str, Any]) -> TruthValue:
    if predicate.all_ is not None:
        values = [_evaluate(child, measurements) for child in predicate.all_]
        if TruthValue.FALSE in values:
            return TruthValue.FALSE
        return TruthValue.UNKNOWN if TruthValue.UNKNOWN in values else TruthValue.TRUE
    if predicate.any_ is not None:
        values = [_evaluate(child, measurements) for child in predicate.any_]
        if TruthValue.TRUE in values:
            return TruthValue.TRUE
        return TruthValue.UNKNOWN if TruthValue.UNKNOWN in values else TruthValue.FALSE
    if predicate.not_ is not None:
        value = _evaluate(predicate.not_, measurements)
        return value if value is TruthValue.UNKNOWN else _truth(value is TruthValue.FALSE)

    op = predicate.op
    if op in {"is_null", "is_not_null"}:
        value = _value(predicate.value, measurements)
        return _truth(value is None if op == "is_null" else value is not None)
    if op in {"is_zero", "is_negative"}:
        value = _value(predicate.value, measurements)
        if value is None:
            return TruthValue.UNKNOWN
        number = _number(value)
        return _truth(number == 0 if op == "is_zero" else number < 0)
    if op in {"is_missing", "is_nan", "contains", "starts_with", "ends_with"}:
        raise MonitorEvaluationError("evaluation_operator_not_supported", f"Unsupported output operator: {op}")

    left_value = _value(predicate.left, measurements)
    right_value = _value(predicate.right, measurements)
    if left_value is None or right_value is None:
        return TruthValue.UNKNOWN
    left = _number(left_value)
    if op in {"between", "not_between"}:
        lower, upper = (_number(value) for value in right_value)
        result = lower <= left <= upper
        return _truth(not result if op == "not_between" else result)
    if op in {"in", "not_in"}:
        included = left in [_number(value) for value in right_value]
        return _truth(included if op == "in" else not included)
    right = _number(right_value)
    comparisons = {"eq": left == right, "ne": left != right, "gt": left > right, "gte": left >= right, "lt": left < right, "lte": left <= right}
    if op not in comparisons:
        raise MonitorEvaluationError("evaluation_operator_not_supported", f"Unsupported breach operator: {op}")
    return _truth(comparisons[op])


def evaluate_breach(predicate: Predicate, measurements: dict[str, Any]) -> bool:
    if not _has_ref(predicate):
        raise MonitorEvaluationError("measurement_reference_required", "Breach predicate must reference a measurement")
    result = _evaluate(predicate, measurements)
    if result is TruthValue.UNKNOWN:
        raise MonitorEvaluationError("evaluation_unknown", "Breach predicate result is unknown")
    return result is TruthValue.TRUE


def evaluate_policy(*, breached: bool, policy: Policy, previous: PolicyState | None = None, evaluated_at: datetime | None = None) -> PolicyDecision:
    previous = previous or PolicyState()
    now = evaluated_at or datetime.now(UTC)
    if now.tzinfo is None:
        raise MonitorEvaluationError("evaluation_time_invalid", "Policy time must be timezone-aware")
    if previous.phase not in {"healthy", "breached"} or previous.breach_streak < 0 or previous.recovery_streak < 0:
        raise MonitorEvaluationError("policy_state_invalid", "Previous policy state is invalid")
    if previous.cooldown_until is not None and previous.cooldown_until.tzinfo is None:
        raise MonitorEvaluationError("policy_state_invalid", "Cooldown time must be timezone-aware")

    phase = previous.phase
    transition = "none"
    incident_action = "none"
    notification = False
    cooldown_until = previous.cooldown_until
    if breached:
        recovery_streak = 0
        breach_streak = previous.breach_streak + 1 if phase == "healthy" else 0
        if phase == "healthy":
            if breach_streak >= policy.consecutive_breaches:
                phase, transition, incident_action, notification = "breached", "opened", "open", True
                cooldown_until = now + timedelta(minutes=policy.cooldown_minutes)
            else:
                transition = "breach_pending"
        elif cooldown_until is None or now >= cooldown_until:
            transition, notification = "reminder_due", True
            cooldown_until = now + timedelta(minutes=policy.cooldown_minutes)
        else:
            transition = "ongoing"
    else:
        breach_streak = 0
        recovery_streak = previous.recovery_streak + 1 if phase == "breached" else 0
        if phase == "breached":
            if recovery_streak >= policy.recovery_passes:
                phase, transition, incident_action = "healthy", "recovered", "resolve"
                recovery_streak, cooldown_until = 0, None
            else:
                transition = "recovery_pending"

    if policy.mode == "track":
        incident_action = "none"
        notification = False
    return PolicyDecision(breached, "failed" if breached else "passed", phase, transition, incident_action, breach_streak, recovery_streak, notification, cooldown_until)
