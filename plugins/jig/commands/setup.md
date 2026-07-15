---
description: Provision the jig-managed runtime and install Socket Firewall, the malware scanner guard routes agent-driven package installs through. Interactive; disclosure before anything is installed.
---

The user invoked jig's setup. guard denies agent-driven package installs
unless they route through a malware scanner; this provisions guard's
managed Python runtime and installs that scanner, Socket Firewall free
(sfw).

First tell the user, concisely, what running this does:

- Installs a pinned uv and CPython under `~/.local/share/jig` (a no-op
  if guard has already provisioned them on this machine).
- Downloads the Socket Firewall free binary from
  `github.com/SocketDev/sfw-free`, pinned by version and sha256, into
  `~/.local/share/jig/bin/sfw`. The binary has no self-updater; only a
  plugin update moves the pin.
- Nothing else on the machine is modified.

And disclose, before running anything, what using Socket Firewall means:

- Proprietary license (PolyForm Shield 1.0.0). Free of charge, no
  account, no API key.
- Always-on telemetry: Socket receives a machine identifier, the names
  and versions of the packages installs fetch, and GitHub organization
  names taken from git remotes.
- Blocking threshold: only malware confirmed by human review is blocked.
  Packages flagged by AI but not yet confirmed print a warning and
  install anyway.
- Cache blind spot: sfw checks packages as they are fetched. Anything
  served from a warm local cache (npm cache, uv cache, pnpm store) never
  reaches the scanner and installs unscanned.
- If Socket's API is unreachable, the wrapped install fails safe: the
  command runs nothing and prints the error to stderr (exiting 0, so
  read the output, not the exit code).

Then, if the user consents, run:

```
sh "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" --with-sfw
```

Then report the result; if it failed, surface the error rather than
claiming success. If the script prints a note about a leftover
`~/.safe-chain` directory, relay it verbatim: earlier jig versions
installed that scanner, and setup never deletes it because the
directory may predate jig.
