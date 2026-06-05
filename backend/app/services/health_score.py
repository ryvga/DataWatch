"""
HealthScoreService — computes weighted data reliability scores.

Formula (weighted by severity):
  score = critical_pass * 0.50 + high_pass * 0.30 + medium_pass * 0.15 + low_pass * 0.05

Returns 0–100. Color: green ≥80, yellow 60–79, red <60.
"""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


SEVERITY_WEIGHTS = {
    "P1": 0.50,  # critical
    "P2": 0.30,  # high
    "P3": 0.15,  # medium
}
DEFAULT_WEIGHT = 0.05


@dataclass
class HealthBreakdown:
    score: float            # 0–100
    grade: str              # A/B/C/D/F
    color: str              # green / yellow / red
    total_checks: int
    passed_checks: int
    failed_checks: int
    by_severity: dict       # {"P1": {"passed": x, "total": y}, ...}
    open_incidents: int
    window_hours: int


def compute_health_score(check_results: list, open_incidents: int = 0, window_hours: int = 24) -> HealthBreakdown:
    """
    check_results: list of dicts with keys: status ('passed'/'failed'), severity (P1/P2/P3).
    """
    by_sev: dict[str, dict] = {}
    for cr in check_results:
        sev = cr.get("severity", "P3")
        if sev not in by_sev:
            by_sev[sev] = {"passed": 0, "total": 0}
        by_sev[sev]["total"] += 1
        if cr.get("status") == "passed":
            by_sev[sev]["passed"] += 1

    weighted_sum = 0.0
    weight_total = 0.0
    for sev, counts in by_sev.items():
        if counts["total"] == 0:
            continue
        w = SEVERITY_WEIGHTS.get(sev, DEFAULT_WEIGHT)
        rate = counts["passed"] / counts["total"]
        weighted_sum += w * rate
        weight_total += w

    raw_score = (weighted_sum / weight_total * 100) if weight_total > 0 else 100.0

    # Penalize for open incidents
    incident_penalty = min(open_incidents * 3, 20)
    score = max(0.0, round(raw_score - incident_penalty, 1))

    total = sum(v["total"] for v in by_sev.values())
    passed = sum(v["passed"] for v in by_sev.values())

    color = "green" if score >= 80 else "yellow" if score >= 60 else "red"
    grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"

    return HealthBreakdown(
        score=score,
        grade=grade,
        color=color,
        total_checks=total,
        passed_checks=passed,
        failed_checks=total - passed,
        by_severity=by_sev,
        open_incidents=open_incidents,
        window_hours=window_hours,
    )
