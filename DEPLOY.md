# Guida al Deploy su DigitalOcean Droplet

Questa guida spiega come deployare l'applicazione VLS Speech-to-Text su una droplet di DigitalOcean.

## Prerequisiti

- Una droplet DigitalOcean con Ubuntu 20.04+ o Debian 11+
- Accesso SSH alla droplet
- Repository GitHub già configurato (https://github.com/proschinesi/vls-speech2text)

## Metodo 1: Deploy Automatico (Consigliato)

### Passo 1: Connettiti alla droplet

```bash
ssh root@TUO_IP_DROPLET
# oppure
ssh utente@TUO_IP_DROPLET
```

### Passo 2: Clona il repository

```bash
cd /opt
sudo git clone https://github.com/proschinesi/vls-speech2text.git
cd vls-speech2text
```

### Passo 3: Esegui lo script di deploy

```bash
chmod +x deploy.sh
sudo ./deploy.sh
```

Lo script installerà automaticamente:
- Python 3 e dipendenze
- FFmpeg e VLC
- Dipendenze Python (Whisper, Flask, etc.)
- Configurazione systemd per avvio automatico
- Configurazione Nginx come reverse proxy
- Configurazione firewall (UFW)

### Passo 4: Verifica il deploy

```bash
# Controlla lo stato del servizio
sudo systemctl status vls-speech2text

# Controlla i log
sudo journalctl -u vls-speech2text -f

# Verifica che l'app risponda
curl http://localhost:5000
```

L'applicazione sarà disponibile su:
- **Diretto**: `http://TUO_IP:5000`
- **Via Nginx**: `http://TUO_IP` (porta 80)

## Metodo 2: Deploy Manuale

### 1. Aggiorna il sistema

```bash
sudo apt-get update
sudo apt-get upgrade -y
```

### 2. Installa dipendenze di sistema

```bash
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    ffmpeg \
    vlc \
    git \
    nginx
```

### 3. Clona il repository

```bash
cd /opt
sudo git clone https://github.com/proschinesi/vls-speech2text.git
cd vls-speech2text
```

### 4. Crea ambiente virtuale e installa dipendenze

```bash
sudo python3 -m venv venv
sudo venv/bin/pip install --upgrade pip
sudo venv/bin/pip install -r requirements.txt
```

### 5. Configura systemd service

Crea il file `/etc/systemd/system/vls-speech2text.service`:

```ini
[Unit]
Description=VLS Speech-to-Text Web Application
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/vls-speech2text
Environment="PATH=/opt/vls-speech2text/venv/bin"
ExecStart=/opt/vls-speech2text/venv/bin/python /opt/vls-speech2text/web_app.py --host 0.0.0.0 --port 5000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Poi:

```bash
sudo systemctl daemon-reload
sudo systemctl enable vls-speech2text
sudo systemctl start vls-speech2text
```

### 6. Configura Nginx (opzionale)

Crea `/etc/nginx/sites-available/vls-speech2text`:

```nginx
server {
    listen 80;
    server_name _;

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
}
```

Abilita il sito:

```bash
sudo ln -s /etc/nginx/sites-available/vls-speech2text /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

### 7. Configura firewall

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 5000/tcp
sudo ufw enable
```

## Aggiornamento del Codice

Per aggiornare il codice dopo aver fatto push su GitHub:

### Metodo rapido (usa lo script):

```bash
cd /opt/vls-speech2text
./deploy_quick.sh
```

### Metodo manuale:

```bash
cd /opt/vls-speech2text
sudo git pull
sudo venv/bin/pip install -r requirements.txt --upgrade
sudo systemctl restart vls-speech2text
```

## Gestione del Servizio

### Comandi utili

```bash
# Avvia servizio
sudo systemctl start vls-speech2text

# Ferma servizio
sudo systemctl stop vls-speech2text

# Riavvia servizio
sudo systemctl restart vls-speech2text

# Stato servizio
sudo systemctl status vls-speech2text

# Log in tempo reale
sudo journalctl -u vls-speech2text -f

# Log ultimi 100 righe
sudo journalctl -u vls-speech2text -n 100
```

## Troubleshooting

### Il servizio non si avvia

1. Controlla i log:
   ```bash
   sudo journalctl -u vls-speech2text -n 50
   ```

2. Verifica che Python e le dipendenze siano installate:
   ```bash
   /opt/vls-speech2text/venv/bin/python --version
   /opt/vls-speech2text/venv/bin/pip list
   ```

3. Prova ad avviare manualmente:
   ```bash
   cd /opt/vls-speech2text
   source venv/bin/activate
   python web_app.py --host 0.0.0.0 --port 5000
   ```

### L'app non risponde

1. Verifica che il servizio sia in esecuzione:
   ```bash
   sudo systemctl status vls-speech2text
   ```

2. Verifica che la porta sia aperta:
   ```bash
   sudo netstat -tlnp | grep 5000
   ```

3. Controlla il firewall:
   ```bash
   sudo ufw status
   ```

### Problemi con FFmpeg o VLC

1. Verifica installazione:
   ```bash
   ffmpeg -version
   vlc --version
   ```

2. Se mancano, reinstalla:
   ```bash
   sudo apt-get install --reinstall ffmpeg vlc
   ```

### Problemi con Whisper

1. Verifica che il modello sia scaricato:
   ```bash
   ls -la ~/.cache/whisper/
   ```

2. I modelli vengono scaricati automaticamente al primo utilizzo.

## Configurazione Avanzata

### Cambiare porta

Modifica `/etc/systemd/system/vls-speech2text.service` e cambia `--port 5000` con la porta desiderata.

Poi:
```bash
sudo systemctl daemon-reload
sudo systemctl restart vls-speech2text
```

### SSL/HTTPS con Let's Encrypt

```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d tuo-dominio.com
```

### Monitoraggio risorse

```bash
# CPU e memoria
htop

# Spazio disco
df -h

# Processi Python
ps aux | grep python
```

## Note Importanti

- **Memoria**: Whisper richiede almeno 2GB di RAM per modelli base, 4GB+ per modelli più grandi
- **CPU**: Il processamento è CPU-intensive, considera una droplet con almeno 2 vCPU
- **Storage**: I modelli Whisper occupano spazio (da 75MB a 3GB a seconda del modello)
- **Network**: Per stream video, assicurati di avere una buona connessione

## Supporto

Per problemi o domande, apri una issue su GitHub: https://github.com/proschinesi/vls-speech2text/issues

