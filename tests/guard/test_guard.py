"""Guard plugin: dispatch, safechain and preflight tools, hooks.json shell wrappers."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2] / "plugins" / "guard"
GUARD = PLUGIN_ROOT / "scripts" / "guard.py"
HOOKS = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text())
SESSION_CMD = HOOKS["hooks"]["SessionStart"][0]["hooks"][0]["command"]
PRETOOL_CMD = HOOKS["hooks"]["PreToolUse"][0]["hooks"][0]["command"]

SESSION_EVENT = {"hook_event_name": "SessionStart"}


def base_env(*, jig_home: str | Path) -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": "/nonexistent",  # keep the runner's real ~/.safe-chain out of play
        "JIG_HOME": str(jig_home),
        "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
    }


def run_guard(
    *,
    shims_dir: str | Path,
    command: str | None = None,
    args: tuple[str, ...] = (),
    event: dict | None = None,
    allow_unscanned: bool = False,
    path: str | None = None,
) -> dict | None:
    env = base_env(jig_home="/nonexistent")
    env["JIG_GUARD_SHIMS_DIR"] = str(shims_dir)
    if path is not None:
        env["PATH"] = path
    if allow_unscanned:
        env["JIG_GUARD_ALLOW_UNSCANNED"] = "1"
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


def run_wrapper(*, command: str, jig_home: str | Path, event: dict) -> dict | None:
    proc = subprocess.run(
        ["/bin/sh", "-c", command],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=base_env(jig_home=jig_home),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    return json.loads(out)["hookSpecificOutput"] if out else None


@pytest.fixture
def shims(tmp_path: Path) -> Path:
    path = tmp_path / "shims"
    path.mkdir()
    return path


@pytest.fixture
def missing(tmp_path: Path) -> Path:
    return tmp_path / "absent"


@pytest.mark.parametrize("command", ["git status", "npm test", "uv run pytest"])
def test_non_install_commands_pass(shims: Path, command: str) -> None:
    assert run_guard(shims_dir=shims, command=command) is None


def test_install_denied_with_shimmed_rerun_line(shims: Path) -> None:
    out = run_guard(shims_dir=shims, command="npm install left-pad")
    assert out["permissionDecision"] == "deny"
    assert f'export PATH="{shims}:$PATH"; npm install left-pad' in out["permissionDecisionReason"]


def test_reissued_command_passes(shims: Path) -> None:
    command = f'export PATH="{shims}:$PATH"; npm install left-pad'
    assert run_guard(shims_dir=shims, command=command) is None


def test_path_already_carrying_shims_passes(shims: Path) -> None:
    assert run_guard(shims_dir=shims, command="npm install left-pad", path=f"{shims}:/usr/bin") is None


def test_optout_does_not_skip_the_scan(shims: Path) -> None:
    assert run_guard(shims_dir=shims, command="npm install left-pad", allow_unscanned=True) is not None


@pytest.mark.parametrize("command", ["pip install requests", "uvx ruff check"])
def test_unscannable_install_denied_with_pointer(missing: Path, command: str) -> None:
    out = run_guard(shims_dir=missing, command=command)
    assert out["permissionDecision"] == "deny"
    assert "safe-chain" in out["permissionDecisionReason"]


def test_optout_allows_unscanned_install(missing: Path) -> None:
    assert run_guard(shims_dir=missing, command="pip install requests", allow_unscanned=True) is None


def test_non_matching_event_skips_enforcement(missing: Path) -> None:
    event = {"hook_event_name": "PostToolUse", "tool_input": {"command": "npm install x"}}
    assert run_guard(shims_dir=missing, event=event) is None


def test_preflight_silent_when_shims_exist(shims: Path) -> None:
    assert run_guard(shims_dir=shims, args=("preflight",), event=SESSION_EVENT) is None


def test_preflight_warns_when_safechain_missing(missing: Path) -> None:
    out = run_guard(shims_dir=missing, args=("preflight",), event=SESSION_EVENT)
    assert "safe-chain" in out["additionalContext"]
    assert out["hookEventName"] == "SessionStart"


def test_preflight_silent_after_optout(missing: Path) -> None:
    assert run_guard(shims_dir=missing, args=("preflight",), event=SESSION_EVENT, allow_unscanned=True) is None


def test_event_routing_reaches_preflight_without_arg(missing: Path) -> None:
    assert run_guard(shims_dir=missing, event=SESSION_EVENT) is not None


def test_direct_tool_selection(missing: Path) -> None:
    assert run_guard(shims_dir=missing, command="pip install requests", args=("safechain",)) is not None


def test_unknown_tool_fails() -> None:
    proc = subprocess.run([sys.executable, GUARD, "nope"], input="{}", capture_output=True, text=True, check=False)
    assert proc.returncode != 0
    assert "unknown tool" in proc.stderr


def test_malformed_stdin_stays_silent() -> None:
    proc = subprocess.run([sys.executable, GUARD], input="not json", capture_output=True, text=True, check=True)
    assert proc.stdout == ""


def test_session_wrapper_reports_missing_runtime() -> None:
    out = run_wrapper(command=SESSION_CMD, jig_home="/nonexistent", event=SESSION_EVENT)
    assert out["hookEventName"] == "SessionStart"
    assert "setup.sh" in out["additionalContext"]


def test_pretool_wrapper_silent_without_runtime() -> None:
    event = {"tool_input": {"command": "npm install x"}}
    assert run_wrapper(command=PRETOOL_CMD, jig_home="/nonexistent", event=event) is None


@pytest.fixture
def jighome(tmp_path: Path) -> Path:
    home = tmp_path / "jighome"
    (home / "bin").mkdir(parents=True)
    (home / "bin" / "python3").symlink_to(sys.executable)
    return home


def test_session_wrapper_execs_preflight(jighome: Path) -> None:
    out = run_wrapper(command=SESSION_CMD, jig_home=jighome, event=SESSION_EVENT)
    assert "safe-chain" in out["additionalContext"]  # HOME=/nonexistent has no shims


def test_pretool_wrapper_execs_enforcement(jighome: Path) -> None:
    event = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "npm install x"}}
    out = run_wrapper(command=PRETOOL_CMD, jig_home=jighome, event=event)
    assert out["permissionDecision"] == "deny"
