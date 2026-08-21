"""Generate or verify the connector capability artifact from executable contracts."""

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
OUTPUT_PATH = REPOSITORY_ROOT / "docs" / "evidence" / "connector-capabilities.generated.json"
sys.path.insert(0, str(BACKEND_ROOT))

from app.connectors.factory import (  # noqa: E402
    CONNECTOR_REGISTRY,
    _connector_class,
    derive_connector_capabilities,
)


def build_matrix() -> dict:
    connectors = {}
    for source_type, registry_entry in CONNECTOR_REGISTRY.items():
        connector_class = _connector_class(source_type)
        connectors[source_type] = {
            "class": connector_class.__name__,
            "readiness": registry_entry["readiness"],
            "profile_dialect": connector_class.profile_dialect,
            "monitor_dialect": connector_class.monitor_dialect,
            "native_profile_kind": connector_class.native_profile_kind,
            "capabilities": derive_connector_capabilities(connector_class),
        }
    return {
        "schema_version": 1,
        "generator": "backend/scripts/generate_connector_capabilities.py",
        "generated_from": "executable connector method overrides and dialect declarations",
        "ci_gate": "full backend suite with REQUIRE_TEST_SERVICES=1 and no silent integration skips",
        "connectors": connectors,
    }


def serialized_matrix() -> str:
    return json.dumps(build_matrix(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if the artifact is stale")
    args = parser.parse_args()
    expected = serialized_matrix()
    if args.check:
        if not OUTPUT_PATH.exists() or OUTPUT_PATH.read_text() != expected:
            print(f"stale connector capability artifact: {OUTPUT_PATH}", file=sys.stderr)
            return 1
        return 0
    OUTPUT_PATH.write_text(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
