import inspect
import logging
from contextlib import suppress
from pathlib import Path
from typing import Any

from sqlglot import exp, parse_one

from app.connectors.base import BaseConnector, ConnectorConfigurationError, SchemaInfo, TableInfo
from app.config import settings


logger = logging.getLogger(__name__)

_DATE_TYPES = {
    "DATE",
    "TIMESTAMP",
    "TIMESTAMP WITH TIME ZONE",
    "TIMESTAMP WITH LOCAL TIME ZONE",
}


class OracleConnector(BaseConnector):
    """Oracle Database connector using python-oracledb thin async mode."""

    profile_dialect = "oracle"

    def __init__(self, config: dict):
        self._config = config
        self._conn: Any | None = None
        self._column_cache: dict[tuple[str, str], list[Any]] = {}
        username = str(config.get("username") or "").strip()
        self._owner = str(config.get("schema") or username.upper()).strip()
        if not self._owner:
            raise ConnectorConfigurationError("Oracle schema scope could not be determined.")

    @staticmethod
    def _bounded_int(config: dict, name: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(config.get(name, default))
        except (TypeError, ValueError) as exc:
            raise ConnectorConfigurationError(f"Oracle {name} must be an integer.") from exc
        if not minimum <= value <= maximum:
            raise ConnectorConfigurationError(
                f"Oracle {name} must be between {minimum} and {maximum}."
            )
        return value

    async def _get_conn(self):
        if self._conn is not None:
            return self._conn

        import oracledb

        if not oracledb.is_thin_mode():
            raise ConnectorConfigurationError("Oracle connector requires python-oracledb thin mode.")

        tls_mode = str(self._config.get("tls_mode", "verify_identity")).lower()
        if tls_mode not in {"verify_identity", "disabled"}:
            raise ConnectorConfigurationError(
                "Oracle tls_mode must be 'verify_identity' or 'disabled'."
            )
        connect_timeout = self._bounded_int(
            self._config, "connect_timeout_seconds", 15, 1, 120
        )
        call_timeout = self._bounded_int(
            self._config, "call_timeout_ms", 120_000, 1_000, 900_000
        )
        kwargs: dict[str, Any] = {
            "host": self._config["host"],
            "port": int(self._config.get("port", 1521)),
            "service_name": self._config["service_name"],
            "protocol": "tcps" if tls_mode == "verify_identity" else "tcp",
            "ssl_server_dn_match": tls_mode == "verify_identity",
            "tcp_connect_timeout": connect_timeout,
        }
        wallet_location = self._config.get("wallet_location")
        if wallet_location:
            wallet_path = Path(str(wallet_location)).expanduser().resolve(strict=False)
            if settings.is_production:
                if not settings.ORACLE_WALLET_ROOT:
                    raise ConnectorConfigurationError(
                        "Oracle wallets are disabled until ORACLE_WALLET_ROOT is configured."
                    )
                wallet_root = Path(settings.ORACLE_WALLET_ROOT).expanduser().resolve(strict=False)
                if wallet_path != wallet_root and wallet_root not in wallet_path.parents:
                    raise ConnectorConfigurationError(
                        "Oracle wallet_location is outside the approved wallet root."
                    )
            kwargs["wallet_location"] = str(wallet_path)
            if self._config.get("wallet_password"):
                kwargs["wallet_password"] = self._config["wallet_password"]

        params = oracledb.ConnectParams(**kwargs)
        self._conn = await oracledb.connect_async(
            user=self._config["username"],
            password=self._config.get("password", ""),
            params=params,
        )
        self._conn.call_timeout = call_timeout
        return self._conn

    @staticmethod
    def _row_to_dict(cursor, row) -> dict:
        if row is None:
            return {}
        names = [item.name if hasattr(item, "name") else item[0] for item in cursor.description]
        return dict(zip(names, row))

    @staticmethod
    async def _maybe_await(value):
        if inspect.isawaitable(value):
            return await value
        return value

    async def test_connection(self) -> bool:
        try:
            conn = await self._get_conn()
            with conn.cursor() as cursor:
                await cursor.execute("SELECT 1 FROM DUAL")
                await cursor.fetchone()
            return True
        except Exception as exc:
            logger.warning("Oracle connection test failed: %s", type(exc).__name__)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        conn = await self._get_conn()
        with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT TABLE_NAME, NUM_ROWS
                FROM ALL_TABLES
                WHERE OWNER = :owner
                ORDER BY TABLE_NAME
                """,
                owner=self._owner,
            )
            rows = await cursor.fetchall()
        return [
            SchemaInfo(
                name=self._owner,
                tables=[
                    TableInfo(
                        name=str(row[0]),
                        estimated_rows=int(row[1]) if row[1] is not None else None,
                    )
                    for row in rows
                ],
            )
        ]

    def _validate_scope(self, schema: str) -> None:
        if schema != self._owner:
            raise ConnectorConfigurationError(
                "Oracle schema must match the connector's configured schema scope."
            )

    async def _get_columns(self, schema: str, table: str) -> list[Any]:
        self._validate_scope(schema)
        cache_key = (schema, table)
        if cache_key in self._column_cache:
            return self._column_cache[cache_key]
        conn = await self._get_conn()
        with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, CHAR_LENGTH,
                       DATA_PRECISION, DATA_SCALE, NULLABLE
                FROM ALL_TAB_COLUMNS
                WHERE OWNER = :owner AND TABLE_NAME = :table_name
                ORDER BY COLUMN_ID
                """,
                owner=self._owner,
                table_name=table,
            )
            rows = list(await cursor.fetchall())
        if not rows:
            raise ConnectorConfigurationError("Oracle table schema could not be verified.")
        self._column_cache[cache_key] = rows
        return rows

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        if not identifier or "\x00" in identifier:
            raise ConnectorConfigurationError("Oracle identifiers must be non-empty.")
        return f'"{identifier.replace(chr(34), chr(34) * 2)}"'

    @staticmethod
    def _format_data_type(row) -> str:
        data_type = str(row[1])
        data_length, char_length, precision, scale = row[2:6]
        if data_type in {"CHAR", "VARCHAR2", "NCHAR", "NVARCHAR2"}:
            return f"{data_type}({char_length if char_length is not None else data_length})"
        if data_type == "NUMBER" and precision is not None:
            return f"NUMBER({precision},{scale or 0})"
        if data_type.startswith("TIMESTAMP") and scale is not None:
            suffix = data_type[len("TIMESTAMP") :]
            return f"TIMESTAMP({scale}){suffix}"
        if data_type == "RAW" and data_length is not None:
            return f"RAW({data_length})"
        return data_type

    async def get_table_ddl(self, schema: str, table: str) -> str:
        rows = await self._get_columns(schema, table)
        lines = []
        for row in rows:
            nullable = "NULL" if row[6] == "Y" else "NOT NULL"
            lines.append(
                f"  {self._quote_identifier(str(row[0]))} "
                f"{self._format_data_type(row)} {nullable}"
            )
        return (
            f"CREATE TABLE {self._quote_identifier(schema)}.{self._quote_identifier(table)} (\n"
            + ",\n".join(lines)
            + "\n);"
        )

    async def get_table_schema(
        self, schema: str, table: str
    ) -> tuple[str, set[str] | None]:
        rows = await self._get_columns(schema, table)
        return await self.get_table_ddl(schema, table), {str(row[0]) for row in rows}

    async def validate_profile_config(
        self,
        schema: str,
        table: str,
        freshness_column: str | None,
    ) -> None:
        if freshness_column is None:
            return
        rows = await self._get_columns(schema, table)
        column = next((row for row in rows if row[0] == freshness_column), None)
        if column is None:
            raise ConnectorConfigurationError(
                "Oracle freshness_column must exist in the verified table schema."
            )
        if str(column[1]).upper() not in _DATE_TYPES:
            raise ConnectorConfigurationError(
                "Oracle freshness_column must use a DATE or TIMESTAMP type."
            )

    @staticmethod
    def _validate_profile_statement(query: str) -> None:
        try:
            parsed = parse_one(query, dialect="oracle")
        except Exception as exc:
            raise ConnectorConfigurationError("Oracle profile query is invalid.") from exc
        if not isinstance(parsed, exp.Select):
            raise ConnectorConfigurationError("Oracle profiling accepts one SELECT statement only.")

    async def execute_profile_query(self, query: str) -> dict:
        self._validate_profile_statement(query)
        conn = await self._get_conn()
        # SET TRANSACTION must be the first statement in a transaction.
        await self._maybe_await(conn.rollback())
        try:
            with conn.cursor() as cursor:
                await cursor.execute("SET TRANSACTION READ ONLY")
                await cursor.execute(query)
                row = await cursor.fetchone()
                result = self._row_to_dict(cursor, row)
        except Exception:
            cancel = getattr(conn, "cancel", None)
            if callable(cancel):
                with suppress(Exception):
                    await self._maybe_await(cancel())
            with suppress(Exception):
                await self._maybe_await(conn.rollback())
            await self.close()
            raise
        else:
            await self._maybe_await(conn.rollback())
            return result

    async def close(self) -> None:
        if self._conn is not None:
            try:
                await self._maybe_await(self._conn.close())
            finally:
                self._conn = None
        self._column_cache.clear()
