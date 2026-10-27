"""Run HRI only. Empty argument values preserve the YAML setting."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

OPTIONS = [
    ("camera_device", int, "recognition"),
    ("display", bool, "recognition"),
    ("confidence", float, "recognition"),
    ("wave_cooldown", float, "recognition"),
    ("cmd_vel_topic", str, "behavior"),
    ("odom_topic", str, "behavior"),
    ("velocity_type", str, "behavior"),
    ("heartbeat_timeout", float, "behavior"),
    ("use_sim_time", bool, "behavior"),
]


def nodes(context):
    overrides = {"recognition": {}, "behavior": {}}
    for name, typ, target in OPTIONS:
        value = LaunchConfiguration(name).perform(context)
        if value:
            if typ is bool:
                if value.lower() not in ("true", "false"):
                    raise ValueError(name + " must be true or false")
                value = value.lower() == "true"
            else:
                value = typ(value)
            overrides[target][name] = value
    config = LaunchConfiguration("params_file").perform(context)
    return [
        Node(
            package="hri_gesture_control",
            executable=executable,
            name=executable,
            output="screen",
            parameters=[config, overrides[target]],
        )
        for executable, target in [
            ("robot_behavior_node", "behavior"),
            ("gesture_recognition_node", "recognition"),
        ]
    ]


def generate_launch_description():
    config = str(Path(get_package_share_directory("hri_gesture_control")) / "config/gestures.yaml")
    return LaunchDescription(
        [DeclareLaunchArgument("params_file", default_value=config)]
        + [
            DeclareLaunchArgument(
                name,
                default_value="true" if name == "use_sim_time" else "",
                description="Override YAML; empty preserves YAML",
            )
            for name, _, _ in OPTIONS
        ]
        + [OpaqueFunction(function=nodes)]
    )
