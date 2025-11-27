#!/usr/bin/env python3
"""
Server web semplificato per trascrizione video con sottotitoli burn-in.
Usa il filtro Whisper nativo di FFmpeg quando disponibile.
"""

import os
import sys
import subprocess
import tempfile
import threading
import time
import json
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_cors import CORS

# Cerca FFmpeg compilato con Whisper
FFMPEG_PATH = None
# Supporta sia macOS che Linux
if os.path.exists("/Users/ube/ffmpeg_build/ffmpeg"):
    FFMPEG_BUILD_DIR = "/Users/ube/ffmpeg_build/ffmpeg"  # macOS
else:
    FFMPEG_BUILD_DIR = "/opt/ffmpeg_build/ffmpeg"  # Linux
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_WRAPPER = os.path.join(SCRIPT_DIR, "ffmpeg_whisper_wrapper.sh")

print(f"\n=== Ricerca FFmpeg con Whisper ===")
print(f"Wrapper path: {FFMPEG_WRAPPER}")
print(f"Wrapper esiste: {os.path.exists(FFMPEG_WRAPPER)}")
print(f"FFmpeg build esiste: {os.path.exists(os.path.join(FFMPEG_BUILD_DIR, 'ffmpeg'))}")

# Prima prova con wrapper script per FFmpeg compilato
if os.path.exists(FFMPEG_WRAPPER) and os.path.exists(os.path.join(FFMPEG_BUILD_DIR, "ffmpeg")):
    try:
        print(f"Provo wrapper: {FFMPEG_WRAPPER}")
        result = subprocess.run(
            [FFMPEG_WRAPPER, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3
        )
        if result.returncode == 0:
            filters_result = subprocess.run(
                [FFMPEG_WRAPPER, "-filters"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=3
            )
            output = (filters_result.stdout + filters_result.stderr).decode('utf-8', errors='ignore')
            if "whisper" in output.lower():
                FFMPEG_PATH = FFMPEG_WRAPPER
                print(f"✓ FFmpeg con Whisper trovato (via wrapper): {FFMPEG_WRAPPER}")
            else:
                print(f"✗ Wrapper funziona ma Whisper non trovato")
        else:
            print(f"✗ Wrapper non funziona (exit code {result.returncode})")
    except Exception as e:
        print(f"Errore verifica FFmpeg wrapper: {e}")
        import traceback
        traceback.print_exc()

# Se non trovato, prova /usr/local/bin/ffmpeg (dopo installazione)
if not FFMPEG_PATH and os.path.exists("/usr/local/bin/ffmpeg"):
    try:
        result = subprocess.run(
            ["/usr/local/bin/ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=2
        )
        if result.returncode == 0:
            filters_result = subprocess.run(
                ["/usr/local/bin/ffmpeg", "-filters"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=2
            )
            output = (filters_result.stdout + filters_result.stderr).decode('utf-8', errors='ignore')
            if "whisper" in output.lower():
                FFMPEG_PATH = "/usr/local/bin/ffmpeg"
                print(f"✓ FFmpeg con Whisper trovato: {FFMPEG_PATH}")
    except:
        pass

# Fallback: FFmpeg nel PATH (Homebrew, senza Whisper, o Railway/system)
if not FFMPEG_PATH:
    FFMPEG_PATH = "ffmpeg"
    print("⚠ FFmpeg con Whisper non trovato")
    print("  Su Railway/cloud, FFmpeg potrebbe non avere il filtro Whisper nativo")
    print("  L'app userà Python Whisper come fallback se disponibile")

# Configura Flask
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app = Flask(__name__, template_folder=template_dir)
CORS(app)

# Stato globale
sessions = {}
session_counter = 0
TEMP_DIR = tempfile.gettempdir()

def check_ffmpeg_whisper():
    """Verifica se FFmpeg ha il filtro Whisper."""
    try:
        result = subprocess.run(
            [FFMPEG_PATH, "-filters"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )
        output = (result.stdout + result.stderr).decode('utf-8', errors='ignore')
        has_whisper = "whisper" in output.lower()
        if has_whisper:
            version_result = subprocess.run(
                [FFMPEG_PATH, "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=2
            )
            version = version_result.stdout.decode('utf-8', errors='ignore').split('\n')[0]
            print(f"✓ Filtro Whisper verificato in {FFMPEG_PATH}")
            print(f"  Versione: {version}")
        return has_whisper
    except Exception as e:
        print(f"Errore verifica Whisper: {e}")
        return False


# Verifica subito quale FFmpeg viene usato
print(f"\n=== Verifica FFmpeg ===")
print(f"FFMPEG_PATH selezionato: {FFMPEG_PATH}")
HAS_WHISPER_FILTER = check_ffmpeg_whisper()
if HAS_WHISPER_FILTER:
    print("✓ Filtro Whisper nativo disponibile in FFmpeg")
else:
    print("⚠ Filtro Whisper nativo NON disponibile - installa FFmpeg 8.0+ con --enable-whisper")


class SimpleVideoSession:
    """Sessione semplificata per trascrizione video."""
    
    def __init__(self, session_id, video_url, language="en", model="base", translate_to=None):
        self.session_id = session_id
        self.video_url = video_url
        self.language = language if language != "auto" else None
        self.model = model
        self.translate_to = translate_to  # Lingua di traduzione (es. 'it' per italiano)
        print(f"[Session {self.session_id}] Inizializzata con translate_to={self.translate_to}")
        
        # File SRT temporaneo
        self.srt_path = os.path.join(TEMP_DIR, f"subs_{session_id}.srt")
        
        # Processo FFmpeg
        self.ffmpeg_process = None
        self.running = False
        self.status = "initializing"
        self.error = None
        
        # Sottotitoli
        self.all_subtitles = []
        self.translated_subtitles = []  # Sottotitoli tradotti
        
        # Crea SRT iniziale
        with open(self.srt_path, 'w', encoding='utf-8') as f:
            f.write("1\n00:00:00,000 --> 00:00:01,000\nCaricamento...\n\n")
    
    def start(self):
        """Avvia FFmpeg con filtro Whisper per trascrizione + burn-in + streaming."""
        try:
            self.status = "starting"
            self.running = True
            
            abs_srt_path = os.path.abspath(self.srt_path)
            # Per il filtro Whisper, usa il percorso diretto
            # Per il filtro subtitles, escape solo i due punti (necessario su macOS/Windows)
            escaped_srt_subtitles = abs_srt_path.replace(":", "\\:")
            
            # Costruisci filtro Whisper
            # NOTA: Il filtro Whisper richiede il percorso completo al file modello
            # I modelli sono tipicamente in ~/.cache/whisper/ o scaricati automaticamente
            # Per ora, usiamo il nome del modello e FFmpeg lo cercherà automaticamente
            # Se non funziona, dobbiamo specificare il percorso completo
            
            # Cerca il modello Whisper (whisper.cpp usa .bin, non .pt)
            # I modelli sono in formato ggml-{model}.bin o {model}.bin
            model_path = None
            model_name = self.model
            possible_paths = [
                # Prova prima il formato semplice (base.bin)
                os.path.expanduser(f"~/.cache/whisper/{model_name}.bin"),
                # Poi il formato ggml- (ggml-base.bin)
                os.path.expanduser(f"~/.cache/whisper/ggml-{model_name}.bin"),
                os.path.expanduser(f"~/.cache/whisper/{model_name}.ggml"),
                os.path.expanduser(f"~/.local/share/whisper/{model_name}.bin"),
                f"/opt/homebrew/opt/whisper-cpp/share/whisper-cpp/{model_name}.bin",
                f"/opt/homebrew/opt/whisper-cpp/share/whisper-cpp/ggml-{model_name}.bin",
                # Modello di test (se disponibile)
                f"/opt/homebrew/opt/whisper-cpp/share/whisper-cpp/for-tests-ggml-tiny.bin" if model_name == "tiny" else None,
            ]
            
            for path in possible_paths:
                if path and os.path.exists(path):
                    model_path = path
                    print(f"[Session {self.session_id}] ✓ Modello trovato: {model_path}")
                    break
            
            # Se non trovato, mostra messaggio di errore chiaro
            if not model_path:
                error_msg = f"Modello Whisper '{model_name}' non trovato!\n"
                error_msg += f"Scarica i modelli whisper.cpp eseguendo:\n"
                error_msg += f"  cd /Users/ube/vls-speech2text && ./download_whisper_models.sh\n"
                error_msg += f"Oppure manualmente da:\n"
                error_msg += f"  https://huggingface.co/ggerganov/whisper.cpp/tree/main"
                print(f"[Session {self.session_id}] ❌ {error_msg}")
                self.error = error_msg
                self.status = "error"
                raise Exception(f"Modello Whisper '{model_name}' non trovato. Esegui ./download_whisper_models.sh per scaricare i modelli.")
            
            whisper_filter = f"whisper=model={model_path}"
            if self.language:
                whisper_filter += f":language={self.language}"
            # Usa 'destination' per il percorso file e 'format=srt' per il formato SRT
            whisper_filter += f":destination={abs_srt_path}:format=srt"
            
            # Comando FFmpeg semplificato:
            # - Legge video
            # - Trascrive con Whisper (genera SRT)
            # - Applica sottotitoli burn-in
            # - Streama via HTTP
            # NOTA: Non possiamo usare -c:a copy con un filtro audio, dobbiamo usare un codec
            ffmpeg_cmd = [
                FFMPEG_PATH,
                "-i", self.video_url,
                "-af", whisper_filter,  # Trascrizione Whisper
                # NOTA: Il filtro subtitles non è disponibile in questa versione di FFmpeg
                # Per ora, non applichiamo burn-in (i sottotitoli saranno disponibili come file SRT separato)
                # TODO: Convertire SRT in ASS e usare filtro ass, oppure usare drawtext
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-g", "30",  # GOP size per frammentazione
                "-sc_threshold", "0",  # Disabilita scene change detection
                "-c:a", "aac",  # Deve essere aac, non copy (il filtro richiede ri-encoding)
                "-b:a", "128k",
                "-ac", "2",  # Forza stereo (2 canali) per compatibilità AAC
                "-ar", "44100",  # Sample rate standard
                # Usa MP4 fragmentato per migliore compatibilità browser
                "-f", "mp4",
                "-movflags", "frag_keyframe+empty_moov+default_base_moof",
                "-frag_duration", "1000000",  # 1 secondo per frammento
                "-"  # stdout per streaming HTTP
            ]
            
            print(f"[Session {self.session_id}] Avvio FFmpeg con Whisper...")
            print(f"Comando completo: {' '.join(ffmpeg_cmd)}")
            
            self.ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0
            )
            
            # Thread per log stderr (per debug) - log TUTTO
            def log_stderr():
                try:
                    for line in iter(self.ffmpeg_process.stderr.readline, b''):
                        if line:
                            decoded = line.decode('utf-8', errors='ignore').strip()
                            # Log tutto per debug
                            print(f"[FFmpeg {self.session_id}] {decoded}")
                except Exception as e:
                    print(f"[FFmpeg {self.session_id}] Errore log stderr: {e}")
            
            stderr_thread = threading.Thread(target=log_stderr, daemon=True)
            stderr_thread.start()
            
            # Aspetta un po' per vedere se FFmpeg si avvia correttamente
            print(f"[Session {self.session_id}] Attendo 3 secondi per verifica avvio FFmpeg...")
            time.sleep(3)
            exit_code = self.ffmpeg_process.poll()
            if exit_code is not None:
                # FFmpeg è terminato subito, c'è un errore
                print(f"[Session {self.session_id}] FFmpeg terminato con exit code: {exit_code}")
                
                # Prova a leggere tutto lo stderr disponibile
                stderr_output = ""
                try:
                    # Leggi tutto quello che c'è nello stderr
                    import select
                    import fcntl
                    
                    # Imposta stderr come non bloccante
                    if sys.platform != 'win32':
                        flags = fcntl.fcntl(self.ffmpeg_process.stderr, fcntl.F_GETFL)
                        fcntl.fcntl(self.ffmpeg_process.stderr, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                    
                    # Leggi tutto lo stderr disponibile
                    chunks = []
                    while True:
                        try:
                            chunk = self.ffmpeg_process.stderr.read(4096)
                            if not chunk:
                                break
                            chunks.append(chunk)
                        except:
                            break
                    
                    if chunks:
                        stderr_output = b''.join(chunks).decode('utf-8', errors='ignore')
                    else:
                        stderr_output = "Nessun output stderr disponibile (processo terminato prima di generare output)"
                        
                except Exception as e:
                    stderr_output = f"Errore lettura stderr: {e}"
                    import traceback
                    traceback.print_exc()
                
                # Mostra le ultime righe dello stderr (dove di solito c'è l'errore)
                stderr_lines = stderr_output.split('\n')
                last_lines = '\n'.join(stderr_lines[-30:]) if len(stderr_lines) > 30 else stderr_output
                
                error_msg = f"FFmpeg terminato (exit code: {exit_code}):\n{last_lines[:2000]}"
                print(f"[Session {self.session_id}] ERRORE: {error_msg}")
                print(f"[Session {self.session_id}] Comando eseguito: {' '.join(ffmpeg_cmd)}")
                self.error = error_msg
                self.status = "error"
                raise Exception(error_msg)
            
            print(f"[Session {self.session_id}] FFmpeg avviato correttamente (PID: {self.ffmpeg_process.pid})")
            
            # Thread per monitorare SRT
            monitor_thread = threading.Thread(target=self._monitor_srt, daemon=True)
            monitor_thread.start()
            
            self.status = "running"
            return True
            
        except Exception as e:
            self.status = "error"
            self.error = str(e)
            print(f"Errore avvio sessione: {e}")
            return False
    
    def _monitor_srt(self):
        """Monitora il file SRT generato da Whisper."""
        import re
        last_size = 0
        check_count = 0
        
        print(f"[Session {self.session_id}] Avvio monitoraggio SRT: {self.srt_path}")
        
        while self.running:
            try:
                check_count += 1
                if os.path.exists(self.srt_path):
                    size = os.path.getsize(self.srt_path)
                    if size != last_size:
                        print(f"[Session {self.session_id}] File SRT modificato: {size} bytes (era {last_size})")
                        try:
                            with open(self.srt_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                            
                            if content.strip():
                                # Parse SRT - pattern migliorato per gestire formati diversi
                                # Supporta sia formato con virgola che con punto nei timestamp
                                pattern = r'(\d+)\s+(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s+-->\s+(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s+(.+?)(?=\n\d+\s+\d{2}:|\Z)'
                                matches = re.findall(pattern, content, re.DOTALL)
                                
                                # Se non trova match, prova pattern alternativo (senza virgola/punto)
                                if not matches:
                                    pattern2 = r'(\d+)\s+(\d{2}):(\d{2}):(\d{2}),(\d{3})\s+-->\s+(\d{2}):(\d{2}):(\d{2}),(\d{3})\s+(.+?)(?=\n\n|\Z)'
                                    matches = re.findall(pattern2, content, re.DOTALL)
                                
                                print(f"[Session {self.session_id}] Pattern trovati {len(matches)} match in SRT (dimensione: {len(content)} chars)")
                                
                                self.all_subtitles = []
                                for m in matches:
                                    idx = int(m[0])
                                    start = int(m[1])*3600 + int(m[2])*60 + int(m[3]) + int(m[4])/1000.0
                                    end = int(m[5])*3600 + int(m[6])*60 + int(m[7]) + int(m[8])/1000.0
                                    text = m[9].strip()
                                    
                                    self.all_subtitles.append({
                                        'index': idx,
                                        'start': start,
                                        'end': end,
                                        'text': text
                                    })
                                
                                if self.all_subtitles:
                                    print(f"[Session {self.session_id}] Trovati {len(self.all_subtitles)} sottotitoli nel file SRT")
                                    
                                    # Traduci i sottotitoli se richiesto
                                    print(f"[Session {self.session_id}] 🔍 Controllo traduzione: translate_to={self.translate_to}, all_subtitles={len(self.all_subtitles)}")
                                    if self.translate_to and self.translate_to != 'none':
                                        print(f"[Session {self.session_id}] ✅ Chiamata traduzione...")
                                        self._translate_subtitles()
                                    else:
                                        print(f"[Session {self.session_id}] ⚠️ Traduzione non richiesta (translate_to={self.translate_to})")
                        except Exception as e:
                            print(f"[Session {self.session_id}] Errore lettura/parsing SRT: {e}")
                        
                        last_size = size
                else:
                    if check_count % 10 == 0:  # Log ogni 10 controlli
                        print(f"[Session {self.session_id}] File SRT non ancora creato: {self.srt_path}")
                
                time.sleep(1)
            except Exception as e:
                print(f"[Session {self.session_id}] Errore monitoraggio SRT: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(2)
    
    def _translate_subtitles(self):
        """Traduce i sottotitoli nella lingua specificata."""
        print(f"[Session {self.session_id}] 🔍 _translate_subtitles chiamato: translate_to={self.translate_to}, all_subtitles={len(self.all_subtitles)}, translated={len(self.translated_subtitles)}")
        
        if not self.translate_to or self.translate_to == 'none':
            print(f"[Session {self.session_id}] ⚠️ Traduzione disabilitata (translate_to={self.translate_to})")
            return
        
        try:
            # Prova prima googletrans, poi fallback a deep-translator se non funziona
            translator = None
            translator_type = None
            try:
                from googletrans import Translator
                translator = Translator()
                translator_type = 'googletrans'
                print(f"[Session {self.session_id}] ✅ Usando googletrans per traduzione")
            except (ImportError, ModuleNotFoundError, AttributeError) as e:
                print(f"[Session {self.session_id}] ⚠️ googletrans non disponibile ({type(e).__name__}: {e}), provo deep-translator...")
                try:
                    from deep_translator import GoogleTranslator
                    translator = GoogleTranslator(source='auto', target=self.translate_to)
                    translator_type = 'deep-translator'
                    print(f"[Session {self.session_id}] ✅ Usando deep-translator per traduzione")
                except ImportError:
                    print(f"[Session {self.session_id}] ❌ Né googletrans né deep-translator disponibili")
                    raise ImportError("Nessun traduttore disponibile")
            
            # Traduci solo i nuovi sottotitoli (quelli non ancora tradotti)
            new_subtitles = self.all_subtitles[len(self.translated_subtitles):]
            
            if not new_subtitles:
                print(f"[Session {self.session_id}] Nessun nuovo sottotitolo da tradurre (tutti già tradotti: {len(self.translated_subtitles)}/{len(self.all_subtitles)})")
                return
            
            print(f"[Session {self.session_id}] 🔄 Traduzione di {len(new_subtitles)} sottotitoli in {self.translate_to}...")
            print(f"[Session {self.session_id}] Esempio primo sottotitolo da tradurre: '{new_subtitles[0]['text'][:50]}...'")
            
            for subtitle in new_subtitles:
                try:
                    # Traduci il testo
                    print(f"[Session {self.session_id}] Traduco: '{subtitle['text'][:50]}...' -> {self.translate_to} (tipo: {translator_type})")
                    
                    if translator_type == 'googletrans':
                        translated = translator.translate(subtitle['text'], dest=self.translate_to)
                        translated_text = translated.text if hasattr(translated, 'text') else str(translated)
                    else:  # deep-translator
                        translated_text = translator.translate(subtitle['text'])
                    
                    print(f"[Session {self.session_id}] ✅ Risultato: '{translated_text[:50]}...'")
                    
                    translated_subtitle = {
                        'index': subtitle['index'],
                        'start': subtitle['start'],
                        'end': subtitle['end'],
                        'text': translated_text
                    }
                    self.translated_subtitles.append(translated_subtitle)
                    
                    if len(self.translated_subtitles) <= 5:  # Log i primi 5
                        print(f"[Session {self.session_id}] 📝 Tradotto #{subtitle['index']}: '{subtitle['text'][:40]}...' -> '{translated_text[:40]}...'")
                except Exception as e:
                    print(f"[Session {self.session_id}] ❌ Errore traduzione sottotitolo {subtitle['index']}: {e}")
                    import traceback
                    traceback.print_exc()
                    # In caso di errore, usa il testo originale
                    self.translated_subtitles.append(subtitle)
            
            print(f"[Session {self.session_id}] ✅ Traduzione completata: {len(self.translated_subtitles)}/{len(self.all_subtitles)} sottotitoli tradotti")
            
        except ImportError:
            print(f"[Session {self.session_id}] ⚠️ googletrans non installato. Installa con: pip install googletrans==4.0.0rc1")
        except Exception as e:
            print(f"[Session {self.session_id}] ❌ Errore durante la traduzione: {e}")
            import traceback
            traceback.print_exc()
    
    def stop(self):
        """Ferma la sessione."""
        self.running = False
        if self.ffmpeg_process:
            try:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait(timeout=5)
            except:
                try:
                    self.ffmpeg_process.kill()
                except:
                    pass
    
    def cleanup(self):
        """Pulisce risorse."""
        self.stop()
        try:
            if os.path.exists(self.srt_path):
                os.unlink(self.srt_path)
        except:
            pass


@app.route('/')
def index():
    """Pagina principale."""
    try:
        return render_template('index_simple.html')
    except:
        # Fallback se template non esiste
        return """
        <!DOCTYPE html>
        <html>
        <head><title>Trascrizione Video</title></head>
        <body>
            <h1>Trascrizione Video con Sottotitoli</h1>
            <p>Inserisci URL video e riproduci con sottotitoli burn-in</p>
            <form id="form">
                <input type="text" id="videoUrl" placeholder="URL video" style="width:400px;padding:10px;">
                <select id="language" style="padding:10px;">
                    <option value="en">Inglese</option>
                    <option value="it">Italiano</option>
                    <option value="auto">Auto</option>
                </select>
                <button type="submit" style="padding:10px;">Riproduci</button>
            </form>
            <div id="status"></div>
            <video id="video" controls style="width:100%;margin-top:20px;"></video>
            <script>
                document.getElementById('form').onsubmit = async (e) => {
                    e.preventDefault();
                    const url = document.getElementById('videoUrl').value;
                    const lang = document.getElementById('language').value;
                    const res = await fetch('/api/start', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({video_url: url, language: lang, model_size: 'base'})
                    });
                    const data = await res.json();
                    if (res.ok) {
                        document.getElementById('video').src = data.stream_url;
                        document.getElementById('status').textContent = 'Streaming avviato';
                    }
                };
            </script>
        </body>
        </html>
        """


@app.route('/api/start', methods=['POST'])
def start_session():
    """Avvia una nuova sessione."""
    global session_counter
    
    if not HAS_WHISPER_FILTER:
        return jsonify({
            'error': 'Filtro Whisper non disponibile. Installa FFmpeg 8.0+ con --enable-whisper'
        }), 400
    
    data = request.json
    video_url = data.get('video_url', '').strip()
    language = data.get('language', 'en')
    model = data.get('model_size', 'base')
    translate_to = data.get('translate_to', None)  # 'it' per italiano, 'none' per disabilitare
    
    if not video_url:
        return jsonify({'error': 'URL video richiesto'}), 400
    
    print(f"[Start] Nuova sessione: video_url={video_url}, language={language}, model={model}, translate_to={translate_to}")
    
    session_counter += 1
    session_id = f"session_{session_counter}"
    
    print(f"[Start] Creazione sessione {session_id}...")
    session = SimpleVideoSession(session_id, video_url, language, model, translate_to=translate_to)
    sessions[session_id] = session
    print(f"[Start] Sessione {session_id} creata e aggiunta a sessions (totale: {len(sessions)})")
    
    # Avvia in thread
    def start():
        session.start()
    
    thread = threading.Thread(target=start, daemon=True)
    thread.start()
    
    print(f"[Start] Thread avviato per sessione {session_id}")
    
    return jsonify({
        'session_id': session_id,
        'stream_url': f'/api/stream/{session_id}',
        'subtitles_url': f'/api/subtitles/{session_id}',
        'status': 'starting'
    })


@app.route('/api/stream/<session_id>')
def stream_video(session_id):
    """Stream del video con sottotitoli."""
    print(f"[Stream] Richiesta stream per sessione {session_id}")
    print(f"[Stream] Sessioni disponibili: {list(sessions.keys())}")
    
    if session_id not in sessions:
        print(f"[Stream] ❌ Sessione {session_id} non trovata in sessions (disponibili: {list(sessions.keys())})")
        return "Sessione non trovata", 404
    
    session = sessions[session_id]
    
    if not session.ffmpeg_process:
        print(f"[Stream] FFmpeg process non esiste per sessione {session_id}")
        return "Stream non disponibile - processo non avviato", 404
    
    poll_result = session.ffmpeg_process.poll()
    if poll_result is not None:
        print(f"[Stream] FFmpeg process terminato (exit code: {poll_result})")
        stderr_output = session.ffmpeg_process.stderr.read().decode('utf-8', errors='ignore') if session.ffmpeg_process.stderr else "N/A"
        print(f"[Stream] Stderr: {stderr_output[:500]}")
        return f"Stream non disponibile - processo terminato (exit: {poll_result})", 404
    
    print(f"[Stream] Avvio streaming per sessione {session_id} (PID: {session.ffmpeg_process.pid})")
    
    def generate():
        """Genera stream da FFmpeg stdout."""
        bytes_sent = 0
        try:
            while session.running and session.ffmpeg_process.poll() is None:
                chunk = session.ffmpeg_process.stdout.read(1024 * 64)  # 64KB chunks
                if chunk:
                    bytes_sent += len(chunk)
                    if bytes_sent == len(chunk):
                        print(f"[Stream {session_id}] Primo chunk inviato ({len(chunk)} bytes)")
                    yield chunk
                else:
                    # Se non ci sono dati, aspetta
                    time.sleep(0.1)
                    # Se non abbiamo ancora inviato nulla dopo 2 secondi, potrebbe esserci un problema
                    if bytes_sent == 0:
                        time.sleep(0.5)
        except Exception as e:
            print(f"[Stream {session_id}] Errore streaming: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print(f"[Stream {session_id}] Streaming terminato (totale: {bytes_sent} bytes)")
    
    return Response(
        stream_with_context(generate()),
        mimetype='video/mp4',  # MP4 fragmentato MIME type
        headers={
            'Content-Type': 'video/mp4',
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Accept-Ranges': 'bytes'
        }
    )


@app.route('/api/subtitles/<session_id>')
def get_subtitles(session_id):
    """Restituisce il file SRT dei sottotitoli."""
    print(f"[Subtitles] Richiesta sottotitoli per sessione {session_id}")
    
    if session_id not in sessions:
        print(f"[Subtitles] Sessione {session_id} non trovata")
        return "Sessione non trovata", 404
    
    session = sessions[session_id]
    
    print(f"[Subtitles] Percorso SRT: {session.srt_path}")
    print(f"[Subtitles] File esiste: {os.path.exists(session.srt_path)}")
    
    if not os.path.exists(session.srt_path):
        # Restituisci file SRT vuoto se non esiste ancora
        print(f"[Subtitles] File SRT non esiste, restituisco placeholder")
        return Response(
            "1\n00:00:00,000 --> 00:00:01,000\nCaricamento sottotitoli...\n\n",
            mimetype='text/srt',
            headers={
                'Content-Type': 'text/srt; charset=utf-8',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Access-Control-Allow-Origin': '*'
            }
        )
    
    try:
        # Se ci sono sottotitoli tradotti, genera SRT da quelli, altrimenti usa il file
        has_translated = hasattr(session, 'translated_subtitles') and session.translated_subtitles
        translate_to = session.translate_to if hasattr(session, 'translate_to') else 'N/A'
        translated_count = len(session.translated_subtitles) if hasattr(session, 'translated_subtitles') else 0
        
        print(f"[Subtitles] 🔍 Controllo: translated_subtitles={translated_count}, translate_to={translate_to}, has_translated={has_translated}")
        
        if has_translated:
            print(f"[Subtitles] ✅ Genero SRT da {len(session.translated_subtitles)} sottotitoli tradotti in {translate_to}")
            print(f"[Subtitles] Esempio primo sottotitolo tradotto: '{session.translated_subtitles[0]['text'][:50]}...'")
            content = ""
            for sub in session.translated_subtitles:
                start_h = int(sub['start'] // 3600)
                start_m = int((sub['start'] % 3600) // 60)
                start_s = int(sub['start'] % 60)
                start_ms = int((sub['start'] % 1) * 1000)
                
                end_h = int(sub['end'] // 3600)
                end_m = int((sub['end'] % 3600) // 60)
                end_s = int(sub['end'] % 60)
                end_ms = int((sub['end'] % 1) * 1000)
                
                content += f"{sub['index']}\n"
                content += f"{start_h:02d}:{start_m:02d}:{start_s:02d},{start_ms:03d} --> {end_h:02d}:{end_m:02d}:{end_s:02d},{end_ms:03d}\n"
                content += f"{sub['text']}\n\n"
        else:
            # Usa il file SRT originale
            with open(session.srt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Converti timestamp da formato con punto a formato con virgola (standard SRT)
            # Whisper genera: 00:00:02.994 --> 00:00:05.574
            # SRT standard:   00:00:02,994 --> 00:00:05,574
            content = content.replace('.', ',')
        
        print(f"[Subtitles] File SRT letto: {len(content)} caratteri, {len(content.splitlines())} righe")
        
        return Response(
            content,
            mimetype='text/srt',
            headers={
                'Content-Type': 'text/srt; charset=utf-8',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Access-Control-Allow-Origin': '*'
            }
        )
    except Exception as e:
        print(f"[Subtitles] Errore lettura SRT: {e}")
        import traceback
        traceback.print_exc()
        return "Errore lettura sottotitoli", 500


@app.route('/api/status/<session_id>')
def get_status(session_id):
    """Stato della sessione."""
    if session_id not in sessions:
        return jsonify({'error': 'Sessione non trovata'}), 404
    
    session = sessions[session_id]
    
    # Restituisci i sottotitoli tradotti se disponibili, altrimenti quelli originali
    subtitles_to_return = session.translated_subtitles if session.translated_subtitles else session.all_subtitles
    
    print(f"[Status {session_id}] Sottotitoli: {len(session.all_subtitles)} originali, {len(session.translated_subtitles)} tradotti")
    print(f"[Status {session_id}] Restituisco {len(subtitles_to_return[-10:])} sottotitoli (tradotti: {len(session.translated_subtitles) > 0})")
    
    return jsonify({
        'status': session.status,
        'error': session.error,
        'subtitles_count': len(session.all_subtitles),
        'subtitles': subtitles_to_return[-10:] if subtitles_to_return else [],
        'translated': len(session.translated_subtitles) > 0
    })


@app.route('/api/stop/<session_id>', methods=['POST'])
def stop_session(session_id):
    """Ferma una sessione."""
    if session_id not in sessions:
        return jsonify({'error': 'Sessione non trovata'}), 404
    
    session = sessions[session_id]
    session.cleanup()
    del sessions[session_id]
    
    return jsonify({'status': 'stopped'})


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=5000)
    args = parser.parse_args()
    
    print(f"\n=== Server Web Semplificato ===")
    print(f"Filtro Whisper: {'✓ Disponibile' if HAS_WHISPER_FILTER else '✗ Non disponibile'}")
    print(f"Accessibile su: http://{args.host}:{args.port}")
    print()
    
    app.run(host=args.host, port=args.port, threaded=True)

