import json
import subprocess
import sys
from pathlib import Path

from app.connectors.factory import CONNECTOR_REGISTRY, ConnectorFactory

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = REPOSITORY_ROOT / "docs" / "evidence" / "connector-capabilities.generated.json"


def test_registry_contains_no_hand_maintained_capability_claims():
    assert all("capabilities" not in entry for entry in CONNECTOR_REGISTRY.values())


def test_generated_capability_artifact_is_current():
    result = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "backend" / "scripts" / "generate_connector_capabilities.py"),
            "--check",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    artifact = json.loads(ARTIFACT.read_text())
    public_matrix = {item["type"]: item["capabilities"] for item in ConnectorFactory.supported_types()}
    generated_matrix = {
        source_type: entry["capabilities"]
        for source_type, entry in artifact["connectors"].items()
    }
    assert generated_matrix == public_matrix
