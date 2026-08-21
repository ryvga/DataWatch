import asyncio
import json
import logging
import time
from concurrent.futures import TimeoutError as FuturesTimeoutError

from google.api_core.exceptions import DeadlineExceeded

from app.connectors.base import (
    BaseConnector,
    ConnectorConfigurationError,
    ScanBudgetExceeded,
    SchemaInfo,
    TableInfo,
)

logger = logging.getLogger(__name__)

_MIN_BYTES_BILLED = 1
_MAX_BYTES_BILLED = 10 * 1024**4


class BigQueryConnector(BaseConnector):
    """Cost-bounded BigQuery adapter with every blocking SDK call off the event loop."""

    profile_dialect = "bigquery"

    def __init__(self, config: dict):
        self._config = config
        self._client = None

    def _maximum_bytes_billed(self) -> int:
        try:
            value = int(self._config.get("maximum_bytes_billed", 1024**3))
        except (TypeError, ValueError) as exc:
            raise ConnectorConfigurationError("BigQuery maximum_bytes_billed must be an integer") from exc
        if not _MIN_BYTES_BILLED <= value <= _MAX_BYTES_BILLED:
            raise ConnectorConfigurationError(
                f"BigQuery maximum_bytes_billed must be between {_MIN_BYTES_BILLED} and {_MAX_BYTES_BILLED}"
            )
        return value

    def _query_timeout_seconds(self) -> int:
        try:
            value = int(self._config.get("query_timeout_seconds", 120))
        except (TypeError, ValueError) as exc:
            raise ConnectorConfigurationError("BigQuery query_timeout_seconds must be an integer") from exc
        if not 1 <= value <= 600:
            raise ConnectorConfigurationError("BigQuery query_timeout_seconds must be between 1 and 600")
        return value

    def _get_client(self):
        if self._client is None:
            from google.cloud import bigquery

            creds_json = self._config.get("credentials_json")
            project = self._config.get("project_id")
            if creds_json:
                from google.oauth2 import service_account

                if isinstance(creds_json, str):
                    try:
                        creds_json = json.loads(creds_json)
                    except json.JSONDecodeError as exc:
                        raise ConnectorConfigurationError("BigQuery credentials_json is invalid JSON") from exc
                if not isinstance(creds_json, dict):
                    raise ConnectorConfigurationError("BigQuery credentials_json must be a JSON object")
                credentials = service_account.Credentials.from_service_account_info(
                    creds_json,
                    scopes=["https://www.googleapis.com/auth/bigquery"],
                )
                project = project or creds_json.get("project_id")
                self._client = bigquery.Client(credentials=credentials, project=project)
            else:
                self._client = bigquery.Client(project=project)
        return self._client

    async def test_connection(self) -> bool:
        try:
            self._maximum_bytes_billed()
            self._query_timeout_seconds()

            def _probe() -> bool:
                client = self._get_client()
                dataset_scope = self._config.get("dataset")
                if dataset_scope:
                    client.get_dataset(f"{client.project}.{dataset_scope}")
                else:
                    list(client.list_datasets(max_results=1))
                return True

            return await asyncio.to_thread(_probe)
        except Exception as exc:
            logger.warning("BigQuery connection test failed: %s", type(exc).__name__)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        dataset_scope = self._config.get("dataset")

        def _discover() -> list[SchemaInfo]:
            client = self._get_client()
            if dataset_scope:
                datasets = [client.get_dataset(f"{client.project}.{dataset_scope}")]
            else:
                datasets = list(client.list_datasets())
            schemas: list[SchemaInfo] = []
            for dataset in datasets:
                tables = [
                    TableInfo(name=table_ref.table_id, estimated_rows=None)
                    for table_ref in client.list_tables(dataset.reference)
                ]
                schemas.append(SchemaInfo(name=dataset.dataset_id, tables=tables))
            return schemas

        return await asyncio.to_thread(_discover)

    def _execute_profile_sync(self, query: str) -> dict:
        from google.cloud import bigquery

        client = self._get_client()
        maximum_bytes = self._maximum_bytes_billed()
        dry_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        dry_job = client.query(query, job_config=dry_config)
        estimated_bytes = int(getattr(dry_job, "total_bytes_processed", 0) or 0)
        if estimated_bytes > maximum_bytes:
            raise ScanBudgetExceeded(
                f"BigQuery dry run estimates {estimated_bytes} bytes, above the configured maximum"
            )

        job_config = bigquery.QueryJobConfig(
            maximum_bytes_billed=maximum_bytes,
            use_query_cache=True,
        )
        job = client.query(query, job_config=job_config)
        try:
            rows = list(job.result(timeout=self._query_timeout_seconds()))
        except (TimeoutError, FuturesTimeoutError, DeadlineExceeded) as exc:
            try:
                job.cancel()
            finally:
                raise TimeoutError("BigQuery profile query exceeded its timeout") from exc
        if not rows:
            return {}
        return dict(rows[0].items())

    async def execute_profile_query(self, query: str) -> dict:
        return await asyncio.to_thread(self._execute_profile_sync, query)

    async def get_table_ddl(self, schema: str, table: str) -> str:
        if not schema or not table or "\x00" in schema or "\x00" in table:
            raise ValueError("BigQuery dataset or table identifier is invalid")
        dataset_scope = self._config.get("dataset")
        if dataset_scope and schema != dataset_scope:
            raise ValueError("BigQuery schema access is restricted to the configured dataset")

        def _ddl() -> str:
            client = self._get_client()
            project = self._config.get("project_id") or client.project
            remote_table = client.get_table(f"{project}.{schema}.{table}")
            lines = [
                f"  {_quote_identifier(field.name)} {field.field_type} "
                f"{'NULL' if field.is_nullable else 'NOT NULL'}"
                for field in remote_table.schema
            ]
            return (
                f"CREATE TABLE {_quote_identifier(schema)}.{_quote_identifier(table)} (\n"
                + ",\n".join(lines)
                + "\n);"
            )

        return await asyncio.to_thread(_ddl)

    async def close(self) -> None:
        client = self._client
        self._client = None
        if client is not None and callable(getattr(client, "close", None)):
            await asyncio.to_thread(client.close)

    async def test_connection_with_latency(self) -> tuple[bool, int]:
        start = time.monotonic()
        ok = await self.test_connection()
        return ok, int((time.monotonic() - start) * 1000)


def _quote_identifier(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"
