#!/usr/bin/env python3
"""
DataWatch Simulator
===================
Continuously mutates the Acme and Startup demo databases to generate realistic
data quality anomalies. After each injection, optionally triggers a DataWatch
profile run so incidents appear immediately without waiting for the scheduler.

Usage
-----
  python scripts/simulator.py                         # loop every 120s
  python scripts/simulator.py --interval 60           # faster loop
  python scripts/simulator.py --scenario null_spike   # one-shot scenario
  python scripts/simulator.py --scenario restore_all  # reset both DBs
  python scripts/simulator.py --list                  # list all scenarios
  python scripts/simulator.py --api-url http://localhost:8000  # with auto profile trigger

Environment
-----------
  ACME_DB_URL        postgresql://write_user:write_pass@localhost:5434/acmedb
  ANALYTICS_DB_URL   postgresql://write_user:write_pass@localhost:5435/analyticsdb
  DATAWATCH_API_URL  http://localhost:8000  (for auto profile trigger)
"""

import argparse
import os
import random
import sys
import time
from datetime import datetime, timezone

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("[ERROR] psycopg2-binary is required: pip install psycopg2-binary")
    sys.exit(1)

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

# ── Connection defaults ────────────────────────────────────────────────────────

DEFAULT_ACME_DB_URL = (
    os.environ.get("ACME_DB_URL")
    or os.environ.get("DEMO_DB_URL")          # backward-compat alias
    or "postgresql://write_user:write_pass@localhost:5434/acmedb"
)

DEFAULT_ANALYTICS_DB_URL = (
    os.environ.get("ANALYTICS_DB_URL")
    or "postgresql://write_user:write_pass@localhost:5435/analyticsdb"
)

DEFAULT_API_URL = os.environ.get("DATAWATCH_API_URL", "")

# ── Logging ────────────────────────────────────────────────────────────────────

def ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")


def log(msg: str) -> None:
    print(f"[{ts()}] {msg}", flush=True)


# ── DB helpers ─────────────────────────────────────────────────────────────────

def connect(url: str, label: str):
    try:
        conn = psycopg2.connect(url)
        conn.autocommit = False
        return conn
    except psycopg2.OperationalError as exc:
        log(f"[WARN] Cannot connect to {label}: {exc}")
        return None


def run(conn, sql: str, params=None, *, fetch: bool = False):
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            result = cur.fetchall() if fetch else None
        conn.commit()
        return result
    except Exception as exc:
        conn.rollback()
        log(f"[ERROR] Query failed: {exc}\n        SQL: {sql[:200]}")
        return None


# ── acmedb scenarios ───────────────────────────────────────────────────────────

def null_spike(conn) -> str:
    """Set payment_status=NULL on ~15% of all orders (large enough for z-score detection)."""
    pct = random.uniform(0.13, 0.18)
    run(conn, """
        UPDATE orders
        SET payment_status = NULL
        WHERE id IN (
            SELECT id FROM orders
            WHERE payment_status IS NOT NULL
            ORDER BY random()
            LIMIT (SELECT (COUNT(*) * %s)::INTEGER FROM orders)
        )
    """, (pct,))
    return f"payment_status=NULL on ~{pct*100:.0f}% of all orders"


def price_corruption(conn) -> str:
    """Flip a random batch of product prices to negative (bad import simulation)."""
    count = random.randint(30, 80)
    run(conn, """
        UPDATE products
        SET price = -ABS(price)
        WHERE id IN (
            SELECT id FROM products WHERE price > 0
            ORDER BY random()
            LIMIT %s
        )
    """, (count,))
    return f"negative price on {count} products"


def row_drop(conn) -> str:
    """Delete a batch of recent orders — triggers row-count anomaly."""
    count = random.randint(300, 700)
    run(conn, """
        DELETE FROM orders
        WHERE id IN (
            SELECT id FROM orders
            WHERE created_at > NOW() - INTERVAL '48 hours'
            ORDER BY random()
            LIMIT %s
        )
    """, (count,))
    return f"deleted {count} recent orders"


def freshness_stall(conn) -> str:
    """Back-date the most-recent events to make the table look stale."""
    hours_back = random.randint(3, 7)
    run(conn, """
        UPDATE events
        SET created_at = created_at - (%s * INTERVAL '1 hour')
        WHERE id IN (
            SELECT id FROM events ORDER BY created_at DESC LIMIT 1000
        )
    """, (hours_back,))
    return f"pushed last 1000 events back {hours_back}h (freshness stall)"


def duplicate_users(conn) -> str:
    """Insert users with duplicate-pattern emails — uniqueness anomaly."""
    count = random.randint(15, 40)
    run(conn, """
        INSERT INTO users (email, full_name, plan, created_at)
        SELECT
            'dup_' || i || '_sim@acme.io',
            'Duplicate Account',
            'free',
            NOW() - (random() * 30 || ' minutes')::INTERVAL
        FROM generate_series(1, %s) i
        ON CONFLICT (email) DO NOTHING
    """, (count,))
    return f"inserted {count} duplicate-pattern users"


def null_recovery(conn) -> str:
    """Restore NULL payment_status back to 'paid' so incidents can auto-resolve."""
    run(conn, """
        UPDATE orders
        SET payment_status = 'paid',
            payment_reference = 'PAY-RECOVERED-' || id::TEXT
        WHERE payment_status IS NULL
          AND status = 'completed'
    """)
    return "restored NULL payment_status → 'paid' on all completed orders"


def high_null_payments(conn) -> str:
    """Nullify the method column on a large share of recent payments."""
    pct = random.uniform(0.25, 0.40)
    run(conn, """
        UPDATE payments
        SET method = NULL
        WHERE id IN (
            SELECT id FROM payments
            WHERE created_at > NOW() - INTERVAL '6 hours'
            ORDER BY random()
            LIMIT GREATEST(100, (
                SELECT (COUNT(*) * %s)::INTEGER FROM payments
                WHERE created_at > NOW() - INTERVAL '6 hours'
            ))
        )
    """, (pct,))
    return f"nullified payment method on ~{pct*100:.0f}% of last-6h payments"


def restore_acme(conn) -> str:
    """Reset acme-db back to a clean, healthy baseline."""
    ops = [
        """UPDATE orders SET payment_status='paid',
               payment_reference=COALESCE(payment_reference,'PAY-RESTORED-'||id::TEXT)
           WHERE payment_status IS NULL AND status='completed'""",
        "UPDATE products SET price = ABS(price) WHERE price < 0",
        "UPDATE payments SET method='card' WHERE method IS NULL",
        "DELETE FROM users WHERE email LIKE 'dup\\_%\\_sim@acme.io' ESCAPE '\\'",
        """UPDATE events SET created_at = NOW() - (random()*30||' minutes')::INTERVAL
           WHERE created_at < NOW() - INTERVAL '3 hours'
             AND id IN (SELECT id FROM events ORDER BY created_at DESC LIMIT 1000)""",
    ]
    for sql in ops:
        run(conn, sql)
    return "acme-db reset to clean baseline"


# ── analyticsdb scenarios ──────────────────────────────────────────────────────

def analytics_null_user_ids(conn) -> str:
    """Insert a batch of events with NULL user_id (broken analytics SDK)."""
    count = random.randint(3000, 8000)
    run(conn, """
        INSERT INTO events (user_id, event_name, event_type, created_at)
        SELECT
            NULL,
            CASE (random()*3)::INTEGER
                WHEN 0 THEN 'page_view'
                WHEN 1 THEN 'feature_used'
                ELSE 'dashboard_viewed' END,
            'user_action',
            NOW() - (random()*60||' minutes')::INTERVAL
        FROM generate_series(1, %s)
    """, (count,))
    return f"inserted {count} events with NULL user_id"


def analytics_zero_sessions(conn) -> str:
    """Insert zero-duration sessions (session timeout bug)."""
    count = random.randint(800, 2000)
    run(conn, """
        INSERT INTO sessions (id, user_id, started_at, ended_at, duration_seconds, pages_visited)
        SELECT
            'sess_sim_' || extract(epoch FROM NOW())::BIGINT || '_' || i,
            'usr_' || (random()*8399+1)::INTEGER,
            NOW() - (random()*90||' minutes')::INTERVAL,
            NOW() - (random()*30||' minutes')::INTERVAL,
            0,
            1
        FROM generate_series(1, %s) i
        ON CONFLICT (id) DO NOTHING
    """, (count,))
    return f"inserted {count} zero-duration sessions"


def analytics_mrr_drop(conn) -> str:
    """Zero out MRR for a random sample of paying users (revenue metric anomaly)."""
    pct = random.uniform(0.12, 0.22)
    run(conn, """
        UPDATE users
        SET mrr = 0
        WHERE id IN (
            SELECT id FROM users WHERE mrr > 0
            ORDER BY random()
            LIMIT GREATEST(100, (SELECT (COUNT(*)*%s)::INTEGER FROM users WHERE mrr>0))
        )
    """, (pct,))
    return f"zeroed MRR on ~{pct*100:.0f}% of paying users"


def analytics_user_churn_spike(conn) -> str:
    """Mark a batch of users as high churn risk — cardinality change on churn_risk."""
    count = random.randint(500, 1500)
    run(conn, """
        UPDATE users
        SET churn_risk = round((random()*0.4 + 0.6)::NUMERIC, 3),
            last_seen_at = NOW() - (random()*30||' days')::INTERVAL
        WHERE id IN (
            SELECT id FROM users WHERE (churn_risk IS NULL OR churn_risk < 0.6)
            ORDER BY random() LIMIT %s
        )
    """, (count,))
    return f"marked {count} users as high-churn-risk"


def restore_analytics(conn) -> str:
    """Reset analyticsdb back to a clean, healthy baseline."""
    ops = [
        "DELETE FROM sessions WHERE id LIKE 'sess\\_sim\\_%' ESCAPE '\\'",
        "DELETE FROM sessions WHERE id LIKE 'sess\\_init\\_anomaly\\_%' ESCAPE '\\'",
        """DELETE FROM events
           WHERE user_id IS NULL
             AND created_at > NOW() - INTERVAL '3 hours'""",
        """UPDATE users SET mrr = round((random()*299)::NUMERIC, 2)
           WHERE mrr = 0 AND plan != 'free'""",
    ]
    for sql in ops:
        run(conn, sql)
    return "analyticsdb reset to clean baseline"


# ── API integration ────────────────────────────────────────────────────────────

_api_tokens: dict[str, str] = {}


def api_login(api_url: str, slug: str, email: str, password: str) -> str | None:
    if not _REQUESTS_AVAILABLE:
        return None
    try:
        r = requests.post(f"{api_url}/auth/login",
                          json={"email": email, "password": password, "org_slug": slug},
                          timeout=10)
        if r.status_code == 200:
            return r.json().get("access_token")
    except Exception:
        pass
    return None


def trigger_all_profiles(api_url: str) -> int:
    """Log into each workspace and trigger profile runs for all monitored tables."""
    if not _REQUESTS_AVAILABLE or not api_url:
        return 0

    workspaces = [
        ("acme-corp",  "mounir@acme.io", "acme1234"),
        ("startup-io", "dev@startup.io", "acme1234"),
    ]
    triggered = 0
    for slug, email, password in workspaces:
        token = _api_tokens.get(slug) or api_login(api_url, slug, email, password)
        if not token:
            continue
        _api_tokens[slug] = token
        headers = {"Authorization": f"Bearer {token}"}
        try:
            r = requests.get(f"{api_url}/api/v1/tables", headers=headers, timeout=10)
            if r.status_code != 200:
                continue
            for tbl in r.json():
                resp = requests.post(
                    f"{api_url}/api/v1/tables/{tbl['id']}/profile",
                    headers=headers, timeout=10)
                if resp.status_code in (200, 202):
                    triggered += 1
        except Exception:
            pass
    return triggered


# ── Scenario registry ──────────────────────────────────────────────────────────

# (function, db_target)  — db_target: 'acme' | 'analytics' | 'both'
SCENARIOS: dict[str, tuple | None] = {
    "null_spike":          (null_spike,          "acme"),
    "price_corruption":    (price_corruption,     "acme"),
    "row_drop":            (row_drop,             "acme"),
    "freshness_stall":     (freshness_stall,      "acme"),
    "duplicate_users":     (duplicate_users,      "acme"),
    "null_recovery":       (null_recovery,        "acme"),
    "high_null_payments":  (high_null_payments,   "acme"),
    "restore_acme":        (restore_acme,         "acme"),
    "analytics_null_user_ids":  (analytics_null_user_ids,  "analytics"),
    "analytics_zero_sessions":  (analytics_zero_sessions,  "analytics"),
    "analytics_mrr_drop":       (analytics_mrr_drop,       "analytics"),
    "analytics_user_churn":     (analytics_user_churn_spike,"analytics"),
    "restore_analytics":        (restore_analytics,         "analytics"),
    "restore_all":         None,  # special: runs both restore_acme + restore_analytics
}

ROTATION_POOL = [
    ("null_spike",                4),
    ("price_corruption",          2),
    ("row_drop",                  2),
    ("freshness_stall",           2),
    ("duplicate_users",           2),
    ("high_null_payments",        2),
    ("analytics_null_user_ids",   3),
    ("analytics_zero_sessions",   2),
    ("analytics_mrr_drop",        2),
    ("analytics_user_churn",      1),
    # occasional recovery so incidents can resolve
    ("null_recovery",             3),
    ("restore_acme",              1),
    ("restore_analytics",         1),
]

_WEIGHTED: list[str] = []
for name, weight in ROTATION_POOL:
    _WEIGHTED.extend([name] * weight)


def pick_random() -> str:
    return random.choice(_WEIGHTED)


# ── Runner ─────────────────────────────────────────────────────────────────────

def run_scenario(name: str, acme_conn, analytics_conn, api_url: str = "") -> None:
    log(f"Scenario: {name}")

    if name == "restore_all":
        if acme_conn:
            msg = restore_acme(acme_conn)
            log(f"  acme-db      → {msg}")
        if analytics_conn:
            msg = restore_analytics(analytics_conn)
            log(f"  analytics-db → {msg}")
        if api_url:
            n = trigger_all_profiles(api_url)
            if n:
                log(f"  → triggered {n} profile run(s)")
        return

    entry = SCENARIOS.get(name)
    if entry is None:
        log(f"[ERROR] Unknown scenario '{name}'")
        return

    fn, target = entry
    triggered = False

    if target in ("acme", "both"):
        if acme_conn:
            try:
                msg = fn(acme_conn)
                log(f"  acme-db      → {msg}")
                triggered = True
            except Exception as exc:
                log(f"  acme-db      → [ERROR] {exc}")
                acme_conn.rollback()
        else:
            log("  acme-db      → [SKIP] no connection")

    if target in ("analytics", "both"):
        if analytics_conn:
            try:
                msg = fn(analytics_conn)
                log(f"  analytics-db → {msg}")
                triggered = True
            except Exception as exc:
                log(f"  analytics-db → [ERROR] {exc}")
                analytics_conn.rollback()
        else:
            log("  analytics-db → [SKIP] no connection")

    if triggered and api_url:
        n = trigger_all_profiles(api_url)
        if n:
            log(f"  → triggered {n} profile run(s) via DataWatch API")


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="DataWatch Simulator — injects anomalies into demo databases."
    )
    parser.add_argument("--scenario",  metavar="NAME",
                        help=f"Run a specific scenario once. Options: {', '.join(sorted(SCENARIOS))}")
    parser.add_argument("--interval",  type=int, default=120, metavar="SEC",
                        help="Seconds between scenarios in loop mode (default: 120)")
    parser.add_argument("--acme-db-url",
                        default=DEFAULT_ACME_DB_URL,
                        help="PostgreSQL write URL for acme-db")
    parser.add_argument("--analytics-db-url",
                        default=DEFAULT_ANALYTICS_DB_URL,
                        help="PostgreSQL write URL for analytics-db")
    parser.add_argument("--api-url",   default=DEFAULT_API_URL, metavar="URL",
                        help="DataWatch API URL — triggers profile runs after each scenario")
    parser.add_argument("--list",      action="store_true",
                        help="List available scenarios and exit")
    args = parser.parse_args()

    if args.list:
        print("Scenarios:")
        for name in sorted(SCENARIOS):
            entry = SCENARIOS[name]
            target = "both (reset)" if name == "restore_all" else (entry[1] if entry else "?")
            print(f"  {name:<40} [{target}]")
        return

    log("DataWatch Simulator starting")
    log(f"  acme-db URL      : {args.acme_db_url}")
    log(f"  analytics-db URL : {args.analytics_db_url}")
    if args.api_url:
        log(f"  DataWatch API    : {args.api_url}  (auto profile trigger ON)")
    else:
        log("  DataWatch API    : (not set — profile trigger OFF)")

    acme_conn      = connect(args.acme_db_url,      "acme-db")
    analytics_conn = connect(args.analytics_db_url, "analytics-db")

    if not acme_conn and not analytics_conn:
        log("[ERROR] Could not connect to either database. Exiting.")
        sys.exit(1)
    if acme_conn:
        log("Connected to acme-db")
    if analytics_conn:
        log("Connected to analytics-db")

    if args.scenario:
        run_scenario(args.scenario, acme_conn, analytics_conn, api_url=args.api_url)
        if acme_conn:
            acme_conn.close()
        if analytics_conn:
            analytics_conn.close()
        return

    log(f"Loop mode: random scenario every ~{args.interval}s. Ctrl-C to stop.")
    try:
        while True:
            scenario = pick_random()
            run_scenario(scenario, acme_conn, analytics_conn, api_url=args.api_url)
            jitter = random.randint(-20, 20)
            wait   = max(30, args.interval + jitter)
            log(f"Sleeping {wait}s...")
            time.sleep(wait)
    except KeyboardInterrupt:
        log("Interrupted. Shutting down.")
    finally:
        if acme_conn:
            acme_conn.close()
        if analytics_conn:
            analytics_conn.close()
        log("Simulator stopped.")


if __name__ == "__main__":
    main()
