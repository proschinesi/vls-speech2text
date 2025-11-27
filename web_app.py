#!/usr/bin/env python3
"""
Server web per trascrizione video con sottotitoli burn-in.
Accessibile da remoto per inserire URL video e riprodurlo con sottotitoli.
"""

import os
import sys
import subprocess
import tempfile
import threading
import time
import json
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_cors import CORS

# Import fcntl solo su sistemi Unix (non Windows)
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

# Aggiungi il percorso dello script principale
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from vlc_speech2text import (
        VLCSpeechToText,
        format_srt_time,
        restart_ffmpeg_video_process,
        is_url
    )
except ImportError:
    print("Errore: Impossibile importare vlc_speech2text. Assicurati che il file esista.")
    sys.exit(1)

# Configura Flask per trovare i template nella directory corretta
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app = Flask(__name__, template_folder=template_dir)
CORS(app)  # Permette accesso da remoto

# Stato globale per le sessioni
sessions = {}
session_counter = 0

# Directory per file temporanei
TEMP_DIR = tempfile.gettempdir()


class VideoTranscriptionSession:
    """Gestisce una sessione di trascrizione video."""
    
    def __init__(self, session_id, video_url, language="en", model_size="base", chunk_duration=10):
        self.session_id = session_id
        self.video_url = video_url
        self.language = language
        self.model_size = model_size
        self.chunk_duration = chunk_duration
        
        # File temporanei
        self.srt_path = os.path.join(TEMP_DIR, f"subs_{session_id}.srt")
        self.video_pipe_path = os.path.join(TEMP_DIR, f"video_{session_id}.ts")
        
        # Processi
        self.ffmpeg_video_process = None
        self.ffmpeg_audio_process = None
        self.stt = None
        
        # Stato
        self.running = False
        self.all_subtitles = []
        self.subtitle_index = 1
        self.chunk_counter = 0
        self.status = "initializing"
        self.error = None
        
        # Crea file SRT iniziale
        self._init_srt_file()
    
    def _init_srt_file(self):
        """Inizializza il file SRT con contenuto minimo."""
        with open(self.srt_path, 'w', encoding='utf-8') as f:
            f.write("1\n")
            f.write("00:00:00,000 --> 00:00:01,000\n")
            f.write("Caricamento sottotitoli...\n")
            f.write("\n")
    
    def start(self):
        """Avvia la trascrizione e lo streaming."""
        try:
            self.status = "starting"
            
            # Carica modello Whisper
            self.stt = VLCSpeechToText(model_size=self.model_size, language=self.language)
            print(f"[Session {self.session_id}] Caricamento modello Whisper...")
            self.stt.load_model()
            
            # Per il web, usiamo una pipe e Flask servirà lo stream via HTTP
            # Crea named pipe per video
            import stat
            try:
                if os.path.exists(self.video_pipe_path):
                    os.unlink(self.video_pipe_path)
                
                # Su macOS, usa sempre file MP4 invece di pipe (più compatibile con browser)
                if sys.platform == 'darwin':
                    # Usa MP4 per migliore compatibilità browser
                    self.video_pipe_path = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
                    print(f"[Session {self.session_id}] Usando file MP4: {self.video_pipe_path}")
                else:
                    # Linux: prova con named pipe
                    try:
                        os.mkfifo(self.video_pipe_path, stat.S_IRUSR | stat.S_IWUSR)
                        print(f"[Session {self.session_id}] Named pipe creata: {self.video_pipe_path}")
                    except Exception as e:
                        print(f"[Session {self.session_id}] Errore creazione pipe, uso file MP4: {e}")
                        self.video_pipe_path = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
                        print(f"[Session {self.session_id}] Usando file MP4: {self.video_pipe_path}")
            except Exception as e:
                print(f"Errore creazione pipe: {e}")
                self.video_pipe_path = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
                print(f"[Session {self.session_id}] Usando file MP4: {self.video_pipe_path}")
            
            # Avvia FFmpeg per processare video con sottotitoli
            print(f"[Session {self.session_id}] Avvio FFmpeg per video con sottotitoli...")
            self.ffmpeg_video_process = restart_ffmpeg_video_process(
                self.video_url,
                self.srt_path,
                self.video_pipe_path,
                use_http=False
            )
            
            time.sleep(2)
            
            time.sleep(2)
            
            # Avvia thread per processare audio
            self.running = True
            self.status = "running"
            processing_thread = threading.Thread(target=self._process_audio, daemon=True)
            processing_thread.start()
            
            return True
            
        except Exception as e:
            self.status = "error"
            self.error = str(e)
            print(f"Errore avvio sessione: {e}")
            return False
    
    def _process_audio(self):
        """Processa l'audio in background e genera sottotitoli."""
        chunk_dir = tempfile.mkdtemp(prefix=f"whisper_{self.session_id}_")
        chunk_pattern = os.path.join(chunk_dir, "chunk_%04d.wav")
        processed_chunks = set()
        
        # Avvia FFmpeg per estrarre audio chunk
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", self.video_url,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            "-f", "segment",
            "-segment_time", str(self.chunk_duration),
            "-segment_format", "wav",
            "-reset_timestamps", "1",
            "-strftime", "0",
            "-y",
            chunk_pattern
        ]
        
        try:
            # Su macOS, usa start_new_session per isolare il processo
            if sys.platform == 'darwin':
                self.ffmpeg_audio_process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True
                )
            else:
                self.ffmpeg_audio_process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            
            while self.running and (self.ffmpeg_audio_process.poll() is None or 
                                   self.ffmpeg_video_process.poll() is None):
                # Cerca nuovi chunk
                for i in range(self.chunk_counter, self.chunk_counter + 10):
                    chunk_file = os.path.join(chunk_dir, f"chunk_{i:04d}.wav")
                    
                    if os.path.exists(chunk_file) and chunk_file not in processed_chunks:
                        processed_chunks.add(chunk_file)
                        time.sleep(0.5)
                        
                        if os.path.getsize(chunk_file) == 0:
                            continue
                        
                        # Calcola timestamp
                        chunk_start_time = (i * self.chunk_duration)
                        chunk_end_time = ((i + 1) * self.chunk_duration)
                        
                        try:
                            # Trascrivi chunk
                            result = self.stt.model.transcribe(
                                chunk_file,
                                language=self.language if self.language != "auto" else None,
                                task="transcribe",
                                fp16=False
                            )
                            
                            text = result["text"].strip()
                            if text:
                                # Aggiungi sottotitolo
                                subtitle = {
                                    'index': self.subtitle_index,
                                    'start': chunk_start_time,
                                    'end': chunk_end_time,
                                    'text': text
                                }
                                self.all_subtitles.append(subtitle)
                                
                                # Aggiorna file SRT
                                try:
                                    with open(self.srt_path, 'w', encoding='utf-8') as f:
                                        for sub in self.all_subtitles:
                                            f.write(f"{sub['index']}\n")
                                            f.write(f"{format_srt_time(sub['start'])} --> {format_srt_time(sub['end'])}\n")
                                            f.write(f"{sub['text']}\n\n")
                                    print(f"[Session {self.session_id}] SRT aggiornato con {len(self.all_subtitles)} sottotitoli")
                                except Exception as e:
                                    print(f"Errore scrittura SRT: {e}")
                                
                                # Riavvia FFmpeg ogni 3 sottotitoli per applicare i nuovi sottotitoli
                                # Questo è necessario perché FFmpeg non rilegge il file SRT quando viene aggiornato
                                if self.subtitle_index % 3 == 0:
                                    print(f"[Session {self.session_id}] Riavvio FFmpeg per applicare {len(self.all_subtitles)} sottotitoli")
                                    try:
                                        if self.ffmpeg_video_process:
                                            self.ffmpeg_video_process.terminate()
                                            try:
                                                self.ffmpeg_video_process.wait(timeout=3)
                                            except subprocess.TimeoutExpired:
                                                self.ffmpeg_video_process.kill()
                                                self.ffmpeg_video_process.wait()
                                    except Exception as e:
                                        print(f"Errore terminazione FFmpeg: {e}")
                                    
                                    # Attendi che il processo sia completamente terminato
                                    time.sleep(1)
                                    
                                    # Riavvia FFmpeg con il file SRT aggiornato
                                    # IMPORTANTE: Il file SRT deve essere completamente scritto prima di riavviare FFmpeg
                                    try:
                                        # Forza flush del file SRT
                                        import os
                                        os.sync()  # Sincronizza filesystem
                                        
                                        # Verifica che il file SRT sia stato scritto
                                        if os.path.exists(self.srt_path) and os.path.getsize(self.srt_path) > 0:
                                            print(f"[Session {self.session_id}] File SRT verificato: {os.path.getsize(self.srt_path)} bytes")
                                        
                                        self.ffmpeg_video_process = restart_ffmpeg_video_process(
                                            self.video_url,
                                            self.srt_path,
                                            self.video_pipe_path,
                                            use_http=False
                                        )
                                        print(f"[Session {self.session_id}] FFmpeg riavviato con SRT aggiornato ({len(self.all_subtitles)} sottotitoli)")
                                        time.sleep(3)  # Attendi più tempo che FFmpeg inizi a scrivere
                                    except Exception as e:
                                        print(f"Errore riavvio FFmpeg: {e}")
                                        import traceback
                                        traceback.print_exc()
                                
                                self.subtitle_index += 1
                            
                            os.unlink(chunk_file)
                            self.chunk_counter = i + 1
                            
                        except Exception as e:
                            print(f"Errore trascrizione chunk: {e}")
                            if os.path.exists(chunk_file):
                                try:
                                    os.unlink(chunk_file)
                                except:
                                    pass
                
                time.sleep(0.5)
                
        except Exception as e:
            self.status = "error"
            self.error = str(e)
            print(f"Errore processamento audio: {e}")
        finally:
            # Pulisci
            try:
                for f in os.listdir(chunk_dir):
                    try:
                        os.unlink(os.path.join(chunk_dir, f))
                    except:
                        pass
                os.rmdir(chunk_dir)
            except:
                pass
    
    def stop(self):
        """Ferma la sessione."""
        self.running = False
        
        if self.ffmpeg_video_process:
            try:
                # Chiudi stdin, stdout, stderr prima di terminare
                if self.ffmpeg_video_process.stdin:
                    try:
                        self.ffmpeg_video_process.stdin.close()
                    except:
                        pass
                if self.ffmpeg_video_process.stdout:
                    try:
                        self.ffmpeg_video_process.stdout.close()
                    except:
                        pass
                if self.ffmpeg_video_process.stderr:
                    try:
                        self.ffmpeg_video_process.stderr.close()
                    except:
                        pass
                
                # Termina il processo
                self.ffmpeg_video_process.terminate()
                try:
                    self.ffmpeg_video_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    # Se non termina, forza kill
                    self.ffmpeg_video_process.kill()
                    self.ffmpeg_video_process.wait()
            except Exception as e:
                print(f"Errore terminazione ffmpeg_video_process: {e}")
                try:
                    if self.ffmpeg_video_process.poll() is None:
                        self.ffmpeg_video_process.kill()
                except:
                    pass
            finally:
                self.ffmpeg_video_process = None
        
        if self.ffmpeg_audio_process:
            try:
                # Chiudi stdin, stdout, stderr prima di terminare
                if self.ffmpeg_audio_process.stdin:
                    try:
                        self.ffmpeg_audio_process.stdin.close()
                    except:
                        pass
                if self.ffmpeg_audio_process.stdout:
                    try:
                        self.ffmpeg_audio_process.stdout.close()
                    except:
                        pass
                if self.ffmpeg_audio_process.stderr:
                    try:
                        self.ffmpeg_audio_process.stderr.close()
                    except:
                        pass
                
                # Termina il processo
                self.ffmpeg_audio_process.terminate()
                try:
                    self.ffmpeg_audio_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    # Se non termina, forza kill
                    self.ffmpeg_audio_process.kill()
                    self.ffmpeg_audio_process.wait()
            except Exception as e:
                print(f"Errore terminazione ffmpeg_audio_process: {e}")
                try:
                    if self.ffmpeg_audio_process.poll() is None:
                        self.ffmpeg_audio_process.kill()
                except:
                    pass
            finally:
                self.ffmpeg_audio_process = None
    
    def cleanup(self):
        """Pulisce i file temporanei e le risorse."""
        self.stop()
        
        # Pulisci file temporanei
        try:
            if os.path.exists(self.srt_path):
                os.unlink(self.srt_path)
        except Exception as e:
            print(f"Errore rimozione SRT: {e}")
        
        try:
            if os.path.exists(self.video_pipe_path):
                # Se è una pipe, rimuovila
                if os.path.exists(self.video_pipe_path):
                    try:
                        os.unlink(self.video_pipe_path)
                    except:
                        pass
        except Exception as e:
            print(f"Errore rimozione pipe: {e}")
        
        # Assicurati che i processi siano None
        self.ffmpeg_video_process = None
        self.ffmpeg_audio_process = None
        self.stt = None


@app.route('/')
def index():
    """Pagina principale."""
    try:
        # Prova prima con la versione semplificata per debug
        simple_path = os.path.join(app.template_folder, 'index_simple.html')
        if os.path.exists(simple_path):
            try:
                return render_template('index_simple.html')
            except Exception as e:
                # Se render_template fallisce, leggi direttamente il file
                with open(simple_path, 'r', encoding='utf-8') as f:
                    return f.read()
        
        # Altrimenti usa il template completo
        template_path = os.path.join(app.template_folder, 'index.html')
        if not os.path.exists(template_path):
            return f"Template non trovato: {template_path}<br>Template folder: {app.template_folder}", 500
        
        try:
            return render_template('index.html')
        except Exception as e:
            # Se render_template fallisce, leggi direttamente il file
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as e:
        import traceback
        error_msg = f"Errore caricamento template: {str(e)}<br><pre>{traceback.format_exc()}</pre><br>Template dir: {app.template_folder}"
        return error_msg, 500

@app.route('/test')
def test():
    """Pagina di test semplice."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test</title>
        <meta charset="UTF-8">
        <style>
            body { font-family: Arial; padding: 20px; background: #f0f0f0; }
            h1 { color: #333; }
        </style>
    </head>
    <body>
        <h1>Test Page</h1>
        <p>Se vedi questo, il server Flask funziona correttamente!</p>
        <p>Template folder: """ + str(app.template_folder) + """</p>
        <p><a href="/">Torna alla pagina principale</a></p>
    </body>
    </html>
    """

@app.route('/debug')
def debug():
    """Pagina di debug."""
    import subprocess
    
    template_path = os.path.join(app.template_folder, 'index.html')
    simple_path = os.path.join(app.template_folder, 'index_simple.html')
    
    # Conta processi FFmpeg
    try:
        ffmpeg_count = len([p for p in subprocess.check_output(['ps', 'aux']).decode().split('\n') if 'ffmpeg' in p and 'video_session' in p])
    except:
        ffmpeg_count = 0
    
    # Lista sessioni attive
    active_sessions = []
    for session_id, session in sessions.items():
        active_sessions.append({
            'id': session_id,
            'status': session.status,
            'error': session.error,
            'pipe_exists': os.path.exists(session.video_pipe_path) if hasattr(session, 'video_pipe_path') else False,
            'srt_exists': os.path.exists(session.srt_path) if hasattr(session, 'srt_path') else False,
            'ffmpeg_running': session.ffmpeg_video_process.poll() is None if session.ffmpeg_video_process else False
        })
    
    info = {
        'template_folder': app.template_folder,
        'index_exists': os.path.exists(template_path),
        'simple_exists': os.path.exists(simple_path),
        'index_size': os.path.getsize(template_path) if os.path.exists(template_path) else 0,
        'simple_size': os.path.getsize(simple_path) if os.path.exists(simple_path) else 0,
        'cwd': os.getcwd(),
        'script_dir': os.path.dirname(os.path.abspath(__file__)),
        'active_sessions_count': len(sessions),
        'active_sessions': active_sessions,
        'ffmpeg_processes': ffmpeg_count,
        'platform': sys.platform
    }
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Debug Info</title>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: monospace; padding: 20px; background: #f5f5f5; }}
            pre {{ background: white; padding: 15px; border-radius: 5px; border: 1px solid #ddd; overflow-x: auto; }}
            .error {{ color: #c62828; font-weight: bold; }}
            .ok {{ color: #2e7d32; }}
            a {{ color: #1976d2; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <h1>🔍 Debug Info</h1>
        <pre>{json.dumps(info, indent=2)}</pre>
        <p><a href="/">← Torna alla pagina principale</a></p>
        <p><a href="/test">Pagina di test</a></p>
        <hr>
        <h2>Test API</h2>
        <p><a href="/api/status/session_1" target="_blank">Status Session 1</a></p>
        <p>Sessioni attive: <strong>{len(sessions)}</strong></p>
        <p>Processi FFmpeg: <strong>{ffmpeg_count}</strong></p>
    </body>
    </html>
    """


@app.route('/api/start', methods=['POST'])
def start_transcription():
    """Avvia una nuova sessione di trascrizione."""
    global session_counter
    
    data = request.json
    video_url = data.get('video_url', '').strip()
    language = data.get('language', 'en')
    model_size = data.get('model_size', 'base')
    chunk_duration = int(data.get('chunk_duration', 10))
    
    if not video_url:
        return jsonify({'error': 'URL video richiesto'}), 400
    
    if not is_url(video_url) and not os.path.exists(video_url):
        return jsonify({'error': 'URL o percorso file non valido'}), 400
    
    # Crea nuova sessione
    session_counter += 1
    session_id = f"session_{session_counter}"
    
    session = VideoTranscriptionSession(
        session_id=session_id,
        video_url=video_url,
        language=language,
        model_size=model_size,
        chunk_duration=chunk_duration
    )
    
    sessions[session_id] = session
    
    # Avvia in thread separato
    def start_in_thread():
        session.start()
    
    thread = threading.Thread(target=start_in_thread, daemon=True)
    thread.start()
    
    # L'URL dello stream sarà servito da Flask
    stream_url = f'/api/stream/{session_id}'
    
    return jsonify({
        'session_id': session_id,
        'video_url': video_url,
        'stream_url': stream_url,
        'status': 'starting'
    })


@app.route('/api/stream/<session_id>')
def stream_video(session_id):
    """Stream del video con sottotitoli burn-in."""
    if session_id not in sessions:
        return "Sessione non trovata", 404
    
    session = sessions[session_id]
    
    if not os.path.exists(session.video_pipe_path):
        return "Stream non disponibile", 404
    
    def generate():
        """Genera lo stream video dal file."""
        max_wait = 30  # Attendi max 30 secondi per l'inizio dello stream
        wait_count = 0
        
        try:
            # Attendi che il file esista e abbia contenuto
            while (not os.path.exists(session.video_pipe_path) or 
                   os.path.getsize(session.video_pipe_path) == 0) and wait_count < max_wait:
                time.sleep(0.5)
                wait_count += 1
            
            if not os.path.exists(session.video_pipe_path):
                print(f"Errore: file non creato dopo {max_wait} secondi")
                return
            
            # Per file MP4, assicurati che abbia almeno alcuni KB prima di iniziare
            file_size = os.path.getsize(session.video_pipe_path)
            if file_size < 1024:  # Meno di 1KB
                print(f"File troppo piccolo ({file_size} bytes), attendo...")
                time.sleep(2)
            
            # Apri il file
            is_pipe = False
            if hasattr(os.path, 'isfifo'):
                try:
                    is_pipe = os.path.isfifo(session.video_pipe_path)
                except:
                    pass
            
            try:
                f = open(session.video_pipe_path, 'rb')
                # Solo per pipe, imposta non-blocking
                if is_pipe and HAS_FCNTL and hasattr(fcntl, 'F_SETFL'):
                    try:
                        flags = fcntl.fcntl(f.fileno(), fcntl.F_GETFL)
                        fcntl.fcntl(f.fileno(), fcntl.F_SETFL, flags | os.O_NONBLOCK)
                    except (OSError, AttributeError):
                        pass
            except Exception as e:
                print(f"Errore apertura file: {e}")
                return
            
            empty_reads = 0
            max_empty_reads = 300  # Max 30 secondi di letture vuote per file MP4
            last_size = 0
            no_growth_count = 0
            min_file_size = 1024 * 100  # Attendi almeno 100KB prima di iniziare
            
            # Attendi che il file abbia una dimensione minima
            while os.path.getsize(session.video_pipe_path) < min_file_size and wait_count < max_wait:
                time.sleep(0.5)
                wait_count += 1
                if wait_count >= max_wait:
                    print(f"File troppo piccolo dopo attesa, procedo comunque")
                    break
            
            while session.running or (session.ffmpeg_video_process and session.ffmpeg_video_process.poll() is None):
                try:
                    # Per file MP4, leggi dalla posizione corrente
                    chunk = f.read(1024 * 128)  # Leggi 128KB alla volta (buffer più grande)
                    if chunk:
                        empty_reads = 0
                        no_growth_count = 0
                        yield chunk
                    else:
                        # Verifica se il file sta crescendo
                        current_size = os.path.getsize(session.video_pipe_path)
                        if current_size > last_size:
                            last_size = current_size
                            no_growth_count = 0
                            # File sta crescendo, riposiziona e riprova
                            f.seek(f.tell())  # Mantieni posizione
                            time.sleep(0.3)  # Attesa leggermente più lunga
                        else:
                            no_growth_count += 1
                            empty_reads += 1
                            if empty_reads > max_empty_reads or no_growth_count > 100:
                                print("File non sta crescendo o troppi read vuoti")
                                break
                            time.sleep(0.3)  # Attesa più lunga per permettere a FFmpeg di scrivere
                except (IOError, OSError) as e:
                    if e.errno == 11:  # EAGAIN - nessun dato disponibile (solo per pipe)
                        time.sleep(0.1)
                        continue
                    else:
                        print(f"Errore lettura file: {e}")
                        break
                except Exception as e:
                    print(f"Errore generico: {e}")
                    break
            
            f.close()
        except Exception as e:
            print(f"Errore streaming: {e}")
            import traceback
            traceback.print_exc()
    
    # Determina MIME type in base al formato file
    if session.video_pipe_path.endswith('.mp4'):
        mimetype = 'video/mp4'
        content_type = 'video/mp4'
    else:
        mimetype = 'video/mp2t'
        content_type = 'video/mp2t'
    
    return Response(
        stream_with_context(generate()),
        mimetype=mimetype,
        headers={
            'Content-Type': content_type,
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
            'X-Accel-Buffering': 'no',
            'Accept-Ranges': 'bytes'
        }
    )


@app.route('/api/status/<session_id>')
def get_status(session_id):
    """Ottiene lo stato della sessione."""
    if session_id not in sessions:
        return jsonify({'error': 'Sessione non trovata'}), 404
    
    session = sessions[session_id]
    
    return jsonify({
        'session_id': session_id,
        'status': session.status,
        'error': session.error,
        'subtitles_count': len(session.all_subtitles),
        'subtitles': session.all_subtitles[-10:] if session.all_subtitles else []  # Ultimi 10
    })


@app.route('/api/stop/<session_id>', methods=['POST'])
def stop_session(session_id):
    """Ferma una sessione."""
    if session_id not in sessions:
        return jsonify({'error': 'Sessione non trovata'}), 404
    
    session = sessions[session_id]
    session.stop()
    
    return jsonify({'status': 'stopped'})


@app.route('/api/cleanup/<session_id>', methods=['POST'])
def cleanup_session(session_id):
    """Pulisce una sessione."""
    if session_id not in sessions:
        return jsonify({'error': 'Sessione non trovata'}), 404
    
    session = sessions[session_id]
    try:
        session.cleanup()
    except Exception as e:
        print(f"Errore cleanup sessione {session_id}: {e}")
    finally:
        if session_id in sessions:
            del sessions[session_id]
    
    return jsonify({'status': 'cleaned'})

@app.route('/api/cleanup/all', methods=['POST'])
def cleanup_all_sessions():
    """Pulisce tutte le sessioni attive."""
    global sessions
    cleaned = 0
    for session_id, session in list(sessions.items()):
        try:
            session.cleanup()
            cleaned += 1
        except Exception as e:
            print(f"Errore cleanup sessione {session_id}: {e}")
    sessions.clear()
    return jsonify({'status': 'cleaned', 'sessions_cleaned': cleaned})


def cleanup_all_sessions():
    """Pulisce tutte le sessioni attive."""
    global sessions
    for session_id, session in list(sessions.items()):
        try:
            session.cleanup()
        except Exception as e:
            print(f"Errore cleanup sessione {session_id}: {e}")
    sessions.clear()


def signal_handler(signum, frame):
    """Gestisce i segnali di terminazione per pulire le risorse."""
    print("\n\nRicevuto segnale di terminazione, pulizia risorse...")
    cleanup_all_sessions()
    sys.exit(0)


if __name__ == '__main__':
    import argparse
    import signal
    
    # Registra handler per segnali di terminazione
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    parser = argparse.ArgumentParser(description='Server web per trascrizione video con sottotitoli')
    parser.add_argument('--host', default='0.0.0.0', help='Host (default: 0.0.0.0 per accesso remoto)')
    parser.add_argument('--port', type=int, default=5000, help='Porta (default: 5000)')
    parser.add_argument('--debug', action='store_true', help='Modalità debug')
    
    args = parser.parse_args()
    
    print(f"\n=== Server Web Trascrizione Video ===")
    print(f"Accessibile su: http://{args.host}:{args.port}")
    print(f"Template folder: {app.template_folder}")
    print(f"Premi Ctrl+C per fermare\n")
    
    # Disabilita il controllo degli accessi per debug
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
    
    try:
        app.run(host=args.host, port=args.port, debug=args.debug, threaded=True, use_reloader=False)
    except KeyboardInterrupt:
        print("\n\nInterruzione da utente, pulizia risorse...")
        cleanup_all_sessions()
    except PermissionError as e:
        print(f"\n❌ Errore permessi: {e}")
        print(f"Prova con una porta diversa: python web_app.py --port 8080")
        cleanup_all_sessions()
        sys.exit(1)
    finally:
        cleanup_all_sessions()

