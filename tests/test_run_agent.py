import pytest
from unittest.mock import MagicMock, patch

# Import the module to test
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import run_agent

@patch('run_agent.policy')
def test_build_review_policies(mock_policy):
    """Test that _build_review_policies sets up the correct allow/deny list."""
    # Setup mocks for the policy module
    mock_policy.deny_all.return_value = "deny_all_policy"

    def allow_side_effect(arg):
        if hasattr(arg, 'name'):
            return f"allow_{arg.name}_policy"
        return f"allow_{arg}_policy"

    mock_policy.allow.side_effect = allow_side_effect

    # Create a mock for the GitHub MCP server
    mock_mcp = MagicMock()
    mock_mcp.name = "github_mcp"

    # Call the function
    policies = run_agent._build_review_policies(mock_mcp)

    # Verify the function called the policy methods correctly
    mock_policy.deny_all.assert_called_once()

    # Verify allow was called with expected arguments
    assert mock_policy.allow.call_count == 5

    # Check that allow was called with the MCP server
    mock_policy.allow.assert_any_call(mock_mcp)

    # Check that allow was called with the specific file operations
    mock_policy.allow.assert_any_call("view_file")
    mock_policy.allow.assert_any_call("find_file")
    mock_policy.allow.assert_any_call("search_file_content")
    mock_policy.allow.assert_any_call("list_directory")

    # Verify the returned list contains what we expect in the right order
    assert policies == [
        "deny_all_policy",
        "allow_github_mcp_policy",
        "allow_view_file_policy",
        "allow_find_file_policy",
        "allow_search_file_content_policy",
        "allow_list_directory_policy",
    ]
