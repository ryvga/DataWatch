from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ConnectorConfigurationError(ValueError):
    """A stable, secret-free connector configuration error safe for API responses."""


class ScanBudgetExceeded(ValueError):
    """The connector can prove the configured scan bound is too small."""


class ScanBudgetUnsupported(NotImplementedError):
    """The connector cannot enforce a requested scan bound."""


class DocumentScanBudgetExceeded(ValueError):
    """A native document plan reached its mandatory document ceiling."""


@dataclass
class TableInfo:
    name: str
    estimated_rows: int | None = None


@dataclass
class SchemaInfo:
    name: str
    tables: list[TableInfo] = field(default_factory=list)


class BaseConnector(ABC):
    """Abstract base for all warehouse connectors."""

    # Automated profiling is intentionally opt-in. A connector may be able to
    # connect, discover assets, and execute a scalar query without supporting
    # the aggregate SQL emitted by ProfilerService.
    profile_dialect: str | None = None
    monitor_dialect: str | None = None
    native_profile_kind: str | None = None

    @abstractmethod
    async def test_connection(self) -> bool:
        """Return True if connection succeeds, False otherwise. Never raise."""

    @abstractmethod
    async def discover_schemas(self) -> list[SchemaInfo]:
        """Return all user-accessible schemas and their tables."""

    @abstractmethod
    async def execute_profile_query(self, query: str) -> dict:
        """Execute an aggregate SQL query and return a flat dict of results."""

    async def execute_monitor_query(self, query: str, *, timeout_seconds: int = 30) -> dict:
        """Execute a restricted scalar monitor query.

        Connectors must opt in with database-enforced read-only and timeout controls.
        Returning the first row from a general query method is insufficient because
        the monitor result contract must detect zero or multiple rows.
        """
        raise NotImplementedError(f"{type(self).__name__} has no restricted monitor execution path")

    async def execute_compiled_monitor(
        self,
        statement: str,
        parameters: dict,
        *,
        timeout_seconds: int = 30,
    ) -> dict:
        """Execute an internally compiled aggregate plan with driver-bound values."""
        raise NotImplementedError(f"{type(self).__name__} has no compiled monitor execution path")

    async def execute_document_monitor(self, plan) -> dict:
        """Execute an internally generated, connector-native document plan."""
        raise NotImplementedError(f"{type(self).__name__} has no document monitor execution path")

    async def enforce_monitor_scan_budget(
        self,
        schema: str,
        table: str,
        max_bytes_scanned: int,
    ) -> None:
        """Fail unless the adapter can enforce a conservative scan upper bound."""
        raise ScanBudgetUnsupported(f"{type(self).__name__} cannot enforce maxBytesScanned")

    @abstractmethod
    async def get_table_ddl(self, schema: str, table: str) -> str:
        """Return a DDL-like string describing the table columns and types."""

    async def get_table_schema(
        self,
        schema: str,
        table: str,
    ) -> tuple[str, set[str] | None]:
        """Return a snapshot plus native column/field names when available."""
        return await self.get_table_ddl(schema, table), None

    async def validate_profile_config(
        self,
        schema: str,
        table: str,
        freshness_column: str | None,
    ) -> None:
        """Fail closed when connector-specific profile settings are unsafe."""

    async def collect_native_profile(
        self,
        schema: str,
        table: str,
        freshness_column: str | None,
    ) -> dict:
        """Return a bounded native profile for non-relational connectors."""
        raise NotImplementedError(f"{type(self).__name__} has no native profiling path")

    async def close(self) -> None:
        """Release any held connections/pools. Override if needed."""
