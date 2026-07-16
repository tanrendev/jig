"""Tier 2: static checks over the manifests the host parses and trusts."""

import json
import re
import tomllib
from typing import TYPE_CHECKING

import pytest
from conftest import PLUGIN_ROOT, REPO

if TYPE_CHECKING:
    from pathlib import Path

MARKETPLACE = REPO / ".claude-plugin" / "marketplace.json"
PLUGIN = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
HOOKS = PLUGIN_ROOT / "hooks" / "hooks.json"

# Hook events the host defines; extend when Claude Code grows one.
EVENTS = {
    "SessionStart",
    "SessionEnd",
    "PreToolUse",
    "PostToolUse",
    "UserPromptSubmit",
    "Notification",
    "Stop",
    "SubagentStop",
    "PreCompact",
}


@pytest.mark.parametrize("path", [MARKETPLACE, PLUGIN, HOOKS], ids=lambda p: p.name)
def test_manifest_parses(*, path: Path) -> None:
    json.loads(path.read_text())


def test_marketplace_plugins_exist_in_tree() -> None:
    for plugin in json.loads(MARKETPLACE.read_text())["plugins"]:
        root = (REPO / plugin["source"]).resolve()
        # Containment: an absolute or ../ source could name a file that
        # exists on the author's machine and nowhere else.
        assert root.is_relative_to(REPO)
        assert (root / ".claude-plugin" / "plugin.json").is_file()


def test_hook_commands_reference_existing_files() -> None:
    for event in json.loads(HOOKS.read_text())["hooks"].values():
        for matcher in event:
            for hook in matcher["hooks"]:
                for ref in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}([^\"\s]+)", hook["command"]):
                    target = (PLUGIN_ROOT / ref.lstrip("/")).resolve()
                    assert target.is_relative_to(PLUGIN_ROOT), ref
                    assert target.is_file(), ref


def test_hook_events_are_host_defined() -> None:
    assert set(json.loads(HOOKS.read_text())["hooks"]) <= EVENTS


def test_hook_timeouts_declared() -> None:
    # Tier 1 reads these as each subprocess's time budget; a hook without
    # one would fall back to host policy the suite cannot see.
    for event in json.loads(HOOKS.read_text())["hooks"].values():
        for matcher in event:
            for hook in matcher["hooks"]:
                assert type(hook["timeout"]) is int  # a JSON true is an int and must not pass
                assert hook["timeout"] > 0


def test_plugin_version_matches_pyproject() -> None:
    # The commitizen bump rewrites both; a mismatch means a release from
    # a half-synced tree.
    with (REPO / "pyproject.toml").open("rb") as f:
        pyproject = tomllib.load(f)
    assert json.loads(PLUGIN.read_text())["version"] == pyproject["project"]["version"]
