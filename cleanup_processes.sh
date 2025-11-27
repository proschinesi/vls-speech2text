#!/bin/bash
# Script per pulire tutti i processi FFmpeg orfani

echo "=== Pulizia Processi FFmpeg ==="

# Conta processi prima
BEFORE=$(ps aux | grep -c "ffmpeg.*video_session\|ffmpeg.*chunk" | grep -v grep || echo "0")
echo "Processi FFmpeg trovati: $BEFORE"

if [ "$BEFORE" -eq "0" ]; then
    echo "Nessun processo da pulire"
    exit 0
fi

# Termina processi FFmpeg
echo "Terminazione processi..."
pkill -9 -f "ffmpeg.*video_session" 2>/dev/null
pkill -9 -f "ffmpeg.*chunk" 2>/dev/null
sleep 2

# Verifica
AFTER=$(ps aux | grep -c "ffmpeg.*video_session\|ffmpeg.*chunk" | grep -v grep || echo "0")
echo "Processi rimanenti: $AFTER"

# Pulisci file temporanei
echo "Pulizia file temporanei..."
rm -f /tmp/*session*.ts /tmp/*session*.srt 2>/dev/null
rm -f /var/folders/*/T/*session*.ts /var/folders/*/T/*session*.srt 2>/dev/null
rm -rf /tmp/whisper_* 2>/dev/null
rm -rf /var/folders/*/T/whisper_* 2>/dev/null

echo "✓ Pulizia completata"

