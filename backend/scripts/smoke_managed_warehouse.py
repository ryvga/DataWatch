"""Credential-gated managed warehouse connection/discovery/profile smoke."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.connectors.factory import ConnectorFactory  # noqa: E402
from app.services.profiler import ProfilerService  # noqa: E402

MANAGED_TYPES = {"bigquery", "snowflake", "redshift", "databricks"}


async def smoke(source_type: str, config: dict, schema: str | None, table: str | None) -> None:
    connector = ConnectorFactory.create(source_type, config)
    try:
        if not await connector.test_connection():
            raise RuntimeError(f"{source_type} connection smoke failed")
        schemas = await connector.discover_schemas()
        if not schemas:
            raise RuntimeError(f"{source_type} discovery returned no schemas")
        if schema and table:
            result = await ProfilerService().profile(connector, schema, table)
            if result.error:
                raise RuntimeError(f"{source_type} profile smoke failed: {result.error}")
            print(f"{source_type}: profile row_count={result.row_count}")
        else:
            print(f"{source_type}: connection and discovery passed ({len(schemas)} schemas)")
    finally:
        await connector.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", required=True, choices=sorted(MANAGED_TYPES))
    parser.add_argument("--config-env", required=True)
    parser.add_argument("--schema-env")
    parser.add_argument("--table-env")
    args = parser.parse_args()
    raw_config = os.environ.get(args.config_env)
    if not raw_config:
        raise SystemExit(f"missing credential configuration environment variable: {args.config_env}")
    config = json.loads(raw_config)
    schema = os.environ.get(args.schema_env) if args.schema_env else None
    table = os.environ.get(args.table_env) if args.table_env else None
    if bool(schema) != bool(table):
        raise SystemExit("schema and table smoke variables must be provided together")
    asyncio.run(smoke(args.type, config, schema, table))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
