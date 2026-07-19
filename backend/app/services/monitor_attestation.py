"""Short-lived HMAC attestations for validated monitor previews."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from app.config import settings
from app.services.monitor_compiler import PLANNER_VERSION

ATTESTATION_VERSION = 1
DEFAULT_TTL_SECONDS = 300


class AttestationError(ValueError):
    """The preview token is malformed, invalid, expired, or context-mismatched."""


@dataclass(frozen=True)
class AttestationClaims:
    org_id: str
    asset_id: str
    definition_hash: str
    schema_fingerprint: str | None
    planner_version: str
    issued_at: int
    expires_at: int


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(value + padding, altchars=b"-_", validate=True)


def create_preview_attestation(
    *,
    org_id: str,
    asset_id: str,
    definition_hash: str,
    schema_fingerprint: str | None,
    now: int | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> tuple[str, AttestationClaims]:
    if ttl_seconds < 30 or ttl_seconds > 900:
        raise ValueError("Attestation TTL must be between 30 and 900 seconds")
    issued_at = int(time.time() if now is None else now)
    claims = AttestationClaims(
        org_id=str(org_id),
        asset_id=str(asset_id),
        definition_hash=definition_hash,
        schema_fingerprint=schema_fingerprint,
        planner_version=PLANNER_VERSION,
        issued_at=issued_at,
        expires_at=issued_at + ttl_seconds,
    )
    payload = {
        "v": ATTESTATION_VERSION,
        "org": claims.org_id,
        "asset": claims.asset_id,
        "hash": claims.definition_hash,
        "schema": claims.schema_fingerprint,
        "planner": claims.planner_version,
        "iat": claims.issued_at,
        "exp": claims.expires_at,
    }
    encoded_payload = _encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_encode(signature)}", claims


def verify_preview_attestation(
    token: str,
    *,
    org_id: str,
    asset_id: str,
    definition_hash: str,
    schema_fingerprint: str | None,
    now: int | None = None,
) -> AttestationClaims:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        supplied_signature = _decode(encoded_signature)
        expected_signature = hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise AttestationError("Preview attestation signature is invalid")
        payload = json.loads(_decode(encoded_payload))
        claims = AttestationClaims(
            org_id=str(payload["org"]),
            asset_id=str(payload["asset"]),
            definition_hash=str(payload["hash"]),
            schema_fingerprint=payload.get("schema"),
            planner_version=str(payload["planner"]),
            issued_at=int(payload["iat"]),
            expires_at=int(payload["exp"]),
        )
        if payload.get("v") != ATTESTATION_VERSION:
            raise AttestationError("Preview attestation version is unsupported")
    except AttestationError:
        raise
    except Exception as exc:
        raise AttestationError("Preview attestation is malformed") from exc

    current_time = int(time.time() if now is None else now)
    if claims.expires_at <= current_time:
        raise AttestationError("Preview attestation has expired")
    if claims.issued_at > current_time + 30:
        raise AttestationError("Preview attestation issue time is invalid")
    expected = (
        str(org_id),
        str(asset_id),
        definition_hash,
        schema_fingerprint,
        PLANNER_VERSION,
    )
    actual = (
        claims.org_id,
        claims.asset_id,
        claims.definition_hash,
        claims.schema_fingerprint,
        claims.planner_version,
    )
    if not hmac.compare_digest(
        json.dumps(actual, separators=(",", ":")),
        json.dumps(expected, separators=(",", ":")),
    ):
        raise AttestationError("Preview attestation does not match current monitor context")
    return claims
