# Source this file; all changes apply only to the current shell.
HRI_WEEK6_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source /opt/ros/jazzy/setup.bash
HRI_WEEK6_VENDOR="$HRI_WEEK6_ROOT/vendor/root/opt/ros/jazzy"
if [ -d "$HRI_WEEK6_VENDOR" ]; then
  export AMENT_PREFIX_PATH="$HRI_WEEK6_VENDOR:${AMENT_PREFIX_PATH:-}"
  export LD_LIBRARY_PATH="$HRI_WEEK6_VENDOR/lib:${LD_LIBRARY_PATH:-}"
  export PYTHONPATH="$HRI_WEEK6_VENDOR/lib/python3.12/site-packages:$HRI_WEEK6_VENDOR/local/lib/python3.12/dist-packages:${PYTHONPATH:-}"
  export PATH="$HRI_WEEK6_VENDOR/bin:$PATH"
  export GZ_SIM_SYSTEM_PLUGIN_PATH="$HRI_WEEK6_VENDOR/lib:${GZ_SIM_SYSTEM_PLUGIN_PATH:-}"
  export GZ_GUI_PLUGIN_PATH="$HRI_WEEK6_VENDOR/lib:${GZ_GUI_PLUGIN_PATH:-}"
  export GZ_SIM_RESOURCE_PATH="$HRI_WEEK6_VENDOR/share:${GZ_SIM_RESOURCE_PATH:-}"
fi
source "$HRI_WEEK6_ROOT/.venv/bin/activate"
if [ -f "$HRI_WEEK6_ROOT/install/local_setup.bash" ]; then
  source "$HRI_WEEK6_ROOT/install/local_setup.bash"
fi
