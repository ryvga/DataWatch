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
You are a senior data engineer expert in data quality and pipeline reliability.
You are given information about a data quality incident — an anomaly detected in a
production data warehouse table. Your job is to generate a clear, actionable
incident report for the data team.

Always respond with valid JSON matching this exact schema — no preamble, no markdown:
{
  "summary": "one sentence plain English description of what happened",
  "likely_causes": [
    {"hypothesis": "specific technical cause", "probability": "high|medium|low"}
  ],
  "impact_assessment": "what business/data processes are affected and how severely",
  "recommended_actions": ["concrete step 1", "concrete step 2"],
  "data_pattern_notes": "any interesting pattern in the historical data",
  "confidence": "high|medium|low"
}

Rules:
- summary must mention the specific table and metric that failed
- likely_causes: 1-3 entries, most probable first
- recommended_actions: 2-5 specific, actionable steps (check X, query Y, contact Z)
- if this is a pipeline failure (row_count=0 or freshness breach), confidence should be "high"
- never say "I cannot determine" — always give your best assessment\
"""

RETRY_SUFFIX = (
    "\n\nYour previous response failed JSON validation. "
    "Return ONLY the raw JSON object — no markdown, no preamble, no explanation."
)


# ── Core generation ────────────────────────────────────────────────────────────

def _get_client() -> OpenAI:
    return OpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.LLM_BASE_URL,
    )


def _call_llm(user_message: str) -> str:
    """OpenRouter call — returns text content."""
    client = _get_client()
    response = client.chat.completions.create(
        model=settings.LLM_MODEL,
        max_tokens=1024,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )
    return response.choices[0].message.content.strip()


def _parse_and_validate(raw: str) -> NarrationResult:
    """Strip markdown fences if present, then parse + validate."""
    text = raw
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return NarrationResult.model_validate(json.loads(text))


def generate_narration(context: str) -> dict:
    """
    Call OpenRouter with 1 validation retry.
    Returns dict (NarrationResult.model_dump() or error dict).
    """
    if not settings.OPENROUTER_API_KEY:
        return {"error": "narration_failed", "reason": "OPENROUTER_API_KEY not set"}

    user_msg = f"Here is the incident context:\n\n{context}\n\nGenerate the incident report JSON."

    # Attempt 1
    raw = None
    try:
        raw = _call_llm(user_msg)
        result = _parse_and_validate(raw)
        logger.info("LLM narration generated (attempt 1), model=%s confidence=%s", settings.LLM_MODEL, result.confidence)
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
        logger.info("LLM narration generated (attempt 2 retry), model=%s confidence=%s", settings.LLM_MODEL, result.confidence)
        return result.model_dump()
    except (json.JSONDecodeError, ValidationError) as e:
        logger.error("LLM attempt 2 also failed: %s", e)
        return {
            "error": "validation_failed",
            "reason": str(e),
            "raw": raw1[:500],
        }
    except Exception as e:
        logger.error("LLM API error on retry: %s", e)
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
