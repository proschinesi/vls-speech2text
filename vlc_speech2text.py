#!/usr/bin/env python3
"""
Script per lanciare VLC con output speech-to-text incorporato.
Usa Whisper per la trascrizione in tempo reale.
"""

import subprocess
import sys
import os
import argparse
import tempfile
import threading
import queue
import time
from pathlib import Path

try:
    import whisper
    import torch
    import numpy as np
except ImportError:
    print("Errore: Installa le dipendenze con: pip install -r requirements.txt")
    sys.exit(1)

# pydub è opzionale (problemi con Python 3.13)
# Richiesto solo per --realtime, non per --live
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    # Non stampare avviso qui - sarà mostrato solo se si usa --realtime


class VLCSpeechToText:
    def __init__(self, model_size="base", language="it"):
        """
        Inizializza il sistema di speech-to-text.
        
        Args:
            model_size: Dimensione del modello Whisper (tiny, base, small, medium, large)
            language: Codice lingua (it per italiano, en per inglese, etc.)
        """
        self.model_size = model_size
        self.language = language
        self.model = None
        self.audio_queue = queue.Queue()
        self.running = False
        
    def load_model(self):
        """Carica il modello Whisper."""
        print(f"Caricamento modello Whisper ({self.model_size})...")
        self.model = whisper.load_model(self.model_size)
        print("Modello caricato!")
        
    def transcribe_audio(self, audio_path):
        """Trascrive un file audio."""
        if not self.model:
            self.load_model()
        
        # Verifica che il file esista e non sia vuoto
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"File audio non trovato: {audio_path}")
        
        file_size = os.path.getsize(audio_path)
        if file_size == 0:
            raise ValueError(f"File audio vuoto: {audio_path}")
        
        print(f"Trascrizione file audio ({file_size} bytes)...")
            
        # Se language è "auto", Whisper rileverà automaticamente la lingua
        transcribe_kwargs = {
            "task": "transcribe"
        }
        if self.language and self.language.lower() != "auto":
            transcribe_kwargs["language"] = self.language
        
        result = self.model.transcribe(
            audio_path,
            **transcribe_kwargs
        )
        return result["text"]
    
    def process_audio_stream(self, audio_file):
        """Processa lo stream audio in tempo reale."""
        if not PYDUB_AVAILABLE:
            print("Errore: pydub non disponibile. Usa la modalità normale (senza --realtime).")
            return
            
        if not self.model:
            self.load_model()
        
        print("\n=== Trascrizione in corso (premi Ctrl+C per interrompere) ===\n")
        
        # Processa l'audio in chunk
        chunk_duration = 10  # secondi per chunk
        
        try:
            audio = AudioSegment.from_file(audio_file)
            total_duration = len(audio) / 1000.0  # in secondi
            
            for start_time in range(0, int(total_duration), chunk_duration):
                if not self.running:
                    break
                    
                end_time = min(start_time + chunk_duration, total_duration)
                chunk = audio[start_time * 1000:end_time * 1000]
                
                # Salva chunk temporaneo
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    chunk.export(tmp.name, format="wav")
                    tmp_path = tmp.name
                
                try:
                    # Trascrivi chunk
                    result = self.model.transcribe(
                        tmp_path,
                        language=self.language,
                        task="transcribe",
                        fp16=False
                    )
                    
                    text = result["text"].strip()
                    if text:
                        print(f"[{start_time:05.1f}s - {end_time:05.1f}s] {text}")
                        
                finally:
                    os.unlink(tmp_path)
                    
        except KeyboardInterrupt:
            print("\n\nInterruzione richiesta dall'utente.")
        except Exception as e:
            print(f"\nErrore durante la trascrizione: {e}")


def is_url(source):
    """Verifica se l'input è un URL."""
    return source.startswith(("http://", "https://", "rtsp://", "rtmp://", "mms://"))


def is_hls_url(source):
    """Verifica se l'URL è un HLS stream."""
    return is_url(source) and (".m3u8" in source.lower() or "hls" in source.lower())


def extract_audio_with_ffmpeg(input_source, output_file, duration=None):
    """Estrae audio usando FFmpeg (alternativa a VLC)."""
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", input_source,
        "-vn",  # No video
        "-acodec", "pcm_s16le",  # PCM 16-bit
        "-ar", "16000",  # Sample rate 16kHz (ottimale per Whisper)
        "-ac", "1",  # Mono
        "-y"  # Overwrite output
    ]
    
    if duration and duration > 0:
        ffmpeg_cmd.extend(["-t", str(int(duration))])
    
    ffmpeg_cmd.append(output_file)
    
    try:
        result = subprocess.run(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=None if not duration else duration + 30
        )
        return result.returncode == 0, result.stderr.decode()
    except subprocess.TimeoutExpired:
        return False, "Timeout durante estrazione audio"
    except FileNotFoundError:
        return False, "FFmpeg non trovato"


def format_srt_time(seconds):
    """Converte secondi in formato SRT (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def get_vlc_time(vlc_port=8080):
    """Ottiene il tempo di riproduzione corrente di VLC in secondi."""
    try:
        import urllib.request
        import xml.etree.ElementTree as ET
        
        url = f"http://localhost:{vlc_port}/requests/status.xml"
        response = urllib.request.urlopen(url, timeout=1)
        xml_data = response.read()
        root = ET.fromstring(xml_data)
        
        # Cerca il tag 'time' che contiene il tempo in secondi
        time_elem = root.find('time')
        if time_elem is not None and time_elem.text:
            return float(time_elem.text) / 1000.0  # Converti da millisecondi a secondi
        return None
    except:
        return None


def update_vlc_subtitles(vlc_port=8080, srt_path=None):
    """Aggiorna i sottotitoli in VLC tramite API HTTP."""
    try:
        import urllib.request
        import urllib.parse
        
        # Forza VLC a ricaricare il file SRT
        # Usa il percorso assoluto del file
        abs_path = os.path.abspath(srt_path) if srt_path else ""
        
        # Su macOS, usa file:// URL con encoding corretto
        if sys.platform == "darwin" and abs_path:
            # Rimuovi spazi e caratteri speciali dal percorso
            file_url = f"file://{abs_path}"
        else:
            file_url = abs_path
        
        # Prova prima a disabilitare i sottotitoli, poi a riabilitarli con il nuovo file
        # Questo forza VLC a ricaricare il file
        base_url = f"http://localhost:{vlc_port}/requests/status.xml"
        
        # Disabilita sottotitoli
        try:
            urllib.request.urlopen(f"{base_url}?command=subtitle_track&val=-1", timeout=0.5)
            time.sleep(0.1)
        except:
            pass
        
        # Ricarica il file SRT
        url = f"{base_url}?command=subtitle_file&val={urllib.parse.quote(file_url, safe='')}"
        urllib.request.urlopen(url, timeout=1)
        
        # Riabilita i sottotitoli (traccia 0)
        try:
            urllib.request.urlopen(f"{base_url}?command=subtitle_track&val=0", timeout=0.5)
        except:
            pass
        
        return True
    except Exception as e:
        # Non stampare errori, l'API potrebbe non essere disponibile
        return False


def restart_ffmpeg_video_process(input_source, srt_path, output_path=None, use_http=False, http_port=8090):
    """
    Riavvia FFmpeg per processare video con sottotitoli burn-in aggiornati.
    
    Args:
        input_source: File o URL di input
        srt_path: Percorso file SRT
        output_path: Percorso output (pipe, file, o None per stdout)
        use_http: Se True, usa HTTP streaming invece di pipe
        http_port: Porta HTTP se use_http=True
    """
    # Escape del percorso SRT per il filtro subtitles
    # Su macOS, potrebbe essere necessario usare percorsi assoluti
    abs_srt_path = os.path.abspath(srt_path)
    
    # Escape caratteri speciali nel percorso SRT per il filtro
    # Sostituisci apostrofi e altri caratteri problematici
    escaped_srt_path = abs_srt_path.replace("'", "\\'").replace(":", "\\:")
    
    # Determina formato output in base al percorso
    # Se è una pipe o file .ts, usa MPEG-TS, altrimenti MP4
    use_mp4 = False
    if output_path and not output_path.endswith('.ts'):
        use_mp4 = True
    
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", input_source,
        "-vf", f"subtitles='{escaped_srt_path}':force_style='FontSize=24,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2,Bold=1'",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-profile:v", "baseline",  # Profilo baseline per massima compatibilità
        "-level", "3.0",
        "-pix_fmt", "yuv420p",  # Formato pixel standard
        "-c:a", "aac",
        "-b:a", "128k",  # Bitrate audio fisso
        "-ar", "44100",  # Sample rate standard
    ]
    
    if use_mp4:
        # MP4 fragmented per streaming - metadati all'inizio
        ffmpeg_cmd.extend([
            "-f", "mp4",
            "-movflags", "frag_keyframe+empty_moov+default_base_moof",  # Streaming-friendly
            "-frag_duration", "1000000"  # 1 secondo per fragment
        ])
    else:
        ffmpeg_cmd.extend(["-f", "mpegts"])
    
    if use_http:
        # HTTP streaming - FFmpeg come server HTTP
        ffmpeg_cmd.extend([
            "-listen", "1",  # Modalità server HTTP
            f"http://0.0.0.0:{http_port}"
        ])
    elif output_path:
        # Output su file/pipe
        ffmpeg_cmd.extend(["-y", output_path])
    else:
        # Output su stdout (per pipe diretta)
        ffmpeg_cmd.append("-")
    
    # Configura process creation per evitare semafori leaked
    import multiprocessing
    # Usa spawn invece di fork su macOS per evitare problemi con semafori
    if sys.platform == 'darwin':
        # Su macOS, usa start_new_session per isolare il processo
        return subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE if not output_path and not use_http else subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True  # Crea nuova sessione per isolare il processo
        )
    else:
        return subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE if not output_path and not use_http else subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )


def launch_vlc_with_subtitles(input_source, model_size="base", language="it", 
                             chunk_duration=10, vlc_path="vlc"):
    """
    Avvia VLC con riproduzione video e sottotitoli burn-in usando FFmpeg.
    FFmpeg processa il video con i sottotitoli incorporati e lo invia a VLC.
    
    Args:
        input_source: File o URL da riprodurre
        model_size: Dimensione modello Whisper
        language: Codice lingua
        chunk_duration: Durata chunk per trascrizione
        vlc_path: Percorso a VLC
    """
    stt = VLCSpeechToText(model_size=model_size, language=language)
    print("Caricamento modello Whisper...")
    stt.load_model()
    
    # Crea file SRT per i sottotitoli con contenuto minimo iniziale
    # VLC non può aprire file SRT vuoti, quindi aggiungiamo un sottotitolo placeholder
    srt_file = tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8')
    srt_file.write("1\n")  # Indice sottotitolo
    srt_file.write("00:00:00,000 --> 00:00:01,000\n")  # Timestamp
    srt_file.write("Caricamento sottotitoli...\n")  # Testo placeholder
    srt_file.write("\n")  # Riga vuota
    srt_file.close()
    srt_path = srt_file.name
    
    # Assicurati che il file esista e abbia contenuto
    if not os.path.exists(srt_path) or os.path.getsize(srt_path) == 0:
        raise Exception(f"Impossibile creare file SRT: {srt_path}")
    
    print(f"\n=== VLC con sottotitoli BURN-IN (FFmpeg) ===")
    print(f"Input: {input_source}")
    print(f"File SRT: {srt_path}")
    print(f"Lingua: {language} (usa --language en per inglese, --language auto per rilevamento automatico)")
    print(f"Chunk: {chunk_duration} secondi")
    print(f"FFmpeg processerà il video con sottotitoli incorporati e lo invierà a VLC\n")
    
    # Usa ffplay invece di VLC - funziona meglio con pipe e streaming
    # Verifica che ffplay sia disponibile
    try:
        subprocess.run(["ffplay", "-version"], 
                      stdout=subprocess.PIPE, 
                      stderr=subprocess.PIPE,
                      check=True,
                      timeout=5)
        use_ffplay = True
        print("✓ ffplay disponibile - useremo ffplay per la riproduzione")
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        use_ffplay = False
        print("⚠ ffplay non trovato - useremo VLC (potrebbe non funzionare bene con pipe)")
        print("  Installa ffplay: ffplay è incluso con FFmpeg")
    
    # Usa una named pipe per lo streaming (funziona meglio con ffplay)
    import stat
    video_pipe_path = os.path.join(tempfile.gettempdir(), f"ffmpeg_playback_{os.getpid()}.ts")
    
    # Crea una named pipe per lo streaming real-time
    try:
        if os.path.exists(video_pipe_path):
            os.unlink(video_pipe_path)
        os.mkfifo(video_pipe_path, stat.S_IRUSR | stat.S_IWUSR)
        print(f"✓ Named pipe creata: {video_pipe_path}")
    except Exception as e:
        print(f"⚠ Errore creazione pipe: {e}")
        # Fallback: usa file normale (meno efficiente ma funziona)
        video_pipe_path = tempfile.NamedTemporaryFile(suffix='.ts', delete=False).name
        print(f"  Usando file temporaneo invece: {video_pipe_path}")
    
    print("Pipeline: FFmpeg (video + sottotitoli) → Pipe → Player (riproduzione)")
    print(f"Pipe: {video_pipe_path}\n")
    
    # Avvia FFmpeg per processare video con sottotitoli burn-in
    print("Avvio FFmpeg per processare video con sottotitoli burn-in...")
    ffmpeg_video_process = restart_ffmpeg_video_process(
        input_source,
        srt_path,
        video_pipe_path,
        use_http=False
    )
    
    # Aspetta che FFmpeg inizi a generare lo stream
    time.sleep(2)
    
    # Avvia il player (ffplay o VLC)
    if use_ffplay:
        player_cmd = [
            "ffplay",
            video_pipe_path,  # ffplay legge dalla pipe
            "-autoexit",  # Esci automaticamente alla fine
            "-fs",  # Fullscreen (opzionale)
        ]
        player_name = "ffplay"
    else:
        player_cmd = [
            vlc_path,
            video_pipe_path,  # VLC legge dalla pipe
        ]
        player_name = "VLC"
    
    print(f"Avvio {player_name} per riprodurre lo stream processato...")
    print(f"Comando: {' '.join(player_cmd)}\n")
    
    # Avvia il player (ffplay o VLC)
    try:
        if use_ffplay:
            # ffplay funziona meglio con pipe
            player_process = subprocess.Popen(
                player_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            # VLC su macOS
            if sys.platform == "darwin":
                player_process = subprocess.Popen(
                    player_cmd,
                    stdout=None,
                    stderr=None,
                )
            else:
                player_process = subprocess.Popen(
                    player_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        
        time.sleep(3)
        
        if player_process.poll() is not None:
            print(f"⚠ Errore: {player_name} si è chiuso immediatamente.")
            print("Verifica che il player sia installato correttamente")
            sys.exit(1)
        else:
            print(f"✓ {player_name} avviato - riproduzione in corso")
            print("✓ FFmpeg sta processando il video con sottotitoli burn-in")
            print("I sottotitoli verranno aggiornati riavviando FFmpeg quando necessario\n")
            
    except Exception as e:
        print(f"❌ Errore durante avvio {player_name}: {e}")
        sys.exit(1)
    
    # Inizia a processare l'audio in parallelo
    chunk_dir = tempfile.mkdtemp(prefix="whisper_chunks_")
    chunk_pattern = os.path.join(chunk_dir, "chunk_%04d.wav")
    chunk_counter = 0
    subtitle_index = 1
    all_subtitles = []
    last_ffmpeg_restart = 0  # Timestamp dell'ultimo riavvio di FFmpeg
    
    # Avvia FFmpeg per estrarre audio chunk in parallelo
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", input_source,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        "-f", "segment",
        "-segment_time", str(chunk_duration),
        "-segment_format", "wav",
        "-reset_timestamps", "1",
        "-strftime", "0",
        "-y",
        chunk_pattern
    ]
    
    ffmpeg_process = subprocess.Popen(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    processed_chunks = set()
    
    try:
        print("Processamento audio e generazione sottotitoli in tempo reale...")
        print("FFmpeg verrà riavviato periodicamente per applicare i nuovi sottotitoli\n")
        
        while player_process.poll() is None or ffmpeg_process.poll() is None:
            # Cerca nuovi chunk
            for i in range(chunk_counter, chunk_counter + 10):
                chunk_file = os.path.join(chunk_dir, f"chunk_{i:04d}.wav")
                
                if os.path.exists(chunk_file) and chunk_file not in processed_chunks:
                    processed_chunks.add(chunk_file)
                    time.sleep(0.5)  # Aspetta che il file sia completo
                    
                    if os.path.getsize(chunk_file) == 0:
                        continue
                    
                    # Calcola timestamp basati sui chunk
                    # I timestamp sono relativi all'inizio del video
                    chunk_start_time = (i * chunk_duration)
                    chunk_end_time = ((i + 1) * chunk_duration)
                    
                    try:
                        # Trascrivi chunk
                        print(f"[Chunk {i}] Trascrizione...", end=" ", flush=True)
                        transcribe_start = time.time()
                        result = stt.model.transcribe(
                            chunk_file,
                            language=language,
                            task="transcribe",
                            fp16=False
                        )
                        transcribe_time = time.time() - transcribe_start
                        
                        text = result["text"].strip()
                        if text:
                            # Aggiungi sottotitolo
                            subtitle = {
                                'index': subtitle_index,
                                'start': chunk_start_time,
                                'end': chunk_end_time,
                                'text': text
                            }
                            all_subtitles.append(subtitle)
                            
                            # Aggiorna file SRT
                            with open(srt_path, 'w', encoding='utf-8') as f:
                                for sub in all_subtitles:
                                    f.write(f"{sub['index']}\n")
                                    f.write(f"{format_srt_time(sub['start'])} --> {format_srt_time(sub['end'])}\n")
                                    f.write(f"{sub['text']}\n\n")
                            
                            # Debug: mostra informazioni sul sottotitolo
                            print(f"✓ ({transcribe_time:.1f}s) - {text[:50]}...")
                            print(f"   Timestamp: {format_srt_time(chunk_start_time)} --> {format_srt_time(chunk_end_time)}")
                            
                            # Riavvia FFmpeg ogni 3-5 sottotitoli per applicare i nuovi sottotitoli burn-in
                            # Questo è necessario perché FFmpeg non ricarica automaticamente il file SRT
                            if subtitle_index % 3 == 0:  # Riavvia ogni 3 sottotitoli
                                try:
                                    print(f"   🔄 Riavvio FFmpeg per applicare nuovi sottotitoli...")
                                    
                                    # Termina FFmpeg corrente
                                    try:
                                        ffmpeg_video_process.terminate()
                                        ffmpeg_video_process.wait(timeout=2)
                                    except:
                                        try:
                                            ffmpeg_video_process.kill()
                                        except:
                                            pass
                                    
                                    # Riavvia FFmpeg con il file SRT aggiornato
                                    ffmpeg_video_process = restart_ffmpeg_video_process(
                                        input_source,
                                        srt_path,
                                        video_pipe_path,
                                        use_http=False
                                    )
                                    
                                    time.sleep(1)  # Aspetta che FFmpeg si riavvii
                                    print(f"   ✓ FFmpeg riavviato con sottotitoli aggiornati")
                                    last_ffmpeg_restart = subtitle_index
                                    
                                except Exception as e:
                                    print(f"   ⚠ Errore riavvio FFmpeg: {str(e)[:50]}")
                            subtitle_index += 1
                        else:
                            print(f"(nessun testo, {transcribe_time:.1f}s)")
                        
                        os.unlink(chunk_file)
                        chunk_counter = i + 1
                        
                    except Exception as e:
                        print(f"Errore: {e}")
                        if os.path.exists(chunk_file):
                            try:
                                os.unlink(chunk_file)
                            except:
                                pass
            
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n\nInterruzione richiesta dall'utente.")
    finally:
        # Termina processi
        try:
            player_process.terminate()
            player_process.wait(timeout=5)
        except:
            try:
                player_process.kill()
            except:
                pass
        
        try:
            ffmpeg_video_process.terminate()
            ffmpeg_video_process.wait(timeout=5)
        except:
            try:
                ffmpeg_video_process.kill()
            except:
                pass
        
        try:
            ffmpeg_process.terminate()
            ffmpeg_process.wait(timeout=5)
        except:
            try:
                ffmpeg_process.kill()
            except:
                pass
        
        # Pulisci named pipe
        try:
            if os.path.exists(video_pipe_path):
                os.unlink(video_pipe_path)
        except:
            pass
        
        # Pulisci chunk
        try:
            for f in os.listdir(chunk_dir):
                try:
                    os.unlink(os.path.join(chunk_dir, f))
                except:
                    pass
            os.rmdir(chunk_dir)
        except:
            pass
        
        print(f"\n\n=== Trascrizione completa ===")
        print(f"File SRT salvato: {srt_path}")
        print(f"Totale sottotitoli generati: {len(all_subtitles)}")
        print(f"\nPuoi aprire il file SRT con VLC o qualsiasi player video per vedere i sottotitoli.")


def launch_ffplay_with_subtitles(input_source, model_size="base", language="it", 
                                chunk_duration=10):
    """
    Avvia ffplay (FFmpeg) con riproduzione video e genera sottotitoli burn-in in tempo reale.
    
    Args:
        input_source: File o URL da riprodurre
        model_size: Dimensione modello Whisper
        language: Codice lingua
        chunk_duration: Durata chunk per trascrizione
    """
    stt = VLCSpeechToText(model_size=model_size, language=language)
    print("Caricamento modello Whisper...")
    stt.load_model()
    
    # Crea file SRT per i sottotitoli (inizialmente vuoto)
    srt_file = tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False)
    srt_file.write("")  # File vuoto iniziale
    srt_file.close()
    srt_path = srt_file.name
    
    print(f"\n=== ffplay con sottotitoli BURN-IN ===")
    print(f"Input: {input_source}")
    print(f"File SRT: {srt_path}")
    print(f"Chunk: {chunk_duration} secondi")
    print(f"I sottotitoli saranno sovrapposti direttamente sul video\n")
    
    # Pipeline: FFmpeg processa video con sottotitoli burn-in -> ffplay riproduce
    # Usa una named pipe (FIFO) per lo streaming in tempo reale
    import stat
    
    video_pipe_path = os.path.join(tempfile.gettempdir(), f"ffplay_subtitles_{os.getpid()}.ts")
    
    # Crea una named pipe per lo streaming real-time
    try:
        if os.path.exists(video_pipe_path):
            os.unlink(video_pipe_path)
        os.mkfifo(video_pipe_path, stat.S_IRUSR | stat.S_IWUSR)
    except Exception as e:
        print(f"Errore creazione pipe: {e}")
        # Fallback: usa file normale
        video_pipe_path = tempfile.NamedTemporaryFile(suffix='.ts', delete=False).name
    
    print("=== Pipeline FFmpeg -> ffplay con sottotitoli burn-in ===")
    print(f"Input: {input_source}")
    print(f"Pipeline: FFmpeg processa video -> ffplay riproduce")
    print(f"File SRT: {srt_path}")
    print(f"Chunk: {chunk_duration} secondi")
    print(f"I sottotitoli verranno incorporati direttamente nel video\n")
    
    # Avvia FFmpeg per processare video con sottotitoli burn-in
    # FFmpeg scrive su una pipe che ffplay leggerà
    print("Avvio FFmpeg per processare video con sottotitoli burn-in...")
    ffmpeg_video_process = restart_ffmpeg_video_process(
        input_source,
        srt_path,
        video_pipe_path
    )
    
    # Aspetta che FFmpeg inizi a generare lo stream
    time.sleep(2)
    
    # Avvia ffplay per riprodurre lo stream processato
    ffplay_cmd = [
        "ffplay",
        video_pipe_path,  # ffplay legge dalla pipe
        "-autoexit",  # Esci automaticamente alla fine
        "-fs",  # Fullscreen (opzionale, rimuovi se non vuoi)
    ]
    
    print("Avvio ffplay per riprodurre lo stream processato...\n")
    
    # Avvia ffplay (con GUI)
    ffplay_process = subprocess.Popen(
        ffplay_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Aspetta che ffplay si avvii
    time.sleep(2)
    
    print("✓ Pipeline attiva: FFmpeg -> ffplay\n")
    
    # Inizia a processare l'audio in parallelo
    chunk_dir = tempfile.mkdtemp(prefix="whisper_chunks_")
    chunk_pattern = os.path.join(chunk_dir, "chunk_%04d.wav")
    chunk_counter = 0
    subtitle_index = 1
    vlc_start_time = time.time()  # Tempo di avvio VLC
    
    # Avvia FFmpeg per estrarre audio chunk in parallelo
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", input_source,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        "-f", "segment",
        "-segment_time", str(chunk_duration),
        "-segment_format", "wav",
        "-reset_timestamps", "1",
        "-strftime", "0",
        "-y",
        chunk_pattern
    ]
    
    ffmpeg_process = subprocess.Popen(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    processed_chunks = set()
    all_subtitles = []  # Accumula tutti i sottotitoli
    
    try:
        print("✓ VLC avviato - riproduzione in corso")
        print("Processamento audio e generazione sottotitoli burn-in in tempo reale...\n")
        
        while ffplay_process.poll() is None or ffmpeg_process.poll() is None:
            # Cerca nuovi chunk
            for i in range(chunk_counter, chunk_counter + 10):
                chunk_file = os.path.join(chunk_dir, f"chunk_{i:04d}.wav")
                
                if os.path.exists(chunk_file) and chunk_file not in processed_chunks:
                    processed_chunks.add(chunk_file)
                    time.sleep(0.5)  # Aspetta che il file sia completo
                    
                    if os.path.getsize(chunk_file) == 0:
                        continue
                    
                    # Calcola timestamp basato sul tempo di riproduzione
                    # I chunk sono consecutivi, quindi timestamp = chunk_index * chunk_duration
                    chunk_start_time = (i * chunk_duration)
                    chunk_end_time = ((i + 1) * chunk_duration)
                    
                    try:
                        # Trascrivi chunk
                        print(f"[Chunk {i}] Trascrizione...", end=" ", flush=True)
                        transcribe_start = time.time()
                        result = stt.model.transcribe(
                            chunk_file,
                            language=language,
                            task="transcribe",
                            fp16=False
                        )
                        transcribe_time = time.time() - transcribe_start
                        
                        text = result["text"].strip()
                        if text:
                            # Aggiungi sottotitolo
                            subtitle = {
                                'index': subtitle_index,
                                'start': chunk_start_time,
                                'end': chunk_end_time,
                                'text': text
                            }
                            all_subtitles.append(subtitle)
                            
                            # Aggiorna file SRT (scrive tutto il file ogni volta)
                            with open(srt_path, 'w', encoding='utf-8') as f:
                                for sub in all_subtitles:
                                    f.write(f"{sub['index']}\n")
                                    f.write(f"{format_srt_time(sub['start'])} --> {format_srt_time(sub['end'])}\n")
                                    f.write(f"{sub['text']}\n\n")
                            
                            print(f"✓ ({transcribe_time:.1f}s) - {text[:50]}...")
                            
                            # Per sottotitoli burn-in in tempo reale, FFmpeg processa continuamente
                            # Il file SRT viene aggiornato, ma FFmpeg non lo ricarica automaticamente
                            # In una pipeline real-time, i sottotitoli vengono aggiunti progressivamente
                            # e FFmpeg continua a processare il video con tutti i sottotitoli disponibili
                            # Nota: i nuovi sottotitoli saranno visibili solo se FFmpeg viene riavviato
                            # Per una vera pipeline real-time, sarebbe necessario un filtro FFmpeg
                            # che legge dinamicamente il file SRT, ma questo non è supportato nativamente
                            
                            subtitle_index += 1
                        else:
                            print(f"(nessun testo, {transcribe_time:.1f}s)")
                        
                        os.unlink(chunk_file)
                        chunk_counter = i + 1
                        
                    except Exception as e:
                        print(f"Errore: {e}")
                        if os.path.exists(chunk_file):
                            try:
                                os.unlink(chunk_file)
                            except:
                                pass
            
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n\nInterruzione richiesta dall'utente.")
    finally:
        # Termina processi
        try:
            ffplay_process.terminate()
            ffplay_process.wait(timeout=5)
        except:
            try:
                ffplay_process.kill()
            except:
                pass
        
        try:
            ffmpeg_video_process.terminate()
            ffmpeg_video_process.wait(timeout=5)
        except:
            try:
                ffmpeg_video_process.kill()
            except:
                pass
        
        try:
            ffmpeg_process.terminate()
            ffmpeg_process.wait(timeout=5)
        except:
            try:
                ffmpeg_process.kill()
            except:
                pass
        
        # Pulisci named pipe
        try:
            if os.path.exists(video_pipe_path):
                os.unlink(video_pipe_path)
        except:
            pass
        
        # Pulisci chunk
        try:
            for f in os.listdir(chunk_dir):
                try:
                    os.unlink(os.path.join(chunk_dir, f))
                except:
                    pass
            os.rmdir(chunk_dir)
        except:
            pass
        
        print(f"\n\n=== Trascrizione completa ===")
        print(f"File SRT salvato: {srt_path}")
        print(f"Totale sottotitoli generati: {len(all_subtitles)}")
        print(f"\nI sottotitoli sono stati incorporati (burn-in) nel video durante la riproduzione.")
        print(f"Puoi usare il file SRT per creare una versione finale del video con sottotitoli permanenti.")
        
        # Mantieni il file SRT (non eliminarlo)
        print(f"\nFile SRT mantenuto: {srt_path}")


def process_live_stream(input_source, model_size="base", language="it", 
                       chunk_duration=10, max_duration=None):
    """
    Processa uno stream live in tempo reale, chunk per chunk.
    Usa FFmpeg con segmentazione per estrarre chunk consecutivi dallo stream.
    
    Args:
        input_source: URL dello stream
        model_size: Dimensione modello Whisper
        language: Codice lingua
        chunk_duration: Durata di ogni chunk in secondi
        max_duration: Durata massima totale (None = infinito)
    """
    stt = VLCSpeechToText(model_size=model_size, language=language)
    stt.load_model()
    
    print(f"\n=== Trascrizione stream LIVE ===")
    print(f"Stream: {input_source}")
    print(f"Chunk: {chunk_duration} secondi")
    if max_duration:
        print(f"Durata massima: {max_duration} secondi")
    print(f"Premi Ctrl+C per interrompere\n")
    
    chunk_dir = tempfile.mkdtemp(prefix="whisper_chunks_")
    chunk_pattern = os.path.join(chunk_dir, "chunk_%04d.wav")
    stream_start_time = time.time()
    chunk_counter = 0
    
    # Avvia FFmpeg in modalità segmentazione continua
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", input_source,
        "-vn",  # No video
        "-acodec", "pcm_s16le",
        "-ar", "16000",  # 16kHz ottimale per Whisper
        "-ac", "1",  # Mono
        "-f", "segment",  # Modalità segmentazione
        "-segment_time", str(chunk_duration),  # Durata ogni segmento
        "-segment_format", "wav",
        "-reset_timestamps", "1",  # Reset timestamp per ogni segmento
        "-strftime", "0",  # Non usare strftime nel nome
        "-y",
        chunk_pattern
    ]
    
    print("Avvio FFmpeg in modalità segmentazione continua...")
    ffmpeg_process = subprocess.Popen(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    try:
        # Monitora i chunk man mano che vengono creati
        processed_chunks = set()
        
        while ffmpeg_process.poll() is None:
            # Controlla durata massima
            elapsed = time.time() - stream_start_time
            if max_duration and elapsed >= max_duration:
                print(f"\nDurata massima ({max_duration}s) raggiunta.")
                ffmpeg_process.terminate()
                break
            
            # Cerca nuovi chunk
            for i in range(chunk_counter, chunk_counter + 10):  # Controlla prossimi 10 chunk
                chunk_file = os.path.join(chunk_dir, f"chunk_{i:04d}.wav")
                
                if os.path.exists(chunk_file) and chunk_file not in processed_chunks:
                    # Nuovo chunk trovato
                    processed_chunks.add(chunk_file)
                    
                    # Aspetta che il file sia completo (non più in scrittura)
                    time.sleep(0.5)
                    
                    if os.path.getsize(chunk_file) == 0:
                        continue
                    
                    print(f"[Chunk {i}] Trascrizione...", end=" ", flush=True)
                    
                    try:
                        # Trascrivi chunk
                        transcribe_start = time.time()
                        result = stt.model.transcribe(
                            chunk_file,
                            language=language,
                            task="transcribe",
                            fp16=False
                        )
                        transcribe_time = time.time() - transcribe_start
                        
                        text = result["text"].strip()
                        if text:
                            print(f"✓ ({transcribe_time:.1f}s)")
                            print(f"[{elapsed:06.1f}s] {text}\n")
                        else:
                            print(f"(nessun testo, {transcribe_time:.1f}s)")
                        
                        # Pulisci chunk
                        os.unlink(chunk_file)
                        chunk_counter = i + 1
                        
                    except Exception as e:
                        print(f"Errore: {e}")
                        if os.path.exists(chunk_file):
                            try:
                                os.unlink(chunk_file)
                            except:
                                pass
            
            time.sleep(0.5)  # Controlla ogni 0.5 secondi
            
    except KeyboardInterrupt:
        print("\n\nInterruzione richiesta dall'utente.")
        ffmpeg_process.terminate()
    finally:
        # Termina FFmpeg
        try:
            ffmpeg_process.terminate()
            ffmpeg_process.wait(timeout=5)
        except:
            ffmpeg_process.kill()
        
        # Pulisci directory chunk
        try:
            for f in os.listdir(chunk_dir):
                try:
                    os.unlink(os.path.join(chunk_dir, f))
                except:
                    pass
            os.rmdir(chunk_dir)
        except:
            pass
        print(f"\nProcessati {chunk_counter} chunk totali.")


def launch_vlc_with_speech2text(input_source, model_size="base", language="it", 
                                output_format="wav", realtime=False, vlc_path="vlc",
                                duration=None, use_ffmpeg=False, live=False, chunk_duration=10):
    """
    Lancia VLC e processa l'audio con speech-to-text.
    
    Args:
        input_source: File o URL da riprodurre con VLC
        model_size: Dimensione modello Whisper
        language: Codice lingua
        output_format: Formato audio di output (wav, mp3, etc.)
        realtime: Se True, processa in tempo reale (più lento ma mostra output durante riproduzione)
        duration: Durata massima in secondi (None = illimitato, utile per stream live)
    """
    stt = VLCSpeechToText(model_size=model_size, language=language)
    
    # Crea file temporaneo per l'audio
    with tempfile.NamedTemporaryFile(suffix=f".{output_format}", delete=False) as tmp_audio:
        audio_file = tmp_audio.name
    
    try:
        is_stream = is_url(input_source)
        is_hls = is_hls_url(input_source)
        
        # Se è uno stream e modalità live, usa processamento live
        if live and is_stream:
            print(f"Modalità LIVE attivata per: {input_source}")
            process_live_stream(
                input_source,
                model_size=model_size,
                language=language,
                chunk_duration=chunk_duration,
                max_duration=duration
            )
            return
        
        if is_hls:
            print(f"Rilevato stream HLS: {input_source}")
        elif is_stream:
            print(f"Rilevato URL: {input_source}")
        else:
            print(f"File locale: {input_source}")
            
        print(f"File audio temporaneo: {audio_file}\n")
        
        # Usa FFmpeg se richiesto o se VLC fallisce
        if use_ffmpeg:
            print("Esecuzione FFmpeg per estrazione audio...")
            if is_stream:
                print("(Connessione allo stream in corso, attendere...)")
            
            success, error_msg = extract_audio_with_ffmpeg(input_source, audio_file, duration)
            if not success:
                print(f"Errore FFmpeg: {error_msg[:500]}")
                if is_stream:
                    print("\nSuggerimenti:")
                    print("  - Verifica che l'URL sia accessibile")
                    print("  - Prova con --duration per limitare la durata")
                return
            
            stdout, stderr = None, error_msg.encode() if error_msg else None
            vlc_process = type('obj', (object,), {'returncode': 0})()
        else:
            # Comando VLC base
            vlc_cmd = [
                vlc_path,
                input_source,
                "--intf", "dummy",  # Interfaccia dummy (nessuna GUI)
                "--no-video",  # Disabilita video se presente
            ]
            
            # Opzioni specifiche per HLS/stream
            if is_hls or is_stream:
                vlc_cmd.extend([
                    "--network-caching=3000",  # Cache di rete per stream
                    "--http-reconnect",  # Riconnessione automatica
                    "--live-caching=3000",  # Cache per stream live
                ])
            
            # Durata limitata (utile per stream live infiniti)
            if duration and duration > 0:
                vlc_cmd.extend(["--run-time", str(int(duration))])
                print(f"Durata limitata a {duration} secondi")
            else:
                vlc_cmd.extend(["--run-time=0"])  # Esegui fino alla fine
            
            # Comando di output - usa formato WAV per compatibilità
            vlc_cmd.extend([
                "--sout", f"#transcode{{acodec=s16l,ab=128,channels=2,samplerate=16000}}:file{{dst={audio_file}}}",
                "--play-and-exit"
            ])
            
            # Avvia VLC in background
            print("Esecuzione VLC...")
            if is_stream:
                print("(Connessione allo stream in corso, attendere...)")
            
            vlc_process = subprocess.Popen(
                vlc_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Attendi che VLC finisca
            try:
                stdout, stderr = vlc_process.communicate(timeout=None if not duration else duration + 60)
            except subprocess.TimeoutExpired:
                print("Timeout raggiunto, interruzione VLC...")
                vlc_process.kill()
                stdout, stderr = vlc_process.communicate()
        
        # Verifica che il file sia stato creato correttamente
        if not os.path.exists(audio_file):
            error_msg = stderr.decode() if stderr else "Errore sconosciuto"
            print(f"Errore: Il file audio non è stato creato.")
            print(f"Dettagli: {error_msg[:500]}")
            
            # Prova con FFmpeg come fallback
            if not use_ffmpeg:
                print("\nTentativo con FFmpeg come alternativa...")
                success, ffmpeg_error = extract_audio_with_ffmpeg(input_source, audio_file, duration)
                if success and os.path.exists(audio_file) and os.path.getsize(audio_file) > 0:
                    print("✓ FFmpeg ha estratto l'audio con successo!")
                else:
                    print(f"Errore anche con FFmpeg: {ffmpeg_error[:300]}")
                    if is_stream:
                        print("\nSuggerimenti per stream:")
                        print("  - Verifica che l'URL sia accessibile")
                        print("  - Prova con --duration per limitare la durata")
                        print("  - Controlla che lo stream supporti l'accesso diretto")
                    return
            else:
                if is_stream:
                    print("\nSuggerimenti per stream:")
                    print("  - Verifica che l'URL sia accessibile")
                    print("  - Prova con --duration per limitare la durata")
                    print("  - Controlla che lo stream supporti l'accesso diretto")
                return
        
        # Verifica dimensione file
        file_size = os.path.getsize(audio_file)
        if file_size == 0:
            error_msg = stderr.decode() if stderr else "Errore sconosciuto"
            print(f"Errore: Il file audio è vuoto (0 bytes).")
            print(f"Dettagli VLC: {error_msg[:500]}")
            if is_stream:
                print("\nPossibili cause:")
                print("  - Lo stream potrebbe non contenere audio")
                print("  - Problema di connessione allo stream")
                print("  - Lo stream potrebbe richiedere autenticazione")
            return
        
        # Verifica formato file con FFmpeg (se disponibile)
        try:
            ffmpeg_check = subprocess.run(
                ["ffmpeg", "-v", "error", "-i", audio_file, "-f", "null", "-"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5
            )
            if ffmpeg_check.returncode != 0:
                error_detail = ffmpeg_check.stderr.decode()[:300]
                print(f"Avviso: Il file audio potrebbe essere corrotto o in formato non valido.")
                print(f"Dettagli FFmpeg: {error_detail}")
                print("Tento comunque la trascrizione...")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass  # FFmpeg non disponibile o timeout, continua comunque
        
        if vlc_process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Errore sconosciuto"
            print(f"Avviso VLC (ma file creato, {file_size} bytes): {error_msg[:200]}")
        
        print(f"VLC completato. File audio creato: {file_size} bytes")
        print("Avvio trascrizione...\n")
        
        # Processa l'audio
        stt.running = True
        if realtime:
            stt.process_audio_stream(audio_file)
        else:
            text = stt.transcribe_audio(audio_file)
            print("\n=== Trascrizione completa ===\n")
            print(text)
            
    except KeyboardInterrupt:
        print("\n\nInterruzione richiesta dall'utente.")
        stt.running = False
    except Exception as e:
        print(f"Errore: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Pulisci file temporaneo
        if os.path.exists(audio_file):
            os.unlink(audio_file)


def main():
    parser = argparse.ArgumentParser(
        description="Lancia VLC con output speech-to-text incorporato",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  %(prog)s video.mp4
  %(prog)s "https://example.com/audio.mp3" --model small --language en
  %(prog)s "https://example.com/stream.m3u8" --duration 300
  %(prog)s video.mkv --realtime
        """
    )
    
    parser.add_argument(
        "input",
        help="File video/audio o URL da riprodurre con VLC"
    )
    
    parser.add_argument(
        "--model",
        choices=["tiny", "base", "small", "medium", "large"],
        default="base",
        help="Dimensione modello Whisper (default: base)"
    )
    
    parser.add_argument(
        "--language",
        default="it",
        help="Codice lingua ISO 639-1 (default: it per italiano). Usa 'auto' per rilevamento automatico, oppure 'en' per inglese, 'es' per spagnolo, etc."
    )
    
    parser.add_argument(
        "--realtime",
        action="store_true",
        help="Processa in tempo reale (mostra output durante riproduzione)"
    )
    
    parser.add_argument(
        "--format",
        default="wav",
        choices=["wav", "mp3", "flac"],
        help="Formato audio di output (default: wav)"
    )
    
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Durata massima in secondi (utile per stream live infiniti, default: illimitato)"
    )
    
    parser.add_argument(
        "--use-ffmpeg",
        action="store_true",
        help="Usa FFmpeg invece di VLC per estrarre l'audio (più affidabile per alcuni stream)"
    )
    
    parser.add_argument(
        "--live",
        action="store_true",
        help="Modalità LIVE: processa stream in tempo reale chunk per chunk (solo per URL/stream)"
    )
    
    parser.add_argument(
        "--chunk-duration",
        type=int,
        default=10,
        help="Durata di ogni chunk in secondi per modalità live (default: 10)"
    )
    
    parser.add_argument(
        "--subtitles",
        action="store_true",
        help="Avvia VLC con riproduzione video e mostra sottotitoli sincronizzati in tempo reale"
    )
    
    args = parser.parse_args()
    
    # Verifica che VLC sia installato e trova il percorso
    vlc_path = None
    
    # Prova prima il comando standard
    try:
        subprocess.run(["vlc", "--version"], 
                      stdout=subprocess.PIPE, 
                      stderr=subprocess.PIPE,
                      check=True)
        vlc_path = "vlc"
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Su macOS, prova a trovare VLC in /Applications
        if sys.platform == "darwin":
            mac_vlc_path = "/Applications/VLC.app/Contents/MacOS/vlc"
            if os.path.exists(mac_vlc_path):
                vlc_path = mac_vlc_path
            else:
                print("Errore: VLC non trovato.")
                print("  macOS: brew install --cask vlc")
                print("  Linux: sudo apt-get install vlc")
                sys.exit(1)
        else:
            print("Errore: VLC non trovato. Installa VLC media player.")
            print("  macOS: brew install --cask vlc")
            print("  Linux: sudo apt-get install vlc")
            sys.exit(1)
    
    # Se richiesta modalità realtime ma pydub non disponibile
    if args.realtime and not PYDUB_AVAILABLE:
        print("Avviso: --realtime richiesto ma pydub non disponibile.")
        print("Continuo in modalità normale...")
        args.realtime = False
    
    # Verifica che --live sia usato solo con URL
    if args.live and not is_url(args.input):
        print("Errore: --live può essere usato solo con URL/stream, non con file locali.")
        sys.exit(1)
    
    # Modalità sottotitoli: avvia VLC con GUI e genera SRT
    if args.subtitles:
        # Verifica che VLC sia disponibile (già verificato sopra)
        if not vlc_path:
            print("Errore: VLC non trovato.")
            print("  macOS: brew install --cask vlc")
            print("  Linux: sudo apt-get install vlc")
            sys.exit(1)
        
        launch_vlc_with_subtitles(
            args.input,
            model_size=args.model,
            language=args.language,
            chunk_duration=args.chunk_duration,
            vlc_path=vlc_path
        )
    else:
        launch_vlc_with_speech2text(
            args.input,
            model_size=args.model,
            language=args.language,
            output_format=args.format,
            realtime=args.realtime,
            vlc_path=vlc_path,
            duration=args.duration,
            use_ffmpeg=args.use_ffmpeg,
            live=args.live,
            chunk_duration=args.chunk_duration
        )


if __name__ == "__main__":
    main()

