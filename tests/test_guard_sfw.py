"""Tier 3: command classification in sfw, pure logic over a wide input space.

Tier 1 proves the deny and reissue flow end to end; the tables here pin
the classifier edges that would be unreadable as subprocess cases.
"""

import sys
from pathlib import Path

import pytest
from conftest import PLUGIN_ROOT

sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

import sfw

SFW = Path("/jig/bin/sfw")


@pytest.mark.parametrize(
    "command",
    [
        "npm install left-pad",
        "npm i left-pad",
        "npm ci",
        "pnpm add left-pad",
        "yarn add left-pad",
        "bun install",
        # Run-on-demand fetchers install without ever saying "install".
        "npx cowsay hi",
        "uvx ruff check",
        "pipx run ruff",
        "pip install requests",
        # Versioned interpreters must not slip past the pattern.
        "pip3 install requests",
        "pip3.11 install requests",
        "python -m pip install requests",
        "python3.12 -m pip install requests",
        # Nor options whose value sits between the tool and the subcommand.
        "pip --index-url https://example.invalid/simple install requests",
        "python3.12 -m pip --proxy http://example.invalid install requests",
        "npm --registry https://example.invalid install left-pad",
        "uv add requests",
        "uv sync",
        "uv pip install requests",
        "uv tool install ruff",
        "poetry add requests",
        "pipx install ruff",
        "pdm add requests",
        # Anywhere in a compound command counts.
        "cd sub && npm install left-pad --ignore-scripts",
    ],
)
def test_classified_as_install(*, command: str) -> None:
    assert sfw.INSTALLS.search(command)


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "npm test",
        "npm run build",
        "pip show requests",
        "pip uninstall requests",
        "uv run pytest",
        "uv lock",
        "poetry run pytest",
        "poetry lock",
    ],
)
def test_not_classified_as_install(*, command: str) -> None:
    assert not sfw.INSTALLS.search(command)


@pytest.mark.parametrize(
    "command",
    ["poetry add requests", "poetry install", "poetry update"],
)
def test_poetry_forms_recognized(*, command: str) -> None:
    assert sfw.POETRY.search(command)


def test_canonical_reissue_is_routed() -> None:
    reissued = sfw.reissue(sfw=SFW, command="cd sub && npm install left-pad")
    assert sfw.is_routed(sfw=SFW, command=reissued)


@pytest.mark.parametrize(
    "command",
    [
        # is_routed exempts only the byte-exact reissue() output, so
        # appended commands and payloads the outer shell would expand
        # before sfw runs must all fail the round-trip.
        f"\"{SFW}\" sh -c ':'; npm install attacker",
        f'"{SFW}" --version; npm install attacker',
        f'"{SFW}" true && npm install attacker',
        f'"{SFW}" sh -c "$(npm install attacker)"',
        f'"{SFW}" sh -c `npm install attacker`',
        # The path must lead a reissue, not merely appear somewhere.
        f'echo "{SFW}" && npm install left-pad',
        # Unbalanced quotes: not a reissue we produced.
        f'"{SFW}" sh -c \'npm install x',
        # Another sfw binary than the resolved one earns no exemption.
        "\"/elsewhere/sfw\" sh -c 'npm install x'",
    ],
)
def test_non_canonical_wrapper_is_not_routed(*, command: str) -> None:
    assert not sfw.is_routed(sfw=SFW, command=command)
