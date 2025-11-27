#!/bin/bash
# Script per verificare errori comuni

echo "=== Verifica Errori ==="
echo ""

cd "$(dirname "$0")"

echo "[1] Verifica sintassi Python..."
python3 -m py_compile web_app.py 2>&1 && echo "✓ web_app.py OK" || echo "✗ Errore sintassi web_app.py"
python3 -m py_compile vlc_speech2text.py 2>&1 && echo "✓ vlc_speech2text.py OK" || echo "✗ Errore sintassi vlc_speech2text.py"

echo ""
echo "[2] Verifica import..."
source venv/bin/activate 2>/dev/null || echo "⚠ venv non attivo"
python3 -c "
import sys
sys.path.insert(0, '.')
try:
    import web_app
    print('✓ Import web_app OK')
except Exception as e:
    print(f'✗ Errore import web_app: {e}')
    import traceback
    traceback.print_exc()
"

echo ""
echo "[3] Verifica processi FFmpeg..."
FFMPEG_COUNT=$(ps aux | grep -c "ffmpeg.*video_session" | grep -v grep || echo "0")
echo "Processi FFmpeg attivi: $FFMPEG_COUNT"
if [ "$FFMPEG_COUNT" -gt "5" ]; then
    echo "⚠ Troppi processi FFmpeg! Esegui: pkill -f 'ffmpeg.*video_session'"
fi

echo ""
echo "[4] Verifica file temporanei..."
TEMP_FILES=$(ls /tmp/*session*.ts /tmp/*session*.srt 2>/dev/null | wc -l)
echo "File temporanei trovati: $TEMP_FILES"

echo ""
echo "[5] Verifica server..."
if curl -s http://localhost:8080 > /dev/null 2>&1; then
    echo "✓ Server risponde"
else
    echo "✗ Server non risponde"
fi

echo ""
echo "=== Fine verifica ==="

