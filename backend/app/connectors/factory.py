from app.connectors.base import BaseConnector


FIELD_METADATA = {
    "host": {"label": "Host", "input_type": "text", "placeholder": "db.example.com"},
    "port": {"label": "Port", "input_type": "number"},
    "database": {"label": "Database", "input_type": "text", "placeholder": "analytics"},
    "username": {"label": "Username", "input_type": "text"},
    "user": {"label": "User", "input_type": "text"},
    "password": {"label": "Password", "input_type": "password", "secret": True},
    "project_id": {"label": "Project ID", "input_type": "text", "placeholder": "my-gcp-project"},
    "credentials_json": {"label": "Service account JSON", "input_type": "textarea", "secret": True},
    "dataset": {"label": "Dataset", "input_type": "text"},
    "account": {"label": "Account", "input_type": "text", "placeholder": "xy12345.us-east-1"},
    "warehouse": {"label": "Warehouse", "input_type": "text"},
    "schema": {"label": "Default schema", "input_type": "text"},
    "path": {"label": "File path", "input_type": "text", "placeholder": "/data/warehouse.duckdb"},
    "uri": {"label": "URI", "input_type": "text", "secret": True},
    "hosts": {"label": "Hosts", "input_type": "text", "placeholder": "node1.example.com,node2.example.com"},
    "keyspace": {"label": "Keyspace", "input_type": "text"},
    "driver": {"label": "ODBC driver", "input_type": "text"},
    "server_hostname": {"label": "Server hostname", "input_type": "text"},
    "http_path": {"label": "HTTP path", "input_type": "text"},
    "access_token": {"label": "Access token", "input_type": "password", "secret": True},
    "catalog": {"label": "Catalog", "input_type": "text"},
    "http_scheme": {"label": "HTTP scheme", "input_type": "select", "options": ["http", "https"]},
}


VERSION_OPTIONS = {
    "postgres": ["Auto-detect", "PostgreSQL 16", "PostgreSQL 15", "PostgreSQL 14", "PostgreSQL 13", "Aurora PostgreSQL"],
    "mysql": ["Auto-detect", "MySQL 8", "MySQL 5.7", "MariaDB 11", "MariaDB 10"],
    "redshift": ["Auto-detect", "RA3", "DC2"],
    "bigquery": ["Auto-detect", "Standard SQL"],
    "snowflake": ["Auto-detect"],
    "clickhouse": ["Auto-detect", "23.x", "24.x", "25.x"],
    "databricks": ["Auto-detect", "SQL Warehouse", "Unity Catalog"],
    "trino": ["Auto-detect", "Trino", "PrestoDB"],
    "duckdb": ["Auto-detect", "0.10+", "1.x"],
    "sqlite": ["Auto-detect", "SQLite 3"],
    "cassandra": ["Auto-detect", "Apache Cassandra 4", "Apache Cassandra 5", "Astra DB"],
    "mongodb": ["Auto-detect", "MongoDB 6", "MongoDB 7", "MongoDB Atlas"],
    "sqlserver": ["Auto-detect", "SQL Server 2022", "SQL Server 2019", "Azure SQL"],
}


def _field_metadata(name: str, default, required: bool) -> dict:
    metadata = FIELD_METADATA.get(name, {})
    return {
        "name": name,
        "label": metadata.get("label", name.replace("_", " ").title()),
        "required": required,
        "default": default,
        "input_type": metadata.get("input_type", "text"),
        "placeholder": metadata.get("placeholder"),
        "secret": bool(metadata.get("secret", False)),
        "options": metadata.get("options"),
    }


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
    "cassandra": {
        "module": "app.connectors.cassandra",
        "class": "CassandraConnector",
        "required": ["hosts"],
        "optional": {"port": 9042, "keyspace": None, "username": None, "password": None},
        "label": "Cassandra",
        "description": "Apache Cassandra (safe monitors — no full-table scans)",
        "tier": 2,
    },
    "mongodb": {
        "module": "app.connectors.mongodb",
        "class": "MongoDBConnector",
        "required": ["uri"],
        "optional": {"database": None},
        "label": "MongoDB",
        "description": "MongoDB document database (Tier 1 — field drift detection)",
        "tier": 1,
    },
    "sqlserver": {
        "module": "app.connectors.sqlserver",
        "class": "SQLServerConnector",
        "required": ["host", "database", "username", "password"],
        "optional": {"port": 1433, "driver": "ODBC Driver 18 for SQL Server"},
        "label": "SQL Server",
        "description": "Microsoft SQL Server / Azure SQL",
        "tier": 2,
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
        result = []
        for k, v in CONNECTOR_REGISTRY.items():
            required_fields = [
                _field_metadata(name, "", True)
                for name in v["required"]
            ]
            optional_fields = [
                _field_metadata(name, default, False)
                for name, default in v["optional"].items()
            ]
            result.append({
                "type": k,
                "label": v["label"],
                "description": v["description"],
                "required": v["required"],
                "optional": v["optional"],
                "fields": required_fields + optional_fields,
                "versions": VERSION_OPTIONS.get(k, ["Auto-detect"]),
                "tier": v.get("tier", 0),
            })
        return result
