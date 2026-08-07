#!/usr/bin/env python3
"""Run development Compose with only the selected provider dependencies."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE_COMPOSE_FILE = PROJECT_ROOT / "docker-compose.yml"
NO_OLLAMA_COMPOSE_FILE = PROJECT_ROOT / "docker-compose.no-ollama.yml"
OLLAMA_PROFILE_RESOLVER = PROJECT_ROOT / "scripts" / "ollama_model_profile.sh"

_MODEL_RECORD = re.compile(r"^(?:text|embedding):[A-Za-z0-9][A-Za-z0-9._:/+@-]*$")
_SENSITIVE_NAME = re.compile(r"(?:KEY|PASSWORD|SECRET|TOKEN|CREDENTIAL)", re.IGNORECASE)


class ComposeProviderStackError(RuntimeError):
    """Raised when the capability-aware Compose selection cannot be proven."""


@dataclass(frozen=True)
class ComposeStackSelection:
    """Sanitized local service selection derived from the provider profile."""

    mode: str
    ollama_models: tuple[str, ...]
    compose_files: tuple[Path, ...]

    @property
    def ollama_required(self) -> bool:
        return bool(self.ollama_models)


def _run_captured(
    command: Sequence[str],
    *,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            cwd=PROJECT_ROOT,
            env=dict(environment) if environment is not None else None,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ComposeProviderStackError("Provider service selection could not execute") from error


def _parse_ollama_init_environment(config_output: str) -> dict[str, str]:
    try:
        payload = json.loads(config_output)
        services = payload["services"]
        init_service = services["ollama-init"]
        raw_environment = init_service["environment"]
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ComposeProviderStackError(
            "Compose configuration omitted the Ollama profile resolver contract"
        ) from error

    if not isinstance(raw_environment, Mapping):
        raise ComposeProviderStackError("Ollama profile resolver environment is invalid")

    environment: dict[str, str] = {}
    for raw_name, raw_value in raw_environment.items():
        name = str(raw_name)
        if _SENSITIVE_NAME.search(name):
            raise ComposeProviderStackError(
                "Ollama profile resolver environment contains a sensitive field"
            )
        if raw_value is None:
            environment[name] = ""
        elif isinstance(raw_value, (str, int, float, bool)):
            environment[name] = str(raw_value)
        else:
            raise ComposeProviderStackError("Ollama profile resolver value is invalid")
    return environment


def _resolved_model_environment() -> dict[str, str]:
    result = _run_captured(
        [
            "docker",
            "compose",
            "-f",
            str(BASE_COMPOSE_FILE),
            "config",
            "--format",
            "json",
        ]
    )
    if result.returncode != 0:
        raise ComposeProviderStackError("Docker Compose provider configuration is invalid")
    return _parse_ollama_init_environment(result.stdout)


def _resolve_ollama_models(environment: Mapping[str, str]) -> tuple[str, ...]:
    resolver_environment = {
        "PATH": os.defpath,
        **environment,
    }
    result = _run_captured(
        ["sh", str(OLLAMA_PROFILE_RESOLVER), "list"],
        environment=resolver_environment,
    )
    if result.returncode != 0:
        raise ComposeProviderStackError("Selected provider capability configuration is invalid")

    records = tuple(line.strip() for line in result.stdout.splitlines() if line.strip())
    if any(not _MODEL_RECORD.fullmatch(record) for record in records):
        raise ComposeProviderStackError("Ollama profile resolver returned an invalid model record")
    return records


def select_compose_stack(
    environment: Mapping[str, str] | None = None,
) -> ComposeStackSelection:
    """Resolve whether the development stack requires local Ollama services."""
    resolved_environment = (
        dict(environment) if environment is not None else _resolved_model_environment()
    )
    ollama_models = _resolve_ollama_models(resolved_environment)
    if ollama_models:
        return ComposeStackSelection(
            mode="ollama-required",
            ollama_models=ollama_models,
            compose_files=(BASE_COMPOSE_FILE,),
        )
    return ComposeStackSelection(
        mode="ollama-not-required",
        ollama_models=(),
        compose_files=(BASE_COMPOSE_FILE, NO_OLLAMA_COMPOSE_FILE),
    )


def build_compose_command(
    selection: ComposeStackSelection,
    compose_arguments: Sequence[str],
) -> list[str]:
    """Build a Docker Compose command without placing credentials in arguments."""
    if not compose_arguments:
        raise ComposeProviderStackError("A Docker Compose command is required")
    command = ["docker", "compose"]
    for compose_file in selection.compose_files:
        command.extend(("-f", str(compose_file)))
    command.extend(compose_arguments)
    return command


def render_plan(selection: ComposeStackSelection) -> str:
    """Return a stable, credential-free selection summary."""
    return "\n".join(
        (
            f"mode: {selection.mode}",
            f"ollama_required: {str(selection.ollama_required).lower()}",
            f"ollama_model_count: {len(selection.ollama_models)}",
        )
    )


def main(arguments: Sequence[str] | None = None) -> int:
    """Print the selected plan or execute Docker Compose with that plan."""
    args = list(sys.argv[1:] if arguments is None else arguments)
    try:
        selection = select_compose_stack()
        if args == ["plan"]:
            print(render_plan(selection))
            return 0
        command = build_compose_command(selection, args)
        result = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
        return result.returncode
    except ComposeProviderStackError as error:
        print(f"compose-provider-stack: {error}", file=sys.stderr)
        return 2
    except OSError:
        print("compose-provider-stack: Docker Compose could not execute", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
