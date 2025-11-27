#!/bin/bash
# Script per scaricare i modelli Whisper per whisper.cpp

MODELS_DIR="$HOME/.cache/whisper"
mkdir -p "$MODELS_DIR"

cd "$MODELS_DIR"

echo "=== Download modelli Whisper per whisper.cpp ==="
echo "Directory: $MODELS_DIR"
echo ""

# Lista modelli disponibili
models=("tiny" "base" "small" "medium" "large")

for model in "${models[@]}"; do
    model_file="${model}.bin"
    if [ -f "$model_file" ]; then
        echo "✓ Modello $model già presente: $model_file"
    else
        echo "Download modello $model..."
        url="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-${model}.bin"
        if curl -L -o "$model_file" "$url"; then
            echo "✓ Modello $model scaricato: $model_file"
        else
            echo "✗ Errore download modello $model"
        fi
    fi
done

echo ""
echo "=== Modelli disponibili ==="
ls -lh *.bin 2>/dev/null || echo "Nessun modello trovato"

