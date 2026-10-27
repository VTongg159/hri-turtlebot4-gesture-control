from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description():
    launch_dir = Path(get_package_share_directory("hri_gesture_control")) / "launch"
    return LaunchDescription(
        [
            IncludeLaunchDescription(PythonLaunchDescriptionSource(str(launch_dir / f)))
            for f in ("simulation.launch.py", "hri_gesture_control.launch.py")
        ]
    )
