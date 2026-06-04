import json
import logging
import time

from app.connectors.base import BaseConnector, SchemaInfo, TableInfo

logger = logging.getLogger(__name__)


class BigQueryConnector(BaseConnector):
    """
    BigQuery connector via google-cloud-bigquery.
    Auth: service account JSON key from connection_config['credentials_json'].
    """

    def __init__(self, config: dict):
        self._config = config
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google.cloud import bigquery
            from google.oauth2 import service_account

            creds_json = self._config.get("credentials_json")
            if isinstance(creds_json, str):
                creds_json = json.loads(creds_json)

            credentials = service_account.Credentials.from_service_account_info(
                creds_json,
                scopes=["https://www.googleapis.com/auth/bigquery"],
            )
            project = self._config.get("project_id") or creds_json.get("project_id")
            self._client = bigquery.Client(credentials=credentials, project=project)
        return self._client

    async def test_connection(self) -> bool:
        try:
            client = self._get_client()
            # List datasets with max_results=1 — lightweight check
            list(client.list_datasets(max_results=1))
            return True
        except Exception as e:
            logger.warning("BigQuery connection test failed: %s", type(e).__name__)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        client = self._get_client()
        schemas: list[SchemaInfo] = []
        for dataset in client.list_datasets():
            tables = []
            for table_ref in client.list_tables(dataset.reference):
                tables.append(TableInfo(name=table_ref.table_id, estimated_rows=None))
            schemas.append(SchemaInfo(name=dataset.dataset_id, tables=tables))
        return schemas

    async def execute_profile_query(self, query: str) -> dict:
        client = self._get_client()
        job = client.query(query)
        rows = list(job.result())
        if not rows:
            return {}
        return dict(rows[0].items())

    async def get_table_ddl(self, schema: str, table: str) -> str:
        client = self._get_client()
        project = self._config.get("project_id")
        table_ref = f"{project}.{schema}.{table}" if project else f"{schema}.{table}"
        tbl = client.get_table(table_ref)
        lines = [f"  {f.name} {f.field_type} {'NULLABLE' if f.is_nullable else 'REQUIRED'}"
                 for f in tbl.schema]
        return f"CREATE TABLE {schema}.{table} (\n" + ",\n".join(lines) + "\n);"

    async def test_connection_with_latency(self) -> tuple[bool, int]:
        start = time.monotonic()
        ok = await self.test_connection()
        ms = int((time.monotonic() - start) * 1000)
        return ok, ms
