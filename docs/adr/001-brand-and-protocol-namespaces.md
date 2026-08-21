# ADR 001 — Product brand and protocol namespaces

## Status

Accepted — 2026-08-21

## Context

The user-facing product and production domain moved from DataWatch/datawatch.io to Panopta/panopta.app. Some tests and operational documentation still used the old host, while the safe-monitor API already used `datawatch.io/v1alpha1` as a machine protocol identifier.

Changing a versioned protocol identifier would invalidate stored definitions, hashes, attestations, examples, and external integrations. A product brand and a protocol namespace have different compatibility requirements.

## Decision

- The user-facing product name is **Panopta**.
- The production web domain is **panopta.app**, configured through `BASE_DOMAIN` and `VITE_BASE_DOMAIN`.
- DataWatch remains the internal engine/repository name and academic project lineage.
- `datawatch.io/v1alpha1` remains the stable safe-monitor protocol namespace. It is an identifier, not a navigable product-domain claim.
- Runtime URLs and tests must derive hostnames from configuration rather than hard-code either domain.

## Consequences

- UI, email defaults, billing callbacks, demo accounts, and deployment documentation use Panopta/panopta.app.
- API/DSL documentation may continue to show `datawatch.io/v1alpha1` only when describing the versioned protocol.
- A future protocol rename requires an explicit version/migration strategy and must preserve canonical hashes for existing revisions.
