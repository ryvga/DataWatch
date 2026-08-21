from concurrent.futures import TimeoutError as FuturesTimeoutError
from types import SimpleNamespace

import pytest
from google.cloud import bigquery

from app.connectors.base import ConnectorConfigurationError, ScanBudgetExceeded
from app.connectors.bigquery import BigQueryConnector
from app.services.profiler import ColumnInfo, ProfilerService


class _QueryConfig:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _Row:
    def __init__(self, payload):
        self._payload = payload

    def items(self):
        return self._payload.items()


class _Job:
    def __init__(self, *, estimated_bytes=0, rows=None, error=None):
        self.total_bytes_processed = estimated_bytes
        self._rows = rows or []
        self._error = error
        self.cancelled = False
        self.timeout = None

    def result(self, *, timeout):
        self.timeout = timeout
        if self._error:
            raise self._error
        return self._rows

    def cancel(self):
        self.cancelled = True


class _Client:
    project = "bounded-project"

    def __init__(self, jobs=None):
        self.jobs = list(jobs or [])
        self.queries = []
        self.dataset_requests = []
        self.list_dataset_calls = 0
        self.closed = False

    def query(self, query, *, job_config):
        self.queries.append((query, job_config))
        return self.jobs.pop(0)

    def get_dataset(self, name):
        self.dataset_requests.append(name)
        return SimpleNamespace(dataset_id=name.rsplit(".", 1)[-1], reference=name)

    def list_datasets(self, **_kwargs):
        self.list_dataset_calls += 1
        return [SimpleNamespace(dataset_id="other", reference="other")]

    def list_tables(self, dataset):
        assert dataset == "bounded-project.analytics"
        return [SimpleNamespace(table_id="events")]

    def get_table(self, name):
        assert name == "bounded-project.analytics.events"
        return SimpleNamespace(
            schema=[
                SimpleNamespace(name="event`id", field_type="INT64", is_nullable=False),
                SimpleNamespace(name="status", field_type="STRING", is_nullable=True),
            ]
        )

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _fake_query_config(monkeypatch):
    monkeypatch.setattr(bigquery, "QueryJobConfig", _QueryConfig)


@pytest.mark.asyncio
async def test_bigquery_profile_dry_runs_then_executes_with_hard_cost_cap(monkeypatch):
    dry_job = _Job(estimated_bytes=900)
    query_job = _Job(rows=[_Row({"_row_count": 3})])
    client = _Client([dry_job, query_job])
    connector = BigQueryConnector(
        {
            "project_id": "bounded-project",
            "maximum_bytes_billed": 1000,
            "query_timeout_seconds": 17,
        }
    )
    connector._client = client
    offloaded = []

    async def _to_thread(function, *args):
        offloaded.append(function)
        return function(*args)

    monkeypatch.setattr("app.connectors.bigquery.asyncio.to_thread", _to_thread)

    assert await connector.execute_profile_query("SELECT COUNT(*) AS _row_count") == {
        "_row_count": 3
    }
    assert offloaded == [connector._execute_profile_sync]
    assert len(client.queries) == 2
    assert client.queries[0][1].dry_run is True
    assert client.queries[0][1].use_query_cache is False
    assert client.queries[1][1].maximum_bytes_billed == 1000
    assert query_job.timeout == 17


@pytest.mark.asyncio
async def test_bigquery_rejects_dry_run_over_budget_without_executing():
    client = _Client([_Job(estimated_bytes=1001)])
    connector = BigQueryConnector(
        {"project_id": "bounded-project", "maximum_bytes_billed": 1000}
    )
    connector._client = client

    with pytest.raises(ScanBudgetExceeded, match="above the configured maximum"):
        await connector.execute_profile_query("SELECT 1")

    assert len(client.queries) == 1


@pytest.mark.asyncio
async def test_bigquery_cancels_query_on_timeout():
    query_job = _Job(error=FuturesTimeoutError())
    client = _Client([_Job(estimated_bytes=1), query_job])
    connector = BigQueryConnector({"project_id": "bounded-project"})
    connector._client = client

    with pytest.raises(TimeoutError, match="exceeded its timeout"):
        await connector.execute_profile_query("SELECT 1")

    assert query_job.cancelled is True


@pytest.mark.asyncio
async def test_bigquery_dataset_scope_avoids_global_enumeration_and_quotes_ddl():
    client = _Client()
    connector = BigQueryConnector(
        {"project_id": "bounded-project", "dataset": "analytics"}
    )
    connector._client = client

    assert await connector.test_connection() is True
    schemas = await connector.discover_schemas()
    ddl = await connector.get_table_ddl("analytics", "events")

    assert client.list_dataset_calls == 0
    assert client.dataset_requests == [
        "bounded-project.analytics",
        "bounded-project.analytics",
    ]
    assert schemas[0].name == "analytics"
    assert schemas[0].tables[0].name == "events"
    assert "`event``id` INT64 NOT NULL" in ddl
    with pytest.raises(ValueError, match="restricted"):
        await connector.get_table_ddl("other", "events")


@pytest.mark.asyncio
async def test_bigquery_close_is_offloaded_and_idempotent():
    client = _Client()
    connector = BigQueryConnector({"project_id": "bounded-project"})
    connector._client = client

    await connector.close()
    await connector.close()

    assert client.closed is True
    assert connector._client is None


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"maximum_bytes_billed": 0}, "between"),
        ({"maximum_bytes_billed": "many"}, "integer"),
        ({"query_timeout_seconds": 0}, "between"),
    ],
)
def test_bigquery_rejects_invalid_execution_bounds(config, message):
    connector = BigQueryConnector({"project_id": "bounded-project", **config})

    method = (
        connector._maximum_bytes_billed
        if "maximum_bytes_billed" in config
        else connector._query_timeout_seconds
    )
    with pytest.raises(ConnectorConfigurationError, match=message):
        method()


def test_bigquery_profiler_uses_standard_sql_and_one_fully_quoted_asset():
    query = ProfilerService().build_profile_query(
        "analytics`prod",
        "order events",
        [
            ColumnInfo("amount`gross", "NUMERIC"),
            ColumnInfo("status", "STRING"),
            ColumnInfo("created_at", "TIMESTAMP"),
        ],
        "created_at",
        dialect="bigquery",
    )

    assert "FROM `analytics``prod.order events`" in query
    assert "SAFE_DIVIDE(COUNTIF(`amount``gross` IS NULL), COUNT(*))" in query
    assert "STDDEV_POP(CAST(`amount``gross` AS FLOAT64))" in query
    assert "CAST(`status` AS STRING)" in query
    assert "TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(TIMESTAMP(`created_at`)), SECOND)" in query
    assert "PERCENTILE_CONT" not in query
    assert "::" not in query
