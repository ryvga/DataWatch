#!/usr/bin/env python3
"""Measure the tiny seeded SQL connector profile path for PFE evidence.

This is a repeatable regression baseline, not a load test or production SLA. The
MySQL, MariaDB, and SQL Server targets are the isolated services declared in
``docker-compose.test-dbs.yml``. SQLite is created in a temporary directory.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path

from app.connectors.mysql import MySQLConnector
from app.connectors.sqlite import SQLiteConnector
from app.connectors.sqlserver import SQLServerConnector
from app.services.profiler import ProfilerService


def _summary(samples: list[float]) -> dict[str, float | int]:
    ordered = sorted(samples)
    p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "runs": len(ordered),
        "p50_ms": round(statistics.median(ordered), 2),
        "p95_ms": round(ordered[p95_index], 2),
        "min_ms": round(ordered[0], 2),
        "max_ms": round(ordered[-1], 2),
    }


async def _measure(connector, schema: str, table: str, runs: int) -> dict:
    profiler = ProfilerService()
    assert await connector.test_connection()
    # One warm-up keeps import/connection setup out of the persistent-query samples.
    warmup = await profiler.profile(
        connector, schema, table, freshness_column="created_at"
    )
    if warmup.error:
        raise RuntimeError(warmup.error)

    samples = []
    for _ in range(runs):
        started = time.perf_counter()
        result = await profiler.profile(
            connector, schema, table, freshness_column="created_at"
        )
        elapsed_ms = (time.perf_counter() - started) * 1_000
        if result.error or result.row_count != 3:
            raise RuntimeError(result.error or f"unexpected row count: {result.row_count}")
        samples.append(elapsed_ms)
    return _summary(samples)


async def _run(runs: int, include_sqlserver: bool) -> dict:
    targets = {
        "mysql": (
            MySQLConnector(
                {
                    "host": os.getenv("MYSQL_TEST_HOST", "test-mysql"),
                    "port": int(os.getenv("MYSQL_TEST_PORT", "3306")),
                    "database": "datawatch_connector_test",
                    "username": "datawatch",
                    "password": "datawatch",
                    "tls_mode": "disabled",
                }
            ),
            "datawatch_connector_test",
            "orders",
        ),
        "mariadb": (
            MySQLConnector(
                {
                    "host": os.getenv("MARIADB_TEST_HOST", "test-mariadb"),
                    "port": int(os.getenv("MARIADB_TEST_PORT", "3306")),
                    "database": "datawatch_connector_test",
                    "username": "datawatch",
                    "password": "datawatch",
                    "tls_mode": "disabled",
                }
            ),
            "datawatch_connector_test",
            "orders",
        ),
    }
    if include_sqlserver:
        targets["sqlserver"] = (
            SQLServerConnector(
                {
                    "host": os.getenv("SQLSERVER_TEST_HOST", "test-sqlserver"),
                    "port": int(os.getenv("SQLSERVER_TEST_PORT", "1433")),
                    "database": "datawatch_connector_test",
                    "username": "datawatch_monitor",
                    "password": "DataWatch-Monitor-2026!",
                    "tls_mode": "disabled",
                }
            ),
            "dbo",
            "orders",
        )

    observations = {}
    try:
        for name, (connector, schema, table) in targets.items():
            observations[name] = await _measure(connector, schema, table, runs)
    finally:
        for connector, _, _ in targets.values():
            await connector.close()

    with tempfile.TemporaryDirectory(prefix="datawatch-sql-benchmark-") as directory:
        sqlite_path = Path(directory) / "connector.db"
        conn = sqlite3.connect(sqlite_path)
        try:
            conn.executescript(
                "CREATE TABLE orders (id INTEGER NOT NULL, amount REAL, status TEXT, "
                "created_at TEXT);"
                "INSERT INTO orders VALUES "
                "(1, 12.5, 'paid', '2026-07-19 10:00:00'),"
                "(2, 0.0, '', '2026-07-19 11:00:00'),"
                "(3, NULL, NULL, '2026-07-19 12:00:00');"
            )
            conn.commit()
        finally:
            conn.close()
        connector = SQLiteConnector({"path": str(sqlite_path)})
        try:
            observations["sqlite"] = await _measure(connector, "main", "orders", runs)
        finally:
            await connector.close()

    return observations


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--include-sqlserver", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.runs <= 1_000:
        parser.error("--runs must be between 1 and 1000")
    print(
        json.dumps(
            asyncio.run(_run(args.runs, args.include_sqlserver)),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
