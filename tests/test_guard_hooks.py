"""Tier 1: guard hooks run exactly as the host runs them.

Commands come verbatim from hooks.json and execute under JIG_TEST_SHELL
(default sh); CI runs the suite once under dash and once under bash. Each
run passes the hook's declared timeout to subprocess.run, so the time
budget is asserted on every test, not in one.
"""

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import PLUGIN_ROOT

HOOKS = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text())
SESSION = HOOKS["hooks"]["SessionStart"][0]["hooks"][0]
PRETOOL = HOOKS["hooks"]["PreToolUse"][0]["hooks"][0]

SESSION_EVENT = {"hook_event_name": "SessionStart"}

RUNTIME_PIN = re.search(
    r'^PYTHON_VERSION="([^"]+)"$', (PLUGIN_ROOT / "scripts" / "setup.sh").read_text(), flags=re.MULTILINE
).group(1)


def bash_event(*, command: str) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}}


def run_hook(*, hook: dict, stdin: str) -> subprocess.CompletedProcess[str]:
    # Bare `sh`: resolves to the shim the sandbox put first in PATH, so
    # this and the `sh` inside the command string are the same interpreter.
    return subprocess.run(
        ["sh", "-c", hook["command"]],  # noqa: S607
        input=stdin,
        capture_output=True,
        text=True,
        timeout=hook["timeout"],
        check=False,
    )


def output(*, proc: subprocess.CompletedProcess[str]) -> dict | None:
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    return json.loads(out)["hookSpecificOutput"] if out else None


def pretool(*, command: str) -> dict | None:
    return output(proc=run_hook(hook=PRETOOL, stdin=json.dumps(bash_event(command=command))))


def session() -> dict | None:
    return output(proc=run_hook(hook=SESSION, stdin=json.dumps(SESSION_EVENT)))


@pytest.fixture
def runtime() -> Path:
    # The managed runtime the wrappers exec: the current interpreter,
    # linked where hooks.json expects it. No scanner.
    home = Path(os.environ["JIG_HOME"])
    (home / "bin").mkdir(parents=True)
    (home / "bin" / "python3").symlink_to(sys.executable)
    return home


@pytest.fixture
def scanner(*, runtime: Path) -> Path:
    sfw = runtime / "bin" / "sfw"
    sfw.write_text("#!/bin/sh\nexit 0\n")
    return sfw


@pytest.fixture
def stamp(*, runtime: Path) -> Path:
    # A stamp matching the shipped pin, so runtime drift is what varies.
    pin = runtime / ".python-pin"
    pin.write_text(f"{RUNTIME_PIN}\n")
    return pin


# --- PreToolUse: install enforcement ---


def test_non_install_command_passes(*, runtime: Path) -> None:
    assert pretool(command="git status") is None


def test_install_denied_when_scanner_missing(*, runtime: Path) -> None:
    out = pretool(command="pip install requests")
    # The full deny shape, field by field: a malformed deny silently
    # becomes an allow, making this the suite's highest-value assertion.
    assert out["hookEventName"] == "PreToolUse"
    assert out["permissionDecision"] == "deny"
    reason = out["permissionDecisionReason"]
    assert "JIG_GUARD_ALLOW_UNSCANNED" in reason
    assert "/jig:setup" in reason


@pytest.mark.parametrize("command", ["npm install left-pad", "cd sub && npm install left-pad --ignore-scripts"])
def test_install_reissued_through_sfw(*, command: str, scanner: Path) -> None:
    out = pretool(command=command)
    assert out["permissionDecision"] == "deny"
    # The reissue must be the whole command behind sh -c: a bare prefix
    # would guard only the first word of a compound command.
    assert f'"{scanner}" sh -c {shlex.quote(command)}' in out["permissionDecisionReason"]


def test_reissued_command_passes(*, scanner: Path) -> None:
    denied = pretool(command="npm install left-pad")
    reissued = denied["permissionDecisionReason"].split("Re-run this exact command: ")[1]
    assert pretool(command=reissued) is None


def test_non_canonical_wrapper_is_denied(*, scanner: Path) -> None:
    # Only the byte-exact reissue is exempt; a wrapper with a smuggled
    # tail must stay denied. The classifier edges live in tier 3.
    out = pretool(command=f"\"{scanner}\" sh -c ':'; npm install attacker")
    assert out["permissionDecision"] == "deny"


def test_wrapped_poetry_stays_deny_only(*, scanner: Path) -> None:
    # Hand-wrapping poetry must not earn the routed exemption: poetry
    # cannot install behind the scan, so it stays deny-only.
    out = pretool(command=f"\"{scanner}\" sh -c 'poetry install'")
    assert out["permissionDecision"] == "deny"
    assert "poetry" in out["permissionDecisionReason"]


def test_poetry_denied_without_reissue(*, scanner: Path) -> None:
    out = pretool(command="poetry add requests")
    assert out["permissionDecision"] == "deny"
    assert "poetry" in out["permissionDecisionReason"]
    assert "sh -c" not in out["permissionDecisionReason"]


def test_optout_allows_unscanned_install(*, runtime: Path) -> None:
    os.environ["JIG_GUARD_ALLOW_UNSCANNED"] = "1"
    assert pretool(command="pip install requests") is None


@pytest.mark.parametrize("value", ["0", "false", "yes"])
def test_optout_requires_the_documented_value(*, value: str, runtime: Path) -> None:
    os.environ["JIG_GUARD_ALLOW_UNSCANNED"] = value
    assert pretool(command="pip install requests") is not None


def test_scanner_present_ignores_optout(*, scanner: Path) -> None:
    # The escape covers what cannot be scanned; a working scanner still scans.
    os.environ["JIG_GUARD_ALLOW_UNSCANNED"] = "1"
    assert pretool(command="npm install left-pad") is not None


def test_missing_runtime_stays_silent() -> None:
    # No managed runtime: the wrapper must not block the tool call, and
    # PreToolUse never provisions (a tool call must not wait on a download).
    proc = run_hook(hook=PRETOOL, stdin=json.dumps(bash_event(command="npm install x")))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""


@pytest.mark.parametrize("stdin", ["not json", ""])
def test_malformed_stdin_stays_silent(*, stdin: str, runtime: Path) -> None:
    proc = run_hook(hook=PRETOOL, stdin=stdin)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""


@pytest.mark.parametrize("stdin", ["[]", '"npm install x"', '{"tool_input": {"command": "npm install x"}}'])
def test_wrong_shape_payload_never_blocks(*, stdin: str, runtime: Path) -> None:
    # Valid JSON of the wrong shape. Some of these crash guard today;
    # what matters to the host is no stdout and no blocking exit code.
    proc = run_hook(hook=PRETOOL, stdin=stdin)
    assert proc.returncode != 2
    assert proc.stdout == ""


def test_non_matching_event_skips_enforcement(*, runtime: Path) -> None:
    event = {"hook_event_name": "PostToolUse", "tool_input": {"command": "npm install x"}}
    proc = run_hook(hook=PRETOOL, stdin=json.dumps(event))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""


# --- SessionStart: provisioning and the preflight report ---


def test_session_silent_when_current(*, scanner: Path, stamp: Path) -> None:
    assert session() is None


def test_session_nudges_setup_rerun_on_stale_runtime(*, scanner: Path, stamp: Path) -> None:
    stamp.write_text("0.0.0\n")
    out = session()
    assert out["hookEventName"] == "SessionStart"
    assert "re-run" in out["additionalContext"]
    assert "setup.sh" in out["additionalContext"]


def test_session_warns_when_scanner_missing(*, stamp: Path) -> None:
    out = session()
    assert "sfw" in out["additionalContext"]
    assert "/jig:setup" in out["additionalContext"]
    assert "re-run" not in out["additionalContext"]  # runtime is fine, only the scanner nags


def test_session_scanner_warning_respects_optout(*, stamp: Path) -> None:
    os.environ["JIG_GUARD_ALLOW_UNSCANNED"] = "1"
    assert session() is None


def test_session_reports_runtime_and_scanner_together(*, stamp: Path) -> None:
    stamp.write_text("0.0.0\n")
    out = session()
    assert "re-run" in out["additionalContext"]
    assert "sfw" in out["additionalContext"]


@pytest.mark.parametrize("stdin", ["not json", "", "[]"])
def test_session_malformed_stdin_stays_silent(*, stdin: str, scanner: Path, stamp: Path) -> None:
    proc = run_hook(hook=SESSION, stdin=stdin)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""


# A plugin tree whose setup.sh the test controls, so the auto-provision
# branch never touches the network. The wrapper derives the script as
# dirname(guard.py)/setup.sh, hence the parallel tree per test.
PROVISION_OK = (
    'mkdir -p "${JIG_HOME}/bin"\n'
    f'ln -sf "{sys.executable}" "${{JIG_HOME}}/bin/python3"\n'
    f'printf "%s\\n" "{RUNTIME_PIN}" > "${{JIG_HOME}}/.python-pin"'
)


@pytest.fixture
def fake_plugin(*, tmp_path: Path) -> Path:
    root = tmp_path / "plugin"
    (root / "scripts").mkdir(parents=True)
    for mod in ("guard.py", "sfw.py", "preflight.py"):
        (root / "scripts" / mod).symlink_to(PLUGIN_ROOT / "scripts" / mod)
    os.environ["CLAUDE_PLUGIN_ROOT"] = str(root)
    return root


def write_setup(*, plugin_root: Path, body: str) -> None:
    (plugin_root / "scripts" / "setup.sh").write_text("#!/bin/sh\n" + body + "\n")


def test_session_provisions_missing_runtime(*, fake_plugin: Path) -> None:
    write_setup(plugin_root=fake_plugin, body=PROVISION_OK)
    out = session()
    assert (Path(os.environ["JIG_HOME"]) / "bin" / "python3").exists()  # wrapper ran setup.sh
    # Fresh stamp matches the pin, so the only preflight note is the
    # scanner one: the test setup.sh provisions no sfw.
    assert "sfw" in out["additionalContext"]
    assert "re-run" not in out["additionalContext"]


def test_session_reports_when_provisioning_fails(*, fake_plugin: Path) -> None:
    write_setup(plugin_root=fake_plugin, body="exit 1")
    out = session()
    assert not (Path(os.environ["JIG_HOME"]) / "bin" / "python3").exists()
    assert "could not provision" in out["additionalContext"]


def test_session_reports_unwritable_jig_home(*, fake_plugin: Path) -> None:
    # A file where the directory belongs: provisioning cannot mkdir it
    # whatever the privileges (a chmod-based setup fails under root).
    Path(os.environ["JIG_HOME"]).write_text("")
    write_setup(plugin_root=fake_plugin, body=PROVISION_OK)
    out = session()
    assert "could not provision" in out["additionalContext"]


def test_session_skips_provision_when_runtime_present(*, fake_plugin: Path, runtime: Path) -> None:
    write_setup(plugin_root=fake_plugin, body='touch "${JIG_HOME}/SENTINEL"')
    session()
    assert not (runtime / "SENTINEL").exists()  # runtime present, no provisioning attempt
