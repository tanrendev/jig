# jig

Every commit gets the trailer
`Co-Authored-By: Claude <noreply@anthropic.com>`.

Always pass function arguments as keyword arguments, in Python code and in
calls to Python APIs, unless the parameter is positional-only.

Declare function signatures keyword-only: a bare `*` before the first
parameter of every function and method we define.

## Labels

Labels apply to issues and PRs alike. Every issue and PR gets exactly one
`type::` label.

- `type::bug`: Something works differently than intended or documented
- `type::feature`: New capability or change in behavior
- `type::maintenance`: Deps, CI, tooling, refactors, tech debt. No user-visible change
- `type::docs`: Documentation only
- `security`: Touches a trust boundary, secret handling, or a vulnerability
- `breaking change`: Requires user action on upgrade
- `agent-authored`: Issue body or PR content written or co-written by an AI agent
- `blocked`: Waiting on something external. Name the blocker in a comment
- `good first issue`: Agreed on, well defined, likely to merge. Small scope (issues only)
- `help wanted`: Agreed on and open to a contributor, any size (issues only)

When asked to create an issue or PR, add the `agent-authored` label to it.
