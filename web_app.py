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
                os.mkfifo(self.video_pipe_path, stat.S_IRUSR | stat.S_IWUSR)
            except Exception as e:
                print(f"Errore creazione pipe: {e}")
                self.video_pipe_path = tempfile.NamedTemporaryFile(suffix='.ts', delete=False).name
            
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
                                with open(self.srt_path, 'w', encoding='utf-8') as f:
                                    for sub in self.all_subtitles:
                                        f.write(f"{sub['index']}\n")
                                        f.write(f"{format_srt_time(sub['start'])} --> {format_srt_time(sub['end'])}\n")
                                        f.write(f"{sub['text']}\n\n")
                                
                                # Riavvia FFmpeg ogni 3 sottotitoli
                                if self.subtitle_index % 3 == 0:
                                    try:
                                        self.ffmpeg_video_process.terminate()
                                        self.ffmpeg_video_process.wait(timeout=2)
                                    except:
                                        try:
                                            self.ffmpeg_video_process.kill()
                                        except:
                                            pass
                                    
                                    self.ffmpeg_video_process = restart_ffmpeg_video_process(
                                        self.video_url,
                                        self.srt_path,
                                        self.video_pipe_path,
                                        use_http=False
                                    )
                                    time.sleep(1)
                                
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
                self.ffmpeg_video_process.terminate()
                self.ffmpeg_video_process.wait(timeout=5)
            except:
                try:
                    self.ffmpeg_video_process.kill()
                except:
                    pass
        
        if self.ffmpeg_audio_process:
            try:
                self.ffmpeg_audio_process.terminate()
                self.ffmpeg_audio_process.wait(timeout=5)
            except:
                try:
                    self.ffmpeg_audio_process.kill()
                except:
                    pass
    
    def cleanup(self):
        """Pulisce i file temporanei."""
        self.stop()
        
        try:
            if os.path.exists(self.srt_path):
                os.unlink(self.srt_path)
        except:
            pass
        
        try:
            if os.path.exists(self.video_pipe_path):
                os.unlink(self.video_pipe_path)
        except:
            pass


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
    template_path = os.path.join(app.template_folder, 'index.html')
    simple_path = os.path.join(app.template_folder, 'index_simple.html')
    
    info = {
        'template_folder': app.template_folder,
        'index_exists': os.path.exists(template_path),
        'simple_exists': os.path.exists(simple_path),
        'index_size': os.path.getsize(template_path) if os.path.exists(template_path) else 0,
        'simple_size': os.path.getsize(simple_path) if os.path.exists(simple_path) else 0,
        'cwd': os.getcwd(),
        'script_dir': os.path.dirname(os.path.abspath(__file__))
    }
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Debug Info</title>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: monospace; padding: 20px; }}
            pre {{ background: #f5f5f5; padding: 10px; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <h1>Debug Info</h1>
        <pre>{json.dumps(info, indent=2)}</pre>
        <p><a href="/">Torna alla pagina principale</a></p>
        <p><a href="/test">Pagina di test</a></p>
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
        """Genera lo stream video dalla pipe."""
        try:
            with open(session.video_pipe_path, 'rb') as f:
                while session.running or (session.ffmpeg_video_process and session.ffmpeg_video_process.poll() is None):
                    chunk = f.read(1024 * 64)  # Leggi 64KB alla volta
                    if not chunk:
                        time.sleep(0.1)
                        continue
                    yield chunk
        except Exception as e:
            print(f"Errore streaming: {e}")
            # Se la pipe è chiusa, prova a riaprirla
            time.sleep(0.5)
    
    return Response(
        stream_with_context(generate()),
        mimetype='video/mp2t',
        headers={
            'Content-Type': 'video/mp2t',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
            'X-Accel-Buffering': 'no'
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
    session.cleanup()
    del sessions[session_id]
    
    return jsonify({'status': 'cleaned'})


if __name__ == '__main__':
    import argparse
    
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
    except PermissionError as e:
        print(f"\n❌ Errore permessi: {e}")
        print(f"Prova con una porta diversa: python web_app.py --port 8080")
        sys.exit(1)

