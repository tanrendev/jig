"""Deny agent package installs that cannot be scanned for malware.

Interactive shells sit behind whatever supply-chain tooling the user set
up, but agent-spawned `bash -c` shells inherit none of it, so the agent
could fetch a typosquatted package the user's own shell would have
refused. Guard fails closed: until a scanner is integrated (#8), every
explicit install is denied, with JIG_GUARD_ALLOW_UNSCANNED=1 as the
escape for users who accept unscanned installs.
"""

import os
import re

MATCH = {"hook_event_name": "PreToolUse", "tool_name": "Bash"}

# Explicit package-fetching commands, including run-on-demand fetchers
# (npx, uvx, pipx run) that install without ever saying "install".
# An option before the subcommand may carry one value token (--index-url
# URL); backtracking keeps the subcommand itself from being eaten as a
# value, so `pip -q install` still matches.
_OPTS = r"(?:-{1,2}\S+(?:\s+[^-\s]\S*)?\s+)*"
INSTALLS = re.compile(
    rf"""\b(?:
        (?:npm|pnpm|yarn|bun)\s+{_OPTS}(?:install|i|ci|add|update|upgrade|up)\b
      | (?:npx|pnpx|bunx|uvx)\s
      | pip(?:3(?:\.\d+)?)?\s+{_OPTS}install\b
      | python(?:3(?:\.\d+)?)?\s+-m\s+pip\s+{_OPTS}install\b
      | uv\s+(?:add|sync)\b
      | uv\s+pip\s+install\b
      | uv\s+tool\s+(?:install|run)\b
      | poetry\s+(?:add|install|update)\b
      | pipx\s+(?:install|run)\b
      | pdm\s+(?:add|install|update)\b
    )""",
    re.VERBOSE,
)

DENY = (
    "Package install blocked: no malware scanner is integrated, so this "
    "install cannot be scanned for known-malicious packages. Set "
    "JIG_GUARD_ALLOW_UNSCANNED=1 to permit unscanned installs."
)


def run(*, event: dict) -> dict | None:
    command = (event.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not INSTALLS.search(command):
        return None
    # Exactly "1": a fail-closed guard must not be switched off by a value
    # (0, false) that reads as an attempt to switch it on.
    if os.environ.get("JIG_GUARD_ALLOW_UNSCANNED") == "1":
        return None
    return {"permissionDecision": "deny", "permissionDecisionReason": DENY}
