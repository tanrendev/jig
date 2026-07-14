"""Guard plugin: dispatch, safechain and preflight tools, hooks.json shell wrappers."""

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
    jig_home: str | Path = "/nonexistent",
    env_file: str | Path | None = None,
) -> dict | None:
    env = base_env(jig_home=jig_home)
    env["JIG_GUARD_SHIMS_DIR"] = str(shims_dir)
    if path is not None:
        env["PATH"] = path
    if allow_unscanned:
        env["JIG_GUARD_ALLOW_UNSCANNED"] = "1"
    if env_file is not None:
        env["CLAUDE_ENV_FILE"] = str(env_file)
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


@pytest.fixture
def shims(*, tmp_path: Path) -> Path:
    path = tmp_path / "shims"
    path.mkdir()
    return path


@pytest.fixture
def missing(*, tmp_path: Path) -> Path:
    return tmp_path / "absent"


@pytest.mark.parametrize("command", ["git status", "npm test", "uv run pytest"])
def test_non_install_commands_pass(*, shims: Path, command: str) -> None:
    assert run_guard(shims_dir=shims, command=command) is None


def test_install_denied_with_shimmed_rerun_line(*, shims: Path) -> None:
    out = run_guard(shims_dir=shims, command="npm install left-pad")
    assert out["permissionDecision"] == "deny"
    rerun = f'export PATH="{shims}:{shims.parent / "bin"}:$PATH"; npm install left-pad'
    assert rerun in out["permissionDecisionReason"]


def test_reissued_command_passes(*, shims: Path) -> None:
    command = f'export PATH="{shims}:{shims.parent / "bin"}:$PATH"; npm install left-pad'
    assert run_guard(shims_dir=shims, command=command) is None


def test_path_already_carrying_shims_passes(*, shims: Path) -> None:
    assert run_guard(shims_dir=shims, command="npm install left-pad", path=f"{shims}:/usr/bin") is None


def test_optout_does_not_skip_the_scan(*, shims: Path) -> None:
    assert run_guard(shims_dir=shims, command="npm install left-pad", allow_unscanned=True) is not None


@pytest.mark.parametrize("command", ["pip install requests", "uvx ruff check"])
def test_unscannable_install_denied_with_pointer(*, missing: Path, command: str) -> None:
    out = run_guard(shims_dir=missing, command=command)
    assert out["permissionDecision"] == "deny"
    assert "safe-chain" in out["permissionDecisionReason"]


def test_optout_allows_unscanned_install(*, missing: Path) -> None:
    assert run_guard(shims_dir=missing, command="pip install requests", allow_unscanned=True) is None


def test_non_matching_event_skips_enforcement(*, missing: Path) -> None:
    event = {"hook_event_name": "PostToolUse", "tool_input": {"command": "npm install x"}}
    assert run_guard(shims_dir=missing, event=event) is None


def test_preflight_silent_when_shims_exist(*, shims: Path) -> None:
    assert run_guard(shims_dir=shims, args=("preflight",), event=SESSION_EVENT) is None


def test_preflight_warns_when_safechain_missing(*, missing: Path) -> None:
    out = run_guard(shims_dir=missing, args=("preflight",), event=SESSION_EVENT)
    assert "safe-chain" in out["additionalContext"]
    assert out["hookEventName"] == "SessionStart"


def test_preflight_silent_after_optout(*, missing: Path) -> None:
    assert run_guard(shims_dir=missing, args=("preflight",), event=SESSION_EVENT, allow_unscanned=True) is None


def test_event_routing_reaches_preflight_without_arg(*, missing: Path) -> None:
    assert run_guard(shims_dir=missing, event=SESSION_EVENT) is not None


RUNTIME_PIN = re.search(
    r'^PYTHON_VERSION="([^"]+)"$', (PLUGIN_ROOT / "scripts" / "setup.sh").read_text(), re.MULTILINE
).group(1)


@pytest.fixture
def stamped_home(*, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    (home / ".python-pin").write_text(f"{RUNTIME_PIN}\n")
    return home


def test_preflight_silent_when_stamp_matches_pin(*, shims: Path, stamped_home: Path) -> None:
    assert run_guard(shims_dir=shims, args=("preflight",), event=SESSION_EVENT, jig_home=stamped_home) is None


def test_preflight_nudges_setup_rerun_on_stale_runtime(*, shims: Path, stamped_home: Path) -> None:
    (stamped_home / ".python-pin").write_text("0.0.0\n")
    out = run_guard(shims_dir=shims, args=("preflight",), event=SESSION_EVENT, jig_home=stamped_home)
    assert "re-run" in out["additionalContext"]
    assert "setup.sh" in out["additionalContext"]


def test_preflight_combines_runtime_and_safechain_warnings(*, missing: Path, stamped_home: Path) -> None:
    (stamped_home / ".python-pin").write_text("0.0.0\n")
    out = run_guard(shims_dir=missing, args=("preflight",), event=SESSION_EVENT, jig_home=stamped_home)
    assert "setup.sh" in out["additionalContext"]
    assert "safe-chain" in out["additionalContext"]


def test_pathwire_prepends_shims_to_env_file(*, shims: Path, tmp_path: Path) -> None:
    env_file = tmp_path / "session-env.sh"
    run_guard(shims_dir=shims, args=("preflight",), event=SESSION_EVENT, env_file=env_file)
    assert env_file.read_text().strip() == f'export PATH="{shims}:{shims.parent / "bin"}:$PATH"'


def test_wired_path_resolves_scanner_binary(*, shims: Path, tmp_path: Path) -> None:
    # Regression for #1: the shim wrapper resolves the scanner with
    # `command -v safe-chain`, and the binary lives in the bin dir next to
    # the shims. Wiring only the shims dir made the wrapper fail open.
    bin_dir = shims.parent / "bin"
    bin_dir.mkdir()
    scanner = bin_dir / "safe-chain"
    scanner.write_text(data="#!/bin/sh\n")
    scanner.chmod(mode=0o755)
    env_file = tmp_path / "session-env.sh"
    run_guard(shims_dir=shims, args=("preflight",), event=SESSION_EVENT, env_file=env_file)
    proc = subprocess.run(
        args=["/bin/sh", "-c", f'. "{env_file}"; command -v safe-chain'],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
        check=False,
    )
    assert proc.returncode == 0, "scanner binary not resolvable from the wired PATH"


def test_reissue_line_carries_scanner_bin_dir(*, shims: Path) -> None:
    out = run_guard(shims_dir=shims, command="npm install left-pad")
    assert str(shims.parent / "bin") in out["permissionDecisionReason"]


def test_pathwire_silent_without_env_file(*, shims: Path) -> None:
    # No CLAUDE_ENV_FILE (non-Claude host or older version): nothing to write, no error.
    assert run_guard(shims_dir=shims, args=("preflight",), event=SESSION_EVENT) is None


def test_pathwire_skips_when_shims_absent(*, missing: Path, tmp_path: Path) -> None:
    env_file = tmp_path / "session-env.sh"
    env_file.touch()
    run_guard(shims_dir=missing, args=("preflight",), event=SESSION_EVENT, env_file=env_file)
    assert env_file.read_text() == ""


def test_pathwire_is_idempotent(*, shims: Path, tmp_path: Path) -> None:
    env_file = tmp_path / "session-env.sh"
    for _ in range(2):
        run_guard(shims_dir=shims, args=("preflight",), event=SESSION_EVENT, env_file=env_file)
    assert env_file.read_text().count("export PATH") == 1


def test_pathwire_runs_even_when_preflight_warns(*, shims: Path, stamped_home: Path, tmp_path: Path) -> None:
    # Side effect (wire) and output (warning) must both happen: a stale pin warns
    # while shims exist to wire. Guards against the dispatcher's first-output-returns.
    (stamped_home / ".python-pin").write_text("0.0.0\n")
    env_file = tmp_path / "session-env.sh"
    out = run_guard(shims_dir=shims, args=("preflight",), event=SESSION_EVENT, jig_home=stamped_home, env_file=env_file)
    assert "re-run" in out["additionalContext"]
    assert f'export PATH="{shims}:{shims.parent / "bin"}:$PATH"' in env_file.read_text()


def test_direct_tool_selection(*, missing: Path) -> None:
    assert run_guard(shims_dir=missing, command="pip install requests", args=("safechain",)) is not None


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
    for mod in ("guard.py", "safechain.py", "preflight.py"):
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
    assert "safe-chain" in out["additionalContext"]  # then execed preflight


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
    out = run_wrapper(command=SESSION_CMD, jig_home=jighome, event=SESSION_EVENT)
    assert "safe-chain" in out["additionalContext"]  # HOME=/nonexistent has no shims


def test_pretool_wrapper_execs_enforcement(*, jighome: Path) -> None:
    event = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "npm install x"}}
    out = run_wrapper(command=PRETOOL_CMD, jig_home=jighome, event=event)
    assert out["permissionDecision"] == "deny"
