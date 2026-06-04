#!/usr/bin/env python3
"""
DataWatch demo seed script.

Usage:
  python scripts/seed_demo.py --clean        # Drop & recreate demo tables with 90d of data
  python scripts/seed_demo.py --history      # Insert 90 synthetic TableProfile records
  python scripts/seed_demo.py --scenario pipeline_failure
  python scripts/seed_demo.py --scenario null_spike
  python scripts/seed_demo.py --scenario schema_drift
  python scripts/seed_demo.py --scenario row_explosion

The script connects to the DataWatch Postgres instance (DATABASE_URL env var)
and also registers the demo org/source/tables via the DataWatch API.

Requires: DATABASE_URL, DATAWATCH_API_URL, DATAWATCH_API_KEY env vars.
"""

import argparse
import json
import os
import random
import sys
import uuid
from datetime import UTC, date, datetime, timedelta

import psycopg2
import requests

# ── Config ─────────────────────────────────────────────────────────────────────
DB_URL = os.environ.get("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
API_URL = os.environ.get("DATAWATCH_API_URL", "http://localhost:8000")
API_KEY = os.environ.get("DATAWATCH_API_KEY", "")

HEADERS = {"x-api-key": API_KEY}

random.seed(42)

COUNTRIES = ["US", "FR", "DE", "MA", "GB", "CA", "AU", "JP"]
CATEGORIES = ["Electronics", "Clothing", "Food", "Books", "Sports"]
STATUSES = ["completed", "pending", "cancelled", "refunded"]


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(DB_URL)


def api(method, path, **kwargs):
    resp = requests.request(method, f"{API_URL}{path}", headers=HEADERS, **kwargs)
    if resp.status_code >= 400:
        print(f"  API {method} {path} → {resp.status_code}: {resp.text[:200]}")
    return resp


# ── Clean + create demo tables ────────────────────────────────────────────────

def create_demo_tables(conn):
    with conn.cursor() as cur:
        print("Creating demo schema…")
        cur.execute("CREATE SCHEMA IF NOT EXISTS demo")

        cur.execute("DROP TABLE IF EXISTS demo.orders CASCADE")
        cur.execute("DROP TABLE IF EXISTS demo.users CASCADE")
        cur.execute("DROP TABLE IF EXISTS demo.products CASCADE")

        cur.execute("""
            CREATE TABLE demo.users (
                id          SERIAL PRIMARY KEY,
                email       TEXT NOT NULL UNIQUE,
                signup_date DATE NOT NULL,
                country     TEXT,
                is_active   BOOLEAN DEFAULT TRUE
            )
        """)

        cur.execute("""
            CREATE TABLE demo.products (
                id          SERIAL PRIMARY KEY,
                name        TEXT NOT NULL,
                category    TEXT,
                price       NUMERIC(10,2),
                stock_count INTEGER DEFAULT 0
            )
        """)

        cur.execute("""
            CREATE TABLE demo.orders (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER REFERENCES demo.users(id),
                product_id INTEGER REFERENCES demo.products(id),
                amount     NUMERIC(10,2),
                status     TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
    conn.commit()
    print("  ✓ Tables created: demo.users, demo.products, demo.orders")


def seed_users(conn):
    print("Seeding 5000 users…")
    with conn.cursor() as cur:
        rows = []
        for i in range(5000):
            signup = date(2022, 1, 1) + timedelta(days=random.randint(0, 800))
            rows.append((
                f"user{i}@example.com",
                signup,
                random.choice(COUNTRIES),
                random.random() > 0.05,
            ))
        cur.executemany(
            "INSERT INTO demo.users (email, signup_date, country, is_active) VALUES (%s,%s,%s,%s)",
            rows,
        )
    conn.commit()
    print("  ✓ 5000 users inserted")


def seed_products(conn):
    print("Seeding 200 products…")
    with conn.cursor() as cur:
        rows = [
            (f"Product {i}", random.choice(CATEGORIES),
             round(random.uniform(5, 500), 2), random.randint(0, 500))
            for i in range(200)
        ]
        cur.executemany(
            "INSERT INTO demo.products (name, category, price, stock_count) VALUES (%s,%s,%s,%s)",
            rows,
        )
    conn.commit()
    print("  ✓ 200 products inserted")


def seed_orders(conn, days=90, rows_per_day=500):
    print(f"Seeding {days} days of orders (~{rows_per_day}/day)…")
    with conn.cursor() as cur:
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        batch = []
        for d in range(days):
            day = today - timedelta(days=days - d)
            count = int(random.gauss(rows_per_day, rows_per_day * 0.15))
            count = max(1, count)
            for _ in range(count):
                ts = day + timedelta(
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59),
                )
                batch.append((
                    random.randint(1, 5000),   # user_id
                    random.randint(1, 200),    # product_id
                    round(random.uniform(5, 500), 2),
                    random.choice(STATUSES),
                    ts,
                ))
        cur.executemany(
            "INSERT INTO demo.orders (user_id, product_id, amount, status, created_at) "
            "VALUES (%s,%s,%s,%s,%s)",
            batch,
        )
    conn.commit()
    total = sum(1 for _ in batch) if 'batch' in dir() else 0
    print(f"  ✓ ~{days * rows_per_day} orders inserted across {days} days")


# ── Profile history ────────────────────────────────────────────────────────────

def seed_profile_history():
    """
    Insert 90 synthetic TableProfile records per monitored table
    so anomaly detectors have a proper baseline on day 1 of the demo.
    """
    print("Seeding profile history via API…")

    resp = api("GET", "/api/v1/tables")
    if resp.status_code != 200:
        print("  ✗ Could not fetch tables. Is the API running with --api-key set?")
        return

    tables = resp.json()
    if not tables:
        print("  ✗ No monitored tables found. Run --clean first and add tables via UI.")
        return

    conn = get_conn()
    with conn.cursor() as cur:
        for table in tables:
            tid = table["id"]
            print(f"  Inserting 90 profiles for {table['schema_name']}.{table['table_name']}…")
            today = datetime.now(UTC)
            for d in range(90, 0, -1):
                collected_at = today - timedelta(days=d)
                row_count = int(random.gauss(500, 40))
                freshness = random.uniform(30, 3600)
                column_metrics = {
                    "amount": {
                        "null_rate": round(random.uniform(0.01, 0.03), 4),
                        "distinct_count": random.randint(450, 520),
                        "mean": round(random.gauss(150, 20), 2),
                        "stddev": round(random.uniform(80, 120), 2),
                        "min": round(random.uniform(5, 20), 2),
                        "max": round(random.uniform(480, 500), 2),
                    }
                }
                cur.execute(
                    """
                    INSERT INTO table_profiles
                      (id, table_id, collected_at, row_count, freshness_seconds,
                       schema_fingerprint, column_metrics, profiling_duration_ms)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()), tid, collected_at,
                        row_count, freshness,
                        "baseline_fingerprint_abc123",
                        json.dumps(column_metrics),
                        random.randint(120, 800),
                    ),
                )
    conn.commit()
    conn.close()
    print(f"  ✓ Profile history seeded for {len(tables)} tables")


# ── Anomaly scenarios ──────────────────────────────────────────────────────────

def scenario_pipeline_failure(conn):
    """Delete all orders from the last 3 days — simulates pipeline outage."""
    print("Injecting scenario: pipeline_failure (zero rows for last 3 days)…")
    with conn.cursor() as cur:
        cutoff = datetime.now(UTC) - timedelta(days=3)
        cur.execute("DELETE FROM demo.orders WHERE created_at >= %s", (cutoff,))
        deleted = cur.rowcount
    conn.commit()
    print(f"  ✓ Deleted {deleted} rows — orders table will show 0 recent rows")


def scenario_null_spike(conn):
    """Nullify 45% of amount values — simulates ETL bug dropping a field."""
    print("Injecting scenario: null_spike (45% of order amounts → NULL)…")
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
    print(f"  ✓ Nullified ~{target} amount values")


def scenario_schema_drift(conn):
    """Drop the status column — simulates schema migration breaking downstream."""
    print("Injecting scenario: schema_drift (DROP COLUMN status)…")
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE demo.orders DROP COLUMN IF EXISTS status")
    conn.commit()
    print("  ✓ Column 'status' dropped from demo.orders")


def scenario_row_explosion(conn):
    """Insert 15x the normal daily volume — simulates duplicated ingestion."""
    print("Injecting scenario: row_explosion (15x today's row count)…")
    with conn.cursor() as cur:
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        rows = []
        for _ in range(500 * 15):
            ts = today + timedelta(
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )
            rows.append((
                random.randint(1, 5000),
                random.randint(1, 200),
                round(random.uniform(5, 500), 2),
                random.choice(STATUSES),
                ts,
            ))
        cur.executemany(
            "INSERT INTO demo.orders (user_id, product_id, amount, status, created_at) "
            "VALUES (%s,%s,%s,%s,%s)",
            rows,
        )
    conn.commit()
    print(f"  ✓ Inserted {len(rows)} extra rows (15x spike)")


SCENARIOS = {
    "pipeline_failure": scenario_pipeline_failure,
    "null_spike": scenario_null_spike,
    "schema_drift": scenario_schema_drift,
    "row_explosion": scenario_row_explosion,
}


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="DataWatch demo seed script")
    parser.add_argument("--clean", action="store_true", help="Drop and recreate demo tables with seed data")
    parser.add_argument("--history", action="store_true", help="Insert synthetic profile history for all monitored tables")
    parser.add_argument("--scenario", choices=list(SCENARIOS.keys()), help="Inject a specific anomaly scenario")
    args = parser.parse_args()

    if not any([args.clean, args.history, args.scenario]):
        parser.print_help()
        sys.exit(1)

    if not DB_URL:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    if args.clean:
        conn = get_conn()
        create_demo_tables(conn)
        seed_users(conn)
        seed_products(conn)
        seed_orders(conn)
        conn.close()
        print("\n✅ Clean demo data ready.")
        print("   Next: connect this Postgres as a data source in the DataWatch UI,")
        print("   add demo.orders, demo.users, demo.products to monitoring,")
        print("   then run: python scripts/seed_demo.py --history")

    if args.history:
        if not API_KEY:
            print("ERROR: DATAWATCH_API_KEY not set")
            sys.exit(1)
        seed_profile_history()
        print("\n✅ Profile history seeded. Anomaly detectors now have 90-day baseline.")

    if args.scenario:
        conn = get_conn()
        SCENARIOS[args.scenario](conn)
        conn.close()
        print(f"\n✅ Scenario '{args.scenario}' injected.")
        print("   Now trigger a profile run:")
        print("   curl -X POST http://localhost:8000/api/v1/tables/{ORDERS_TABLE_ID}/run \\")
        print("        -H 'x-api-key: YOUR_KEY'")


if __name__ == "__main__":
    main()
