# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
# 3.14 floor: parenthesis-free multi-exception except (PEP 758) and deferred
# annotation evaluation (PEP 649). The managed runtime (setup.sh) is newer.
"""guard entrypoint: reads a hook event on stdin, runs the tools it matches.

hooks.json registers this one script for every event guard handles; new
tools plug into TOOLS without touching the hook definitions.

Usage:
  guard.py           run every tool whose MATCH fits the event
  guard.py <tool>    run one tool by name (manual testing)

Tool contract: a module with MATCH (event fields it applies to) and
run(*, event) returning a hookSpecificOutput payload without hookEventName,
or None to stay silent. Tools never return "allow": an allow decision
bypasses the permission prompt, and a guard must not widen permissions.
Deny or say nothing.
"""

import json
import sys
from typing import TYPE_CHECKING

import preflight
import safechain

if TYPE_CHECKING:
    from types import ModuleType

TOOLS = {"safechain": safechain, "preflight": preflight}


def matches(*, tool: ModuleType, event: dict) -> bool:
    return all(event.get(key) == want for key, want in tool.MATCH.items())


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else None
    if name is not None and name not in TOOLS:
        sys.exit(f"guard: unknown tool {name!r} (have: {', '.join(sorted(TOOLS))})")
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError, UnicodeDecodeError:
        return  # not a payload we can judge; stay out of the way
    tools = [TOOLS[name]] if name else [t for t in TOOLS.values() if matches(tool=t, event=event)]
    for tool in tools:
        out = tool.run(event=event)
        if out:
            sys.stdout.write(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": event.get("hook_event_name", "PreToolUse"),
                            **out,
                        }
                    }
                )
                + "\n"
            )
            return


if __name__ == "__main__":
    main()
