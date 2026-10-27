#!/usr/bin/env bash
set -e
HRI_WEEK6_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$HRI_WEEK6_ROOT/scripts/env.sh"
HRI_WEEK6_MODE="${1:-demo}"
if [ "$#" -gt 0 ]; then shift; fi
case "$HRI_WEEK6_MODE" in
  sim|simulation) HRI_WEEK6_LAUNCH=simulation.launch.py ;;
  hri) HRI_WEEK6_LAUNCH=hri_gesture_control.launch.py ;;
  demo) HRI_WEEK6_LAUNCH=demo.launch.py ;;
  *) echo 'Usage: scripts/run.sh {sim|hri|demo} [launch_argument:=value ...]'; exit 2 ;;
esac
if [ "$HRI_WEEK6_MODE" != hri ] && pgrep -f '^gz sim server' >/dev/null; then
  echo 'Gazebo server is already running. Use scripts/run.sh hri, or close the existing simulator first.' >&2
  exit 1
fi
exec python "$HRI_WEEK6_ROOT/scripts/process_supervisor.py" ros2 launch hri_gesture_control "$HRI_WEEK6_LAUNCH" "$@"
