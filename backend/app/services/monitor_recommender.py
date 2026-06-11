"""
LLM-backed monitor recommendations and natural language rule conversion.

Provider: OpenRouter/OpenAI-compatible API configured through app.config.settings.
Fallbacks: deterministic safe defaults when no key is configured or generation fails.
"""
import asyncio
import json
import logging
from typing import Any

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

MONITOR_TYPES = {
    "freshness",
    "row_count",
    "null_rate",
    "duplicate",
    "schema_drift",
    "value_range",
    "enum_drift",
    "custom_sql",
}
SEVERITIES = {"P1", "P2", "P3"}

RECOMMENDER_SYSTEM_PROMPT = (
    "You are a data quality expert. Given a database table schema, recommend specific monitors."
)

NL_RULE_SYSTEM_PROMPT = """\
You convert natural language data quality business rules into SQL checks.
Return valid JSON only. The SQL must be a SELECT COUNT(*) query that counts VIOLATIONS,
not compliant rows. Do not include markdown or explanatory text outside JSON.
"""


def _get_client(api_key: str | None = None) -> OpenAI:
    return OpenAI(
        api_key=api_key or settings.OPENROUTER_API_KEY,
        base_url=settings.LLM_BASE_URL,
    )


def _format_columns(columns: list[dict]) -> str:
    formatted = []
    for column in columns:
        nullable = "nullable" if column.get("nullable") else "non-nullable"
        formatted.append(
            f"- {column.get('name')}: {column.get('data_type')} "
            f"({column.get('category')}, {nullable})"
        )
    return "\n".join(formatted)


def _strip_markdown_fences(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return text


def _parse_json(raw: str) -> Any:
    text = _strip_markdown_fences(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start_candidates = [pos for pos in (text.find("["), text.find("{")) if pos != -1]
        if not start_candidates:
            raise
        start = min(start_candidates)
        end = max(text.rfind("]"), text.rfind("}"))
        if end <= start:
            raise
        return json.loads(text[start : end + 1])


def _call_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    api_key: str | None = None,
    model: str | None = None,
    response_format: dict | None = None,
    max_tokens: int = 2048,
) -> str:
    client = _get_client(api_key)
    kwargs: dict[str, Any] = {
        "model": model or settings.LLM_MODEL,
        "max_tokens": max_tokens,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if response_format:
        kwargs["response_format"] = response_format

    response = client.chat.completions.create(**kwargs)
    return (response.choices[0].message.content or "").strip()


def _timestamp_column(columns: list[dict]) -> dict | None:
    for column in columns:
        if column.get("category") == "timestamp":
            return column
    for column in columns:
        if column.get("category") == "date":
            return column
    return None


def _safe_default_monitors(table_name: str, columns: list[dict]) -> list[dict]:
    monitors: list[dict] = [
        {
            "monitor_type": "row_count",
            "column_name": None,
            "name": f"{table_name} row count is non-zero",
            "rationale": "A table unexpectedly dropping to zero rows usually indicates an upstream load or extraction failure.",
            "severity": "P1",
            "config": {"min_rows": 1},
        }
    ]

    freshness_column = _timestamp_column(columns)
    if freshness_column:
        monitors.insert(
            0,
            {
                "monitor_type": "freshness",
                "column_name": freshness_column.get("name"),
                "name": f"{table_name} freshness",
                "rationale": "Timestamp or date columns can detect stalled ingestion and delayed pipeline runs.",
                "severity": "P1",
                "config": {"max_age_hours": 24},
            },
        )

    for column in columns:
        if column.get("nullable") is False:
            monitors.append(
                {
                    "monitor_type": "null_rate",
                    "column_name": column.get("name"),
                    "name": f"{column.get('name')} null rate",
                    "rationale": "This column is marked non-nullable, so null values likely violate the table contract.",
                    "severity": "P2",
                    "config": {"max_null_rate": 0},
                }
            )

    return monitors


def _validate_monitor(item: Any) -> dict | None:
    if not isinstance(item, dict):
        return None

    monitor_type = item.get("monitor_type")
    name = item.get("name")
    severity = item.get("severity")

    if monitor_type not in MONITOR_TYPES or not name or severity not in SEVERITIES:
        return None

    monitor = dict(item)
    monitor.setdefault("column_name", None)
    monitor.setdefault("rationale", "")
    if not isinstance(monitor.get("config"), dict):
        monitor["config"] = {}
    return monitor


def _extract_monitor_list(parsed: Any) -> list[Any]:
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for key in ("monitors", "recommendations", "items"):
            value = parsed.get(key)
            if isinstance(value, list):
                return value
    return []


def _format_existing_monitors(monitors: list[dict]) -> str:
    if not monitors:
        return ""
    lines = []
    for m in monitors:
        mtype = m.get("monitor_type") or m.get("type") or "custom_sql"
        name = m.get("name") or ""
        col = m.get("column_name") or ""
        lines.append(f"- {mtype} on {col or 'table'}: {name}")
    return "\n".join(lines)


async def recommend_monitors(
    table_name: str,
    columns: list[dict],
    org_llm_key: str | None,
    org_model: str | None,
    db_type: str = "postgres",
    existing_monitors: list[dict] | None = None,
) -> list[dict]:
    effective_key = org_llm_key or settings.OPENROUTER_API_KEY
    if not effective_key:
        return _safe_default_monitors(table_name, columns)

    formatted_columns = _format_columns(columns)
    existing_section = ""
    if existing_monitors:
        existing_section = (
            f"\nAlready active monitors (do NOT suggest duplicates):\n"
            f"{_format_existing_monitors(existing_monitors)}\n"
        )
    user_prompt = (
        f"Table '{table_name}' in {db_type} has these columns:\n{formatted_columns}\n"
        f"{existing_section}\n"
        "Recommend monitors as JSON array of "
        "{monitor_type, column_name (or null), name, rationale, severity (P1/P2/P3), "
        "config (dict with any relevant params)}.\n"
        "monitor_type options: freshness, row_count, null_rate, duplicate, schema_drift, "
        "value_range, enum_drift, custom_sql.\n"
        "Return only the JSON array."
    )

    try:
        raw = await asyncio.to_thread(
            _call_llm,
            system_prompt=RECOMMENDER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            api_key=effective_key,
            model=org_model,
        )
        parsed = _parse_json(raw)
        monitors = [
            monitor
            for monitor in (_validate_monitor(item) for item in _extract_monitor_list(parsed))
            if monitor is not None
        ]
        if not monitors:
            raise ValueError("LLM returned no valid monitor recommendations")
        return monitors
    except Exception as exc:
        logger.warning("Monitor recommendation failed for table %s: %s", table_name, exc)
        return _safe_default_monitors(table_name, columns)


async def nl_rule_to_sql(
    natural_language_rule: str,
    table_name: str,
    columns: list[dict],
    org_llm_key: str | None,
    org_model: str | None,
) -> dict:
    effective_key = org_llm_key or settings.OPENROUTER_API_KEY
    if not effective_key:
        return {
            "sql": "",
            "explanation": "Could not generate SQL",
            "severity": "P3",
            "estimated_impact": "Unknown",
        }

    formatted_columns = _format_columns(columns)
    user_prompt = f"""\
Table '{table_name}' has these columns:
{formatted_columns}

Convert this business rule to a SQL COUNT(*) check that returns the number of violating rows:
{natural_language_rule}

Example:
Rule: paid orders must have payment reference
SQL: SELECT COUNT(*) FROM orders WHERE status = 'paid' AND payment_reference IS NULL

Return JSON with exactly these keys:
{{"sql": "SELECT COUNT(*) ...", "explanation": "...", "severity": "P1|P2|P3", "estimated_impact": "..."}}
"""

    try:
        raw = await asyncio.to_thread(
            _call_llm,
            system_prompt=NL_RULE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            api_key=effective_key,
            model=org_model,
            response_format={"type": "json_object"},
            max_tokens=1024,
        )
        parsed = _parse_json(raw)
        if not isinstance(parsed, dict):
            raise ValueError("LLM returned non-object SQL rule response")

        sql = str(parsed.get("sql") or "").strip()
        if not sql:
            raise ValueError("LLM returned empty SQL")

        severity = parsed.get("severity")
        if severity not in SEVERITIES:
            severity = "P3"

        return {
            "sql": sql,
            "explanation": str(parsed.get("explanation") or "").strip(),
            "severity": severity,
            "estimated_impact": str(parsed.get("estimated_impact") or "Unknown").strip(),
        }
    except Exception as exc:
        logger.warning("Natural language SQL rule generation failed for table %s: %s", table_name, exc)
        return {
            "sql": "",
            "explanation": "Could not generate SQL",
            "severity": "P3",
            "estimated_impact": "Unknown",
        }
