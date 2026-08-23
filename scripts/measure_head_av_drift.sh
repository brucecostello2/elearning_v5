#!/usr/bin/env bash
# measure_head_av_drift.sh - AD-03 s10 criterion 3: head A/V drift.
#
# WP-04-FRAME-ALIGN. Measures the drift on a REAL render artifact, not from the
# arithmetic. Video length is taken from the frame count and the frame rate, not from
# the container duration field, because the container rounds and the frame count does
# not.
#
# Usage:
#   scripts/measure_head_av_drift.sh <head.mp4> <narration.wav> [more-narration.wav ...]
#
# The narration arguments are the Stage 5 per-scene audio files, in scene order. Their
# durations are summed - that sum is the length the head is supposed to be.
#
# Requires ffprobe. node-01 has no host ffprobe; run it inside the worker image:
#   docker run --rm -u 0 -v "$PWD":/w:ro -w /w --entrypoint bash \
#     ghcr.io/brucecostello2/ivgs-workers:v5.5.4-metrics \
#     scripts/measure_head_av_drift.sh head.mp4 scene_*.wav
#
# Exit 0 if drift < 1 frame, 1 otherwise. Exit code is NOT the evidence - read the
# numbers it prints.
set -uo pipefail

if [ "$#" -lt 2 ]; then
    echo "usage: $0 <head.mp4> <narration.wav> [narration.wav ...]" >&2
    exit 2
fi

HEAD="$1"; shift

if ! command -v ffprobe >/dev/null 2>&1; then
    echo "ffprobe not found - see the header for the docker invocation" >&2
    exit 2
fi

probe() { ffprobe -v error "$@"; }

RFR=$(probe -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 "$HEAD")
AFR=$(probe -select_streams v:0 -show_entries stream=avg_frame_rate -of csv=p=0 "$HEAD")
NBF=$(probe -select_streams v:0 -show_entries stream=nb_frames -of csv=p=0 "$HEAD")

if [ -z "$NBF" ] || [ "$NBF" = "N/A" ]; then
    # Stream copy concat can leave nb_frames unset; count packets instead.
    NBF=$(probe -select_streams v:0 -count_packets -show_entries stream=nb_read_packets \
          -of csv=p=0 "$HEAD")
fi

FPS=$(awk -F/ '{ if (NF==2 && $2>0) printf "%.9f", $1/$2; else printf "%.9f", $1 }' <<<"$RFR")

AUDIO_TOTAL=0
echo "narration parts:"
for a in "$@"; do
    d=$(probe -show_entries format=duration -of csv=p=0 "$a")
    printf "  %-48s %s s\n" "$(basename "$a")" "$d"
    AUDIO_TOTAL=$(awk -v t="$AUDIO_TOTAL" -v d="$d" 'BEGIN{printf "%.9f", t+d}')
done

VIDEO_S=$(awk -v n="$NBF" -v f="$FPS" 'BEGIN{printf "%.9f", n/f}')
DRIFT=$(awk -v v="$VIDEO_S" -v a="$AUDIO_TOTAL" 'BEGIN{printf "%.9f", v-a}')
DRIFT_F=$(awk -v d="$DRIFT" -v f="$FPS" 'BEGIN{printf "%.4f", d*f}')
ABS_F=$(awk -v d="$DRIFT_F" 'BEGIN{printf "%.4f", (d<0?-d:d)}')

echo
echo "head artifact      : $HEAD"
echo "r_frame_rate       : $RFR"
echo "avg_frame_rate     : $AFR"
echo "frames             : $NBF"
echo "fps                : $FPS"
echo "video length       : $VIDEO_S s   (frames / fps)"
echo "narration length   : $AUDIO_TOTAL s   (sum of $# part(s))"
echo "A/V drift          : $DRIFT s"
echo "A/V drift (frames) : $DRIFT_F"
echo

if [ "$RFR" != "$AFR" ]; then
    echo "WARNING: r_frame_rate != avg_frame_rate - the head is not CFR, so"
    echo "         frames/fps is not an exact length. Treat the result as indicative."
fi

PASS=$(awk -v a="$ABS_F" 'BEGIN{print (a<1.0)?"1":"0"}')
if [ "$PASS" = "1" ]; then
    echo "VERDICT: PASS - drift is under one frame (AD-03 s10 criterion 3)"
    exit 0
fi
echo "VERDICT: FAIL - drift is $ABS_F frames, criterion 3 requires < 1"
exit 1
