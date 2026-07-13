#!/bin/sh
# jig managed runtime: pinned uv and pinned CPython under one prefix jig
# owns (JIG_HOME, default ~/.local/share/jig). Hooks exec
# $JIG_HOME/bin/python3 directly, so every user runs the exact interpreter
# pinned below and a hook bug report never starts at "which python is that
# machine on". Idempotent; re-run after a pin bump.
#
# The pins are the single source of the runtime version for all jig
# plugins. Installer env vars per
# https://docs.astral.sh/uv/reference/installer/
set -eu

UV_VERSION="0.11.28"
# Pre-release: matches the repo toolchain (requires-python >=3.15); move
# to 3.15.0 final when it lands (Oct 2026).
PYTHON_VERSION="3.15.0b3"
SAFECHAIN_VERSION="1.5.12"

with_safechain=0
for arg in "$@"; do
  case "$arg" in
    --with-safechain) with_safechain=1 ;;
    *) echo "setup: unknown option: $arg" >&2; exit 2 ;;
  esac
done

JIG_HOME="${JIG_HOME:-$HOME/.local/share/jig}"
mkdir -p "$JIG_HOME/bin"

uv="$JIG_HOME/bin/uv"
installed="$("$uv" --version 2>/dev/null | awk '{print $2}' || true)"
if [ "$installed" != "$UV_VERSION" ]; then
  # UV_UNMANAGED_INSTALL: fixed target dir, no shell profile edits, and
  # `uv self update` disabled, so only this script moves the pin.
  curl -LsSf "https://astral.sh/uv/$UV_VERSION/install.sh" \
    | UV_UNMANAGED_INSTALL="$JIG_HOME/bin" sh
fi

# --no-bin: without it uv also drops a python3.x executable into the
# user-level bin dir, breaking the promise that setup touches only JIG_HOME.
export UV_PYTHON_INSTALL_DIR="$JIG_HOME/python"
"$uv" python install --no-bin "$PYTHON_VERSION"

# Locate the managed build by path instead of `uv python find`, which may
# prefer a same-version system interpreter outside JIG_HOME.
py="$(find "$UV_PYTHON_INSTALL_DIR" -maxdepth 3 \
  -path "*cpython-$PYTHON_VERSION-*/bin/python3" | head -n 1)"
[ -n "$py" ] || { echo "setup: managed cpython-$PYTHON_VERSION not found under $UV_PYTHON_INSTALL_DIR" >&2; exit 1; }
ln -sf "$py" "$JIG_HOME/bin/python3"

"$JIG_HOME/bin/python3" -c "import sys
assert sys.version.startswith('$PYTHON_VERSION'), sys.version
print('jig runtime ok:', sys.version.split()[0], 'at', sys.executable)"

# Stamp what was provisioned: preflight compares this against the pin a
# plugin update ships and nudges a setup.sh re-run when they diverge.
printf '%s\n' "$PYTHON_VERSION" >"$JIG_HOME/.python-pin"

# safe-chain is the scanner guard routes installs through. Opt-in via
# --with-safechain, driven by the /guard:setup skill so the user sees and
# approves this third-party install. Its --ci mode writes PATH shims to
# ~/.safe-chain/shims, which the SessionStart hook prepends onto PATH.
if [ "$with_safechain" = 1 ]; then
  if [ -d "$HOME/.safe-chain/shims" ]; then
    echo "safe-chain already installed (~/.safe-chain/shims)."
  else
    echo "Installing Aikido safe-chain $SAFECHAIN_VERSION (--ci PATH shims)..."
    # Version-pinned. safe-chain's installer verifies the binary it fetches
    # against an embedded checksum; what stays unverified is the installer
    # script itself (fetched over TLS from the pinned release URL). Pin its
    # SHA256 before wider distribution.
    curl -fsSL "https://github.com/AikidoSec/safe-chain/releases/download/$SAFECHAIN_VERSION/install-safe-chain.sh" \
      | sh -s -- --ci
  fi
fi
