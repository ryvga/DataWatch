# Monitor Builder Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn AI recommendations, Natural Language Rule Builder, and custom monitor creation into one tested workflow where users can generate SQL checks, test them, save them as custom monitors, and see them in the UI.

**Architecture:** Keep custom monitors backed by the existing `custom_monitors` API. Add frontend SQL synthesis for recommendation types that can be represented as SQL count checks, gate monitor saving on a successful SQL test, and refresh the custom monitor list after any save. Verification uses Playwright against the running tenant app with network mocking for AI recommendation responses.

**Tech Stack:** React 18, Vite, FastAPI existing APIs, Playwright Chromium, Docker Compose dev stack.

---

## File Map

- `src/pages/TableDetail.jsx`: AI recommendation save flow, editable NL SQL, table-level custom monitor test-before-save.
- `src/pages/Monitors.jsx`: global custom monitor modal test-before-save.
- `src/api/endpoints.js`: already has required custom monitor and custom check endpoints.
- `tests/playwright/monitor-builder.spec.mjs`: browser regression tests for recommendation save, NL edit/test/save, and `/monitors` modal test-before-save.
- `package.json`: add `test:e2e` script for the Playwright spec.

### Task 1: Add Failing Playwright Regression Tests

**Files:**
- Create: `tests/playwright/monitor-builder.spec.mjs`
- Modify: `package.json`

- [ ] **Step 1: Write the failing browser tests**

Create `tests/playwright/monitor-builder.spec.mjs` with tests that:
- log in to `acme-corp.localhost:5173`
- mock `POST /api/v1/sources/*/recommend-monitors` to return one `null_rate` recommendation
- click AI recommendation `Add monitor` and expect it to appear in `Custom SQL Monitors`
- generate an NL rule, edit the SQL textarea, test it, save it, and delete it
- open `/monitors`, open `Add monitor`, verify `Create monitor` is disabled until `Test SQL` succeeds

- [ ] **Step 2: Add the script**

Add this script to `package.json`:

```json
"test:e2e": "node tests/playwright/monitor-builder.spec.mjs"
```

- [ ] **Step 3: Run and verify RED**

Run: `npm run test:e2e`

Expected failures before implementation:
- AI recommendation does not create a custom monitor because it calls `createTable`.
- NL SQL is not editable because it renders as `<pre>`.
- `/monitors` add dialog has no `Test SQL` button and save is not test-gated.

### Task 2: Save AI Recommendations as Custom SQL Monitors

**Files:**
- Modify: `src/pages/TableDetail.jsx`

- [ ] **Step 1: Add SQL synthesis helpers**

Add helpers near the AI recommender:
- `quoteSqlIdent(identifier)` for safe identifier quoting.
- `tableParts(tableName)` to split `schema.table`.
- `recommendationSql(rec, tableName)` to return SQL for `null_rate`, `row_count`, `duplicate`, `freshness`, and `value_range` where possible.

- [ ] **Step 2: Replace `createTable` in `applyRec`**

`applyRec` should:
- synthesize SQL from the recommendation
- call `createCustomMonitor(tableId, { name, description, sql_query, severity, run_on_profile: true })`
- mark the recommendation added
- call `onMonitorSaved?.()` so the Custom SQL Monitors panel refreshes
- show a clear error for unsupported recommendation types

- [ ] **Step 3: Pass refresh callback**

Add `onMonitorSaved` prop to `AIMonitorRecommender` and pass the same `setCustomMonitorsRefreshKey` callback used by NL Rule Builder.

- [ ] **Step 4: Run focused browser test**

Run: `npm run test:e2e`

Expected: AI recommendation section proceeds past its previous failure.

### Task 3: Upgrade Natural Language Rule Builder

**Files:**
- Modify: `src/pages/TableDetail.jsx`

- [ ] **Step 1: Make generated SQL editable**

Add `sqlDraft` state. After generation, set it from `r.data.sql`. Replace the `<pre>` with a `<textarea aria-label="Generated SQL">` bound to `sqlDraft`.

- [ ] **Step 2: Make severity editable**

Add `severityDraft` state. After generation, set it from `r.data.severity || 'P3'`. Render a severity `<select>` next to impact.

- [ ] **Step 3: Gate save on tested SQL**

Track `lastTestedSql`. Clear `testResult` and `lastTestedSql` when SQL changes. Save button is disabled until `lastTestedSql === sqlDraft.trim()` and a test result exists.

- [ ] **Step 4: Use edited values**

`testSql` posts `{ sql: sqlDraft, name: rule, severity: severityDraft }`. `saveAsMonitor` saves `sql_query: sqlDraft`, `severity: severityDraft`, and preserves explanation/rule in description.

- [ ] **Step 5: Run focused browser test**

Run: `npm run test:e2e`

Expected: NL edit/test/save/delete passes.

### Task 4: Add Test-Before-Save to Custom Monitor Create Flows

**Files:**
- Modify: `src/pages/TableDetail.jsx`
- Modify: `src/pages/Monitors.jsx`

- [ ] **Step 1: Table page custom add form**

Add test state for the add form: `addTesting`, `addTestResult`, `addLastTestedSql`. Add `Test SQL` button next to `Save monitor`. Save disabled until current SQL was tested successfully or with a known violation count.

- [ ] **Step 2: Global `/monitors` modal**

Import `runCustomCheck`. Add `testing`, `testResult`, `lastTestedSql`. Reset test state when table or SQL changes. Add `Test SQL`; disable `Create monitor` until SQL was tested.

- [ ] **Step 3: Run focused browser test**

Run: `npm run test:e2e`

Expected: `/monitors` modal test-before-save passes.

### Task 5: Final Verification

**Files:** all modified files.

- [ ] **Step 1: Build frontend**

Run: `npm run build`

Expected: Vite build exits 0.

- [ ] **Step 2: Run Playwright regression**

Run: `npm run test:e2e`

Expected: all browser checks pass and no temporary monitors remain.

- [ ] **Step 3: Verify stack route manually with Playwright summary**

Run the Playwright spec output and check it reports:
- AI recommendation monitor saved/deleted
- NL monitor saved/deleted
- global monitor modal save was gated until test

