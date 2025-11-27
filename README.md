# VLC Speech-to-Text

Script per lanciare VLC da linea di comando con output speech-to-text incorporato utilizzando Whisper.

## 🚀 Deploy su DigitalOcean

Per deployare l'applicazione su una droplet DigitalOcean, consulta la [guida completa di deploy](DEPLOY.md).

**Deploy rapido:**
```bash
# Sulla droplet
cd /opt
sudo git clone https://github.com/proschinesi/vls-speech2text.git
cd vls-speech2text
sudo ./deploy.sh
```

---

## Script disponibili

Questo progetto include tre approcci per la trascrizione:

1. **`web_app.py`** - **NUOVO!** Interfaccia web accessibile da remoto per riprodurre video con sottotitoli burn-in
2. **`vlc_speech2text.py`** - Usa Python Whisper (funziona con qualsiasi versione di FFmpeg)
3. **`ffmpeg_whisper.py`** - Usa il filtro Whisper integrato in FFmpeg 8.0+ (richiede FFmpeg compilato con `--enable-whisper`)

---

## 🌐 Interfaccia Web (web_app.py)

**Nuovo!** Applicazione web Flask per trascrivere e riprodurre video con sottotitoli burn-in in tempo reale, accessibile da remoto.

### Caratteristiche

- ✅ Interfaccia web moderna e intuitiva
- ✅ Accessibile da remoto (configurabile)
- ✅ Riproduzione video con sottotitoli burn-in in tempo reale
- ✅ Supporto per URL video e file locali
- ✅ Selezione lingua e modello Whisper
- ✅ Aggiornamento sottotitoli in tempo reale durante la riproduzione

### Avvio rapido

```bash
# Installa dipendenze (se non già fatto)
pip install -r requirements.txt

# Avvia il server web
./start_web.sh

# Oppure direttamente:
python web_app.py
```

Il server sarà accessibile su `http://localhost:5000` (o l'IP del tuo computer per accesso remoto).

### Accesso remoto

Per rendere il server accessibile da altri dispositivi sulla rete:

```bash
# Avvia con host 0.0.0.0 (accessibile da qualsiasi IP)
python web_app.py --host 0.0.0.0 --port 5000

# Oppure con lo script
./start_web.sh --host 0.0.0.0 --port 5000
```

Poi accedi da un altro dispositivo usando l'IP del computer: `http://<IP_COMPUTER>:5000`

### Utilizzo

1. Apri il browser e vai all'URL del server (es. `http://localhost:5000`)
2. Inserisci l'URL del video o il percorso del file
3. Seleziona lingua e modello Whisper (opzionale)
4. Clicca su "▶️ Riproduci con Sottotitoli"
5. Il video verrà riprodotto con sottotitoli burn-in generati in tempo reale

### Opzioni da linea di comando

```bash
python web_app.py [OPZIONI]

Opzioni:
  --host HOST         Host su cui ascoltare (default: 0.0.0.0 per accesso remoto)
  --port PORT         Porta del server (default: 5000)
  --debug             Modalità debug
```

### Esempi

```bash
# Server locale (solo localhost)
python web_app.py --host 127.0.0.1 --port 5000

# Server remoto (accessibile da rete)
python web_app.py --host 0.0.0.0 --port 8080

# Con debug attivo
python web_app.py --debug
```

### Note

- Il server gestisce automaticamente più sessioni simultanee
- I sottotitoli vengono aggiornati ogni 3 sottotitoli generati
- I file temporanei vengono puliti automaticamente alla chiusura della sessione
- Per migliori performance, usa modelli più piccoli (tiny/base) per stream live

---

---

## FFmpeg Whisper (FFmpeg 8.0+)

**Nuovo!** Script che utilizza il filtro Whisper integrato in FFmpeg 8.0, come descritto in [Phoronix](https://www.phoronix.com/news/FFmpeg-Lands-Whisper).

### Requisiti FFmpeg Whisper

- **FFmpeg 8.0+** compilato con `--enable-whisper`
- **Whisper.cpp** installato sul sistema
- **Python 3.8+** (solo per lo script wrapper)

### Installazione FFmpeg con supporto Whisper

```bash
# Installa Whisper.cpp
# macOS:
brew install whisper.cpp

# Linux (Ubuntu/Debian):
# Compila da sorgente: https://github.com/ggerganov/whisper.cpp

# Compila FFmpeg 8.0+ con supporto Whisper
git clone https://git.ffmpeg.org/ffmpeg.git
cd ffmpeg
./configure --enable-whisper
make && sudo make install
```

### Utilizzo FFmpeg Whisper

```bash
# Verifica supporto Whisper
./ffmpeg_whisper.sh --check

# Trascrivi un video (genera file.srt)
./ffmpeg_whisper.sh video.mp4

# Trascrivi con modello specifico e lingua
./ffmpeg_whisper.sh audio.mp3 --model small --language en

# Output in formato JSON
./ffmpeg_whisper.sh video.mp4 --format json --output transcript.json

# Usa accelerazione GPU (se disponibile)
./ffmpeg_whisper.sh video.mp4 --gpu --model large

# Invia output JSON a endpoint HTTP
./ffmpeg_whisper.sh audio.mp3 --format json --http-endpoint "http://localhost:8080/api/transcribe"

# Limita durata per stream live
./ffmpeg_whisper.sh "https://example.com/stream.m3u8" --duration 300

# Stream LIVE in tempo reale (processa chunk per chunk)
./ffmpeg_whisper.sh "https://example.com/live.m3u8" --live

# Stream LIVE con chunk personalizzati (5 secondi per chunk)
./ffmpeg_whisper.sh "https://example.com/live.m3u8" --live --chunk-duration 5

# Stream LIVE con durata massima
./ffmpeg_whisper.sh "https://example.com/live.m3u8" --live --duration 600
```

### Opzioni FFmpeg Whisper

```bash
python ffmpeg_whisper.py [INPUT] [OPZIONI]

Opzioni:
  --model {tiny,base,small,medium,large}
                        Modello Whisper (default: base)
  --language LANGUAGE   Codice lingua ISO 639-1 (default: it)
  --output, -o FILE     File di output (default: input.srt/json/txt)
  --format {srt,json,txt}
                        Formato di output (default: srt)
  --gpu                 Usa accelerazione GPU se disponibile
  --http-endpoint URL   URL HTTP per inviare output JSON
  --duration SECONDI    Durata massima in secondi
  --live                Modalità LIVE: processa stream in tempo reale (solo URL)
  --chunk-duration SEC  Durata chunk per modalità live (default: 10 secondi)
  --check               Verifica solo se FFmpeg supporta Whisper
```

**Nota**: Se FFmpeg non ha il supporto Whisper, lo script ti indicherà come abilitarlo. Puoi comunque usare `vlc_speech2text.py` che funziona con qualsiasi versione di FFmpeg.

---

## VLC Speech-to-Text (Python Whisper)

## Requisiti

- **VLC Media Player** installato e disponibile nel PATH
- **Python 3.8+**
- **FFmpeg** (richiesto da Whisper e pydub)

### Installazione dipendenze

```bash
# Installa VLC (se non già installato)
# macOS:
brew install --cask vlc

# Linux (Ubuntu/Debian):
sudo apt-get install vlc

# Installa FFmpeg
# macOS:
brew install ffmpeg

# Linux:
sudo apt-get install ffmpeg

# Installa dipendenze Python (crea ambiente virtuale)
python3 -m venv venv
source venv/bin/activate  # Su Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Utilizzo

### Metodo 1: Script wrapper (consigliato)

```bash
./vlc_stt.sh video.mp4
```

### Metodo 2: Attivazione manuale ambiente virtuale

```bash
source venv/bin/activate  # Su Windows: venv\Scripts\activate
python vlc_speech2text.py video.mp4
```

### Opzioni disponibili

```bash
python vlc_speech2text.py [INPUT] [OPZIONI]

Opzioni:
  --model {tiny,base,small,medium,large}
                        Dimensione modello Whisper (default: base)
  --language LANGUAGE   Codice lingua ISO 639-1 (default: it)
  --realtime            Processa in tempo reale
  --format {wav,mp3,flac}
                        Formato audio di output (default: wav)
  --duration SECONDI    Durata massima in secondi (utile per stream live)
  --use-ffmpeg          Usa FFmpeg invece di VLC per estrarre l'audio
  --live                Modalità LIVE: processa stream in tempo reale (solo URL)
  --chunk-duration SEC   Durata chunk per modalità live (default: 10 secondi)
  --subtitles           Avvia ffplay (FFmpeg) con riproduzione video e sottotitoli burn-in
```

### Esempi

```bash
# Trascrivi un video in italiano
./vlc_stt.sh video.mp4

# Trascrivi un audio online in inglese con modello più grande
./vlc_stt.sh "https://example.com/audio.mp3" --model small --language en

# Trascrivi uno stream HLS (limita a 5 minuti per stream live infiniti)
./vlc_stt.sh "https://example.com/stream.m3u8" --duration 300

# Trascrivi uno stream HLS con modello veloce
./vlc_stt.sh "https://example.com/live.m3u8" --model tiny --duration 60

# Usa FFmpeg invece di VLC (più affidabile per alcuni stream)
./vlc_stt.sh "https://example.com/stream.m3u8" --use-ffmpeg --duration 300

# Stream LIVE in tempo reale (processa chunk per chunk)
./vlc_stt.sh "https://example.com/live.m3u8" --live

# Stream LIVE con chunk personalizzati (5 secondi per chunk)
./vlc_stt.sh "https://example.com/live.m3u8" --live --chunk-duration 5

# Avvia ffplay con video e sottotitoli burn-in in tempo reale
./vlc_stt.sh video.mp4 --subtitles

# Stream con sottotitoli burn-in
./vlc_stt.sh "https://example.com/stream.m3u8" --subtitles

# Processa in tempo reale (mostra output durante riproduzione)
./vlc_stt.sh video.mkv --realtime

# Usa modello più veloce (tiny) per test rapidi
./vlc_stt.sh audio.mp3 --model tiny
```

**Nota**: Se usi il metodo 2 (attivazione manuale), sostituisci `./vlc_stt.sh` con `python vlc_speech2text.py` negli esempi sopra.

## Come funziona

1. Lo script lancia VLC in modalità headless (senza GUI)
2. VLC estrae l'audio dal file/URL specificato e lo salva in un file temporaneo
3. Per stream HLS/HTTP, VLC usa opzioni ottimizzate (cache, riconnessione automatica)
4. Whisper processa l'audio e genera la trascrizione
5. Il testo viene mostrato nell'output

## Supporto Stream

Lo script supporta:
- **File locali**: video/audio (mp4, mkv, avi, mp3, etc.)
- **URL HTTP/HTTPS**: stream audio/video online
- **HLS streams**: URL `.m3u8` e stream HLS (con riconnessione automatica)
- **Stream live**: usa `--duration` per limitare la durata di stream infiniti

## Modelli Whisper

- **tiny**: Più veloce, meno accurato (~39M parametri)
- **base**: Bilanciato tra velocità e accuratezza (~74M parametri) - **default**
- **small**: Più accurato, più lento (~244M parametri)
- **medium**: Molto accurato, lento (~769M parametri)
- **large**: Massima accuratezza, molto lento (~1550M parametri)

## Note

- Il primo utilizzo scaricherà automaticamente il modello Whisper selezionato
- I modelli più grandi richiedono più memoria e tempo di elaborazione
- Per file molto lunghi, considera l'uso di `--realtime` per vedere l'output progressivamente

## Troubleshooting

### VLC non trovato
Assicurati che VLC sia installato e disponibile nel PATH. Puoi verificare con:
```bash
vlc --version
```

### Errore FFmpeg
Installa FFmpeg come indicato nella sezione Requisiti.

### Memoria insufficiente
Usa un modello più piccolo (es. `--model tiny` o `--model base`).

### File audio vuoto o corrotto
Se VLC non riesce a creare il file audio:
- Prova con `--use-ffmpeg` per usare FFmpeg invece di VLC
- Lo script tenta automaticamente FFmpeg se VLC fallisce
- Verifica che lo stream/URL sia accessibile

### Ambiente virtuale
Se hai problemi con le dipendenze, assicurati di aver attivato l'ambiente virtuale:
```bash
source venv/bin/activate
```

## Confronto tra gli approcci

| Caratteristica | `vlc_speech2text.py` | `ffmpeg_whisper.py` |
|---------------|---------------------|---------------------|
| Requisiti FFmpeg | Qualsiasi versione | FFmpeg 8.0+ con `--enable-whisper` |
| Dipendenze Python | Sì (Whisper, PyTorch) | No (solo wrapper) |
| Accelerazione GPU | Sì (via PyTorch) | Sì (via Whisper.cpp) |
| Output formati | Testo, SRT (via Python) | SRT, JSON, HTTP |
| Performance | Buona | Potenzialmente migliore |
| Facilità installazione | Facile | Richiede compilazione FFmpeg |

**Raccomandazione**: 
- Usa `vlc_speech2text.py` se vuoi una soluzione pronta all'uso
- Usa `ffmpeg_whisper.py` se hai FFmpeg 8.0+ con Whisper e vuoi performance ottimali

