from datetime import UTC, datetime, timedelta

import pytest

from app.services.monitor_dsl import MonitorDefinition, Policy, Predicate
from app.services.monitor_evaluator import (
    MonitorEvaluationError,
    PolicyState,
    evaluate_breach,
    evaluate_policy,
)
from tests.test_monitor_dsl import valid_definition


def _breach(body=None) -> Predicate:
    if body is None:
        return MonitorDefinition.model_validate(valid_definition()).spec.breach_when
    return Predicate.model_validate(body)


def test_breach_evaluator_resolves_nested_numeric_measurement_predicates():
    predicate = _breach(
        {
            "all": [
                {"op": "gte", "left": {"ref": "rate"}, "right": {"literal": 0.1}},
                {
                    "any": [
                        {"op": "gt", "left": {"ref": "count"}, "right": {"literal": 2}},
                        {"not": {"op": "is_zero", "value": {"ref": "count"}}},
                    ]
                },
            ]
        }
    )

    assert evaluate_breach(predicate, {"rate": 0.2, "count": 1}) is True
    assert evaluate_breach(predicate, {"rate": 0.01, "count": 10}) is False


@pytest.mark.parametrize(
    ("body", "measurements", "expected"),
    [
        ({"op": "between", "left": {"ref": "v"}, "right": {"literal": [1, 3]}}, {"v": 2}, True),
        ({"op": "in", "left": {"ref": "v"}, "right": {"literal": [1, 3]}}, {"v": 2}, False),
        ({"op": "not_in", "left": {"ref": "v"}, "right": {"literal": [1, 3]}}, {"v": 2}, True),
        ({"op": "is_null", "value": {"ref": "v"}}, {"v": None}, True),
        ({"op": "is_not_null", "value": {"ref": "v"}}, {"v": 0}, True),
        ({"op": "is_negative", "value": {"ref": "v"}}, {"v": -1}, True),
    ],
)
def test_breach_evaluator_supports_bounded_output_operators(body, measurements, expected):
    assert evaluate_breach(_breach(body), measurements) is expected


@pytest.mark.parametrize(
    ("body", "measurements", "code"),
    [
        ({"op": "gt", "left": {"ref": "missing"}, "right": {"literal": 1}}, {}, "measurement_missing"),
        ({"op": "eq", "left": {"ref": "v"}, "right": {"literal": 1}}, {"v": True}, "evaluation_type_invalid"),
        ({"op": "eq", "left": {"ref": "v"}, "right": {"literal": 1}}, {"v": None}, "evaluation_unknown"),
        ({"op": "is_nan", "value": {"ref": "v"}}, {"v": 1}, "evaluation_operator_not_supported"),
    ],
)
def test_breach_evaluator_fails_closed_without_coercion(body, measurements, code):
    with pytest.raises(MonitorEvaluationError) as exc:
        evaluate_breach(_breach(body), measurements)
    assert exc.value.code == code


def test_policy_requires_consecutive_breaches_and_recovery_passes():
    policy = Policy(consecutiveBreaches=2, recoveryPasses=2, cooldownMinutes=60)
    now = datetime(2026, 7, 19, 20, 0, tzinfo=UTC)

    first = evaluate_policy(breached=True, policy=policy, evaluated_at=now)
    assert first.phase == "healthy"
    assert first.breach_streak == 1
    assert first.transition == "breach_pending"

    opened = evaluate_policy(
        breached=True,
        policy=policy,
        previous=PolicyState(
            phase=first.phase,
            breach_streak=first.breach_streak,
        ),
        evaluated_at=now + timedelta(minutes=1),
    )
    assert opened.phase == "breached"
    assert opened.transition == "opened"
    assert opened.notification_eligible is True

    pending = evaluate_policy(
        breached=False,
        policy=policy,
        previous=PolicyState(
            phase="breached",
            breach_streak=opened.breach_streak,
            cooldown_until=opened.cooldown_until,
        ),
        evaluated_at=now + timedelta(minutes=2),
    )
    assert pending.phase == "breached"
    assert pending.recovery_streak == 1

    recovered = evaluate_policy(
        breached=False,
        policy=policy,
        previous=PolicyState(
            phase="breached",
            recovery_streak=pending.recovery_streak,
            cooldown_until=pending.cooldown_until,
        ),
        evaluated_at=now + timedelta(minutes=3),
    )
    assert recovered.phase == "healthy"
    assert recovered.transition == "recovered"


def test_three_valued_groups_only_error_when_root_remains_unknown():
    false_and_unknown = _breach(
        {"all": [
            {"op": "gt", "left": {"ref": "known"}, "right": {"literal": 1}},
            {"op": "gt", "left": {"ref": "nullable"}, "right": {"literal": 1}},
        ]}
    )
    true_or_unknown = _breach(
        {"any": [
            {"op": "gt", "left": {"ref": "known"}, "right": {"literal": 1}},
            {"op": "gt", "left": {"ref": "nullable"}, "right": {"literal": 1}},
        ]}
    )

    assert evaluate_breach(false_and_unknown, {"known": 0, "nullable": None}) is False
    assert evaluate_breach(true_or_unknown, {"known": 2, "nullable": None}) is True


def test_policy_cooldown_suppresses_ongoing_notification_without_closing_alert():
    policy = Policy(consecutiveBreaches=1, recoveryPasses=1, cooldownMinutes=60)
    now = datetime(2026, 7, 19, 20, 0, tzinfo=UTC)
    decision = evaluate_policy(
        breached=True,
        policy=policy,
        previous=PolicyState(
            phase="breached",
            cooldown_until=now + timedelta(minutes=30),
        ),
        evaluated_at=now,
    )

    assert decision.phase == "breached"
    assert decision.transition == "ongoing"
    assert decision.notification_eligible is False
    assert decision.cooldown_until == now + timedelta(minutes=30)


def test_policy_payload_is_stable_json_shape():
    now = datetime(2026, 7, 19, 20, 0, tzinfo=UTC)
    payload = evaluate_policy(
        breached=True,
        policy=Policy(consecutiveBreaches=1),
        evaluated_at=now,
    ).payload()
    assert payload == {
        "version": "monitor-evaluation/v1",
        "rawState": "breached",
        "runStatus": "failed",
        "effectiveState": "breached",
        "transition": "opened",
        "incidentAction": "open",
        "breachStreak": 1,
        "recoveryStreak": 0,
        "notificationEligible": True,
        "cooldownUntil": "2026-07-19T21:00:00+00:00",
    }


def test_closed_policy_does_not_accumulate_irrelevant_recovery_streak():
    decision = evaluate_policy(
        breached=False,
        policy=Policy(recoveryPasses=3),
        previous=PolicyState(phase="healthy", recovery_streak=20),
    )
    assert decision.phase == "healthy"
    assert decision.recovery_streak == 0


@pytest.mark.parametrize(
    "state",
    [
        PolicyState(phase="unknown"),
        PolicyState(breach_streak=-1),
        PolicyState(cooldown_until=datetime(2026, 7, 19, 20, 0)),
    ],
)
def test_policy_rejects_corrupted_previous_state(state):
    with pytest.raises(MonitorEvaluationError) as exc:
        evaluate_policy(breached=True, policy=Policy(), previous=state)
    assert exc.value.code == "policy_state_invalid"
