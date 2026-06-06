#!/usr/bin/env python3
"""Run an API-level connector matrix against the local DataWatch stack.

The suite intentionally goes through FastAPI instead of importing app code. That
keeps Docker networking, credential encryption, source CRUD, discovery, and
custom monitor execution in the verification path.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = os.environ.get("DATAWATCH_BASE_URL", "http://localhost:8000").rstrip("/")
ORG_SLUG = os.environ.get("DATAWATCH_ORG_SLUG", "acme-corp")
EMAIL = os.environ.get("DATAWATCH_EMAIL", "mounir@acme.io")
PASSWORD = os.environ.get("DATAWATCH_PASSWORD", "demo1234")
TARGET_TABLE_ID = os.environ.get(
    "DATAWATCH_MATRIX_TABLE_ID",
    "3856dac6-46a1-462b-a8ce-f6c1de0d983e",
)


@dataclass
class MatrixContext:
    token: str
    created_sources: list[str]
    created_monitors: list[tuple[str, str]]


class MatrixFailure(RuntimeError):
    pass


def request_json(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    expected: tuple[int, ...] = (200,),
    timeout: int = 45,
) -> Any:
    url = f"{BASE_URL}{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            if resp.status not in expected:
                raise MatrixFailure(f"{method} {path} returned {resp.status}: {raw}")
            if resp.status == 204 or not raw:
                return None
            return json.loads(raw)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        if exc.code in expected:
            return json.loads(raw) if raw else None
        raise MatrixFailure(f"{method} {path} returned {exc.code}: {raw}") from exc
    except URLError as exc:
        raise MatrixFailure(f"{method} {path} failed: {exc.reason}") from exc


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise MatrixFailure(message)


def step(name: str) -> None:
    print(f"==> {name}", flush=True)


def login() -> str:
    step("login")
    result = request_json(
        "POST",
        "/auth/login",
        body={"email": EMAIL, "password": PASSWORD, "org_slug": ORG_SLUG},
    )
    token = result.get("access_token")
    assert_true(bool(token), "login did not return an access token")
    return token


def check_connector_metadata(token: str) -> None:
    step("connector metadata")
    types = request_json("GET", "/api/v1/sources/connector-types", token=token)
    seen = {item["type"] for item in types}
    for expected in ("postgres", "mongodb", "duckdb"):
        assert_true(expected in seen, f"connector metadata missing {expected}")


def preview_connection(token: str, label: str, source_type: str, config: dict[str, Any]) -> None:
    step(f"preview {label}")
    result = request_json(
        "POST",
        "/api/v1/sources/test-connection",
        token=token,
        body={"type": source_type, "connection_config": config},
        timeout=60,
    )
    assert_true(result.get("connected") is True, f"{label} did not connect: {result}")


def preview_all_connections(token: str) -> None:
    preview_connection(
        token,
        "SQL demo Postgres",
        "postgres",
        {
            "host": "demo-db",
            "port": 5432,
            "database": "shopDemo",
            "username": "readonly_user",
            "password": "readonly_pass",
        },
    )
    preview_connection(
        token,
        "warehouse analytics Postgres",
        "postgres",
        {
            "host": "analytics-db",
            "port": 5432,
            "database": "analyticsdb",
            "username": "analytics_ro",
            "password": "readonly_pass",
        },
    )
    preview_connection(
        token,
        "NoSQL MongoDB",
        "mongodb",
        {"uri": "mongodb://test-mongo:27017", "database": "datawatch_nosql"},
    )


def list_sources(token: str) -> list[dict[str, Any]]:
    return request_json("GET", "/api/v1/sources", token=token)


def find_source(token: str, name: str) -> dict[str, Any]:
    sources = list_sources(token)
    matches = [source for source in sources if source["name"] == name]
    assert_true(bool(matches), f"source not found: {name}")
    return matches[0]


def assert_discovery_has(
    token: str,
    source_id: str,
    schema_name: str,
    table_name: str,
) -> None:
    discovery = request_json(
        "POST",
        f"/api/v1/sources/{source_id}/discover",
        token=token,
        timeout=90,
    )
    schemas = {schema["name"]: schema for schema in discovery.get("schemas", [])}
    assert_true(schema_name in schemas, f"schema {schema_name} missing from discovery")
    tables = {table["name"] for table in schemas[schema_name].get("tables", [])}
    assert_true(table_name in tables, f"table {schema_name}.{table_name} missing from discovery")


def assert_schema_ddl_contains(
    token: str,
    source_id: str,
    schema_name: str,
    table_name: str,
    required_text: str,
) -> None:
    query = urlencode({"schema_name": schema_name, "table_name": table_name})
    result = request_json(
        "GET",
        f"/api/v1/sources/{source_id}/table-schema?{query}",
        token=token,
        timeout=60,
    )
    ddl = result.get("ddl", "")
    assert_true(required_text in ddl, f"DDL for {schema_name}.{table_name} missing {required_text!r}: {ddl[:500]}")


def check_existing_sources(token: str) -> None:
    step("existing SQL and warehouse sources")
    sql_source = find_source(token, "Shop Demo DB (live)")
    warehouse_source = find_source(token, "Analytics Warehouse")

    assert_discovery_has(token, sql_source["id"], "public", "orders")
    assert_schema_ddl_contains(token, sql_source["id"], "public", "orders", "payment_status")

    assert_discovery_has(token, warehouse_source["id"], "public", "events")
    assert_schema_ddl_contains(token, warehouse_source["id"], "public", "events", "event_name")


def create_mongo_source(ctx: MatrixContext) -> str:
    step("create temporary MongoDB source")
    suffix = int(time.time())
    source = request_json(
        "POST",
        "/api/v1/sources",
        token=ctx.token,
        body={
            "name": f"Matrix MongoDB {suffix}",
            "type": "mongodb",
            "connection_config": {
                "uri": "mongodb://test-mongo:27017",
                "database": "datawatch_nosql",
            },
        },
        timeout=60,
        expected=(201,),
    )
    source_id = source["id"]
    ctx.created_sources.append(source_id)
    assert_discovery_has(ctx.token, source_id, "datawatch_nosql", "events")
    assert_schema_ddl_contains(ctx.token, source_id, "datawatch_nosql", "events", "metadata.browser")
    return source_id


def check_custom_monitor(ctx: MatrixContext) -> None:
    step("custom monitor create/run/delete")
    monitor = request_json(
        "POST",
        f"/api/v1/tables/{TARGET_TABLE_ID}/custom-monitors",
        token=ctx.token,
        body={
            "name": f"Matrix row-count monitor {int(time.time())}",
            "description": "Connector matrix monitor that should pass on analytics events.",
            "sql_query": "SELECT 0 AS violations",
            "severity": "P3",
            "run_on_profile": False,
        },
        expected=(201,),
    )
    monitor_id = monitor["id"]
    ctx.created_monitors.append((TARGET_TABLE_ID, monitor_id))

    result = request_json(
        "POST",
        f"/api/v1/tables/{TARGET_TABLE_ID}/custom-monitors/{monitor_id}/run",
        token=ctx.token,
        timeout=90,
    )
    assert_true(result.get("passed") is True, f"custom monitor did not pass: {result}")
    assert_true(result.get("violation_count") == 0, f"custom monitor returned violations: {result}")


def cleanup(ctx: MatrixContext) -> None:
    for table_id, monitor_id in reversed(ctx.created_monitors):
        try:
            request_json(
                "DELETE",
                f"/api/v1/tables/{table_id}/custom-monitors/{monitor_id}",
                token=ctx.token,
                expected=(204, 404),
            )
        except MatrixFailure as exc:
            print(f"cleanup warning: monitor {monitor_id}: {exc}", file=sys.stderr)

    for source_id in reversed(ctx.created_sources):
        try:
            request_json(
                "DELETE",
                f"/api/v1/sources/{source_id}",
                token=ctx.token,
                expected=(204, 404),
            )
        except MatrixFailure as exc:
            print(f"cleanup warning: source {source_id}: {exc}", file=sys.stderr)


def main() -> int:
    ctx: MatrixContext | None = None
    try:
        token = login()
        ctx = MatrixContext(token=token, created_sources=[], created_monitors=[])
        check_connector_metadata(token)
        preview_all_connections(token)
        check_existing_sources(token)
        create_mongo_source(ctx)
        check_custom_monitor(ctx)
    except MatrixFailure as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        if ctx:
            cleanup(ctx)

    print("\nConnector matrix passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
