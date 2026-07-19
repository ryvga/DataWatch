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

    table = SimpleNamespace(id=UUID(ASSET_ID), source_id="source-1")
    source = SimpleNamespace(id="source-1", type="postgres")

    class Database:
        async def execute(self, statement):
            class Result:
                def one_or_none(self):
                    return (table, source)

            return Result()

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
        "compatible": False,
        "unsupported": ["dsl_compiler_not_implemented"],
        "activationSupported": False,
    }
