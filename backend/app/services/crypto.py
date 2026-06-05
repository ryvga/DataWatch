"""
Credential encryption using Fernet with HKDF-derived per-org keys.

Design: HKDF(master_key, salt=org_id, info=b"datawatch-creds")
- Even if the master key leaks, cross-org decryption is prevented because
  each org gets a unique derived key.
- Master key from FERNET_MASTER_KEY env var (base64url-encoded 32 bytes).
"""
import base64
import json

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import settings


def _derive_key(org_id: str) -> bytes:
    """Derive a 32-byte Fernet key from master key + org_id via HKDF."""
    master = base64.urlsafe_b64decode(settings.FERNET_MASTER_KEY)
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=org_id.encode(),
        info=b"datawatch-creds",
    )
    raw_key = hkdf.derive(master)
    return base64.urlsafe_b64encode(raw_key)


def encrypt_config(config: dict, org_id: str) -> str:
    """JSON-serialize config, encrypt with org-derived key, return base64 string."""
    key = _derive_key(org_id)
    f = Fernet(key)
    return f.encrypt(json.dumps(config).encode()).decode()


def decrypt_config(encrypted: str, org_id: str) -> dict:
    """Decrypt and JSON-deserialize config."""
    key = _derive_key(org_id)
    f = Fernet(key)
    return json.loads(f.decrypt(encrypted.encode()).decode())


class CryptoService:
    """Instance-based helper for encrypting/decrypting per-org secrets."""

    def encrypt_for_org(self, value: str, org_id: str) -> str:
        key = _derive_key(org_id)
        return Fernet(key).encrypt(value.encode()).decode()

    def decrypt_for_org(self, encrypted: str, org_id: str) -> str:
        key = _derive_key(org_id)
        return Fernet(key).decrypt(encrypted.encode()).decode()
