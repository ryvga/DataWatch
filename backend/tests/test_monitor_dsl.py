from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.services.monitor_dsl import (
    MonitorDefinition,
    canonical_json,
    definition_hash,
    predicate_stats,
)

ASSET_ID = "8efef403-4c5d-4930-a2dd-f289c16f41a9"


def valid_definition() -> dict:
    return {
        "apiVersion": "datawatch.io/v1alpha1",
        "kind": "Monitor",
        "metadata": {"name": "paid-orders-require-reference", "labels": {"team": "payments"}},
        "spec": {
            "target": {"assetId": ASSET_ID},
            "trigger": {"type": "on_profile"},
            "measurements": [
                {
                    "id": "invalid_orders",
                    "type": "violations",
                    "violationWhen": {
                        "all": [
                            {
                                "op": "eq",
                                "left": {"field": "status"},
                                "right": {"literal": "paid"},
                            },
                            {"op": "is_null", "value": {"field": "payment_reference"}},
                        ]
                    },
                    "output": ["count", "rate"],
                }
            ],
            "breachWhen": {
                "op": "gt",
                "left": {"ref": "invalid_orders.rate"},
                "right": {"literal": 0.01},
            },
            "policy": {
                "severity": "P2",
                "consecutiveBreaches": 2,
                "recoveryPasses": 2,
                "cooldownMinutes": 60,
                "notifyOnExecutionError": True,
            },
            "execution": {
                "timeoutSeconds": 30,
                "maxBytesScanned": 1_000_000_000,
                "maxDocumentsScanned": 1_000_000,
                "sampling": {"mode": "auto"},
            },
        },
    }


def test_v1alpha1_example_is_canonical_and_stably_hashed():
    first = MonitorDefinition.model_validate(valid_definition())
    reordered = MonitorDefinition.model_validate(
        {key: valid_definition()[key] for key in ("spec", "metadata", "kind", "apiVersion")}
    )

    assert first.spec.target.asset_id == UUID(ASSET_ID)
    assert definition_hash(first) == definition_hash(reordered)
    assert canonical_json(first) == canonical_json(reordered)
    assert predicate_stats(first) == {"predicateNodes": 4, "predicateDepth": 2}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda definition: definition.update({"unknown": True}),
        lambda definition: definition.update({"apiVersion": "datawatch.io/v2"}),
        lambda definition: definition["metadata"].update({"name": "Not Valid"}),
        lambda definition: definition["spec"]["measurements"][0].update({"extra": "no"}),
        lambda definition: definition["spec"]["measurements"].append(deepcopy(definition["spec"]["measurements"][0])),
        lambda definition: definition["spec"]["breachWhen"]["left"].update({"ref": "missing.rate"}),
        lambda definition: definition["spec"]["breachWhen"]["left"].update({"ref": "invalid_orders.unknown"}),
        lambda definition: definition["spec"]["breachWhen"]["right"].update({"field": "also_invalid"}),
        lambda definition: definition["spec"]["execution"].update({"timeoutSeconds": 121}),
        lambda definition: definition["spec"]["breachWhen"]["right"].update({"literal": float("nan")}),
    ],
)
def test_dsl_rejects_unknown_versions_fields_refs_and_invalid_bounds(mutate):
    definition = valid_definition()
    mutate(definition)
    with pytest.raises(ValidationError):
        MonitorDefinition.model_validate(definition)


def test_dsl_rejects_predicates_deeper_than_limit():
    definition = valid_definition()
    predicate = definition["spec"]["breachWhen"]
    for _ in range(10):
        predicate = {"not": predicate}
    definition["spec"]["breachWhen"] = predicate

    with pytest.raises(ValidationError, match="depth 10"):
        MonitorDefinition.model_validate(definition)


def test_metric_measurement_has_strict_type_contract():
    definition = valid_definition()
    definition["spec"]["measurements"] = [{"id": "rows", "type": "metric", "metric": "row_count"}]
    definition["spec"]["breachWhen"] = {
        "op": "eq",
        "left": {"ref": "rows"},
        "right": {"literal": 0},
    }

    model = MonitorDefinition.model_validate(definition)
    assert model.spec.measurements[0].metric == "row_count"


def test_richer_monitor_metadata_filters_and_track_mode_are_canonical():
    definition = valid_definition()
    definition["metadata"].update(
        {
            "description": "Orders must remain complete for the payments domain.",
            "owner": "payments@example.com",
            "qualityDimension": "completeness",
            "notes": "Review the upstream checkout job before disabling this monitor.",
        }
    )
    definition["spec"]["measurements"] = [
        {
            "id": "paid_email_null_rate",
            "type": "metric",
            "metric": "null_rate",
            "field": "email",
            "filterWhen": {
                "op": "eq",
                "left": {"field": "status"},
                "right": {"literal": "paid"},
            },
        }
    ]
    definition["spec"]["breachWhen"] = {
        "op": "gt",
        "left": {"ref": "paid_email_null_rate"},
        "right": {"literal": 0.01},
    }
    definition["spec"]["policy"] = {"mode": "track", "audience": ["payments"]}

    model = MonitorDefinition.model_validate(definition)

    assert model.metadata.quality_dimension == "completeness"
    assert model.spec.policy.mode == "track"
    assert model.spec.measurements[0].filter_when is not None
    assert predicate_stats(model) == {"predicateNodes": 2, "predicateDepth": 1}


def test_interval_trigger_requires_a_scheduler_interval():
    definition = valid_definition()
    definition["spec"]["trigger"] = {"type": "interval"}
    with pytest.raises(ValidationError, match="intervalMinutes"):
        MonitorDefinition.model_validate(definition)

    definition["spec"]["trigger"] = {"type": "interval", "intervalMinutes": 15}
    model = MonitorDefinition.model_validate(definition)
    assert model.spec.trigger.interval_minutes == 15


@pytest.mark.parametrize("operator", ["not_between", "is_empty", "is_whitespace", "is_future"])
def test_extended_predicate_operators_are_structurally_valid(operator):
    definition = valid_definition()
    if operator in {"is_empty", "is_whitespace", "is_future"}:
        definition["spec"]["measurements"][0]["violationWhen"] = {
            "op": operator,
            "value": {"field": "status"},
        }
    else:
        definition["spec"]["measurements"][0]["violationWhen"] = {
            "op": operator,
            "left": {"field": "amount"},
            "right": {"literal": [1, 10]},
        }
    assert MonitorDefinition.model_validate(definition).spec.measurements[0].violation_when.op == operator


@pytest.mark.asyncio
async def test_validation_endpoint_resolves_tenant_asset_and_returns_plan():
    from app.routers.monitor_dsl import validate_monitor_definition

    table = SimpleNamespace(
        id=UUID(ASSET_ID),
        source_id="source-1",
        schema_name="public",
        table_name="orders",
        dbt_model_yaml=("CREATE TABLE public.orders (status text NULL, payment_reference text NULL);"),
    )
    source = SimpleNamespace(id="source-1", type="postgres")

    class Database:
        async def execute(self, statement):
            class Result:
                def one_or_none(self):
                    return (table, source)

            return Result()

        async def scalar(self, statement):
            return None

    definition = MonitorDefinition.model_validate(valid_definition())
    response = await validate_monitor_definition(
        definition,
        org=SimpleNamespace(id="org-1"),
        db=Database(),
    )

    assert response["valid"] is True
    assert response["definitionHash"] == definition_hash(definition)
    assert response["stats"] == {
        "measurements": 1,
        "predicateNodes": 4,
        "predicateDepth": 2,
    }
    assert response["capabilityPlan"] == {
        "sourceType": "postgres",
        "requirements": ["violations"],
        "compilationSupported": True,
        "plannerVersion": "datawatch-v1alpha1-relational-2",
        "compatible": True,
        "unsupported": [],
        "issues": [],
        "activationSupported": True,
        "activationBlockers": [],
    }


@pytest.mark.asyncio
async def test_validation_distinguishes_valid_grammar_from_schema_incompatibility():
    from app.routers.monitor_dsl import validate_monitor_definition

    table = SimpleNamespace(
        id=UUID(ASSET_ID),
        schema_name="public",
        table_name="orders",
        dbt_model_yaml="CREATE TABLE public.orders (amount text NULL);",
    )
    source = SimpleNamespace(type="postgres")

    class Database:
        async def execute(self, statement):
            class Result:
                def one_or_none(self):
                    return (table, source)

            return Result()

        async def scalar(self, statement):
            return None

    body = valid_definition()
    body["spec"]["measurements"] = [{"id": "average", "type": "metric", "metric": "mean", "field": "amount"}]
    body["spec"]["breachWhen"] = {
        "op": "gt",
        "left": {"ref": "average"},
        "right": {"literal": 10},
    }
    response = await validate_monitor_definition(
        MonitorDefinition.model_validate(body),
        org=SimpleNamespace(id="org-1"),
        db=Database(),
    )

    assert response["valid"] is True
    assert response["capabilityPlan"]["compilationSupported"] is False
    assert response["capabilityPlan"]["compatible"] is False
    assert response["capabilityPlan"]["unsupported"] == ["field_type_not_supported"]
    assert response["capabilityPlan"]["issues"][0]["message"] == ("mean does not support amount (string)")


@pytest.mark.asyncio
async def test_preview_returns_bound_plan_without_enabling_execution():
    from app.routers.monitor_dsl import preview_monitor_definition

    table = SimpleNamespace(
        id=UUID(ASSET_ID),
        schema_name="public",
        table_name="orders",
        dbt_model_yaml=("CREATE TABLE public.orders (status text NULL, payment_reference text NULL);"),
    )
    source = SimpleNamespace(type="postgres")

    class Database:
        async def execute(self, statement):
            class Result:
                def one_or_none(self):
                    return (table, source)

            return Result()

        async def scalar(self, statement):
            return None

    response = await preview_monitor_definition(
        MonitorDefinition.model_validate(valid_definition()),
        org=SimpleNamespace(id="org-1"),
        db=Database(),
    )

    assert response["preview"]["status"] == "compiled_validation_only"
    assert len(response["compiledPlan"]["relation"]["schemaFingerprint"]) == 32
    assert response["compiledPlan"]["statementMode"] == "preview_only"
    assert response["capabilityPlan"]["activationSupported"] is True
    assert response["capabilityPlan"]["activationBlockers"] == []


@pytest.mark.asyncio
async def test_mongodb_preview_uses_native_bounded_planner_and_attestation():
    from app.routers.monitor_dsl import preview_monitor_definition

    table = SimpleNamespace(
        id=UUID(ASSET_ID),
        schema_name="analytics",
        table_name="events",
        dbt_model_yaml=(
            'CREATE COLLECTION "analytics"."events" ("status" string NULL, "payment_reference" string NULL);'
        ),
    )
    source = SimpleNamespace(type="mongodb")

    class Database:
        async def execute(self, statement):
            class Result:
                def one_or_none(self):
                    return (table, source)

            return Result()

        async def scalar(self, statement):
            return None

    body = valid_definition()
    body["spec"]["execution"].pop("maxBytesScanned")
    body["spec"]["execution"]["maxDocumentsScanned"] = 100
    body["spec"]["execution"]["sampling"] = {"mode": "off"}
    response = await preview_monitor_definition(
        MonitorDefinition.model_validate(body),
        org=SimpleNamespace(id="org-1"),
        db=Database(),
    )

    assert response["preview"]["status"] == "compiled_validation_only"
    assert response["preview"]["plannerVersion"] == ("datawatch-v1alpha1-mongodb-1")
    assert response["compiledPlan"]["kind"] == "mongodb_bounded_aggregate"
    assert response["compiledPlan"]["pipeline"][0] == {"$limit": 101}
    assert len(response["compiledPlan"]["relation"]["schemaFingerprint"]) == 64
    assert response["capabilityPlan"]["activationSupported"] is True


@pytest.mark.asyncio
async def test_cassandra_preview_uses_partition_bound_planner_and_attestation():
    from app.routers.monitor_dsl import preview_monitor_definition

    table = SimpleNamespace(
        id=UUID(ASSET_ID),
        schema_name="analytics",
        table_name="events",
        dbt_model_yaml=(
            'CREATE TABLE "analytics"."events" (\n'
            '  "tenant_id" text is_partition_key=true is_clustering_key=false,\n'
            '  "event_id" int is_partition_key=false is_clustering_key=true,\n'
            '  "status" text is_partition_key=false is_clustering_key=false,\n'
            '  "payment_reference" text is_partition_key=false is_clustering_key=false\n);'
        ),
    )
    source = SimpleNamespace(type="cassandra")

    class Database:
        async def execute(self, statement):
            class Result:
                def one_or_none(self):
                    return (table, source)

            return Result()

        async def scalar(self, statement):
            return None

    body = valid_definition()
    body["spec"]["trigger"] = {"type": "manual"}
    body["spec"]["execution"].pop("maxBytesScanned")
    body["spec"]["execution"].pop("maxDocumentsScanned")
    body["spec"]["execution"]["maxRowsScanned"] = 100
    body["spec"]["execution"]["partitionBindings"] = {"tenant_id": "tenant-a"}
    body["spec"]["execution"]["sampling"] = {"mode": "off"}
    response = await preview_monitor_definition(
        MonitorDefinition.model_validate(body),
        org=SimpleNamespace(id="org-1"),
        db=Database(),
    )

    assert response["preview"]["status"] == "compiled_validation_only"
    assert response["preview"]["plannerVersion"] == "datawatch-v1alpha1-cassandra-1"
    assert response["compiledPlan"]["kind"] == "cassandra_partition_scan"
    assert response["compiledPlan"]["statementMode"] == "internal_prepared_only"
    assert response["compiledPlan"]["parameters"] == [{"name": "tenant_id", "value": "tenant-a"}]
    assert response["capabilityPlan"]["activationSupported"] is True


@pytest.mark.asyncio
async def test_incompatible_preview_does_not_issue_activation_attestation():
    from app.routers.monitor_dsl import preview_monitor_definition

    table = SimpleNamespace(
        id=UUID(ASSET_ID),
        schema_name="public",
        table_name="orders",
        dbt_model_yaml="CREATE TABLE public.orders (amount text NULL);",
    )
    source = SimpleNamespace(type="postgres")

    class Database:
        async def execute(self, statement):
            class Result:
                def one_or_none(self):
                    return (table, source)

            return Result()

        async def scalar(self, statement):
            return None

    body = valid_definition()
    body["spec"]["measurements"] = [{"id": "average", "type": "metric", "metric": "mean", "field": "amount"}]
    body["spec"]["breachWhen"] = {
        "op": "gt",
        "left": {"ref": "average"},
        "right": {"literal": 10},
    }
    response = await preview_monitor_definition(
        MonitorDefinition.model_validate(body),
        org=SimpleNamespace(id="org-1"),
        db=Database(),
    )

    assert response["preview"]["status"] == "validation_only"
    assert "attestation" not in response["preview"]
    assert "compiledPlan" not in response
    assert response["capabilityPlan"]["compilationSupported"] is False
