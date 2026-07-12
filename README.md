# jig

Plugin marketplace for Claude Code. One plugin:

- **guard**: blocks destructive shell commands (rm -rf on roots and globs,
  force pushes, hard resets) in a PreToolUse hook before they run.

## Install

```
/plugin marketplace add tanrendev/jig
/plugin install guard@jig
```

## Repository layout

```
.claude-plugin/marketplace.json    catalog read by Claude Code
plugins/<name>/                    one directory per plugin
```
