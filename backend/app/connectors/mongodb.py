import asyncio
import hashlib
import json
import logging
import math
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from app.connectors.base import (
    BaseConnector,
    ConnectorConfigurationError,
    SchemaInfo,
    TableInfo,
)

logger = logging.getLogger(__name__)

_SYSTEM_DATABASES = {"admin", "local", "config"}
_DEFAULT_SAMPLE_SIZE = 1000
_MIN_SAMPLE_SIZE = 25
_MAX_SAMPLE_SIZE = 1000
_MAX_FIELD_PATHS = 500
_MAX_NESTING_DEPTH = 8
_MAX_ARRAY_ITEMS = 100
_MAX_PROFILE_DOCUMENT_BYTES = 128 * 1024
_MAX_PROFILE_SAMPLE_BYTES = 8 * 1024 * 1024
_SAMPLE_BATCH_SIZE = 16


class MongoDBConnector(BaseConnector):
    """Async MongoDB connector via PyMongo's native asyncio client."""

    native_profile_kind = "document"

    def __init__(self, config: dict):
        self._config = config
        self._client = None

    def _get_client(self):
        if self._client is None:
            from pymongo import AsyncMongoClient
            from pymongo.server_api import ServerApi

            tls_mode = str(self._config.get("tls_mode", "verify_identity")).lower()
            if tls_mode not in {"verify_identity", "disabled"}:
                raise ValueError("tls_mode must be 'verify_identity' or 'disabled'")
            tls_options = {"tls": False}
            if tls_mode == "verify_identity":
                tls_options = {
                    "tls": True,
                    "tlsAllowInvalidCertificates": False,
                    "tlsAllowInvalidHostnames": False,
                }
            self._client = AsyncMongoClient(
                self._config["uri"],
                **tls_options,
                serverSelectionTimeoutMS=10_000,
                connectTimeoutMS=10_000,
                socketTimeoutMS=30_000,
                maxPoolSize=5,
                appName="DataWatch",
                server_api=ServerApi("1", strict=False, deprecation_errors=True),
            )
        return self._client

    def _database_name(self) -> str:
        configured = self._config.get("database")
        if not configured:
            from pymongo.uri_parser import parse_uri

            parsed = parse_uri(self._config["uri"])
            configured = parsed.get("database")
        if not configured:
            raise ConnectorConfigurationError("MongoDB requires one configured database.")
        configured = str(configured)
        if "\x00" in configured:
            raise ConnectorConfigurationError("MongoDB database name is invalid.")
        if configured.lower() in _SYSTEM_DATABASES:
            raise ConnectorConfigurationError(
                "MongoDB system databases cannot be monitored."
            )
        return configured

    def _collection(self, database: str, collection: str):
        configured_database = self._database_name()
        if database != configured_database:
            raise ConnectorConfigurationError(
                "MongoDB operations are restricted to the configured database."
            )
        if (
            not collection
            or "\x00" in collection
            or collection.lower().startswith("system.")
        ):
            raise ConnectorConfigurationError("MongoDB collection name is invalid.")
        return self._get_client()[configured_database][collection]

    def _sample_size(self) -> int:
        try:
            size = int(self._config.get("profile_sample_size", _DEFAULT_SAMPLE_SIZE))
        except (TypeError, ValueError) as exc:
            raise ValueError("profile_sample_size must be an integer") from exc
        if size < _MIN_SAMPLE_SIZE or size > _MAX_SAMPLE_SIZE:
            raise ValueError(
                f"profile_sample_size must be between {_MIN_SAMPLE_SIZE} and {_MAX_SAMPLE_SIZE}"
            )
        return size

    async def test_connection(self) -> bool:
        try:
            client = self._get_client()
            database_name = self._database_name()
            self._sample_size()
            await client.admin.command("ping")
            await client[database_name].list_collection_names()
            return True
        except Exception as e:
            logger.warning("MongoDB connection test failed: %s", type(e).__name__)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        client = self._get_client()
        database_names = [self._database_name()]

        schemas: list[SchemaInfo] = []
        for database_name in database_names:
            if database_name in _SYSTEM_DATABASES:
                continue

            database = client[database_name]
            collection_names = await database.list_collection_names()
            semaphore = asyncio.Semaphore(8)

            async def _table_info(collection_name: str) -> TableInfo:
                collection = database[collection_name]
                async with semaphore:
                    estimated_rows = await collection.estimated_document_count()
                return TableInfo(
                    name=collection_name,
                    estimated_rows=estimated_rows,
                )

            tables = list(
                await asyncio.gather(
                    *(
                        _table_info(collection_name)
                        for collection_name in sorted(collection_names)
                    )
                )
            )
            schemas.append(SchemaInfo(name=database_name, tables=tables))

        return schemas

    async def execute_profile_query(self, query: str) -> dict:
        raise NotImplementedError(
            "MongoDB does not execute caller-provided aggregation pipelines"
        )

    async def get_table_ddl(self, schema: str, table: str) -> str:
        snapshot, _column_names = await self.get_table_schema(schema, table)
        return snapshot

    async def get_table_schema(
        self,
        schema: str,
        table: str,
    ) -> tuple[str, set[str]]:
        collection = self._collection(schema, table)
        schema_sample_size = min(100, self._sample_size())
        sampled = await self._sample_documents(
            collection,
            requested=schema_sample_size,
            max_time_ms=10_000,
        )
        documents = sampled["documents"]
        field_stats = _summarize_fields(documents)

        lines = []
        for field_path in _sort_field_paths(field_stats):
            stats = field_stats[field_path]
            inferred_type = _format_type_distribution(stats["type_distribution"])
            nullable = "NOT NULL" if stats["required"] else "NULL"
            presence = _format_percent(stats["presence_rate"] * 100)
            lines.append(
                f"  {_quote_identifier(field_path)} {inferred_type} {nullable} {presence}"
            )

        snapshot = (
            f"CREATE COLLECTION {_quote_identifier(schema)}."
            f"{_quote_identifier(table)} (\n"
            + ",\n".join(lines)
            + "\n);"
        )
        return snapshot, set(field_stats)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def get_collection_stats(self, database: str, collection: str) -> dict:
        coll = self._collection(database, collection)
        db = self._get_client()[self._database_name()]

        document_count = await coll.estimated_document_count()
        avg_document_size_bytes = None
        try:
            raw_stats = await db.command("collStats", collection)
            avg_document_size_bytes = _numeric_value(raw_stats.get("avgObjSize"))
        except Exception as e:
            logger.warning("MongoDB collection stats failed: %s", type(e).__name__)

        sample_size = self._sample_size()
        sampled = await self._sample_documents(
            coll,
            requested=sample_size,
            max_time_ms=30_000,
        )
        documents = sampled["documents"]
        field_stats = _summarize_fields(documents)

        return {
            "document_count": document_count,
            "avg_document_size_bytes": avg_document_size_bytes,
            "sample_size": len(documents),
            "sampled_bytes": sampled["sampled_bytes"],
            "sample_byte_budget": _MAX_PROFILE_SAMPLE_BYTES,
            "sample_byte_budget_exhausted": sampled["byte_budget_exhausted"],
            "oversized_sampled_count": sampled["oversized_count"],
            "field_stats": {
                field_path: {
                    "type_distribution": stats["type_distribution"],
                    "presence_rate": stats["presence_rate"],
                    "null_rate": stats["null_rate"],
                    "numeric_min": stats["numeric_min"],
                    "numeric_max": stats["numeric_max"],
                    "numeric_mean": stats["numeric_mean"],
                    "min_len": stats["min_len"],
                    "max_len": stats["max_len"],
                    "avg_len": stats["avg_len"],
                    "required": stats["required"],
                }
                for field_path, stats in field_stats.items()
            },
            "fields_truncated": len(field_stats) >= _MAX_FIELD_PATHS,
        }

    async def _sample_documents(
        self,
        collection,
        *,
        requested: int,
        max_time_ms: int,
    ) -> dict:
        pipeline = [
            {"$sample": {"size": requested}},
            {
                "$project": {
                    "_datawatch_size": {"$bsonSize": "$$ROOT"},
                    "_datawatch_document": {
                        "$cond": [
                            {
                                "$lte": [
                                    {"$bsonSize": "$$ROOT"},
                                    _MAX_PROFILE_DOCUMENT_BYTES,
                                ]
                            },
                            "$$ROOT",
                            None,
                        ]
                    },
                }
            },
        ]
        cursor = await collection.aggregate(
            pipeline,
            maxTimeMS=max_time_ms,
            allowDiskUse=False,
            batchSize=_SAMPLE_BATCH_SIZE,
        )
        documents: list[dict] = []
        sampled_bytes = 0
        oversized_count = 0
        byte_budget_exhausted = False
        try:
            async for envelope in cursor:
                document = envelope.get("_datawatch_document")
                document_size = int(envelope.get("_datawatch_size") or 0)
                if document is None or document_size > _MAX_PROFILE_DOCUMENT_BYTES:
                    oversized_count += 1
                    continue
                if sampled_bytes + document_size > _MAX_PROFILE_SAMPLE_BYTES:
                    byte_budget_exhausted = True
                    break
                documents.append(document)
                sampled_bytes += document_size
        finally:
            await cursor.close()
        return {
            "documents": documents,
            "sampled_bytes": sampled_bytes,
            "byte_budget_exhausted": byte_budget_exhausted,
            "oversized_count": oversized_count,
        }

    async def validate_profile_config(
        self,
        schema: str,
        table: str,
        freshness_column: str | None,
    ) -> None:
        if freshness_column is None:
            return
        collection = self._collection(schema, table)
        index_information = await collection.index_information()
        if not _has_leading_index(index_information, freshness_column):
            raise ConnectorConfigurationError(
                "MongoDB freshness_column must be the leading field of an index."
            )
        cursor = collection.find(
            {freshness_column: {"$type": "date"}},
            {freshness_column: 1, "_id": 0},
        ).sort(freshness_column, -1).limit(1).max_time_ms(10_000)
        rows = await cursor.to_list(length=1)
        if not rows or not isinstance(_nested_value(rows[0], freshness_column), datetime):
            raise ConnectorConfigurationError(
                "MongoDB freshness_column must contain an indexed scalar BSON date."
            )

    async def collect_native_profile(
        self,
        schema: str,
        table: str,
        freshness_column: str | None,
    ) -> dict:
        await self.validate_profile_config(schema, table, freshness_column)
        stats = await self.get_collection_stats(schema, table)
        field_stats = stats["field_stats"]

        fingerprint_payload = [
            {
                "field": field_path,
                "types": sorted(field_stats[field_path]["type_distribution"]),
                "required": field_stats[field_path]["required"],
            }
            for field_path in sorted(field_stats)
        ]
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()

        column_metrics: dict[str, dict] = {
            "_collection": {
                "avg_document_size_bytes": stats["avg_document_size_bytes"],
                "sample_size": stats["sample_size"],
            }
        }
        for field_path, field in field_stats.items():
            present_count = sum(field["type_distribution"].values())
            metrics = {
                key: value
                for key, value in field.items()
                if key != "required" and value is not None
            }
            metrics["type_rates"] = {
                type_name: count / present_count if present_count else 0.0
                for type_name, count in field["type_distribution"].items()
            }
            metrics["sample_size"] = stats["sample_size"]
            column_metrics[field_path] = metrics

        freshness_seconds = None
        if freshness_column is not None:
            collection = self._collection(schema, table)
            cursor = collection.find(
                {freshness_column: {"$type": "date"}},
                {freshness_column: 1, "_id": 0},
            ).sort(freshness_column, -1).limit(1).max_time_ms(10_000)
            rows = await cursor.to_list(length=1)
            newest = _nested_value(rows[0], freshness_column) if rows else None
            if not isinstance(newest, datetime):
                raise ConnectorConfigurationError(
                    "MongoDB freshness_column did not return a scalar BSON date."
                )
            if newest.tzinfo is None:
                newest = newest.replace(tzinfo=timezone.utc)
            freshness_seconds = (
                datetime.now(timezone.utc) - newest.astimezone(timezone.utc)
            ).total_seconds()

        return {
            "row_count": stats["document_count"],
            "freshness_seconds": freshness_seconds,
            "schema_fingerprint": fingerprint,
            "column_metrics": column_metrics,
            "profile_provenance": {
                "profile_mode": "sampled_native",
                "connector": "mongodb",
                "count_mode": "estimated",
                "population_estimate": stats["document_count"],
                "sample_strategy": "random_bounded",
                "sample_size": stats["sample_size"],
                "sample_limit": self._sample_size(),
                "sampled_bytes": stats["sampled_bytes"],
                "sample_byte_budget": stats["sample_byte_budget"],
                "sample_byte_budget_exhausted": stats["sample_byte_budget_exhausted"],
                "document_byte_limit": _MAX_PROFILE_DOCUMENT_BYTES,
                "oversized_sampled_count": stats["oversized_sampled_count"],
                "array_item_limit": _MAX_ARRAY_ITEMS,
                "schema_mode": "sampled",
                "field_limit": _MAX_FIELD_PATHS,
                "fields_truncated": stats["fields_truncated"],
            },
        }


def _summarize_fields(documents: list[dict]) -> dict:
    total_documents = len(documents)
    summaries: dict[str, dict] = {}

    for document in documents:
        flattened = dict(
            _flatten_document(document, max_depth=_MAX_NESTING_DEPTH)
        )
        for field_path, value in flattened.items():
            if field_path not in summaries:
                if len(summaries) >= _MAX_FIELD_PATHS:
                    continue
                summaries[field_path] = {
                    "present_count": 0,
                    "null_count": 0,
                    "types": Counter(),
                    "numeric_count": 0,
                    "numeric_sum": 0.0,
                    "numeric_min": None,
                    "numeric_max": None,
                    "string_count": 0,
                    "string_length_sum": 0,
                    "min_len": None,
                    "max_len": None,
                }

            summary = summaries[field_path]
            summary["present_count"] += 1
            value_type = _infer_type(value)
            summary["types"][value_type] += 1
            if value is None:
                summary["null_count"] += 1

            numeric_value = _numeric_value(value)
            if numeric_value is not None:
                summary["numeric_count"] += 1
                summary["numeric_sum"] += numeric_value
                summary["numeric_min"] = (
                    numeric_value
                    if summary["numeric_min"] is None
                    else min(summary["numeric_min"], numeric_value)
                )
                summary["numeric_max"] = (
                    numeric_value
                    if summary["numeric_max"] is None
                    else max(summary["numeric_max"], numeric_value)
                )
            if isinstance(value, str):
                length = len(value)
                summary["string_count"] += 1
                summary["string_length_sum"] += length
                summary["min_len"] = (
                    length
                    if summary["min_len"] is None
                    else min(summary["min_len"], length)
                )
                summary["max_len"] = (
                    length
                    if summary["max_len"] is None
                    else max(summary["max_len"], length)
                )

    result = {}
    for field_path, summary in summaries.items():
        presence_rate = (
            summary["present_count"] / total_documents
            if total_documents
            else 0.0
        )
        result[field_path] = {
            "type_distribution": dict(summary["types"]),
            "presence_rate": presence_rate,
            "null_rate": (
                summary["null_count"] / total_documents
                if total_documents
                else 0.0
            ),
            "numeric_min": summary["numeric_min"],
            "numeric_max": summary["numeric_max"],
            "numeric_mean": (
                summary["numeric_sum"] / summary["numeric_count"]
                if summary["numeric_count"]
                else None
            ),
            "min_len": summary["min_len"],
            "max_len": summary["max_len"],
            "avg_len": (
                summary["string_length_sum"] / summary["string_count"]
                if summary["string_count"]
                else None
            ),
            "required": (
                total_documents > 0
                and summary["present_count"] == total_documents
                and summary["null_count"] == 0
            ),
        }
    return result


def _flatten_document(
    document: dict,
    prefix: str = "",
    *,
    depth: int = 0,
    max_depth: int = _MAX_NESTING_DEPTH,
):
    for key, value in document.items():
        segment = str(key).replace("\\", "\\\\").replace(".", "\\.")
        field_path = f"{prefix}.{segment}" if prefix else segment
        if isinstance(value, dict) and depth < max_depth:
            yield from _flatten_document(
                value,
                field_path,
                depth=depth + 1,
                max_depth=max_depth,
            )
        else:
            yield field_path, value


def _numeric_value(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if type(value).__name__ == "Decimal128":
        try:
            numeric = float(value.to_decimal())
            return numeric if math.isfinite(numeric) else None
        except (AttributeError, TypeError, ValueError):
            return None
    return None


def _has_leading_index(index_information: dict, field_path: str) -> bool:
    for details in index_information.values():
        if details.get("partialFilterExpression"):
            continue
        keys = details.get("key") or []
        if keys and keys[0][0] == field_path and keys[0][1] in {1, -1}:
            return True
    return False


def _nested_value(document: dict, field_path: str):
    value = document
    for part in field_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _quote_identifier(identifier: str) -> str:
    if not identifier or "\x00" in identifier:
        raise ConnectorConfigurationError("MongoDB asset identifier is invalid.")
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


def _infer_type(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, datetime):
        return "datetime"
    if isinstance(value, date):
        return "date"
    if isinstance(value, UUID):
        return "uuid"
    if isinstance(value, bytes):
        return "binary"
    if isinstance(value, list):
        if not value:
            return "array"
        item_types = sorted({_infer_type(item) for item in value[:_MAX_ARRAY_ITEMS]})
        return f"array<{ '|'.join(item_types) }>"
    if isinstance(value, dict):
        return "object"

    type_name = type(value).__name__
    if type_name == "ObjectId":
        return "ObjectId"
    if type_name in {"Decimal128", "Int64"}:
        return "number"
    if type_name in {"Binary", "Code"}:
        return "binary"
    if type_name == "Regex":
        return "regex"
    return type_name


def _format_type_distribution(type_distribution: dict[str, int]) -> str:
    types = [type_name for type_name in type_distribution if type_name != "null"]
    if not types:
        return "null"
    return "|".join(sorted(types))


def _format_percent(value: float) -> str:
    rounded = round(value, 1)
    if rounded.is_integer():
        return f"{int(rounded)}%"
    return f"{rounded}%"


def _sort_field_paths(field_stats: dict) -> list[str]:
    return sorted(field_stats, key=lambda field_path: (field_path != "_id", field_path))
