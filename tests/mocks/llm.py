"""Mock LLM agents and responses for testing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable


class MockLLMResult:
    """Mock result from LLM agent execution."""

    def __init__(self, output: str) -> None:
        """Initialize mock result."""
        self.output = output


class MockLLMAgent:
    """Mock LLM agent for testing without real API calls."""

    def __init__(self, responses: dict[str, str]) -> None:
        """Initialize mock agent.

        Args:
        ----
            responses: Mapping of input patterns to responses

        """
        self.responses = responses
        self.call_history: list[dict[str, Any]] = []

    def run(self, user_prompt: str) -> Awaitable[MockLLMResult]:
        """Mock execution of the agent."""
        self.call_history.append({"user_prompt": user_prompt})

        async def mock_run() -> MockLLMResult:
            response = self._get_response_for_prompt(user_prompt)
            return MockLLMResult(response)

        return mock_run()

    def _get_response_for_prompt(self, prompt: str) -> str:
        """Get appropriate response for the given prompt."""
        prompt_lower = prompt.lower()
        for pattern, response in self.responses.items():
            if pattern.lower() in prompt_lower:
                return response
        return self.responses.get("default", "Mock LLM response")
