"""Unit tests for AnomalyService — no DB required."""
import pytest
from unittest.mock import MagicMock
import pickle

import numpy as np


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_profile(
    row_count=500,
    freshness_seconds=3600.0,
    fingerprint="fp_a",
    column_metrics=None,
    profile_provenance=None,
):
    p = MagicMock()
    p.row_count = row_count
    p.freshness_seconds = freshness_seconds
    p.schema_fingerprint = fingerprint
    p.column_metrics = column_metrics or {"amount": {"null_rate": 0.01, "mean": 150.0, "stddev": 50.0}}
    p.profile_provenance = profile_provenance or {}
    return p


def make_table(freshness_column="created_at", interval=60, sensitivity=3.0):
    t = MagicMock()
    t.freshness_column = freshness_column
    t.check_interval_minutes = interval
    t.sensitivity = sensitivity
    return t


# ── Z-Score tests ──────────────────────────────────────────────────────────────

def test_z_score_flags_extreme_drop():
    from app.services.anomaly import run_z_score_checks
    history = [make_profile(row_count=500 + i) for i in range(15)]
    current = make_profile(row_count=0)
    results = run_z_score_checks(current, history, threshold=3.0)
    row_count_check = next((r for r in results if "row_count" in r.check_name), None)
    assert row_count_check is not None
    assert row_count_check.status == "failed"
    assert row_count_check.deviation_score is not None
    assert abs(row_count_check.deviation_score) > 3.0


def test_z_score_skips_bootstrap():
    from app.services.anomaly import run_z_score_checks
    history = [make_profile(row_count=500) for _ in range(5)]  # < 7 points
    current = make_profile(row_count=0)
    results = run_z_score_checks(current, history, threshold=3.0)
    assert results == [], "Should skip z-score with fewer than 7 history points"


def test_z_score_skips_constant():
    from app.services.anomaly import run_z_score_checks
    history = [make_profile(row_count=500) for _ in range(15)]  # all same → stddev=0
    current = make_profile(row_count=500)
    results = run_z_score_checks(current, history, threshold=3.0)
    row_check = next((r for r in results if "row_count" in r.check_name), None)
    assert row_check is None, "Should skip metric with stddev=0"


def test_z_score_passes_normal():
    from app.services.anomaly import run_z_score_checks
    import random
    random.seed(0)
    history = [make_profile(row_count=490 + random.randint(-20, 20)) for _ in range(15)]
    current = make_profile(row_count=505)  # well within range
    results = run_z_score_checks(current, history, threshold=3.0)
    row_check = next((r for r in results if "row_count" in r.check_name), None)
    assert row_check is None or row_check.status == "passed"


# ── Rule-Based tests ───────────────────────────────────────────────────────────

def test_rule_row_count_zero():
    from app.services.anomaly import run_rule_checks
    current = make_profile(row_count=0)
    table = make_table()
    results = run_rule_checks(current, None, table)
    check = next((r for r in results if r.check_name == "row_count_zero"), None)
    assert check is not None
    assert check.status == "failed"


def test_rule_row_count_nonzero_passes():
    from app.services.anomaly import run_rule_checks
    current = make_profile(row_count=500)
    results = run_rule_checks(current, None, make_table())
    check = next((r for r in results if r.check_name == "row_count_zero"), None)
    assert check is not None
    assert check.status == "passed"


def test_rule_freshness_sla_breach():
    from app.services.anomaly import run_rule_checks
    # interval=60min, SLA = 60*60*1.5 = 5400s
    current = make_profile(freshness_seconds=10000.0)
    table = make_table(freshness_column="updated_at", interval=60)
    results = run_rule_checks(current, None, table)
    check = next((r for r in results if r.check_name == "freshness_sla_breach"), None)
    assert check is not None
    assert check.status == "failed"


def test_rule_schema_drift():
    from app.services.anomaly import run_rule_checks
    current = make_profile(fingerprint="fp_new")
    prev = make_profile(fingerprint="fp_old")
    results = run_rule_checks(current, prev, make_table())
    check = next((r for r in results if r.check_name == "schema_drift"), None)
    assert check is not None
    assert check.status == "failed"


def test_estimated_counts_do_not_trigger_exact_zero_or_growth_rules():
    from app.services.anomaly import run_row_growth_check, run_rule_checks

    provenance = {"count_mode": "estimated", "schema_mode": "sampled"}
    current = make_profile(row_count=0, profile_provenance=provenance)
    history = [
        make_profile(row_count=100 + i, profile_provenance=provenance)
        for i in range(10)
    ]

    rules = run_rule_checks(current, history[-1], make_table())
    assert all(result.check_name != "row_count_zero" for result in rules)
    assert run_row_growth_check(current, history) == []


def test_sampled_schema_fingerprint_does_not_open_one_run_drift():
    from app.services.anomaly import run_rule_checks, run_schema_change_check

    provenance = {"count_mode": "estimated", "schema_mode": "sampled"}
    current = make_profile(fingerprint="sample-new", profile_provenance=provenance)
    previous = make_profile(fingerprint="sample-old", profile_provenance=provenance)

    results = run_rule_checks(current, previous, make_table())

    assert all(result.check_name != "schema_drift" for result in results)
    assert run_schema_change_check(current, [previous]) == []


def test_rule_null_rate_spike():
    from app.services.anomaly import run_rule_checks
    current = make_profile(column_metrics={"amount": {"null_rate": 0.45}})
    prev = make_profile(column_metrics={"amount": {"null_rate": 0.01}})
    results = run_rule_checks(current, prev, make_table())
    check = next((r for r in results if r.check_name == "null_rate_spike"), None)
    assert check is not None
    assert check.status == "failed"
    assert check.deviation_score > 0.20


# ── Additional anomaly checks ──────────────────────────────────────────────────

def test_distribution_drift_flags_current_mean_outlier():
    from app.services.anomaly import run_distribution_drift_check

    history = [
        make_profile(column_metrics={"amount": {"mean": 100 + i, "stddev": 10}})
        for i in range(10)
    ]
    current = make_profile(column_metrics={"amount": {"mean": 150, "stddev": 10}})

    results = run_distribution_drift_check(current, history)
    check = next((r for r in results if r.check_name == "distribution_drift_mean"), None)

    assert check is not None
    assert check.column_name == "amount"
    assert check.check_type == "z_score"
    assert check.status == "failed"
    assert check.deviation_score is not None
    assert abs(check.deviation_score) > 3.0


def test_null_rate_trend_flags_monotonic_increase():
    from app.services.anomaly import run_null_rate_trend_check

    history = [
        make_profile(column_metrics={"email": {"null_rate": rate}})
        for rate in [0.01, 0.02, 0.03, 0.04, 0.05]
    ]
    current = make_profile(column_metrics={"email": {"null_rate": 0.06}})

    results = run_null_rate_trend_check(current, history)
    check = next((r for r in results if r.check_name == "null_rate_trending"), None)

    assert check is not None
    assert check.column_name == "email"
    assert check.check_type == "rule"
    assert check.status == "failed"
    assert check.deviation_score is not None
    assert check.deviation_score > 0


def test_freshness_check_reports_stale_and_sla_breach():
    from app.services.anomaly import run_freshness_check

    current = make_profile(freshness_seconds=7500.0)
    table = make_table(freshness_column="updated_at", interval=60)

    results = run_freshness_check(current, table)
    stale = next((r for r in results if r.check_name == "freshness_stale"), None)
    sla = next((r for r in results if r.check_name == "freshness_sla_breach"), None)

    assert stale is not None
    assert stale.status == "failed"
    assert stale.observed_value == 7500.0
    assert stale.expected_range == {"low": 0, "high": 3600}
    assert sla is not None
    assert sla.status == "failed"
    assert sla.expected_range == {"low": 0, "high": 7200}


def test_schema_change_check_reports_fingerprint_and_column_count_changes():
    from app.services.anomaly import run_schema_change_check

    prev = make_profile(
        fingerprint="fp_old",
        column_metrics={"id": {"null_rate": 0}, "amount": {"mean": 10, "stddev": 1}},
    )
    current = make_profile(
        fingerprint="fp_new",
        column_metrics={
            "id": {"null_rate": 0},
            "amount": {"mean": 10, "stddev": 1},
            "status": {"null_rate": 0},
        },
    )

    results = run_schema_change_check(current, [prev])
    drift = next((r for r in results if r.check_name == "schema_drift"), None)
    count = next((r for r in results if r.check_name == "schema_column_count_change"), None)

    assert drift is not None
    assert drift.status == "failed"
    assert drift.observed_value is None
    assert drift.expected_range == {"previous": "fp_old", "current": "fp_new"}
    assert count is not None
    assert count.status == "failed"
    assert count.observed_value == 3.0
    assert count.expected_range == {"previous": 2, "current": 3}


def test_isolation_forest_retrains_cached_model_on_feature_mismatch():
    from sklearn.ensemble import IsolationForest

    from app.services.anomaly import run_isolation_forest

    table_id = "orders"
    history = [
        make_profile(
            row_count=500 + i,
            freshness_seconds=3600.0 + i,
            column_metrics={"amount": {"mean": 100.0 + i}},
        )
        for i in range(21)
    ]
    current = make_profile(
        row_count=540,
        freshness_seconds=3610.0,
        column_metrics={"amount": {"mean": 120.0}},
    )
    stale_model = IsolationForest(contamination=0.05, random_state=42)
    stale_model.fit(np.array([[float(i)] for i in range(21)]))

    class FakeRedis:
        def __init__(self):
            self.deleted_keys = []
            self.set_keys = []

        def get(self, key):
            return pickle.dumps(stale_model)

        def delete(self, key):
            self.deleted_keys.append(key)

        def setex(self, key, ttl, value):
            self.set_keys.append(key)

    redis_client = FakeRedis()

    results = run_isolation_forest(current, history, table_id, redis_client)

    assert len(results) == 1
    assert redis_client.deleted_keys == [f"isoforest:{table_id}:3"]
    assert redis_client.set_keys == [f"isoforest:{table_id}:3"]


def test_sampled_native_profiles_only_expose_freshness_to_metric_detectors():
    from app.services.anomaly import _extract_flat_metrics, run_rule_checks

    provenance = {
        "profile_mode": "sampled_native",
        "count_mode": "estimated",
        "schema_mode": "sampled",
    }
    previous = make_profile(
        row_count=1000,
        freshness_seconds=60,
        column_metrics={"amount": {"null_rate": 0.0, "numeric_mean": 10}},
        profile_provenance=provenance,
    )
    current = make_profile(
        row_count=10,
        freshness_seconds=120,
        column_metrics={"amount": {"null_rate": 0.9, "numeric_mean": 1000}},
        profile_provenance=provenance,
    )

    assert _extract_flat_metrics(current) == {"freshness_seconds": 120.0}
    checks = run_rule_checks(current, previous, make_table())
    assert {check.check_name for check in checks} == {"freshness_sla_breach"}


# ── IncidentService tests ──────────────────────────────────────────────────────

def test_severity_p1_row_count_zero():
    from app.services.anomaly import AnomalyResult
    from app.services.incident import classify_severity
    checks = [AnomalyResult("rule", "row_count_zero", None, "failed", 0, None, None)]
    assert classify_severity(checks) == "P1"


def test_severity_p2_schema_drift():
    from app.services.anomaly import AnomalyResult
    from app.services.incident import classify_severity
    checks = [AnomalyResult("rule", "schema_drift", None, "failed", None, None, None)]
    assert classify_severity(checks) == "P2"


def test_severity_p2_three_failures():
    from app.services.anomaly import AnomalyResult
    from app.services.incident import classify_severity
    checks = [AnomalyResult("z_score", f"z_score_metric_{i}", None, "failed", 0, None, 4.0) for i in range(3)]
    assert classify_severity(checks) == "P2"


def test_severity_p3_one_failure():
    from app.services.anomaly import AnomalyResult
    from app.services.incident import classify_severity
    checks = [AnomalyResult("z_score", "z_score_row_count", None, "failed", 0, None, 3.5)]
    assert classify_severity(checks) == "P3"


def test_dsl_monitor_failure_uses_policy_severity_and_title():
    from app.services.anomaly import AnomalyResult
    from app.services.incident import classify_severity, generate_title

    checks = [
        AnomalyResult(
            "monitor_dsl",
            "dsl_monitor:orders-valid",
            None,
            "failed",
            None,
            None,
            None,
            details={"severity": "P1"},
        )
    ]
    assert classify_severity(checks) == "P1"
    assert generate_title("orders", checks) == "[P1] orders — custom monitor failed: orders-valid"
