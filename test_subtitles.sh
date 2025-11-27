#!/bin/bash
# Test per verificare se i sottotitoli vengono applicati correttamente

echo "=== Test Sottotitoli ==="

# Crea un file SRT di test
TEST_SRT="/tmp/test_subtitles.srt"
cat > "$TEST_SRT" << 'EOF'
1
00:00:00,000 --> 00:00:05,000
Test sottotitolo 1

2
00:00:05,000 --> 00:00:10,000
Test sottotitolo 2

3
00:00:10,000 --> 00:00:15,000
Test sottotitolo 3
EOF

echo "File SRT creato: $TEST_SRT"
cat "$TEST_SRT"

# Test URL video
VIDEO_URL="https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/TearsOfSteel.mp4"
OUTPUT="/tmp/test_subtitles_output.mp4"

echo ""
echo "Test FFmpeg con sottotitoli..."
echo "Comando:"
echo "ffmpeg -i \"$VIDEO_URL\" -vf \"subtitles=$TEST_SRT:force_style='FontSize=24,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2,Bold=1'\" -t 15 -y \"$OUTPUT\""

# Esegui FFmpeg per 15 secondi
ffmpeg -i "$VIDEO_URL" \
  -vf "subtitles=$TEST_SRT:force_style='FontSize=24,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2,Bold=1'" \
  -t 15 \
  -y "$OUTPUT" 2>&1 | grep -E "error|subtitle|filter" | head -10

if [ -f "$OUTPUT" ]; then
    SIZE=$(ls -lh "$OUTPUT" | awk '{print $5}')
    echo ""
    echo "✓ File generato: $OUTPUT ($SIZE)"
    echo "Apri con: open $OUTPUT"
    echo "Verifica che i sottotitoli siano visibili nel video"
else
    echo "✗ Errore: file non generato"
fi

