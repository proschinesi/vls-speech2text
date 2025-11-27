#!/bin/bash
# Script per monitorare l'installazione FFmpeg

LOG_FILE="/tmp/ffmpeg_install_new.log"

echo "=== Monitoraggio Installazione FFmpeg con Whisper ==="
echo ""

if [[ -f "$LOG_FILE" ]]; then
    echo "📋 Ultime 20 righe del log:"
    echo "----------------------------------------"
    tail -20 "$LOG_FILE"
    echo "----------------------------------------"
    echo ""
else
    echo "⚠ Log file non trovato: $LOG_FILE"
    echo ""
fi

# Verifica processi attivi
echo "🔍 Processi attivi:"
if pgrep -f "install_ffmpeg8_whisper" > /dev/null; then
    echo "✓ Installazione IN CORSO"
    ps aux | grep -i "install_ffmpeg\|ffmpeg.*configure\|ffmpeg.*make" | grep -v grep | head -3
else
    echo "✗ Nessun processo di installazione attivo"
fi

echo ""
echo "📊 Stato FFmpeg:"
if command -v ffmpeg &> /dev/null; then
    VERSION=$(ffmpeg -version 2>/dev/null | head -1)
    echo "Versione: $VERSION"
    
    if ffmpeg -filters 2>/dev/null | grep -qi whisper; then
        echo "✅ Filtro Whisper: DISPONIBILE"
        ffmpeg -filters 2>/dev/null | grep -i whisper
    else
        echo "❌ Filtro Whisper: NON DISPONIBILE"
    fi
else
    echo "FFmpeg non trovato"
fi

echo ""
echo "💡 Per monitorare in tempo reale:"
echo "   tail -f $LOG_FILE"

