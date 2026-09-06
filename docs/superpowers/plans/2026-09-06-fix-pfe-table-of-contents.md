# PFE Table of Contents Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore a clean, genuinely updateable Word table of contents without the synthetic continuation row that corrupts the field result.

**Architecture:** Keep one continuous Word `TOC` field and its deterministic cached hyperlinks. Let Word and the renderer paginate the entries naturally; preserve the existing Roman-numbered preliminary section and Arabic-numbered report body.

**Tech Stack:** Python, python-docx, WordprocessingML, LibreOffice PDF rendering, Poppler inspection tools.

---

### Task 1: Remove the invalid continuation entry

**Files:**
- Modify: `scripts/pfe/build_rapport_word.py`

- [x] **Step 1: Delete the special `level == -1` rendering branch**

Remove the paragraph that forces a page break from inside the cached result of the native Word `TOC` field.

- [x] **Step 2: Delete the synthetic Chapter 3 continuation entry**

Remove `("V. Table des matières — suite", "", None, -1)` so every cached result is a real heading or preliminary-section link.

### Task 2: Rebuild and stabilize pagination

**Files:**
- Modify: `output/pfe/Rapport_PFE_DataWatch_Mounir_Gaiby.docx`
- Update: `tmp/pfe/report_page_map.json`

- [x] **Step 1: Build the report with the existing page map**

Run: `python scripts/pfe/build_rapport_word.py`

Expected: the DOCX is generated successfully.

- [x] **Step 2: Render the DOCX and extract the definitive page map**

Run the document renderer, then `python scripts/pfe/extract_report_page_map.py` against the rendered PDF.

Expected: the table of contents occupies two continuous pages and the body begins on Arabic page 1.

- [x] **Step 3: Rebuild once with definitive page numbers**

Run the builder and renderer again.

Expected: cached table-of-contents links show the final page numbers.

### Task 3: Verify the repaired deliverable

**Files:**
- Verify: `output/pfe/Rapport_PFE_DataWatch_Mounir_Gaiby.docx`

- [x] **Step 1: Inspect the table-of-contents pages visually**

Confirm there is no synthetic continuation title, no clipped entry, no blank table-of-contents page, and no overlap.

- [x] **Step 2: Audit the DOCX structure**

Run the document accessibility/structure audit and inspect `word/document.xml` for one balanced `TOC` field.

Expected: one field begin, one separator, one field end, and no text matching `Table des matières — suite`.

- [x] **Step 3: Check the repository diff**

Run: `git diff --check`

Expected: no whitespace errors.
