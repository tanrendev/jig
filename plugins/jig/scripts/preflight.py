"""Session-start drift report for guard.

Reports what per-call enforcement cannot see: the provisioned runtime no
longer matching the pin this plugin version ships, or the install scanner
missing. The SessionStart wrapper in hooks.json verifies the managed
runtime before this runs (a Python tool cannot report its own interpreter
missing). additionalContext advises the model, it gates nothing.
"""

import os
import re
from pathlib import Path

MATCH = {"hook_event_name": "SessionStart"}

PIN_LINE = re.compile(r'^PYTHON_VERSION="([^"]+)"$', re.MULTILINE)


def jig_home() -> Path:
    return Path(os.environ.get("JIG_HOME") or Path.home() / ".local" / "share" / "jig")


def scanner_warning() -> str | None:
    if os.environ.get("JIG_GUARD_ALLOW_UNSCANNED") == "1":
        return None  # the user accepts unscanned installs; nothing to nag about
    if (jig_home() / "bin" / "sfw").is_file():
        return None
    return (
        "guard: Socket Firewall (sfw) is not installed, so agent package "
        "installs will be denied as unscannable. Tell the user to run "
        "/jig:setup to install it."
    )


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
        "scripts/setup.sh from the jig plugin to update it."
    )


def run(*, event: dict) -> dict | None:  # noqa: ARG001  uniform tool contract
    warnings = [w for w in (runtime_warning(), scanner_warning()) if w]
    return {"additionalContext": " ".join(warnings)} if warnings else None
