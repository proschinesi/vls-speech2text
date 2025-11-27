#!/bin/bash
# Script per verificare lo stato dell'installazione FFmpeg

echo "Verifica stato installazione FFmpeg con Whisper..."
echo ""

if [[ -f /tmp/ffmpeg_install.log ]]; then
    echo "=== Ultime righe del log ==="
    tail -30 /tmp/ffmpeg_install.log
    echo ""
fi

# Verifica se il processo è ancora in esecuzione
if pgrep -f "install_ffmpeg8_whisper.sh" > /dev/null; then
    echo "✓ Installazione in corso..."
else
    echo "Installazione completata o non in esecuzione"
fi

echo ""
echo "=== Verifica FFmpeg attuale ==="
if command -v ffmpeg &> /dev/null; then
    ffmpeg -version | head -1
    echo ""
    echo "Verifica filtro Whisper:"
    if ffmpeg -filters 2>/dev/null | grep -qi whisper; then
        echo "✓ Filtro Whisper TROVATO!"
        ffmpeg -filters 2>/dev/null | grep -i whisper
    else
        echo "✗ Filtro Whisper NON trovato"
    fi
else
    echo "FFmpeg non trovato"
fi

