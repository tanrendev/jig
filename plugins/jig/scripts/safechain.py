"""Route agent package installs through Aikido safe-chain.

safe-chain protects interactive shells with aliases and CI with PATH shims,
but agent-spawned `bash -c` shells load neither, so the agent can install a
typosquatted package the user's own shell would have refused. This tool
closes that gap: explicit install commands are denied with the exact
re-run line that routes them through the shims, and denied outright when
safe-chain is absent.

Deny-and-reissue instead of an updatedInput rewrite is deliberate: a
rewrite needs permissionDecision "allow", which bypasses the permission
prompt, and updatedInput is silently ignored on PreToolUse anyway
(anthropics/claude-code#26506). "ask" is not an escape: it overrides
permissions.deny (#39344). Deny-and-reissue costs one round-trip per
install; installs are rare.

Wrapped-manager list and shim location (~/.safe-chain/shims, created by
the installer's --ci mode) come from the safe-chain README, v1.5.x:
https://github.com/AikidoSec/safe-chain
"""

import os
import re
from pathlib import Path

MATCH = {"hook_event_name": "PreToolUse", "tool_name": "Bash"}

# Explicit package-fetching commands, including run-on-demand fetchers
# (npx, uvx, pipx run) that install without ever saying "install".
INSTALLS = re.compile(
    r"""\b(?:
        (?:npm|pnpm|yarn|bun)\s+(?:-{1,2}\S+\s+)*(?:install|i|ci|add|update|upgrade|up)\b
      | (?:npx|pnpx|bunx|uvx)\s
      | pip3?\s+(?:-{1,2}\S+\s+)*install\b
      | python3?\s+-m\s+pip\s+install\b
      | uv\s+(?:add|sync)\b
      | uv\s+pip\s+install\b
      | uv\s+tool\s+(?:install|run)\b
      | poetry\s+(?:add|install|update)\b
      | pipx\s+(?:install|run)\b
      | pdm\s+(?:add|install|update)\b
    )""",
    re.VERBOSE,
)

DENY_MISSING = (
    "Package install blocked: Aikido safe-chain is not installed, so this "
    "install cannot be scanned for known-malicious packages. Run /jig:setup "
    "to install it, or set JIG_GUARD_ALLOW_UNSCANNED=1 to permit unscanned "
    "installs."
)


def shims_path() -> Path:
    return Path(os.environ.get("JIG_GUARD_SHIMS_DIR") or Path.home() / ".safe-chain" / "shims")


def scan_path_prefix() -> str:
    # The shims locate the scanner with `command -v safe-chain`, and the
    # binary lives in the bin dir next to the shims, which nothing else puts
    # on PATH. Wiring only the shims made the wrappers fail open (#1).
    shims = shims_path()
    return f"{shims}:{shims.parent / 'bin'}"


def run(*, event: dict) -> dict | None:
    command = (event.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not INSTALLS.search(command):
        return None
    shims = shims_path()
    if str(shims) in command or str(shims) in os.environ.get("PATH", ""):
        return None  # already routed through the shims
    if shims.is_dir():
        return {
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "Installs must run through the Aikido safe-chain malware "
                "scan. Re-run this exact command: "
                f'export PATH="{scan_path_prefix()}:$PATH"; {command}'
            ),
        }
    if os.environ.get("JIG_GUARD_ALLOW_UNSCANNED"):
        return None
    return {"permissionDecision": "deny", "permissionDecisionReason": DENY_MISSING}
