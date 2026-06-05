import logging
from typing import Any

from app.connectors.base import BaseConnector, SchemaInfo, TableInfo

logger = logging.getLogger(__name__)

_DEFAULT_DRIVER = "ODBC Driver 18 for SQL Server"
_SKIP_SCHEMAS = {
    "sys",
    "INFORMATION_SCHEMA",
    "db_accessadmin",
    "db_backupoperator",
    "db_datareader",
    "db_datawriter",
    "db_ddladmin",
    "db_denydatareader",
    "db_denydatawriter",
    "db_owner",
    "db_securityadmin",
    "guest",
}


class SQLServerConnector(BaseConnector):
    """Async Microsoft SQL Server connector via aioodbc."""

    def __init__(self, config: dict):
        self._config = config
        self._conn: Any | None = None

    def _connection_string(self) -> str:
        c = self._config
        driver = c.get("driver", _DEFAULT_DRIVER)
        host = c["host"]
        port = int(c.get("port", 1433))
        database = c["database"]
        username = c.get("username") or c.get("user", "")
        password = c.get("password", "")
        return (
            f"DRIVER={{{driver}}};"
            f"SERVER={host},{port};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            "TrustServerCertificate=yes"
        )

    async def _get_conn(self):
        if self._conn is None or getattr(self._conn, "closed", False):
            import aioodbc

            self._conn = await aioodbc.connect(
                dsn=self._connection_string(),
                autocommit=True,
            )
        return self._conn

    @staticmethod
    def _row_to_dict(cursor, row) -> dict:
        if row is None:
            return {}
        columns = [col[0] for col in cursor.description]
        return dict(zip(columns, row))

    async def test_connection(self) -> bool:
        try:
            conn = await self._get_conn()
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                await cur.fetchone()
            return True
        except Exception as e:
            logger.warning("SQL Server connection test failed: %s", type(e).__name__)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        conn = await self._get_conn()
        placeholders = ",".join("?" for _ in _SKIP_SCHEMAS)
        query = f"""
            SELECT
                t.TABLE_SCHEMA AS table_schema,
                t.TABLE_NAME AS table_name,
                row_counts.estimated_rows
            FROM INFORMATION_SCHEMA.TABLES AS t
            LEFT JOIN (
                SELECT
                    s.name AS table_schema,
                    o.name AS table_name,
                    SUM(p.rows) AS estimated_rows
                FROM sys.objects AS o
                INNER JOIN sys.schemas AS s ON s.schema_id = o.schema_id
                INNER JOIN sys.partitions AS p ON p.object_id = o.object_id
                WHERE o.type = 'U'
                  AND p.index_id IN (0, 1)
                GROUP BY s.name, o.name
            ) AS row_counts
              ON row_counts.table_schema = t.TABLE_SCHEMA
             AND row_counts.table_name = t.TABLE_NAME
            WHERE t.TABLE_TYPE = 'BASE TABLE'
              AND t.TABLE_SCHEMA NOT IN ({placeholders})
            ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME
        """
        async with conn.cursor() as cur:
            await cur.execute(query, tuple(_SKIP_SCHEMAS))
            rows = await cur.fetchall()

        schemas: dict[str, SchemaInfo] = {}
        for row in rows:
            schema_name = row[0]
            if schema_name not in schemas:
                schemas[schema_name] = SchemaInfo(name=schema_name)
            estimated_rows = int(row[2]) if row[2] is not None else None
            schemas[schema_name].tables.append(
                TableInfo(name=row[1], estimated_rows=estimated_rows)
            )
        return list(schemas.values())

    async def execute_profile_query(self, query: str) -> dict:
        conn = await self._get_conn()
        async with conn.cursor() as cur:
            await cur.execute(query)
            row = await cur.fetchone()
            return self._row_to_dict(cur, row)

    @staticmethod
    def _format_data_type(row) -> str:
        data_type = row[1]
        char_length = row[2]
        numeric_precision = row[3]
        numeric_scale = row[4]
        datetime_precision = row[5]

        if data_type in {"char", "varchar", "nchar", "nvarchar", "binary", "varbinary"}:
            length = "max" if char_length == -1 else char_length
            return f"{data_type}({length})"
        if data_type in {"decimal", "numeric"} and numeric_precision is not None:
            scale = numeric_scale if numeric_scale is not None else 0
            return f"{data_type}({numeric_precision},{scale})"
        if data_type in {
            "datetime2",
            "datetimeoffset",
            "time",
        } and datetime_precision is not None:
            return f"{data_type}({datetime_precision})"
        return data_type

    async def get_table_ddl(self, schema: str, table: str) -> str:
        conn = await self._get_conn()
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    COLUMN_NAME,
                    DATA_TYPE,
                    CHARACTER_MAXIMUM_LENGTH,
                    NUMERIC_PRECISION,
                    NUMERIC_SCALE,
                    DATETIME_PRECISION,
                    IS_NULLABLE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
                ORDER BY ORDINAL_POSITION
                """,
                (schema, table),
            )
            rows = await cur.fetchall()

        lines = []
        for row in rows:
            nullable = "NULL" if row[6] == "YES" else "NOT NULL"
            lines.append(f"  [{row[0]}] {self._format_data_type(row)} {nullable}")
        return f"CREATE TABLE [{schema}].[{table}] (\n" + ",\n".join(lines) + "\n);"

    async def close(self) -> None:
        if self._conn is not None and not getattr(self._conn, "closed", False):
            await self._conn.close()
        self._conn = None
