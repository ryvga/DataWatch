"""Unit tests for AnomalyService — no DB required."""
import pytest
from unittest.mock import MagicMock


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_profile(row_count=500, freshness_seconds=3600.0, fingerprint="fp_a", column_metrics=None):
    p = MagicMock()
    p.row_count = row_count
    p.freshness_seconds = freshness_seconds
    p.schema_fingerprint = fingerprint
    p.column_metrics = column_metrics or {"amount": {"null_rate": 0.01, "mean": 150.0, "stddev": 50.0}}
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


def test_rule_null_rate_spike():
    from app.services.anomaly import run_rule_checks
    current = make_profile(column_metrics={"amount": {"null_rate": 0.45}})
    prev = make_profile(column_metrics={"amount": {"null_rate": 0.01}})
    results = run_rule_checks(current, prev, make_table())
    check = next((r for r in results if r.check_name == "null_rate_spike"), None)
    assert check is not None
    assert check.status == "failed"
    assert check.deviation_score > 0.20


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
