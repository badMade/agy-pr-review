import os
import sys
import pytest
from unittest.mock import patch, mock_open

# Import the function to test
from run_agent import _write_github_output

def test_write_github_output_no_env_var(monkeypatch):
    """Test that it returns early if GITHUB_OUTPUT is not set"""
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    with patch("builtins.open", mock_open()) as mocked_file:
        _write_github_output("test text")
        mocked_file.assert_not_called()

def test_write_github_output_success(monkeypatch, tmp_path):
    """Test successful write to GITHUB_OUTPUT with proper delimiter formatting"""
    output_file = tmp_path / "github_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

    with patch("uuid.uuid4") as mock_uuid:
        class MockUUID:
            hex = "1234567890abcdef"
        mock_uuid.return_value = MockUUID()

        _write_github_output("hello world")

    assert output_file.exists()
    content = output_file.read_text(encoding="utf-8")

    expected = "response<<EOF_1234567890abcdef\nhello world\nEOF_1234567890abcdef\nstats={}\n"
    assert content == expected

def test_write_github_output_oserror(monkeypatch, capsys):
    """Test OSError handling when file cannot be written"""
    monkeypatch.setenv("GITHUB_OUTPUT", "/invalid/path/github_output.txt")

    with patch("builtins.open", side_effect=OSError("Permission denied")):
        _write_github_output("test text")

    captured = capsys.readouterr()
    assert "Warning: Could not write to GITHUB_OUTPUT: Permission denied" in captured.err
