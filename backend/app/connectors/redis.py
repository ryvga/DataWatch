import asyncio
import hashlib
import json
import logging
from collections import Counter

from app.connectors.base import (
    BaseConnector,
    ConnectorConfigurationError,
    KeyScanBudgetExceeded,
    SchemaInfo,
    TableInfo,
)

logger = logging.getLogger(__name__)

_MIN_SCAN_KEYS = 25
_MAX_SCAN_KEYS = 10_000
_MIN_SCAN_COUNT = 10
_MAX_SCAN_COUNT = 1_000
_MAX_SCAN_ROUNDS_FACTOR = 4
_KEYSPACE_TABLE = "keyspace"


class RedisConnector(BaseConnector):
    """Bounded Redis keyspace profiler that never reads stored values."""

    native_profile_kind = "keyspace"

    def __init__(self, config: dict):
        self._config = config
        self._client = None

    def _database(self) -> int:
        try:
            database = int(self._config.get("database", 0))
        except (TypeError, ValueError) as exc:
            raise ConnectorConfigurationError("Redis database must be an integer.") from exc
        if not 0 <= database <= 15:
            raise ConnectorConfigurationError("Redis database must be between 0 and 15.")
        return database

    def _scan_limits(self) -> tuple[int, int]:
        try:
            max_keys = int(self._config.get("max_scan_keys", 1_000))
            scan_count = int(self._config.get("scan_count", 100))
        except (TypeError, ValueError) as exc:
            raise ConnectorConfigurationError("Redis scan limits must be integers.") from exc
        if not _MIN_SCAN_KEYS <= max_keys <= _MAX_SCAN_KEYS:
            raise ConnectorConfigurationError(
                f"Redis max_scan_keys must be between {_MIN_SCAN_KEYS} and {_MAX_SCAN_KEYS}."
            )
        if not _MIN_SCAN_COUNT <= scan_count <= _MAX_SCAN_COUNT:
            raise ConnectorConfigurationError(
                f"Redis scan_count must be between {_MIN_SCAN_COUNT} and {_MAX_SCAN_COUNT}."
            )
        return max_keys, scan_count

    def _key_pattern(self) -> str:
        pattern = str(self._config.get("key_pattern", "*")).strip()
        if not pattern or "\x00" in pattern or len(pattern.encode("utf-8")) > 512:
            raise ConnectorConfigurationError("Redis key_pattern is invalid.")
        return pattern

    def _get_client(self):
        if self._client is None:
            from redis.asyncio import Redis

            tls_mode = str(self._config.get("tls_mode", "verify_identity")).lower()
            if tls_mode not in {"verify_identity", "disabled"}:
                raise ConnectorConfigurationError("Redis tls_mode must be verify_identity or disabled.")
            tls_options = {"ssl": False}
            if tls_mode == "verify_identity":
                tls_options = {
                    "ssl": True,
                    "ssl_cert_reqs": "required",
                    "ssl_check_hostname": True,
                }
                if self._config.get("ssl_ca"):
                    tls_options["ssl_ca_data"] = self._config["ssl_ca"]
            self._client = Redis(
                host=self._config["host"],
                port=int(self._config.get("port", 6379)),
                db=self._database(),
                username=self._config.get("username") or None,
                password=self._config.get("password") or None,
                socket_connect_timeout=10,
                socket_timeout=30,
                max_connections=5,
                decode_responses=False,
                client_name="DataWatch",
                **tls_options,
            )
        return self._client

    def _validate_scope(self, schema: str, table: str) -> None:
        expected_schema = f"db{self._database()}"
        if schema != expected_schema or table != _KEYSPACE_TABLE:
            raise ConnectorConfigurationError("Redis operations are restricted to the configured database keyspace.")

    async def test_connection(self) -> bool:
        try:
            self._scan_limits()
            self._key_pattern()
            return bool(await self._get_client().ping())
        except Exception as exc:
            logger.warning("Redis connection test failed: %s", type(exc).__name__)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        client = self._get_client()
        estimated_rows = await client.dbsize() if self._key_pattern() == "*" else None
        return [
            SchemaInfo(
                name=f"db{self._database()}",
                tables=[TableInfo(name=_KEYSPACE_TABLE, estimated_rows=estimated_rows)],
            )
        ]

    async def execute_profile_query(self, query: str) -> dict:
        raise NotImplementedError("Redis does not execute caller-provided commands")

    async def execute_monitor_query(self, query: str, *, timeout_seconds: int = 30) -> dict:
        raise NotImplementedError("Redis does not execute caller-provided commands")

    async def get_table_ddl(self, schema: str, table: str) -> str:
        snapshot, _ = await self.get_table_schema(schema, table)
        return snapshot

    async def get_table_schema(
        self,
        schema: str,
        table: str,
    ) -> tuple[str, set[str]]:
        self._validate_scope(schema, table)
        fields = {
            "key_type",
            "memory_bytes",
            "ttl_ms",
            "hash_fields",
            "stream_entries",
            "stream_groups",
            "stream_pending",
            "stream_lag",
        }
        lines = []
        for field in sorted(fields):
            data_type = "STRING NOT NULL" if field == "key_type" else "NUMBER NULL"
            lines.append(f'  "{field}" {data_type}')
        pattern_digest = hashlib.sha256(self._key_pattern().encode("utf-8")).hexdigest()
        snapshot = (
            f'CREATE KEYSPACE VIEW "{schema}"."{table}" (\n'
            + ",\n".join(lines)
            + f"\n) WITH key_pattern_sha256='{pattern_digest}';"
        )
        return snapshot, fields

    async def validate_profile_config(
        self,
        schema: str,
        table: str,
        freshness_column: str | None,
    ) -> None:
        self._validate_scope(schema, table)
        self._scan_limits()
        self._key_pattern()
        if freshness_column is not None:
            raise ConnectorConfigurationError("Redis keyspace freshness must use typed TTL/Stream monitors.")

    async def _scan_keys(self, *, max_keys_override: int | None = None) -> tuple[list[bytes], bool, int]:
        client = self._get_client()
        configured_max_keys, scan_count = self._scan_limits()
        max_keys = max_keys_override if max_keys_override is not None else configured_max_keys
        cursor = 0
        rounds = 0
        seen: set[bytes] = set()
        max_rounds = max(16, (max_keys // scan_count + 1) * _MAX_SCAN_ROUNDS_FACTOR)
        complete = False
        while rounds < max_rounds and len(seen) < max_keys:
            cursor, keys = await client.scan(
                cursor=cursor,
                match=self._key_pattern(),
                count=scan_count,
            )
            rounds += 1
            page_truncated = False
            for index, key in enumerate(keys):
                raw = key if isinstance(key, bytes) else str(key).encode("utf-8")
                seen.add(raw)
                if len(seen) >= max_keys:
                    page_truncated = any(
                        (remaining if isinstance(remaining, bytes) else str(remaining).encode("utf-8")) not in seen
                        for remaining in keys[index + 1 :]
                    )
                    break
            if int(cursor) == 0 and not page_truncated:
                complete = True
                break
        return list(seen), complete, rounds

    async def execute_keyspace_monitor(self, plan) -> dict:
        from app.services.redis_monitor import (
            MAX_KEYS_SCANNED,
            RedisMonitorPlan,
            evaluate_redis_rows,
        )
        from app.services.schema_binding import parse_ddl_columns, redis_schema_fingerprint

        if not isinstance(plan, RedisMonitorPlan):
            raise ValueError("Redis monitor plan type is invalid")
        self._validate_scope(plan.relation.schema_name, plan.relation.table_name)
        if not 1 <= plan.max_keys_scanned <= MAX_KEYS_SCANNED or not 1 <= plan.timeout_seconds <= 120:
            raise ValueError("Redis monitor plan contract is invalid")
        current_ddl, _ = await self.get_table_schema(
            plan.relation.schema_name,
            plan.relation.table_name,
        )
        current_fingerprint = redis_schema_fingerprint(parse_ddl_columns(current_ddl), current_ddl)
        if current_fingerprint != plan.relation.schema_fingerprint:
            raise ValueError("Redis configured key pattern no longer matches the compiled plan")

        async with asyncio.timeout(plan.timeout_seconds):
            keys, complete, _ = await self._scan_keys(
                max_keys_override=plan.max_keys_scanned + 1,
            )
            if not complete or len(keys) > plan.max_keys_scanned:
                raise KeyScanBudgetExceeded("Redis monitor reached maxKeysScanned")
            metrics = await self._base_metrics(keys)
            await self._populate_monitor_structure_metrics(metrics)

        rows = []
        for metric in metrics:
            if metric["ttl_ms"] == -2:
                raise ValueError("Redis key disappeared during the bounded monitor scan")
            unavailable = metric.get("unavailable", set())
            if unavailable.intersection(plan.selected_fields):
                raise ValueError("Redis ACL denied a required monitor metadata field")
            rows.append(
                {
                    field: metric.get(field)
                    for field in (
                        "key_type",
                        "ttl_ms",
                        "memory_bytes",
                        "hash_fields",
                        "stream_entries",
                        "stream_groups",
                        "stream_pending",
                        "stream_lag",
                    )
                }
            )
        return evaluate_redis_rows(plan, rows)

    async def _populate_monitor_structure_metrics(self, metrics: list[dict]) -> None:
        client = self._get_client()
        operations: list[tuple[int, str]] = []
        pipeline = client.pipeline(transaction=False)
        for index, metric in enumerate(metrics):
            metric["key_type"] = metric["type"]
            metric["unavailable"] = set()
            if not metric["type_available"]:
                metric["unavailable"].add("key_type")
            if not metric["ttl_available"]:
                metric["unavailable"].add("ttl_ms")
            if not metric["memory_available"]:
                metric["unavailable"].add("memory_bytes")
            for field in (
                "hash_fields",
                "stream_entries",
                "stream_groups",
                "stream_pending",
                "stream_lag",
            ):
                metric[field] = None
            if metric["type"] == "hash":
                pipeline.hlen(metric["key"])
                operations.append((index, "hash_fields"))
            elif metric["type"] == "stream":
                pipeline.xlen(metric["key"])
                operations.append((index, "stream_entries"))
                pipeline.xinfo_groups(metric["key"])
                operations.append((index, "stream_groups"))
        raw = await pipeline.execute(raise_on_error=False) if operations else []
        for (index, operation), value in zip(operations, raw):
            metric = metrics[index]
            if operation == "hash_fields":
                parsed = _optional_int(value)
                if parsed is None:
                    metric["unavailable"].add(operation)
                else:
                    metric[operation] = parsed
                continue
            if operation == "stream_entries":
                parsed = _optional_int(value)
                if parsed is None:
                    metric["unavailable"].add(operation)
                else:
                    metric[operation] = parsed
                continue
            if not isinstance(value, list):
                metric["unavailable"].update({"stream_groups", "stream_pending", "stream_lag"})
                continue
            metric["stream_groups"] = len(value)
            pending_total = 0
            lag_total = 0
            for group in value:
                pending = _optional_int(_mapping_value(group, "pending")) if isinstance(group, dict) else None
                lag = _optional_int(_mapping_value(group, "lag")) if isinstance(group, dict) else None
                if pending is None:
                    metric["unavailable"].add("stream_pending")
                else:
                    pending_total += pending
                if lag is None:
                    metric["unavailable"].add("stream_lag")
                else:
                    lag_total += lag
            metric["stream_pending"] = pending_total
            metric["stream_lag"] = lag_total

    async def _base_metrics(self, keys: list[bytes]) -> list[dict]:
        client = self._get_client()
        pipeline = client.pipeline(transaction=False)
        for key in keys:
            pipeline.type(key)
            pipeline.pttl(key)
            pipeline.memory_usage(key)
        raw = await pipeline.execute(raise_on_error=False)
        metrics = []
        for index, key in enumerate(keys):
            values = raw[index * 3 : index * 3 + 3]
            key_type = _redis_type(values[0])
            ttl_ms = _optional_int(values[1])
            memory_bytes = _optional_int(values[2])
            metrics.append(
                {
                    "key": key,
                    "type": key_type,
                    "ttl_ms": ttl_ms,
                    "memory_bytes": memory_bytes,
                    "type_available": not isinstance(values[0], Exception),
                    "ttl_available": not isinstance(values[1], Exception),
                    "memory_available": not isinstance(values[2], Exception),
                }
            )
        return metrics

    async def _structure_metrics(self, metrics: list[dict]) -> tuple[dict[str, int], set[str]]:
        client = self._get_client()
        operations: list[str] = []
        pipeline = client.pipeline(transaction=False)
        for metric in metrics:
            if metric["type"] == "hash":
                pipeline.hlen(metric["key"])
                operations.append("hash")
            elif metric["type"] == "stream":
                pipeline.xlen(metric["key"])
                operations.append("stream_length")
                pipeline.xinfo_groups(metric["key"])
                operations.append("stream_groups")
        raw = await pipeline.execute(raise_on_error=False) if operations else []
        totals = {
            "hash_fields": 0,
            "stream_entries": 0,
            "stream_groups": 0,
            "stream_pending": 0,
            "stream_lag": 0,
        }
        unavailable: set[str] = set()
        for operation, value in zip(operations, raw):
            if operation == "hash":
                parsed = _optional_int(value)
                if parsed is None:
                    unavailable.add("hash_fields")
                else:
                    totals["hash_fields"] += parsed
            elif operation == "stream_length":
                parsed = _optional_int(value)
                if parsed is None:
                    unavailable.add("stream_entries")
                else:
                    totals["stream_entries"] += parsed
            elif operation == "stream_groups":
                if not isinstance(value, list):
                    unavailable.update({"stream_groups", "stream_pending", "stream_lag"})
                    continue
                totals["stream_groups"] += len(value)
                for group in value:
                    if not isinstance(group, dict):
                        unavailable.update({"stream_pending", "stream_lag"})
                        continue
                    pending = _optional_int(_mapping_value(group, "pending"))
                    lag = _optional_int(_mapping_value(group, "lag"))
                    if pending is None:
                        unavailable.add("stream_pending")
                    else:
                        totals["stream_pending"] += pending
                    if lag is None:
                        unavailable.add("stream_lag")
                    else:
                        totals["stream_lag"] += lag
        return totals, unavailable

    async def collect_native_profile(
        self,
        schema: str,
        table: str,
        freshness_column: str | None,
    ) -> dict:
        await self.validate_profile_config(schema, table, freshness_column)
        keys, scan_complete, scan_rounds = await self._scan_keys()
        base_metrics = await self._base_metrics(keys)
        structures, unavailable = await self._structure_metrics(base_metrics)
        if any(not metric["type_available"] for metric in base_metrics):
            unavailable.add("key_type")
        if any(not metric["ttl_available"] for metric in base_metrics):
            unavailable.add("ttl")
        if any(not metric["memory_available"] for metric in base_metrics):
            unavailable.add("memory")
        type_distribution = Counter(metric["type"] for metric in base_metrics)
        memory_values = [metric["memory_bytes"] for metric in base_metrics if metric["memory_bytes"] is not None]
        ttl_expiring = sum(1 for metric in base_metrics if metric["ttl_ms"] is not None and metric["ttl_ms"] >= 0)
        persistent = sum(1 for metric in base_metrics if metric["ttl_ms"] == -1)
        missing = sum(1 for metric in base_metrics if metric["ttl_ms"] == -2)
        contract = {
            "kind": "redis_keyspace_v2",
            "fields": sorted((await self.get_table_schema(schema, table))[1]),
            "key_pattern_sha256": hashlib.sha256(self._key_pattern().encode("utf-8")).hexdigest(),
        }
        fingerprint = hashlib.sha256(json.dumps(contract, sort_keys=True).encode("utf-8")).hexdigest()
        observed = len(base_metrics)
        return {
            "row_count": observed,
            "freshness_seconds": None,
            "schema_fingerprint": fingerprint,
            "column_metrics": {
                "_keyspace": {
                    "keys_observed": observed,
                    "scan_complete": scan_complete,
                    "type_distribution": dict(sorted(type_distribution.items())),
                    "ttl_expiring_keys": ttl_expiring,
                    "persistent_keys": persistent,
                    "missing_during_scan": missing,
                    "memory_bytes": sum(memory_values) if memory_values else None,
                    "memory_avg_bytes": (sum(memory_values) / len(memory_values) if memory_values else None),
                    "memory_max_bytes": max(memory_values) if memory_values else None,
                    "unavailable_metrics": sorted(unavailable),
                    **structures,
                }
            },
            "profile_provenance": {
                "profile_mode": "sampled_native",
                "connector": "redis",
                "count_mode": "exact" if scan_complete else "lower_bound",
                "scan_strategy": "bounded_cursor",
                "scan_complete": scan_complete,
                "scan_rounds": scan_rounds,
                "key_pattern_sha256": hashlib.sha256(self._key_pattern().encode("utf-8")).hexdigest(),
                "keys_observed": observed,
                "max_scan_keys": self._scan_limits()[0],
                "values_collected": False,
            },
        }

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def _redis_type(value) -> str:
    if isinstance(value, bytes):
        return value.decode("ascii", errors="replace")
    if isinstance(value, str):
        return value
    return "unknown"


def _optional_int(value) -> int | None:
    if isinstance(value, bool) or isinstance(value, Exception) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _mapping_value(mapping: dict, name: str):
    return mapping.get(name, mapping.get(name.encode("ascii")))
