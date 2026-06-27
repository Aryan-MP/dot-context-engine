import json

from typer.testing import CliRunner

from dot.cli import app

runner = CliRunner()


def test_init_skips_claude_when_not_detected(tmp_path):
    (tmp_path / "main.py").write_text("print('hi')\n")
    result = runner.invoke(app, ["init", str(tmp_path), "--no-sync"])
    assert result.exit_code == 0, result.output
    assert not (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / ".claude").exists()
    assert "Claude Code not detected" in result.output


def test_init_autodetects_claude(tmp_path):
    (tmp_path / ".claude").mkdir()
    result = runner.invoke(app, ["init", str(tmp_path), "--no-sync"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "CLAUDE.md").exists()
    mcp_config = json.loads((tmp_path / ".mcp.json").read_text())
    assert mcp_config["mcpServers"]["dot"]["args"] == ["mcp"]
    config = json.loads((tmp_path / ".dot" / "config.json").read_text())
    assert "claude" in config["integrations"]


def test_init_forced_claude(tmp_path):
    result = runner.invoke(app, ["init", str(tmp_path), "--no-sync", "--claude"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "CLAUDE.md").exists()


def test_init_adds_dot_to_gitignore(tmp_path):
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    result = runner.invoke(app, ["init", str(tmp_path), "--no-sync"])
    assert result.exit_code == 0, result.output
    content = (tmp_path / ".gitignore").read_text()
    assert ".dot/" in content
    assert "node_modules/" in content  # existing entries preserved

    # idempotent — second init doesn't duplicate the entry
    runner.invoke(app, ["init", str(tmp_path), "--no-sync"])
    assert (tmp_path / ".gitignore").read_text().count(".dot/") == 1


def test_init_copilot_flag(tmp_path):
    (tmp_path / "main.py").write_text("x = 1\n")
    result = runner.invoke(app, ["init", str(tmp_path), "--copilot"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".github" / "copilot-instructions.md").exists()
    config = json.loads((tmp_path / ".dot" / "config.json").read_text())
    assert "copilot" in config["integrations"]


def test_init_warns_without_git(tmp_path):
    (tmp_path / "main.py").write_text("x = 1\n")
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "no git repository found" in result.output
