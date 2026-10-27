#!/usr/bin/env bash
set -euo pipefail
HRI_WEEK6_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HRI_WEEK6_MODEL="$HRI_WEEK6_ROOT/src/hri_gesture_control/models/gesture_recognizer.task"
curl -fL --retry 3 -o "$HRI_WEEK6_MODEL.tmp" https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task
printf '%s  %s\n' "97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482" "$HRI_WEEK6_MODEL.tmp" | sha256sum -c -
mv "$HRI_WEEK6_MODEL.tmp" "$HRI_WEEK6_MODEL"
