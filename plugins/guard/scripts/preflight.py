"""Session-start environment report for guard.

The SessionStart wrapper in hooks.json verifies the managed runtime before
this runs (a Python tool cannot report its own interpreter missing), so the
only check left here is safe-chain. Enforcement in safechain.py re-checks
per call regardless: session state drifts, and additionalContext advises
the model, it gates nothing.
"""

import os

from safechain import shims_path

MATCH = {"hook_event_name": "SessionStart"}

WARNING = (
    "guard: Aikido safe-chain is not installed on this machine, so "
    "agent-driven package installs will be denied rather than run "
    "unscanned. Tell the user early if installs are likely in this "
    "session: they can install safe-chain from "
    "https://github.com/AikidoSec/safe-chain (installer with --ci so PATH "
    "shims exist) or set JIG_GUARD_ALLOW_UNSCANNED=1 to accept unscanned "
    "installs."
)


def run(*, event: dict) -> dict | None:  # noqa: ARG001  uniform tool contract
    if os.environ.get("JIG_GUARD_ALLOW_UNSCANNED"):
        return None  # the user opted out; don't nag every session
    shims = shims_path()
    if shims.is_dir() or str(shims) in os.environ.get("PATH", ""):
        return None
    return {"additionalContext": WARNING}
