from app.connectors.base import BaseConnector


class ConnectorFactory:
    @staticmethod
    def create(source_type: str, config: dict) -> BaseConnector:
        """Instantiate the correct connector for source_type."""
        match source_type.lower():
            case "postgres":
                from app.connectors.postgres import PostgresConnector
                return PostgresConnector(config)
            case "bigquery":
                from app.connectors.bigquery import BigQueryConnector
                return BigQueryConnector(config)
            case "snowflake":
                from app.connectors.snowflake import SnowflakeConnector
                return SnowflakeConnector(config)
            case "duckdb":
                from app.connectors.duckdb import DuckDBConnector
                return DuckDBConnector(config)
            case _:
                raise ValueError(f"Unsupported source type: {source_type}")
