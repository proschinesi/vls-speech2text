#!/bin/bash
# Script rapido per aggiornare il codice sulla droplet
# Eseguire questo script sulla droplet per fare pull del codice aggiornato

set -e

APP_DIR="/opt/vls-speech2text"

if [ ! -d "$APP_DIR" ]; then
    echo "Errore: Directory $APP_DIR non trovata."
    echo "Esegui prima deploy.sh per la configurazione iniziale."
    exit 1
fi

echo "=== Aggiornamento codice ==="
cd $APP_DIR

# Pull del codice
echo "Aggiornamento da GitHub..."
git pull

# Aggiorna dipendenze se necessario
echo "Verifica dipendenze..."
if [ -f "requirements.txt" ]; then
    $APP_DIR/venv/bin/pip install -r requirements.txt --upgrade
fi

# Riavvia il servizio
echo "Riavvio servizio..."
sudo systemctl restart vls-speech2text

echo "=== Aggiornamento completato! ==="
echo "Verifica lo stato con: sudo systemctl status vls-speech2text"

