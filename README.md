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
documentation/                     contributor docs; testing.md is the test strategy
```

## Third-party

Part of `plugins/jig/skills/` originates from
[mattpocock/skills](https://github.com/mattpocock/skills), used under the
MIT License; the rest are my own:

<details>
<summary>MIT License, Copyright (c) 2026 Matt Pocock</summary>

```
MIT License

Copyright (c) 2026 Matt Pocock

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

</details>
