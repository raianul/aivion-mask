#!/usr/bin/env bash
set -euo pipefail

# Colors
G='\033[0;32m'
Y='\033[1;33m'
R='\033[0;31m'
B='\033[1m'
N='\033[0m'

INSTALL_DIR="$HOME/.aivion-mask"
VENV_DIR="$INSTALL_DIR/venv"
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

MARKER_BEGIN="# >>> aivion-mask (auto-installed) >>>"
MARKER_END="# <<< aivion-mask (auto-installed) <<<"

printf "${B}aivion-mask installer${N}\n\n"

# 1. Python check
if ! command -v python3 >/dev/null 2>&1; then
    printf "${R}python3 not found.${N} Install Python 3.10+ first (https://python.org).\n"
    exit 1
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_OK=$(python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' && echo 1 || echo 0)
if [ "$PY_OK" != "1" ]; then
    printf "${R}Python ${PY_VER} detected. Need 3.10+.${N}\n"
    printf "Use pyenv or asdf to install a newer Python.\n"
    exit 1
fi
printf "  ✓ Python ${PY_VER}\n"

# 2. Sanity-check repo layout
if [ ! -d "$REPO_ROOT/packages/core" ] || [ ! -d "$REPO_ROOT/packages/claude" ]; then
    printf "${R}Cannot find packages/core or packages/claude in ${REPO_ROOT}.${N}\n"
    printf "Run install.sh from the repository root.\n"
    exit 1
fi
printf "  ✓ Repo layout looks good\n"

# 3. Install dir + venv
mkdir -p "$INSTALL_DIR"
chmod 700 "$INSTALL_DIR"
if [ -d "$VENV_DIR" ]; then
    printf "  ↻ Reusing existing venv at ${VENV_DIR}\n"
else
    python3 -m venv "$VENV_DIR"
    printf "  ✓ Created venv at ${VENV_DIR}\n"
fi

# 4. Install packages
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet "$REPO_ROOT/packages/core"
"$VENV_DIR/bin/pip" install --quiet "$REPO_ROOT/packages/claude"
printf "  ✓ Installed aivion-mask-core + aivion-mask-claude\n"

# 5. Detect shell rc
SHELL_NAME=$(basename "${SHELL:-/bin/zsh}")
case "$SHELL_NAME" in
    zsh)  RC="$HOME/.zshrc" ;;
    bash) RC="$HOME/.bashrc" ;;
    *)    RC="$HOME/.${SHELL_NAME}rc" ;;
esac

# 6. Update RC file
if grep -qF "$MARKER_BEGIN" "$RC" 2>/dev/null; then
    printf "  ↻ ${RC} already has aivion-mask block — skipping\n"
else
    printf "\n${Y}I'd like to add these lines to ${RC}:${N}\n"
    printf "    ${MARKER_BEGIN}\n"
    printf "    export PATH=\"${VENV_DIR}/bin:\$PATH\"\n"
    printf "    export ANTHROPIC_BASE_URL=http://localhost:47474\n"
    printf "    ${MARKER_END}\n\n"
    read -p "Proceed? [Y/n] " confirm
    confirm=${confirm:-Y}
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        cat >> "$RC" <<EOF

${MARKER_BEGIN}
export PATH="${VENV_DIR}/bin:\$PATH"
export ANTHROPIC_BASE_URL=http://localhost:47474
${MARKER_END}
EOF
        printf "  ✓ Updated ${RC}\n"
    else
        printf "  ${Y}Skipped${N} — add these manually if you change your mind:\n"
        printf "    export PATH=\"${VENV_DIR}/bin:\$PATH\"\n"
        printf "    export ANTHROPIC_BASE_URL=http://localhost:47474\n"
    fi
fi

printf "\n${G}${B}Installed.${N}\n\n"

# 7. Start the proxy and open the dashboard
AIVION_BIN="$VENV_DIR/bin/aivion-mask"
printf "Starting proxy...\n"
"$AIVION_BIN" start
printf "Opening dashboard...\n"
"$AIVION_BIN" dashboard || true

printf "\n${G}Done.${N} Open a new terminal (or ${Y}source ${RC}${N}) so Claude Code picks up the proxy.\n"
printf "Useful commands: ${Y}aivion-mask status${N} | ${Y}aivion-mask logs -f${N} | ${Y}aivion-mask stop${N}\n"
printf "To uninstall: ${Y}bash ${REPO_ROOT}/uninstall.sh${N}\n"
