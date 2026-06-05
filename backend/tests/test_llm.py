"""Unit tests for LLM validation — mocks OpenRouter call, no API key required."""
import json
from unittest.mock import MagicMock, patch

import pytest

VALID_NARRATION = {
    "summary": "The orders table stopped receiving data, indicating a pipeline failure.",
    "likely_causes": [{"hypothesis": "ETL job crashed", "probability": "high"}],
    "impact_assessment": "Revenue reporting impacted.",
    "recommended_actions": ["Check ETL logs", "Restart pipeline job"],
    "data_pattern_notes": "Row count was stable before this event.",
    "confidence": "high",
}


def test_narration_result_valid():
    from app.services.llm import NarrationResult
    result = NarrationResult.model_validate(VALID_NARRATION)
    assert result.confidence == "high"
    assert len(result.likely_causes) == 1
    assert result.likely_causes[0].probability == "high"


def test_narration_result_invalid_probability():
    from app.services.llm import NarrationResult
    import pydantic
    bad = {**VALID_NARRATION, "likely_causes": [{"hypothesis": "X", "probability": "extreme"}]}
    with pytest.raises(pydantic.ValidationError):
        NarrationResult.model_validate(bad)


def test_narration_result_empty_summary():
    from app.services.llm import NarrationResult
    import pydantic
    bad = {**VALID_NARRATION, "summary": "   "}
    with pytest.raises(pydantic.ValidationError):
        NarrationResult.model_validate(bad)


def test_narration_result_empty_causes():
    from app.services.llm import NarrationResult
    import pydantic
    bad = {**VALID_NARRATION, "likely_causes": []}
    with pytest.raises(pydantic.ValidationError):
        NarrationResult.model_validate(bad)


def test_generate_narration_success():
    from app.services.llm import generate_narration

    with patch("app.services.llm._call_llm", return_value=json.dumps(VALID_NARRATION)), \
         patch("app.services.llm.settings") as mock_settings:
        mock_settings.OPENROUTER_API_KEY = "test-key"
        result = generate_narration("test context")

    assert result["confidence"] == "high"
    assert "error" not in result


def test_generate_narration_strips_markdown_fences():
    from app.services.llm import generate_narration
    wrapped = f"```json\n{json.dumps(VALID_NARRATION)}\n```"

    with patch("app.services.llm._call_llm", return_value=wrapped), \
         patch("app.services.llm.settings") as mock_settings:
        mock_settings.OPENROUTER_API_KEY = "test-key"
        result = generate_narration("test context")

    assert "error" not in result
    assert result["summary"] == VALID_NARRATION["summary"]


def test_generate_narration_retry_on_bad_json():
    from app.services.llm import generate_narration
    call_count = {"n": 0}

    def side_effect(msg, api_key=None, model=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return "this is not json at all"
        return json.dumps(VALID_NARRATION)

    with patch("app.services.llm._call_llm", side_effect=side_effect), \
         patch("app.services.llm.settings") as mock_settings:
        mock_settings.OPENROUTER_API_KEY = "test-key"
        result = generate_narration("test context")

    assert call_count["n"] == 2, "Should retry exactly once"
    assert "error" not in result


def test_generate_narration_both_attempts_fail():
    from app.services.llm import generate_narration

    with patch("app.services.llm._call_llm", return_value="not valid json"), \
         patch("app.services.llm.settings") as mock_settings:
        mock_settings.OPENROUTER_API_KEY = "test-key"
        result = generate_narration("test context")

    assert result.get("error") == "validation_failed"


def test_generate_narration_no_api_key():
    from app.services.llm import generate_narration
    with patch("app.config.settings") as mock_settings:
        mock_settings.OPENROUTER_API_KEY = ""
        result = generate_narration("test context")
    assert result.get("error") == "narration_failed"
