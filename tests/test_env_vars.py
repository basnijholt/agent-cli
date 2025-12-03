"""Test that environment variables are correctly mapped to CLI options."""

import os
import re
from unittest import mock

from typer.testing import CliRunner

from agent_cli.cli import app

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"})


def test_openai_base_url_env_var() -> None:
    """Test that OPENAI_BASE_URL environment variable sets the openai_base_url option."""
    env_vars = {"OPENAI_BASE_URL": "http://test"}

    with (
        mock.patch.dict(os.environ, env_vars),
        mock.patch("agent_cli.agents.autocorrect._async_autocorrect"),
    ):
        # We use --print-args to see what the CLI parsed.
        # We need to provide a dummy text argument so it doesn't try to read clipboard if it's empty/fails.
        result = runner.invoke(app, ["autocorrect", "--print-args", "dummy text"])

    assert result.exit_code == 0
    # Strip ANSI codes
    clean_output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)

    # Check if openai_base_url matches the env var
    assert "openai_base_url" in clean_output
    assert "http://test" in clean_output
