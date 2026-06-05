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
        "description": "E-commerce platform — orders, users, products",
    },
    {
        "slug": "startup-io",
        "name": "Startup.io",
        "plan": "growth",
        "email": "dev@startup.io",
        "password": "demo1234",
        "description": "SaaS analytics — events, sessions, users",
    },
    {
        "slug": "retail-demo",
        "name": "Retail Demo",
        "plan": "starter",
        "email": "admin@retail.demo",
        "password": "demo1234",
        "description": "Retail inventory — inventory, orders, customers",
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
    fired = [{
        "check_name": check_name,
        "check_type": check_type,
        "status": "failed",
        "observed_value": obs,
        "deviation_score": round((obs - expected) / max(expected * 0.1, 1), 2),
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
    # Also add a second fake source for UI variety
    sid2 = seed_source(conn, org_id, "Analytics Warehouse", "postgres", {
        "host": "analytics.acme.io", "port": 5432, "database": "analytics",
        "username": "readonly", "password": "readonly",
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

    print(f"  ✓ acme-corp: 3 tables, 3 incidents (1×P1, 1×P2, 1×P3 freshness)")


def seed_startup(conn, org_id):
    """Growth workspace: resolved P2 incident, currently healthy."""
    print("  → Seeding startup-io data...")
    sid = seed_source(conn, org_id, "Startup Production", "postgres", {
        "host": "db.startup.io", "port": 5432, "database": "startup_prod",
        "username": "analytics_ro", "password": "readonly",
    })

    events_tid = seed_table(conn, sid, "public", "events", "created_at", 15)
    sessions_tid = seed_table(conn, sid, "public", "sessions", "started_at", 30)
    users_tid = seed_table(conn, sid, "public", "users", "created_at", 60)

    # Events — 45 days, P2 schema drift happened 7 days ago (resolved)
    base = 500000
    for h in range(45 * 24, 7 * 24, -6):
        seed_profile(conn, events_tid, base + random.randint(-1000, 2000), random.randint(5, 20) * 60, EVENTS_COLS, offset_hours=h)

    # Schema drift: event_type column added 7 days ago
    extended_cols = EVENTS_COLS + [{"name": "event_type", "category": "text", "distinct_count": 12}]
    for h in range(7 * 24, 0, -6):
        seed_profile(conn, events_tid, base + random.randint(-500, 1500), random.randint(5, 15) * 60, extended_cols, offset_hours=h)
    current_pid = seed_profile(conn, events_tid, base + 3000, 8 * 60, extended_cols)

    # Resolved P2 incident
    iid = str(uuid.uuid4())
    ts = ago(days=7)
    fired = [{"check_name": "schema_drift", "check_type": "rule", "status": "failed"}]
    narration = {
        "summary": "A new column event_type was added to the events table. The schema fingerprint changed from fp_12345 to fp_67890.",
        "likely_causes": [{"hypothesis": "Planned schema migration for event categorization feature", "probability": "high"}],
        "impact_assessment": "Low impact — column addition. Downstream queries using SELECT * may receive unexpected data.",
        "recommended_actions": ["Review schema change with engineering team", "Update downstream consumers if needed"],
        "data_pattern_notes": "Clean schema addition, no data loss detected.",
        "confidence": "medium",
    }
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO incidents (id, org_id, table_id, severity, status, title, fired_checks, llm_narration, created_at, resolved_at)
            VALUES (%s, %s, %s, 'P2', 'resolved', 'events — schema drift (column event_type added)', %s::jsonb, %s::jsonb, %s, NOW())
        """, (iid, org_id, events_tid, json.dumps(fired), json.dumps(narration), ts))
    conn.commit()

    # Sessions and users — healthy
    for h in range(30 * 24, 0, -12):
        seed_profile(conn, sessions_tid, 180000 + h * 5, random.randint(3, 10) * 60, SESSIONS_COLS, offset_hours=h)
    seed_profile(conn, sessions_tid, 182500, 3 * 60, SESSIONS_COLS)
    seed_profile(conn, users_tid, 8400, 1 * 60, USERS_COLS)

    print(f"  ✓ startup-io: 3 tables, 1 resolved P2 incident")


def seed_retail(conn, org_id):
    """Starter workspace: healthy, no active incidents."""
    print("  → Seeding retail-demo data...")
    sid = seed_source(conn, org_id, "Retail Database", "mysql", {
        "host": "db.retail.io", "port": 3306, "database": "retail_prod",
        "username": "monitor_user", "password": "readonly",
    })

    inventory_tid = seed_table(conn, sid, "public", "inventory", "updated_at", 60)
    orders_tid = seed_table(conn, sid, "public", "orders", "created_at", 30)

    for h in range(14 * 24, 0, -12):
        seed_profile(conn, inventory_tid, 8000 + random.randint(-50, 50), 0, INVENTORY_COLS, offset_hours=h)
        seed_profile(conn, orders_tid, 2400 + h * 3 + random.randint(-20, 30), random.randint(10, 30) * 60, ORDERS_COLS, offset_hours=h)

    seed_profile(conn, inventory_tid, 8030, 0, INVENTORY_COLS)
    seed_profile(conn, orders_tid, 2800, 25 * 60, ORDERS_COLS)

    print(f"  ✓ retail-demo: 2 tables, 0 active incidents (healthy)")


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
    print("─" * 50)
    print("🔗 App:   http://localhost:5173")
    print("🔗 Admin: http://localhost:5173/admin")
    print("─" * 50)
    print("Workspace logins:")
    for ws in WORKSPACES:
        print(f"  {ws['slug']:15}  {ws['email']:25}  demo1234  ({ws['plan']})")
    print(f"\n  Admin portal:    {STAFF_EMAIL:25}  admin1234")
    print("─" * 50)


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
