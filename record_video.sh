#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$SCRIPT_DIR/Recordings"
timestamp=$(date +%Y%m%d_%H%M%S)
scrcpy --audio-codec=aac --record="$SCRIPT_DIR/Recordings/screen_recording_${timestamp}.mp4" --no-audio-playback --video-buffer=50 --audio-buffer=50 --show-touches --stay-awake "$@"
