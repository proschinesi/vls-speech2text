#!/bin/bash
# Script di troubleshooting per errori 403 e altri problemi

echo "=== Troubleshooting VLS Speech-to-Text ==="
echo ""

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

APP_DIR="/opt/vls-speech2text"

echo -e "${YELLOW}[1] Verifica stato servizio systemd...${NC}"
if systemctl is-active --quiet vls-speech2text; then
    echo -e "${GREEN}✓ Servizio attivo${NC}"
else
    echo -e "${RED}✗ Servizio NON attivo${NC}"
    echo "  Esegui: sudo systemctl status vls-speech2text"
fi

echo ""
echo -e "${YELLOW}[2] Verifica permessi directory...${NC}"
if [ -d "$APP_DIR" ]; then
    ls -la $APP_DIR | head -5
    if [ -w "$APP_DIR" ]; then
        echo -e "${GREEN}✓ Directory scrivibile${NC}"
    else
        echo -e "${RED}✗ Directory NON scrivibile${NC}"
        echo "  Esegui: sudo chown -R \$USER:\$USER $APP_DIR"
    fi
else
    echo -e "${RED}✗ Directory non trovata: $APP_DIR${NC}"
fi

echo ""
echo -e "${YELLOW}[3] Verifica che l'app risponda localmente...${NC}"
if curl -s http://localhost:5000 > /dev/null; then
    echo -e "${GREEN}✓ App risponde su localhost:5000${NC}"
else
    echo -e "${RED}✗ App NON risponde su localhost:5000${NC}"
    echo "  Controlla i log: sudo journalctl -u vls-speech2text -n 50"
fi

echo ""
echo -e "${YELLOW}[4] Verifica porta 5000 in ascolto...${NC}"
if netstat -tlnp 2>/dev/null | grep -q ":5000"; then
    echo -e "${GREEN}✓ Porta 5000 in ascolto${NC}"
    netstat -tlnp 2>/dev/null | grep ":5000"
else
    echo -e "${RED}✗ Porta 5000 NON in ascolto${NC}"
fi

echo ""
echo -e "${YELLOW}[5] Verifica configurazione Nginx...${NC}"
if [ -f "/etc/nginx/sites-enabled/vls-speech2text" ]; then
    echo -e "${GREEN}✓ Configurazione Nginx trovata${NC}"
    if nginx -t 2>&1 | grep -q "successful"; then
        echo -e "${GREEN}✓ Configurazione Nginx valida${NC}"
    else
        echo -e "${RED}✗ Configurazione Nginx NON valida${NC}"
        nginx -t
    fi
else
    echo -e "${YELLOW}⚠ Configurazione Nginx non trovata${NC}"
fi

echo ""
echo -e "${YELLOW}[6] Verifica firewall...${NC}"
if command -v ufw &> /dev/null; then
    ufw status | head -10
else
    echo "UFW non installato o non disponibile"
fi

echo ""
echo -e "${YELLOW}[7] Verifica log recenti...${NC}"
echo "Ultimi 10 log del servizio:"
sudo journalctl -u vls-speech2text -n 10 --no-pager

echo ""
echo -e "${YELLOW}[8] Verifica utente servizio...${NC}"
SERVICE_USER=$(grep "^User=" /etc/systemd/system/vls-speech2text.service 2>/dev/null | cut -d'=' -f2)
if [ -n "$SERVICE_USER" ]; then
    echo "Utente servizio: $SERVICE_USER"
    echo "Verifica permessi:"
    sudo -u $SERVICE_USER test -r $APP_DIR/web_app.py && echo -e "${GREEN}✓ File leggibile${NC}" || echo -e "${RED}✗ File NON leggibile${NC}"
else
    echo -e "${RED}✗ Utente servizio non trovato${NC}"
fi

echo ""
echo -e "${YELLOW}[9] Test connessione diretta...${NC}"
echo "Testando http://127.0.0.1:5000..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000)
if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✓ Risposta 200 OK${NC}"
elif [ "$HTTP_CODE" = "403" ]; then
    echo -e "${RED}✗ Errore 403 Forbidden${NC}"
    echo "  Possibili cause:"
    echo "  - Permessi file/directory errati"
    echo "  - Configurazione Flask che blocca l'accesso"
    echo "  - SELinux o AppArmor attivo"
elif [ "$HTTP_CODE" = "000" ]; then
    echo -e "${RED}✗ Nessuna connessione (servizio non in esecuzione?)${NC}"
else
    echo -e "${YELLOW}⚠ Codice HTTP: $HTTP_CODE${NC}"
fi

echo ""
echo -e "${YELLOW}[10] Verifica SELinux/AppArmor...${NC}"
if command -v getenforce &> /dev/null; then
    SELINUX_STATUS=$(getenforce 2>/dev/null)
    if [ "$SELINUX_STATUS" = "Enforcing" ]; then
        echo -e "${YELLOW}⚠ SELinux in modalità Enforcing (potrebbe bloccare)${NC}"
    else
        echo "SELinux: $SELINUX_STATUS"
    fi
fi

echo ""
echo "=== Fine diagnostica ==="
echo ""
echo "Soluzioni comuni per errore 403:"
echo "1. Rivedi permessi: sudo chown -R \$USER:\$USER $APP_DIR"
echo "2. Verifica utente servizio in /etc/systemd/system/vls-speech2text.service"
echo "3. Controlla log: sudo journalctl -u vls-speech2text -f"
echo "4. Riavvia servizio: sudo systemctl restart vls-speech2text"
echo "5. Test diretto: curl http://127.0.0.1:5000"

