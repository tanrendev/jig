"""Guard plugin: dispatch, installs and preflight tools, hooks.json shell wrappers."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2] / "plugins" / "jig"
GUARD = PLUGIN_ROOT / "scripts" / "guard.py"
HOOKS = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text())
SESSION_CMD = HOOKS["hooks"]["SessionStart"][0]["hooks"][0]["command"]
PRETOOL_CMD = HOOKS["hooks"]["PreToolUse"][0]["hooks"][0]["command"]

SESSION_EVENT = {"hook_event_name": "SessionStart"}


def base_env(*, jig_home: str | Path) -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": "/nonexistent",  # keep the runner's real home out of play
        "JIG_HOME": str(jig_home),
        "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
    }


def run_guard(
    *,
    command: str | None = None,
    args: tuple[str, ...] = (),
    event: dict | None = None,
    allow_unscanned: str | None = None,
    jig_home: str | Path = "/nonexistent",
) -> dict | None:
    env = base_env(jig_home=jig_home)
    if allow_unscanned is not None:
        env["JIG_GUARD_ALLOW_UNSCANNED"] = allow_unscanned
    if event is None:
        event = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}}
    proc = subprocess.run(
        [sys.executable, GUARD, *args],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    out = proc.stdout.strip()
    return json.loads(out)["hookSpecificOutput"] if out else None


def run_wrapper(
    *, command: str, jig_home: str | Path, event: dict, plugin_root: str | Path = PLUGIN_ROOT
) -> dict | None:
    env = base_env(jig_home=jig_home)
    env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    proc = subprocess.run(
        ["/bin/sh", "-c", command],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    return json.loads(out)["hookSpecificOutput"] if out else None


@pytest.mark.parametrize("command", ["git status", "npm test", "uv run pytest"])
def test_non_install_commands_pass(*, command: str) -> None:
    assert run_guard(command=command) is None


@pytest.mark.parametrize(
    "command",
    [
        "npm install left-pad",
        "pip install requests",
        "uvx ruff check",
        # Versioned interpreters must not slip past the regex.
        "pip3.11 install requests",
        "python3.12 -m pip install requests",
        # Nor options whose value sits between the tool and the subcommand.
        "pip --index-url https://example.invalid/simple install requests",
        "python3.12 -m pip --proxy http://example.invalid install requests",
        "npm --registry https://example.invalid install left-pad",
    ],
)
def test_install_denied_with_escape_pointer(*, command: str) -> None:
    out = run_guard(command=command)
    assert out["permissionDecision"] == "deny"
    assert "JIG_GUARD_ALLOW_UNSCANNED" in out["permissionDecisionReason"]


def test_optout_allows_unscanned_install() -> None:
    assert run_guard(command="pip install requests", allow_unscanned="1") is None


@pytest.mark.parametrize("value", ["0", "false", "yes"])
def test_optout_requires_the_documented_value(*, value: str) -> None:
    assert run_guard(command="pip install requests", allow_unscanned=value) is not None


def test_non_matching_event_skips_enforcement() -> None:
    event = {"hook_event_name": "PostToolUse", "tool_input": {"command": "npm install x"}}
    assert run_guard(event=event) is None


RUNTIME_PIN = re.search(
    r'^PYTHON_VERSION="([^"]+)"$', (PLUGIN_ROOT / "scripts" / "setup.sh").read_text(), re.MULTILINE
).group(1)


@pytest.fixture
def stamped_home(*, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    (home / ".python-pin").write_text(f"{RUNTIME_PIN}\n")
    return home


def test_preflight_silent_when_stamp_matches_pin(*, stamped_home: Path) -> None:
    assert run_guard(args=("preflight",), event=SESSION_EVENT, jig_home=stamped_home) is None


def test_preflight_silent_when_unprovisioned() -> None:
    # No stamp to compare; the SessionStart wrapper covers missing runtimes.
    assert run_guard(args=("preflight",), event=SESSION_EVENT) is None


def test_preflight_nudges_setup_rerun_on_stale_runtime(*, stamped_home: Path) -> None:
    (stamped_home / ".python-pin").write_text("0.0.0\n")
    out = run_guard(args=("preflight",), event=SESSION_EVENT, jig_home=stamped_home)
    assert "re-run" in out["additionalContext"]
    assert "setup.sh" in out["additionalContext"]
    assert out["hookEventName"] == "SessionStart"


def test_event_routing_reaches_preflight_without_arg(*, stamped_home: Path) -> None:
    (stamped_home / ".python-pin").write_text("0.0.0\n")
    assert run_guard(event=SESSION_EVENT, jig_home=stamped_home) is not None


def test_direct_tool_selection() -> None:
    assert run_guard(command="pip install requests", args=("installs",)) is not None


def test_unknown_tool_fails() -> None:
    proc = subprocess.run([sys.executable, GUARD, "nope"], input="{}", capture_output=True, text=True, check=False)
    assert proc.returncode != 0
    assert "unknown tool" in proc.stderr


def test_malformed_stdin_stays_silent() -> None:
    proc = subprocess.run([sys.executable, GUARD], input="not json", capture_output=True, text=True, check=True)
    assert proc.stdout == ""


# A plugin tree the SessionStart wrapper can drive with a setup.sh we control,
# so the auto-provision branch never touches the network. setup.sh is derived
# by the wrapper as dirname(guard.py)/setup.sh, hence the per-test rewrite.
PROVISION_OK = (
    'mkdir -p "${JIG_HOME}/bin"\n'
    f'ln -sf "{sys.executable}" "${{JIG_HOME}}/bin/python3"\n'
    f'printf "%s\\n" "{RUNTIME_PIN}" > "${{JIG_HOME}}/.python-pin"'
)


def write_setup(plugin_root: Path, *, body: str) -> None:
    (plugin_root / "scripts" / "setup.sh").write_text("#!/bin/sh\n" + body + "\n")


@pytest.fixture
def fake_plugin(*, tmp_path: Path) -> Path:
    root = tmp_path / "plugin"
    (root / "scripts").mkdir(parents=True)
    for mod in ("guard.py", "installs.py", "preflight.py"):
        (root / "scripts" / mod).symlink_to(PLUGIN_ROOT / "scripts" / mod)
    return root


@pytest.fixture
def jighome(*, tmp_path: Path) -> Path:
    home = tmp_path / "jighome"
    (home / "bin").mkdir(parents=True)
    (home / "bin" / "python3").symlink_to(sys.executable)
    return home


def test_session_wrapper_provisions_missing_runtime(*, fake_plugin: Path, tmp_path: Path) -> None:
    jig = tmp_path / "fresh"  # no interpreter yet
    write_setup(fake_plugin, body=PROVISION_OK)
    out = run_wrapper(command=SESSION_CMD, jig_home=jig, event=SESSION_EVENT, plugin_root=fake_plugin)
    assert (jig / "bin" / "python3").exists()  # wrapper ran setup.sh
    assert out is None  # then execed preflight: fresh stamp matches the pin, no drift


def test_session_wrapper_reports_when_provisioning_fails(*, fake_plugin: Path, tmp_path: Path) -> None:
    jig = tmp_path / "fresh"
    write_setup(fake_plugin, body="exit 1")
    out = run_wrapper(command=SESSION_CMD, jig_home=jig, event=SESSION_EVENT, plugin_root=fake_plugin)
    assert not (jig / "bin" / "python3").exists()
    assert "could not provision" in out["additionalContext"]


def test_session_wrapper_skips_provision_when_present(*, fake_plugin: Path, jighome: Path) -> None:
    write_setup(fake_plugin, body='touch "${JIG_HOME}/SENTINEL"')
    run_wrapper(command=SESSION_CMD, jig_home=jighome, event=SESSION_EVENT, plugin_root=fake_plugin)
    assert not (jighome / "SENTINEL").exists()  # runtime present, no provisioning attempt


def test_pretool_wrapper_silent_without_runtime() -> None:
    # PreToolUse never provisions (a tool call must not block on a download).
    event = {"tool_input": {"command": "npm install x"}}
    assert run_wrapper(command=PRETOOL_CMD, jig_home="/nonexistent", event=event) is None


def test_setup_rejects_unknown_option() -> None:
    # Arg parsing precedes provisioning, so this exits before any network call.
    setup = PLUGIN_ROOT / "scripts" / "setup.sh"
    proc = subprocess.run(["/bin/sh", str(setup), "--bogus"], capture_output=True, text=True, check=False)
    assert proc.returncode == 2
    assert "unknown option" in proc.stderr


def test_session_wrapper_execs_preflight(*, jighome: Path) -> None:
    (jighome / ".python-pin").write_text("0.0.0\n")  # stale stamp so preflight has output
    out = run_wrapper(command=SESSION_CMD, jig_home=jighome, event=SESSION_EVENT)
    assert "re-run" in out["additionalContext"]


def test_pretool_wrapper_execs_enforcement(*, jighome: Path) -> None:
    event = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "npm install x"}}
    out = run_wrapper(command=PRETOOL_CMD, jig_home=jighome, event=event)
    assert out["permissionDecision"] == "deny"
