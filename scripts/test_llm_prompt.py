#!/usr/bin/env python3
"""
LLM prompt test harness.

Usage:
  python scripts/test_llm_prompt.py --incident-id <uuid>
  python scripts/test_llm_prompt.py --fixture pipeline_failure

Prints:
  - Full assembled context with token count
  - LLM response (raw JSON)
  - Pydantic validation result (pass/fail)
  - Jury readiness check for pipeline_failure scenario

Requires: DATABASE_URL, OPENROUTER_API_KEY env vars.
"""
import asyncio
import json
import os
import sys

# Allow running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import argparse
from datetime import UTC, datetime, timedelta

# ── Fixtures ───────────────────────────────────────────────────────────────────

FIXTURE_PIPELINE_FAILURE = {
    "incident": {
        "id": "fixture-000",
        "severity": "P1",
        "title": "[P1] demo.orders — row count dropped to 0",
        "created_at": datetime.now(UTC).isoformat(),
        "fired_checks": [
            {"check_name": "row_count_zero", "observed_value": 0, "expected_range": {"low": 400, "high": 600}, "deviation_score": None},
            {"check_name": "freshness_sla_breach", "observed_value": 259200, "expected_range": {"low": 0, "high": 5400}, "deviation_score": None},
        ],
    },
    "table": {
        "schema": "demo", "name": "orders",
        "freshness_column": "created_at", "check_interval_minutes": 60,
        "sensitivity": 3.0, "dbt_model_yaml": None,
    },
    "source": {"name": "Demo Postgres", "type": "postgres"},
    "profile_history": [
        {"date": (datetime.now(UTC) - timedelta(days=14-i)).strftime("%Y-%m-%d"),
         "row_count": 490 + (i * 3), "freshness_seconds": 3540 + (i * 10),
         "null_rate_amount": 0.012}
        for i in range(13)
    ] + [{"date": datetime.now(UTC).strftime("%Y-%m-%d"), "row_count": 0,
          "freshness_seconds": 259200, "null_rate_amount": 0.0}],
}

FIXTURE_NULL_SPIKE = {
    "incident": {
        "id": "fixture-001",
        "severity": "P2",
        "title": "[P2] demo.orders — null_rate_amount anomalous (z-score)",
        "created_at": datetime.now(UTC).isoformat(),
        "fired_checks": [
            {"check_name": "null_rate_spike", "observed_value": 0.45, "expected_range": {"low": 0.0, "high": 0.03}, "deviation_score": 12.3},
            {"check_name": "z_score_null_rate__amount", "observed_value": 0.45, "deviation_score": 11.8},
        ],
    },
    "table": {"schema": "demo", "name": "orders", "freshness_column": "created_at", "check_interval_minutes": 60, "sensitivity": 3.0, "dbt_model_yaml": None},
    "source": {"name": "Demo Postgres", "type": "postgres"},
    "profile_history": [
        {"date": (datetime.now(UTC) - timedelta(days=14-i)).strftime("%Y-%m-%d"),
         "row_count": 500 + (i * 2), "freshness_seconds": 3600, "null_rate_amount": 0.012 + (i * 0.001)}
        for i in range(13)
    ] + [{"date": datetime.now(UTC).strftime("%Y-%m-%d"), "row_count": 498,
          "freshness_seconds": 3600, "null_rate_amount": 0.45}],
}

FIXTURES = {"pipeline_failure": FIXTURE_PIPELINE_FAILURE, "null_spike": FIXTURE_NULL_SPIKE}


def build_fixture_context(fixture: dict) -> str:
    inc = fixture["incident"]
    tbl = fixture["table"]
    src = fixture["source"]
    hist = fixture.get("profile_history", [])

    checks_str = "\n".join(
        f"  FAIL: {c['check_name']} | observed={c.get('observed_value')} | deviation={c.get('deviation_score')}"
        for c in inc["fired_checks"]
    )

    if hist:
        header = "  date\t\trows\tfreshness_s\tnull_amount"
        rows = "\n".join(
            f"  {h['date']}\t{h['row_count']}\t{h['freshness_seconds']:.0f}\t{h['null_rate_amount']:.3f}"
            + ("\t← ANOMALY" if i == len(hist) - 1 else "")
            for i, h in enumerate(hist)
        )
        history_str = header + "\n" + rows
    else:
        history_str = "  (no history)"

    return f"""=== INCIDENT ===
ID:        {inc['id']}
Severity:  {inc['severity']}
Title:     {inc['title']}
Detected:  {inc['created_at'][:16]}

=== SOURCE ===
Warehouse: {src['name']} ({src['type']})
Table:     {tbl['schema']}.{tbl['name']}
Freshness column: {tbl['freshness_column']}
Check interval:   {tbl['check_interval_minutes']} minutes
Sensitivity:      {tbl['sensitivity']}σ

=== FAILED CHECKS ===
{checks_str}

=== PROFILE HISTORY (last 14 days) ===
{history_str}"""


def count_tokens(text: str) -> int:
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        # Rough estimate: 1 token ≈ 4 chars
        return len(text) // 4


def validate_jury_readiness(narration: dict, scenario: str) -> list[str]:
    """Check that demo narration meets jury expectations."""
    issues = []
    if scenario != "pipeline_failure":
        return []
    summary = narration.get("summary", "").lower()
    if not any(w in summary for w in ["pipeline", "ingestion", "data", "orders", "row"]):
        issues.append("summary should mention the pipeline or orders table")
    causes = narration.get("likely_causes", [])
    if not any(c.get("probability") == "high" for c in causes):
        issues.append("expected at least one high-probability cause for a P1 pipeline failure")
    actions = " ".join(narration.get("recommended_actions", [])).lower()
    if not any(w in actions for w in ["etl", "pipeline", "job", "check", "ingest", "source"]):
        issues.append("recommended_actions should mention the ETL job or data source")
    if narration.get("confidence") != "high":
        issues.append(f"expected confidence=high for pipeline failure, got {narration.get('confidence')}")
    return issues


async def run_with_real_incident(incident_id: str):
    from app.services.llm_context import build_context
    from app.services.llm import generate_narration, NarrationResult
    import pydantic

    print(f"Loading incident {incident_id} from DB…")
    context = await build_context(incident_id)
    run_test(context, "real_incident", generate_narration, NarrationResult)


def run_test(context: str, scenario: str, generate_fn, NarrationResult):
    from app.services.llm import NarrationResult as NR
    import pydantic

    tokens = count_tokens(context)

    print("\n" + "="*60)
    print("ASSEMBLED CONTEXT")
    print("="*60)
    print(context)
    print(f"\n→ Token estimate: {tokens}")

    if tokens > 3000:
        print(f"⚠  WARNING: context exceeds 3000 token target ({tokens})")
    else:
        print(f"✓ Token budget OK ({tokens}/3000)")

    if not os.environ.get("OPENROUTER_API_KEY"):
        print("\n⚠  OPENROUTER_API_KEY not set — skipping LLM call")
        return

    print("\n" + "="*60)
    print("CALLING LLM…")
    print("="*60)

    narration = generate_fn(context)

    print(json.dumps(narration, indent=2))

    if "error" in narration:
        print(f"\n✗ FAILED: {narration['error']} — {narration.get('reason', '')}")
        return

    # Validate
    try:
        NR.model_validate(narration)
        print("\n✓ Pydantic validation PASSED")
    except pydantic.ValidationError as e:
        print(f"\n✗ Pydantic validation FAILED:\n{e}")
        return

    # Jury readiness
    issues = validate_jury_readiness(narration, scenario)
    if issues:
        print("\n⚠  Jury readiness issues:")
        for issue in issues:
            print(f"   - {issue}")
    else:
        print("✓ Jury readiness check PASSED")


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--incident-id", help="Real incident UUID from DB")
    group.add_argument("--fixture", choices=list(FIXTURES.keys()), help="Use a hardcoded test fixture")
    args = parser.parse_args()

    if args.fixture:
        fixture = FIXTURES[args.fixture]
        context = build_fixture_context(fixture)

        # Import generate_narration after sys.path is set
        from app.services.llm import generate_narration, NarrationResult
        run_test(context, args.fixture, generate_narration, NarrationResult)
    else:
        # Real DB call
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            print("ERROR: DATABASE_URL not set")
            sys.exit(1)
        asyncio.run(run_with_real_incident(args.incident_id))


if __name__ == "__main__":
    main()
