"""
AnomalyService — four detection methods:
  1. Z-Score (rolling 14-day window, per-metric)
  2. Rule-Based (always-on: row_count=0, freshness SLA, schema drift, null spike)
  3. Isolation Forest (multivariate, 30-day window, Redis-cached model)
  4. STL Seasonal Decomposition (≥21 days of row_count history)
"""
import logging
import pickle
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

Z_SCORE_MIN_POINTS = 7
Z_SCORE_WINDOW = 14
ISO_FOREST_MIN_POINTS = 21
STL_MIN_POINTS = 21
NULL_SPIKE_THRESHOLD = 0.20     # 20pp change flags
ISO_ANOMALY_THRESHOLD = -0.1    # decision_function score


@dataclass
class AnomalyResult:
    check_type: str           # z_score | rule | isoforest | stl
    check_name: str
    column_name: str | None
    status: str               # passed | failed
    observed_value: float | None
    expected_range: dict | None   # {"low": x, "high": y}
    deviation_score: float | None
    details: dict | None = None


# ── Metric extraction helpers ─────────────────────────────────────────────────

def _extract_flat_metrics(profile) -> dict[str, float]:
    """Flatten a TableProfile into a {metric_key: value} dict for Z-score / IsoForest."""
    flat: dict[str, float] = {}
    if profile.row_count is not None:
        flat["row_count"] = float(profile.row_count)
    if profile.freshness_seconds is not None:
        flat["freshness_seconds"] = float(profile.freshness_seconds)

    if profile.column_metrics:
        for col_name, metrics in profile.column_metrics.items():
            if not isinstance(metrics, dict):
                continue
            for metric_name, val in metrics.items():
                if val is not None:
                    try:
                        flat[f"{metric_name}__{col_name}"] = float(val)
                    except (TypeError, ValueError):
                        pass
    return flat


# ── 1. Z-Score ────────────────────────────────────────────────────────────────

def run_z_score_checks(
    current_profile,
    history: list,          # list of TableProfile, oldest first
    threshold: float,
) -> list[AnomalyResult]:
    results: list[AnomalyResult] = []

    current_metrics = _extract_flat_metrics(current_profile)
    history_metrics = [_extract_flat_metrics(p) for p in history]

    for metric_key, current_val in current_metrics.items():
        # Build rolling window (last Z_SCORE_WINDOW points)
        window = [h[metric_key] for h in history_metrics if metric_key in h]
        window = window[-Z_SCORE_WINDOW:]

        if len(window) < Z_SCORE_MIN_POINTS:
            continue  # bootstrap period

        arr = np.array(window, dtype=float)
        mean = float(np.mean(arr))
        std = float(np.std(arr))

        if std == 0:
            continue  # constant metric, skip

        z = (current_val - mean) / std
        abs_z = abs(z)

        low = mean - threshold * std
        high = mean + threshold * std

        col_name = None
        display_name = metric_key
        if "__" in metric_key:
            metric_part, col_name = metric_key.split("__", 1)
            display_name = f"{metric_part}[{col_name}]"

        results.append(AnomalyResult(
            check_type="z_score",
            check_name=f"z_score_{display_name}",
            column_name=col_name,
            status="failed" if abs_z > threshold else "passed",
            observed_value=current_val,
            expected_range={"low": round(low, 4), "high": round(high, 4)},
            deviation_score=round(z, 4),
        ))

    return results


# ── 2. Rule-Based Checks ──────────────────────────────────────────────────────

def run_rule_checks(
    current_profile,
    prev_profile,           # may be None on first run
    table,                  # MonitoredTable ORM object
) -> list[AnomalyResult]:
    results: list[AnomalyResult] = []

    # Row count = 0
    if current_profile.row_count is not None:
        failed = current_profile.row_count == 0
        results.append(AnomalyResult(
            check_type="rule",
            check_name="row_count_zero",
            column_name=None,
            status="failed" if failed else "passed",
            observed_value=float(current_profile.row_count),
            expected_range={"low": 1, "high": None},
            deviation_score=None,
        ))

    # Freshness SLA (SLA = check_interval_minutes * 60 * 1.5 grace)
    if current_profile.freshness_seconds is not None and table.freshness_column:
        sla_seconds = table.check_interval_minutes * 60 * 1.5
        failed = current_profile.freshness_seconds > sla_seconds
        results.append(AnomalyResult(
            check_type="rule",
            check_name="freshness_sla_breach",
            column_name=table.freshness_column,
            status="failed" if failed else "passed",
            observed_value=round(current_profile.freshness_seconds, 1),
            expected_range={"low": 0, "high": sla_seconds},
            deviation_score=None,
        ))

    # Schema drift
    if prev_profile and current_profile.schema_fingerprint:
        drifted = current_profile.schema_fingerprint != prev_profile.schema_fingerprint
        results.append(AnomalyResult(
            check_type="rule",
            check_name="schema_drift",
            column_name=None,
            status="failed" if drifted else "passed",
            observed_value=None,
            expected_range=None,
            deviation_score=None,
        ))

    # Null rate spike (>20pp change per column)
    if prev_profile and current_profile.column_metrics and prev_profile.column_metrics:
        for col_name, metrics in current_profile.column_metrics.items():
            if not isinstance(metrics, dict):
                continue
            curr_null = metrics.get("null_rate")
            prev_metrics = prev_profile.column_metrics.get(col_name, {})
            prev_null = prev_metrics.get("null_rate") if isinstance(prev_metrics, dict) else None

            if curr_null is not None and prev_null is not None:
                delta = abs(float(curr_null) - float(prev_null))
                results.append(AnomalyResult(
                    check_type="rule",
                    check_name="null_rate_spike",
                    column_name=col_name,
                    status="failed" if delta > NULL_SPIKE_THRESHOLD else "passed",
                    observed_value=round(float(curr_null), 4),
                    expected_range={
                        "low": max(0.0, round(float(prev_null) - NULL_SPIKE_THRESHOLD, 4)),
                        "high": min(1.0, round(float(prev_null) + NULL_SPIKE_THRESHOLD, 4)),
                    },
                    deviation_score=round(delta, 4),
                ))

    return results


# ── 3. Isolation Forest ───────────────────────────────────────────────────────

def run_isolation_forest(
    current_profile,
    history: list,
    table_id: str,
    redis_client=None,
) -> list[AnomalyResult]:
    if len(history) < ISO_FOREST_MIN_POINTS:
        return []

    try:
        from sklearn.ensemble import IsolationForest

        # Build feature matrix from history
        all_metrics = [_extract_flat_metrics(p) for p in history]
        current_metrics = _extract_flat_metrics(current_profile)

        # Use shared keys only
        all_keys = sorted(set(current_metrics.keys()) & set().union(*[m.keys() for m in all_metrics]))
        if not all_keys:
            return []

        def _vec(m: dict) -> list:
            return [m.get(k, 0.0) for k in all_keys]

        X = np.array([_vec(m) for m in all_metrics[-30:]])
        x_curr = np.array([_vec(current_metrics)])

        # Try to load cached model
        model = None
        model_key = f"isoforest:{table_id}"
        if redis_client:
            try:
                cached = redis_client.get(model_key)
                if cached:
                    model = pickle.loads(cached)
            except Exception:
                pass

        if model is None:
            model = IsolationForest(contamination=0.05, random_state=42)
            model.fit(X)
            if redis_client:
                try:
                    redis_client.setex(model_key, 7 * 24 * 3600, pickle.dumps(model))
                except Exception:
                    pass

        score = float(model.decision_function(x_curr)[0])
        failed = score < ISO_ANOMALY_THRESHOLD

        return [AnomalyResult(
            check_type="isoforest",
            check_name="isolation_forest_multivariate",
            column_name=None,
            status="failed" if failed else "passed",
            observed_value=round(score, 4),
            expected_range={"low": ISO_ANOMALY_THRESHOLD, "high": 1.0},
            deviation_score=round(score, 4),
        )]

    except Exception as e:
        logger.warning("IsolationForest check failed: %s", e)
        return []


# ── 4. STL Seasonal Decomposition ────────────────────────────────────────────

def run_stl_check(current_profile, history: list) -> list[AnomalyResult]:
    row_counts = [p.row_count for p in history if p.row_count is not None]
    if len(row_counts) < STL_MIN_POINTS:
        return []

    try:
        import pandas as pd
        from statsmodels.tsa.seasonal import STL

        series = pd.Series(row_counts + [current_profile.row_count], dtype=float)
        stl = STL(series, period=7, robust=True)
        fit = stl.fit()
        residuals = fit.resid.values
        resid_std = float(np.std(residuals[:-1]))  # exclude current

        if resid_std == 0:
            return []

        last_resid = float(residuals[-1])
        threshold = 3.0 * resid_std
        failed = abs(last_resid) > threshold

        return [AnomalyResult(
            check_type="stl",
            check_name="stl_row_count_seasonal",
            column_name=None,
            status="failed" if failed else "passed",
            observed_value=float(current_profile.row_count),
            expected_range={
                "low": round(float(series.iloc[-1] - last_resid) - threshold, 1),
                "high": round(float(series.iloc[-1] - last_resid) + threshold, 1),
            },
            deviation_score=round(last_resid / resid_std, 4) if resid_std else None,
        )]

    except Exception as e:
        logger.warning("STL check failed: %s", e)
        return []


# ── 5. Cardinality Drop Check ─────────────────────────────────────────────────

CARDINALITY_DROP_THRESHOLD = 0.30  # 30% relative drop is suspicious

def run_cardinality_checks(
    current_profile,
    history: list,
) -> list[AnomalyResult]:
    """Detect when a column's distinct count ratio drops significantly."""
    results: list[AnomalyResult] = []
    if len(history) < Z_SCORE_MIN_POINTS:
        return results

    curr_metrics = current_profile.column_metrics or {}
    for col_name, col_data in curr_metrics.items():
        if not isinstance(col_data, dict):
            continue
        curr_card = col_data.get("cardinality_ratio")
        if curr_card is None:
            continue

        hist_cards = []
        for p in history[-Z_SCORE_WINDOW:]:
            if p.column_metrics and col_name in p.column_metrics:
                v = p.column_metrics[col_name]
                if isinstance(v, dict) and v.get("cardinality_ratio") is not None:
                    hist_cards.append(float(v["cardinality_ratio"]))

        if len(hist_cards) < Z_SCORE_MIN_POINTS:
            continue

        avg_hist = float(np.mean(hist_cards))
        if avg_hist == 0:
            continue

        relative_drop = (avg_hist - float(curr_card)) / avg_hist
        results.append(AnomalyResult(
            check_type="rule",
            check_name="cardinality_drop",
            column_name=col_name,
            status="failed" if relative_drop > CARDINALITY_DROP_THRESHOLD else "passed",
            observed_value=round(float(curr_card), 4),
            expected_range={"low": round(avg_hist * (1 - CARDINALITY_DROP_THRESHOLD), 4), "high": 1.0},
            deviation_score=round(relative_drop, 4),
        ))

    return results


# ── 6. Row Count Growth Rate ──────────────────────────────────────────────────

def run_row_growth_check(
    current_profile,
    history: list,
    threshold: float = 3.0,
) -> list[AnomalyResult]:
    """Detect abnormal row count growth rate (rows added per interval)."""
    if len(history) < Z_SCORE_MIN_POINTS:
        return []

    counts = [p.row_count for p in history if p.row_count is not None]
    if len(counts) < 2:
        return []

    deltas = [counts[i] - counts[i - 1] for i in range(1, len(counts))]
    deltas = deltas[-Z_SCORE_WINDOW:]

    if len(deltas) < Z_SCORE_MIN_POINTS - 1:
        return []

    arr = np.array(deltas, dtype=float)
    mean = float(np.mean(arr))
    std = float(np.std(arr))

    if std == 0:
        return []

    current_delta = (current_profile.row_count or 0) - (history[-1].row_count or 0)
    z = (current_delta - mean) / std

    return [AnomalyResult(
        check_type="z_score",
        check_name="row_count_growth_rate",
        column_name=None,
        status="failed" if abs(z) > threshold else "passed",
        observed_value=float(current_delta),
        expected_range={"low": round(mean - threshold * std, 1), "high": round(mean + threshold * std, 1)},
        deviation_score=round(z, 4),
    )]


# ── 7. Enum / Category Drift ──────────────────────────────────────────────────

ENUM_DRIFT_MIN_HISTORY = 3
ENUM_NEW_VALUE_THRESHOLD = 0.01  # flag if new value appears in >1% of rows


def run_enum_drift_check(
    current_profile,
    history: list,
) -> list[AnomalyResult]:
    """
    Detect when categorical columns gain unexpected new values or lose known values.
    Requires column_metrics to contain top_values list: [{value, count}].
    """
    results: list[AnomalyResult] = []
    if len(history) < ENUM_DRIFT_MIN_HISTORY:
        return results

    curr_metrics = current_profile.column_metrics or {}
    curr_rows = current_profile.row_count or 1

    for col_name, col_data in curr_metrics.items():
        if not isinstance(col_data, dict):
            continue
        curr_top = col_data.get("top_values")
        if not curr_top or not isinstance(curr_top, list):
            continue

        # Build historical value set
        hist_values: set[str] = set()
        for p in history[-ENUM_DRIFT_MIN_HISTORY:]:
            if not p.column_metrics:
                continue
            hist_col = p.column_metrics.get(col_name, {})
            for tv in hist_col.get("top_values", []):
                if tv.get("value") is not None:
                    hist_values.add(str(tv["value"]))

        if not hist_values:
            continue

        # Check for new values above threshold
        for tv in curr_top:
            val = str(tv.get("value", ""))
            count = tv.get("count", 0)
            if val not in hist_values and count / curr_rows > ENUM_NEW_VALUE_THRESHOLD:
                results.append(AnomalyResult(
                    check_type="rule",
                    check_name="enum_drift",
                    column_name=col_name,
                    status="failed",
                    observed_value=round(count / curr_rows, 4),
                    expected_range={"known_values": sorted(hist_values)[:20]},
                    deviation_score=round(count / curr_rows, 4),
                    details={"new_value": val, "count": count},
                ))
            elif val not in hist_values:
                results.append(AnomalyResult(
                    check_type="rule",
                    check_name="enum_new_value",
                    column_name=col_name,
                    status="passed",  # informational
                    observed_value=round(count / curr_rows, 4),
                    expected_range=None,
                    deviation_score=0,
                ))

    return results


# ── 8. Distribution Drift Mean ────────────────────────────────────────────────

def _safe_float(value) -> float | None:
    try:
        if value is None:
            return None
        val = float(value)
        if not np.isfinite(val):
            return None
        return val
    except (TypeError, ValueError):
        return None


def run_distribution_drift_check(current_profile, history) -> list[AnomalyResult]:
    """Detect numeric column mean drift against the historical rolling average."""
    results: list[AnomalyResult] = []
    curr_metrics = getattr(current_profile, "column_metrics", None) or {}
    if not isinstance(curr_metrics, dict):
        return results

    history = history or []
    for col_name, col_data in curr_metrics.items():
        if not isinstance(col_data, dict):
            continue
        current_mean = _safe_float(col_data.get("mean"))
        current_stddev = _safe_float(col_data.get("stddev"))
        if current_mean is None or current_stddev is None:
            continue

        hist_means: list[float] = []
        for profile in history[-Z_SCORE_WINDOW:]:
            profile_metrics = getattr(profile, "column_metrics", None) or {}
            if not isinstance(profile_metrics, dict):
                continue
            hist_col = profile_metrics.get(col_name, {})
            if not isinstance(hist_col, dict):
                continue
            hist_mean = _safe_float(hist_col.get("mean"))
            hist_stddev = _safe_float(hist_col.get("stddev"))
            if hist_mean is not None and hist_stddev is not None:
                hist_means.append(hist_mean)

        if len(hist_means) < Z_SCORE_MIN_POINTS:
            continue

        arr = np.array(hist_means, dtype=float)
        mean = float(np.mean(arr))
        std = float(np.std(arr))
        if std == 0:
            continue

        z = (current_mean - mean) / std
        results.append(AnomalyResult(
            check_type="z_score",
            check_name="distribution_drift_mean",
            column_name=col_name,
            status="failed" if abs(z) > 3.0 else "passed",
            observed_value=round(current_mean, 4),
            expected_range={"low": round(mean - 3.0 * std, 4), "high": round(mean + 3.0 * std, 4)},
            deviation_score=round(z, 4),
        ))

    return results


# ── 9. Null Rate Trend ────────────────────────────────────────────────────────

def run_null_rate_trend_check(current_profile, history) -> list[AnomalyResult]:
    """Detect columns whose null_rate is monotonically increasing."""
    results: list[AnomalyResult] = []
    history = history or []
    if len(history) < 5:
        return results

    curr_metrics = getattr(current_profile, "column_metrics", None) or {}
    if not isinstance(curr_metrics, dict):
        return results

    for col_name, col_data in curr_metrics.items():
        if not isinstance(col_data, dict):
            continue

        rates: list[float] = []
        for profile in history[-5:]:
            profile_metrics = getattr(profile, "column_metrics", None) or {}
            if not isinstance(profile_metrics, dict):
                continue
            hist_col = profile_metrics.get(col_name, {})
            if not isinstance(hist_col, dict):
                continue
            null_rate = _safe_float(hist_col.get("null_rate"))
            if null_rate is not None:
                rates.append(null_rate)

        current_null_rate = _safe_float(col_data.get("null_rate"))
        if current_null_rate is None or len(rates) < 5:
            continue

        rates.append(current_null_rate)
        trending = all(rates[i] > rates[i - 1] for i in range(1, len(rates)))
        slope = float(np.polyfit(np.arange(len(rates), dtype=float), np.array(rates, dtype=float), 1)[0])

        results.append(AnomalyResult(
            check_type="rule",
            check_name="null_rate_trending",
            column_name=col_name,
            status="failed" if trending else "passed",
            observed_value=round(current_null_rate, 4),
            expected_range={"low": 0.0, "high": round(rates[0], 4)},
            deviation_score=round(slope, 4),
        ))

    return results


# ── 10. Freshness ─────────────────────────────────────────────────────────────

def run_freshness_check(current_profile, monitored_table) -> list[AnomalyResult]:
    """Check freshness staleness and SLA breach for tables with a freshness column."""
    results: list[AnomalyResult] = []
    freshness_column = getattr(monitored_table, "freshness_column", None)
    freshness_seconds = _safe_float(getattr(current_profile, "freshness_seconds", None))
    if not freshness_column or freshness_seconds is None:
        return results

    interval_minutes = _safe_float(getattr(monitored_table, "check_interval_minutes", None))
    if interval_minutes is None:
        return results

    stale_seconds = interval_minutes * 60
    sla_seconds = stale_seconds * 2

    if freshness_seconds > sla_seconds:
        results.append(AnomalyResult(
            check_type="rule",
            check_name="freshness_sla_breach",
            column_name=freshness_column,
            status="failed",
            observed_value=round(freshness_seconds, 1),
            expected_range={"low": 0, "high": round(sla_seconds, 1)},
            deviation_score=None,
        ))

    results.append(AnomalyResult(
        check_type="rule",
        check_name="freshness_stale",
        column_name=freshness_column,
        status="failed" if freshness_seconds > stale_seconds else "passed",
        observed_value=round(freshness_seconds, 1),
        expected_range={"low": 0, "high": round(stale_seconds, 1)},
        deviation_score=None,
    ))

    return results


# ── 11. Schema Change ─────────────────────────────────────────────────────────

def run_schema_change_check(current_profile, history) -> list[AnomalyResult]:
    """Detect schema fingerprint drift and column count changes."""
    results: list[AnomalyResult] = []
    history = history or []
    if len(history) < 1:
        return results

    prev_profile = history[-1]
    curr_fp = getattr(current_profile, "schema_fingerprint", None)
    prev_fp = getattr(prev_profile, "schema_fingerprint", None)
    if curr_fp is not None and prev_fp is not None:
        changed = curr_fp != prev_fp
        results.append(AnomalyResult(
            check_type="rule",
            check_name="schema_drift",
            column_name=None,
            status="failed" if changed else "passed",
            observed_value=None,
            expected_range={"previous": prev_fp, "current": curr_fp} if changed else None,
            deviation_score=None,
        ))

    curr_metrics = getattr(current_profile, "column_metrics", None) or {}
    prev_metrics = getattr(prev_profile, "column_metrics", None) or {}
    if isinstance(curr_metrics, dict) and isinstance(prev_metrics, dict):
        curr_count = len(curr_metrics)
        prev_count = len(prev_metrics)
        if curr_count != prev_count:
            results.append(AnomalyResult(
                check_type="rule",
                check_name="schema_column_count_change",
                column_name=None,
                status="failed",
                observed_value=float(curr_count),
                expected_range={"previous": prev_count, "current": curr_count},
                deviation_score=float(curr_count - prev_count),
            ))

    return results


# ── 12. CUSUM (Cumulative Sum Control Chart) ──────────────────────────────────

CUSUM_MIN_POINTS = 10


def run_cusum_check(
    current_profile,
    history: list,
    k: float = 0.5,
    h: float = 5.0,
) -> list[AnomalyResult]:
    """
    CUSUM (Cumulative Sum Control Chart) — detects gradual shifts in row count.
    k = allowance parameter (half the shift we want to detect, in stddev units)
    h = decision threshold (alert when cumulative sum exceeds h stddevs)
    """
    row_counts = [p.row_count for p in history if p.row_count is not None]
    if len(row_counts) < CUSUM_MIN_POINTS or current_profile.row_count is None:
        return []

    try:
        arr = np.array(row_counts, dtype=float)
        mean = float(np.mean(arr))
        std = float(np.std(arr))
        if std == 0:
            return []

        # Compute normalized deviations for history (to warm up CUSUM)
        c_plus = 0.0
        c_minus = 0.0
        for x in row_counts:
            d_i = (x - mean) / std
            c_plus = max(0.0, c_plus + d_i - k)
            c_minus = max(0.0, c_minus - d_i - k)

        # Apply current point
        d_curr = (float(current_profile.row_count) - mean) / std
        c_plus = max(0.0, c_plus + d_curr - k)
        c_minus = max(0.0, c_minus - d_curr - k)

        max_cusum = max(c_plus, c_minus)
        failed = c_plus > h or c_minus > h
        direction = "upward" if c_plus > c_minus else "downward"

        return [AnomalyResult(
            check_type="cusum",
            check_name="cusum_row_count",
            column_name=None,
            status="failed" if failed else "passed",
            observed_value=round(max_cusum, 4),
            expected_range={"low": 0.0, "high": h},
            deviation_score=round(max_cusum, 4),
            details={"c_plus": round(c_plus, 4), "c_minus": round(c_minus, 4), "direction": direction},
        )]
    except Exception as e:
        logger.warning("CUSUM check failed: %s", e)
        return []


# ── 13. Mann-Kendall Trend Test ───────────────────────────────────────────────

MANN_KENDALL_MIN_POINTS = 8
MANN_KENDALL_TAU_THRESHOLD = 0.6
MANN_KENDALL_PVALUE_THRESHOLD = 0.05


def run_mann_kendall_check(
    current_profile,
    history: list,
) -> list[AnomalyResult]:
    """
    Mann-Kendall non-parametric trend test for monotonic trends in row count.
    Uses scipy.stats.kendalltau for the test statistic.
    """
    row_counts = [p.row_count for p in history if p.row_count is not None]
    if len(row_counts) < MANN_KENDALL_MIN_POINTS or current_profile.row_count is None:
        return []

    try:
        from scipy import stats

        series = row_counts + [current_profile.row_count]
        n = len(series)
        tau, p_value = stats.kendalltau(np.arange(n), series)

        if abs(tau) > MANN_KENDALL_TAU_THRESHOLD and p_value < MANN_KENDALL_PVALUE_THRESHOLD:
            direction = "upward" if tau > 0 else "downward"
            failed = True
        else:
            direction = "none"
            failed = False

        return [AnomalyResult(
            check_type="statistical",
            check_name="mann_kendall_trend",
            column_name=None,
            status="failed" if failed else "passed",
            observed_value=round(float(tau), 4),
            expected_range={"low": -MANN_KENDALL_TAU_THRESHOLD, "high": MANN_KENDALL_TAU_THRESHOLD},
            deviation_score=round(float(tau), 4),
            details={"p_value": round(float(p_value), 6), "direction": direction, "n": n},
        )]
    except Exception as e:
        logger.warning("Mann-Kendall check failed: %s", e)
        return []


# ── 14. Percentile Drift Check ────────────────────────────────────────────────

PERCENTILE_DRIFT_THRESHOLD = 0.30  # 30% relative change triggers a flag
PERCENTILE_DRIFT_MIN_HISTORY = 5


def run_percentile_drift_check(
    current_profile,
    history: list,
) -> list[AnomalyResult]:
    """
    Detect when numeric column percentiles (p50, p95) drift significantly
    from their historical rolling averages.
    """
    results: list[AnomalyResult] = []
    if len(history) < PERCENTILE_DRIFT_MIN_HISTORY:
        return results

    curr_metrics = getattr(current_profile, "column_metrics", None) or {}
    if not isinstance(curr_metrics, dict):
        return results

    for col_name, col_data in curr_metrics.items():
        if not isinstance(col_data, dict):
            continue

        for percentile_key in ("p50", "p95"):
            curr_val = _safe_float(col_data.get(percentile_key))
            if curr_val is None:
                continue

            # Collect historical values (last 14 profiles)
            hist_vals: list[float] = []
            for p in history[-14:]:
                p_metrics = getattr(p, "column_metrics", None) or {}
                if not isinstance(p_metrics, dict):
                    continue
                hist_col = p_metrics.get(col_name, {})
                if not isinstance(hist_col, dict):
                    continue
                v = _safe_float(hist_col.get(percentile_key))
                if v is not None:
                    hist_vals.append(v)

            if len(hist_vals) < PERCENTILE_DRIFT_MIN_HISTORY:
                continue

            hist_avg = float(np.mean(hist_vals))
            relative_change = abs(curr_val - hist_avg) / max(abs(hist_avg), 1.0)
            failed = relative_change > PERCENTILE_DRIFT_THRESHOLD

            results.append(AnomalyResult(
                check_type="statistical",
                check_name=f"percentile_drift_{percentile_key}",
                column_name=col_name,
                status="failed" if failed else "passed",
                observed_value=round(curr_val, 4),
                expected_range={
                    "low": round(hist_avg * (1 - PERCENTILE_DRIFT_THRESHOLD), 4),
                    "high": round(hist_avg * (1 + PERCENTILE_DRIFT_THRESHOLD), 4),
                },
                deviation_score=round(relative_change, 4),
            ))

    return results


# ── 8. Uniqueness / Duplicate Rate Check ──────────────────────────────────────

UNIQUENESS_DROP_THRESHOLD = 0.05  # flag if uniqueness drops >5% relative

def run_uniqueness_check(
    current_profile,
    history: list,
) -> list[AnomalyResult]:
    """
    Detect columns where uniqueness_ratio dropped significantly (duplicate surge).
    Uses uniqueness_ratio from column_metrics (= distinct_count / row_count).
    """
    results: list[AnomalyResult] = []
    if len(history) < 3:
        return results

    curr_metrics = current_profile.column_metrics or {}
    for col_name, col_data in curr_metrics.items():
        if not isinstance(col_data, dict):
            continue
        curr_uniq = col_data.get("uniqueness_ratio")
        if curr_uniq is None:
            continue

        hist_uniqs = []
        for p in history[-7:]:
            if p.column_metrics and col_name in p.column_metrics:
                v = p.column_metrics[col_name]
                if isinstance(v, dict) and v.get("uniqueness_ratio") is not None:
                    hist_uniqs.append(float(v["uniqueness_ratio"]))

        if len(hist_uniqs) < 2:
            continue

        avg_hist = float(np.mean(hist_uniqs))
        if avg_hist < 0.01:
            continue  # was never unique, skip

        relative_drop = (avg_hist - float(curr_uniq)) / avg_hist
        results.append(AnomalyResult(
            check_type="rule",
            check_name="uniqueness_drop",
            column_name=col_name,
            status="failed" if relative_drop > UNIQUENESS_DROP_THRESHOLD else "passed",
            observed_value=round(float(curr_uniq), 4),
            expected_range={"low": round(avg_hist * (1 - UNIQUENESS_DROP_THRESHOLD), 4), "high": 1.0},
            deviation_score=round(relative_drop, 4),
        ))

    return results
