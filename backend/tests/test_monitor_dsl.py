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
        lambda definition: definition["spec"]["measurements"].append(
            deepcopy(definition["spec"]["measurements"][0])
        ),
        lambda definition: definition["spec"]["breachWhen"]["left"].update(
            {"ref": "missing.rate"}
        ),
        lambda definition: definition["spec"]["breachWhen"]["left"].update(
            {"ref": "invalid_orders.unknown"}
        ),
        lambda definition: definition["spec"]["breachWhen"]["right"].update(
            {"field": "also_invalid"}
        ),
        lambda definition: definition["spec"]["execution"].update(
            {"timeoutSeconds": 121}
        ),
        lambda definition: definition["spec"]["breachWhen"]["right"].update(
            {"literal": float("nan")}
        ),
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
    definition["spec"]["measurements"] = [
        {"id": "rows", "type": "metric", "metric": "row_count"}
    ]
    definition["spec"]["breachWhen"] = {
        "op": "eq",
        "left": {"ref": "rows"},
        "right": {"literal": 0},
    }

    model = MonitorDefinition.model_validate(definition)
    assert model.spec.measurements[0].metric == "row_count"


@pytest.mark.asyncio
async def test_validation_endpoint_resolves_tenant_asset_and_returns_plan():
    from app.routers.monitor_dsl import validate_monitor_definition

    table = SimpleNamespace(
        id=UUID(ASSET_ID),
        source_id="source-1",
        schema_name="public",
        table_name="orders",
        dbt_model_yaml=(
            "CREATE TABLE public.orders ("
            "status text NULL, payment_reference text NULL"
            ");"
        ),
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
        "activationSupported": False,
        "activationBlockers": [
            "dsl_run_persistence_not_implemented",
            "dsl_policy_evaluation_not_implemented",
        ],
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
    body["spec"]["measurements"] = [
        {"id": "average", "type": "metric", "metric": "mean", "field": "amount"}
    ]
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
    assert response["capabilityPlan"]["issues"][0]["message"] == (
        "mean does not support amount (string)"
    )


@pytest.mark.asyncio
async def test_preview_returns_bound_plan_without_enabling_execution():
    from app.routers.monitor_dsl import preview_monitor_definition

    table = SimpleNamespace(
        id=UUID(ASSET_ID),
        schema_name="public",
        table_name="orders",
        dbt_model_yaml=(
            "CREATE TABLE public.orders ("
            "status text NULL, payment_reference text NULL"
            ");"
        ),
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
    assert response["capabilityPlan"]["activationSupported"] is False
    assert response["capabilityPlan"]["activationBlockers"] == [
        "dsl_run_persistence_not_implemented",
        "dsl_policy_evaluation_not_implemented",
    ]


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
    body["spec"]["measurements"] = [
        {"id": "average", "type": "metric", "metric": "mean", "field": "amount"}
    ]
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
