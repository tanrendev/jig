"""Hermetic sandbox, applied to every test (documentation/testing.md).

The tier 1 helpers spawn hooks without an explicit env, so the subprocess
inherits exactly what this fixture leaves in os.environ. A test that needs
another variable sets it after the scrub; the fixture restores everything
on teardown.
"""

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

REPO = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO / "plugins" / "jig"

# Resolved at import, before the sandbox scrubs the environment. The
# command strings in hooks.json invoke `sh` themselves, so varying only
# the shell that spawns them would leave the hook body on the system sh
# in every CI lane. The sandbox instead shims `sh` at the head of PATH:
# outer and inner shell then vary together, as they do on a real machine.
SHELL = shutil.which(os.environ.get("JIG_TEST_SHELL", "sh"))
assert SHELL, "JIG_TEST_SHELL does not name an available shell"


@pytest.fixture(autouse=True)
def sandbox(*, tmp_path: Path) -> Iterator[None]:
    saved = dict(os.environ)
    home = tmp_path / "home"
    home.mkdir()
    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "sh").symlink_to(SHELL)
    os.environ.clear()
    os.environ.update(
        {
            "PATH": f"{shim}:/usr/bin:/bin",
            "HOME": str(home),
            # Left uncreated: tests that need a populated JIG_HOME build it,
            # the rest exercise the unprovisioned paths.
            "JIG_HOME": str(tmp_path / "jig"),
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
        }
    )
    yield
    os.environ.clear()
    os.environ.update(saved)
