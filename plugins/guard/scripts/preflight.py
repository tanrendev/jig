"""Session-start environment report for guard.

The SessionStart wrapper in hooks.json verifies the managed runtime before
this runs (a Python tool cannot report its own interpreter missing), so the
checks left here are drift checks: is safe-chain present, and does the
provisioned runtime still match the pin this plugin version ships?
Enforcement in safechain.py re-checks its own facts per call regardless:
session state drifts, and additionalContext advises the model, it gates
nothing.
"""

import os
import re
from pathlib import Path

from safechain import shims_path

MATCH = {"hook_event_name": "SessionStart"}

PIN_LINE = re.compile(r'^PYTHON_VERSION="([^"]+)"$', re.MULTILINE)

SAFECHAIN_WARNING = (
    "guard: Aikido safe-chain is not installed on this machine, so "
    "agent-driven package installs will be denied rather than run "
    "unscanned. Tell the user early if installs are likely in this "
    "session: they can install safe-chain from "
    "https://github.com/AikidoSec/safe-chain (installer with --ci so PATH "
    "shims exist) or set JIG_GUARD_ALLOW_UNSCANNED=1 to accept unscanned "
    "installs."
)


def jig_home() -> Path:
    return Path(os.environ.get("JIG_HOME") or Path.home() / ".local" / "share" / "jig")


def runtime_warning() -> str | None:
    # The pin ships with the plugin (setup.sh is the single home for it);
    # the stamp records what setup.sh last provisioned on this machine.
    try:
        pin = PIN_LINE.search(Path(__file__).with_name("setup.sh").read_text())
        provisioned = (jig_home() / ".python-pin").read_text().strip()
    except OSError:
        return None  # unprovisioned or pre-stamp install; the wrapper covers missing runtimes
    if pin is None or provisioned == pin.group(1):
        return None
    return (
        f"guard: the managed runtime is Python {provisioned} but this "
        f"plugin version pins {pin.group(1)}. Tell the user to re-run "
        "scripts/setup.sh from the guard plugin to update it."
    )


def safechain_warning() -> str | None:
    if os.environ.get("JIG_GUARD_ALLOW_UNSCANNED"):
        return None  # the user opted out; don't nag every session
    shims = shims_path()
    if shims.is_dir() or str(shims) in os.environ.get("PATH", ""):
        return None
    return SAFECHAIN_WARNING


def run(*, event: dict) -> dict | None:  # noqa: ARG001  uniform tool contract
    warnings = [w for w in (runtime_warning(), safechain_warning()) if w]
    if not warnings:
        return None
    return {"additionalContext": "\n\n".join(warnings)}
