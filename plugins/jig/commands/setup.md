---
description: Install the Aikido safe-chain malware scanner that guard routes agent-driven package installs through. Interactive; shows what it will do before installing.
---

The user invoked guard's setup. guard blocks agent-driven package installs
unless they route through a malware scanner; this installs that scanner,
Aikido safe-chain.

First tell the user, concisely, what running this does:

- Ensures guard's managed Python runtime exists under `~/.local/share/jig`
  (pinned uv and CPython; already present if guard has run a session).
- Downloads and runs Aikido safe-chain's official installer (`--ci` mode)
  from `github.com/AikidoSec/safe-chain` into `~/.safe-chain`, writing shim
  commands (`npm`, `pip`, `uv`, and others) that check each package against
  Aikido's malware feed before download. The installer is fetched over the
  network and is version-pinned but not checksum-verified.
- Nothing else on the machine is modified.

Then run:

```
sh "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" --with-safechain
```

Then report the result. The script prints whether safe-chain installed; if
it failed, surface the error rather than claiming success. Tell the user
scanning becomes active in each new session, when guard prepends the shims
onto PATH, so this already-running shell is not covered: a new session or
terminal is needed for full effect.
