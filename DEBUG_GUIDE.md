# Guida al Debug

## Come identificare gli errori

### 1. Console del Browser

1. Apri `http://localhost:8080`
2. Premi **F12** (o Cmd+Option+I su Mac)
3. Vai alla tab **Console**
4. Prova a riprodurre un video
5. Cerca messaggi in **rosso** (errori)

### 2. Log del Server

```bash
# Vedi log in tempo reale
tail -f /tmp/web_app.log

# Cerca errori
tail -100 /tmp/web_app.log | grep -i error
```

### 3. Pagina di Debug

Vai su `http://localhost:8080/debug` per vedere:
- Sessioni attive
- Processi FFmpeg
- Stato dell'applicazione

### 4. Test API

```bash
# Status di una sessione
curl http://localhost:8080/api/status/session_1

# Verifica che il server risponda
curl http://localhost:8080
```

## Errori Comuni

### Errore 403
- **Causa**: Permessi o configurazione
- **Fix**: Vedi `TROUBLESHOOTING_LOCAL.md`

### Video non si riproduce
- **Causa**: Formato non supportato o pipe non funzionante
- **Check**: Console browser per errori video
- **Fix**: Prova con un URL video diverso

### "Stream non disponibile"
- **Causa**: FFmpeg non ha creato la pipe/file
- **Check**: `/tmp/video_session_*.ts` esiste?
- **Fix**: Controlla log server per errori FFmpeg

### Processi FFmpeg accumulati
- **Causa**: Sessioni non terminate correttamente
- **Fix**: `pkill -f "ffmpeg.*video_session"`

## Comandi Utili

```bash
# Verifica errori
./check_errors.sh

# Pulisci processi FFmpeg
pkill -f "ffmpeg.*video_session"

# Riavvia server
kill $(lsof -t -i:8080)
cd /Users/ube/vls-speech2text
source venv/bin/activate
python web_app.py --host 127.0.0.1 --port 8080
```

## Report Errori

Quando riporti un errore, includi:
1. Messaggio di errore esatto
2. Quando si verifica (avvio, riproduzione, etc.)
3. Output console browser (F12)
4. Ultime righe del log: `tail -50 /tmp/web_app.log`

