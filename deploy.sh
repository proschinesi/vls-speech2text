#!/bin/bash
# Script di deploy per DigitalOcean Droplet
# Eseguire questo script sulla droplet dopo aver clonato il repository

set -e

echo "=== Deploy VLS Speech-to-Text su DigitalOcean ==="

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Verifica che siamo su Ubuntu/Debian
if ! command -v apt-get &> /dev/null; then
    echo -e "${RED}Errore: Questo script è progettato per Ubuntu/Debian${NC}"
    exit 1
fi

# Verifica che siamo root o con sudo
if [ "$EUID" -ne 0 ]; then 
    echo -e "${YELLOW}Nota: Alcuni comandi richiedono sudo. Assicurati di avere i permessi.${NC}"
fi

echo -e "${GREEN}[1/6] Aggiornamento sistema...${NC}"
sudo apt-get update
sudo apt-get upgrade -y

echo -e "${GREEN}[2/6] Installazione dipendenze di sistema...${NC}"
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    ffmpeg \
    vlc \
    git \
    nginx \
    supervisor \
    ufw

echo -e "${GREEN}[3/6] Configurazione ambiente Python...${NC}"
# Crea directory per l'applicazione
APP_DIR="/opt/vls-speech2text"
sudo mkdir -p $APP_DIR

# Se il repo è già clonato, fai pull
if [ -d "$APP_DIR/.git" ]; then
    echo "Repository già presente, aggiornamento..."
    cd $APP_DIR
    sudo git pull
else
    echo "Clonazione repository..."
    # Sostituisci con il tuo URL GitHub
    sudo git clone https://github.com/proschinesi/vls-speech2text.git $APP_DIR
fi

# Crea ambiente virtuale
if [ ! -d "$APP_DIR/venv" ]; then
    echo "Creazione ambiente virtuale..."
    sudo python3 -m venv $APP_DIR/venv
fi

# Installa dipendenze Python
echo "Installazione dipendenze Python..."
sudo $APP_DIR/venv/bin/pip install --upgrade pip
sudo $APP_DIR/venv/bin/pip install -r $APP_DIR/requirements.txt

# Imposta permessi
sudo chown -R $USER:$USER $APP_DIR

echo -e "${GREEN}[4/6] Configurazione systemd service...${NC}"
# Crea file systemd service
sudo tee /etc/systemd/system/vls-speech2text.service > /dev/null <<EOF
[Unit]
Description=VLS Speech-to-Text Web Application
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/web_app.py --host 0.0.0.0 --port 5000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Ricarica systemd e avvia servizio
sudo systemctl daemon-reload
sudo systemctl enable vls-speech2text
sudo systemctl start vls-speech2text

echo -e "${GREEN}[5/6] Configurazione firewall...${NC}"
# Configura UFW
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 5000/tcp
sudo ufw --force enable

echo -e "${GREEN}[6/6] Configurazione Nginx (opzionale)...${NC}"
# Crea configurazione Nginx
sudo tee /etc/nginx/sites-available/vls-speech2text > /dev/null <<EOF
server {
    listen 80;
    server_name _;

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
}
EOF

# Abilita sito Nginx
sudo ln -sf /etc/nginx/sites-available/vls-speech2text /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx

echo -e "${GREEN}=== Deploy completato! ===${NC}"
echo ""
echo "L'applicazione è disponibile su:"
echo "  - Diretto: http://$(curl -s ifconfig.me):5000"
echo "  - Via Nginx: http://$(curl -s ifconfig.me)"
echo ""
echo "Comandi utili:"
echo "  - Stato servizio: sudo systemctl status vls-speech2text"
echo "  - Log servizio: sudo journalctl -u vls-speech2text -f"
echo "  - Riavvia servizio: sudo systemctl restart vls-speech2text"
echo "  - Stop servizio: sudo systemctl stop vls-speech2text"
echo ""

