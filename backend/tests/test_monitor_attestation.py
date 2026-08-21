import pytest

from app.services.monitor_attestation import (
    ATTESTATION_VERSION,
    PLANNER_VERSION,
    AttestationError,
    create_preview_attestation,
    verify_preview_attestation,
)


def _claims(token: str, *, now: int = 1_000):
    return verify_preview_attestation(
        token,
        org_id="org-1",
        asset_id="asset-1",
        definition_hash="a" * 64,
        schema_fingerprint="schema-1",
        now=now,
    )


def test_preview_attestation_is_bound_to_full_context_and_expiry():
    token, issued = create_preview_attestation(
        org_id="org-1",
        asset_id="asset-1",
        definition_hash="a" * 64,
        schema_fingerprint="schema-1",
        now=1_000,
        ttl_seconds=60,
    )

    verified = _claims(token)
    assert verified == issued
    assert verified.planner_version == PLANNER_VERSION
    assert PLANNER_VERSION == "datawatch-v1alpha1-relational-2"
    assert verified.expires_at == 1_060
    assert ATTESTATION_VERSION == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"org_id": "org-2"},
        {"asset_id": "asset-2"},
        {"definition_hash": "b" * 64},
        {"schema_fingerprint": "schema-2"},
    ],
)
def test_preview_attestation_rejects_context_changes(overrides):
    token, _ = create_preview_attestation(
        org_id="org-1",
        asset_id="asset-1",
        definition_hash="a" * 64,
        schema_fingerprint="schema-1",
        now=1_000,
        ttl_seconds=60,
    )
    expected = {
        "org_id": "org-1",
        "asset_id": "asset-1",
        "definition_hash": "a" * 64,
        "schema_fingerprint": "schema-1",
        "now": 1_000,
    }
    expected.update(overrides)
    with pytest.raises(AttestationError, match="does not match"):
        verify_preview_attestation(token, **expected)


def test_preview_attestation_rejects_tampering_and_expiry():
    token, _ = create_preview_attestation(
        org_id="org-1",
        asset_id="asset-1",
        definition_hash="a" * 64,
        schema_fingerprint="schema-1",
        now=1_000,
        ttl_seconds=60,
    )
    payload, signature = token.split(".")
    tampered = f"{payload[:-1]}A.{signature}"

    with pytest.raises(AttestationError, match="signature"):
        _claims(tampered)
    with pytest.raises(AttestationError, match="expired"):
        _claims(token, now=1_060)


def test_preview_attestation_rejects_invalid_ttl():
    with pytest.raises(ValueError, match="between 30 and 900"):
        create_preview_attestation(
            org_id="org-1",
            asset_id="asset-1",
            definition_hash="a" * 64,
            schema_fingerprint=None,
            ttl_seconds=10,
        )


def test_preview_attestation_is_bound_to_native_planner_version():
    native_version = "datawatch-v1alpha1-mongodb-1"
    token, _ = create_preview_attestation(
        org_id="org-1",
        asset_id="asset-1",
        definition_hash="a" * 64,
        schema_fingerprint="schema-1",
        planner_version=native_version,
        now=1_000,
        ttl_seconds=60,
    )
    verified = verify_preview_attestation(
        token,
        org_id="org-1",
        asset_id="asset-1",
        definition_hash="a" * 64,
        schema_fingerprint="schema-1",
        planner_version=native_version,
        now=1_000,
    )
    assert verified.planner_version == native_version

    with pytest.raises(AttestationError, match="does not match"):
        verify_preview_attestation(
            token,
            org_id="org-1",
            asset_id="asset-1",
            definition_hash="a" * 64,
            schema_fingerprint="schema-1",
            planner_version=PLANNER_VERSION,
            now=1_000,
        )
