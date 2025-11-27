#!/bin/bash
# Wrapper per FFmpeg compilato con Whisper
# Imposta le variabili d'ambiente necessarie per trovare le librerie

FFMPEG_BUILD_DIR="/Users/ube/ffmpeg_build/ffmpeg"
FFMPEG_BIN="$FFMPEG_BUILD_DIR/ffmpeg"

# Su macOS, DYLD_LIBRARY_PATH non funziona per sicurezza
# Dobbiamo usare install_name_tool o installare le librerie
# Per ora, prova a eseguire dalla directory di build
cd "$FFMPEG_BUILD_DIR"

# Esegui FFmpeg
exec "$FFMPEG_BIN" "$@"

