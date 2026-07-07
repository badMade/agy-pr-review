import unittest
import sys
from unittest.mock import patch, MagicMock
import os
import io

# Mock google.antigravity so run_agent.py can be imported
mock_modules = {
    'google.antigravity': MagicMock(),
    'google.antigravity.hooks': MagicMock(),
    'google': MagicMock()
}

with patch.dict(sys.modules, mock_modules):
    import run_agent

class TestRunAgent(unittest.TestCase):
    @patch.dict(os.environ, {"GITHUB_OUTPUT": "dummy_path.txt"})
    @patch("builtins.open", side_effect=OSError("Mocked OSError"))
    @patch("sys.stderr", new_callable=io.StringIO)
    def test_write_github_output_oserror(self, mock_stderr, mock_open):
        run_agent._write_github_output("test text")

        mock_open.assert_called_once_with("dummy_path.txt", "a", encoding="utf-8")

        error_output = mock_stderr.getvalue()
        self.assertIn("Warning: Could not write to GITHUB_OUTPUT: Mocked OSError", error_output)

if __name__ == "__main__":
    unittest.main()
