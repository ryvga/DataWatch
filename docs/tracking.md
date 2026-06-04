# DataWatch — Tracking Rules (Linear + Notion)

> This document is **mandatory reading** before starting any work session.
> DataWatch is a PFE (final-year thesis) project. Every decision, problem, and measurement
> feeds into the written rapport and jury defense. Nothing gets lost — log it.

---

## Why Tracking Matters

The written rapport needs:
- Architecture justification (why these tech choices)
- Proof of difficulty (what broke, how it was solved)
- Performance evidence (real numbers, not estimates)
- ML methodology (why z-score + IsoForest + STL, what you observed)
- LLM engineering (prompt iterations, what worked, what didn't)

If it's not in Notion, it didn't happen (as far as the jury is concerned).

---

## Linear — Project Management

**URL:** https://linear.app/mounir-gaiby/project/datawatch-77f9ab167670
**Team:** Mounir Gaiby | **Prefix:** `MOU-`

### Ticket States

| State | Meaning | When to set |
|---|---|---|
| Backlog | Not started | Default |
| In Progress | Currently being worked on | When you start a session on this ticket |
| Done | Fully shipped | When code is working, tested, and logged to Notion |

### Rules

1. **Only one ticket In Progress at a time.** If you switch context, move the old ticket back to Backlog or forward to Done.
2. **Move to Done = code works + tests pass + Notion updated.** Not before.
3. **Never work on something without a ticket.** If it's not in Linear, create a ticket first.
4. **Bug fixes get their own ticket** if they take > 30 minutes.

### Ticket Naming

- Feature tickets: `Day N — Short Title` or descriptive name
- Bug tickets: `[BUG] Short description of the broken behavior`
- Improvement: `[IMPROVE] What + where`

---

## Notion — Documentation Hub

**Hub:** https://app.notion.com/p/374cb96c4e1c81af9989e9fafb3e2f7a

### Pages and What Goes Where

---

### 📊 7-Day Build Log
**URL:** https://app.notion.com/p/374cb96c4e1c813686f6c77c3612bcea

The primary day-by-day progress record. Update this **at the end of every work session** — not the next day.

Each day entry has 5 sections:

**✅ Done** — Specific deliverables. Not "worked on profiler" but "implemented single-query profiler that computes 10 metrics in one SQL aggregate — verified with EXPLAIN ANALYZE on 1M row table."

**🧠 Decisions Made** — Every non-obvious choice, even small ones. Format: *"Used X instead of Y because Z. Considered also W but rejected because..."*

**🔥 Problems & Solutions** — Paste the actual error message. Describe the fix. Note what you learned. These sections write your "Difficultés" rapport chapter.

**📏 Numbers Measured** — Real measurements only. Examples:
- Profile query on 500k rows: 340ms
- LLM API latency: p50=2.1s, p95=4.8s
- Redis discovery cache hit rate: 94%
- Test suite duration: 8.2s

**💡 Rapport Notes** — Anything worth highlighting to the jury. Interesting findings, clever design choices, surprising behaviors.

---

### 📄 Rapport & Presentation Material
**URL:** https://app.notion.com/p/374cb96c4e1c8126853bc980cbde78e6

The source material for writing the rapport. Contains sub-pages:

**Technical Decisions Log** (table: Decision | Alternatives Considered | Rationale | Day)
- Log every architecture or design decision here
- Example entries:
  - "Single aggregate SQL query per profile" | "Multiple queries / pandas" | "Avoids N+1, 10x faster on large tables" | Day 3
  - "HKDF per-org Fernet key" | "Single shared key" | "Cross-org decryption impossible even if master leaks" | Day 2
  - "APScheduler MemoryJobStore" | "SQLAlchemyJobStore" | "Avoids async/sync SQLAlchemy mismatch" | Day 6

**Problems & Solutions** (by day)
- Mirror of Build Log problems section, but here add more detail
- Include: exact error, root cause, what you tried first, final fix

**Performance Measurements**
- Profile query times at different table sizes
- LLM API latency distribution
- API response times (p50/p95 for key endpoints)
- Redis cache hit rates
- Celery task throughput

**ML Observations**
- Z-score: what threshold value works best and why
- IsoForest: contamination parameter sensitivity
- STL: which tables showed seasonality
- False positive rates during demo testing

**LLM Prompt Iterations**
- Each prompt version + what changed + why
- Sample outputs for pipeline_failure, null_spike, schema_drift scenarios
- Token count per context assembly

**Code Highlights**
- Code snippets for rapport appendix
- The single aggregate SQL query builder
- HKDF key derivation
- The incident deduplication logic

**Rapport Sections Status**
- Table tracking which chapters are drafted / reviewed / done

---

### 🏗️ Architecture & Technical Design
**URL:** https://app.notion.com/p/374cb96c4e1c818b9c54dd576d209d9c

For Architecture Decision Records (ADRs) and system design diagrams.

Format for each ADR:
```
Title: [short name]
Status: Accepted | Superseded
Context: What problem we were solving
Decision: What we chose
Consequences: What this implies going forward
Alternatives Rejected: What we didn't choose and why
```

---

### 🎭 Demo Script & Jury Prep
**URL:** https://app.notion.com/p/374cb96c4e1c81c6911bf6040b81cef1

The exact sequence of steps for the jury demo. Keep this up to date as the demo evolves.

**Contents:**
- Pre-demo setup checklist (seed data, API keys, DB state)
- Demo script step-by-step (what to click, what to say)
- Expected outputs at each step
- Fallback plan if something fails during demo
- Likely jury questions + prepared answers

---

### 🎓 Academic Defense Angles
**URL:** https://app.notion.com/p/374cb96c4e1c8120a8f8c5ebffa5fa79

For the oral defense preparation:
- How to frame each technical choice academically
- References and papers for detection methods (Z-score, Isolation Forest, STL)
- Comparison with existing tools (Monte Carlo, Great Expectations, dbt tests)
- Limitations to acknowledge proactively
- Future work section

---

## Tracking Workflow Per Work Session

### Starting a session

```
1. Open Linear → move ticket to In Progress
2. Open Notion 7-Day Build Log → note what you're starting under today's date
3. Start a timer (optional but useful for measuring actual time)
```

### During the session

```
- When something breaks: immediately note the error in Notion (copy-paste, don't paraphrase)
- When you make a non-obvious decision: note it in Decisions Made
- When you measure something: write the exact number down immediately
```

### Ending a session

```
1. Fill in Build Log:
   - Done: specific things shipped
   - Decisions: what you chose and why
   - Problems: what broke and how you fixed it
   - Numbers: any latency/throughput/token-count measurements
   - Rapport Notes: anything worth highlighting

2. If the decision is architecture-level → also log to Rapport Material → Technical Decisions Log

3. Move Linear ticket to Done (if complete) or leave In Progress (if continuing)

4. Commit with proper format (see docs/development.md)
```

---

## Rapport Chapter → Source Mapping

When writing the rapport, pull content from:

| Rapport Chapter | Notion Source |
|---|---|
| Introduction / Contexte | Hub + Architecture page |
| Architecture technique | Architecture page + ADRs + Technical Decisions Log |
| Difficultés rencontrées | Problems & Solutions + Build Log daily problems |
| Résultats et mesures | Performance Measurements table |
| Détection d'anomalies | ML Observations + Architecture page detection section |
| LLM engineering | LLM Prompt Iterations + test_llm_prompt.py outputs |
| Conclusion / Perspectives | Demo Script + Academic Defense page |
| Annexes — code | Code Highlights + relevant source files |

---

## What Must Always Be Logged

Non-negotiable — if you do any of these, log it:

| Event | Where to log |
|---|---|
| New connector implemented | Build Log + Technical Decisions (why this library?) |
| Detection algorithm added/tuned | Build Log + ML Observations (what threshold, why?) |
| LLM prompt changed | LLM Prompt Iterations (old vs new, what improved) |
| Performance measured | Performance Measurements (exact numbers, table size, hardware) |
| Bug took > 20 minutes to fix | Problems & Solutions (error message + root cause + fix) |
| Architecture decision made | Technical Decisions Log (ADR format) |
| Surprising behavior observed | Rapport Notes in Build Log |
