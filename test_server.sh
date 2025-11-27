#!/bin/bash
# Script per testare il server web

cd "$(dirname "$0")"

echo "=== Test Server Web Trascrizione Video ==="
echo ""

# Verifica dipendenze
echo "Verifica dipendenze..."
if ! python3 -c "import flask" 2>/dev/null; then
    echo "⚠ Flask non installato. Installazione..."
    if [ -d "venv" ]; then
        source venv/bin/activate
    fi
    pip install flask flask-cors
fi

# Verifica FFmpeg Whisper
echo ""
echo "Verifica supporto FFmpeg Whisper..."
if ffmpeg -filters 2>&1 | grep -qi whisper; then
    echo "✅ Filtro Whisper nativo DISPONIBILE"
else
    echo "⚠ Filtro Whisper nativo NON disponibile (userà Python Whisper)"
fi

echo ""
echo "Avvio server web..."
echo "Accessibile su: http://localhost:5000"
echo "Premi Ctrl+C per fermare"
echo ""

python3 web_app.py --host 0.0.0.0 --port 5000
