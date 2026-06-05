"""
LLMService — context assembly + OpenRouter narration + Pydantic validation + Redis caching.

Model:    configurable via LLM_MODEL env var (default: nvidia/nemotron-3-ultra-550b-a55b:free)
Provider: OpenRouter (OpenAI-compatible API at LLM_BASE_URL)
Tokens:   max_tokens=1024, temperature=0
Cache:    Redis key llm:incident:{id}, TTL=24h
Retry:    1 retry with validation-error hint on bad JSON
"""
import json
import logging
from typing import Literal

import redis
from openai import OpenAI
from pydantic import BaseModel, ValidationError, field_validator

from app.config import settings

logger = logging.getLogger(__name__)

# ── Pydantic output schema ─────────────────────────────────────────────────────

class LikelyCause(BaseModel):
    hypothesis: str
    probability: Literal["high", "medium", "low"]


class NarrationResult(BaseModel):
    summary: str
    likely_causes: list[LikelyCause]
    impact_assessment: str
    recommended_actions: list[str]
    data_pattern_notes: str
    confidence: Literal["high", "medium", "low"]

    @field_validator("summary")
    @classmethod
    def summary_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("summary must not be empty")
        return v[:500]

    @field_validator("likely_causes")
    @classmethod
    def causes_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("likely_causes must have at least one entry")
        return v[:5]

    @field_validator("recommended_actions")
    @classmethod
    def actions_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("recommended_actions must have at least one entry")
        return v[:8]


# ── Prompts ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a senior data reliability engineer. You have deep expertise in SQL databases, \
data pipelines, and incident investigation. You write in plain English — specific about \
numbers, times, and table names. You always suggest exact debug queries the team can run.

You are given information about a data quality incident detected in a production database. \
Generate a clear, actionable incident report.

Always respond with valid JSON matching this exact schema — no preamble, no markdown:
{
  "summary": "one sentence plain English description of what happened, with exact numbers",
  "likely_causes": [
    {"hypothesis": "specific technical cause mentioning the table/column/system", "probability": "high|medium|low"}
  ],
  "impact_assessment": "what business processes, dashboards, or downstream systems are affected",
  "recommended_actions": [
    "concrete step 1 (e.g. 'Run: SELECT COUNT(*) FROM orders WHERE ...')",
    "concrete step 2"
  ],
  "debug_queries": [
    "SELECT * FROM table WHERE column IS NULL AND created_at >= NOW() - INTERVAL '24 hours' LIMIT 100",
    "SELECT date_trunc('hour', created_at), COUNT(*) FROM table GROUP BY 1 ORDER BY 1 DESC LIMIT 48"
  ],
  "client_safe_summary": "1-2 sentence business summary with no internal table names or technical details",
  "data_pattern_notes": "notable trend in historical data that explains or contextualizes the anomaly",
  "confidence": "high|medium|low"
}

Rules:
- summary MUST mention the specific table, column, and metric values (e.g. 'null_rate 0.8% → 18.4%')
- likely_causes: 2-3 entries, most probable first, each hypothesis must be specific
- recommended_actions: 3-5 actionable steps — at least one must be a runnable SQL query
- debug_queries: 2-4 SQL queries an engineer can immediately run to investigate
- client_safe_summary: business language only, no table names, assume non-technical reader
- if row_count=0 or freshness breach: confidence = "high"
- never say 'I cannot determine' — always give best assessment based on available data\
"""

RETRY_SUFFIX = (
    "\n\nYour previous response failed JSON validation. "
    "Return ONLY the raw JSON object — no markdown, no preamble, no explanation."
)


# ── Core generation ────────────────────────────────────────────────────────────

def _get_client(api_key: str | None = None) -> OpenAI:
    return OpenAI(
        api_key=api_key or settings.OPENROUTER_API_KEY,
        base_url=settings.LLM_BASE_URL,
    )


def _call_llm(user_message: str, api_key: str | None = None, model: str | None = None) -> str:
    """OpenRouter call — returns text content."""
    client = _get_client(api_key)
    response = client.chat.completions.create(
        model=model or settings.LLM_MODEL,
        max_tokens=4096,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )
    return response.choices[0].message.content.strip()


def _repair_truncated_json(raw: str) -> str:
    """Best-effort repair of a JSON string truncated mid-stream."""
    text = raw.strip()
    # Strip markdown fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    # Try to close any open string — find last unescaped quote pair imbalance
    # Simple heuristic: count open braces/brackets and close them
    in_string = False
    escape_next = False
    open_braces = 0
    open_brackets = 0

    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch == "{":
                open_braces += 1
            elif ch == "}":
                open_braces -= 1
            elif ch == "[":
                open_brackets += 1
            elif ch == "]":
                open_brackets -= 1

    # Close unclosed string first
    if in_string:
        text += '"'
    # Close unclosed arrays then objects
    text += "]" * max(0, open_brackets) + "}" * max(0, open_braces)
    return text


def _parse_and_validate(raw: str) -> NarrationResult:
    """Strip markdown fences if present, attempt repair on decode error, then validate."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return NarrationResult.model_validate(json.loads(text))
    except json.JSONDecodeError:
        # Attempt repair on truncated response before giving up
        repaired = _repair_truncated_json(raw)
        return NarrationResult.model_validate(json.loads(repaired))


def generate_narration(context: str, org_api_key: str | None = None, org_model: str | None = None) -> dict:
    """
    Call OpenRouter with 1 validation retry.
    org_api_key / org_model: per-org overrides set by staff (take priority over global env).
    Returns dict (NarrationResult.model_dump() or error dict).
    """
    effective_key = org_api_key or settings.OPENROUTER_API_KEY
    effective_model = org_model or settings.LLM_MODEL
    if not effective_key:
        return {"error": "narration_failed", "reason": "No LLM API key configured"}

    user_msg = f"Here is the incident context:\n\n{context}\n\nGenerate the incident report JSON."

    # Attempt 1
    raw = None
    try:
        raw = _call_llm(user_msg, api_key=effective_key, model=effective_model)
        result = _parse_and_validate(raw)
        logger.info("LLM narration generated (attempt 1), model=%s confidence=%s", effective_model, result.confidence)
        return result.model_dump()
    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning("LLM attempt 1 failed validation: %s", e)
        raw1 = raw or "(no response)"
    except Exception as e:
        logger.error("LLM API error on attempt 1: %s", e)
        return {"error": "narration_failed", "reason": str(e)}

    # Attempt 2 — append retry hint
    try:
        raw2 = _call_llm(user_msg + RETRY_SUFFIX)
        result = _parse_and_validate(raw2)
        logger.info("LLM narration generated (attempt 2), model=%s confidence=%s", settings.LLM_MODEL, result.confidence)
        return result.model_dump()
    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning("LLM attempt 2 also failed: %s", e)
    except Exception as e:
        logger.error("LLM API error on attempt 2: %s", e)
        return {"error": "narration_failed", "reason": str(e)}

    # Attempt 3 — minimal prompt to maximise chance of clean JSON
    MINIMAL_PROMPT = (
        "Output ONLY a JSON object with these exact keys: "
        "summary (string), likely_causes (array of objects with hypothesis+probability), "
        "impact_assessment (string), recommended_actions (array of strings), "
        "data_pattern_notes (string), confidence (high|medium|low). "
        f"Context: {user_msg[:800]}"
    )
    try:
        raw3 = _call_llm(MINIMAL_PROMPT)
        result = _parse_and_validate(raw3)
        logger.info("LLM narration generated (attempt 3 minimal), model=%s", settings.LLM_MODEL)
        return result.model_dump()
    except (json.JSONDecodeError, ValidationError) as e:
        logger.error("LLM all 3 attempts failed: %s", e)
        return {"error": "validation_failed", "reason": str(e)}
    except Exception as e:
        logger.error("LLM API error on attempt 3: %s", e)
        return {"error": "narration_failed", "reason": str(e)}


# ── Redis cache ────────────────────────────────────────────────────────────────

def _redis_client():
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def get_cached_narration(incident_id: str) -> dict | None:
    try:
        r = _redis_client()
        val = r.get(f"llm:incident:{incident_id}")
        r.close()
        return json.loads(val) if val else None
    except Exception:
        return None


def cache_narration(incident_id: str, narration: dict) -> None:
    try:
        r = _redis_client()
        r.setex(f"llm:incident:{incident_id}", 86400, json.dumps(narration))
        r.close()
    except Exception as e:
        logger.warning("Failed to cache narration: %s", e)


def invalidate_narration_cache(incident_id: str) -> None:
    try:
        r = _redis_client()
        r.delete(f"llm:incident:{incident_id}")
        r.close()
    except Exception:
        pass


# ── Build context (re-export from llm_context for backwards compat) ────────────

async def build_context(incident_id: str) -> str:
    from app.services.llm_context import build_context as _build
    return await _build(incident_id)
