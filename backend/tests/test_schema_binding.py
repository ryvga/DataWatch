import uuid

import pytest

from app.services.schema_binding import (
    LogicalType,
    SchemaBindingError,
    build_relation_binding,
    parse_ddl_columns,
)


def test_parse_single_line_and_multiline_ddl_with_quoted_identifiers_and_constraints():
    ddl = (
        'CREATE TABLE "odd schema"."orders" ('
        '"order id" bigint NOT NULL, '
        'amount numeric(12, 2) NULL, '
        '[created at] timestamp without time zone NOT NULL, '
        '`is active` boolean DEFAULT true, '
        'PRIMARY KEY ("order id")'
        ');'
    )
    columns = parse_ddl_columns(ddl)

    assert [(column.name, column.data_type, column.logical_type, column.nullable) for column in columns] == [
        ("order id", "bigint", LogicalType.INTEGER, False),
        ("amount", "numeric(12, 2)", LogicalType.NUMBER, True),
        ("created at", "timestamp without time zone", LogicalType.TIMESTAMP, False),
        ("is active", "boolean", LogicalType.BOOLEAN, True),
    ]


def test_parse_connector_type_families():
    ddl = """CREATE TABLE main.events (
      id INTEGER NOT NULL,
      ratio DOUBLE PRECISION NULL,
      label CHARACTER VARYING(255) NULL,
      payload JSONB NULL,
      happened_on DATE NULL,
      bytes BLOB NULL,
      warehouse_id INT64 NOT NULL,
      giant_id HUGEINT NULL
    );"""
    columns = parse_ddl_columns(ddl)
    assert [column.logical_type for column in columns] == [
        LogicalType.INTEGER,
        LogicalType.NUMBER,
        LogicalType.STRING,
        LogicalType.STRING,
        LogicalType.DATE,
        LogicalType.BINARY,
        LogicalType.INTEGER,
        LogicalType.INTEGER,
    ]


def test_relation_binding_requires_a_parseable_known_schema():
    asset_id = uuid.uuid4()
    binding = build_relation_binding(
        asset_id=asset_id,
        source_type="postgres",
        schema_name="public",
        table_name="orders",
        ddl="CREATE TABLE public.orders (id integer NOT NULL);",
        latest_schema_fingerprint=None,
    )
    assert binding.asset_id == asset_id
    assert binding.column("id").logical_type == LogicalType.INTEGER
    assert len(binding.schema_fingerprint) == 32

    with pytest.raises(SchemaBindingError, match="structured schema") as missing:
        build_relation_binding(
            asset_id=asset_id,
            source_type="postgres",
            schema_name="public",
            table_name="orders",
            ddl=None,
            latest_schema_fingerprint=None,
        )
    assert missing.value.code == "schema_snapshot_missing"

    unknown = build_relation_binding(
        asset_id=asset_id,
        source_type="postgres",
        schema_name="public",
        table_name="orders",
        ddl="CREATE TABLE public.orders (payload mystery_type NULL);",
        latest_schema_fingerprint=None,
    )
    assert unknown.column("payload").logical_type == LogicalType.UNKNOWN

    with pytest.raises(SchemaBindingError, match="does not match") as stale:
        build_relation_binding(
            asset_id=asset_id,
            source_type="postgres",
            schema_name="public",
            table_name="orders",
            ddl="CREATE TABLE public.orders (id integer NOT NULL);",
            latest_schema_fingerprint="stale-profile-fingerprint",
        )
    assert stale.value.code == "schema_snapshot_stale"
