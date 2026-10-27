from glob import glob
from os.path import isfile

from setuptools import setup

package_name = "hri_gesture_control"
setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ]
    + [
        ("share/" + package_name + "/" + d, [p for p in glob(d + "/*") if isfile(p)])
        for d in ("launch", "config", "models", "worlds")
    ],
    install_requires=["setuptools"],
    tests_require=["pytest"],
    zip_safe=True,
    maintainer="HRI Week 6",
    maintainer_email="student@example.com",
    description="Webcam gestures for TurtleBot 4 on Jazzy",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "gesture_recognition_node = hri_gesture_control.gesture_recognition_node:main",
            "robot_behavior_node = hri_gesture_control.robot_behavior_node:main",
        ]
    },
)
