"""``codemap knowledge {write,validate,lint}`` subcommand group (FIX-2).

Registered via the ``codemap.cli_commands`` entry-point group. This is the
single on-disk writer/validator for the knowledge contract:

* ``write``    — take a content payload (json, from a file or stdin) and write
  the yml + md twin via :func:`knowledge_writer.write_knowledge`.
* ``validate`` — dry-run a payload (or built knowledge) against the schema,
  writing nothing; non-zero exit if invalid.
* ``lint``     — scan an existing project's ``.ai-memory/knowledge/*.yml`` and
  report schema violations; non-zero exit if any.

specode-distill (LLM-authored payloads) and task-swarm (mechanical payloads)
both call ``write`` instead of hand-writing files, so the schema / id / merge
/ stamping logic lives in exactly one place.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from codemap_aimemory.knowledge_schema import CATEGORIES
from codemap_aimemory.knowledge_schema import validate as validate_schema
from codemap_aimemory.knowledge_writer import write_knowledge

__all__ = ["register"]


def _load_payload(payload: str) -> dict[str, Any]:
    text = sys.stdin.read() if payload == "-" else Path(payload).read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("payload must be a JSON object")
    return data


def register(app: typer.Typer) -> None:
    knowledge_app = typer.Typer(
        no_args_is_help=True,
        help="Write / validate / lint .ai-memory/knowledge (the single writer).",
    )

    @knowledge_app.command("write")
    def write_cmd(
        project: Annotated[
            Path,
            typer.Option(
                "--project",
                "-p",
                exists=True,
                file_okay=False,
                dir_okay=True,
                resolve_path=True,
                help="Project root containing .ai-memory/.",
            ),
        ] = Path("."),
        category: Annotated[
            str, typer.Option("--category", "-C", help=f"One of {', '.join(CATEGORIES)}.")
        ] = "",
        payload: Annotated[
            str,
            typer.Option("--payload", help="JSON payload file, or '-' for stdin."),
        ] = "-",
        output: Annotated[str, typer.Option("--output", "-o", help="yaml | json.")] = "yaml",
    ) -> None:
        """Write a knowledge payload to its yml + md twin."""
        try:
            data = _load_payload(payload)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            typer.echo(f"Error: cannot read payload: {exc}", err=True)
            raise typer.Exit(code=2) from exc

        result = write_knowledge(project, category, data)
        _emit(result, output)
        if result.get("errors"):
            raise typer.Exit(code=1)

    @knowledge_app.command("validate")
    def validate_cmd(
        category: Annotated[
            str, typer.Option("--category", "-C", help=f"One of {', '.join(CATEGORIES)}.")
        ] = "",
        payload: Annotated[
            str, typer.Option("--payload", help="JSON payload file, or '-' for stdin.")
        ] = "-",
        output: Annotated[str, typer.Option("--output", "-o", help="yaml | json.")] = "yaml",
    ) -> None:
        """Dry-run a payload against the schema — writes nothing."""
        try:
            data = _load_payload(payload)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            typer.echo(f"Error: cannot read payload: {exc}", err=True)
            raise typer.Exit(code=2) from exc

        if category not in CATEGORIES:
            _emit({"errors": [f"unknown category: {category!r}"]}, output)
            raise typer.Exit(code=1)

        # Build a representative knowledge dict (identity + fields) to lint.
        candidate: dict[str, Any] = {
            "knowledge_id": data.get("knowledge_id"),
            "type": data.get("type"),
        }
        candidate.update(data.get("fields") or {})
        errors = validate_schema(candidate, category)
        # Also require that an id is derivable (write would otherwise reject).
        if not (
            data.get("knowledge_id")
            or data.get("spec_id")
            or data.get("signature")
            or data.get("title")
        ):
            errors = [
                *errors,
                "cannot derive knowledge_id (need knowledge_id/spec_id/signature/title)",
            ]
        _emit({"category": category, "errors": errors}, output)
        if errors:
            raise typer.Exit(code=1)

    @knowledge_app.command("lint")
    def lint_cmd(
        project: Annotated[
            Path,
            typer.Option(
                "--project",
                "-p",
                exists=True,
                file_okay=False,
                dir_okay=True,
                resolve_path=True,
                help="Project root containing .ai-memory/.",
            ),
        ] = Path("."),
        output: Annotated[str, typer.Option("--output", "-o", help="yaml | json.")] = "yaml",
    ) -> None:
        """Scan .ai-memory/knowledge/*.yml and report schema violations."""
        import yaml

        knowledge_root = project / ".ai-memory" / "knowledge"
        findings: list[dict[str, Any]] = []
        if knowledge_root.is_dir():
            for category in CATEGORIES:
                for yml_file in sorted((knowledge_root / category).glob("*.yml")):
                    try:
                        kn = yaml.safe_load(yml_file.read_text(encoding="utf-8"))
                    except (OSError, yaml.YAMLError) as exc:
                        findings.append({"file": yml_file.name, "errors": [f"unreadable: {exc}"]})
                        continue
                    if not isinstance(kn, dict):
                        findings.append({"file": yml_file.name, "errors": ["not a mapping"]})
                        continue
                    errs = validate_schema(kn, category)
                    if errs:
                        findings.append(
                            {
                                "file": yml_file.name,
                                "knowledge_id": kn.get("knowledge_id"),
                                "errors": errs,
                            }
                        )
        _emit({"findings": findings, "count": len(findings)}, output)
        if findings:
            raise typer.Exit(code=1)

    app.add_typer(knowledge_app, name="knowledge")


def _emit(result: dict[str, Any], output: str) -> None:
    if output == "json":
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        import yaml

        yaml.safe_dump(result, sys.stdout, allow_unicode=True, sort_keys=False)
