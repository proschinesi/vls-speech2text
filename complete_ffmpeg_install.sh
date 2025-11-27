#!/bin/bash
# Script per completare l'installazione FFmpeg con Whisper

cd /Users/ube/ffmpeg_build/ffmpeg

echo "=== Completamento Installazione FFmpeg con Whisper ==="
echo ""
echo "Questo script richiede la password sudo per installare FFmpeg in /usr/local"
echo ""

# Verifica se la compilazione è completata
if [ ! -f "ffmpeg" ]; then
    echo "❌ FFmpeg non compilato. Esegui prima install_ffmpeg8_whisper.sh"
    exit 1
fi

echo "Installazione FFmpeg con Whisper..."
echo "Richiederà la password sudo"
sudo make install

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Installazione completata!"
    echo ""
    echo "Verifica:"
    /usr/local/bin/ffmpeg -version | head -1
    echo ""
    if /usr/local/bin/ffmpeg -filters 2>&1 | grep -qi whisper; then
        echo "✅ Filtro Whisper TROVATO!"
        /usr/local/bin/ffmpeg -filters 2>&1 | grep -i whisper
    else
        echo "❌ Filtro Whisper NON trovato"
    fi
else
    echo "❌ Errore durante l'installazione"
    exit 1
fi
