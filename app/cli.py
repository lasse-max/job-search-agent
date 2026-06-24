"""CLI entrypoint.

Stage 0 intentionally exposes only a small status command. Stage 1 will add scan,
review, manual intake, digest, and export commands after owner approval.
"""

from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True)


@app.command()
def stage0_status() -> None:
    """Show the current Stage 0 boundary."""

    typer.echo("Stage 0 scaffold is ready. Review docs/source_coverage_audit.md before Stage 1.")


if __name__ == "__main__":
    app()

