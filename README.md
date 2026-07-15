# jig

Plugin marketplace for Claude Code. One plugin:

- **guard**: PreToolUse guardrails. Today: routes agent-driven package
  installs through the [Socket Firewall free](https://github.com/SocketDev/sfw-free)
  malware scan and blocks installs that can't be scanned. Next:
  deny-list for destructive shell commands (rm -rf on roots and globs,
  force pushes, hard resets).

## Install

```
/plugin marketplace add tanrendev/jig
/plugin install guard@jig
```

The hooks run on a jig-managed Python runtime. Provision it, plus the
Socket Firewall scanner guard reissues installs through, with `/jig:setup`
(which discloses what the scanner phones home before installing), or from
the installed plugin directory:

```
sh scripts/setup.sh --with-sfw
```

Without the flag, setup provisions only the runtime. Everything lands
under `~/.local/share/jig` (override with `JIG_HOME`), pinned by version
and checksum; nothing else on the machine is read or modified. Until the
runtime exists, guard stays inactive and prints a notice instead of
blocking anything. Without the scanner, guard denies agent-driven
installs as unscannable (`JIG_GUARD_ALLOW_UNSCANNED=1` opts out).

## Repository layout

```
.claude-plugin/marketplace.json    catalog read by Claude Code
plugins/<name>/                    one directory per plugin
```
