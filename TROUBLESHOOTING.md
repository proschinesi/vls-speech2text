# Troubleshooting - Errore 403

Se ricevi un errore **403 Forbidden** quando accedi all'applicazione, segui questa guida.

## Diagnostica Rapida

Esegui lo script di troubleshooting sulla droplet:

```bash
cd /opt/vls-speech2text
chmod +x troubleshoot.sh
./troubleshoot.sh
```

## Fix Automatico

Prova lo script di fix automatico:

```bash
cd /opt/vls-speech2text
chmod +x fix_403.sh
./fix_403.sh
```

## Soluzioni Manuali

### 1. Verifica Permessi Directory

```bash
APP_DIR="/opt/vls-speech2text"
sudo chown -R $USER:$USER $APP_DIR
sudo chmod -R 755 $APP_DIR
```

### 2. Verifica Utente Servizio Systemd

Controlla il file di servizio:

```bash
sudo cat /etc/systemd/system/vls-speech2text.service
```

Assicurati che la riga `User=` specifichi un utente valido (non root se possibile):

```ini
[Service]
User=ubuntu  # o il tuo utente
```

Poi ricarica e riavvia:

```bash
sudo systemctl daemon-reload
sudo systemctl restart vls-speech2text
```

### 3. Verifica che l'App Risponda Localmente

```bash
# Test locale
curl http://127.0.0.1:5000

# Se funziona localmente ma non da remoto, è un problema di firewall o Nginx
```

### 4. Controlla i Log

```bash
# Log del servizio
sudo journalctl -u vls-speech2text -n 50 -f

# Cerca errori di permessi o connessione
```

### 5. Verifica Firewall

```bash
# Controlla stato firewall
sudo ufw status

# Assicurati che le porte siano aperte
sudo ufw allow 5000/tcp
sudo ufw allow 80/tcp
```

### 6. Test Manuale dell'Applicazione

Avvia manualmente per vedere errori diretti:

```bash
cd /opt/vls-speech2text
source venv/bin/activate
python web_app.py --host 0.0.0.0 --port 5000
```

Se funziona manualmente ma non come servizio, il problema è nella configurazione systemd.

### 7. Verifica Configurazione Nginx

Se usi Nginx, controlla la configurazione:

```bash
sudo nginx -t
sudo cat /etc/nginx/sites-enabled/vls-speech2text
```

Assicurati che il proxy pass punti a `http://127.0.0.1:5000` e non a `http://localhost:5000`.

### 8. SELinux/AppArmor

Se SELinux è attivo, potrebbe bloccare:

```bash
# Verifica stato
getenforce

# Disabilita temporaneamente (solo per test)
sudo setenforce 0

# Se risolve, configura SELinux correttamente o disabilitalo permanentemente
```

### 9. Verifica Porta in Uso

```bash
# Controlla se la porta 5000 è in uso
sudo netstat -tlnp | grep 5000

# Se un altro processo usa la porta, cambia porta nell'app
```

### 10. Reinstallazione Servizio

Se nulla funziona, ricrea il servizio:

```bash
# Ferma servizio
sudo systemctl stop vls-speech2text
sudo systemctl disable vls-speech2text

# Rimuovi file servizio
sudo rm /etc/systemd/system/vls-speech2text.service

# Ricrea usando deploy.sh o manualmente
cd /opt/vls-speech2text
sudo ./deploy.sh
```

## Checklist Completa

- [ ] Servizio systemd attivo: `sudo systemctl status vls-speech2text`
- [ ] Porta 5000 in ascolto: `sudo netstat -tlnp | grep 5000`
- [ ] App risponde localmente: `curl http://127.0.0.1:5000`
- [ ] Permessi directory corretti: `ls -la /opt/vls-speech2text`
- [ ] Utente servizio valido: `grep User= /etc/systemd/system/vls-speech2text.service`
- [ ] Firewall configurato: `sudo ufw status`
- [ ] Nginx configurato (se usato): `sudo nginx -t`
- [ ] Nessun errore nei log: `sudo journalctl -u vls-speech2text -n 50`

## Errori Comuni

### "Permission denied" nei log

**Causa**: Permessi file/directory errati o utente servizio sbagliato.

**Soluzione**:
```bash
sudo chown -R $USER:$USER /opt/vls-speech2text
sudo chmod -R 755 /opt/vls-speech2text
```

### "Address already in use"

**Causa**: Porta 5000 già in uso.

**Soluzione**: Cambia porta o termina il processo:
```bash
sudo lsof -i :5000
sudo kill <PID>
```

### "Connection refused" da remoto

**Causa**: Firewall o app in ascolto solo su localhost.

**Soluzione**: 
- Verifica che `--host 0.0.0.0` sia usato
- Apri porta firewall: `sudo ufw allow 5000/tcp`

### Nginx restituisce 502 Bad Gateway

**Causa**: App non in esecuzione o Nginx non può connettersi.

**Soluzione**:
- Verifica che l'app sia attiva: `sudo systemctl status vls-speech2text`
- Verifica configurazione Nginx: `sudo nginx -t`

## Supporto

Se il problema persiste:
1. Esegui `./troubleshoot.sh` e condividi l'output
2. Condividi i log: `sudo journalctl -u vls-speech2text -n 100`
3. Apri una issue su GitHub con i dettagli

