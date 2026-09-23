#!/bin/sh
# EWVE one-time setup (macOS / Linux).  Run from the ewve folder:  ./setup.sh
# Set SKIP_TRANSCRIPTS=1 to skip the whisper model download (~470 MB); click-to-cut transcripts are then off.
set -e
cd "$(dirname "$0")"
say() { printf '\n\033[1m%s\033[0m\n' "$1"; }

say "1/4  Checking tools"
command -v python3 >/dev/null || { echo "Python 3 is required: https://www.python.org/downloads/"; exit 1; }
if ! command -v ffmpeg >/dev/null; then
  if command -v brew >/dev/null; then brew install ffmpeg
  else echo "ffmpeg is required. macOS: install Homebrew (https://brew.sh) then 'brew install ffmpeg'. Linux: 'sudo apt install ffmpeg'."; exit 1; fi
fi
if [ -z "$SKIP_TRANSCRIPTS" ] && ! command -v whisper-cli >/dev/null && ! command -v whisper-cpp >/dev/null; then
  if command -v brew >/dev/null; then brew install whisper-cpp
  else echo "whisper.cpp not found; transcripts will be skipped. See https://github.com/ggml-org/whisper.cpp"; fi
fi

say "2/4  Python environment"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip numpy

say "3/4  Transcription model"
if [ -z "$SKIP_TRANSCRIPTS" ] && [ ! -f models/ggml-small.en.bin ]; then
  mkdir -p models
  curl -L --fail -C - -o models/ggml-small.en.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin
fi

say "4/4  Done"
echo "Start EWVE with:  ./ewve"
echo "Or open a folder of videos directly:  ./ewve \"/path/to/videos\""
