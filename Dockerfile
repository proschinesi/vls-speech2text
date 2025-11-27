FROM ubuntu:22.04

# Evita prompt interattivi durante apt-get
ENV DEBIAN_FRONTEND=noninteractive

# Installa dipendenze sistema e build tools
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    build-essential \
    cmake \
    pkg-config \
    git \
    yasm \
    nasm \
    autoconf \
    automake \
    libtool \
    libass-dev \
    libfreetype6-dev \
    libgnutls28-dev \
    libmp3lame-dev \
    libsdl2-dev \
    libva-dev \
    libvdpau-dev \
    libvorbis-dev \
    libxcb1-dev \
    libxcb-shm0-dev \
    libxcb-xfixes0-dev \
    meson \
    ninja-build \
    wget \
    curl \
    zlib1g-dev \
    libbz2-dev \
    && rm -rf /var/lib/apt/lists/*

# Compila x264 (richiesto da FFmpeg)
WORKDIR /tmp
RUN git clone https://code.videolan.org/videolan/x264.git && \
    cd x264 && \
    ./configure --prefix=/usr/local --enable-shared --disable-cli && \
    make -j$(nproc) && \
    make install && \
    ldconfig && \
    echo "✓ x264 compilato"

# Compila x265 (richiesto da FFmpeg)
WORKDIR /tmp
RUN git clone https://bitbucket.org/multicoreware/x265_git.git x265 && \
    cd x265/build/linux && \
    cmake -G "Unix Makefiles" -DCMAKE_INSTALL_PREFIX=/usr/local ../../source && \
    make -j$(nproc) && \
    make install && \
    ldconfig && \
    echo "✓ x265 compilato"

# Compila whisper.cpp
WORKDIR /tmp
RUN git clone https://github.com/ggerganov/whisper.cpp.git && \
    cd whisper.cpp && \
    make && \
    echo "✓ whisper.cpp compilato"

# Compila FFmpeg 8.0 con Whisper
WORKDIR /tmp/ffmpeg_build
RUN git clone --depth 1 https://git.ffmpeg.org/ffmpeg.git && \
    cd ffmpeg && \
    git fetch --tags && \
    (git checkout -f release/8.0 2>/dev/null || git checkout -f n8.0 2>/dev/null || git checkout -f master || echo "Usando branch corrente") && \
    echo "Configurazione FFmpeg..." && \
    ./configure \
        --enable-libwhisper \
        --extra-cflags="-I/tmp/whisper.cpp" \
        --extra-ldflags="-L/tmp/whisper.cpp -lwhisper" \
        --enable-libass \
        --enable-libfreetype \
        --enable-libmp3lame \
        --enable-libvorbis \
        --enable-libx264 \
        --enable-libx265 \
        --enable-nonfree \
        --enable-shared \
        --enable-pic \
        --prefix=/usr/local 2>&1 | tee /tmp/ffmpeg_configure.log && \
    echo "Compilazione FFmpeg (questo richiede tempo)..." && \
    make -j$(nproc) 2>&1 | tee /tmp/ffmpeg_make.log && \
    echo "Installazione FFmpeg..." && \
    make install && \
    ldconfig && \
    echo "✓ FFmpeg con Whisper compilato e installato"

# Verifica FFmpeg e mostra log se ci sono problemi
RUN echo "Verifica FFmpeg..." && \
    /usr/local/bin/ffmpeg -version && \
    echo "Verifica filtro Whisper..." && \
    (/usr/local/bin/ffmpeg -filters 2>&1 | grep -i whisper && echo "✓ FFmpeg con Whisper verificato") || \
    (echo "⚠ Filtro Whisper non trovato, mostro log:" && cat /tmp/ffmpeg_configure.log /tmp/ffmpeg_make.log && exit 1)

# Setup applicazione
WORKDIR /app

# Copia requirements e installa dipendenze Python
COPY requirements.txt .
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt

# Copia tutto il codice
COPY . .

# Crea wrapper script per FFmpeg (come su prem)
RUN echo '#!/bin/bash\n/usr/local/bin/ffmpeg "$@"' > ffmpeg_whisper_wrapper.sh && \
    chmod +x ffmpeg_whisper_wrapper.sh

# Crea directory per modelli Whisper
RUN mkdir -p /root/.cache/whisper

# Esponi porta (Railway userà PORT da environment)
EXPOSE 8080

# Crea script di avvio che gestisce PORT
RUN echo '#!/bin/bash' > /app/start.sh && \
    echo 'exec python3 web_app_simple.py --host 0.0.0.0 --port ${PORT:-8080}' >> /app/start.sh && \
    chmod +x /app/start.sh

# Avvia applicazione
CMD ["/bin/bash", "/app/start.sh"]

