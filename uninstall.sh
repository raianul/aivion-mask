#!/usr/bin/env bash
set -euo pipefail

G='\033[0;32m'
Y='\033[1;33m'
R='\033[0;31m'
B='\033[1m'
N='\033[0m'

INSTALL_DIR="$HOME/.aivion-mask"
VENV_DIR="$INSTALL_DIR/venv"

MARKER_BEGIN="# >>> aivion-mask (auto-installed) >>>"
MARKER_END="# <<< aivion-mask (auto-installed) <<<"

printf "${B}aivion-mask uninstaller${N}\n\n"

# 1. Stop the proxy if running
if [ -x "${VENV_DIR}/bin/aivion-mask" ]; then
    "${VENV_DIR}/bin/aivion-mask" stop 2>/dev/null || true
    printf "  ✓ Stopped proxy\n"
fi

# 2. Remove the rc block from zsh + bash (whichever has it)
for RC in "$HOME/.zshrc" "$HOME/.bashrc"; do
    [ -f "$RC" ] || continue
    if grep -qF "$MARKER_BEGIN" "$RC"; then
        # Use a temp file rather than sed -i (portable across BSD/GNU)
        awk -v b="$MARKER_BEGIN" -v e="$MARKER_END" '
            $0 == b {skip=1; next}
            $0 == e {skip=0; next}
            !skip
        ' "$RC" > "${RC}.aivion-mask.tmp"
        mv "${RC}.aivion-mask.tmp" "$RC"
        printf "  ✓ Removed aivion-mask block from ${RC}\n"
    fi
done

# 3. Remove venv
if [ -d "$VENV_DIR" ]; then
    rm -rf "$VENV_DIR"
    printf "  ✓ Removed venv at ${VENV_DIR}\n"
fi

# 4. Ask before removing data dir
if [ -d "$INSTALL_DIR" ] && [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
    printf "\n${Y}${INSTALL_DIR} still contains:${N}\n"
    ls -la "$INSTALL_DIR" | tail -n +2 | sed 's/^/    /'
    printf "\nThis includes your config, sessions DB, auth token, and logs.\n"
    read -p "Delete it all? [y/N] " confirm
    confirm=${confirm:-N}
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        rm -rf "$INSTALL_DIR"
        printf "  ✓ Removed ${INSTALL_DIR}\n"
    else
        printf "  ${Y}Kept${N} — delete manually with: ${Y}rm -rf ${INSTALL_DIR}${N}\n"
    fi
fi

printf "\n${G}${B}Uninstalled.${N}\n"
printf "Open a new terminal so the rc changes take effect.\n"
