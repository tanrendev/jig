# Test strategy

This document governs every test in this repository. Read it before writing
or changing a test; it is irrelevant to any other work. It is written against
the Claude Code plugin contract and deliberately says nothing about the
current implementation of any script, so it should survive rewrites of the
code behind it.

## The system under test

A Claude Code plugin, stripped of implementation, is two things:

1. Manifests (`marketplace.json`, `plugin.json`, `hooks.json`) that the host
   parses and trusts.
2. Hook processes the host spawns. The host writes a JSON payload to stdin,
   sets environment variables such as `CLAUDE_PLUGIN_ROOT`, reads back an
   exit code and stdout JSON, and enforces a per-hook timeout.

That process boundary is the only interface users ever touch, and it survives
every rewrite of the scripts behind it. Tests concentrate there. Code
internals get tests only where real logic with a real input space exists
behind the boundary.

One property is specific to hooks and shapes the whole strategy: a hook that
fails must never break the user's session. A library that crashes fails its
own caller; a broken SessionStart hook damages every session on the machine,
and a malformed PreToolUse response can silently turn a deny into an allow.
Failure paths are first-class test subjects here, never afterthoughts.

## Choosing where a test goes

Work down this list and stop at the first match:

1. Does the behavior only exist when the host runs a hook end to end
   (environment, stdin, exit code, stdout)? Tier 1.
2. Is it a static fact about the manifests (a referenced path exists, a
   version matches)? Tier 2.
3. Is it a pure function with an input space too large to enumerate readably
   at the process boundary? Tier 3.

Behavior that only shows over the network or inside a real Claude Code
session (cold provisioning, live host drift) is out of scope for this
suite: the cost of running it outweighs what it would catch at this size.

If a candidate test needs mocks or filesystem fakes, it is misplaced in
tier 3; move it up to tier 1.

## Tier 1: hook integration tests

The bulk of the suite. Each test runs a hook exactly as the host runs it: a
subprocess with a payload on stdin, asserting only what the host observes
(exit code, stdout JSON, stderr).

### The verbatim rule

Tests parse `hooks.json` and execute its command strings as found. Re-typing
a command into a test is forbidden, for two reasons:

- The one-liners embedded in `hooks.json` are code, and executing them
  verbatim is the only way to test them at all.
- Drift between manifest and tests becomes impossible: editing the command in
  `hooks.json` changes what the tests run, automatically.

### Sandbox

An autouse fixture gives every test a hermetic environment:

- `HOME` and `JIG_HOME` point into `tmp_path`.
- `CLAUDE_PLUGIN_ROOT` points at the real plugin directory in the working
  tree.
- Everything else is scrubbed from the environment; a test declares any extra
  variable it needs.

Hermetic means isolated from mutable host state, and no more than that.
Read-only access to the working tree (the plugin directory, `hooks.json`) is
expected; the verbatim rule depends on it. A test that writes outside its
`tmp_path`, or reads mutable host state such as the real `HOME` or the real
`~/.local/share/jig`, is a bug in the test, whatever it asserts.

### Payload fixtures

Hook input payloads are checked-in JSON files captured from real Claude Code
sessions, with the host version recorded alongside each capture. Tests derive
variants (edit one field, drop one field) in code from those captures. The
payload schema belongs to the host and will change; when it does, refreshing
the captures updates the whole suite in one place.

### Required case matrix

Every hook, whatever it does, gets at least these cases:

- Happy path: a well-formed payload produces the expected decision in stdout
  JSON and the expected exit code.
- The blocking path, where the hook has one: the deny decision is present and
  well-formed. A malformed deny silently becomes an allow, which makes this
  the highest-value single assertion in the suite.
- Malformed stdin: invalid JSON, empty input, and valid JSON of the wrong
  shape.
- Missing prerequisites: no managed runtime, an unwritable `JIG_HOME`. The
  session-safety invariant must hold and the output must be something the
  host treats as non-blocking.
- Time budget: the hook finishes comfortably inside the timeout declared in
  `hooks.json`. The host kills it at the wall, and what happens after a kill
  is host policy this repo does not control.

### Shell matrix, no Python matrix

The command strings run under whatever `/bin/sh` is on the user's machine; on
Debian-family systems that is dash. Tier 1 runs under both dash and bash in
CI.

There is no Python version matrix. The plugin provisions its own pinned
runtime, so any other interpreter version is a configuration that cannot
occur in the field. This inverts the usual library setup, where the
interpreter matrix is the backbone of CI.

## Tier 2: manifest checks

One small file of static checks, no subprocesses:

- All manifests parse as JSON.
- Every plugin listed in `marketplace.json` exists in the tree.
- Every path a manifest references (scripts, commands, hook targets) exists.
- Hook event names and matcher fields are values the host defines.
- The plugin version matches `pyproject.toml` (the commitizen sync happened).

Trivially cheap, and it catches the entire class of "released a plugin that
does not load", which no amount of script testing reaches.

## Tier 3: unit tests

A unit test is justified for a pure function whose input space is large
enough that enumerating it at the process boundary would be slow or
unreadable. Command-string classification (is this a package install, which
ecosystem, can it be scanned) is the canonical example.

Rules:

- Table-driven `pytest.mark.parametrize`; the table is the spec.
- Every regression adds a row citing the issue number in a comment.
- No mocks, no filesystem fakes, no monkeypatching. Needing one means the
  test belongs in tier 1.
- The implementation owes this tier one thing only: parsing and
  classification logic extracted into pure functions. That is the single
  demand the strategy makes of code structure.

## Suite-wide policy

- `filterwarnings = ["error"]`: every warning fails the suite.
- The suite is offline. A test that needs the network has no tier to live
  in and does not get written.
- No coverage gate. At this size a percentage invites gaming; the tier 1 case
  matrix is the coverage policy. Revisit if the plugin count grows.
- Plain pytest, zero plugins. Add `pytest-xdist` when the suite crosses
  roughly a minute of wall time, and nothing else without a concrete need.
- Functional `def test_*` style, no test classes. The house keyword-only
  convention applies to test helpers like any other code.
- No fixture for what a local variable can do; no parametrize for a single
  case.
- Layout: flat `tests/`, one file per plugin and tier
  (`test_<plugin>_hooks.py`, `test_manifests.py`,
  `test_<plugin>_<topic>.py` for units). Split into directories when a
  second plugin makes flat hurt, and only then.

## CI

Per PR: the whole suite, once under dash and once under bash. Lint and
typing stay in their existing jobs.

## Deliberately not used

- Hypothesis: the input space is command strings with known shapes; a
  parametrize table is clearer and faster.
- Snapshot libraries: hook outputs are small JSON documents; literal expected
  values read better.
- Mocking frameworks: excluded by the tier rules above.
- tox and nox: uv already owns environments.
- Coverage tooling: no gate, so no infrastructure.
- Network-dependent end-to-end tests (cold provisioning against the real
  installers, headless `claude` runs): dropped as not worth their cost at
  the current size. Revisit if a provisioning regression ever ships.
- A shared test-helper module: extract a helper when two files duplicate it,
  and only what they duplicate.

## Provenance

The strategy comes from a July 2026 survey of the test suites of Django,
Flask, FastAPI, pandas, and requests. What was borrowed:

- Warnings as errors: universal across all five.
- Hermeticity through autouse fixtures: Flask (context-leak detector, env
  pinning) and requests (proxy-variable scrubbing).
- Testing at the boundary users actually hit: FastAPI, which runs its
  documentation examples as the test suite.
- Regression rows citing issue numbers: requests and pandas.
- No coverage gate: three of the five enforce none, and the exception
  (FastAPI) gates at exactly 100 percent. Nothing in between exists in that
  population, which reads as a verdict on intermediate thresholds.
