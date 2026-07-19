---
description: Set up jig. Provision the managed runtime and Socket Firewall (once per machine), then configure this repo for the engineering skills (once per repo). Interactive; disclosure before anything is installed.
---

The user invoked jig's setup. It has two independent parts, each detecting
its own state and skipping itself when its work is already done:

1. **Machine**: provision guard's managed Python runtime and the malware
   scanner it routes agent-driven installs through.
2. **Repo**: configure this repository for the engineering skills (issue
   tracker, triage label vocabulary, domain doc layout).

# Part 1 — Machine

guard denies agent-driven package installs unless they route through a
malware scanner; this part provisions guard's managed Python runtime and
installs that scanner, Socket Firewall free (sfw).

If `~/.local/share/jig/bin/python3` and `~/.local/share/jig/bin/sfw` both
exist, the machine is already provisioned: say so and move on to Part 2
(re-running is only needed after a plugin update moves a pin).

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

# Part 2 — Repo

Scaffold the per-repo configuration that the engineering skills assume:

- **Issue tracker** — where issues live (GitHub by default; local markdown
  is also supported out of the box)
- **Triage labels** — the strings used for the canonical triage roles
- **Domain docs** — where `CONTEXT.md` and ADRs live, and the consumer
  rules for reading them

If `docs/agents/issue-tracker.md` already exists, this repo is configured:
say so and stop, unless the user asked to reconfigure (switching trackers,
restarting from scratch).

This is a prompt-driven part, not a deterministic script. Explore, present
what you found, confirm with the user, then write.

## Process

### 1. Explore

Look at the current repo to understand its starting state. Read whatever
exists; don't assume:

- `git remote -v` and `.git/config` — is this a GitHub repo? Which one?
- `AGENTS.md` and `CLAUDE.md` at the repo root — does either exist? Is
  there already an `## Agent skills` section in either?
- `CONTEXT.md` and `CONTEXT-MAP.md` at the repo root
- `docs/adr/` and any `src/*/docs/adr/` directories
- `docs/agents/` — does this part's prior output already exist?
- `.scratch/` — sign that a local-markdown issue tracker convention is
  already in use
- Monorepo signals — a `pnpm-workspace.yaml`, a `workspaces` field in
  `package.json`, or a populated `packages/*` with its own `src/`. Present
  only in a genuinely large multi-package repo; their absence means
  single-context, which is almost every repo.

### 2. Present findings and ask

Summarise what's present and what's missing. Then take the sections in
order — one section, one answer, then the next.

Lead each section with the recommended answer so the user can accept it in
a word. Give a one-line explainer only when the choice genuinely branches;
skip a section entirely when exploration already settled it (Section C
when there's no monorepo).

**Section A — Issue tracker.**

> Explainer: The "issue tracker" is where issues live for this repo.
> Skills like `to-tickets`, `triage`, and `to-spec` read from and write to
> it — they need to know whether to call `gh issue create`, write a
> markdown file under `.scratch/`, or follow some other workflow you
> describe. Pick the place you actually track work for this repo.

Default posture: these skills were designed for GitHub. If a `git remote`
points at GitHub, propose that. If a `git remote` points at GitLab
(`gitlab.com` or a self-hosted host), propose GitLab. Otherwise (or if the
user prefers), offer:

- **GitHub** — issues live in the repo's GitHub Issues (uses the `gh` CLI)
- **GitLab** — issues live in the repo's GitLab Issues (uses the
  [`glab`](https://gitlab.com/gitlab-org/cli) CLI)
- **Local markdown** — issues live as files under `.scratch/<feature>/` in
  this repo (good for solo projects or repos without a remote)
- **Other** (Jira, Linear, etc.) — ask the user to describe the workflow
  in one paragraph; record it as freeform prose

Record the choice in `docs/agents/issue-tracker.md`. The GitHub and GitLab
templates carry a "PRs as a request surface" flag, defaulted **off** —
leave it off and don't raise it; a user who wants external PRs in the
triage queue can flip the flag in the file later.

**Section B — Triage label vocabulary.** Ask exactly one question:

> Do you want to keep the default triage labels? (recommended: **yes**)

The defaults are the roles in the
[triage-labels.md](../scripts/setup/triage-labels.md) template: dash-free
state labels (`needs triage`, `needs info`, `ready for agent`,
`ready for human`, `wontfix`) and the categories `bug` and `feature`. On
**yes**, write the template as-is. Only if the user says no — usually
because their tracker already uses other names (e.g. `bug:triage` for
`needs-triage`) — collect the overrides so `triage` applies existing
labels instead of creating duplicates.

**Section C — Domain docs.** Default to **single-context** — one
`CONTEXT.md` + `docs/adr/` at the repo root. This fits almost every repo;
write it without asking.

Offer **multi-context** — a root `CONTEXT-MAP.md` pointing to per-context
`CONTEXT.md` files — only when exploration found monorepo signals. Then
confirm which layout they want.

### 3. Confirm and edit

Show the user a draft of:

- The `## Agent skills` block to add to whichever of `CLAUDE.md` /
  `AGENTS.md` is being edited (see step 4 for selection rules)
- The contents of `docs/agents/issue-tracker.md`,
  `docs/agents/triage-labels.md`, and `docs/agents/domain.md`

Let them edit before writing.

### 4. Write

**Pick the file to edit:**

- If `CLAUDE.md` exists, edit it.
- Else if `AGENTS.md` exists, edit it.
- If neither exists, ask the user which one to create — don't pick for
  them.

Never create `AGENTS.md` when `CLAUDE.md` already exists (or vice versa) —
always edit the one that's already there.

If an `## Agent skills` block already exists in the chosen file, update
its contents in-place rather than appending a duplicate. Don't overwrite
user edits to the surrounding sections.

The block:

```markdown
## Agent skills

### Issue tracker

[one-line summary of where issues are tracked]. See `docs/agents/issue-tracker.md`.

### Triage labels

[one-line summary of the label vocabulary]. See `docs/agents/triage-labels.md`.

### Domain docs

[one-line summary of layout — "single-context" or "multi-context"]. See `docs/agents/domain.md`.
```

Then write the docs files using the seed templates under
`${CLAUDE_PLUGIN_ROOT}/scripts/setup/` as a starting point:

- `issue-tracker-github.md` — GitHub issue tracker
- `issue-tracker-gitlab.md` — GitLab issue tracker
- `issue-tracker-local.md` — local-markdown issue tracker
- `triage-labels.md` — label mapping
- `domain.md` — domain doc consumer rules + layout

For "other" issue trackers, write `docs/agents/issue-tracker.md` from
scratch using the user's description.

### 5. Done

Tell the user the setup is complete and which engineering skills will now
read from these files. Mention they can edit `docs/agents/*.md` directly
later — re-running this part is only necessary to switch issue trackers or
restart from scratch.
