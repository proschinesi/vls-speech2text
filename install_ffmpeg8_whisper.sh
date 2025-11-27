#!/bin/bash
# Script per installare FFmpeg 8.0+ con supporto Whisper su macOS

set -e  # Esci in caso di errore

echo "=========================================="
echo "Installazione FFmpeg 8.0+ con Whisper"
echo "=========================================="
echo ""

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Verifica se siamo su macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo -e "${RED}Errore: Questo script è per macOS${NC}"
    exit 1
fi

# Verifica Homebrew
if ! command -v brew &> /dev/null; then
    echo -e "${RED}Errore: Homebrew non trovato. Installa Homebrew da https://brew.sh${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Homebrew trovato${NC}"

# Directory di lavoro
BUILD_DIR="$HOME/ffmpeg_build"
FFMPEG_DIR="$BUILD_DIR/ffmpeg"
INSTALL_PREFIX="/usr/local"

echo ""
echo "Directory di build: $BUILD_DIR"
echo "Directory di installazione: $INSTALL_PREFIX"
echo ""

# Verifica se FFmpeg esiste già e se ha supporto Whisper
NEEDS_REBUILD=false
if command -v ffmpeg &> /dev/null; then
    CURRENT_VERSION=$(ffmpeg -version 2>/dev/null | head -1 | awk '{print $3}' | cut -d. -f1)
    echo -e "${YELLOW}⚠ FFmpeg già installato: $(ffmpeg -version 2>/dev/null | head -1)${NC}"
    
    # Verifica se ha il filtro Whisper
    if ffmpeg -filters 2>/dev/null | grep -qi whisper; then
        echo -e "${GREEN}✓ FFmpeg ha già il supporto Whisper!${NC}"
        echo "Non è necessario reinstallare."
        exit 0
    else
        echo -e "${YELLOW}⚠ FFmpeg NON ha il supporto Whisper${NC}"
        NEEDS_REBUILD=true
    fi
    
    if [[ "$NEEDS_REBUILD" == true ]]; then
        echo -e "${YELLOW}Vuoi reinstallare FFmpeg con supporto Whisper? (Y/n)${NC}"
        read -r response
        if [[ "$response" =~ ^[Nn]$ ]]; then
            echo "Installazione annullata"
            exit 0
        fi
    fi
fi

# Crea directory di build
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

echo ""
echo "=========================================="
echo "Passo 1: Installazione dipendenze"
echo "=========================================="
echo ""

# Installa dipendenze base
echo "Installazione dipendenze base..."
brew install automake autoconf libtool pkg-config yasm nasm || true

# Installa codec e librerie
echo "Installazione codec e librerie..."
brew install x264 x265 libvpx libvorbis opus sdl2 || true

# Installa whisper-cpp (nota: in Homebrew si chiama whisper-cpp, non whisper.cpp)
echo "Installazione whisper-cpp..."
if brew list whisper-cpp &> /dev/null; then
    echo -e "${GREEN}✓ whisper-cpp già installato${NC}"
else
    brew install whisper-cpp
    echo -e "${GREEN}✓ whisper-cpp installato${NC}"
fi

# Verifica whisper-cpp
if ! pkg-config --exists libwhisper 2>/dev/null; then
    echo -e "${YELLOW}⚠ pkg-config non trova libwhisper, verifico percorso manualmente...${NC}"
    WHISPER_PREFIX=$(brew --prefix whisper-cpp)
    if [[ -d "$WHISPER_PREFIX" ]]; then
        echo -e "${GREEN}✓ whisper-cpp trovato in: $WHISPER_PREFIX${NC}"
        export PKG_CONFIG_PATH="$WHISPER_PREFIX/lib/pkgconfig:$PKG_CONFIG_PATH"
    else
        echo -e "${RED}✗ whisper-cpp non trovato${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ whisper-cpp configurato correttamente${NC}"
fi

echo ""
echo "=========================================="
echo "Passo 2: Download/Update FFmpeg"
echo "=========================================="
echo ""

if [[ -d "$FFMPEG_DIR" ]]; then
    echo "Directory FFmpeg esistente, aggiornamento..."
    cd "$FFMPEG_DIR"
    git fetch origin
    git checkout master || git checkout main
    git pull origin master || git pull origin main
else
    echo "Clone repository FFmpeg..."
    git clone https://git.ffmpeg.org/ffmpeg.git "$FFMPEG_DIR"
    cd "$FFMPEG_DIR"
fi

# Verifica che siamo su un branch con versione 8.0+
echo "Verifica versione FFmpeg..."
LATEST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "n8.0")
echo "Ultimo tag: $LATEST_TAG"

# Checkout versione stabile 8.0 o superiore
if git tag | grep -q "^n8\."; then
    LATEST_8_TAG=$(git tag | grep "^n8\." | sort -V | tail -1)
    echo "Checkout tag: $LATEST_8_TAG"
    git checkout "$LATEST_8_TAG" 2>/dev/null || git checkout master
else
    echo "Checkout branch master (versione più recente)"
    git checkout master || git checkout main
fi

echo ""
echo "=========================================="
echo "Passo 3: Configurazione FFmpeg"
echo "=========================================="
echo ""

# Prepara variabili d'ambiente per whisper-cpp
WHISPER_PREFIX=$(brew --prefix whisper-cpp)
export PKG_CONFIG_PATH="$WHISPER_PREFIX/lib/pkgconfig:$PKG_CONFIG_PATH"
export LDFLAGS="-L$WHISPER_PREFIX/lib $LDFLAGS"
export CPPFLAGS="-I$WHISPER_PREFIX/include $CPPFLAGS"

echo "Configurazione FFmpeg con supporto Whisper..."
echo "whisper.cpp prefix: $WHISPER_PREFIX"

# Configura FFmpeg
./configure \
    --prefix="$INSTALL_PREFIX" \
    --enable-whisper \
    --enable-libx264 \
    --enable-libx265 \
    --enable-libvpx \
    --enable-libvorbis \
    --enable-libopus \
    --enable-shared \
    --enable-pic \
    --enable-gpl \
    --enable-version3 \
    --extra-libs="-L$WHISPER_PREFIX/lib" \
    --extra-cflags="-I$WHISPER_PREFIX/include" \
    2>&1 | tee configure.log

if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
    echo -e "${RED}✗ Errore durante la configurazione${NC}"
    echo "Controlla configure.log per dettagli"
    exit 1
fi

# Verifica che whisper sia abilitato
if grep -q "whisper" configure.log; then
    echo -e "${GREEN}✓ Supporto Whisper abilitato nella configurazione${NC}"
else
    echo -e "${YELLOW}⚠ Attenzione: Whisper potrebbe non essere abilitato${NC}"
fi

echo ""
echo "=========================================="
echo "Passo 4: Compilazione FFmpeg"
echo "=========================================="
echo ""

# Numero di core CPU
CORES=$(sysctl -n hw.ncpu)
echo "Compilazione con $CORES core (questo può richiedere 10-30 minuti)..."

make -j"$CORES" 2>&1 | tee make.log

if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
    echo -e "${RED}✗ Errore durante la compilazione${NC}"
    echo "Controlla make.log per dettagli"
    exit 1
fi

echo -e "${GREEN}✓ Compilazione completata${NC}"

echo ""
echo "=========================================="
echo "Passo 5: Installazione FFmpeg"
echo "=========================================="
echo ""

echo "Installazione in $INSTALL_PREFIX..."
echo "Potrebbe essere richiesta la password sudo"

sudo make install

if [[ $? -ne 0 ]]; then
    echo -e "${RED}✗ Errore durante l'installazione${NC}"
    exit 1
fi

# Aggiorna cache delle librerie dinamiche
sudo ldconfig 2>/dev/null || true

echo ""
echo "=========================================="
echo "Passo 6: Verifica installazione"
echo "=========================================="
echo ""

# Verifica versione
NEW_VERSION=$(ffmpeg -version 2>/dev/null | head -1)
echo "Versione FFmpeg installata:"
echo "$NEW_VERSION"

# Verifica filtro Whisper
echo ""
echo "Verifica supporto Whisper..."
if ffmpeg -filters 2>/dev/null | grep -qi whisper; then
    echo -e "${GREEN}✓ Filtro Whisper trovato!${NC}"
    ffmpeg -filters 2>/dev/null | grep -i whisper
else
    echo -e "${RED}✗ Filtro Whisper NON trovato${NC}"
    echo "FFmpeg potrebbe non essere stato compilato correttamente con Whisper"
    exit 1
fi

echo ""
echo "=========================================="
echo -e "${GREEN}✓ Installazione completata!${NC}"
echo "=========================================="
echo ""
echo "FFmpeg 8.0+ con supporto Whisper è ora installato."
echo ""
echo "Puoi verificare con:"
echo "  ffmpeg -version"
echo "  ffmpeg -filters | grep whisper"
echo ""
echo "Per testare il filtro Whisper:"
echo "  python3 ffmpeg_whisper.py --check"

