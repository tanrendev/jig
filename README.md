# jig

Plugin marketplace for Claude Code. One plugin:

- **guard**: PreToolUse guardrails. Today: blocks agent-driven package
  installs that can't be scanned for malware; the scanner integration is
  being swapped ([#8](https://github.com/tanrendev/jig/issues/8)). Next:
  deny-list for destructive shell commands (rm -rf on roots and globs,
  force pushes, hard resets).

## Install

```
/plugin marketplace add tanrendev/jig
/plugin install guard@jig
```

The hooks run on a jig-managed Python runtime. Provision it once
(and re-run after a version-pin bump) from the installed plugin directory:

```
sh scripts/setup.sh
```

This pins uv and CPython under `~/.local/share/jig` (override with
`JIG_HOME`); nothing else on the machine is read or modified. Until it runs,
guard stays inactive and prints a notice instead of blocking anything.

## Repository layout

```
.claude-plugin/marketplace.json    catalog read by Claude Code
plugins/<name>/                    one directory per plugin
documentation/                     contributor docs; testing.md is the test strategy
```
