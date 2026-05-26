"""Click CLI for pii-scrubber.

Commands:
    scrub   De-identify a single file (or stdin) and print/save the result.
    batch   De-identify every text file in a directory, sharing one registry
            so tokens stay consistent across the corpus.

LLM enrichment is ON BY DEFAULT. Use --no-llm to force the fully-offline path,
or --llm-backend to pin a specific model. --json-output emits machine-readable
JSON for CI pipelines.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from . import __version__
from .corpus import CorpusScrubber
from .llm import available_backends, default_backend
from .models import ScrubConfig
from .scrubber import Scrubber

try:  # Rich is optional at runtime; degrade to plain text if missing.
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    _console: Console | None = Console()
except Exception:  # pragma: no cover
    _console = None


_TEXT_GLOBS = ("*.txt", "*.md", "*.vtt", "*.csv")


def _build_config(no_llm: bool, backend: str | None, scrub_dates: bool, reversible: bool, person_style: str) -> ScrubConfig:
    return ScrubConfig(
        use_llm=not no_llm,
        llm_backend=backend,
        scrub_dates=scrub_dates,
        keep_key=reversible,
        person_style=person_style,
    )


def _print_manifest(title: str, manifest_dict: dict) -> None:
    if _console is None:
        click.echo(f"{title}: {json.dumps(manifest_dict)}")
        return
    table = Table(title=title, title_style="bold", header_style="bold")
    table.add_column("Entity type")
    table.add_column("Redactions", justify="right")
    table.add_column("Unique", justify="right")
    counts = manifest_dict["counts"]
    uniq = manifest_dict["unique_entities"]
    for etype in sorted(set(counts) | set(uniq)):
        table.add_row(etype, str(counts.get(etype, 0)), str(uniq.get(etype, 0)))
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{manifest_dict['total_redactions']}[/bold]",
        f"[bold]{manifest_dict['total_unique_entities']}[/bold]",
    )
    _console.print(table)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="pii-scrubber")
def cli() -> None:
    """pii-scrubber — de-identify qualitative research data.

    Reduces re-identification risk; it does not guarantee anonymity and is not
    a compliance certification. Human review is required before data leaves the
    room.
    """


@cli.command()
@click.argument("source", type=click.Path(exists=True, dir_okay=False, allow_dash=True), required=False)
@click.option("-o", "--output", type=click.Path(dir_okay=False), help="Write scrubbed text here.")
@click.option("--json-output", "json_out", is_flag=True, help="Emit machine-readable JSON (for CI).")
@click.option("--no-llm", is_flag=True, help="Force the fully-offline rule-based path.")
@click.option("--llm-backend", type=click.Choice(["anthropic", "gemini", "openai"]), help="Pin an LLM backend.")
@click.option("--scrub-dates", is_flag=True, help="Also redact dates (off by default).")
@click.option("--reversible", is_flag=True, help="Keep a token->original key (re-introduces risk).")
@click.option("--person-style", type=click.Choice(["participant", "tag"]), default="participant", show_default=True)
def scrub(source, output, json_out, no_llm, llm_backend, scrub_dates, reversible, person_style):
    """De-identify a single document (file path, or '-' for stdin)."""
    if source in (None, "-"):
        text = sys.stdin.read()
    else:
        text = Path(source).read_text(encoding="utf-8", errors="replace")

    config = _build_config(no_llm, llm_backend, scrub_dates, reversible, person_style)
    result = Scrubber(config=config).scrub(text)

    if json_out:
        click.echo(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return

    if output:
        Path(output).write_text(result.scrubbed_text, encoding="utf-8")
        if _console:
            _console.print(f"[green]Scrubbed text written to[/green] {output}")
        else:
            click.echo(f"Scrubbed text written to {output}")
    else:
        if _console:
            _console.print(Panel(result.scrubbed_text, title="Scrubbed text", border_style="cyan"))
        else:
            click.echo(result.scrubbed_text)

    _print_manifest("Redaction manifest", result.manifest.to_dict())
    if reversible and _console:
        _console.print(
            "[yellow]A reversible key was produced. Store it separately from "
            "the scrubbed text and treat it as raw PII.[/yellow]"
        )


@cli.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("-o", "--output-dir", type=click.Path(file_okay=False), help="Write scrubbed copies here.")
@click.option("--json-output", "json_out", is_flag=True, help="Emit a combined JSON report.")
@click.option("--no-llm", is_flag=True, help="Force the fully-offline rule-based path.")
@click.option("--llm-backend", type=click.Choice(["anthropic", "gemini", "openai"]), help="Pin an LLM backend.")
@click.option("--scrub-dates", is_flag=True, help="Also redact dates (off by default).")
@click.option("--person-style", type=click.Choice(["participant", "tag"]), default="participant", show_default=True)
def batch(directory, output_dir, json_out, no_llm, llm_backend, scrub_dates, person_style):
    """De-identify every text file in DIRECTORY with corpus-wide consistency."""
    files: list[Path] = []
    for pattern in _TEXT_GLOBS:
        files.extend(sorted(Path(directory).glob(pattern)))
    if not files:
        raise click.ClickException(f"No text files ({', '.join(_TEXT_GLOBS)}) found in {directory}")

    config = _build_config(no_llm, llm_backend, scrub_dates, False, person_style)
    cs = CorpusScrubber(config=config)
    documents = {f.name: f.read_text(encoding="utf-8", errors="replace") for f in files}
    corpus = cs.scrub_all(documents)

    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        for name, res in corpus.results.items():
            (out_path / name).write_text(res.scrubbed_text, encoding="utf-8")

    if json_out:
        click.echo(json.dumps(corpus.to_dict(), indent=2, ensure_ascii=False))
        return

    if _console:
        _console.print(f"[bold]Scrubbed {len(files)} document(s)[/bold] with a shared registry.")
    else:
        click.echo(f"Scrubbed {len(files)} document(s).")
    for name, res in corpus.results.items():
        line = f"  {name}: {res.manifest.total} redactions"
        click.echo(line)
    _print_manifest("Combined manifest (corpus-wide)", corpus.combined.to_dict())


@cli.command()
def backends():
    """Show which LLM backends are configured and available."""
    avail = available_backends()
    default = default_backend()
    for name in ("anthropic", "gemini", "openai"):
        status = "available" if name in avail else "no API key"
        marker = " (default)" if name == default else ""
        click.echo(f"{name:10s} {status}{marker}")
    if not avail:
        click.echo("\nNo API keys detected — running rule-based only. Set an API "
                   "key or pass --no-llm to silence the LLM layer.")


# Expose the enabled set for documentation/testing.
DEFAULT_TYPES = sorted(t.value for t in ScrubConfig().enabled_types)


def main() -> None:  # pragma: no cover
    cli()


if __name__ == "__main__":  # pragma: no cover
    main()
