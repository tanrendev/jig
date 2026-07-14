# jig

Guardrail hooks for Claude Code, packaged as one plugin. Features:

- **guard**: PreToolUse guardrails. Today: routes agent-driven package
  installs through the Aikido safe-chain malware scan and blocks installs
  that can't be scanned. Next: deny-list for destructive shell commands
  (rm -rf on roots and globs, force pushes, hard resets).

## Install

```
/plugin marketplace add tanrendev/jig
/plugin install jig@jig
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
plugins/jig/                       the plugin: commands, hooks, scripts
```
