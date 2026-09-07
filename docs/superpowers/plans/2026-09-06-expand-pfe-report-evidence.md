# DataWatch PFE Evidence Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a longer French PFE report that documents every material DataWatch feature with readable screenshots, domain-specific UML, an exhaustive database view, and a professional June-to-August Gantt chart.

**Architecture:** Preserve the existing deterministic Word builder and add three evidence pipelines around it: live browser capture, reproducible diagram generation, and database inventory export. Keep overview diagrams in the body and exhaustive schema/data material in annexes so the A4 document remains readable.

**Tech Stack:** Python 3.12, python-docx, Playwright, Graphviz, Matplotlib, PostgreSQL, LibreOffice, Poppler.

---

### Task 1: Create the global human writing skill

**Files:**
- Create: `/Users/mounir/.codex/skills/human-voice-writing/SKILL.md`
- Create: `/Users/mounir/.codex/skills/human-voice-writing/agents/openai.yaml`

- [x] **Step 1: Initialize the skill**

Run the skill creator initializer with the global Codex skills directory.

Expected: a discoverable `human-voice-writing` skill with no unused resource folders.

- [x] **Step 2: Replace the scaffold with the writing contract**

The contract must require specific nouns and verbs, mixed sentence lengths, evidence-backed numbers, visible limitations, and removal of stock AI transitions. It must also prohibit fabricated specificity and protect readability in academic or legal prose.

- [x] **Step 3: Validate the skill**

Run `quick_validate.py /Users/mounir/.codex/skills/human-voice-writing`.

Expected: validation succeeds with no scaffold markers.

### Task 2: Export database structure and seeded evidence

**Files:**
- Create: `scripts/pfe/export_database_evidence.py`
- Create: `docs/pfe/database_evidence.json`

- [x] **Step 1: Export the SQLAlchemy metadata**

Serialize all twenty-nine application tables, primary keys, foreign keys, significant columns, types and nullability. Reject secrets and encrypted connection values from sample output.

- [x] **Step 2: Query the seeded PostgreSQL database**

Record row counts and selected non-sensitive examples for the Acme demonstration workspace.

- [x] **Step 3: Validate completeness**

Assert that the exported table set matches `Base.metadata.tables` and that every table has a documented responsibility.

### Task 3: Replace and expand report diagrams

**Files:**
- Create: `scripts/pfe/generate_report_visuals.py`
- Create or update: `docs/diagrams/pfe/*.dot`
- Create or update: `docs/diagrams/pfe/*.svg`
- Create or update: `docs/diagrams/pfe/*-doc.png`

- [x] **Step 1: Generate the dated Gantt chart**

Render a horizontal timeline from 1 June through 31 August 2026 with sprint bars, milestone markers and an ongoing-product lane extending beyond the PFE boundary.

- [x] **Step 2: Generate use case and activity diagrams**

Create global, organization-operator and staff use-case views plus the incident lifecycle activity diagram.

- [x] **Step 3: Generate sequence diagrams**

Create separate diagrams for source onboarding, scheduled detection, operator investigation and observe-only AI governance.

- [x] **Step 4: Generate architecture and class diagrams**

Create logical layers, Docker deployment, monitoring classes, collaboration classes, typed-monitor classes and AI-governance classes.

- [x] **Step 5: Generate database diagrams**

Create one complete twenty-nine-table relationship map and readable detailed maps for core monitoring, identity/collaboration and AI governance.

- [x] **Step 6: Render and inspect every diagram**

Confirm every generated image remains readable at the physical width used in the A4 report.

### Task 4: Expand live application screenshots

**Files:**
- Modify: `frontend/tests/playwright/capture-pfe-report.mjs`
- Create: `docs/screenshots/pfe/*-report.png`
- Modify: `docs/pfe/DEMO_RECORDING_FLOW.md`

- [x] **Step 1: Capture the workspace entry and overview**

Capture login and Operations after the real seed has finished.

- [x] **Step 2: Capture monitoring and incident workflows**

Capture Tables, table detail, monitor recommendations, monitor builder, monitor catalogue, incident list, incident facts and AI narration.

- [x] **Step 3: Capture organization features**

Capture Reports, Teams, data sources, connector catalogue, alert routes and notification preferences.

- [x] **Step 4: Capture AI governance and staff administration**

Capture AI systems, one detailed evidence view, staff statistics, organizations and one organization detail page.

- [x] **Step 5: Verify capture quality**

Reject loading skeletons, browser errors, clipped dialogs, secrets and empty states that contradict the seed.

### Task 5: Expand the French report

**Files:**
- Modify: `scripts/pfe/build_rapport_word.py`
- Modify: `docs/pfe/report_source.json`
- Modify: `docs/pfe/REPORT_BUILD.md`
- Modify: `output/pfe/Rapport_PFE_DataWatch_Mounir_Gaiby.docx`

- [x] **Step 1: Extend Chapter 1 planning**

Describe the three-month PFE window and the product continuation after August; insert the new Gantt figure.

- [x] **Step 2: Extend Chapter 3 analysis and design**

Add numbered subsections and prose around each use-case, sequence, activity, architecture, class and database figure.

- [x] **Step 3: Extend Chapter 4 interface coverage**

Add every verified screenshot with a numbered caption and a paragraph that interprets the visible evidence.

- [x] **Step 4: Add exhaustive database annexes**

Add the twenty-nine-table dictionary, relationships, seeded row counts and non-sensitive sample data.

- [x] **Step 5: Apply the human writing contract**

Rewrite generic passages with uneven but controlled cadence, concrete details, direct claims and nearby limits. Preserve the French academic register and all factual qualifiers.

- [x] **Step 6: Rebuild the native indexes**

Update the Word table of contents, list of figures and list of tables without synthetic continuation paragraphs.

### Task 6: Render, audit and publish

**Files:**
- Update: `tmp/pfe/report-page-map.json`
- Verify: `output/pfe/Rapport_PFE_DataWatch_Mounir_Gaiby.docx`

- [x] **Step 1: Stabilize page numbers**

Build, render, extract the page map, then rebuild and render again.

- [x] **Step 2: Inspect every rendered page**

Confirm figure scale, caption pairing, page breaks, Roman preliminaries, Arabic body numbering, table headers and appendix readability.

- [x] **Step 3: Run structural checks**

Run the accessibility audit, validate one balanced Word TOC field, compile the generation scripts and run `git diff --check`.

- [x] **Step 4: Commit and push**

Commit the report, reproducible sources, captures and evidence manifest, then push the current main branch as previously requested for cross-computer continuation.
