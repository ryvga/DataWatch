"""Structured relational schema bindings derived from connector DDL snapshots."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class LogicalType(StrEnum):
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    STRING = "string"
    DATE = "date"
    TIMESTAMP = "timestamp"
    BINARY = "binary"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SchemaColumn:
    name: str
    data_type: str
    logical_type: LogicalType
    nullable: bool

    def payload(self) -> dict:
        return {
            "name": self.name,
            "dataType": self.data_type,
            "logicalType": self.logical_type.value,
            "nullable": self.nullable,
        }


@dataclass(frozen=True)
class RelationBinding:
    asset_id: UUID
    source_type: str
    schema_name: str
    table_name: str
    columns: tuple[SchemaColumn, ...]
    schema_fingerprint: str

    def column(self, name: str) -> SchemaColumn | None:
        return next((column for column in self.columns if column.name == name), None)

    def payload(self) -> dict:
        return {
            "assetId": str(self.asset_id),
            "sourceType": self.source_type,
            "schema": self.schema_name,
            "table": self.table_name,
            "schemaFingerprint": self.schema_fingerprint,
            "columns": [column.payload() for column in self.columns],
        }


class SchemaBindingError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_CONSTRAINT_PREFIXES = (
    "CONSTRAINT ",
    "PRIMARY KEY",
    "FOREIGN KEY",
    "UNIQUE ",
    "CHECK ",
    "KEY ",
    "INDEX ",
)

_INLINE_CONSTRAINTS = (
    " NOT NULL",
    " NULLABLE",
    " NULL",
    " REQUIRED",
    " DEFAULT",
    " PRIMARY KEY",
    " UNIQUE",
    " REFERENCES",
    " CHECK",
    " COLLATE",
    " GENERATED",
    " IDENTITY",
    " IS_PARTITION_KEY",
    " IS_CLUSTERING_KEY",
)


def _split_items(body: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    i = 0
    while i < len(body):
        char = body[i]
        if quote:
            current.append(char)
            if quote == "]" and char == "]":
                if i + 1 < len(body) and body[i + 1] == "]":
                    current.append(body[i + 1])
                    i += 1
                else:
                    quote = None
            elif quote in {'"', "`", "'"} and char == quote:
                if i + 1 < len(body) and body[i + 1] == quote:
                    current.append(body[i + 1])
                    i += 1
                else:
                    quote = None
            i += 1
            continue
        if char in {'"', "`", "'"}:
            quote = char
        elif char == "[":
            quote = "]"
        elif char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            if "".join(current).strip():
                items.append("".join(current).strip())
            current = []
            i += 1
            continue
        current.append(char)
        i += 1
    if "".join(current).strip():
        items.append("".join(current).strip())
    return items


def _split_identifier(item: str) -> tuple[str, str] | None:
    item = item.strip()
    if not item:
        return None
    openers = {'"': '"', "`": "`", "[": "]"}
    closer = openers.get(item[0])
    if closer:
        chars: list[str] = []
        i = 1
        while i < len(item):
            char = item[i]
            if char == closer:
                if i + 1 < len(item) and item[i + 1] == closer:
                    chars.append(closer)
                    i += 2
                    continue
                return "".join(chars), item[i + 1 :].strip()
            chars.append(char)
            i += 1
        return None
    parts = item.split(maxsplit=1)
    return (parts[0], parts[1]) if len(parts) == 2 else None


def logical_type_for(data_type: str) -> LogicalType:
    normalized = re.sub(r"\s+", " ", data_type.strip().lower())
    base = normalized.split("(", 1)[0].strip()
    if any(token in base for token in ("timestamp", "datetime", "timestamptz")):
        return LogicalType.TIMESTAMP
    if re.search(r"\bdate\b", base):
        return LogicalType.DATE
    if any(token in base for token in ("bool", "bit")):
        return LogicalType.BOOLEAN
    if re.search(
        r"\b(tinyint|smallint|mediumint|integer|bigint|hugeint|uinteger|ubigint|"
        r"usmallint|utinyint|u?int\d*|serial|bigserial)\b",
        base,
    ):
        return LogicalType.INTEGER
    if any(
        token in base
        for token in ("numeric", "decimal", "number", "real", "float", "double", "money")
    ):
        return LogicalType.NUMBER
    if any(token in base for token in ("binary", "blob", "bytea", "bytes", "varbinary")):
        return LogicalType.BINARY
    if any(
        token in base
        for token in ("char", "text", "string", "uuid", "json", "xml", "enum")
    ):
        return LogicalType.STRING
    return LogicalType.UNKNOWN


def parse_ddl_columns(ddl: str | None) -> tuple[SchemaColumn, ...]:
    if not ddl or "(" not in ddl or ")" not in ddl:
        return ()
    body = ddl[ddl.find("(") + 1 : ddl.rfind(")")]
    columns: list[SchemaColumn] = []
    seen: set[str] = set()
    for item in _split_items(body):
        upper_item = item.lstrip().upper()
        if upper_item.startswith(_CONSTRAINT_PREFIXES):
            continue
        split = _split_identifier(item)
        if not split:
            continue
        name, remainder = split
        upper_remainder = f" {remainder.upper()}"
        boundaries = [
            upper_remainder.find(token)
            for token in _INLINE_CONSTRAINTS
            if upper_remainder.find(token) >= 0
        ]
        boundary = min(boundaries) if boundaries else len(upper_remainder)
        data_type = re.sub(r"\s+", " ", remainder[: max(0, boundary - 1)].strip()).lower()
        if not name or not data_type or name in seen:
            continue
        nullable = " NOT NULL" not in upper_remainder and " REQUIRED" not in upper_remainder
        columns.append(
            SchemaColumn(
                name=name,
                data_type=data_type,
                logical_type=logical_type_for(data_type),
                nullable=nullable,
            )
        )
        seen.add(name)
    return tuple(columns)


def schema_fingerprint(columns: tuple[SchemaColumn, ...]) -> str:
    canonical = "|".join(
        sorted(f"{column.name}:{column.data_type}" for column in columns)
    )
    return hashlib.md5(canonical.encode("utf-8")).hexdigest()


def build_relation_binding(
    *,
    asset_id: UUID,
    source_type: str,
    schema_name: str,
    table_name: str,
    ddl: str | None,
    latest_schema_fingerprint: str | None,
) -> RelationBinding:
    columns = parse_ddl_columns(ddl)
    if not columns:
        raise SchemaBindingError(
            "schema_snapshot_missing",
            "A structured schema snapshot is required before this monitor can compile",
        )
    computed_fingerprint = schema_fingerprint(columns)
    if (
        latest_schema_fingerprint
        and latest_schema_fingerprint != computed_fingerprint
    ):
        raise SchemaBindingError(
            "schema_snapshot_stale",
            "The stored DDL snapshot does not match the latest successful profile",
        )
    return RelationBinding(
        asset_id=asset_id,
        source_type=source_type.lower(),
        schema_name=schema_name,
        table_name=table_name,
        columns=columns,
        schema_fingerprint=computed_fingerprint,
    )
