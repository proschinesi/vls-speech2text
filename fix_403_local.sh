#!/bin/bash
# Script per risolvere errori 403 in ambiente locale

set -e

echo "=== Fix Errori 403 (Locale) ==="
echo ""

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${YELLOW}[1] Correzione permessi directory...${NC}"
chmod -R 755 "$APP_DIR"
echo -e "${GREEN}✓ Permessi corretti${NC}"

echo ""
echo -e "${YELLOW}[2] Verifica permessi file Python...${NC}"
find "$APP_DIR" -name "*.py" -exec chmod 644 {} \;
chmod +x "$APP_DIR/web_app.py" 2>/dev/null || true
echo -e "${GREEN}✓ Permessi file Python corretti${NC}"

echo ""
echo -e "${YELLOW}[3] Verifica permessi script...${NC}"
chmod +x "$APP_DIR"/*.sh 2>/dev/null || true
echo -e "${GREEN}✓ Script resi eseguibili${NC}"

echo ""
echo -e "${YELLOW}[4] Verifica directory templates...${NC}"
TEMPLATE_DIR="$APP_DIR/templates"
if [ -d "$TEMPLATE_DIR" ]; then
    chmod -R 755 "$TEMPLATE_DIR"
    echo -e "${GREEN}✓ Permessi templates corretti${NC}"
    
    # Verifica file template
    if [ ! -f "$TEMPLATE_DIR/index.html" ] && [ ! -f "$TEMPLATE_DIR/index_simple.html" ]; then
        echo -e "${RED}✗ Nessun template trovato!${NC}"
        echo "  Crea almeno un template in $TEMPLATE_DIR"
    fi
else
    echo -e "${YELLOW}⚠ Directory templates non trovata${NC}"
    mkdir -p "$TEMPLATE_DIR"
    echo "  Directory creata"
fi

echo ""
echo -e "${YELLOW}[5] Verifica ambiente virtuale...${NC}"
if [ ! -d "$APP_DIR/venv" ]; then
    echo -e "${YELLOW}⚠ Ambiente virtuale non trovato, creazione...${NC}"
    cd "$APP_DIR"
    python3 -m venv venv
    echo -e "${GREEN}✓ Ambiente virtuale creato${NC}"
fi

echo ""
echo -e "${YELLOW}[6] Verifica dipendenze...${NC}"
if [ -f "$APP_DIR/requirements.txt" ]; then
    cd "$APP_DIR"
    source venv/bin/activate 2>/dev/null || true
    pip install -q -r requirements.txt 2>/dev/null || {
        echo -e "${YELLOW}⚠ Alcune dipendenze potrebbero non essere installate${NC}"
        echo "  Installa manualmente con: pip install -r requirements.txt"
    }
    echo -e "${GREEN}✓ Dipendenze verificate${NC}"
fi

echo ""
echo -e "${YELLOW}[7] Test configurazione Flask...${NC}"
cd "$APP_DIR"
source venv/bin/activate 2>/dev/null || true

# Test che web_app.py possa essere importato
if python3 -c "import sys; sys.path.insert(0, '.'); import web_app" 2>/dev/null; then
    echo -e "${GREEN}✓ web_app.py importabile${NC}"
else
    echo -e "${RED}✗ Errore importazione web_app.py${NC}"
    python3 -c "import sys; sys.path.insert(0, '.'); import web_app" 2>&1 | head -5
fi

echo ""
echo -e "${YELLOW}[8] Verifica porta 5000...${NC}"
# Rileva OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    if lsof -i :5000 &>/dev/null; then
        echo -e "${YELLOW}⚠ Porta 5000 in uso${NC}"
        echo "  Processi:"
        lsof -i :5000 | grep LISTEN
        echo ""
        read -p "Vuoi terminare i processi sulla porta 5000? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            kill $(lsof -t -i:5000) 2>/dev/null || true
            sleep 1
            echo -e "${GREEN}✓ Porta 5000 liberata${NC}"
        fi
    else
        echo -e "${GREEN}✓ Porta 5000 libera${NC}"
    fi
else
    if netstat -tlnp 2>/dev/null | grep -q ":5000"; then
        echo -e "${YELLOW}⚠ Porta 5000 in uso${NC}"
    else
        echo -e "${GREEN}✓ Porta 5000 libera${NC}"
    fi
fi

echo ""
echo -e "${YELLOW}[9] Test avvio server...${NC}"
echo "Per testare, avvia il server con:"
echo "  ./start_web.sh"
echo ""
echo "Oppure direttamente:"
echo "  cd $APP_DIR"
echo "  source venv/bin/activate"
echo "  python web_app.py --host 127.0.0.1 --port 5000"
echo ""

echo ""
echo "=== Fine fix ==="
echo ""
echo "Prossimi passi:"
echo "1. Avvia il server: ./start_web.sh"
echo "2. Apri browser: http://localhost:5000"
echo "3. Se ancora 403, controlla i log del server"
echo ""

