#!/bin/bash
# Script per risolvere errori 403 comuni

set -e

echo "=== Fix Errori 403 ==="

APP_DIR="/opt/vls-speech2text"
SERVICE_USER=$(whoami)

# Se eseguito come root, usa un utente non-root
if [ "$EUID" -eq 0 ]; then
    if id "ubuntu" &>/dev/null; then
        SERVICE_USER="ubuntu"
    elif id "debian" &>/dev/null; then
        SERVICE_USER="debian"
    else
        SERVICE_USER=$(ls /home | head -1)
    fi
    echo "Trovato utente: $SERVICE_USER"
fi

echo ""
echo "[1] Correzione permessi directory..."
if [ -d "$APP_DIR" ]; then
    sudo chown -R $SERVICE_USER:$SERVICE_USER $APP_DIR
    sudo chmod -R 755 $APP_DIR
    echo "✓ Permessi corretti"
else
    echo "✗ Directory non trovata: $APP_DIR"
    exit 1
fi

echo ""
echo "[2] Aggiornamento configurazione systemd..."
# Leggi l'utente corrente o usa quello trovato
sudo sed -i "s/^User=.*/User=$SERVICE_USER/" /etc/systemd/system/vls-speech2text.service 2>/dev/null || true

# Se non c'è la riga User, aggiungila
if ! grep -q "^User=" /etc/systemd/system/vls-speech2text.service; then
    sudo sed -i "/^\[Service\]/a User=$SERVICE_USER" /etc/systemd/system/vls-speech2text.service
fi

echo "✓ Configurazione systemd aggiornata"

echo ""
echo "[3] Verifica configurazione Flask..."
# Assicurati che web_app.py usi host 0.0.0.0
if grep -q "host='127.0.0.1'" $APP_DIR/web_app.py 2>/dev/null; then
    echo "⚠ Trovato host='127.0.0.1', dovrebbe essere '0.0.0.0'"
    echo "  Modifica manualmente web_app.py o usa --host 0.0.0.0"
fi

echo ""
echo "[4] Riavvio servizio..."
sudo systemctl daemon-reload
sudo systemctl restart vls-speech2text
sleep 2

echo ""
echo "[5] Verifica stato..."
if systemctl is-active --quiet vls-speech2text; then
    echo "✓ Servizio attivo"
else
    echo "✗ Servizio NON attivo, controlla i log:"
    echo "  sudo journalctl -u vls-speech2text -n 50"
fi

echo ""
echo "[6] Test connessione..."
sleep 2
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000 || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo "✓ App risponde correttamente (200 OK)"
elif [ "$HTTP_CODE" = "403" ]; then
    echo "✗ Ancora errore 403"
    echo ""
    echo "Prova anche:"
    echo "1. Verifica SELinux: sudo setenforce 0 (temporaneo)"
    echo "2. Controlla log: sudo journalctl -u vls-speech2text -f"
    echo "3. Test manuale: cd $APP_DIR && source venv/bin/activate && python web_app.py"
else
    echo "⚠ Codice HTTP: $HTTP_CODE"
fi

echo ""
echo "=== Fine fix ==="

