"""Gazebo Harmonic empty world plus unmodified official TurtleBot 4 spawn launch."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory as share
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    OpaqueFunction,
    SetEnvironmentVariable,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def simulator(context):
    gui = LaunchConfiguration("gui").perform(context) == "true"
    world = str(Path(share("hri_gesture_control")) / "worlds/hri_empty.sdf")
    gui_config = str(Path(share("hri_gesture_control")) / "config/gazebo_gui.config")
    gz_args = f"-r -v 3 {world} --gui-config {gui_config}" + ("" if gui else " -s")
    return [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                str(Path(share("ros_gz_sim")) / "launch/gz_sim.launch.py")
            ),
            launch_arguments={"gz_args": gz_args, "on_exit_shutdown": "true"}.items(),
        )
    ]


def generate_launch_description():
    resources = ":".join(
        str(Path(share(p)).parent) for p in ("turtlebot4_description", "irobot_create_description")
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument("world", default_value="hri_empty"),
            DeclareLaunchArgument("gui", default_value="true", choices=["true", "false"]),
            DeclareLaunchArgument("model", default_value="lite", choices=["lite", "standard"]),
            SetEnvironmentVariable("GZ_SIM_RESOURCE_PATH", resources),
            OpaqueFunction(function=simulator),
            Node(
                package="ros_gz_bridge",
                executable="parameter_bridge",
                name="clock_bridge",
                arguments=["/world/hri_empty/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock"],
                remappings=[("/world/hri_empty/clock", "/clock")],
                output="screen",
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    str(Path(share("turtlebot4_gz_bringup")) / "launch/turtlebot4_spawn.launch.py")
                ),
                launch_arguments={
                    "model": LaunchConfiguration("model"),
                    "use_sim_time": "true",
                    "nav2": "false",
                    "slam": "false",
                    "localization": "false",
                    "rviz": "false",
                }.items(),
            ),
        ]
    )
