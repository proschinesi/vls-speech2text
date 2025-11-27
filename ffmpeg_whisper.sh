#!/bin/bash
# Wrapper script per lanciare ffmpeg_whisper.py con l'ambiente virtuale attivato

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Attiva l'ambiente virtuale (se esiste)
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Esegui lo script Python
python3 ffmpeg_whisper.py "$@"

