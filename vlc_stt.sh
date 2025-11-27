#!/bin/bash
# Wrapper script per lanciare vlc_speech2text.py con l'ambiente virtuale attivato

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Attiva l'ambiente virtuale
source venv/bin/activate

# Esegui lo script Python
python vlc_speech2text.py "$@"

