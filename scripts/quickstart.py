#!/usr/bin/env python3
"""
DataWatch Quickstart
====================
Creates two workspaces connected to live databases, seeds 30 days of healthy
profile history (so statistical anomaly detection has baseline data), injects
initial anomalies, then triggers real DataWatch profile runs so the full
pipeline fires: profiler → anomaly detection → LLM narration → incidents.

Workspaces
----------
  acme-corp   (growth)  mounir@acme.io / acme1234   — e-commerce, live acme-db
  startup-io  (growth)  dev@startup.io / acme1234   — SaaS analytics, live analytics-db
  Staff admin           admin@datawatch.io / admin1234

Usage
-----
  python scripts/quickstart.py            # full setup (register + seed + inject + profiles)
  python scripts/quickstart.py --reset    # drop all workspaces + re-run full setup
  python scripts/quickstart.py --inject   # inject anomalies + trigger profile runs only
  python scripts/quickstart.py --status   # show what is seeded in the DB
  python scripts/quickstart.py --local    # use localhost:5434/5435 for data-source configs
                                          # (default uses docker service names acme-db/analytics-db)

Environment overrides
---------------------
  DB_URL          DataWatch PostgreSQL connection (default: localhost:5433)
  API_URL         DataWatch API base URL (default: http://localhost:8000)
  ACME_DB_URL     acme-db write connection (for anomaly injection)
  ANALYTICS_DB_URL analytics-db write connection (for anomaly injection)
"""

import argparse
import hashlib
import json
import os
import random
import sys
import time
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
        "password": "acme1234",
        "db_host_docker": "acme-db",
        "db_host_local": "localhost",
        "db_port_docker": 5432,
        "db_port_local": 5434,
        "db_name": "acmedb",
        "db_user": "readonly_user",
        "db_pass": "readonly_pass",
    },
    {
        "slug": "startup-io",
        "name": "Startup.io",
        "plan": "growth",
        "email": "dev@startup.io",
        "password": "acme1234",
        "db_host_docker": "analytics-db",
        "db_host_local": "localhost",
        "db_port_docker": 5432,
        "db_port_local": 5435,
        "db_name": "analyticsdb",
        "db_user": "analytics_ro",
        "db_pass": "readonly_pass",
    },
]

EXTRA_USERS = {
    "acme-corp": [
        {"email": "alice@acme.io",   "password": "acme1234", "role": "admin",  "full_name": "Alice Chen"},
        {"email": "bob@acme.io",     "password": "acme1234", "role": "member", "full_name": "Bob Martin"},
    ],
    "startup-io": [
        {"email": "carol@startup.io", "password": "acme1234", "role": "member", "full_name": "Carol Kim"},
    ],
}

TEAMS_CONFIG = {
    "acme-corp": [
        {"name": "Data Engineering", "color": "#3b82f6",
         "description": "Owns all data pipelines and warehouse integrity",
         "members": ["mounir@acme.io", "alice@acme.io"], "oncall": True},
        {"name": "Analytics",        "color": "#10b981",
         "description": "Business intelligence and reporting",
         "members": ["alice@acme.io"], "oncall": False},
        {"name": "Platform",         "color": "#8b5cf6",
         "description": "Infrastructure and developer tooling",
         "members": ["bob@acme.io"], "oncall": False},
    ],
    "startup-io": [
        {"name": "Backend", "color": "#ef4444",
         "description": "API services and data infrastructure",
         "members": ["dev@startup.io", "carol@startup.io"], "oncall": True},
        {"name": "Data",    "color": "#f59e0b",
         "description": "Analytics engineering and data quality",
         "members": ["carol@startup.io"], "oncall": False},
    ],
}

random.seed(42)

# ── Connection helpers ──────────────────────────────────────────────────────────

def db_conn():
    return psycopg2.connect(DB_URL)


def now():
    return datetime.now(UTC)


def ago(days=0, hours=0, minutes=0):
    return now() - timedelta(days=days, hours=hours, minutes=minutes)


def future(days=0, hours=0):
    return now() + timedelta(days=days, hours=hours)


# ── API helpers ─────────────────────────────────────────────────────────────────

_tokens: dict[str, str] = {}


def _headers(slug: str | None = None) -> dict:
    token = _tokens.get(slug or "")
    if token:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    return {"Content-Type": "application/json"}


def api(method, path, slug=None, silent=False, **kwargs):
    """Call the DataWatch API. path should include the full path e.g. /api/v1/tables."""
    resp = requests.request(method, f"{API_URL}{path}", headers=_headers(slug), timeout=30, **kwargs)
    if not silent and resp.status_code >= 400:
        print(f"  WARNING {method} {path} -> {resp.status_code}: {resp.text[:200]}")
    return resp


def login(slug: str) -> bool:
    ws = next((w for w in WORKSPACES if w["slug"] == slug), None)
    if not ws:
        return False
    r = requests.post(f"{API_URL}/auth/login", json={
        "email": ws["email"], "password": ws["password"], "org_slug": slug,
    }, timeout=15)
    if r.status_code == 200:
        _tokens[slug] = r.json()["access_token"]
        return True
    print(f"  WARNING login failed for {slug}: {r.status_code} {r.text[:100]}")
    return False


def register(ws: dict) -> bool:
    r = requests.post(f"{API_URL}/auth/register", json={
        "org_name": ws["name"], "org_slug": ws["slug"],
        "email": ws["email"], "password": ws["password"],
    }, timeout=15)
    if r.status_code == 201:
        print(f"  + Registered: {ws['slug']}")
        return True
    if r.status_code == 409:
        print(f"  i Already exists: {ws['slug']}")
        return False
    print(f"  x Register failed ({ws['slug']}): {r.text[:100]}")
    return False


# ── Direct DB seeding ───────────────────────────────────────────────────────────

def seed_source(conn, org_id, name, source_type, config) -> str:
    from app.services.crypto import encrypt_config
    encrypted = encrypt_config(config, str(org_id))
    sid = str(uuid.uuid4())
    # Source was connected ~35 days ago
    created = ago(days=35)
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO data_sources
              (id, org_id, name, type, connection_config, status, last_connected_at, created_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, 'connected', NOW(), %s)
            ON CONFLICT DO NOTHING
        """, (sid, org_id, name, source_type, json.dumps({"encrypted": encrypted}), created))
        cur.execute("SELECT id FROM data_sources WHERE org_id=%s AND name=%s", (org_id, name))
        row = cur.fetchone()
    conn.commit()
    return str(row[0]) if row else sid


def seed_table(conn, source_id, schema, table, freshness_col="created_at", interval=5,
               owner_team_id=None, owner_user_id=None) -> str:
    # Tables were added ~31 days ago (matching start of profile history)
    created = ago(days=31)
    with conn.cursor() as cur:
        # Check if already exists (handles both PK and unique-constraint conflicts)
        cur.execute(
            "SELECT id FROM monitored_tables WHERE source_id=%s AND schema_name=%s AND table_name=%s",
            (source_id, schema, table))
        row = cur.fetchone()
        if row:
            return str(row[0])
        tid = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO monitored_tables
              (id, source_id, schema_name, table_name, freshness_column,
               check_interval_minutes, sensitivity, is_active,
               owner_team_id, owner_user_id, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, 3.0, true, %s, %s, %s)
        """, (tid, source_id, schema, table, freshness_col, interval,
              owner_team_id, owner_user_id, created))
    conn.commit()
    return tid


def compute_real_fingerprint(db_url: str, schema: str, table: str) -> str | None:
    """
    Compute the schema fingerprint the DataWatch profiler will generate,
    by querying information_schema.columns from the actual database.
    Returns None if the DB is unreachable.
    """
    try:
        conn = psycopg2.connect(db_url, connect_timeout=5)
        with conn.cursor() as cur:
            # Must use data_type (not udt_name) — matches profiler's compute_schema_fingerprint
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
            """, (schema, table))
            cols = cur.fetchall()
        conn.close()
        if not cols:
            return None
        pairs = sorted(f"{name}:{dtype}" for name, dtype in cols)
        return hashlib.md5("|".join(pairs).encode()).hexdigest()
    except Exception:
        return None


def seed_profile(conn, table_id: str, row_count: int, freshness_seconds: int,
                 columns: list, offset_hours: int = 0,
                 schema_fingerprint: str | None = None) -> str:
    pid = str(uuid.uuid4())
    col_metrics: dict = {}
    for col in columns:
        col_metrics[col["name"]] = {
            "null_rate": col.get("null_rate", random.uniform(0, 0.03)),
            "distinct_count": col.get("distinct_count",
                                      int(row_count * random.uniform(0.1, 0.9))),
            "cardinality_ratio": col.get("cardinality_ratio", random.uniform(0.1, 0.95)),
        }
        if col.get("category") == "numeric":
            base = col.get("base_value", 100)
            noise = random.uniform(0.9, 1.1)
            col_metrics[col["name"]].update({
                "min":    round(base * 0.1 * noise, 2),
                "max":    round(base * 10 * noise, 2),
                "mean":   round(base * noise, 2),
                "stddev": round(base * 0.12 * noise, 2),
            })
    # Use the provided fingerprint (real MD5 from live DB) or fall back to a stable fake
    schema_fp = schema_fingerprint or f"fp_{hash(str([c['name'] for c in columns])) % 100000:05d}"
    ts = ago(hours=offset_hours)
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO table_profiles
              (id, table_id, row_count, freshness_seconds, schema_fingerprint,
               column_metrics, profiling_duration_ms, collected_at)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
        """, (pid, table_id, row_count, freshness_seconds, schema_fp,
              json.dumps(col_metrics), random.randint(80, 450), ts))
        if offset_hours == 0:
            cur.execute("UPDATE monitored_tables SET last_profiled_at=%s WHERE id=%s",
                        (ts, table_id))
    conn.commit()
    return pid


# ── Org/user lookups ────────────────────────────────────────────────────────────

def get_org_id(conn, slug: str):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM organizations WHERE slug=%s", (slug,))
        row = cur.fetchone()
        return row[0] if row else None


def get_user_id(conn, email: str):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE email=%s", (email,))
        row = cur.fetchone()
        return row[0] if row else None


# ── Column schemas ──────────────────────────────────────────────────────────────

ORDERS_COLS = [
    {"name": "id",             "category": "numeric", "base_value": 1,   "distinct_count": 50000},
    {"name": "user_id",        "category": "numeric", "base_value": 1,   "null_rate": 0.001},
    {"name": "total_amount",   "category": "numeric", "base_value": 125},
    {"name": "status",         "category": "text",    "distinct_count": 4},
    {"name": "payment_status", "category": "text",    "distinct_count": 3, "null_rate": 0.01},
    {"name": "currency",       "category": "text",    "distinct_count": 3},
    {"name": "country",        "category": "text",    "distinct_count": 5},
    {"name": "created_at",     "category": "timestamp"},
]

USERS_COLS = [
    {"name": "id",         "category": "numeric", "base_value": 1, "distinct_count": 12000},
    {"name": "email",      "category": "text",    "distinct_count": 11950, "null_rate": 0.001},
    {"name": "full_name",  "category": "text",    "distinct_count": 11800, "null_rate": 0.02},
    {"name": "plan",       "category": "text",    "distinct_count": 4},
    {"name": "is_active",  "category": "text",    "distinct_count": 2},
    {"name": "created_at", "category": "timestamp"},
]

PRODUCTS_COLS = [
    {"name": "id",             "category": "numeric", "base_value": 1, "distinct_count": 3500},
    {"name": "name",           "category": "text",    "distinct_count": 3498},
    {"name": "price",          "category": "numeric", "base_value": 200},
    {"name": "stock_quantity", "category": "numeric", "base_value": 5000},
    {"name": "category",       "category": "text",    "distinct_count": 3},
    {"name": "created_at",     "category": "timestamp"},
]

EVENTS_ACME_COLS = [
    {"name": "id",         "category": "text",    "distinct_count": 200000},
    {"name": "user_id",    "category": "numeric", "null_rate": 0.02},
    {"name": "event_name", "category": "text",    "distinct_count": 7},
    {"name": "session_id", "category": "text",    "distinct_count": 80000},
    {"name": "created_at", "category": "timestamp"},
]

EVENTS_STARTUP_COLS = [
    {"name": "id",         "category": "text",    "distinct_count": 500000},
    {"name": "user_id",    "category": "text",    "distinct_count": 8200, "null_rate": 0.02},
    {"name": "event_name", "category": "text",    "distinct_count": 8},
    {"name": "event_type", "category": "text",    "distinct_count": 3},
    {"name": "session_id", "category": "text",    "distinct_count": 180000},
    {"name": "created_at", "category": "timestamp"},
]

SESSIONS_COLS = [
    {"name": "id",               "category": "text",    "distinct_count": 180000},
    {"name": "user_id",          "category": "text",    "distinct_count": 7500, "null_rate": 0.03},
    {"name": "duration_seconds", "category": "numeric", "base_value": 280},
    {"name": "pages_visited",    "category": "numeric", "base_value": 6},
    {"name": "country",          "category": "text",    "distinct_count": 5},
    {"name": "started_at",       "category": "timestamp"},
]

USERS_STARTUP_COLS = [
    {"name": "id",         "category": "text", "distinct_count": 8400},
    {"name": "email",      "category": "text", "distinct_count": 8380, "null_rate": 0.002},
    {"name": "plan",       "category": "text", "distinct_count": 4},
    {"name": "mrr",        "category": "numeric", "base_value": 95},
    {"name": "created_at", "category": "timestamp"},
]


# ── Workspace seeders ───────────────────────────────────────────────────────────

def seed_acme(conn, org_id, team_ids: dict, use_local: bool = False):
    print("  → Seeding acme-corp tables + 30-day profile history...")
    ws = next(w for w in WORKSPACES if w["slug"] == "acme-corp")

    # Data source config uses Docker service names — the profiler runs inside Docker.
    # use_local only affects injection (connect via mapped ports), not the stored config.
    db_host = ws["db_host_docker"]
    db_port = ws["db_port_docker"]

    de_team_id        = team_ids.get("Data Engineering")
    analytics_team_id = team_ids.get("Analytics")
    platform_team_id  = team_ids.get("Platform")
    owner_id = get_user_id(conn, "mounir@acme.io")
    alice_id = get_user_id(conn, "alice@acme.io")
    bob_id   = get_user_id(conn, "bob@acme.io")

    # Data sources — always use Docker service names so the profiler can reach them
    main_sid = seed_source(conn, org_id, "Acme Shop DB (live)", "postgres", {
        "host": db_host, "port": db_port,
        "database": ws["db_name"], "username": ws["db_user"], "password": ws["db_pass"],
    })

    # Monitored tables (5 min interval for fast demo feedback)
    orders_tid   = seed_table(conn, main_sid, "public", "orders",   "created_at", 5,
                              owner_team_id=de_team_id,        owner_user_id=owner_id)
    users_tid    = seed_table(conn, main_sid, "public", "users",    "created_at", 10,
                              owner_team_id=analytics_team_id, owner_user_id=alice_id)
    products_tid = seed_table(conn, main_sid, "public", "products", "created_at", 15,
                              owner_team_id=platform_team_id,  owner_user_id=bob_id)
    events_tid   = seed_table(conn, main_sid, "public", "events",   "created_at", 5,
                              owner_team_id=de_team_id,        owner_user_id=owner_id)

    # Compute real schema fingerprints from the live DB (matching what the profiler computes)
    acme_write_url = os.environ.get(
        "ACME_DB_URL",
        "postgresql://write_user:write_pass@localhost:5434/acmedb",
    )
    fp_orders   = compute_real_fingerprint(acme_write_url, "public", "orders")
    fp_users    = compute_real_fingerprint(acme_write_url, "public", "users")
    fp_products = compute_real_fingerprint(acme_write_url, "public", "products")
    fp_events   = compute_real_fingerprint(acme_write_url, "public", "events")

    if fp_orders:
        print(f"    ✓ computed real schema fingerprints from acme-db")
    else:
        print(f"    i could not reach acme-db for fingerprints (schema drift will fire once)")

    # 30 days of healthy profile history (every 6 hours = 120 profiles for orders)
    base_orders = 8500
    for h in range(30 * 24, 0, -6):
        drift = 1 + random.uniform(-0.03, 0.04)
        seed_profile(conn, orders_tid, int(base_orders * drift),
                     random.randint(20, 50) * 60, ORDERS_COLS,
                     offset_hours=h, schema_fingerprint=fp_orders)
        base_orders = int(base_orders * (1 + random.uniform(-0.001, 0.002)))
    seed_profile(conn, orders_tid, base_orders, 25 * 60, ORDERS_COLS,
                 offset_hours=0, schema_fingerprint=fp_orders)

    # Users — 21 days history
    base_users = 12000
    for h in range(21 * 24, 0, -12):
        seed_profile(conn, users_tid, base_users + random.randint(-50, 100),
                     random.randint(5, 20) * 60, USERS_COLS,
                     offset_hours=h, schema_fingerprint=fp_users)
    seed_profile(conn, users_tid, base_users + 50, 10 * 60, USERS_COLS,
                 offset_hours=0, schema_fingerprint=fp_users)

    # Products — 21 days history (mostly static)
    for h in range(21 * 24, 0, -24):
        seed_profile(conn, products_tid, 3500 + random.randint(-10, 20),
                     0, PRODUCTS_COLS,
                     offset_hours=h, schema_fingerprint=fp_products)
    seed_profile(conn, products_tid, 3510, 0, PRODUCTS_COLS,
                 offset_hours=0, schema_fingerprint=fp_products)

    # Events — 14 days history
    base_events = 200000
    for h in range(14 * 24, 0, -6):
        seed_profile(conn, events_tid, base_events + random.randint(-500, 1000),
                     random.randint(5, 15) * 60, EVENTS_ACME_COLS,
                     offset_hours=h, schema_fingerprint=fp_events)
    seed_profile(conn, events_tid, base_events + 500, 8 * 60, EVENTS_ACME_COLS,
                 offset_hours=0, schema_fingerprint=fp_events)

    print(f"  + acme-corp: 4 monitored tables, ~30 days profile history, connected to acme-db:5432/{ws['db_name']}")
    return {"orders": orders_tid, "users": users_tid, "products": products_tid, "events": events_tid}


def seed_startup(conn, org_id, team_ids: dict, use_local: bool = False):
    print("  → Seeding startup-io tables + 30-day profile history...")
    ws = next(w for w in WORKSPACES if w["slug"] == "startup-io")

    # Always use Docker service names for stored config
    db_host = ws["db_host_docker"]
    db_port = ws["db_port_docker"]

    backend_team_id = team_ids.get("Backend")
    data_team_id    = team_ids.get("Data")
    owner_id = get_user_id(conn, "dev@startup.io")
    carol_id = get_user_id(conn, "carol@startup.io")

    sid = seed_source(conn, org_id, "Analytics DB (live)", "postgres", {
        "host": db_host, "port": db_port,
        "database": ws["db_name"], "username": ws["db_user"], "password": ws["db_pass"],
    })

    events_tid   = seed_table(conn, sid, "public", "events",   "created_at", 5,
                              owner_team_id=backend_team_id, owner_user_id=owner_id)
    sessions_tid = seed_table(conn, sid, "public", "sessions", "started_at", 10,
                              owner_team_id=backend_team_id, owner_user_id=owner_id)
    users_tid    = seed_table(conn, sid, "public", "users",    "created_at", 10,
                              owner_team_id=data_team_id,    owner_user_id=carol_id)

    # Compute real fingerprints from live analytics-db
    analytics_write_url = os.environ.get(
        "ANALYTICS_DB_URL",
        "postgresql://write_user:write_pass@localhost:5435/analyticsdb",
    )
    fp_ev = compute_real_fingerprint(analytics_write_url, "public", "events")
    fp_ss = compute_real_fingerprint(analytics_write_url, "public", "sessions")
    fp_us = compute_real_fingerprint(analytics_write_url, "public", "users")
    if fp_ev:
        print(f"    ✓ computed real schema fingerprints from analytics-db")

    # 30 days healthy history
    base_events = 500000
    for h in range(30 * 24, 0, -6):
        seed_profile(conn, events_tid, base_events + random.randint(-1000, 2000),
                     random.randint(5, 20) * 60, EVENTS_STARTUP_COLS,
                     offset_hours=h, schema_fingerprint=fp_ev)
    seed_profile(conn, events_tid, base_events + 500, 10 * 60, EVENTS_STARTUP_COLS,
                 offset_hours=0, schema_fingerprint=fp_ev)

    base_sessions = 180000
    for h in range(30 * 24, 0, -12):
        seed_profile(conn, sessions_tid, base_sessions + random.randint(-200, 400),
                     random.randint(3, 10) * 60, SESSIONS_COLS,
                     offset_hours=h, schema_fingerprint=fp_ss)
    seed_profile(conn, sessions_tid, base_sessions + 100, 5 * 60, SESSIONS_COLS,
                 offset_hours=0, schema_fingerprint=fp_ss)

    base_users = 8400
    for h in range(30 * 24, 0, -24):
        seed_profile(conn, users_tid, base_users + random.randint(-10, 30),
                     random.randint(30, 90) * 60, USERS_STARTUP_COLS,
                     offset_hours=h, schema_fingerprint=fp_us)
    seed_profile(conn, users_tid, base_users + 10, 45 * 60, USERS_STARTUP_COLS,
                 offset_hours=0, schema_fingerprint=fp_us)

    print(f"  + startup-io: 3 monitored tables, ~30 days profile history, connected to analytics-db:5432/{ws['db_name']}")
    return {"events": events_tid, "sessions": sessions_tid, "users": users_tid}


# ── Extra users ─────────────────────────────────────────────────────────────────

def seed_extra_users(conn, slug: str):
    from app.auth import hash_password
    org_id = get_org_id(conn, slug)
    if not org_id:
        return
    created = 0
    for u in EXTRA_USERS.get(slug, []):
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE email=%s", (u["email"],))
            if cur.fetchone():
                continue
            cur.execute("""
                INSERT INTO users (id, org_id, email, password_hash, role, full_name, is_active, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, true, NOW())
                ON CONFLICT DO NOTHING
            """, (str(uuid.uuid4()), org_id, u["email"],
                  hash_password(u["password"]), u["role"], u["full_name"]))
        conn.commit()
        created += 1
    if created:
        print(f"  + {created} extra user(s) for {slug}")


# ── Teams ────────────────────────────────────────────────────────────────────────

def seed_teams(conn, slug: str) -> dict:
    org_id = get_org_id(conn, slug)
    if not org_id:
        return {}
    team_ids: dict = {}
    for t in TEAMS_CONFIG.get(slug, []):
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM teams WHERE org_id=%s AND name=%s", (org_id, t["name"]))
            row = cur.fetchone()
            if row:
                team_id = row[0]
            else:
                team_id = str(uuid.uuid4())
                cur.execute("""
                    INSERT INTO teams (id, org_id, name, description, color, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                """, (team_id, org_id, t["name"], t.get("description"), t.get("color")))
        conn.commit()
        team_ids[t["name"]] = team_id

        for i, email in enumerate(t["members"]):
            user_id = get_user_id(conn, email)
            if not user_id:
                continue
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO team_members (id, team_id, user_id, role, joined_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT DO NOTHING
                """, (str(uuid.uuid4()), team_id, user_id,
                      "lead" if i == 0 else "member"))
            conn.commit()

    print(f"  + {len(team_ids)} team(s) for {slug}: {', '.join(team_ids)}")
    return team_ids


# ── On-call ──────────────────────────────────────────────────────────────────────

def seed_oncall(conn, slug: str, team_ids: dict):
    scheduled = 0
    for t in TEAMS_CONFIG.get(slug, []):
        if not t.get("oncall"):
            continue
        team_id = team_ids.get(t["name"])
        if not team_id:
            continue
        user_ids = [get_user_id(conn, e) for e in t["members"]]
        user_ids = [u for u in user_ids if u]
        if not user_ids:
            continue
        slots = [
            (ago(days=3),   ago(days=1),    user_ids[0]),
            (ago(days=1),   future(days=2), user_ids[1] if len(user_ids) > 1 else user_ids[0]),
            (future(days=2), future(days=5), user_ids[0]),
        ]
        with conn.cursor() as cur:
            for starts_at, ends_at, uid in slots:
                cur.execute("""
                    INSERT INTO oncall_schedules (id, team_id, user_id, starts_at, ends_at, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                """, (str(uuid.uuid4()), team_id, uid, starts_at, ends_at))
        conn.commit()
        scheduled += 3
    print(f"  + {scheduled} on-call slot(s) for {slug}")


# ── Notification prefs ───────────────────────────────────────────────────────────

def seed_notification_prefs(conn, slug: str):
    org_id = get_org_id(conn, slug)
    if not org_id:
        return
    ws = next((w for w in WORKSPACES if w["slug"] == slug), None)
    all_users = [{"email": ws["email"], "role": "owner"}] + [
        {"email": u["email"], "role": u["role"]} for u in EXTRA_USERS.get(slug, [])
    ]
    created = 0
    for u in all_users:
        user_id = get_user_id(conn, u["email"])
        if not user_id:
            continue
        role = u["role"]
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_notification_prefs
                  (id, user_id, org_id, notify_assigned, notify_team,
                   notify_status_change, daily_digest, digest_hour, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                  notify_assigned=EXCLUDED.notify_assigned
            """, (str(uuid.uuid4()), user_id, org_id,
                  True,
                  role in ("owner", "admin"),
                  True,
                  role == "owner",
                  8))
        conn.commit()
        created += 1
    print(f"  + {created} notification pref(s) for {slug}")


# ── Staff ────────────────────────────────────────────────────────────────────────

def seed_staff(conn):
    from app.auth import hash_password
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM staff_users WHERE email=%s", (STAFF_EMAIL,))
        if cur.fetchone():
            print(f"  i Staff already exists: {STAFF_EMAIL}")
            return
        cur.execute("""
            INSERT INTO staff_users (id, email, password_hash, full_name, is_active, created_at)
            VALUES (%s, %s, %s, 'DataWatch Admin', true, NOW())
        """, (str(uuid.uuid4()), STAFF_EMAIL, hash_password(STAFF_PASSWORD)))
    conn.commit()
    print(f"  + Staff: {STAFF_EMAIL} / {STAFF_PASSWORD}")


def update_plan(conn, slug: str, plan: str):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE organizations SET plan=%s, subscription_status='active' WHERE slug=%s",
            (plan, slug))
    conn.commit()


def backdate_workspace(conn, slug: str):
    """Set org and user created_at to realistic past dates matching the profile history."""
    with conn.cursor() as cur:
        # Org was created ~45 days ago (before monitoring started)
        cur.execute(
            "UPDATE organizations SET created_at=%s WHERE slug=%s",
            (ago(days=45), slug))
        # Users joined ~43 days ago
        cur.execute(
            "UPDATE users SET created_at=%s WHERE org_id=(SELECT id FROM organizations WHERE slug=%s)",
            (ago(days=43), slug))
    conn.commit()


def trigger_autopilot():
    """Queue autopilot (AI monitor recommendations) for every seeded table via the API."""
    print("\n  Triggering AI autopilot for all seeded tables...")
    queued = 0
    for ws in WORKSPACES:
        if ws["slug"] not in _tokens and not login(ws["slug"]):
            continue
        r = api("GET", "/api/v1/tables", slug=ws["slug"])
        if r.status_code != 200:
            continue
        for tbl in r.json():
            resp = api("POST", f"/api/v1/tables/{tbl['id']}/retry-autopilot", slug=ws["slug"])
            if resp.status_code in (200, 202):
                queued += 1
                print(f"    ↑ autopilot queued: {ws['slug']}: {tbl['schema_name']}.{tbl['table_name']}")
            else:
                print(f"    x autopilot failed: {ws['slug']}: {tbl['table_name']} → {resp.status_code}")
    print(f"  + Autopilot queued for {queued} table(s)")


# ── Anomaly injection ────────────────────────────────────────────────────────────

def inject_anomalies(use_local: bool = False):
    """Inject initial anomalies into acme-db and analytics-db so the profiler has something to detect."""
    acme_url = os.environ.get(
        "ACME_DB_URL",
        "postgresql://write_user:write_pass@localhost:5434/acmedb"
        if use_local else
        "postgresql://write_user:write_pass@acme-db:5432/acmedb",
    )
    analytics_url = os.environ.get(
        "ANALYTICS_DB_URL",
        "postgresql://write_user:write_pass@localhost:5435/analyticsdb"
        if use_local else
        "postgresql://write_user:write_pass@analytics-db:5432/analyticsdb",
    )

    # ── acme-db: payment_status null spike ──────────────────────────────────
    try:
        conn = psycopg2.connect(acme_url)
        conn.autocommit = False
        with conn.cursor() as cur:
            # Null out ~15% of all orders payment_status — big enough for z-score detection
            # (historical baseline seeded at ~1% null rate, spike to ~15% is clearly anomalous)
            cur.execute("""
                UPDATE orders
                SET payment_status = NULL
                WHERE id IN (
                    SELECT id FROM orders
                    WHERE payment_status IS NOT NULL
                    ORDER BY random()
                    LIMIT (SELECT (COUNT(*) * 0.15)::INTEGER FROM orders)
                )
            """)
            # Also add 50 negative-price products for variety
            cur.execute("""
                UPDATE products
                SET price = -ABS(price)
                WHERE id IN (
                    SELECT id FROM products WHERE price > 0
                    ORDER BY random() LIMIT 50
                )
            """)
        conn.commit()
        conn.close()
        print("  + acme-db: injected payment_status null spike + 50 negative prices")
    except Exception as e:
        print(f"  WARNING: could not inject into acme-db: {e}")

    # ── analytics-db: user_id null spike in events ──────────────────────────
    try:
        conn = psycopg2.connect(analytics_url)
        conn.autocommit = False
        with conn.cursor() as cur:
            # Insert 15,000 events with NULL user_id (broken analytics SDK)
            cur.execute("""
                INSERT INTO events (user_id, event_name, event_type, created_at)
                SELECT
                    NULL,
                    CASE (random() * 3)::INTEGER
                        WHEN 0 THEN 'page_view'
                        WHEN 1 THEN 'feature_used'
                        ELSE 'dashboard_viewed' END,
                    'user_action',
                    NOW() - (random() * 90 || ' minutes')::INTERVAL
                FROM generate_series(1, 15000)
            """)
            # Insert 2,000 zero-duration sessions
            cur.execute("""
                INSERT INTO sessions (id, user_id, started_at, ended_at, duration_seconds, pages_visited)
                SELECT
                    'sess_init_anomaly_' || i,
                    'usr_' || (random() * 8399 + 1)::INTEGER,
                    NOW() - (random() * 90 || ' minutes')::INTERVAL,
                    NOW() - (random() * 30 || ' minutes')::INTERVAL,
                    0,
                    1
                FROM generate_series(1, 2000) i
                ON CONFLICT (id) DO NOTHING
            """)
        conn.commit()
        conn.close()
        print("  + analytics-db: injected 15k null-user_id events + 2k zero-duration sessions")
    except Exception as e:
        print(f"  WARNING: could not inject into analytics-db: {e}")


# ── Profile run triggering ───────────────────────────────────────────────────────

def trigger_profiles():
    """Log into each workspace and trigger profile runs for all monitored tables."""
    print("\n  Triggering profile runs via DataWatch API...")
    triggered = 0
    for ws in WORKSPACES:
        if not login(ws["slug"]):
            print(f"  WARNING: could not log in as {ws['slug']}")
            continue
        r = api("GET", "/api/v1/tables", slug=ws["slug"])
        if r.status_code != 200:
            print(f"  WARNING: could not list tables for {ws['slug']}")
            continue
        tables = r.json()
        for tbl in tables:
            resp = api("POST", f"/api/v1/tables/{tbl['id']}/profile", slug=ws["slug"])
            if resp.status_code in (200, 202):
                triggered += 1
                print(f"    ↑ {ws['slug']}: {tbl['schema_name']}.{tbl['table_name']}")
            else:
                print(f"    x {ws['slug']}: {tbl['schema_name']}.{tbl['table_name']} → {resp.status_code}")
    print(f"  + Triggered {triggered} profile run(s)")
    return triggered


def wait_for_incidents(max_wait: int = 120) -> list:
    """Poll /api/v1/incidents for all workspaces until incidents appear or timeout."""
    print(f"\n  Waiting up to {max_wait}s for incidents to be created...")
    deadline = time.time() + max_wait
    all_found: list = []

    while time.time() < deadline:
        found_now = []
        for ws in WORKSPACES:
            if ws["slug"] not in _tokens:
                login(ws["slug"])
            r = api("GET", "/api/v1/incidents", slug=ws["slug"], silent=True)
            if r.status_code == 200:
                incs = r.json()
                if isinstance(incs, list):
                    found_now.extend([(ws["slug"], i) for i in incs])
        if len(found_now) > len(all_found):
            all_found = found_now
            print(f"\n  ✓ {len(all_found)} incident(s) created!", flush=True)
            for slug, inc in all_found:
                severity = inc.get("severity", "?")
                title    = inc.get("title", "")[:70]
                status   = inc.get("status", "")
                print(f"    [{severity}] {status:12}  {title}")
        if len(all_found) >= 2:
            break
        time.sleep(3)
        print("    ...", end="\r", flush=True)

    return all_found


# ── Bootstrap ─────────────────────────────────────────────────────────────────────

def _bootstrap_env():
    sys.path.insert(0, "/app" if os.path.exists("/app") else
                    os.path.join(os.path.dirname(__file__), "..", "backend"))
    os.environ.setdefault("SECRET_KEY",
                          "4c7e10d117a0c4418b579b896562e0ef9bd9f5a50943775a3f82b0c8db30e1c3")
    os.environ.setdefault("FERNET_MASTER_KEY",
                          "1jRowibOMgPgktVFz0jgwy6taCRXm7MEthu3ETc5_80=")
    os.environ.setdefault("DATABASE_URL",
                          "postgresql+asyncpg://datawatch:datawatch@localhost:5433/datawatch")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


# ── Entrypoints ───────────────────────────────────────────────────────────────────

def run_full(use_local: bool = False):
    print("\nDataWatch Quickstart — full setup")
    print("=" * 60)

    print("\n1. Registering workspaces via API...")
    for ws in WORKSPACES:
        register(ws)

    print("\n2. Bootstrapping backend environment...")
    _bootstrap_env()
    conn = db_conn()

    print("\n3. Staff user...")
    try:
        seed_staff(conn)
    except Exception as e:
        print(f"  WARNING: {e}")

    print("\n4. Setting plans + backdating timestamps...")
    for ws in WORKSPACES:
        try:
            update_plan(conn, ws["slug"], ws["plan"])
            backdate_workspace(conn, ws["slug"])
        except Exception as e:
            print(f"  WARNING plan/backdate for {ws['slug']}: {e}")

    print("\n5. Extra users...")
    for ws in WORKSPACES:
        try:
            seed_extra_users(conn, ws["slug"])
        except Exception as e:
            print(f"  WARNING extra users for {ws['slug']}: {e}")

    print("\n6. Teams...")
    all_team_ids: dict = {}
    for ws in WORKSPACES:
        try:
            all_team_ids[ws["slug"]] = seed_teams(conn, ws["slug"])
        except Exception as e:
            print(f"  WARNING teams for {ws['slug']}: {e}")
            all_team_ids[ws["slug"]] = {}

    print("\n7. On-call schedules...")
    for ws in WORKSPACES:
        try:
            seed_oncall(conn, ws["slug"], all_team_ids.get(ws["slug"], {}))
        except Exception as e:
            print(f"  WARNING on-call for {ws['slug']}: {e}")

    print("\n8. Notification preferences...")
    for ws in WORKSPACES:
        try:
            seed_notification_prefs(conn, ws["slug"])
        except Exception as e:
            print(f"  WARNING prefs for {ws['slug']}: {e}")

    print("\n9. Data sources, monitored tables, profile history...")
    all_table_ids: dict = {}
    for ws in WORKSPACES:
        org_id = get_org_id(conn, ws["slug"])
        if not org_id:
            print(f"  x Org not found: {ws['slug']}")
            continue
        team_ids = all_team_ids.get(ws["slug"], {})
        try:
            if ws["slug"] == "acme-corp":
                all_table_ids["acme-corp"] = seed_acme(conn, org_id, team_ids, use_local)
            elif ws["slug"] == "startup-io":
                all_table_ids["startup-io"] = seed_startup(conn, org_id, team_ids, use_local)
        except Exception as e:
            print(f"  WARNING data seed for {ws['slug']}: {e}")
            import traceback; traceback.print_exc()

    conn.close()

    print("\n10. Injecting initial anomalies into live databases...")
    inject_anomalies(use_local=use_local)

    print("\n11. Triggering DataWatch profile runs...")
    try:
        trigger_profiles()
    except Exception as e:
        print(f"  WARNING: profile trigger failed: {e}")
        print("  (The APScheduler will run profiles automatically on the configured interval)")

    print("\n12. Waiting for incidents from detection pipeline...")
    try:
        wait_for_incidents(max_wait=90)
    except Exception as e:
        print(f"  WARNING: wait failed: {e}")

    print("\n13. Triggering AI autopilot (monitor recommendations for each table)...")
    try:
        trigger_autopilot()
    except Exception as e:
        print(f"  WARNING: autopilot trigger failed: {e}")
        print("  (Use the Retry button in the table detail view, or wait for APScheduler)")

    _print_credentials()


def run_inject(use_local: bool = False):
    """Inject anomalies and trigger profile runs without re-seeding."""
    print("\nDataWatch — injecting anomalies + triggering profiles")
    print("=" * 60)
    _bootstrap_env()
    inject_anomalies(use_local=use_local)
    try:
        trigger_profiles()
        wait_for_incidents(max_wait=90)
    except Exception as e:
        print(f"  WARNING: {e}")
    _print_credentials()


def run_reset(use_local: bool = False):
    print("\nResetting all demo workspaces...")
    _bootstrap_env()
    conn = db_conn()
    slugs = [ws["slug"] for ws in WORKSPACES]
    with conn.cursor() as cur:
        # Delete orgs (cascades to users, sources, tables, profiles, incidents, alerts)
        cur.execute("DELETE FROM organizations WHERE slug = ANY(%s)", (slugs,))
        cur.execute("DELETE FROM staff_users WHERE email=%s", (STAFF_EMAIL,))
    conn.commit()
    conn.close()
    print("  + Cleared. Running full setup...")
    run_full(use_local=use_local)


def run_status():
    _bootstrap_env()
    conn = db_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT o.slug, o.plan, o.subscription_status,
                   COUNT(DISTINCT u.id)  AS users,
                   COUNT(DISTINCT t.id)  AS teams,
                   COUNT(DISTINCT mt.id) AS tables,
                   COUNT(DISTINCT i.id)  AS incidents
            FROM organizations o
            LEFT JOIN users u  ON u.org_id  = o.id
            LEFT JOIN teams t  ON t.org_id  = o.id
            LEFT JOIN data_sources ds ON ds.org_id = o.id
            LEFT JOIN monitored_tables mt ON mt.source_id = ds.id
            LEFT JOIN incidents i ON i.org_id = o.id
            GROUP BY o.id ORDER BY o.created_at
        """)
        orgs = cur.fetchall()

        cur.execute("SELECT email, is_active FROM staff_users")
        staff = cur.fetchall()

        cur.execute("SELECT COUNT(*) FROM table_profiles")
        profiles = cur.fetchone()[0]

        cur.execute("""
            SELECT severity, status, COUNT(*) FROM incidents
            GROUP BY severity, status ORDER BY severity, status
        """)
        incidents = cur.fetchall()

    conn.close()

    print("\nDB Status")
    print("=" * 72)
    print(f"{'Org':20} {'Plan':10} {'Status':12} {'Users':6} {'Teams':5} {'Tables':7} {'Incs':6}")
    print("-" * 72)
    for row in orgs:
        slug, plan, status, users, teams, tables, incs = row
        print(f"{slug:20} {plan:10} {status:12} {users:6} {teams:5} {tables:7} {incs:6}")

    print(f"\nTable profiles: {profiles:,}")
    if incidents:
        print("Incidents:")
        for sev, status, count in incidents:
            print(f"  {sev} {status}: {count}")
    print(f"\nStaff users: {len(staff)}")
    for email, active in staff:
        print(f"  {email} (active={active})")
    _print_credentials()


def _print_credentials():
    print()
    print("=" * 72)
    print("LOGIN CREDENTIALS")
    print("=" * 72)
    for ws in WORKSPACES:
        url = f"http://{ws['slug']}.localhost:5173"
        print(f"\n  {ws['name']} ({ws['slug']})")
        print(f"    URL:      {url}")
        print(f"    Email:    {ws['email']}")
        print(f"    Password: {ws['password']}")
        for u in EXTRA_USERS.get(ws["slug"], []):
            print(f"    + {u['email']} ({u['role']})")
    print(f"\n  Staff Admin Portal")
    print(f"    URL:      http://admin.localhost:5173")
    print(f"    Email:    {STAFF_EMAIL}")
    print(f"    Password: {STAFF_PASSWORD}")
    print()
    print("  Simulator (run in a separate terminal):")
    print("    docker compose --profile simulator up simulator")
    print("    OR: python scripts/simulator.py --api-url http://localhost:8000")
    print("=" * 72)


# ── Entry point ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DataWatch Quickstart")
    parser.add_argument("--reset",   action="store_true",
                        help="Drop all workspaces and re-run full setup")
    parser.add_argument("--inject",  action="store_true",
                        help="Inject anomalies + trigger profiles only (skip seed)")
    parser.add_argument("--status",  action="store_true",
                        help="Show current DB state")
    parser.add_argument("--local",   action="store_true",
                        help="Use localhost:5434/5435 for data-source host configs")
    args = parser.parse_args()

    if args.reset:
        run_reset(use_local=args.local)
    elif args.inject:
        run_inject(use_local=args.local)
    elif args.status:
        run_status()
    else:
        run_full(use_local=args.local)
