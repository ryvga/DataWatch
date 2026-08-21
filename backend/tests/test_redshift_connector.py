from app.connectors.redshift import RedshiftConnector


def test_redshift_credentials_are_passed_as_driver_kwargs():
    connector = RedshiftConnector(
        {
            "host": "warehouse.example.com options=unsafe",
            "port": 5439,
            "database": "analytics sslmode=disable",
            "username": "monitor user=admin",
            "password": "secret sslmode=disable",
        }
    )

    assert connector._connect_kwargs() == {
        "host": "warehouse.example.com options=unsafe",
        "port": 5439,
        "dbname": "analytics sslmode=disable",
        "user": "monitor user=admin",
        "password": "secret sslmode=disable",
        "sslmode": "require",
    }
