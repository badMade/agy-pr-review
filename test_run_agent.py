import pytest
import os
import sys
from run_agent import _load_command

def test_load_command_missing_file(tmp_path):
    action_path = str(tmp_path)
    result = _load_command("nonexistent", action_path, {})
    assert result is None

def test_load_command_path_traversal(tmp_path, capsys):
    action_path = str(tmp_path)
    for invalid_name in ["../foo", "foo/bar", "foo\\bar"]:
        with pytest.raises(SystemExit) as excinfo:
            _load_command(invalid_name, action_path, {})
        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        # The !r formatting adds repr-style quotes, meaning backslashes are escaped
        assert f"::error::Invalid command name: {invalid_name!r}" in captured.out

def test_load_command_valid_interpolation(tmp_path):
    action_path = tmp_path
    commands_dir = action_path / ".github" / "commands"
    commands_dir.mkdir(parents=True)

    toml_content = """
prompt = \"\"\"Hello !{ echo $NAME }, your role is !{ echo $ROLE }. Missing: !{ echo $MISSING }.\"\"\"
description = "Test prompt"
"""
    command_file = commands_dir / "my_cmd.toml"
    command_file.write_text(toml_content)

    env_context = {
        "NAME": "Alice",
        "ROLE": "Admin",
    }

    result = _load_command("my_cmd", str(action_path), env_context)

    # MISSING should evaluate to ""
    assert result == "Hello Alice, your role is Admin. Missing: ."
