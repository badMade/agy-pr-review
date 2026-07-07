import sys
from unittest.mock import MagicMock

# Mock google.antigravity before importing run_agent
mock_types = MagicMock()
mock_antigravity = MagicMock()
mock_antigravity.types = mock_types
sys.modules['google'] = MagicMock()
sys.modules['google.antigravity'] = mock_antigravity
sys.modules['google.antigravity.hooks'] = MagicMock()
sys.modules['google.antigravity.hooks.policy'] = MagicMock()

import run_agent

def test_build_github_mcp():
    """Test that _build_github_mcp configures the MCP server correctly."""

    # Call the function
    result = run_agent._build_github_mcp()

    # Assertions
    mock_types.McpStdioServer.assert_called_once()

    # Get the kwargs it was called with
    _, kwargs = mock_types.McpStdioServer.call_args

    assert kwargs.get('name') == 'github'
    assert kwargs.get('command') == 'docker'

    assert 'args' in kwargs
    args = kwargs['args']
    assert "run" in args
    assert "-i" in args
    assert "--rm" in args
    assert "-e" in args
    assert "GITHUB_PERSONAL_ACCESS_TOKEN" in args
    assert "ghcr.io/github/github-mcp-server:v0.27.0" in args

    assert 'enabled_tools' in kwargs
    enabled_tools = kwargs['enabled_tools']
    expected_tools = [
        "add_comment_to_pending_review",
        "pull_request_read",
        "pull_request_review_write",
        "add_issue_comment",
        "issue_read",
        "list_issues",
        "search_issues",
        "list_pull_requests",
        "search_pull_requests",
        "get_commit",
        "get_file_contents",
        "list_commits",
        "search_code",
    ]
    for tool in expected_tools:
        assert tool in enabled_tools
