"""CLI tests using Click's test runner."""

import json
from pathlib import Path

from click.testing import CliRunner

from pii_scrubber.cli import cli

FIXTURES = Path(__file__).parent / "fixtures"


def test_scrub_stdin_offline():
    runner = CliRunner()
    result = runner.invoke(cli, ["scrub", "--no-llm", "-"], input="Email a@b.com here.")
    assert result.exit_code == 0
    assert "[EMAIL_1]" in result.output
    assert "a@b.com" not in result.output


def test_scrub_json_output():
    runner = CliRunner()
    result = runner.invoke(cli, ["scrub", "--no-llm", "--json-output", "-"],
                           input="Email a@b.com here.")
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "scrubbed_text" in payload
    assert payload["manifest"]["total_redactions"] >= 1
    assert payload["reversible"] is False


def test_scrub_file(tmp_path):
    src = FIXTURES / "transcript.txt"
    out = tmp_path / "scrubbed.txt"
    runner = CliRunner()
    result = runner.invoke(cli, ["scrub", "--no-llm", str(src), "-o", str(out)])
    assert result.exit_code == 0
    scrubbed = out.read_text()
    assert "sarah.chen@globex.com" not in scrubbed
    assert "Participant 1" in scrubbed


def test_batch_corpus(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli, ["batch", "--no-llm", "--json-output", str(FIXTURES)])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "documents" in payload
    assert "combined_manifest" in payload


def test_batch_no_files(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli, ["batch", "--no-llm", str(tmp_path)])
    assert result.exit_code != 0
    assert "No text files" in result.output


def test_backends_command(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    runner = CliRunner()
    result = runner.invoke(cli, ["backends"])
    assert result.exit_code == 0
    assert "anthropic" in result.output
    assert "no API key" in result.output


def test_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "pii-scrubber" in result.output
