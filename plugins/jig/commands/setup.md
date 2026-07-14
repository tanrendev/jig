---
description: Provision the jig-managed Python runtime that guard's hooks run on. Interactive; shows what it will do before running.
---

The user invoked jig's setup. guard's hooks exec a managed Python
runtime; this provisions it (or updates it after a version-pin bump).

First tell the user, concisely, what running this does:

- Installs a pinned uv and CPython under `~/.local/share/jig` (a no-op
  if guard has already provisioned them on this machine).
- Nothing else on the machine is modified.

Then run:

```
sh "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh"
```

Then report the result; if it failed, surface the error rather than
claiming success. If the script prints a note about a leftover
`~/.safe-chain` directory, relay it verbatim: earlier jig versions
installed that scanner, and setup never deletes it because the
directory may predate jig.
