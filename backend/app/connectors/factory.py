from app.connectors.base import BaseConnector

# Connector registry: type → (module_path, class_name, required_config_keys)
CONNECTOR_REGISTRY = {
    "postgres": {
        "module": "app.connectors.postgres",
        "class": "PostgresConnector",
        "required": ["host", "database"],
        "optional": {"port": 5432, "username": "", "password": ""},
        "label": "PostgreSQL",
        "description": "PostgreSQL / Aurora Postgres",
    },
    "mysql": {
        "module": "app.connectors.mysql",
        "class": "MySQLConnector",
        "required": ["host", "database"],
        "optional": {"port": 3306, "username": "root", "password": ""},
        "label": "MySQL / MariaDB",
        "description": "MySQL 5.7+, MariaDB 10+",
    },
    "redshift": {
        "module": "app.connectors.redshift",
        "class": "RedshiftConnector",
        "required": ["host", "database", "username", "password"],
        "optional": {"port": 5439},
        "label": "Amazon Redshift",
        "description": "AWS Redshift (Postgres-compatible)",
    },
    "bigquery": {
        "module": "app.connectors.bigquery",
        "class": "BigQueryConnector",
        "required": ["project_id"],
        "optional": {"credentials_json": None, "dataset": None},
        "label": "Google BigQuery",
        "description": "Google Cloud BigQuery",
    },
    "snowflake": {
        "module": "app.connectors.snowflake",
        "class": "SnowflakeConnector",
        "required": ["account", "user", "database"],
        "optional": {"password": "", "warehouse": "COMPUTE_WH", "schema": "PUBLIC"},
        "label": "Snowflake",
        "description": "Snowflake Cloud Data Platform",
    },
    "clickhouse": {
        "module": "app.connectors.clickhouse",
        "class": "ClickHouseConnector",
        "required": ["host"],
        "optional": {"port": 8123, "database": "default", "username": "default", "password": ""},
        "label": "ClickHouse",
        "description": "ClickHouse OLAP database",
    },
    "databricks": {
        "module": "app.connectors.databricks",
        "class": "DatabricksConnector",
        "required": ["server_hostname", "http_path", "access_token"],
        "optional": {"catalog": "hive_metastore", "schema": "default"},
        "label": "Databricks",
        "description": "Databricks Lakehouse SQL",
    },
    "trino": {
        "module": "app.connectors.trino",
        "class": "TrinoConnector",
        "required": ["host", "catalog"],
        "optional": {"port": 8080, "user": "trino", "password": "", "schema": "default", "http_scheme": "http"},
        "label": "Trino / Presto",
        "description": "Trino or PrestoDB federated query",
    },
    "duckdb": {
        "module": "app.connectors.duckdb",
        "class": "DuckDBConnector",
        "required": [],
        "optional": {"path": ":memory:"},
        "label": "DuckDB",
        "description": "DuckDB in-process OLAP",
    },
    "sqlite": {
        "module": "app.connectors.sqlite",
        "class": "SQLiteConnector",
        "required": ["path"],
        "optional": {},
        "label": "SQLite",
        "description": "SQLite file database",
    },
}


class ConnectorFactory:
    @staticmethod
    def create(source_type: str, config: dict) -> BaseConnector:
        key = source_type.lower()
        entry = CONNECTOR_REGISTRY.get(key)
        if not entry:
            raise ValueError(f"Unsupported source type: {source_type}")
        import importlib
        mod = importlib.import_module(entry["module"])
        cls = getattr(mod, entry["class"])
        return cls(config)

    @staticmethod
    def supported_types() -> list[dict]:
        """Return metadata for all connector types (for UI forms)."""
        return [
            {
                "type": k,
                "label": v["label"],
                "description": v["description"],
                "required": v["required"],
                "optional": v["optional"],
            }
            for k, v in CONNECTOR_REGISTRY.items()
        ]
