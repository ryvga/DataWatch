# Connector Matrix Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repeatable integration suite that proves DataWatch can connect to SQL, NoSQL, and warehouse-style demo sources and exercise core monitor workflows through the public API.

**Architecture:** Use the existing Docker Compose stack for the application, demo PostgreSQL database, and analytics PostgreSQL warehouse. Add a Compose overlay for a seeded MongoDB NoSQL source, then run a Python standard-library API matrix that logs in, tests source connections, discovers schemas, reads schema DDL, creates/runs/deletes a custom monitor, and cleans up temporary sources.

**Tech Stack:** Docker Compose, FastAPI HTTP endpoints, PostgreSQL demo sources, MongoDB 7 test source, Python 3 standard library.

---

### Task 1: API Matrix Runner

**Files:**
- Create: `scripts/run_connector_matrix.py`

- [x] **Step 1: Write a runner that fails without the Mongo test DB**

Run: `python3 scripts/run_connector_matrix.py`
Expected: FAIL on the MongoDB preview connection until `test-mongo` is available.

- [x] **Step 2: Implement the matrix assertions**

The runner must verify:
- JWT login for `acme-corp`
- connector metadata includes `postgres`, `mongodb`, and `duckdb`
- preview connections for `demo-db`, `analytics-db`, and `test-mongo`
- source discovery and schema DDL for existing demo SQL and warehouse sources
- temporary Mongo source create/discover/schema/read/delete
- custom monitor create/run/delete on table `3856dac6-46a1-462b-a8ce-f6c1de0d983e`

### Task 2: Seeded NoSQL Test Database

**Files:**
- Create: `docker-compose.test-dbs.yml`
- Create: `scripts/test_dbs/mongo_seed.js`

- [x] **Step 1: Add MongoDB test service**

Run: `docker compose -f docker-compose.yml -f docker-compose.test-dbs.yml up -d test-mongo`
Expected: Mongo starts on the app Compose network and is reachable as `test-mongo:27017` from the API container.

- [x] **Step 2: Seed realistic NoSQL events**

Seed `datawatch_nosql.events` with nested documents, optional fields, nulls, and mixed event types so schema inference has meaningful fields.

### Task 3: Verification And Commit

**Files:**
- Modify only test/plan/support files.

- [x] **Step 1: Run connector matrix**

Run: `python3 scripts/run_connector_matrix.py`
Expected: PASS with all matrix checks completed.

- [x] **Step 2: Run existing verification**

Run frontend build, frontend Playwright regression, and backend pytest smoke suite.

- [x] **Step 3: Commit atomically**

Commit message: `test(integration): add connector matrix suite`
