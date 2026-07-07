import sys
from unittest.mock import MagicMock
import pytest

# Mock google.antigravity before importing run_agent
mock_google = MagicMock()
mock_antigravity = MagicMock()
mock_policy = MagicMock()
mock_antigravity.hooks.policy = mock_policy
mock_google.antigravity = mock_antigravity

sys.modules['google'] = mock_google
sys.modules['google.antigravity'] = mock_antigravity
sys.modules['google.antigravity.hooks'] = MagicMock()
sys.modules['google.antigravity.hooks'].policy = mock_policy

from run_agent import _build_goal_policies, policy

@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset mocks before each test to ensure test isolation."""
    policy.allow_all.reset_mock()
    policy.confirm_run_command.reset_mock()

def test_build_goal_policies_trust_workspace():
    """Test that when trust_workspace is True, allow_all policy is returned in a list."""
    # Setup mock return
    policy.allow_all.return_value = "allow_all_mock"

    # Execute
    result = _build_goal_policies(trust_workspace=True)

    # Assert
    assert result == ["allow_all_mock"]
    policy.allow_all.assert_called_once()
    policy.confirm_run_command.assert_not_called()

def test_build_goal_policies_no_trust_workspace():
    """Test that when trust_workspace is False, confirm_run_command policy is returned."""
    # Setup mock return
    policy.confirm_run_command.return_value = "confirm_run_mock"

    # Execute
    result = _build_goal_policies(trust_workspace=False)

    # Assert
    assert result == "confirm_run_mock"
    policy.confirm_run_command.assert_called_once()
    policy.allow_all.assert_not_called()
