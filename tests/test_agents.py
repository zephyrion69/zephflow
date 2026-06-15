from unittest.mock import MagicMock, patch

import pytest

from src.agents.base import BaseAgent
from src.agents.developer import DeveloperAgent
from src.agents.planner import PlannerAgent
from src.agents.reviewer import ReviewerAgent
from src.agents.spec_validator import SpecValidatorAgent
from src.core.config import settings


class DummyAgent(BaseAgent):
    def run(self, input_data):
        return {"result": self._call_llm("system", "user")}


def test_base_agent_openai_success() -> None:
    settings.OPENAI_API_KEY = "test-openai-key"
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "openai-response"}}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_response) as mock_post:
        agent = DummyAgent("gpt-4")
        res = agent.run({})
        assert res["result"] == "openai-response"
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.openai.com/v1/chat/completions"
        assert kwargs["headers"]["Authorization"] == "Bearer test-openai-key"
        assert kwargs["json"]["model"] == "gpt-4"


def test_base_agent_anthropic_success() -> None:
    settings.ANTHROPIC_API_KEY = "test-anthropic-key"
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "content": [{"text": "anthropic-response"}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_response) as mock_post:
        agent = DummyAgent("claude-3-5-sonnet")
        res = agent.run({})
        assert res["result"] == "anthropic-response"
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.anthropic.com/v1/messages"
        assert kwargs["headers"]["x-api-key"] == "test-anthropic-key"
        assert kwargs["json"]["model"] == "claude-3-5-sonnet"


def test_base_agent_gemini_success() -> None:
    settings.GEMINI_API_KEY = "test-gemini-key"
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "gemini-response"}]}}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_response) as mock_post:
        agent = DummyAgent("gemini-1.5-pro")
        res = agent.run({})
        assert res["result"] == "gemini-response"
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert "gemini-1.5-pro" in args[0]
        assert "key=test-gemini-key" in args[0]
        assert kwargs["json"]["contents"][0]["role"] == "user"


def test_base_agent_missing_keys() -> None:
    settings.OPENAI_API_KEY = None
    settings.ANTHROPIC_API_KEY = None
    settings.GEMINI_API_KEY = None

    with pytest.raises(ValueError) as exc:
        DummyAgent("gpt-4").run({})
    assert "OPENAI_API_KEY non configurée" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        DummyAgent("claude-3").run({})
    assert "ANTHROPIC_API_KEY non configurée" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        DummyAgent("gemini-pro").run({})
    assert "GEMINI_API_KEY non configurée" in str(exc.value)


def test_base_agent_unknown_model() -> None:
    with pytest.raises(ValueError) as exc:
        DummyAgent("unknown-model-foo").run({})
    assert "Modèle non supporté" in str(exc.value)


def test_planner_agent() -> None:
    settings.OPENAI_API_KEY = "key"
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "## Implementation Plan\n1. Task"}}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_response) as mock_post:
        agent = PlannerAgent("gpt-4")
        res = agent.run({"requirements": "reqs", "code_context": "context"})
        assert "Implementation Plan" in res["plan"]
        kwargs = mock_post.call_args[1]
        assert "reqs" in kwargs["json"]["messages"][1]["content"]
        assert "context" in kwargs["json"]["messages"][1]["content"]


def test_developer_agent() -> None:
    settings.OPENAI_API_KEY = "key"
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "def test():\n    pass"}}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_response) as mock_post:
        agent = DeveloperAgent("gpt-4")
        res = agent.run({
            "requirements": "reqs",
            "plan": "plan",
            "file_path": "main.py",
            "current_content": "old_code",
            "feedback": "fix bug"
        })
        assert "def test():" in res["code"]
        kwargs = mock_post.call_args[1]
        assert "reqs" in kwargs["json"]["messages"][1]["content"]
        assert "plan" in kwargs["json"]["messages"][1]["content"]
        assert "main.py" in kwargs["json"]["messages"][1]["content"]
        assert "old_code" in kwargs["json"]["messages"][1]["content"]
        assert "fix bug" in kwargs["json"]["messages"][1]["content"]


def test_reviewer_agent_approved() -> None:
    settings.OPENAI_API_KEY = "key"
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "APPROVED: True\nCOMMENTS: Looks great!"}}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_response):
        agent = ReviewerAgent("gpt-4")
        res = agent.run({"code": "code", "file_path": "a.py", "requirements": "req"})
        assert res["approved"] is True
        assert res["comments"] == "Looks great!"


def test_reviewer_agent_rejected() -> None:
    settings.OPENAI_API_KEY = "key"
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "APPROVED: False\nCOMMENTS: Add tests."}}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_response):
        agent = ReviewerAgent("gpt-4")
        res = agent.run({"code": "code", "file_path": "a.py", "requirements": "req"})
        assert res["approved"] is False
        assert res["comments"] == "Add tests."


def test_spec_validator_agent_valid() -> None:
    settings.OPENAI_API_KEY = "key"
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "VALID: True\nCOMMENTS: Matches PRD."}}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_response):
        agent = SpecValidatorAgent("gpt-4")
        res = agent.run({"code": "code", "requirements": "req", "file_path": "a.py"})
        assert res["valid"] is True
        assert res["comments"] == "Matches PRD."


def test_spec_validator_agent_invalid() -> None:
    settings.OPENAI_API_KEY = "key"
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{
            "message": {
                "content": "VALID: False\nCOMMENTS: Missing feature X."
            }
        }]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_response):
        agent = SpecValidatorAgent("gpt-4")
        res = agent.run({"code": "code", "requirements": "req", "file_path": "a.py"})
        assert res["valid"] is False
        assert res["comments"] == "Missing feature X."
