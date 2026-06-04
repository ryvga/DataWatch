#!/usr/bin/env python3
"""
DataWatch comprehensive demo seed.

One command to go from empty DB → full jury-ready demo with:
  • 3 demo tables (orders, users, products) with realistic data
  • 90-day profile history per table (enables all 4 detectors)
  • Pre-seeded incidents at P1 / P2 / P3 severity with LLM narrations
  • Demo org + user registered and ready to log in

Usage:
  python scripts/seed_demo.py --full           # complete fresh setup (run once)
  python scripts/seed_demo.py --reset          # drop demo + re-run --full
  python scripts/seed_demo.py --scenario pipeline_failure
  python scripts/seed_demo.py --scenario null_spike
  python scripts/seed_demo.py --scenario schema_drift
  python scripts/seed_demo.py --scenario row_explosion

Environment (defaults work with docker-compose dev stack):
  DB_URL           postgresql://datawatch:datawatch@localhost:5433/datawatch
  API_URL          http://localhost:8000
  DEMO_EMAIL       demo@datawatch.io
  DEMO_PASSWORD    demo1234

After --full, log in at http://localhost:3000 with demo@datawatch.io / demo1234
"""

import argparse
import json
import os
import random
import sys
import time
import uuid
from datetime import UTC, date, datetime, timedelta

import psycopg2
import requests

# ── Config ─────────────────────────────────────────────────────────────────────

DB_URL = os.environ.get(
    "DB_URL",
    os.environ.get("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
    or "postgresql://datawatch:datawatch@localhost:5433/datawatch"
)
API_URL = os.environ.get("API_URL", "http://localhost:8000")
DEMO_EMAIL = os.environ.get("DEMO_EMAIL", "demo@datawatch.io")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "demo1234")

random.seed(42)

COUNTRIES = ["US", "FR", "DE", "MA", "GB", "CA", "AU", "JP", "ES", "BR"]
CATEGORIES = ["Electronics", "Clothing", "Food", "Books", "Sports", "Home", "Beauty"]
STATUSES = ["completed", "pending", "cancelled", "refunded"]

# ── API helpers ────────────────────────────────────────────────────────────────

_token = None
_api_key = None


def _headers():
    if _token:
        return {"Authorization": f"Bearer {_token}", "Content-Type": "application/json"}
    if _api_key:
        return {"x-api-key": _api_key, "Content-Type": "application/json"}
    return {"Content-Type": "application/json"}


def api(method, path, silent=False, **kwargs):
    resp = requests.request(method, f"{API_URL}{path}", headers=_headers(), timeout=30, **kwargs)
    if not silent and resp.status_code >= 400:
        print(f"  ⚠ API {method} {path} → {resp.status_code}: {resp.text[:300]}")
    return resp


def login(email, password):
    global _token
    r = requests.post(f"{API_URL}/auth/login",
                      json={"email": email, "password": password}, timeout=10)
    if r.status_code == 200:
        _token = r.json()["access_token"]
        return True
    return False


def register(org_name, org_slug, email, password):
    global _api_key
    r = requests.post(f"{API_URL}/auth/register",
                      json={"org_name": org_name, "org_slug": org_slug,
                            "email": email, "password": password}, timeout=10)
    if r.status_code == 201:
        _api_key = r.json()["api_key"]
        print(f"  ✓ Org '{org_name}' registered. API key: {_api_key[:20]}…")
        return True
    if r.status_code == 409:
        print(f"  ℹ Org '{org_slug}' already exists, logging in…")
        return False
    print(f"  ✗ Register failed: {r.text[:200]}")
    return False


# ── DB helpers ─────────────────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(DB_URL)


def check_api():
    try:
        r = requests.get(f"{API_URL}/health", timeout=5)
        return r.status_code == 200 and r.json().get("db") == "connected"
    except Exception:
        return False


# ── Step 1: Demo schema + realistic data ──────────────────────────────────────

def create_demo_schema(conn):
    print("\n📦 Creating demo schema and tables…")
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS demo")
        cur.execute("DROP TABLE IF EXISTS demo.orders CASCADE")
        cur.execute("DROP TABLE IF EXISTS demo.users CASCADE")
        cur.execute("DROP TABLE IF EXISTS demo.products CASCADE")
        cur.execute("DROP TABLE IF EXISTS demo.events CASCADE")

        cur.execute("""
            CREATE TABLE demo.users (
                id          SERIAL PRIMARY KEY,
                email       TEXT NOT NULL UNIQUE,
                signup_date DATE NOT NULL,
                country     TEXT,
                plan        TEXT DEFAULT 'free',
                is_active   BOOLEAN DEFAULT TRUE,
                created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE demo.products (
                id          SERIAL PRIMARY KEY,
                name        TEXT NOT NULL,
                category    TEXT,
                price       NUMERIC(10,2),
                stock_count INTEGER DEFAULT 0,
                is_available BOOLEAN DEFAULT TRUE
            )
        """)
        cur.execute("""
            CREATE TABLE demo.orders (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER REFERENCES demo.users(id),
                product_id INTEGER REFERENCES demo.products(id),
                amount     NUMERIC(10,2),
                status     TEXT,
                country    TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE demo.events (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER REFERENCES demo.users(id),
                event_type TEXT,
                properties JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
    conn.commit()
    print("  ✓ Schema created: demo.users, demo.products, demo.orders, demo.events")


def seed_users(conn, count=3000):
    print(f"  Seeding {count} users…")
    with conn.cursor() as cur:
        rows = []
        for i in range(count):
            signup = date(2023, 1, 1) + timedelta(days=random.randint(0, 700))
            rows.append((
                f"user{i}@example.com",
                signup,
                random.choice(COUNTRIES),
                random.choice(["free", "starter", "growth"]),
                random.random() > 0.04,
            ))
        cur.executemany(
            "INSERT INTO demo.users (email, signup_date, country, plan, is_active) "
            "VALUES (%s,%s,%s,%s,%s)",
            rows,
        )
    conn.commit()
    print(f"  ✓ {count} users")


def seed_products(conn, count=150):
    print(f"  Seeding {count} products…")
    with conn.cursor() as cur:
        rows = [
            (f"Product {i:03d}", random.choice(CATEGORIES),
             round(random.uniform(5, 999), 2), random.randint(0, 500),
             random.random() > 0.08)
            for i in range(count)
        ]
        cur.executemany(
            "INSERT INTO demo.products (name, category, price, stock_count, is_available) "
            "VALUES (%s,%s,%s,%s,%s)",
            rows,
        )
    conn.commit()
    print(f"  ✓ {count} products")


def seed_orders(conn, days=90, base_per_day=480):
    print(f"  Seeding {days} days of orders (~{base_per_day}/day with realistic variance)…")
    with conn.cursor() as cur:
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        batch = []
        for d in range(days):
            day = today - timedelta(days=days - d)
            # Realistic: weekday/weekend variance + slight growth trend
            weekday = day.weekday()
            weekend_factor = 0.7 if weekday >= 5 else 1.0
            trend_factor = 1 + (d / days) * 0.15  # 15% growth over 90 days
            count = int(random.gauss(base_per_day * weekend_factor * trend_factor,
                                     base_per_day * 0.12))
            count = max(50, count)
            for _ in range(count):
                ts = day + timedelta(hours=random.randint(0, 23), minutes=random.randint(0, 59))
                batch.append((
                    random.randint(1, 3000),
                    random.randint(1, 150),
                    round(random.uniform(5, 850), 2),
                    random.choice(STATUSES),
                    random.choice(COUNTRIES),
                    ts,
                ))
        cur.executemany(
            "INSERT INTO demo.orders (user_id, product_id, amount, status, country, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            batch,
        )
    conn.commit()
    print(f"  ✓ ~{len(batch):,} orders across {days} days")


def seed_events(conn, days=30):
    print(f"  Seeding {days} days of events…")
    event_types = ["page_view", "add_to_cart", "checkout", "signup", "login", "search"]
    with conn.cursor() as cur:
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        batch = []
        for d in range(days):
            day = today - timedelta(days=days - d)
            count = random.randint(800, 1500)
            for _ in range(count):
                ts = day + timedelta(hours=random.randint(0, 23), minutes=random.randint(0, 59))
                batch.append((
                    random.randint(1, 3000),
                    random.choice(event_types),
                    json.dumps({"page": f"/p{random.randint(1, 50)}", "duration_ms": random.randint(100, 8000)}),
                    ts,
                ))
        cur.executemany(
            "INSERT INTO demo.events (user_id, event_type, properties, created_at) "
            "VALUES (%s,%s,%s,%s)",
            batch,
        )
    conn.commit()
    print(f"  ✓ ~{len(batch):,} events")


# ── Step 2: Register demo org + source + tables ───────────────────────────────

def setup_datawatch(conn):
    global _token, _api_key
    print("\n🔑 Setting up DataWatch org, source and tables…")

    # Register or login
    ok = register("DataWatch Demo", "demo-corp", DEMO_EMAIL, DEMO_PASSWORD)
    if not ok:
        # Already registered
        if not login(DEMO_EMAIL, DEMO_PASSWORD):
            print("  ✗ Cannot login. Try --reset to start fresh.")
            sys.exit(1)
    else:
        if not login(DEMO_EMAIL, DEMO_PASSWORD):
            print("  ✗ Login after register failed")
            sys.exit(1)

    print(f"  ✓ Logged in as {DEMO_EMAIL}")

    # Create data source pointing at the docker postgres (internal hostname)
    r = api("POST", "/api/v1/sources", json={
        "name": "Demo Postgres",
        "type": "postgres",
        "connection_config": {
            "host": "postgres",
            "port": 5432,
            "database": "datawatch",
            "username": "datawatch",
            "password": "datawatch",
        }
    })

    if r.status_code not in (200, 201):
        # Source might already exist
        r2 = api("GET", "/api/v1/sources")
        sources = r2.json() if r2.status_code == 200 else []
        source = next((s for s in sources if s["name"] == "Demo Postgres"), None)
        if not source:
            print("  ✗ Could not create data source")
            sys.exit(1)
        source_id = source["id"]
        print(f"  ℹ Using existing source: {source_id}")
    else:
        source_id = r.json()["id"]
        print(f"  ✓ Data source created: {source_id} (status: {r.json()['status']})")

    # Add monitored tables
    tables_config = [
        {
            "source_id": source_id, "schema_name": "demo", "table_name": "orders",
            "freshness_column": "created_at", "check_interval_minutes": 60, "sensitivity": 3.0,
        },
        {
            "source_id": source_id, "schema_name": "demo", "table_name": "users",
            "freshness_column": "created_at", "check_interval_minutes": 120, "sensitivity": 3.0,
        },
        {
            "source_id": source_id, "schema_name": "demo", "table_name": "products",
            "freshness_column": None, "check_interval_minutes": 360, "sensitivity": 2.5,
        },
    ]

    table_ids = {}
    existing_r = api("GET", "/api/v1/tables")
    existing = {f"{t['schema_name']}.{t['table_name']}": t["id"]
                for t in (existing_r.json() if existing_r.status_code == 200 else [])}

    for cfg in tables_config:
        key = f"{cfg['schema_name']}.{cfg['table_name']}"
        if key in existing:
            table_ids[key] = existing[key]
            print(f"  ℹ Table {key} already monitored: {table_ids[key]}")
        else:
            tr = api("POST", "/api/v1/tables", json=cfg)
            if tr.status_code in (200, 201):
                table_ids[key] = tr.json()["id"]
                print(f"  ✓ Monitoring {key}: {table_ids[key]}")
            else:
                print(f"  ✗ Failed to add {key}")

    return source_id, table_ids


# ── Step 3: Seed 90-day profile history ──────────────────────────────────────

def build_orders_metrics(day_idx, days, anomaly=None):
    """Realistic profile metrics for demo.orders with gradual growth."""
    base_rows = 480 + int(day_idx * 1.5)
    weekday = day_idx % 7
    weekend_dip = 0.72 if weekday >= 5 else 1.0
    row_count = max(50, int(random.gauss(base_rows * weekend_dip, 45)))

    metrics = {
        "id":         {"null_rate": 0.0, "distinct_count": float(row_count)},
        "user_id":    {"null_rate": round(random.uniform(0.0, 0.02), 4), "distinct_count": float(min(row_count, 3000))},
        "product_id": {"null_rate": 0.0, "distinct_count": float(min(row_count, 150))},
        "amount": {
            "null_rate":      round(random.uniform(0.01, 0.025), 4),
            "distinct_count": float(row_count - random.randint(5, 30)),
            "min":            round(random.uniform(5.0, 12.0), 2),
            "max":            round(random.uniform(820.0, 880.0), 2),
            "mean":           round(random.gauss(165.0, 8.0), 2),
            "stddev":         round(random.gauss(210.0, 12.0), 2),
        },
        "status":  {"null_rate": 0.0, "distinct_count": 4.0},
        "country": {"null_rate": round(random.uniform(0.0, 0.01), 4), "distinct_count": 10.0},
        "created_at": {
            "null_rate": 0.0,
            "min": (datetime(2026, 1, 1) + timedelta(days=day_idx)).isoformat(),
            "max": (datetime(2026, 1, 1) + timedelta(days=day_idx, hours=23, minutes=59)).isoformat(),
        },
    }

    freshness = round(random.uniform(1200, 4200), 1)

    if anomaly == "pipeline_failure":
        row_count = 0
        freshness = 259200.0  # 3 days
        metrics["amount"]["null_rate"] = 0.0
    elif anomaly == "null_spike":
        metrics["amount"]["null_rate"] = round(random.uniform(0.42, 0.48), 4)
    elif anomaly == "row_explosion":
        row_count = row_count * 15

    return row_count, freshness, metrics


def build_users_metrics(day_idx):
    new_users = random.randint(25, 55)
    total = 3000 + day_idx * new_users
    return total, None, {
        "id":          {"null_rate": 0.0, "distinct_count": float(total)},
        "email":       {"null_rate": 0.0, "distinct_count": float(total)},
        "signup_date": {"null_rate": 0.0, "min": "2023-01-01", "max": "2026-06-01"},
        "country":     {"null_rate": round(random.uniform(0.0, 0.015), 4), "distinct_count": 10.0},
        "plan":        {"null_rate": 0.0, "distinct_count": 3.0},
        "is_active":   {"null_rate": 0.0, "distinct_count": 2.0},
        "created_at":  {
            "null_rate": 0.0,
            "min": "2023-01-01T00:00:00",
            "max": (datetime(2026, 1, 1) + timedelta(days=day_idx)).isoformat(),
        },
    }


def build_products_metrics():
    count = 150
    return count, None, {
        "id":           {"null_rate": 0.0, "distinct_count": float(count)},
        "name":         {"null_rate": 0.0, "distinct_count": float(count)},
        "category":     {"null_rate": 0.0, "distinct_count": 7.0},
        "price":        {
            "null_rate": round(random.uniform(0.0, 0.01), 4),
            "distinct_count": float(count - random.randint(0, 10)),
            "min": round(random.uniform(4.5, 6.0), 2),
            "max": round(random.uniform(990.0, 1010.0), 2),
            "mean": round(random.gauss(320.0, 15.0), 2),
            "stddev": round(random.gauss(280.0, 10.0), 2),
        },
        "stock_count":  {
            "null_rate": 0.0,
            "min": 0.0, "max": 500.0,
            "mean": round(random.gauss(180.0, 20.0), 2),
            "stddev": round(random.gauss(145.0, 10.0), 2),
        },
        "is_available": {"null_rate": 0.0, "distinct_count": 2.0},
    }


def seed_profile_history(conn, table_ids, days=92):
    print(f"\n📊 Seeding {days}-day profile history for {len(table_ids)} tables…")
    fp = "demo_schema_fingerprint_v1"
    today = datetime.now(UTC).replace(hour=2, minute=0, second=0, microsecond=0)

    with conn.cursor() as cur:
        for key, tid in table_ids.items():
            # Remove old synthetic profiles
            cur.execute("DELETE FROM table_profiles WHERE table_id = %s", (tid,))
            print(f"  Inserting {days} profiles for {key}…")

            for d in range(days):
                collected_at = today - timedelta(days=days - d)

                if key == "demo.orders":
                    row_count, freshness, metrics = build_orders_metrics(d, days)
                elif key == "demo.users":
                    row_count, freshness, metrics = build_users_metrics(d)
                else:
                    row_count, freshness, metrics = build_products_metrics()

                cur.execute(
                    """
                    INSERT INTO table_profiles
                      (id, table_id, collected_at, row_count, freshness_seconds,
                       schema_fingerprint, column_metrics, profiling_duration_ms)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        str(uuid.uuid4()), tid, collected_at,
                        row_count, freshness, fp,
                        json.dumps(metrics),
                        random.randint(80, 450),
                    ),
                )

    # Update last_profiled_at so the Tables list shows the correct date
    with conn.cursor() as cur:
        for tid in table_ids.values():
            cur.execute(
                "UPDATE monitored_tables SET last_profiled_at = NOW() - INTERVAL '1 hour' WHERE id = %s",
                (tid,),
            )
    conn.commit()
    print(f"  ✓ Profile history seeded — all 4 detectors now have sufficient baseline")


# ── Step 4: Seed incidents with LLM narrations ────────────────────────────────

P1_NARRATION = {
    "summary": "demo.orders stopped receiving data — row count dropped to 0, indicating a complete pipeline failure on 2026-06-04.",
    "likely_causes": [
        {"hypothesis": "Upstream ETL job crashed or was not triggered, resulting in no new orders loaded into demo.orders", "probability": "high"},
        {"hypothesis": "Source database connection lost during ingestion window — orders exist in source but failed to transfer", "probability": "medium"},
        {"hypothesis": "Table was accidentally truncated or DDL migration ran without a transaction guard", "probability": "low"},
    ],
    "impact_assessment": "All downstream revenue reporting, order fulfilment dashboards, and ML recommendation models relying on demo.orders have zero data for 2026-06-04. Customer-facing order history APIs will return stale data. Estimated revenue visibility gap: 480+ orders (~$79k).",
    "recommended_actions": [
        "Check Airflow/DAG logs for the orders ingestion job — look for exit code != 0 or missing run",
        "Query source system directly: SELECT COUNT(*) FROM source_orders WHERE created_at >= NOW() - INTERVAL '24h'",
        "Inspect warehouse COPY/INSERT logs for errors or zero-row loads",
        "Verify network connectivity between ETL host and warehouse endpoint",
        "Initiate backfill from source system after root cause is confirmed",
    ],
    "data_pattern_notes": "Row count was stable and growing gradually (~480-560/day, trending +15% over 90 days) with consistent freshness ~3600s. The sudden drop to 0 with freshness jumping to 259,200s (72h) indicates a hard stop rather than gradual degradation — consistent with a cron job failure or scheduler misconfiguration.",
    "confidence": "high",
}

P2_NARRATION = {
    "summary": "demo.orders amount column null rate spiked from ~1.5% baseline to 44.8% — consistent with an ETL transformation bug dropping the payment amount field.",
    "likely_causes": [
        {"hypothesis": "ETL pipeline field mapping broke after source schema change — amount field renamed or moved", "probability": "high"},
        {"hypothesis": "Payment processor webhook payload changed format, causing null deserialization on the amount attribute", "probability": "medium"},
        {"hypothesis": "Database column type mismatch causing silent cast failure for non-integer amounts", "probability": "low"},
    ],
    "impact_assessment": "44.8% of orders have no amount recorded. Revenue aggregations will undercount by approximately half. Any SLA or billing calculations based on this table are currently unreliable. Financial reporting must be halted until data is corrected.",
    "recommended_actions": [
        "Query demo.orders WHERE amount IS NULL AND created_at >= NOW() - INTERVAL '24h' to scope affected rows",
        "Check ETL transformation logs for field mapping errors or type cast warnings",
        "Compare source system payload schema against the current ETL extraction template",
        "Run backfill query against source to recover the null amounts",
        "Add a NOT NULL constraint alert on amount column to detect this earlier next time",
    ],
    "data_pattern_notes": "Amount null rate was stable at 1.2-2.8% for 90 days (baseline null = missing optional promo orders). The jump to 44.8% in a single profile run is a clean step-function — not a gradual drift — strongly suggesting a code deployment or schema change event.",
    "confidence": "high",
}

P3_NARRATION = {
    "summary": "demo.orders row count showed a statistically significant deviation from seasonal baseline — z-score of 3.4σ above the 14-day rolling mean.",
    "likely_causes": [
        {"hypothesis": "Flash sale or marketing campaign drove above-normal order volume", "probability": "high"},
        {"hypothesis": "Duplicate ingestion run — same batch processed twice", "probability": "medium"},
    ],
    "impact_assessment": "Row count 38% above baseline. If legitimate traffic, reporting looks healthy. If duplication, revenue totals and inventory calculations are overstated. Investigate before closing.",
    "recommended_actions": [
        "Check for duplicate order IDs: SELECT id, COUNT(*) FROM demo.orders GROUP BY id HAVING COUNT(*) > 1",
        "Verify with marketing team whether a campaign ran today",
        "Check ingestion job logs for any duplicate execution",
    ],
    "data_pattern_notes": "Row count typically follows a weekday/weekend pattern with ~15% weekend dip. This spike occurred on a Tuesday (historically high-volume) but exceeded even the highest weekday baseline by 38%. IsoForest scored this as anomalous with decision function = -0.18.",
    "confidence": "medium",
}


def seed_incidents(conn, table_ids):
    print("\n🚨 Seeding pre-built incidents with LLM narrations…")

    # Get org_id from DB
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM organizations WHERE slug = 'demo-corp' LIMIT 1")
        row = cur.fetchone()
        if not row:
            cur.execute("SELECT id FROM organizations LIMIT 1")
            row = cur.fetchone()
        if not row:
            print("  ✗ No org found — run --full first")
            return
        org_id = str(row[0])

    orders_id = table_ids.get("demo.orders")
    if not orders_id:
        print("  ✗ demo.orders not monitored")
        return

    # Remove old demo incidents
    with conn.cursor() as cur:
        cur.execute("DELETE FROM incidents WHERE org_id = %s", (org_id,))
    conn.commit()

    today = datetime.now(UTC)
    incidents = [
        {
            "id": str(uuid.uuid4()),
            "org_id": org_id,
            "table_id": orders_id,
            "severity": "P1",
            "status": "open",
            "title": "[P1] demo.orders — row count dropped to 0 (pipeline failure)",
            "fired_checks": json.dumps([
                {"check_name": "row_count_zero", "check_type": "rule",
                 "observed_value": 0, "expected_range": {"low": 380, "high": 600}, "deviation_score": None},
                {"check_name": "freshness_sla_breach", "check_type": "rule",
                 "observed_value": 259200, "expected_range": {"low": 0, "high": 5400}, "deviation_score": None},
            ]),
            "llm_narration": json.dumps(P1_NARRATION),
            "created_at": today - timedelta(hours=2),
            "acknowledged_at": None,
            "resolved_at": None,
        },
        {
            "id": str(uuid.uuid4()),
            "org_id": org_id,
            "table_id": orders_id,
            "severity": "P2",
            "status": "acknowledged",
            "title": "[P2] demo.orders — null_rate_amount spiked from 1.5% to 44.8%",
            "fired_checks": json.dumps([
                {"check_name": "null_rate_spike", "check_type": "rule",
                 "observed_value": 0.448, "expected_range": {"low": 0.0, "high": 0.05}, "deviation_score": None},
                {"check_name": "z_score_null_rate__amount", "check_type": "z_score",
                 "column_name": "amount", "observed_value": 0.448, "expected_range": {"low": 0.005, "high": 0.035},
                 "deviation_score": 11.3},
            ]),
            "llm_narration": json.dumps(P2_NARRATION),
            "created_at": today - timedelta(days=3, hours=6),
            "acknowledged_at": today - timedelta(days=3, hours=5),
            "resolved_at": None,
        },
        {
            "id": str(uuid.uuid4()),
            "org_id": org_id,
            "table_id": orders_id,
            "severity": "P3",
            "status": "resolved",
            "title": "[P3] demo.orders — row_count anomalous (z-score 3.4σ, IsoForest)",
            "fired_checks": json.dumps([
                {"check_name": "z_score_row_count", "check_type": "z_score",
                 "observed_value": 724, "expected_range": {"low": 420, "high": 590},
                 "deviation_score": 3.41},
                {"check_name": "isolation_forest", "check_type": "isoforest",
                 "observed_value": -0.18, "expected_range": {"low": -0.1, "high": 1.0}, "deviation_score": None},
            ]),
            "llm_narration": json.dumps(P3_NARRATION),
            "created_at": today - timedelta(days=7),
            "acknowledged_at": today - timedelta(days=7, minutes=-30),
            "resolved_at": today - timedelta(days=6, hours=22),
        },
    ]

    with conn.cursor() as cur:
        for inc in incidents:
            cur.execute(
                """
                INSERT INTO incidents
                  (id, org_id, table_id, severity, status, title,
                   fired_checks, llm_narration, created_at, acknowledged_at, resolved_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    inc["id"], inc["org_id"], inc["table_id"],
                    inc["severity"], inc["status"], inc["title"],
                    inc["fired_checks"], inc["llm_narration"],
                    inc["created_at"], inc["acknowledged_at"], inc["resolved_at"],
                ),
            )
    conn.commit()
    print(f"  ✓ 3 incidents seeded: P1 (open), P2 (acknowledged), P3 (resolved)")
    return incidents[0]["id"]  # return P1 incident id


# ── Step 5: Anomaly injection ──────────────────────────────────────────────────

def inject_pipeline_failure(conn):
    print("  Injecting: pipeline_failure — deleting recent orders…")
    with conn.cursor() as cur:
        cutoff = datetime.now(UTC) - timedelta(days=3)
        cur.execute("DELETE FROM demo.orders WHERE created_at >= %s", (cutoff,))
        deleted = cur.rowcount
    conn.commit()
    print(f"  ✓ Deleted {deleted:,} recent orders — demo.orders now returns 0 rows")


def inject_null_spike(conn):
    print("  Injecting: null_spike — nullifying 45% of order amounts…")
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM demo.orders")
        total = cur.fetchone()[0]
        target = int(total * 0.45)
        cur.execute(
            "UPDATE demo.orders SET amount = NULL "
            "WHERE id IN (SELECT id FROM demo.orders ORDER BY random() LIMIT %s)",
            (target,),
        )
    conn.commit()
    print(f"  ✓ Nullified ~{target:,} amount values")


def inject_schema_drift(conn):
    print("  Injecting: schema_drift — dropping 'status' column…")
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE demo.orders DROP COLUMN IF EXISTS status")
    conn.commit()
    print("  ✓ Column 'status' dropped from demo.orders")


def inject_row_explosion(conn):
    print("  Injecting: row_explosion — inserting 15× normal daily volume…")
    with conn.cursor() as cur:
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        rows = []
        for _ in range(480 * 15):
            ts = today + timedelta(hours=random.randint(0, 23), minutes=random.randint(0, 59))
            rows.append((
                random.randint(1, 3000), random.randint(1, 150),
                round(random.uniform(5, 850), 2), random.choice(STATUSES),
                random.choice(COUNTRIES), ts,
            ))
        cur.executemany(
            "INSERT INTO demo.orders (user_id, product_id, amount, status, country, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            rows,
        )
    conn.commit()
    print(f"  ✓ Inserted {len(rows):,} rows — 15× spike")


SCENARIOS = {
    "pipeline_failure": inject_pipeline_failure,
    "null_spike":       inject_null_spike,
    "schema_drift":     inject_schema_drift,
    "row_explosion":    inject_row_explosion,
}


def trigger_run_and_wait(table_key, table_ids, timeout=60):
    tid = table_ids.get(table_key)
    if not tid:
        print(f"  ✗ {table_key} not found in monitored tables")
        return

    r = api("POST", f"/api/v1/tables/{tid}/run")
    if r.status_code not in (200, 201):
        print(f"  ✗ Failed to trigger run for {table_key}")
        return

    task_id = r.json()["task_id"]
    print(f"  ⏳ Profile task queued: {task_id} — waiting up to {timeout}s…", end="", flush=True)

    deadline = time.time() + timeout
    last_profile_id = None
    while time.time() < deadline:
        time.sleep(3)
        tr = api("GET", f"/api/v1/tables/{tid}", silent=True)
        if tr.status_code == 200:
            t = tr.json()
            if t.get("latest_profile") and t["latest_profile"].get("id") != last_profile_id:
                p = t["latest_profile"]
                status = "error" if p.get("error") else "ok"
                print(f" done ({status}, {p.get('row_count', '?')} rows, {p.get('profiling_duration_ms', '?')}ms)")
                return
        print(".", end="", flush=True)
    print(" timeout")


# ── Main ───────────────────────────────────────────────────────────────────────

def cmd_full():
    print("\n🚀 DataWatch Full Demo Setup")
    print("=" * 50)

    # Pre-flight
    if not check_api():
        print("✗ API not reachable at", API_URL)
        print("  Make sure docker-compose is running: docker compose up -d")
        sys.exit(1)
    print("✓ API healthy")

    conn = get_conn()

    # 1. Demo data
    create_demo_schema(conn)
    seed_users(conn)
    seed_products(conn)
    seed_orders(conn)
    seed_events(conn)

    # 2. DataWatch setup
    source_id, table_ids = setup_datawatch(conn)

    if not table_ids:
        print("✗ No tables registered — aborting")
        conn.close()
        sys.exit(1)

    # 3. Profile history (90 days)
    seed_profile_history(conn, table_ids)

    # 4. Pre-built incidents with narrations
    p1_id = seed_incidents(conn, table_ids)

    # 5. Inject P1 scenario + trigger a live run so the UI shows fresh data
    orders_id = table_ids.get("demo.orders")
    if orders_id:
        print("\n⚡ Triggering live profile run on demo.orders…")
        trigger_run_and_wait("demo.orders", table_ids, timeout=45)

    conn.close()

    print("\n" + "=" * 50)
    print("✅  Demo ready!")
    print(f"\n  🌐  http://localhost:3000")
    print(f"  📧  {DEMO_EMAIL}")
    print(f"  🔑  {DEMO_PASSWORD}")
    print(f"\n  Open Incidents: 1× P1 open, 1× P2 acknowledged")
    print(f"  Tables: demo.orders · demo.users · demo.products")
    print(f"  Profile history: 90+ days (all 4 detectors active)")
    print(f"\n  Inject a new anomaly:")
    print(f"  python scripts/seed_demo.py --scenario pipeline_failure")
    print(f"  python scripts/seed_demo.py --scenario null_spike")


def cmd_reset():
    print("\n♻️  Resetting demo…")
    if not check_api():
        print("✗ API not reachable")
        sys.exit(1)

    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS demo CASCADE")
    conn.commit()
    conn.close()
    print("  ✓ Demo schema dropped")
    cmd_full()


def cmd_scenario(name):
    if not check_api():
        print("✗ API not reachable")
        sys.exit(1)

    if not login(DEMO_EMAIL, DEMO_PASSWORD):
        print(f"✗ Cannot login as {DEMO_EMAIL} — run --full first")
        sys.exit(1)

    r = api("GET", "/api/v1/tables")
    table_ids = {f"{t['schema_name']}.{t['table_name']}": t["id"] for t in r.json()} if r.status_code == 200 else {}

    if not table_ids:
        print("✗ No monitored tables found — run --full first")
        sys.exit(1)

    conn = get_conn()
    print(f"\n💉 Injecting scenario: {name}")
    SCENARIOS[name](conn)
    conn.close()

    print("\n⚡ Triggering profile run on demo.orders…")
    trigger_run_and_wait("demo.orders", table_ids, timeout=60)

    print(f"\n✅ Scenario '{name}' complete.")
    print(f"   Check the Incidents page: http://localhost:3000/incidents")
    print(f"   (LLM narration may take 10-30s to generate in the background)")


def main():
    parser = argparse.ArgumentParser(description="DataWatch demo seed")
    parser.add_argument("--full", action="store_true", help="Full setup from scratch")
    parser.add_argument("--reset", action="store_true", help="Drop demo + re-run full setup")
    parser.add_argument("--scenario", choices=list(SCENARIOS.keys()), help="Inject an anomaly scenario")
    args = parser.parse_args()

    if not any([args.full, args.reset, args.scenario]):
        parser.print_help()
        sys.exit(1)

    if not DB_URL or "localhost" not in DB_URL and "5433" not in DB_URL:
        # Construct default
        pass

    if args.reset:
        cmd_reset()
    elif args.full:
        cmd_full()
    elif args.scenario:
        cmd_scenario(args.scenario)


if __name__ == "__main__":
    main()
