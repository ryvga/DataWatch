#!/usr/bin/env python3
"""
DataWatch comprehensive multi-workspace demo seed.

Creates 3 workspaces with realistic data:
  • acme-corp     (Agency plan)   — orders, users, products tables, active P1 incident
  • startup-io    (Growth plan)   — events, sessions, users tables, P2 incident resolved
  • retail-demo   (Starter plan)  — inventory, orders tables, healthy state
  + Staff account: admin@datawatch.io / admin1234

Usage:
  python scripts/seed_demo.py --full     # complete fresh setup
  python scripts/seed_demo.py --reset    # drop demo orgs + re-run --full
  python scripts/seed_demo.py --status   # show what's seeded

Login URLs (local dev):
  App:   http://localhost:5173  →  workspace: acme-corp  email: mounir@acme.io  pass: demo1234
  Admin: http://localhost:5173/admin  →  email: admin@datawatch.io  pass: admin1234

Environment:
  DB_URL        postgresql://datawatch:datawatch@localhost:5433/datawatch
  API_URL       http://localhost:8000
"""

import argparse
import json
import os
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta

import psycopg2
import requests

# ── Config ─────────────────────────────────────────────────────────────────────

DB_URL = os.environ.get(
    "DB_URL",
    os.environ.get("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
    or "postgresql://datawatch:datawatch@localhost:5433/datawatch",
)
API_URL = os.environ.get("API_URL", "http://localhost:8000")

STAFF_EMAIL = "admin@datawatch.io"
STAFF_PASSWORD = "admin1234"

WORKSPACES = [
    {
        "slug": "acme-corp",
        "name": "Acme Corp",
        "plan": "growth",
        "email": "mounir@acme.io",
        "password": "demo1234",
        "description": "E-commerce (live demo-db): 4 incidents — P1 payment null spike, P2 email duplicates, P2 negative prices, P3 freshness",
    },
    {
        "slug": "startup-io",
        "name": "Startup.io",
        "plan": "growth",
        "email": "dev@startup.io",
        "password": "demo1234",
        "description": "SaaS analytics (live analytics-db): 4 incidents — P1 user_id null spike, P2 zero sessions, P3 row drop, P2 resolved schema drift",
    },
    {
        "slug": "retail-demo",
        "name": "Retail Demo",
        "plan": "starter",
        "email": "admin@retail.demo",
        "password": "demo1234",
        "description": "Retail (mocked): 3 incidents — P1 payment null, P2 schema drift, P2 email cardinality drop",
    },
]

random.seed(42)

# ── Helpers ────────────────────────────────────────────────────────────────────

def db_conn():
    return psycopg2.connect(DB_URL)


def now():
    return datetime.now(UTC)


def ago(days=0, hours=0, minutes=0):
    return now() - timedelta(days=days, hours=hours, minutes=minutes)


# ── API helpers ────────────────────────────────────────────────────────────────

_tokens = {}  # slug → token


def _headers(slug=None):
    token = _tokens.get(slug)
    if token:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    return {"Content-Type": "application/json"}


def api(method, path, slug=None, silent=False, **kwargs):
    resp = requests.request(method, f"{API_URL}{path}", headers=_headers(slug), timeout=30, **kwargs)
    if not silent and resp.status_code >= 400:
        print(f"  ⚠ {method} {path} → {resp.status_code}: {resp.text[:200]}")
    return resp


def register(ws):
    r = requests.post(f"{API_URL}/auth/register", json={
        "org_name": ws["name"],
        "org_slug": ws["slug"],
        "email": ws["email"],
        "password": ws["password"],
    }, timeout=10)
    if r.status_code == 201:
        print(f"  ✓ Registered: {ws['slug']}")
        return True
    if r.status_code == 409:
        print(f"  ℹ Already exists: {ws['slug']}")
        return False
    print(f"  ✗ Register failed: {r.text[:100]}")
    return False


def login_ws(ws):
    r = requests.post(f"{API_URL}/auth/login", json={
        "email": ws["email"],
        "password": ws["password"],
        "org_slug": ws["slug"],
    }, timeout=10)
    if r.status_code == 200:
        _tokens[ws["slug"]] = r.json()["access_token"]
        return True
    print(f"  ✗ Login failed for {ws['slug']}: {r.text[:100]}")
    return False


def staff_login():
    r = requests.post(f"{API_URL}/auth/staff/login", json={
        "email": STAFF_EMAIL,
        "password": STAFF_PASSWORD,
    }, timeout=10)
    if r.status_code == 200:
        _tokens["staff"] = r.json()["access_token"]
        print(f"  ✓ Staff logged in")
        return True
    print(f"  ✗ Staff login failed (is STAFF_PASSWORD set in .env?): {r.text[:100]}")
    return False


# ── Direct DB seeding (for historical data that API can't create) ──────────────

def seed_source(conn, org_id, name, source_type, config):
    from app.services.crypto import encrypt_config
    encrypted = encrypt_config(config, str(org_id))
    sid = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO data_sources (id, org_id, name, type, connection_config, status, last_connected_at, created_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, 'connected', NOW(), NOW())
            ON CONFLICT DO NOTHING
        """, (sid, org_id, name, source_type, json.dumps({"encrypted": encrypted})))
    conn.commit()
    return sid


def seed_table(conn, source_id, schema, table, freshness_col="created_at", interval=60):
    tid = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO monitored_tables
              (id, source_id, schema_name, table_name, freshness_column,
               check_interval_minutes, sensitivity, is_active, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, 3.0, true, NOW())
            ON CONFLICT DO NOTHING
        """, (tid, source_id, schema, table, freshness_col, interval))
    conn.commit()
    return tid


def seed_profile(conn, table_id, row_count, freshness_seconds, columns, offset_hours=0):
    """Insert a historical table profile. Always updates last_profiled_at on the table."""
    pid = str(uuid.uuid4())
    # Build column_metrics from columns list
    col_metrics = {}
    for col in columns:
        col_metrics[col["name"]] = {
            "null_rate": col.get("null_rate", random.uniform(0, 0.05)),
            "distinct_count": col.get("distinct_count", int(row_count * random.uniform(0.1, 0.9))),
            "cardinality_ratio": col.get("cardinality_ratio", random.uniform(0.05, 0.95)),
        }
        if col.get("category") == "numeric":
            v = col.get("base_value", 100)
            noise = random.uniform(0.85, 1.15)
            col_metrics[col["name"]].update({
                "min": round(v * 0.1 * noise, 2),
                "max": round(v * 10 * noise, 2),
                "mean": round(v * noise, 2),
                "stddev": round(v * 0.15 * noise, 2),
            })
    schema_fp = f"fp_{hash(str([c['name'] for c in columns])) % 100000:05d}"
    ts = ago(hours=offset_hours)
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO table_profiles
              (id, table_id, row_count, freshness_seconds, schema_fingerprint,
               column_metrics, profiling_duration_ms, collected_at)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
        """, (pid, table_id, row_count, freshness_seconds, schema_fp,
              json.dumps(col_metrics), random.randint(80, 500), ts))
        # Keep last_profiled_at updated with the most recent profile
        if offset_hours == 0:
            cur.execute("UPDATE monitored_tables SET last_profiled_at=%s WHERE id=%s", (ts, table_id))
    conn.commit()
    return pid


def seed_incident(conn, org_id, table_id, profile_id, severity, title, check_name, check_type, obs, expected, narration, offset_hours=2):
    iid = str(uuid.uuid4())
    ts = ago(hours=offset_hours)
    if obs is not None and expected is not None:
        deviation = round((obs - expected) / max(abs(expected) * 0.1, 1), 2)
    else:
        deviation = None
    fired = [{
        "check_name": check_name,
        "check_type": check_type,
        "status": "failed",
        "observed_value": obs,
        "deviation_score": deviation,
    }]
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO incidents
              (id, org_id, table_id, severity, status, title,
               fired_checks, llm_narration, created_at)
            VALUES (%s, %s, %s, %s, 'open', %s, %s::jsonb, %s::jsonb, %s)
        """, (iid, org_id, table_id, severity, title,
              json.dumps(fired), json.dumps(narration), ts))
    conn.commit()
    return iid


def seed_check_results(conn, table_id, profile_id, checks):
    with conn.cursor() as cur:
        for ck in checks:
            cur.execute("""
                INSERT INTO check_results
                  (id, table_id, profile_id, check_type, check_name, status,
                   observed_value, expected_range, deviation_score, checked_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, NOW())
            """, (str(uuid.uuid4()), table_id, profile_id,
                  ck["check_type"], ck["check_name"], ck["status"],
                  ck.get("observed"), json.dumps(ck.get("expected_range")), ck.get("score")))
    conn.commit()


# ── Org lookup ─────────────────────────────────────────────────────────────────

def get_org_id(conn, slug):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM organizations WHERE slug=%s", (slug,))
        row = cur.fetchone()
        return row[0] if row else None


# ── Column schemas ─────────────────────────────────────────────────────────────

ORDERS_COLS = [
    {"name": "id", "category": "numeric", "base_value": 1, "distinct_count": 50000},
    {"name": "user_id", "category": "numeric", "base_value": 1, "null_rate": 0.001},
    {"name": "total_amount", "category": "numeric", "base_value": 120},
    {"name": "status", "category": "text", "distinct_count": 5},
    {"name": "payment_status", "category": "text", "distinct_count": 4, "null_rate": 0.008},
    {"name": "created_at", "category": "timestamp"},
    {"name": "country", "category": "text", "distinct_count": 20},
]

USERS_COLS = [
    {"name": "id", "category": "numeric", "base_value": 1, "distinct_count": 12000},
    {"name": "email", "category": "text", "distinct_count": 11900, "null_rate": 0.001},
    {"name": "name", "category": "text", "distinct_count": 11500, "null_rate": 0.02},
    {"name": "plan", "category": "text", "distinct_count": 4},
    {"name": "created_at", "category": "timestamp"},
]

PRODUCTS_COLS = [
    {"name": "id", "category": "numeric", "base_value": 1, "distinct_count": 3500},
    {"name": "name", "category": "text", "distinct_count": 3490},
    {"name": "price", "category": "numeric", "base_value": 80},
    {"name": "stock", "category": "numeric", "base_value": 150},
    {"name": "category", "category": "text", "distinct_count": 12},
    {"name": "created_at", "category": "timestamp"},
]

EVENTS_COLS = [
    {"name": "id", "category": "text", "distinct_count": 500000},
    {"name": "user_id", "category": "text", "distinct_count": 8000, "null_rate": 0.12},
    {"name": "event_name", "category": "text", "distinct_count": 45},
    {"name": "properties", "category": "text"},
    {"name": "created_at", "category": "timestamp"},
]

SESSIONS_COLS = [
    {"name": "id", "category": "text", "distinct_count": 180000},
    {"name": "user_id", "category": "text", "distinct_count": 7500, "null_rate": 0.05},
    {"name": "started_at", "category": "timestamp"},
    {"name": "duration_seconds", "category": "numeric", "base_value": 280},
    {"name": "pages_visited", "category": "numeric", "base_value": 5},
]

INVENTORY_COLS = [
    {"name": "sku", "category": "text", "distinct_count": 8000},
    {"name": "product_name", "category": "text", "distinct_count": 7900},
    {"name": "quantity", "category": "numeric", "base_value": 200},
    {"name": "cost_price", "category": "numeric", "base_value": 45},
    {"name": "location", "category": "text", "distinct_count": 12},
    {"name": "updated_at", "category": "timestamp"},
]


# ── Seed a workspace ───────────────────────────────────────────────────────────

def seed_acme(conn, org_id):
    """Agency workspace: connects to the real demo-db docker container with active P1 incident."""
    print("  → Seeding acme-corp data (connected to demo-db)...")
    # This points to the real demo-db Docker container seeded by demo_db_init.sql
    sid = seed_source(conn, org_id, "Shop Demo DB (live)", "postgres", {
        "host": "demo-db",  # Docker service name; use "localhost" port 5434 for local dev
        "port": 5432,
        "database": "shopDemo",
        "username": "readonly_user",
        "password": "readonly_pass",
    })
    # Second source — the shared analytics-db Docker container
    sid2 = seed_source(conn, org_id, "Analytics Warehouse", "postgres", {
        "host": "analytics-db", "port": 5432, "database": "analyticsdb",
        "username": "analytics_ro", "password": "readonly_pass",
    })

    orders_tid = seed_table(conn, sid, "public", "orders", "created_at", 30)
    users_tid = seed_table(conn, sid, "public", "users", "created_at", 60)
    products_tid = seed_table(conn, sid, "public", "products", "created_at", 120)

    # 90-day history for orders
    base_rows = 50000
    for h in range(90 * 24, 0, -6):
        drift = 1 + random.uniform(-0.04, 0.06)
        seed_profile(conn, orders_tid, int(base_rows * drift), random.randint(20, 45) * 60,
                     ORDERS_COLS, offset_hours=h)
        base_rows = int(base_rows * (1 + random.uniform(-0.002, 0.003)))

    # Latest profile — ANOMALY: null spike on payment_status
    anomaly_cols = [c.copy() for c in ORDERS_COLS]
    for c in anomaly_cols:
        if c["name"] == "payment_status":
            c["null_rate"] = 0.184  # Was 0.8%, now 18.4%
    current_pid = seed_profile(conn, orders_tid, base_rows + 120, 18 * 60, anomaly_cols, offset_hours=0)

    seed_check_results(conn, orders_tid, current_pid, [
        {"check_type": "rule", "check_name": "null_rate_spike", "status": "failed",
         "observed": 0.184, "expected_range": {"low": 0.0, "high": 0.028}, "score": 14.2},
        {"check_type": "z_score", "check_name": "z_score_null_rate__payment_status", "status": "failed",
         "observed": 0.184, "expected_range": {"low": -0.02, "high": 0.02}, "score": 8.7},
        {"check_type": "rule", "check_name": "row_count_zero", "status": "passed",
         "observed": base_rows, "expected_range": {"low": 1, "high": None}, "score": None},
        {"check_type": "rule", "check_name": "freshness_sla_breach", "status": "failed",
         "observed": 18 * 60, "expected_range": {"low": 0, "high": 45 * 60}, "score": None},
    ])

    # P1 incident — payment_status null spike
    seed_incident(conn, org_id, orders_tid, current_pid, "P1",
        "orders.payment_status — null rate spike (0.8% → 18.4%)",
        "null_rate_spike", "rule", 0.184, 0.028,
        {
            "summary": "The orders table experienced a 23× increase in null payment_status values. Null rate jumped from 0.8% to 18.4%, affecting approximately 9,200 rows in the last 4 hours.",
            "likely_causes": [
                {"hypothesis": "A recent checkout API change removed payment_status from the order creation payload", "probability": "high"},
                {"hypothesis": "Failed webhook from payment processor not writing back payment_status", "probability": "medium"},
                {"hypothesis": "Database migration removed NOT NULL constraint on payment_status", "probability": "low"},
            ],
            "impact_assessment": "Revenue reporting, order fulfillment dashboards, and billing reconciliation are affected. Approximately 9,200 orders have incomplete payment data.",
            "recommended_actions": [
                "Check recent checkout service deployments (last 6 hours)",
                "Inspect payment webhook logs for failures",
                "Run: SELECT * FROM orders WHERE payment_status IS NULL AND created_at >= NOW() - INTERVAL '6h' LIMIT 100",
                "Verify payment_status is being set in the order creation flow",
            ],
            "data_pattern_notes": "The spike started abruptly 4 hours ago, suggesting a deployment or configuration change rather than gradual drift.",
            "confidence": "high",
        },
        offset_hours=4,
    )

    # Users — 60 days history + P2 duplicate incident
    for h in range(60 * 24, 0, -12):
        rows = 12000 + h * 2 + random.randint(-50, 50)
        seed_profile(conn, users_tid, rows, random.randint(5, 25) * 60, USERS_COLS, offset_hours=h)
    # Latest users profile — low uniqueness on email (duplicate emails detected)
    dup_cols = [c.copy() for c in USERS_COLS]
    for c in dup_cols:
        if c["name"] == "email":
            c["distinct_count"] = 11800  # was 11950, dropped → duplicates
    users_pid = seed_profile(conn, users_tid, 12450, 2 * 60, dup_cols)
    seed_incident(conn, org_id, users_tid, users_pid, "P2",
        "users.email — uniqueness drop detected (duplicate emails)",
        "uniqueness_drop", "rule", 0.9517, 0.99,
        {
            "summary": "The users table email column uniqueness ratio dropped from 99.5% to 95.2%, indicating approximately 350 duplicate email addresses were inserted.",
            "likely_causes": [
                {"hypothesis": "A data migration or batch import ran without uniqueness validation", "probability": "high"},
                {"hypothesis": "The UNIQUE constraint on users.email was temporarily dropped during a migration", "probability": "medium"},
            ],
            "impact_assessment": "User authentication and communications may be affected. Duplicate emails can cause login issues, double notifications, and inaccurate user counts in reports.",
            "recommended_actions": [
                "Run: SELECT email, COUNT(*) FROM users GROUP BY email HAVING COUNT(*) > 1 ORDER BY 2 DESC LIMIT 50",
                "Identify when duplicates were inserted: SELECT email, MIN(created_at), MAX(created_at) FROM users GROUP BY email HAVING COUNT(*) > 1",
                "Review recent batch imports and migrations",
                "Re-add UNIQUE constraint after deduplication",
            ],
            "debug_queries": [
                "SELECT email, COUNT(*) as count FROM users GROUP BY email HAVING COUNT(*) > 1 ORDER BY 2 DESC LIMIT 50",
                "SELECT COUNT(*) as total_users, COUNT(DISTINCT email) as unique_emails, COUNT(*) - COUNT(DISTINCT email) as duplicates FROM users",
            ],
            "client_safe_summary": "A data quality issue was detected in user account records. The engineering team is investigating and will resolve the issue.",
            "confidence": "high",
        },
        offset_hours=2,
    )

    # Products — 30 days, healthy
    for h in range(30 * 24, 0, -24):
        seed_profile(conn, products_tid, 3400 + random.randint(-20, 30), 0, PRODUCTS_COLS, offset_hours=h)
    seed_profile(conn, products_tid, 3520, 0, PRODUCTS_COLS)

    # P3 incident — orders freshness (data not updated for 3 hours)
    seed_incident(conn, org_id, orders_tid, current_pid, "P3",
        "orders — freshness warning (3.2h since last update, expected <1h)",
        "freshness_sla_breach", "rule", 11520, 3600,
        {
            "summary": "The orders table has not received new data for 3.2 hours. The expected update interval is 1 hour.",
            "likely_causes": [
                {"hypothesis": "ETL job or data pipeline failed silently", "probability": "high"},
                {"hypothesis": "Database connection pool exhausted on the source system", "probability": "medium"},
            ],
            "impact_assessment": "Real-time order tracking and inventory dashboards may show stale data. SLA breach if data is not updated within 30 minutes.",
            "recommended_actions": [
                "Check ETL job logs for errors",
                "Run: SELECT MAX(created_at), NOW() - MAX(created_at) AS lag FROM orders",
                "Verify source system connectivity",
            ],
            "debug_queries": [
                "SELECT MAX(created_at) as last_order, NOW() - MAX(created_at) as lag FROM orders",
                "SELECT date_trunc('hour', created_at) as hour, COUNT(*) FROM orders WHERE created_at > NOW() - INTERVAL '24h' GROUP BY 1 ORDER BY 1 DESC",
            ],
            "client_safe_summary": "Order data is experiencing a brief delay. Our team is monitoring the situation.",
            "data_pattern_notes": "Orders table normally updates every 15-30 minutes. The gap started 3.2 hours ago.",
            "confidence": "high",
        },
        offset_hours=3,
    )

    # P2 incident — products price anomaly (negative prices injected by bad import)
    products_pid = seed_profile(conn, products_tid, 3520, 0, PRODUCTS_COLS)
    seed_incident(conn, org_id, products_tid, products_pid, "P2",
        "products — negative price values detected (bad data import)",
        "negative_rate", "rule", 0.043, 0.0,
        {
            "summary": "4.3% of product prices are now negative values, affecting approximately 152 products. This started 2 hours ago and coincides with a bulk import job.",
            "likely_causes": [
                {"hypothesis": "Bulk import script did not validate prices before insertion, allowing negative values from the source CSV", "probability": "high"},
                {"hypothesis": "A discount calculation bug applied an absolute value sign flip to the price column", "probability": "medium"},
            ],
            "impact_assessment": "Customers seeing negative-priced products in the catalog. Checkout flow may compute negative totals. Revenue reporting will show understated figures.",
            "recommended_actions": [
                "Run: SELECT id, name, price FROM products WHERE price < 0 LIMIT 50",
                "Roll back or fix the bulk import job",
                "Add a CHECK constraint: ALTER TABLE products ADD CONSTRAINT price_positive CHECK (price >= 0)",
                "Audit any orders placed in the last 2 hours for pricing errors",
            ],
            "debug_queries": [
                "SELECT COUNT(*), AVG(price), MIN(price) FROM products WHERE price < 0",
                "SELECT * FROM products WHERE price < 0 ORDER BY created_at DESC LIMIT 20",
            ],
            "confidence": "high",
        },
        offset_hours=2,
    )

    print(f"  ✓ acme-corp: 3 tables, 4 incidents (1×P1, 2×P2, 1×P3)")


EVENTS_EXTENDED_COLS = [
    {"name": "id", "category": "text", "distinct_count": 500000},
    {"name": "user_id", "category": "text", "distinct_count": 8000, "null_rate": 0.02},
    {"name": "event_name", "category": "text", "distinct_count": 45},
    {"name": "event_type", "category": "text", "distinct_count": 3},
    {"name": "properties", "category": "text"},
    {"name": "session_id", "category": "text", "distinct_count": 120000},
    {"name": "created_at", "category": "timestamp"},
]

SESSIONS_EXTENDED_COLS = [
    {"name": "id", "category": "text", "distinct_count": 180000},
    {"name": "user_id", "category": "text", "distinct_count": 7500, "null_rate": 0.05},
    {"name": "started_at", "category": "timestamp"},
    {"name": "ended_at", "category": "timestamp"},
    {"name": "duration_seconds", "category": "numeric", "base_value": 280},
    {"name": "pages_visited", "category": "numeric", "base_value": 5},
    {"name": "country", "category": "text", "distinct_count": 5},
]


def seed_startup(conn, org_id):
    """Growth workspace: connects to analytics-db. Multiple active incidents + resolved ones."""
    print("  → Seeding startup-io data (connected to analytics-db)...")
    # Live analytics-db Docker container
    sid = seed_source(conn, org_id, "Analytics DB (live)", "postgres", {
        "host": "analytics-db",
        "port": 5432,
        "database": "analyticsdb",
        "username": "analytics_ro",
        "password": "readonly_pass",
    })
    # Second source for variety
    sid2 = seed_source(conn, org_id, "Data Warehouse (Snowflake)", "snowflake", {
        "account": "xy12345.us-east-1", "user": "ANALYTICS_RO",
        "password": "readonly", "database": "ANALYTICS_DW", "warehouse": "COMPUTE_WH",
    })

    events_tid = seed_table(conn, sid, "public", "events", "created_at", 15)
    sessions_tid = seed_table(conn, sid, "public", "sessions", "started_at", 30)
    users_tid = seed_table(conn, sid, "public", "users", "created_at", 60)

    # Events — 45 days of healthy history, then schema drift 7 days ago
    base = 500000
    for h in range(45 * 24, 7 * 24, -6):
        seed_profile(conn, events_tid, base + random.randint(-1000, 2000), random.randint(5, 20) * 60, EVENTS_COLS, offset_hours=h)

    # Schema drift: event_type column added 7 days ago
    for h in range(7 * 24, 3, -6):
        seed_profile(conn, events_tid, base + random.randint(-500, 1500), random.randint(5, 15) * 60, EVENTS_EXTENDED_COLS, offset_hours=h)

    # Latest profile — P1: user_id null spike (analytics SDK broken)
    anomaly_events_cols = [c.copy() for c in EVENTS_EXTENDED_COLS]
    for c in anomaly_events_cols:
        if c["name"] == "user_id":
            c["null_rate"] = 0.702  # Was 2%, now 70.2% — tracking pipeline broken
    events_pid = seed_profile(conn, events_tid, base + 12000, 1 * 60, anomaly_events_cols, offset_hours=0)

    seed_check_results(conn, events_tid, events_pid, [
        {"check_type": "rule", "check_name": "null_rate_spike", "status": "failed",
         "observed": 0.702, "expected_range": {"low": 0.0, "high": 0.04}, "score": 58.4},
        {"check_type": "z_score", "check_name": "z_score_null_rate__user_id", "status": "failed",
         "observed": 0.702, "expected_range": {"low": -0.05, "high": 0.05}, "score": 32.1},
        {"check_type": "rule", "check_name": "row_count_zero", "status": "passed",
         "observed": base + 12000, "expected_range": {"low": 1, "high": None}, "score": None},
    ])

    # P1 incident — events.user_id null spike (analytics SDK crash)
    seed_incident(conn, org_id, events_tid, events_pid, "P1",
        "events.user_id — 70.2% null rate (analytics SDK crash)",
        "null_rate_spike", "rule", 0.702, 0.04,
        {
            "summary": "The events table user_id column null rate jumped from 2% to 70.2%, affecting approximately 12,000 events in the last hour. This indicates the analytics SDK is no longer passing user context with events.",
            "likely_causes": [
                {"hypothesis": "A frontend deploy reset the analytics SDK configuration, losing the user identification token", "probability": "high"},
                {"hypothesis": "The auth token refresh flow is silently failing, causing the SDK to lose the user_id mid-session", "probability": "medium"},
                {"hypothesis": "A content security policy change blocked the analytics SDK from accessing cookies", "probability": "low"},
            ],
            "impact_assessment": "User-level attribution for all events in the last hour is lost. Funnel analysis, cohort tracking, and personalization features are broken. Approximately 12,000 anonymous events cannot be attributed.",
            "recommended_actions": [
                "Check the latest frontend deployment for analytics SDK version or configuration changes",
                "Test: analyticsSDK.identify(userId) in browser console — does it throw?",
                "Run: SELECT COUNT(*), MAX(created_at) FROM events WHERE user_id IS NULL AND created_at > NOW() - INTERVAL '2h'",
                "Verify auth token is being passed to analytics SDK initialization",
            ],
            "debug_queries": [
                "SELECT date_trunc('hour', created_at) as hr, COUNT(*) as total, COUNT(user_id) as identified, ROUND(COUNT(CASE WHEN user_id IS NULL THEN 1 END)::NUMERIC/COUNT(*)*100,1) as null_pct FROM events WHERE created_at > NOW() - INTERVAL '6h' GROUP BY 1 ORDER BY 1 DESC",
                "SELECT event_name, COUNT(*) FROM events WHERE user_id IS NULL AND created_at > NOW() - INTERVAL '2h' GROUP BY 1 ORDER BY 2 DESC",
            ],
            "client_safe_summary": "A data collection issue has been detected. The engineering team is investigating and will restore full tracking shortly.",
            "confidence": "high",
        },
        offset_hours=1,
    )

    # Resolved P2 — schema drift (7 days ago)
    iid = str(uuid.uuid4())
    ts = ago(days=7)
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO incidents (id, org_id, table_id, severity, status, title, fired_checks, llm_narration, created_at, resolved_at)
            VALUES (%s, %s, %s, 'P2', 'resolved', 'events — schema drift (event_type column added)', %s::jsonb, %s::jsonb, %s, %s)
        """, (iid, org_id, events_tid,
              json.dumps([{"check_name": "schema_drift", "check_type": "rule", "status": "failed"}]),
              json.dumps({
                  "summary": "A new column event_type was added to the events table. Schema fingerprint changed.",
                  "likely_causes": [{"hypothesis": "Planned schema migration for event categorization", "probability": "high"}],
                  "impact_assessment": "Low impact — additive change. Downstream SELECT * queries may receive unexpected column.",
                  "recommended_actions": ["Update downstream consumers", "Document schema change"],
                  "confidence": "medium",
              }),
              ts, ago(days=6)))
    conn.commit()

    # Sessions — 30 days history, then freshness breach
    base_sess = 180000
    for h in range(30 * 24, 4, -12):
        seed_profile(conn, sessions_tid, base_sess + h * 5 + random.randint(-200, 200), random.randint(3, 10) * 60, SESSIONS_EXTENDED_COLS, offset_hours=h)

    # Latest sessions profile — P2: zero-duration sessions spike
    anomaly_sess_cols = [c.copy() for c in SESSIONS_EXTENDED_COLS]
    for c in anomaly_sess_cols:
        if c["name"] == "duration_seconds":
            c["base_value"] = 0  # Zero-duration sessions spiked
    sessions_pid = seed_profile(conn, sessions_tid, base_sess + 3500, 18 * 60, anomaly_sess_cols, offset_hours=0)

    seed_check_results(conn, sessions_tid, sessions_pid, [
        {"check_type": "z_score", "check_name": "z_score_mean__duration_seconds", "status": "failed",
         "observed": 0.0, "expected_range": {"low": 220.0, "high": 340.0}, "score": -21.3},
        {"check_type": "rule", "check_name": "freshness_sla_breach", "status": "failed",
         "observed": 18 * 60, "expected_range": {"low": 0, "high": 10 * 60}, "score": None},
    ])

    seed_incident(conn, org_id, sessions_tid, sessions_pid, "P2",
        "sessions.duration_seconds — zero-duration spike (session timeout bug)",
        "z_score_mean__duration_seconds", "z_score", 0.0, 280.0,
        {
            "summary": "3,500 sessions in the last 2 hours have duration_seconds = 0, compared to the expected average of 280s. This indicates a session timeout or tracking bug causing premature session closure.",
            "likely_causes": [
                {"hypothesis": "Session close event firing on page load instead of page unload (event listener bug)", "probability": "high"},
                {"hypothesis": "Server-side session expiry timer set to 0 by a misconfigured environment variable", "probability": "medium"},
            ],
            "impact_assessment": "Session duration metrics, engagement analytics, and user journey analysis are completely unreliable. A/B test results for any experiment active in the last 2 hours may be skewed.",
            "recommended_actions": [
                "Check if session_end event is firing correctly: grep logs for 'session_close' events",
                "Run: SELECT AVG(duration_seconds), COUNT(*) FROM sessions WHERE started_at > NOW() - INTERVAL '3h'",
                "Verify SESSION_TIMEOUT environment variable value on all app servers",
            ],
            "debug_queries": [
                "SELECT date_trunc('hour', started_at) as hr, COUNT(*) as total, AVG(duration_seconds) as avg_dur, COUNT(CASE WHEN duration_seconds = 0 THEN 1 END) as zero_dur FROM sessions WHERE started_at > NOW() - INTERVAL '6h' GROUP BY 1 ORDER BY 1 DESC",
            ],
            "confidence": "high",
        },
        offset_hours=2,
    )

    # Users — single healthy profile
    seed_profile(conn, users_tid, 8400, 45 * 60, USERS_COLS)
    seed_incident(conn, org_id, users_tid, seed_profile(conn, users_tid, 8100, 3 * 60, USERS_COLS, offset_hours=0), "P3",
        "users — row count drop detected (−3.5% from baseline)",
        "row_growth_rate", "z_score", -3.5, 0.0,
        {
            "summary": "The users table row count decreased by 3.5% compared to the 14-day baseline. A net decrease in users indicates bulk deletions, hard deletes from a GDPR request batch, or a sync job gone wrong.",
            "likely_causes": [
                {"hypothesis": "GDPR right-to-erasure batch job deleted more accounts than expected", "probability": "medium"},
                {"hypothesis": "A data sync from the CRM accidentally deleted users that were marked 'inactive' in source", "probability": "medium"},
            ],
            "impact_assessment": "Revenue reporting, churn calculations, and user count KPIs will show an unexpected drop. Review any scheduled batch jobs that ran in the last 6 hours.",
            "recommended_actions": [
                "Check deletion audit logs for the last 6 hours",
                "Run: SELECT COUNT(*) FROM users WHERE created_at < NOW() - INTERVAL '1h'",
                "Compare with yesterday's count: SELECT date_trunc('day', NOW()) as today, COUNT(*) FROM users",
            ],
            "confidence": "medium",
        },
        offset_hours=1,
    )

    print(f"  ✓ startup-io: 3 tables, 4 incidents (1×P1, 2×P2/P3 active, 1×P2 resolved)")


CUSTOMER_COLS = [
    {"name": "id", "category": "numeric", "base_value": 1, "distinct_count": 15000},
    {"name": "email", "category": "text", "distinct_count": 14900, "null_rate": 0.002},
    {"name": "name", "category": "text", "distinct_count": 14800, "null_rate": 0.01},
    {"name": "phone", "category": "text", "distinct_count": 13000, "null_rate": 0.08},
    {"name": "region", "category": "text", "distinct_count": 8},
    {"name": "created_at", "category": "timestamp"},
]


def seed_retail(conn, org_id):
    """Starter workspace: 3 active incidents across 3 tables."""
    print("  → Seeding retail-demo data (active incidents)...")
    sid = seed_source(conn, org_id, "Retail PostgreSQL", "postgres", {
        "host": "db.retail.io", "port": 5432, "database": "retail_prod",
        "username": "monitor_ro", "password": "readonly",
    })
    sid2 = seed_source(conn, org_id, "Retail MySQL (legacy)", "mysql", {
        "host": "mysql.retail.io", "port": 3306, "database": "retail_legacy",
        "username": "monitor_user", "password": "readonly",
    })

    inventory_tid = seed_table(conn, sid, "public", "inventory", "updated_at", 60)
    orders_tid = seed_table(conn, sid, "public", "orders", "created_at", 30)
    customers_tid = seed_table(conn, sid, "public", "customers", "created_at", 120)

    # Inventory — 30 days healthy, then schema change
    base_inv_cols = [c.copy() for c in INVENTORY_COLS]
    for h in range(30 * 24, 0, -12):
        seed_profile(conn, inventory_tid, 8000 + random.randint(-50, 100), 0, base_inv_cols, offset_hours=h)

    # Latest inventory profile — schema drift (warehouse_zone column dropped!)
    dropped_cols = [c for c in INVENTORY_COLS if c["name"] != "location"]
    inv_pid = seed_profile(conn, inventory_tid, 8030, 0, dropped_cols, offset_hours=0)

    seed_check_results(conn, inventory_tid, inv_pid, [
        {"check_type": "rule", "check_name": "schema_drift", "status": "failed",
         "observed": None, "expected_range": None, "score": None},
    ])

    seed_incident(conn, org_id, inventory_tid, inv_pid, "P2",
        "inventory — schema drift: location column missing",
        "schema_drift", "rule", None, None,
        {
            "summary": "The inventory table schema fingerprint changed. The 'location' column is no longer present in the profile, suggesting a column drop or rename.",
            "likely_causes": [
                {"hypothesis": "A migration script renamed 'location' to 'warehouse_zone' without updating monitoring config", "probability": "high"},
                {"hypothesis": "An ALTER TABLE DROP COLUMN statement was executed on the wrong environment", "probability": "medium"},
            ],
            "impact_assessment": "Warehouse routing logic that reads the location column will fail silently. Stock picks and fulfillment routing may be broken.",
            "recommended_actions": [
                "Run: SELECT column_name FROM information_schema.columns WHERE table_name='inventory'",
                "Check recent database migration history for DROP COLUMN or RENAME COLUMN statements",
                "Verify fulfillment service is still routing correctly",
            ],
            "confidence": "high",
        },
        offset_hours=3,
    )

    # Orders — 14 days, then freshness + null spike
    for h in range(14 * 24, 0, -6):
        seed_profile(conn, orders_tid, 2400 + h * 2 + random.randint(-30, 30), random.randint(10, 30) * 60, ORDERS_COLS, offset_hours=h)

    orders_null_cols = [c.copy() for c in ORDERS_COLS]
    for c in orders_null_cols:
        if c["name"] == "payment_status":
            c["null_rate"] = 0.31  # 31% nulls — way above normal 1%
    orders_pid = seed_profile(conn, orders_tid, 2800, 6 * 60, orders_null_cols, offset_hours=0)

    seed_check_results(conn, orders_tid, orders_pid, [
        {"check_type": "rule", "check_name": "null_rate_spike", "status": "failed",
         "observed": 0.31, "expected_range": {"low": 0.0, "high": 0.02}, "score": 26.0},
        {"check_type": "rule", "check_name": "freshness_sla_breach", "status": "failed",
         "observed": 6 * 60, "expected_range": {"low": 0, "high": 45 * 60}, "score": None},
    ])

    seed_incident(conn, org_id, orders_tid, orders_pid, "P1",
        "orders.payment_status — 31% null rate (payment gateway timeout)",
        "null_rate_spike", "rule", 0.31, 0.02,
        {
            "summary": "The orders table payment_status is NULL for 31% of records in the last 6 hours (868 orders), up from the normal 1%. This strongly suggests the payment gateway callback is not reaching the system.",
            "likely_causes": [
                {"hypothesis": "Payment gateway webhook endpoint returned a non-200 status, stopping status updates", "probability": "high"},
                {"hypothesis": "The order processing worker queue is backed up and payment confirmations are delayed", "probability": "medium"},
                {"hypothesis": "SSL certificate on the webhook endpoint expired, causing gateway to reject callbacks", "probability": "medium"},
            ],
            "impact_assessment": "868 orders have no payment status. Revenue recognition, order fulfillment, and inventory deduction are all blocked for these orders. Customer emails for order confirmation are also delayed.",
            "recommended_actions": [
                "Check payment gateway dashboard for failed webhook deliveries",
                "Verify webhook endpoint SSL certificate expiry",
                "Run: SELECT COUNT(*), MAX(created_at) FROM orders WHERE payment_status IS NULL AND created_at > NOW() - INTERVAL '8h'",
                "Check worker queue depth and processing lag",
            ],
            "debug_queries": [
                "SELECT date_trunc('hour', created_at) as hr, COUNT(*) as total, COUNT(CASE WHEN payment_status IS NULL THEN 1 END) as null_count FROM orders WHERE created_at > NOW() - INTERVAL '12h' GROUP BY 1 ORDER BY 1 DESC",
            ],
            "confidence": "high",
        },
        offset_hours=6,
    )

    # Customers table — cardinality drop on email
    for h in range(21 * 24, 0, -24):
        seed_profile(conn, customers_tid, 15000 + random.randint(-20, 30), 3 * 60, CUSTOMER_COLS, offset_hours=h)

    cust_dup_cols = [c.copy() for c in CUSTOMER_COLS]
    for c in cust_dup_cols:
        if c["name"] == "email":
            c["distinct_count"] = 13800  # Was 14900 — dropped 7.4%
            c["cardinality_ratio"] = 0.92
    cust_pid = seed_profile(conn, customers_tid, 15020, 3 * 60, cust_dup_cols, offset_hours=0)

    seed_check_results(conn, customers_tid, cust_pid, [
        {"check_type": "cardinality", "check_name": "cardinality_drop__email", "status": "failed",
         "observed": 0.918, "expected_range": {"low": 0.98, "high": 1.0}, "score": -7.4},
    ])

    seed_incident(conn, org_id, customers_tid, cust_pid, "P2",
        "customers.email — cardinality drop (−7.4%, duplicate emails detected)",
        "cardinality_drop__email", "cardinality", 0.918, 0.99,
        {
            "summary": "The customers table email column uniqueness dropped from 99.3% to 91.8%, suggesting ~1,100 duplicate email addresses were imported. This may cause login conflicts and duplicate marketing sends.",
            "likely_causes": [
                {"hypothesis": "A CRM sync job imported contacts without checking for existing email matches", "probability": "high"},
                {"hypothesis": "A bulk import from a trade show list included emails already in the system", "probability": "medium"},
            ],
            "impact_assessment": "Duplicate customer accounts will cause authentication issues and double-sending of promotional emails. Lifetime value calculations will be split across duplicates.",
            "recommended_actions": [
                "Run: SELECT email, COUNT(*) FROM customers GROUP BY email HAVING COUNT(*) > 1 ORDER BY 2 DESC LIMIT 50",
                "Review recent CRM sync logs and import jobs",
                "Merge duplicate accounts and re-add UNIQUE constraint",
            ],
            "confidence": "high",
        },
        offset_hours=5,
    )

    print(f"  ✓ retail-demo: 3 tables, 3 incidents (1×P1, 2×P2 active)")


def seed_staff(conn):
    """Seed staff user directly into DB."""
    from app.auth import hash_password
    sid = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM staff_users WHERE email=%s", (STAFF_EMAIL,))
        if cur.fetchone():
            print(f"  ℹ Staff user already exists: {STAFF_EMAIL}")
            return
        hashed = hash_password(STAFF_PASSWORD)
        cur.execute("""
            INSERT INTO staff_users (id, email, password_hash, full_name, is_active, created_at)
            VALUES (%s, %s, %s, 'DataWatch Admin', true, NOW())
        """, (sid, STAFF_EMAIL, hashed))
    conn.commit()
    print(f"  ✓ Staff user: {STAFF_EMAIL} / {STAFF_PASSWORD}")


def update_plan(conn, slug, plan):
    with conn.cursor() as cur:
        cur.execute("UPDATE organizations SET plan=%s, subscription_status='active' WHERE slug=%s", (plan, slug))
    conn.commit()


# ── Entrypoints ────────────────────────────────────────────────────────────────

def run_full():
    print("\n🌱 DataWatch multi-workspace seed starting...")

    # Start API to handle registration
    print("\n1. Registering workspaces via API...")
    for ws in WORKSPACES:
        register(ws)

    print("\n2. Seeding staff user...")
    import sys
    sys.path.insert(0, "/Users/mounir/Documents/Claude/Projects/DataWatch/backend")
    os.environ.setdefault("SECRET_KEY", "4c7e10d117a0c4418b579b896562e0ef9bd9f5a50943775a3f82b0c8db30e1c3")
    os.environ.setdefault("FERNET_MASTER_KEY", "1jRowibOMgPgktVFz0jgwy6taCRXm7MEthu3ETc5_80=")
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://datawatch:datawatch@localhost:5433/datawatch")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

    conn = db_conn()
    seed_staff(conn)

    print("\n3. Seeding table profiles, incidents, check results...")
    for ws in WORKSPACES:
        org_id = get_org_id(conn, ws["slug"])
        if not org_id:
            print(f"  ✗ Org not found: {ws['slug']}")
            continue
        update_plan(conn, ws["slug"], ws["plan"])
        if ws["slug"] == "acme-corp":
            seed_acme(conn, org_id)
        elif ws["slug"] == "startup-io":
            seed_startup(conn, org_id)
        elif ws["slug"] == "retail-demo":
            seed_retail(conn, org_id)

    conn.close()

    print("\n✅ Seed complete!\n")
    print("─" * 60)
    print("WORKSPACE LOGINS (password: demo1234 for all)")
    print("─" * 60)
    for ws in WORKSPACES:
        print(f"  {ws['slug']:15}  {ws['email']:28}  demo1234")
        print(f"    → {ws['description']}")
        print()
    print(f"  STAFF ADMIN:     {STAFF_EMAIL:28}  admin1234")
    print()
    print("URLs (local dev):")
    print("  Workspace acme-corp:  http://acme-corp.localhost:5173")
    print("  Workspace startup-io: http://startup-io.localhost:5173")
    print("  Workspace retail:     http://retail-demo.localhost:5173")
    print("  Admin portal:         http://admin.localhost:5173")
    print("  MailHog UI:           http://localhost:8025")
    print("  Demo DB (acme):       host=localhost port=5434 db=shopDemo user=readonly_user pass=readonly_pass")
    print("  Analytics DB (startup): host=localhost port=5435 db=analyticsdb user=analytics_ro pass=readonly_pass")
    print("─" * 60)


def run_reset():
    print("🗑  Resetting demo data...")
    conn = db_conn()
    slugs = [ws["slug"] for ws in WORKSPACES]
    with conn.cursor() as cur:
        cur.execute("DELETE FROM organizations WHERE slug = ANY(%s)", (slugs,))
        cur.execute("DELETE FROM staff_users WHERE email=%s", (STAFF_EMAIL,))
    conn.commit()
    conn.close()
    print("  ✓ Cleared. Running --full...")
    run_full()


def run_status():
    conn = db_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT slug, plan, subscription_status FROM organizations ORDER BY created_at")
        orgs = cur.fetchall()
        cur.execute("SELECT email, is_active FROM staff_users")
        staff = cur.fetchall()
        cur.execute("SELECT COUNT(*) FROM table_profiles")
        profiles = cur.fetchone()[0]
        cur.execute("SELECT severity, status, COUNT(*) FROM incidents GROUP BY severity, status")
        incidents = cur.fetchall()
    conn.close()
    print(f"\n📊 DB Status:")
    print(f"  Organizations: {len(orgs)}")
    for slug, plan, status in orgs:
        print(f"    {slug:20} plan={plan:12} status={status}")
    print(f"  Staff users: {len(staff)}")
    for email, active in staff:
        print(f"    {email:30} active={active}")
    print(f"  Table profiles: {profiles:,}")
    print(f"  Incidents:")
    for sev, status, count in incidents:
        print(f"    {sev} {status}: {count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DataWatch demo seed")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.reset:
        run_reset()
    elif args.status:
        run_status()
    else:
        run_full()
