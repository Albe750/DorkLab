#!/usr/bin/env bash
# Avvio diretto dalla cartella del progetto, senza installazione.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
exec python3 -m dorklab "$@"
