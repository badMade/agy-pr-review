import sys
import os
import pytest
from unittest.mock import patch

# Create mock module
class MockPolicy:
    def allow_all(self): pass
    def confirm_run_command(self): pass

class MockHooks:
    policy = MockPolicy()

class MockTypes:
    McpStdioServer = object

class MockAntigravity:
    Agent = object
    LocalAgentConfig = object
    types = MockTypes()
    hooks = MockHooks()

# Inject into sys.modules before importing run_agent
sys.modules['google'] = type('google', (), {})
sys.modules['google.antigravity'] = MockAntigravity
sys.modules['google.antigravity.hooks'] = MockHooks

# Now import _load_command
from run_agent import _load_command

def test_load_command_missing_file():
    with patch('os.path.exists', return_value=False):
        result = _load_command('test_cmd', '/mock/path', {})
        assert result is None
