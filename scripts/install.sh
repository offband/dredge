#!/usr/bin/env bash
set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local}"
YES=0
SKIP_DEPS=0
SKIP_BUILD=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Install Dredge.

Usage:
  ./scripts/install.sh [options]

Options:
  --prefix <path>     Install prefix. Default: $HOME/.local
  --yes               Do not prompt before package installation
  --skip-deps         Do not install OS package dependencies
  --skip-build        Only check/install dependencies, do not install script
  --dry-run           Print detected environment and planned actions only
  -h, --help          Show this help

Environment:
  PREFIX=/path        Install prefix override

The binary is installed to:
  <prefix>/bin/dredge
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix)
      PREFIX="${2:?missing value for --prefix}"
      shift 2
      ;;
    --yes)
      YES=1
      shift
      ;;
    --skip-deps)
      SKIP_DEPS=1
      shift
      ;;
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

confirm() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "DRY RUN: would ask: $1"
    return 1
  fi
  if [ "$YES" -eq 1 ]; then
    return 0
  fi
  printf "%s [y/N] " "$1"
  read -r answer
  case "$answer" in
    y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

run_pkg_install() {
  if [ "$SKIP_DEPS" -eq 1 ]; then
    echo "Skipping OS dependency installation."
    return 0
  fi

  if need_cmd apt-get; then
    echo "Detected package manager: apt-get"
    [ "$DRY_RUN" -eq 1 ] && echo "DRY RUN: would install python3 python3-pip" && return 0
    if confirm "Install Python dependencies with apt-get?"; then
      sudo apt-get update
      sudo apt-get install -y python3 python3-pip
    fi
  elif need_cmd dnf; then
    echo "Detected package manager: dnf"
    [ "$DRY_RUN" -eq 1 ] && echo "DRY RUN: would install python3 python3-pip" && return 0
    if confirm "Install Python dependencies with dnf?"; then
      sudo dnf install -y python3 python3-pip
    fi
  elif need_cmd yum; then
    echo "Detected package manager: yum"
    [ "$DRY_RUN" -eq 1 ] && echo "DRY RUN: would install python3 python3-pip" && return 0
    if confirm "Install Python dependencies with yum?"; then
      sudo yum install -y python3 python3-pip
    fi
  elif need_cmd pacman; then
    echo "Detected package manager: pacman"
    [ "$DRY_RUN" -eq 1 ] && echo "DRY RUN: would install python python-pip" && return 0
    if confirm "Install Python dependencies with pacman?"; then
      sudo pacman -Sy --needed python python-pip
    fi
  elif need_cmd zypper; then
    echo "Detected package manager: zypper"
    [ "$DRY_RUN" -eq 1 ] && echo "DRY RUN: would install python3 python3-pip" && return 0
    if confirm "Install Python dependencies with zypper?"; then
      sudo zypper install -y python3 python3-pip
    fi
  elif need_cmd apk; then
    echo "Detected package manager: apk"
    [ "$DRY_RUN" -eq 1 ] && echo "DRY RUN: would install python3 py3-pip" && return 0
    if confirm "Install Python dependencies with apk?"; then
      sudo apk add python3 py3-pip
    fi
  elif need_cmd brew; then
    echo "Detected package manager: brew"
    [ "$DRY_RUN" -eq 1 ] && echo "DRY RUN: would install python" && return 0
    if confirm "Install Python with Homebrew?"; then
      brew install python
    fi
  else
    echo "No supported package manager detected. Install Python 3.11+ manually." >&2
  fi
}

check_python() {
  if need_cmd python3; then
    if ! version="$(python3 - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
    )"; then
      echo "python3 3.11+ is required; found $version." >&2
      return 1
    fi
    echo "Found python3: $(python3 --version)"
    return 0
  fi

  echo "python3 is required. Install Python 3.11+, then rerun this script." >&2
  return 1
}

build_and_install() {
  if [ "$SKIP_BUILD" -eq 1 ]; then
    echo "Skipping build."
    return 0
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    echo "DRY RUN: would install Dredge package to $PREFIX/lib/dredge and launcher to $PREFIX/bin/dredge"
    return 0
  fi

  mkdir -p "$PREFIX/bin" "$PREFIX/lib"
  REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  INSTALL_ROOT="$PREFIX/lib/dredge"
  rm -rf "$INSTALL_ROOT"
  mkdir -p "$INSTALL_ROOT"
  cp -R "$REPO_ROOT/src" "$INSTALL_ROOT/src"
  find "$INSTALL_ROOT/src" -type d -name __pycache__ -prune -exec rm -rf {} +
  cat > "$PREFIX/bin/dredge" <<EOF
#!/usr/bin/env bash
PYTHONPATH="$INSTALL_ROOT/src\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m dredge "\$@"
EOF
  chmod +x "$PREFIX/bin/dredge"
  echo "Installed dredge to $PREFIX/bin/dredge"

  case ":$PATH:" in
    *":$PREFIX/bin:"*) ;;
    *)
      echo "Note: $PREFIX/bin is not currently in PATH."
      echo "Add this to your shell profile if needed:"
      echo "  export PATH=\"$PREFIX/bin:\$PATH\""
      ;;
  esac
}

main() {
  echo "Dredge installer"
  echo "OS: $(uname -s 2>/dev/null || echo unknown)"
  echo "Arch: $(uname -m 2>/dev/null || echo unknown)"
  echo "Prefix: $PREFIX"

  run_pkg_install
  check_python
  build_and_install

  if need_cmd "$PREFIX/bin/dredge"; then
    "$PREFIX/bin/dredge" version
  fi
}

main "$@"
