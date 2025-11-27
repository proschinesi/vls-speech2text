#!/bin/bash
# Script di troubleshooting per ambiente locale (macOS/Linux)

echo "=== Troubleshooting VLS Speech-to-Text (Locale) ==="
echo ""

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Rileva OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macOS"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="Linux"
else
    OS="Unknown"
fi

echo -e "${BLUE}Sistema operativo: $OS${NC}"
echo ""

# Directory corrente come APP_DIR
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${YELLOW}[1] Verifica directory progetto...${NC}"
if [ -d "$APP_DIR" ]; then
    echo -e "${GREEN}✓ Directory trovata: $APP_DIR${NC}"
    if [ -w "$APP_DIR" ]; then
        echo -e "${GREEN}✓ Directory scrivibile${NC}"
    else
        echo -e "${RED}✗ Directory NON scrivibile${NC}"
    fi
else
    echo -e "${RED}✗ Directory non trovata${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}[2] Verifica file principali...${NC}"
FILES=("web_app.py" "vlc_speech2text.py" "requirements.txt")
for file in "${FILES[@]}"; do
    if [ -f "$APP_DIR/$file" ]; then
        echo -e "${GREEN}✓ $file trovato${NC}"
    else
        echo -e "${RED}✗ $file NON trovato${NC}"
    fi
done

echo ""
echo -e "${YELLOW}[3] Verifica ambiente virtuale...${NC}"
if [ -d "$APP_DIR/venv" ]; then
    echo -e "${GREEN}✓ Ambiente virtuale trovato${NC}"
    if [ -f "$APP_DIR/venv/bin/activate" ]; then
        echo -e "${GREEN}✓ Script di attivazione presente${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Ambiente virtuale non trovato${NC}"
    echo "  Crea con: python3 -m venv venv"
fi

echo ""
echo -e "${YELLOW}[4] Verifica dipendenze Python...${NC}"
if [ -d "$APP_DIR/venv" ]; then
    if $APP_DIR/venv/bin/python --version &>/dev/null; then
        PYTHON_VERSION=$($APP_DIR/venv/bin/python --version)
        echo -e "${GREEN}✓ Python: $PYTHON_VERSION${NC}"
        
        # Verifica pacchetti principali
        PACKAGES=("flask" "whisper" "torch")
        for pkg in "${PACKAGES[@]}"; do
            if $APP_DIR/venv/bin/pip show $pkg &>/dev/null; then
                VERSION=$($APP_DIR/venv/bin/pip show $pkg | grep "^Version:" | cut -d' ' -f2)
                echo -e "${GREEN}  ✓ $pkg ($VERSION)${NC}"
            else
                echo -e "${RED}  ✗ $pkg NON installato${NC}"
            fi
        done
    else
        echo -e "${RED}✗ Python non disponibile nell'ambiente virtuale${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Salta verifica (venv non presente)${NC}"
fi

echo ""
echo -e "${YELLOW}[5] Verifica FFmpeg...${NC}"
if command -v ffmpeg &> /dev/null; then
    FFMPEG_VERSION=$(ffmpeg -version 2>/dev/null | head -1)
    echo -e "${GREEN}✓ FFmpeg installato${NC}"
    echo "  $FFMPEG_VERSION"
else
    echo -e "${RED}✗ FFmpeg NON installato${NC}"
    if [[ "$OS" == "macOS" ]]; then
        echo "  Installa con: brew install ffmpeg"
    else
        echo "  Installa con: sudo apt-get install ffmpeg"
    fi
fi

echo ""
echo -e "${YELLOW}[6] Verifica VLC (opzionale)...${NC}"
if command -v vlc &> /dev/null; then
    VLC_VERSION=$(vlc --version 2>/dev/null | head -1)
    echo -e "${GREEN}✓ VLC installato${NC}"
    echo "  $VLC_VERSION"
else
    echo -e "${YELLOW}⚠ VLC non trovato (opzionale)${NC}"
    if [[ "$OS" == "macOS" ]]; then
        echo "  Installa con: brew install --cask vlc"
    else
        echo "  Installa con: sudo apt-get install vlc"
    fi
fi

echo ""
echo -e "${YELLOW}[7] Verifica porta 5000...${NC}"
if [[ "$OS" == "macOS" ]]; then
    # macOS usa lsof
    if lsof -i :5000 &>/dev/null; then
        echo -e "${YELLOW}⚠ Porta 5000 in uso${NC}"
        echo "  Processi:"
        lsof -i :5000 | grep LISTEN
        echo ""
        echo "  Per liberare la porta:"
        echo "    kill \$(lsof -t -i:5000)"
    else
        echo -e "${GREEN}✓ Porta 5000 libera${NC}"
    fi
else
    # Linux
    if netstat -tlnp 2>/dev/null | grep -q ":5000"; then
        echo -e "${YELLOW}⚠ Porta 5000 in uso${NC}"
        netstat -tlnp 2>/dev/null | grep ":5000"
    else
        echo -e "${GREEN}✓ Porta 5000 libera${NC}"
    fi
fi

echo ""
echo -e "${YELLOW}[8] Verifica che l'app risponda...${NC}"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✓ App risponde correttamente (200 OK)${NC}"
elif [ "$HTTP_CODE" = "403" ]; then
    echo -e "${RED}✗ Errore 403 Forbidden${NC}"
    echo "  Possibili cause:"
    echo "  - Permessi file/directory errati"
    echo "  - Template non trovati"
    echo "  - Configurazione Flask"
elif [ "$HTTP_CODE" = "000" ]; then
    echo -e "${YELLOW}⚠ App non risponde (non in esecuzione?)${NC}"
    echo "  Avvia con: ./start_web.sh"
else
    echo -e "${YELLOW}⚠ Codice HTTP: $HTTP_CODE${NC}"
fi

echo ""
echo -e "${YELLOW}[9] Verifica template HTML...${NC}"
TEMPLATE_DIR="$APP_DIR/templates"
if [ -d "$TEMPLATE_DIR" ]; then
    echo -e "${GREEN}✓ Directory templates trovata${NC}"
    TEMPLATES=("index.html" "index_simple.html")
    for tpl in "${TEMPLATES[@]}"; do
        if [ -f "$TEMPLATE_DIR/$tpl" ]; then
            SIZE=$(wc -c < "$TEMPLATE_DIR/$tpl")
            echo -e "${GREEN}  ✓ $tpl (${SIZE} bytes)${NC}"
        else
            echo -e "${YELLOW}  ⚠ $tpl non trovato${NC}"
        fi
    done
else
    echo -e "${RED}✗ Directory templates non trovata${NC}"
fi

echo ""
echo -e "${YELLOW}[10] Test importazione moduli...${NC}"
if [ -d "$APP_DIR/venv" ]; then
    cd "$APP_DIR"
    source venv/bin/activate 2>/dev/null
    
    # Test import Flask
    if python3 -c "import flask" 2>/dev/null; then
        echo -e "${GREEN}✓ Flask importabile${NC}"
    else
        echo -e "${RED}✗ Flask NON importabile${NC}"
    fi
    
    # Test import whisper
    if python3 -c "import whisper" 2>/dev/null; then
        echo -e "${GREEN}✓ Whisper importabile${NC}"
    else
        echo -e "${RED}✗ Whisper NON importabile${NC}"
    fi
    
    # Test import vlc_speech2text
    if python3 -c "import sys; sys.path.insert(0, '.'); from vlc_speech2text import VLCSpeechToText" 2>/dev/null; then
        echo -e "${GREEN}✓ vlc_speech2text importabile${NC}"
    else
        echo -e "${RED}✗ vlc_speech2text NON importabile${NC}"
        echo "  Errore:"
        python3 -c "import sys; sys.path.insert(0, '.'); from vlc_speech2text import VLCSpeechToText" 2>&1 | head -3
    fi
else
    echo -e "${YELLOW}⚠ Salta test (venv non presente)${NC}"
fi

echo ""
echo -e "${YELLOW}[11] Verifica permessi file eseguibili...${NC}"
SCRIPTS=("start_web.sh" "vlc_stt.sh" "web_app.py")
for script in "${SCRIPTS[@]}"; do
    if [ -f "$APP_DIR/$script" ]; then
        if [ -x "$APP_DIR/$script" ]; then
            echo -e "${GREEN}✓ $script eseguibile${NC}"
        else
            echo -e "${YELLOW}⚠ $script non eseguibile${NC}"
            echo "  Rendi eseguibile con: chmod +x $script"
        fi
    fi
done

echo ""
echo "=== Fine diagnostica ==="
echo ""
echo "Comandi utili:"
echo "  Avvia server: ./start_web.sh"
echo "  Avvia con debug: ./start_web.sh --debug"
echo "  Avvia su porta diversa: ./start_web.sh --port 8080"
echo "  Test connessione: curl http://localhost:5000"
echo ""

