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
    libass-dev \
    libfreetype6-dev \
    libgnutls28-dev \
    libmp3lame-dev \
    libsdl2-dev \
    libtool \
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
    && rm -rf /var/lib/apt/lists/*

# Compila whisper.cpp
WORKDIR /tmp
RUN git clone https://github.com/ggerganov/whisper.cpp.git && \
    cd whisper.cpp && \
    make && \
    echo "✓ whisper.cpp compilato"

# Compila FFmpeg 8.0 con Whisper
WORKDIR /tmp/ffmpeg_build
RUN git clone https://git.ffmpeg.org/ffmpeg.git && \
    cd ffmpeg && \
    git fetch && \
    (git checkout -f release/8.0 2>/dev/null || git checkout -f n8.0 2>/dev/null || echo "Usando branch corrente") && \
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
        --prefix=/usr/local && \
    make -j$(nproc) && \
    make install && \
    ldconfig && \
    echo "✓ FFmpeg con Whisper compilato e installato"

# Verifica FFmpeg
RUN /usr/local/bin/ffmpeg -version && \
    /usr/local/bin/ffmpeg -filters | grep -i whisper && \
    echo "✓ FFmpeg con Whisper verificato"

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

