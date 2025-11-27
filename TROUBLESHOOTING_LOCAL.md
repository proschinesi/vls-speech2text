# Troubleshooting Locale (macOS/Linux)

## Problema: Errore 403

### Diagnostica Rapida

Esegui lo script di troubleshooting:

```bash
./troubleshoot_local.sh
```

### Fix Automatico

```bash
./fix_403_local.sh
```

## Problemi Comuni

### 1. Porta 5000 Occupata (macOS)

Su macOS, la porta 5000 è spesso usata da **AirPlay Receiver**. 

**Soluzione**: Usa una porta diversa:

```bash
# Avvia su porta 8080
./start_web.sh --port 8080

# Oppure
python web_app.py --host 127.0.0.1 --port 8080
```

Poi accedi a: `http://localhost:8080`

**Disabilitare AirPlay Receiver** (opzionale):
1. Vai su **Preferenze di Sistema** → **Condivisione**
2. Disabilita **AirPlay Receiver**

### 2. Flask Non Installato

```bash
source venv/bin/activate
pip install flask flask-cors
```

### 3. Dipendenze Mancanti

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Permessi File

```bash
chmod +x web_app.py
chmod +x *.sh
chmod -R 755 templates/
```

### 5. Template Non Trovati

Verifica che la directory `templates/` contenga:
- `index.html` o
- `index_simple.html`

## Test Rapido

```bash
# 1. Attiva ambiente virtuale
source venv/bin/activate

# 2. Test import
python -c "import flask; import whisper; print('OK')"

# 3. Avvia server su porta alternativa
python web_app.py --host 127.0.0.1 --port 8080

# 4. In un altro terminale, testa
curl http://localhost:8080
```

## Verifica Configurazione

```bash
# Verifica Python
python --version  # Dovrebbe essere 3.8+

# Verifica FFmpeg
ffmpeg -version

# Verifica dipendenze
pip list | grep -E "flask|whisper|torch"
```

## Log e Debug

Avvia con debug per vedere errori dettagliati:

```bash
./start_web.sh --debug --port 8080
```

Gli errori verranno mostrati nel terminale.

## Porte Alternative Consigliate

- `8080` - Porta comune per sviluppo
- `5001` - Alternativa a 5000
- `8000` - Altra opzione comune
- `3000` - Porta spesso usata per web apps

## Comandi Utili

```bash
# Verifica porta in uso (macOS)
lsof -i :5000

# Verifica porta in uso (Linux)
netstat -tlnp | grep 5000

# Libera porta (ATTENZIONE: termina processi)
kill $(lsof -t -i:5000)  # macOS
```

## Se Nulla Funziona

1. **Reinstalla ambiente virtuale**:
   ```bash
   rm -rf venv
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Test minimo Flask**:
   ```bash
   python -c "from flask import Flask; app = Flask(__name__); app.run(port=8080)"
   ```
   Se questo funziona, il problema è in `web_app.py`.

3. **Controlla log Python**:
   ```bash
   python web_app.py --port 8080 2>&1 | tee server.log
   ```

