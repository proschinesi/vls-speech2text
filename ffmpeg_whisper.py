#!/usr/bin/env python3
"""
Script per utilizzare FFmpeg 8.0 con il filtro Whisper integrato per la trascrizione automatica.
Basato su: https://www.phoronix.com/news/FFmpeg-Lands-Whisper

Requisiti:
- FFmpeg 8.0+ compilato con --enable-whisper
- Libreria Whisper.cpp installata sul sistema
"""

import subprocess
import sys
import os
import argparse
import json
import tempfile
import re
import time
from pathlib import Path


def check_ffmpeg_whisper_support():
    """Verifica se FFmpeg ha il supporto per il filtro Whisper."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-filters"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        
        # Cerca il filtro whisper nell'output
        output = result.stdout + result.stderr
        if "whisper" in output.lower():
            return True, "Filtro Whisper trovato"
        else:
            return False, "Filtro Whisper non trovato. FFmpeg potrebbe non essere compilato con --enable-whisper"
    except FileNotFoundError:
        return False, "FFmpeg non trovato. Installa FFmpeg 8.0+ con supporto Whisper"
    except subprocess.TimeoutExpired:
        return False, "Timeout durante verifica FFmpeg"
    except Exception as e:
        return False, f"Errore durante verifica: {e}"


def check_ffmpeg_version():
    """Verifica la versione di FFmpeg."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        output = result.stdout + result.stderr
        # Estrai versione
        for line in output.split('\n'):
            if 'ffmpeg version' in line.lower():
                return True, line.strip()
        return True, "FFmpeg trovato (versione non determinata)"
    except FileNotFoundError:
        return False, "FFmpeg non trovato"
    except Exception as e:
        return False, f"Errore: {e}"


def format_srt_time(seconds):
    """Converte secondi in formato SRT (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def parse_whisper_output(output_text, output_format="srt"):
    """
    Analizza l'output di FFmpeg Whisper e converte in formato richiesto.
    
    FFmpeg Whisper può generare output in vari formati. Questa funzione
    cerca di estrarre le informazioni dalla stderr di FFmpeg.
    """
    # L'output di Whisper viene tipicamente stampato su stderr
    # Il formato esatto dipende da come FFmpeg implementa il filtro
    # FFmpeg Whisper potrebbe generare direttamente SRT o richiedere parsing
    lines = output_text.split('\n')
    
    if output_format == "json":
        # Cerca JSON nell'output
        json_data = []
        for line in lines:
            line = line.strip()
            if line.startswith('{') or line.startswith('['):
                try:
                    data = json.loads(line)
                    json_data.append(data)
                except:
                    pass
        
        if json_data:
            return json.dumps(json_data, indent=2, ensure_ascii=False)
        return json.dumps([], indent=2)
    
    elif output_format == "srt":
        # Cerca timestamp e testo nell'output
        # Questo è un parser generico - potrebbe dover essere adattato
        # in base al formato esatto dell'output di FFmpeg Whisper
        srt_lines = []
        subtitle_index = 1
        
        # Pattern comune: [timestamp] testo
        pattern = r'\[?(\d+):(\d+):(\d+)[.,](\d+)\]?\s+(.+)'
        
        for line in lines:
            match = re.search(pattern, line)
            if match:
                hours, minutes, seconds, millis, text = match.groups()
                start_time = int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000.0
                end_time = start_time + 5.0  # Default 5 secondi (dovrebbe essere calcolato)
                
                srt_lines.append(f"{subtitle_index}")
                srt_lines.append(f"{format_srt_time(start_time)} --> {format_srt_time(end_time)}")
                srt_lines.append(text.strip())
                srt_lines.append("")
                subtitle_index += 1
        
        if srt_lines:
            return "\n".join(srt_lines)
        
        # Fallback: se non troviamo pattern, restituiamo l'output grezzo
        return output_text
    
    else:  # text
        # Estrai solo il testo
        text_lines = []
        for line in lines:
            # Rimuovi timestamp e formattazione
            line = re.sub(r'\[?\d+:\d+:\d+[.,]\d+\]?\s*', '', line).strip()
            if line and not line.startswith('[') and not line.startswith('{'):
                text_lines.append(line)
        
        return "\n".join(text_lines)


def is_url(source):
    """Verifica se l'input è un URL."""
    return source.startswith(("http://", "https://", "rtsp://", "rtmp://", "mms://", "udp://", "tcp://"))


def transcribe_with_ffmpeg_whisper(
    input_source,
    output_file=None,
    model="base",
    language="it",
    output_format="srt",
    gpu=False,
    http_endpoint=None,
    duration=None
):
    """
    Trascrive audio/video usando FFmpeg con filtro Whisper.
    
    Args:
        input_source: File o URL da trascrivere
        output_file: File di output (None = stdout)
        model: Modello Whisper (tiny, base, small, medium, large)
        language: Codice lingua ISO 639-1
        output_format: Formato output (srt, json, txt)
        gpu: Usa accelerazione GPU se disponibile
        http_endpoint: URL HTTP per inviare output JSON
        duration: Durata massima in secondi
    """
    
    # Costruisci comando FFmpeg
    ffmpeg_cmd = ["ffmpeg"]
    
    # Input
    ffmpeg_cmd.extend(["-i", input_source])
    
    # Durata limitata
    if duration and duration > 0:
        ffmpeg_cmd.extend(["-t", str(int(duration))])
    
    # Filtro Whisper
    # Nota: La sintassi esatta può variare in base all'implementazione
    # FFmpeg Whisper potrebbe usare parametri diversi
    whisper_filter = f"whisper=model={model}"
    
    if language:
        whisper_filter += f":language={language}"
    
    if gpu:
        whisper_filter += ":gpu=1"
    
    # Se http_endpoint è specificato, invia JSON via HTTP
    if http_endpoint and output_format == "json":
        whisper_filter += f":output={http_endpoint}"
    
    # Applica filtro audio
    ffmpeg_cmd.extend(["-af", whisper_filter])
    
    # Per Whisper, l'output della trascrizione potrebbe essere su stderr
    # o richiedere un formato specifico. Proviamo diversi approcci:
    
    # Se output_format è json e c'è un endpoint HTTP, non serve file output
    if http_endpoint and output_format == "json":
        ffmpeg_cmd.extend(["-f", "null", "-"])  # Nessun output file
    elif output_format == "srt":
        # FFmpeg Whisper potrebbe generare SRT direttamente o richiedere formato specifico
        # Proviamo prima senza specificare formato, poi con srt
        ffmpeg_cmd.extend(["-f", "srt"])
    elif output_format == "json":
        # Per JSON, potrebbe essere necessario un formato specifico
        ffmpeg_cmd.extend(["-f", "json"])
    else:  # txt
        ffmpeg_cmd.extend(["-f", "null", "-"])  # Nessun output audio/video
    
    if output_file:
        ffmpeg_cmd.append(output_file)
    else:
        if output_format != "txt":
            # Se non specificato, genera nome file automatico
            input_path = Path(input_source)
            if input_path.exists():
                base_name = input_path.stem
            else:
                base_name = "output"
            output_file = f"{base_name}.{output_format}"
            ffmpeg_cmd.append(output_file)
        else:
            ffmpeg_cmd.append("-")  # stdout per testo
    
    # Nota: output_file potrebbe essere stato generato automaticamente sopra
    print(f"Esecuzione: {' '.join(ffmpeg_cmd)}")
    print(f"Input: {input_source}")
    print(f"Modello: {model}, Lingua: {language}")
    if output_file:
        print(f"Output: {output_file}")
    print()
    
    try:
        # Esegui FFmpeg
        # Nota: Whisper output viene tipicamente su stderr
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        # Leggi output in tempo reale
        stdout_lines = []
        stderr_lines = []
        
        # Leggi da entrambi i stream
        import threading
        
        def read_stream(stream, lines_list):
            for line in stream:
                lines_list.append(line)
                # Mostra progresso in tempo reale
                if "whisper" in line.lower() or "transcribe" in line.lower():
                    print(line.strip(), flush=True)
        
        stdout_thread = threading.Thread(
            target=read_stream,
            args=(process.stdout, stdout_lines),
            daemon=True
        )
        stderr_thread = threading.Thread(
            target=read_stream,
            args=(process.stderr, stderr_lines),
            daemon=True
        )
        
        stdout_thread.start()
        stderr_thread.start()
        
        # Attendi completamento
        returncode = process.wait()
        
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)
        
        stdout_text = "".join(stdout_lines)
        stderr_text = "".join(stderr_lines)
        
        # L'output di Whisper potrebbe essere su stdout o stderr
        # a seconda dell'implementazione
        output_text = stdout_text if stdout_text else stderr_text
        
        if returncode != 0:
            print(f"\nErrore FFmpeg (codice {returncode}):")
            error_output = stderr_text[-2000:] if len(stderr_text) > 2000 else stderr_text
            print(error_output)
            
            # Suggerimenti per errori comuni
            if "whisper" in stderr_text.lower() and "not found" in stderr_text.lower():
                print("\n💡 Suggerimento: Il filtro Whisper potrebbe non essere disponibile.")
                print("   Verifica che FFmpeg sia compilato con --enable-whisper")
            elif "model" in stderr_text.lower():
                print("\n💡 Suggerimento: Il modello Whisper potrebbe non essere disponibile.")
                print("   Verifica che i modelli Whisper siano installati correttamente")
            
            return False, stderr_text
        
        # Se output_file è stato generato automaticamente, verifica che esista
        if output_file and os.path.exists(output_file):
            file_size = os.path.getsize(output_file)
            if file_size > 0:
                print(f"\n✓ File generato: {output_file} ({file_size} bytes)")
            else:
                print(f"\n⚠ Avviso: File {output_file} è vuoto")
                # L'output potrebbe essere su stderr invece che nel file
                if stderr_text:
                    print("\nOutput su stderr:")
                    print(stderr_text[-500:])
        elif not output_file and output_format == "txt":
            # Processa output per formato testo
            processed_output = parse_whisper_output(output_text, output_format)
            print("\n=== Trascrizione ===\n")
            print(processed_output)
        
        return True, output_text
        
    except KeyboardInterrupt:
        print("\n\nInterruzione richiesta dall'utente.")
        process.terminate()
        return False, "Interrotto dall'utente"
    except Exception as e:
        return False, f"Errore durante trascrizione: {e}"


def process_live_stream_ffmpeg_whisper(
    input_source,
    model="base",
    language="it",
    output_format="srt",
    gpu=False,
    chunk_duration=10,
    max_duration=None,
    output_file=None
):
    """
    Processa uno stream live in tempo reale usando FFmpeg Whisper chunk per chunk.
    
    Args:
        input_source: URL dello stream
        model: Modello Whisper
        language: Codice lingua
        output_format: Formato output (srt, json, txt)
        gpu: Usa accelerazione GPU
        chunk_duration: Durata di ogni chunk in secondi
        max_duration: Durata massima totale (None = infinito)
        output_file: File di output per accumulare risultati
    """
    print(f"\n=== Trascrizione stream LIVE con FFmpeg Whisper ===")
    print(f"Stream: {input_source}")
    print(f"Modello: {model}, Lingua: {language}")
    print(f"Chunk: {chunk_duration} secondi")
    if max_duration:
        print(f"Durata massima: {max_duration} secondi")
    print(f"Premi Ctrl+C per interrompere\n")
    
    chunk_dir = tempfile.mkdtemp(prefix="ffmpeg_whisper_chunks_")
    chunk_pattern = os.path.join(chunk_dir, "chunk_%04d.wav")
    stream_start_time = time.time()
    chunk_counter = 0
    all_subtitles = []  # Accumula tutti i sottotitoli
    subtitle_index = 1
    
    # Avvia FFmpeg in modalità segmentazione continua
    ffmpeg_segment_cmd = [
        "ffmpeg",
        "-i", input_source,
        "-vn",  # No video
        "-acodec", "pcm_s16le",
        "-ar", "16000",  # 16kHz ottimale per Whisper
        "-ac", "1",  # Mono
        "-f", "segment",  # Modalità segmentazione
        "-segment_time", str(chunk_duration),
        "-segment_format", "wav",
        "-reset_timestamps", "1",
        "-strftime", "0",
        "-y",
        chunk_pattern
    ]
    
    print("Avvio FFmpeg in modalità segmentazione continua...")
    ffmpeg_process = subprocess.Popen(
        ffmpeg_segment_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Prepara file di output se specificato
    if output_file:
        # Crea file vuoto iniziale
        with open(output_file, 'w', encoding='utf-8') as f:
            if output_format == "srt":
                f.write("")
            elif output_format == "json":
                f.write("[]")
            else:
                f.write("")
        print(f"Output: {output_file}")
    
    try:
        processed_chunks = set()
        
        while ffmpeg_process.poll() is None:
            # Controlla durata massima
            elapsed = time.time() - stream_start_time
            if max_duration and elapsed >= max_duration:
                print(f"\nDurata massima ({max_duration}s) raggiunta.")
                ffmpeg_process.terminate()
                break
            
            # Cerca nuovi chunk
            for i in range(chunk_counter, chunk_counter + 10):
                chunk_file = os.path.join(chunk_dir, f"chunk_{i:04d}.wav")
                
                if os.path.exists(chunk_file) and chunk_file not in processed_chunks:
                    processed_chunks.add(chunk_file)
                    time.sleep(0.5)  # Aspetta che il file sia completo
                    
                    if os.path.getsize(chunk_file) == 0:
                        continue
                    
                    print(f"[Chunk {i}] Trascrizione...", end=" ", flush=True)
                    
                    # Trascrivi chunk usando FFmpeg Whisper
                    chunk_start_time = i * chunk_duration
                    chunk_end_time = (i + 1) * chunk_duration
                    
                    # Crea file temporaneo per output chunk
                    chunk_output = tempfile.NamedTemporaryFile(
                        mode='w',
                        suffix=f'.{output_format}',
                        delete=False
                    )
                    chunk_output.close()
                    
                    try:
                        transcribe_start = time.time()
                        success, result = transcribe_with_ffmpeg_whisper(
                            input_source=chunk_file,
                            output_file=chunk_output.name,
                            model=model,
                            language=language,
                            output_format=output_format,
                            gpu=gpu,
                            duration=None
                        )
                        transcribe_time = time.time() - transcribe_start
                        
                        if success and os.path.exists(chunk_output.name):
                            # Leggi risultato
                            with open(chunk_output.name, 'r', encoding='utf-8') as f:
                                chunk_result = f.read()
                            
                            if chunk_result.strip():
                                if output_format == "srt":
                                    # Parse SRT e aggiungi timestamp corretti
                                    lines = chunk_result.strip().split('\n')
                                    # Estrai testo dai sottotitoli
                                    text_lines = []
                                    for line in lines:
                                        if line and not line.strip().isdigit() and '-->' not in line:
                                            text_lines.append(line.strip())
                                    
                                    text = ' '.join(text_lines)
                                    if text:
                                        subtitle = {
                                            'index': subtitle_index,
                                            'start': chunk_start_time,
                                            'end': chunk_end_time,
                                            'text': text
                                        }
                                        all_subtitles.append(subtitle)
                                        
                                        # Aggiorna file output
                                        if output_file:
                                            with open(output_file, 'w', encoding='utf-8') as f:
                                                for sub in all_subtitles:
                                                    f.write(f"{sub['index']}\n")
                                                    f.write(f"{format_srt_time(sub['start'])} --> {format_srt_time(sub['end'])}\n")
                                                    f.write(f"{sub['text']}\n\n")
                                        
                                        print(f"✓ ({transcribe_time:.1f}s) - {text[:60]}...")
                                        subtitle_index += 1
                                    else:
                                        print(f"(nessun testo, {transcribe_time:.1f}s)")
                                elif output_format == "json":
                                    # Aggiungi timestamp e aggiungi a JSON
                                    try:
                                        chunk_data = json.loads(chunk_result)
                                        if isinstance(chunk_data, list):
                                            for item in chunk_data:
                                                item['start'] = chunk_start_time
                                                item['end'] = chunk_end_time
                                        else:
                                            chunk_data['start'] = chunk_start_time
                                            chunk_data['end'] = chunk_end_time
                                            chunk_data = [chunk_data]
                                        
                                        all_subtitles.extend(chunk_data if isinstance(chunk_data, list) else [chunk_data])
                                        
                                        # Aggiorna file JSON
                                        if output_file:
                                            with open(output_file, 'w', encoding='utf-8') as f:
                                                json.dump(all_subtitles, f, indent=2, ensure_ascii=False)
                                        
                                        print(f"✓ ({transcribe_time:.1f}s)")
                                    except json.JSONDecodeError:
                                        print(f"(errore parsing JSON, {transcribe_time:.1f}s)")
                                else:  # txt
                                    if chunk_result.strip():
                                        print(f"✓ ({transcribe_time:.1f}s)")
                                        print(f"[{chunk_start_time:06.1f}s] {chunk_result.strip()[:80]}...")
                                        
                                        # Aggiungi a file output
                                        if output_file:
                                            with open(output_file, 'a', encoding='utf-8') as f:
                                                f.write(f"[{chunk_start_time:06.1f}s] {chunk_result.strip()}\n")
                            else:
                                print(f"(nessun testo, {transcribe_time:.1f}s)")
                        else:
                            print(f"(errore, {transcribe_time:.1f}s)")
                        
                        # Pulisci chunk e output temporaneo
                        if os.path.exists(chunk_file):
                            os.unlink(chunk_file)
                        if os.path.exists(chunk_output.name):
                            os.unlink(chunk_output.name)
                        chunk_counter = i + 1
                        
                    except Exception as e:
                        print(f"Errore: {e}")
                        if os.path.exists(chunk_file):
                            try:
                                os.unlink(chunk_file)
                            except:
                                pass
                        if os.path.exists(chunk_output.name):
                            try:
                                os.unlink(chunk_output.name)
                            except:
                                pass
            
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n\nInterruzione richiesta dall'utente.")
        ffmpeg_process.terminate()
    finally:
        # Termina FFmpeg
        try:
            ffmpeg_process.terminate()
            ffmpeg_process.wait(timeout=5)
        except:
            try:
                ffmpeg_process.kill()
            except:
                pass
        
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
        
        print(f"\n\n=== Trascrizione completata ===")
        print(f"Processati {chunk_counter} chunk totali")
        if output_file and os.path.exists(output_file):
            file_size = os.path.getsize(output_file)
            print(f"File salvato: {output_file} ({file_size} bytes)")
            print(f"Totale sottotitoli: {len(all_subtitles)}")


def main():
    parser = argparse.ArgumentParser(
        description="Trascrizione audio/video usando FFmpeg 8.0 con filtro Whisper integrato",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  %(prog)s video.mp4
  %(prog)s audio.mp3 --model small --language en --output subtitles.srt
  %(prog)s "https://example.com/stream.m3u8" --format json --output output.json
  %(prog)s video.mp4 --gpu --model large
  %(prog)s audio.mp3 --http-endpoint "http://localhost:8080/api/transcribe"
  %(prog)s "https://example.com/live.m3u8" --live --chunk-duration 10
  %(prog)s "https://example.com/stream.m3u8" --live --duration 300
        """
    )
    
    parser.add_argument(
        "input",
        help="File audio/video o URL da trascrivere"
    )
    
    parser.add_argument(
        "--model",
        choices=["tiny", "base", "small", "medium", "large"],
        default="base",
        help="Modello Whisper da utilizzare (default: base)"
    )
    
    parser.add_argument(
        "--language",
        default="it",
        help="Codice lingua ISO 639-1 (default: it per italiano)"
    )
    
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="File di output (default: stdout o input.srt/json/txt)"
    )
    
    parser.add_argument(
        "--format",
        choices=["srt", "json", "txt"],
        default="srt",
        help="Formato di output (default: srt)"
    )
    
    parser.add_argument(
        "--gpu",
        action="store_true",
        help="Usa accelerazione GPU se disponibile"
    )
    
    parser.add_argument(
        "--http-endpoint",
        default=None,
        help="URL HTTP per inviare output JSON (solo con --format json)"
    )
    
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Durata massima in secondi (utile per stream live)"
    )
    
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verifica solo se FFmpeg supporta Whisper e esci"
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
    
    args = parser.parse_args()
    
    # Verifica supporto Whisper
    print("Verifica supporto FFmpeg Whisper...")
    has_whisper, whisper_msg = check_ffmpeg_whisper_support()
    
    if not has_whisper:
        print(f"❌ {whisper_msg}")
        print("\nPer abilitare il supporto Whisper in FFmpeg:")
        print("1. Installa Whisper.cpp: https://github.com/ggerganov/whisper.cpp")
        print("2. Compila FFmpeg 8.0+ con: ./configure --enable-whisper")
        print("3. Oppure usa uno script alternativo che usa Python Whisper")
        sys.exit(1)
    
    print(f"✓ {whisper_msg}")
    
    # Verifica versione
    has_version, version_msg = check_ffmpeg_version()
    if has_version:
        print(f"✓ {version_msg}")
    print()
    
    if args.check:
        print("FFmpeg supporta Whisper! Puoi procedere con la trascrizione.")
        sys.exit(0)
    
    # Verifica che --live sia usato solo con URL
    if args.live and not is_url(args.input):
        print("Errore: --live può essere usato solo con URL/stream, non con file locali.")
        sys.exit(1)
    
    # Determina file di output
    output_file = args.output
    if not output_file:
        # Genera nome file basato su input e formato
        input_path = Path(args.input)
        if input_path.exists():
            base_name = input_path.stem
        else:
            base_name = "output"
        
        output_file = f"{base_name}.{args.format}"
        print(f"Output automatico: {output_file}")
    
    # Se modalità live, usa processamento chunk per chunk
    if args.live:
        process_live_stream_ffmpeg_whisper(
            input_source=args.input,
            model=args.model,
            language=args.language,
            output_format=args.format,
            gpu=args.gpu,
            chunk_duration=args.chunk_duration,
            max_duration=args.duration,
            output_file=output_file
        )
    else:
        # Esegui trascrizione normale
        success, result = transcribe_with_ffmpeg_whisper(
            input_source=args.input,
            output_file=output_file,
            model=args.model,
            language=args.language,
            output_format=args.format,
            gpu=args.gpu,
            http_endpoint=args.http_endpoint,
            duration=args.duration
        )
    
    if not args.live:
        if success:
            print(f"\n✓ Trascrizione completata!")
            if output_file and os.path.exists(output_file):
                file_size = os.path.getsize(output_file)
                print(f"  File salvato: {output_file} ({file_size} bytes)")
        else:
            print(f"\n❌ Errore durante trascrizione: {result}")
            sys.exit(1)


if __name__ == "__main__":
    main()

