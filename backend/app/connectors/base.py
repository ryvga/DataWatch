from abc import ABC, abstractmethod
from dataclasses import dataclass, field


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

    @abstractmethod
    async def test_connection(self) -> bool:
        """Return True if connection succeeds, False otherwise. Never raise."""

    @abstractmethod
    async def discover_schemas(self) -> list[SchemaInfo]:
        """Return all user-accessible schemas and their tables."""

    @abstractmethod
    async def execute_profile_query(self, query: str) -> dict:
        """Execute an aggregate SQL query and return a flat dict of results."""

    @abstractmethod
    async def get_table_ddl(self, schema: str, table: str) -> str:
        """Return a DDL-like string describing the table columns and types."""

    async def close(self) -> None:
        """Release any held connections/pools. Override if needed."""
