#!/bin/sh
# jig managed runtime: pinned uv and pinned CPython under one prefix jig
# owns (JIG_HOME, default ~/.local/share/jig). Hooks exec
# $JIG_HOME/bin/python3 directly, so every user runs the exact interpreter
# pinned below and a hook bug report never starts at "which python is that
# machine on". Idempotent; re-run after a pin bump.
#
# The pins are the single source of the runtime version for the jig
# plugin. Installer env vars per
# https://docs.astral.sh/uv/reference/installer/
set -eu

UV_VERSION="0.11.28"
# Pre-release: matches the repo toolchain (requires-python >=3.15); move
# to 3.15.0 final when it lands (Oct 2026).
PYTHON_VERSION="3.15.0b3"
SFW_VERSION="1.13.1"

with_sfw=0
case "$#:${1-}" in
  0:) ;;
  1:--with-sfw) with_sfw=1 ;;
  *) echo "setup: unknown option: $1" >&2; exit 2 ;;
esac

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

# Socket Firewall free: the malware scanner guard reissues installs
# through. Pinned by version and per-platform sha256 (the digests GitHub's
# release API publishes for the tag), so a retagged release cannot swap
# the binary. The binary has no self-updater (verified in #8); only this
# script moves the pin. Windows is out of scope: these hooks run via sh.
if [ "$with_sfw" = 1 ]; then
  arch="$(uname -m)"
  case "$arch" in
    aarch64|arm64) arch="arm64" ;;
    x86_64) ;;
    *) echo "setup: no sfw build for $arch" >&2; exit 1 ;;
  esac
  case "$(uname -s)" in
    Darwin) plat="macos-$arch" ;;
    # ldd is glibc's here and musl's on Alpine; only musl says so.
    Linux) if ldd --version 2>&1 | grep -qi musl; then plat="musl-linux-$arch"; else plat="linux-$arch"; fi ;;
    *) echo "setup: no sfw build for $(uname -s)" >&2; exit 1 ;;
  esac
  case "$plat" in
    linux-x86_64)      sfw_sha="4dc46b626a7c5b81c0b54e1984ee53be5a628dbfb2f55ab14e9b04c8a134db6a" ;;
    linux-arm64)       sfw_sha="f87bbbca2192fca9740f9bdb115e7cfaa22e957a8f5234d5f97fce1383aa1d66" ;;
    musl-linux-x86_64) sfw_sha="fa372d97507a281d30b2b71ba18add8d2886d6726c1e4b9d8c14f6b3223f066b" ;;
    musl-linux-arm64)  sfw_sha="2ec770209d45763a919a1d22e35fbb3ea74458ae0d4c20646ca591f6e002591d" ;;
    macos-x86_64)      sfw_sha="6c7d5fcf66bc5284b3320cf6e12e4654135eb64ef3a926ea77e3d0904782d862" ;;
    macos-arm64)       sfw_sha="30ab1981303fc18f41db9d1615d9a792015d9d9e52da658a387bc89fe344db8f" ;;
  esac
  sfw="$JIG_HOME/bin/sfw"
  if [ "$("$sfw" --version 2>/dev/null | awk '{print $NF}' || true)" = "$SFW_VERSION" ]; then
    echo "sfw $SFW_VERSION already installed at $sfw"
  else
    tmp="$sfw.download"
    curl -fsSL -o "$tmp" \
      "https://github.com/SocketDev/sfw-free/releases/download/v$SFW_VERSION/sfw-free-$plat"
    if command -v sha256sum >/dev/null; then
      got="$(sha256sum "$tmp" | awk '{print $1}')"
    else
      got="$(shasum -a 256 "$tmp" | awk '{print $1}')"  # macOS ships shasum, not sha256sum
    fi
    [ "$got" = "$sfw_sha" ] || {
      rm -f "$tmp"
      echo "setup: sfw checksum mismatch for sfw-free-$plat (expected $sfw_sha, got $got)" >&2
      exit 1
    }
    chmod +x "$tmp"
    mv "$tmp" "$sfw"
    echo "sfw $SFW_VERSION installed at $sfw"
  fi
fi

# Earlier versions installed Aikido safe-chain as the install scanner
# (removed in #7, replacement tracked in #8). Point at the leftover but
# never delete it: the directory may predate jig.
if [ -d "$HOME/.safe-chain" ]; then
  echo "Note: jig no longer uses Aikido safe-chain. If /jig:setup installed it,"
  echo "remove the leftover with: rm -rf ~/.safe-chain (keep it if you installed it yourself)."
fi
