#!/bin/bash
# Script per avviare il server web

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Attiva l'ambiente virtuale (se esiste)
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Avvia il server web
python3 web_app.py "$@"

