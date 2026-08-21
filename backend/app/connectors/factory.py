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
    "maximum_bytes_billed": {"label": "Maximum bytes billed per profile", "input_type": "number"},
    "query_timeout_seconds": {"label": "Query timeout (seconds)", "input_type": "number"},
    "account": {"label": "Account", "input_type": "text", "placeholder": "xy12345.us-east-1"},
    "warehouse": {"label": "Warehouse", "input_type": "text"},
    "schema": {"label": "Default schema", "input_type": "text"},
    "path": {"label": "File path", "input_type": "text", "placeholder": "/data/warehouse.duckdb"},
    "uri": {"label": "URI", "input_type": "text", "secret": True},
    "hosts": {"label": "Hosts", "input_type": "text", "placeholder": "node1.example.com,node2.example.com"},
    "keyspace": {"label": "Keyspace", "input_type": "text"},
    "driver": {"label": "ODBC driver", "input_type": "text"},
    "server_hostname": {"label": "Server hostname", "input_type": "text"},
    "tls_server_name": {"label": "TLS server name", "input_type": "text"},
    "http_path": {"label": "HTTP path", "input_type": "text"},
    "access_token": {"label": "Access token", "input_type": "password", "secret": True},
    "catalog": {"label": "Catalog", "input_type": "text"},
    "http_scheme": {"label": "HTTP scheme", "input_type": "select", "options": ["http", "https"]},
    "tls_mode": {
        "label": "TLS mode",
        "input_type": "select",
        "options": ["verify_identity", "disabled"],
    },
    "ssl_ca": {"label": "TLS CA certificate (PEM)", "input_type": "textarea"},
    "profile_sample_size": {
        "label": "Profile sample size",
        "input_type": "number",
    },
    "key_pattern": {
        "label": "Key pattern",
        "input_type": "text",
        "placeholder": "app:*",
    },
    "max_scan_keys": {"label": "Maximum scanned keys", "input_type": "number"},
    "scan_count": {"label": "SCAN count hint", "input_type": "number"},
    "service_name": {"label": "Service name", "input_type": "text", "placeholder": "FREEPDB1"},
    "wallet_location": {"label": "Wallet directory", "input_type": "text"},
    "wallet_password": {"label": "Wallet password", "input_type": "password", "secret": True},
    "connect_timeout_seconds": {"label": "Connect timeout (seconds)", "input_type": "number"},
    "call_timeout_ms": {"label": "Call timeout (milliseconds)", "input_type": "number"},
}


VERSION_OPTIONS = {
    "postgres": [
        "Auto-detect",
        "PostgreSQL 16",
        "PostgreSQL 15",
        "PostgreSQL 14",
        "PostgreSQL 13",
        "Aurora PostgreSQL",
    ],
    "mysql": ["Auto-detect", "MySQL 8", "MySQL 5.7"],
    "mariadb": ["Auto-detect", "MariaDB 11.4 LTS", "MariaDB 10.11 LTS"],
    "redshift": ["Auto-detect", "RA3", "DC2"],
    "bigquery": ["Auto-detect", "Standard SQL"],
    "snowflake": ["Auto-detect"],
    "clickhouse": ["Auto-detect", "23.x", "24.x", "25.x"],
    "databricks": ["Auto-detect", "SQL Warehouse", "Unity Catalog"],
    "trino": ["Auto-detect", "Trino", "PrestoDB"],
    "duckdb": ["Auto-detect", "0.10+", "1.x"],
    "sqlite": ["Auto-detect", "SQLite 3"],
    "cassandra": ["Auto-detect", "Apache Cassandra 4", "Apache Cassandra 5"],
    "mongodb": ["Auto-detect", "MongoDB 6", "MongoDB 7", "MongoDB Atlas"],
    "redis": ["Auto-detect", "Redis 7", "Redis 8"],
    "sqlserver": ["Auto-detect", "SQL Server 2022", "SQL Server 2019", "Azure SQL"],
    "oracle": ["Auto-detect", "Oracle Database 23ai Free", "Oracle Database 19c"],
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
        "readiness": "stable",
    },
    "mysql": {
        "module": "app.connectors.mysql",
        "class": "MySQLConnector",
        "required": ["host", "database", "username"],
        "optional": {
            "port": 3306,
            "password": "",
            "tls_mode": "verify_identity",
            "ssl_ca": None,
        },
        "label": "MySQL",
        "description": "MySQL 5.7+",
        "readiness": "experimental",
    },
    "mariadb": {
        "module": "app.connectors.mysql",
        "class": "MySQLConnector",
        "required": ["host", "database", "username"],
        "optional": {
            "port": 3306,
            "password": "",
            "tls_mode": "verify_identity",
            "ssl_ca": None,
        },
        "label": "MariaDB",
        "description": "MariaDB 10.11+ / 11.4 LTS",
        "readiness": "experimental",
    },
    "redshift": {
        "module": "app.connectors.redshift",
        "class": "RedshiftConnector",
        "required": ["host", "database", "username", "password"],
        "optional": {"port": 5439, "schema": None},
        "label": "Amazon Redshift",
        "description": "AWS Redshift (Postgres-compatible)",
        "readiness": "experimental",
    },
    "bigquery": {
        "module": "app.connectors.bigquery",
        "class": "BigQueryConnector",
        "required": ["project_id"],
        "optional": {
            "credentials_json": None,
            "dataset": None,
            "maximum_bytes_billed": 1073741824,
            "query_timeout_seconds": 120,
        },
        "label": "Google BigQuery",
        "description": "Google Cloud BigQuery with dry-run cost enforcement",
        "readiness": "experimental",
    },
    "snowflake": {
        "module": "app.connectors.snowflake",
        "class": "SnowflakeConnector",
        "required": ["account", "user", "database"],
        "optional": {
            "password": "",
            "warehouse": "COMPUTE_WH",
            "schema": "PUBLIC",
            "query_timeout_seconds": 120,
        },
        "label": "Snowflake",
        "description": "Snowflake with scoped discovery and timeout-bounded profiling",
        "readiness": "experimental",
    },
    "clickhouse": {
        "module": "app.connectors.clickhouse",
        "class": "ClickHouseConnector",
        "required": ["host"],
        "optional": {"port": 8123, "database": "default", "username": "default", "password": ""},
        "label": "ClickHouse",
        "description": "ClickHouse OLAP database",
        "readiness": "experimental",
    },
    "databricks": {
        "module": "app.connectors.databricks",
        "class": "DatabricksConnector",
        "required": ["server_hostname", "http_path", "access_token"],
        "optional": {"catalog": "hive_metastore", "schema": "default"},
        "label": "Databricks",
        "description": "Databricks Lakehouse SQL",
        "readiness": "experimental",
    },
    "trino": {
        "module": "app.connectors.trino",
        "class": "TrinoConnector",
        "required": ["host", "catalog"],
        "optional": {"port": 8080, "user": "trino", "password": "", "schema": "default", "http_scheme": "http"},
        "label": "Trino / Presto",
        "description": "Trino or PrestoDB federated query",
        "readiness": "experimental",
    },
    "duckdb": {
        "module": "app.connectors.duckdb",
        "class": "DuckDBConnector",
        "required": [],
        "optional": {"path": ":memory:"},
        "label": "DuckDB",
        "description": "DuckDB in-process OLAP",
        "readiness": "beta",
    },
    "sqlite": {
        "module": "app.connectors.sqlite",
        "class": "SQLiteConnector",
        "required": ["path"],
        "optional": {},
        "label": "SQLite",
        "description": "SQLite file database",
        "readiness": "beta",
    },
    "cassandra": {
        "module": "app.connectors.cassandra",
        "class": "CassandraConnector",
        "required": ["hosts"],
        "optional": {
            "port": 9042,
            "keyspace": None,
            "username": None,
            "password": None,
            "tls_mode": "verify_identity",
            "tls_server_name": None,
            "ssl_ca": None,
        },
        "label": "Cassandra",
        "description": "Apache Cassandra discovery/schema and manual partition-bound typed monitors",
        "tier": 2,
        "readiness": "experimental",
    },
    "mongodb": {
        "module": "app.connectors.mongodb",
        "class": "MongoDBConnector",
        "required": ["uri", "database"],
        "optional": {
            "tls_mode": "verify_identity",
            "profile_sample_size": 1000,
        },
        "label": "MongoDB",
        "description": "MongoDB document database (Tier 1 — field drift detection)",
        "tier": 1,
        "readiness": "experimental",
    },
    "redis": {
        "module": "app.connectors.redis",
        "class": "RedisConnector",
        "required": ["host"],
        "optional": {
            "port": 6379,
            "database": 0,
            "username": None,
            "password": None,
            "tls_mode": "verify_identity",
            "ssl_ca": None,
            "key_pattern": "*",
            "max_scan_keys": 1000,
            "scan_count": 100,
        },
        "label": "Redis",
        "description": "Redis bounded profile and metadata-only typed keyspace monitors",
        "tier": 2,
        "readiness": "experimental",
    },
    "sqlserver": {
        "module": "app.connectors.sqlserver",
        "class": "SQLServerConnector",
        "required": ["host", "database", "username", "password"],
        "optional": {
            "port": 1433,
            "driver": "ODBC Driver 18 for SQL Server",
            "tls_mode": "verify_identity",
        },
        "label": "SQL Server",
        "description": "Microsoft SQL Server / Azure SQL",
        "tier": 2,
        "readiness": "experimental",
    },
    "oracle": {
        "module": "app.connectors.oracle",
        "class": "OracleConnector",
        "required": ["host", "service_name", "username", "password"],
        "optional": {
            "port": 1521,
            "schema": None,
            "tls_mode": "verify_identity",
            "wallet_location": None,
            "wallet_password": None,
            "connect_timeout_seconds": 15,
            "call_timeout_ms": 120000,
        },
        "label": "Oracle Database",
        "description": "Oracle Database 19c+ / 23ai using the async thin driver",
        "tier": 2,
        "readiness": "experimental",
    },
}


def _connector_class(source_type: str) -> type[BaseConnector]:
    import importlib

    entry = CONNECTOR_REGISTRY[source_type]
    module = importlib.import_module(entry["module"])
    return getattr(module, entry["class"])


def _overrides(connector_class: type[BaseConnector], method_name: str) -> bool:
    return getattr(connector_class, method_name) is not getattr(BaseConnector, method_name)


def derive_connector_capabilities(connector_class: type[BaseConnector]) -> dict:
    """Generate the public matrix from executable adapter contracts."""
    profile_dialect = connector_class.profile_dialect
    has_native_profile = _overrides(connector_class, "collect_native_profile")
    if profile_dialect in {"postgres", "duckdb"}:
        profiling = "full"
    elif profile_dialect or has_native_profile:
        profiling = "core"
    else:
        profiling = "none"

    custom_monitors = (
        "legacy_sql_scalar"
        if connector_class.monitor_dialect and _overrides(connector_class, "execute_monitor_query")
        else "none"
    )
    compiled_monitors = "none"
    if connector_class.monitor_dialect and _overrides(connector_class, "execute_compiled_monitor"):
        compiled_monitors = "internal_read_only"
    elif _overrides(connector_class, "execute_document_monitor"):
        compiled_monitors = "internal_document_read_only"
    elif _overrides(connector_class, "execute_partition_monitor"):
        compiled_monitors = "internal_partition_read_only"
    elif _overrides(connector_class, "execute_keyspace_monitor"):
        compiled_monitors = "internal_keyspace_read_only"

    return {
        "connection_test": _overrides(connector_class, "test_connection"),
        "discovery": _overrides(connector_class, "discover_schemas"),
        "schema": _overrides(connector_class, "get_table_ddl"),
        "profiling": profiling,
        "custom_monitors": custom_monitors,
        "compiled_monitors": compiled_monitors,
        "sampling": has_native_profile,
    }


class ConnectorFactory:
    @staticmethod
    def capabilities_for(source_type: str) -> dict:
        key = source_type.lower()
        if key not in CONNECTOR_REGISTRY:
            raise ValueError(f"Unsupported source type: {source_type}")
        return derive_connector_capabilities(_connector_class(key))

    @staticmethod
    def create(source_type: str, config: dict) -> BaseConnector:
        key = source_type.lower()
        entry = CONNECTOR_REGISTRY.get(key)
        if not entry:
            raise ValueError(f"Unsupported source type: {source_type}")
        cls = _connector_class(key)
        return cls(config)

    @staticmethod
    def supported_types() -> list[dict]:
        """Return metadata for all connector types (for UI forms)."""
        result = []
        for k, v in CONNECTOR_REGISTRY.items():
            required_fields = [_field_metadata(name, "", True) for name in v["required"]]
            optional_fields = [_field_metadata(name, default, False) for name, default in v["optional"].items()]
            result.append(
                {
                    "type": k,
                    "label": v["label"],
                    "description": v["description"],
                    "required": v["required"],
                    "optional": v["optional"],
                    "fields": required_fields + optional_fields,
                    "versions": VERSION_OPTIONS.get(k, ["Auto-detect"]),
                    "tier": v.get("tier", 0),
                    "readiness": v["readiness"],
                    "capabilities": derive_connector_capabilities(_connector_class(k)),
                }
            )
        return result
