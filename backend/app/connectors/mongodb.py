import ast
import json
import logging
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.connectors.base import BaseConnector, SchemaInfo, TableInfo

logger = logging.getLogger(__name__)

_SYSTEM_DATABASES = {"admin", "local", "config"}


class MongoDBConnector(BaseConnector):
    """Async MongoDB connector via motor."""

    def __init__(self, config: dict):
        self._config = config
        self._client = None

    def _get_client(self):
        if self._client is None:
            from motor.motor_asyncio import AsyncIOMotorClient

            self._client = AsyncIOMotorClient(self._config["uri"])
        return self._client

    async def test_connection(self) -> bool:
        try:
            client = self._get_client()
            await client.admin.command("ping")
            return True
        except Exception as e:
            logger.warning("MongoDB connection test failed: %s", type(e).__name__)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        client = self._get_client()
        configured_database = self._config.get("database")
        database_names = (
            [configured_database]
            if configured_database
            else await client.list_database_names()
        )

        schemas: list[SchemaInfo] = []
        for database_name in database_names:
            if database_name in _SYSTEM_DATABASES:
                continue

            database = client[database_name]
            collection_names = await database.list_collection_names()
            tables: list[TableInfo] = []
            for collection_name in sorted(collection_names):
                collection = database[collection_name]
                estimated_rows = await collection.estimated_document_count()
                tables.append(
                    TableInfo(name=collection_name, estimated_rows=estimated_rows)
                )
            schemas.append(SchemaInfo(name=database_name, tables=tables))

        return schemas

    async def execute_profile_query(self, query: str) -> dict:
        command = _parse_profile_command(query)
        database_name = command.get("database") or self._config.get("database")
        collection_name = command.get("collection")
        pipeline = command.get("pipeline")

        if not database_name or not collection_name or not isinstance(pipeline, list):
            return {}

        try:
            collection = self._get_client()[database_name][collection_name]
            rows = await collection.aggregate(pipeline).to_list(length=1)
            return dict(rows[0]) if rows else {}
        except Exception as e:
            logger.warning("MongoDB profile query failed: %s", type(e).__name__)
            return {}

    async def get_table_ddl(self, schema: str, table: str) -> str:
        collection = self._get_client()[schema][table]
        documents = await collection.aggregate([{"$sample": {"size": 100}}]).to_list(
            length=100
        )
        field_stats = _summarize_fields(documents, sample_value_limit=0)

        lines = []
        for field_path in _sort_field_paths(field_stats):
            stats = field_stats[field_path]
            inferred_type = _format_type_distribution(stats["type_distribution"])
            nullable = "NOT NULL" if stats["required"] else "NULL"
            presence = _format_percent(stats["presence_rate"])
            lines.append(
                f"  {field_path} {inferred_type} {nullable} {presence}"
            )

        return f"CREATE COLLECTION {schema}.{table} (\n" + ",\n".join(lines) + "\n);"

    async def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    async def get_collection_stats(self, database: str, collection: str) -> dict:
        db = self._get_client()[database]
        coll = db[collection]

        document_count = await coll.estimated_document_count()
        avg_document_size_bytes = None
        try:
            raw_stats = await db.command("collStats", collection)
            avg_document_size_bytes = raw_stats.get("avgObjSize")
        except Exception as e:
            logger.warning("MongoDB collection stats failed: %s", type(e).__name__)

        documents = await coll.aggregate([{"$sample": {"size": 1000}}]).to_list(
            length=1000
        )
        field_stats = _summarize_fields(documents, sample_value_limit=5)

        return {
            "document_count": document_count,
            "avg_document_size_bytes": avg_document_size_bytes,
            "field_stats": {
                field_path: {
                    "type_distribution": stats["type_distribution"],
                    "presence_rate": stats["presence_rate"],
                    "sample_values": stats["sample_values"],
                }
                for field_path, stats in field_stats.items()
            },
        }


def _parse_profile_command(query: str) -> dict:
    try:
        parsed = json.loads(query)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(query)
        except (SyntaxError, ValueError):
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _summarize_fields(documents: list[dict], sample_value_limit: int) -> dict:
    total_documents = len(documents)
    summaries: dict[str, dict] = {}

    for document in documents:
        flattened = dict(_flatten_document(document))
        for field_path, value in flattened.items():
            if field_path not in summaries:
                summaries[field_path] = {
                    "present_count": 0,
                    "null_count": 0,
                    "types": Counter(),
                    "sample_values": [],
                }

            summary = summaries[field_path]
            summary["present_count"] += 1
            value_type = _infer_type(value)
            summary["types"][value_type] += 1
            if value is None:
                summary["null_count"] += 1
            elif (
                sample_value_limit
                and len(summary["sample_values"]) < sample_value_limit
                and value not in summary["sample_values"]
            ):
                summary["sample_values"].append(_sample_value(value))

    result = {}
    for field_path, summary in summaries.items():
        presence_rate = (
            (summary["present_count"] / total_documents) * 100
            if total_documents
            else 0.0
        )
        result[field_path] = {
            "type_distribution": dict(summary["types"]),
            "presence_rate": presence_rate,
            "sample_values": summary["sample_values"],
            "required": (
                total_documents > 0
                and summary["present_count"] == total_documents
                and summary["null_count"] == 0
            ),
        }
    return result


def _flatten_document(document: dict, prefix: str = ""):
    for key, value in document.items():
        field_path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            yield from _flatten_document(value, field_path)
        else:
            yield field_path, value


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
        item_types = sorted({_infer_type(item) for item in value})
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


def _sample_value(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, list):
        return [_sample_value(item) for item in value[:5]]
    if isinstance(value, dict):
        return {key: _sample_value(item) for key, item in list(value.items())[:5]}
    return str(value)


def _sort_field_paths(field_stats: dict) -> list[str]:
    return sorted(field_stats, key=lambda field_path: (field_path != "_id", field_path))
