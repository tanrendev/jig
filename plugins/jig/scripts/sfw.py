"""Route agent package installs through the Socket Firewall (sfw) scan.

Interactive shells sit behind whatever supply-chain tooling the user set
up, but agent-spawned `bash -c` shells inherit none of it, so the agent
could fetch a typosquatted package the user's own shell would have
refused. This tool closes that gap: explicit install commands are denied
with the exact re-run line that routes them through sfw, and denied
outright when sfw is absent.

Deny-and-reissue instead of an updatedInput rewrite is deliberate: a
rewrite needs permissionDecision "allow", which bypasses the permission
prompt, and updatedInput is silently ignored on PreToolUse anyway
(anthropics/claude-code#26506). Deny-and-reissue costs one round-trip per
install; installs are rare.

sfw wraps the command it is given with env vars (HTTPS_PROXY, PIP_CERT,
NODE_EXTRA_CA_CERTS, ...) that route package fetches through an ephemeral
local proxy, which checks each fetch against Socket's feed and 403s
confirmed malware. Spike notes with the observed behavior per command
form and per outage shape: https://github.com/tanrendev/jig/issues/8

The scan is defeatable by design. A reissued command that clears the
injected environment (env -i, unset) fetches outside the proxy, the same
ceiling safe-chain's PATH shims had. This raises the cost of a naive
unscanned install; it is not a sandbox. Closing that gap needs egress
control, which is out of scope here.
"""

import os
import re
import shlex
from pathlib import Path

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
    flags=re.VERBOSE,
)

# The one guarded form that cannot complete behind the scan: poetry's
# TLS stack trusts only certifi and sfw does not export
# REQUESTS_CA_BUNDLE, so every fetch dies on "unknown ca". Reissuing it
# would trade this deny for a misleading SSL error, hence deny-only.
POETRY = re.compile(r"\bpoetry\s+(?:add|install|update)\b")

DENY_MISSING = (
    "Package install blocked: Socket Firewall (sfw) is not installed, so "
    "this install cannot be scanned for known-malicious packages. Run "
    "/jig:setup to install it, or set JIG_GUARD_ALLOW_UNSCANNED=1 to "
    "permit unscanned installs."
)

DENY_POETRY = (
    "Package install blocked: poetry cannot install behind the Socket "
    "Firewall scan (its TLS stack rejects the scan proxy), so this "
    "install cannot be scanned. Prefer pip or uv here, or set "
    "JIG_GUARD_ALLOW_UNSCANNED=1 to permit unscanned installs."
)


def sfw_path() -> Path:
    return Path(os.environ.get("JIG_HOME") or Path.home() / ".local" / "share" / "jig") / "bin" / "sfw"


def allow_unscanned() -> bool:
    # Exactly "1": a fail-closed guard must not be switched off by a value
    # (0, false) that reads as an attempt to switch it on.
    return os.environ.get("JIG_GUARD_ALLOW_UNSCANNED") == "1"


def reissue(*, sfw: Path, command: str) -> str:
    # sh -c, not a bare prefix: a prefix would guard only the first word
    # of a compound command (`cd x && npm i`); the proxy env sfw injects
    # reaches every install inside the nested shell.
    return f'"{sfw}" sh -c {shlex.quote(command)}'


def is_routed(*, sfw: Path, command: str) -> bool:
    # Accept only the exact reissue shape: sfw path, `sh`, `-c`, one
    # payload token. A prefix test would exempt anything that merely
    # starts with the (deterministic) sfw path, so `"$sfw" true; npm i
    # evil` would run the install after the `;` outside the scan.
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False  # unbalanced quotes: not a reissue we produced
    match tokens:
        case [path, "sh", "-c", _]:
            return path == str(sfw)
        case _:
            return False


def run(*, event: dict) -> dict | None:
    command = (event.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not INSTALLS.search(command):
        return None
    sfw = sfw_path()
    if is_routed(sfw=sfw, command=command):
        return None
    if POETRY.search(command):
        reason = None if allow_unscanned() else DENY_POETRY
    elif not sfw.is_file():
        reason = None if allow_unscanned() else DENY_MISSING
    else:
        reason = (
            "Installs must run through the Socket Firewall malware scan. "
            f"Re-run this exact command: {reissue(sfw=sfw, command=command)}"
        )
    return {"permissionDecision": "deny", "permissionDecisionReason": reason} if reason else None
