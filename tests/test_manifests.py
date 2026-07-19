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


def test_command_plugin_root_references_resolve() -> None:
    # Commands name their support files (setup templates) the same way
    # hooks.json names its scripts; a dangling reference ships a command
    # that cannot find them.
    for command in (PLUGIN_ROOT / "commands").glob("*.md"):
        for ref in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}([^\"\s`]+)", command.read_text()):
            target = (PLUGIN_ROOT / ref.lstrip("/")).resolve()
            assert target.is_relative_to(PLUGIN_ROOT), ref
            assert target.exists(), ref


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


SKILL_MANIFESTS = sorted((PLUGIN_ROOT / "skills").glob("*/*/SKILL.md"))
BUCKETS = sorted(p for p in (PLUGIN_ROOT / "skills").iterdir() if p.is_dir())


def _skill_frontmatter(*, path: Path) -> dict[str, str]:
    # The host reads a flat key: value block between --- fences; parsing
    # anything richer here would accept skills the host rejects.
    text = path.read_text()
    assert text.startswith("---\n"), path
    block, fence, _ = text.removeprefix("---\n").partition("\n---\n")
    assert fence, path
    fields = {}
    for line in block.splitlines():
        key, sep, value = line.partition(":")
        assert sep, line
        fields[key.strip()] = value.strip().strip('"')
    return fields


@pytest.mark.parametrize("path", SKILL_MANIFESTS, ids=lambda p: p.parent.name)
def test_skill_frontmatter_names_and_describes_itself(*, path: Path) -> None:
    fields = _skill_frontmatter(path=path)
    # The folder is the identity the host loads the skill under.
    assert fields["name"] == path.parent.name
    # Descriptions sit in context every turn and truncate past the cap.
    assert 0 < len(fields["description"]) <= 1024


@pytest.mark.parametrize("path", SKILL_MANIFESTS, ids=lambda p: p.parent.name)
def test_skill_relative_links_resolve(*, path: Path) -> None:
    # Skills disclose reference material through relative links; a
    # dangling one ships a skill pointing at nothing. Fenced blocks and
    # code spans are exempt: their links are examples addressed to the
    # repo the skill operates on, not files of this plugin.
    prose = re.sub(r"```.*?```|`[^`]*`", "", path.read_text(), flags=re.DOTALL)
    for target in re.findall(r"\]\((?!https?://)([^)#]+)", prose):
        assert (path.parent / target).is_file(), target


@pytest.mark.parametrize("bucket", BUCKETS, ids=lambda p: p.name)
def test_bucket_readme_lists_exactly_its_skills(*, bucket: Path) -> None:
    # Each bucket README indexes its skills by relative link; adding or
    # removing a skill without touching the index desyncs them silently.
    readme = (bucket / "README.md").read_text()
    listed = set(re.findall(r"\]\(\./([^/)]+)/SKILL\.md\)", readme))
    present = {p.name for p in bucket.iterdir() if p.is_dir()}
    assert listed == present


def test_plugin_version_matches_pyproject() -> None:
    # The commitizen bump rewrites both; a mismatch means a release from
    # a half-synced tree.
    with (REPO / "pyproject.toml").open("rb") as f:
        pyproject = tomllib.load(f)
    assert json.loads(PLUGIN.read_text())["version"] == pyproject["project"]["version"]
