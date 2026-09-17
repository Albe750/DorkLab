#!/usr/bin/env bash
# Installazione di DorkLab su Fedora.
#
# Usa i pacchetti RPM dove disponibili (piu' leggeri e aggiornati dal sistema)
# e pip solo per le dipendenze opzionali.

set -euo pipefail

BLUE=$'\033[1;34m'; GREEN=$'\033[1;32m'; YELLOW=$'\033[1;33m'; RESET=$'\033[0m'
say() { printf '%s==>%s %s\n' "$BLUE" "$RESET" "$1"; }
ok()  { printf '%s  ok%s %s\n' "$GREEN" "$RESET" "$1"; }
warn(){ printf '%s  !!%s %s\n' "$YELLOW" "$RESET" "$1"; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v dnf >/dev/null 2>&1; then
    warn "dnf non trovato: questo script e' pensato per Fedora."
    warn "Su altre distribuzioni: pip install --user -r requirements.txt"
    exit 1
fi

say "Installazione delle dipendenze di sistema"
sudo dnf install -y python3 python3-pip python3-pyqt6 python3-requests
ok "dipendenze di base installate"

say "Dipendenze opzionali"
sudo dnf install -y python3-pypdf 2>/dev/null && ok "pypdf (metadati PDF)" \
    || warn "python3-pypdf non disponibile: pip install --user pypdf"

read -r -p "Installare il supporto al motore agentico Claude? [s/N] " reply
if [[ "$reply" =~ ^[SsYy]$ ]]; then
    pip install --user "anthropic>=0.40" && ok "anthropic installato"
fi

say "Installazione di DorkLab"
pip install --user "$HERE"
ok "dorklab installato"

say "Voce nel menu applicazioni"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$DESKTOP_DIR" "$ICON_DIR"
install -m 0644 "$HERE/packaging/dorklab.svg" "$ICON_DIR/dorklab.svg"
sed "s|@EXEC@|$HOME/.local/bin/dorklab|" "$HERE/packaging/dorklab.desktop" \
    > "$DESKTOP_DIR/dorklab.desktop"
chmod 0644 "$DESKTOP_DIR/dorklab.desktop"
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
ok "voce di menu creata"

echo
say "Fatto. Avvia con:  dorklab"
if ! printf '%s' "$PATH" | grep -q "$HOME/.local/bin"; then
    warn "~/.local/bin non e' nel PATH. Aggiungi al tuo ~/.bashrc:"
    echo '      export PATH="$HOME/.local/bin:$PATH"'
fi
