# TurtleBot 4 Gesture Control — HRI Week 06

Control TurtleBot 4 in Gazebo Harmonic using a webcam, MediaPipe Gesture Recognizer, and ROS 2 Jazzy. Users select a behavior with a hand gesture and confirm it with a thumbs-up. The robot uses odometry to execute motions and stops on STOP, CANCEL, or a watchdog timeout.

## Requirements

- Ubuntu 24.04 LTS, ROS 2 Jazzy, and Gazebo Harmonic.
- Official TurtleBot 4 Simulator; the Lite model is used by default.
- Python 3.12, OpenCV, and MediaPipe Tasks.
- A built-in or USB webcam. Nav2, SLAM, and a map are not required.

## Project structure

```text
.
├── README.md
├── LICENSE
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── scripts/
│   ├── download_model.sh
│   ├── env.sh
│   ├── fetch_simulator.py
│   ├── process_supervisor.py
│   ├── run.sh
│   ├── simulator_packages.txt
│   ├── test_faults.py
│   └── test_simulation.py
└── src/hri_gesture_control/
    ├── config/
    ├── hri_gesture_control/
    │   ├── behavior.py
    │   ├── gesture_filters.py
    │   ├── gesture_recognition_node.py
    │   ├── qos.py
    │   └── robot_behavior_node.py
    ├── launch/
    ├── models/                 # Model documentation; download the .task file separately
    ├── resource/
    ├── test/
    ├── worlds/
    ├── package.xml
    ├── setup.cfg
    └── setup.py
```

## Installation and build

Clone the repository into `~/hri_week6_ws`, or use another dedicated workspace directory. Scripts resolve paths relative to the project location and do not depend on a specific username.

Check your environment before installing dependencies:

```bash
source /opt/ros/jazzy/setup.bash
ros2 pkg list | rg 'turtlebot4|irobot'
gz sim --version
python3 --version
ls -l /dev/video*
apt-get -s install ros-jazzy-turtlebot4-simulator
```

Install any missing dependencies using the official packages:

```bash
sudo apt install ros-jazzy-turtlebot4-simulator python3-venv \
  python3-opencv python3-pytest python3-colcon-common-extensions curl
```

Create a Python environment, download the model, and build the package:

```bash
cd ~/hri_week6_ws
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
bash scripts/download_model.sh
source scripts/env.sh
python -m colcon build --symlink-install --packages-select hri_gesture_control
source install/local_setup.bash
```

Use `--system-site-packages` to access Jazzy's `rclpy`. Run `python -m colcon` inside the virtual environment so that the nodes use the correct Python interpreter. The model download is verified with SHA256; its source is documented in `src/hri_gesture_control/models/README.md`.

### Local fallback without sudo

If the machine already has the underlying ROS/Gazebo dependencies, you can extract the official simulator packages into `vendor/`:

```bash
python3 scripts/fetch_simulator.py
source scripts/env.sh
python -m colcon build --symlink-install --packages-select hri_gesture_control
source install/local_setup.bash
```

The script checks package SHA256 hashes against local apt metadata before extraction and does not install system packages. This fallback depends on the libraries already available on the machine; installation through apt remains the primary approach. `scripts/env.sh` only changes the environment of the current shell.

## Running the system

### Launch everything

Terminal 1:

```bash
cd ~/hri_week6_ws
./scripts/run.sh demo
```

Wait for the robot to spawn and for `diffdrive_controller` to become active. In Terminal 2:

```bash
cd ~/hri_week6_ws
source scripts/env.sh
ros2 topic echo /dock_status --once
ros2 action send_goal /undock irobot_create_msgs/action/Undock '{}'
```

Wait for `SUCCEEDED`, then start using hand gestures. Skip undocking if the robot is already undocked. Allow the simulator to finish initializing; an undock goal sent too early may be rejected.

### Launch Gazebo and HRI separately

```bash
# Terminal 1
./scripts/run.sh sim

# Terminal 2, after undocking
./scripts/run.sh hri
```

`run.sh sim` and `run.sh demo` refuse to start a second simulator when a Gazebo server is already running. `run.sh hri` starts only the two HRI nodes; use it only when those nodes are not already running.

You can also launch the components directly after sourcing the workspace:

```bash
ros2 launch hri_gesture_control simulation.launch.py
ros2 launch hri_gesture_control hri_gesture_control.launch.py
ros2 launch hri_gesture_control demo.launch.py
```

Keep the launch terminals open. Press Ctrl+C in the launch terminal to stop the process group. Closing the webcam window also stops its heartbeat, causing the controller to stop the robot.

## Gesture controls

| Gesture | Label | Action |
|---|---|---|
| One raised index finger | `POINTING_UP` | Select four forward/backward cycles |
| Two raised fingers | `VICTORY` | Select one circular lap |
| Wave | `WAVE` | Select a left/right/return greeting |
| Thumbs-up | `THUMBS_UP` | Confirm the selected behavior |
| Open palm | `OPEN_PALM` | Stop, clear the selection, and enter STOPPED |
| Closed fist | `CLOSED_FIST` | Cancel, clear the selection, and return to IDLE |

Hold the selection gesture for about one second, lower your hand for 0.5 seconds, then hold a thumbs-up for about one second. Confirm within 10 seconds of selecting a behavior. Selection alone does not move the robot; a thumbs-up without a selection does not start a motion.

For Wave, face your open palm toward the camera and move it clearly from side to side for 3–4 beats within about two seconds. Wait for `WAVE` / `Selected: GREETING`, then lower your hand and confirm. While the robot is executing a behavior, an open palm takes priority as STOP. After STOP or CANCEL, select and confirm again; the robot does not resume automatically.

## Architecture and topics

```text
Webcam → OpenCV → MediaPipe → gesture filtering / Wave landmarks
                                         ↓
                               /detected_gesture
                                         ↓
                               Robot behavior FSM
                              ↗                  ↘
                         /odom                /cmd_vel
```

- `gesture_recognition_node`: camera capture, recognition, event filtering, landmark drawing, and the webcam UI.
- `robot_behavior_node`: selection/confirmation, behavior FSM, odometry feedback, and watchdogs using nonblocking timers.
- `behavior.py`, `gesture_filters.py`: pure Python logic that can be tested without ROS.
- `qos.py`: gesture events use depth 1, volatile durability, and a 0.3-second lifespan.

| Topic | Message type | Content |
|---|---|---|
| `/detected_gesture` | `std_msgs/msg/String` | Gesture labels published as events |
| `/gesture_system/heartbeat` | `std_msgs/msg/Bool` | Camera and inference health |
| `/gesture_system/status` | `std_msgs/msg/String` | Robot state as JSON |
| `/gesture_system/recognition` | `std_msgs/msg/String` | Labels, scores, landmarks, and Wave diagnostics as JSON |
| `/cmd_vel` | Observed: `geometry_msgs/msg/TwistStamped` | Velocity commands |
| `/odom` | `nav_msgs/msg/Odometry` | Position and orientation feedback |
| `/clock` | `rosgraph_msgs/msg/Clock` | Simulation time |

The controller inspects actual subscribers to select `TwistStamped` or `Twist`. A heartbeat is sent after successful image capture and inference, including when no hand is visible. The absence of a new gesture event is not treated as a camera failure.

## Configuration

Default configuration: `src/hri_gesture_control/config/gestures.yaml`.

| Parameter | Default |
|---|---|
| Camera / inference | Device 0, 640×480, 15 Hz |
| Selection gestures | Confidence 0.70, four consecutive frames |
| Thumbs-up confirmation | Confidence 0.60, held continuously for 0.60 s |
| STOP | Confidence 0.60, bypasses temporal filtering delay |
| Wave | Confidence 0.55, amplitude 0.10 of image width, three reversals within 2 s |
| Wave cooldown | 2.5 s |
| Default command speed limits | 0.12 m/s; 0.45 rad/s |
| Forward/backward / circle | Forward distance 0.30 m; radius 0.45 m |
| Heartbeat / odometry timeout | 0.8 s / 0.6 s |

Examples of launch overrides:

```bash
./scripts/run.sh hri camera_device:=2
./scripts/run.sh hri cmd_vel_topic:=/robot1/cmd_vel odom_topic:=/robot1/odom
./scripts/run.sh hri params_file:=/path/to/gestures.yaml
./scripts/run.sh sim gui:=false
./scripts/run.sh hri display:=false
```

An empty launch argument preserves the YAML value. Gesture, status, and heartbeat topics are shared for a single robot; do not run multiple HRI instances on the same topics.

## Testing and code checks

Pure Python unit tests:

```bash
.venv/bin/python -m pytest
```

Build and ROS package tests:

```bash
source scripts/env.sh
python -m colcon build --symlink-install --packages-select hri_gesture_control
python -m colcon test --packages-select hri_gesture_control --event-handlers console_direct+
colcon test-result --verbose
```

Lint and formatting:

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/ruff check src scripts
.venv/bin/ruff format --check src scripts
```

### Gazebo integration tests

Keep the simulator running with the robot undocked. Stop the HRI nodes first. Run only the controller in Terminal 1:

```bash
source scripts/env.sh
ros2 run hri_gesture_control robot_behavior_node --ros-args \
  --params-file src/hri_gesture_control/config/gestures.yaml -p use_sim_time:=true
```

Terminal 2:

```bash
source scripts/env.sh
python scripts/test_simulation.py
```

This script injects gesture labels and heartbeats to test the three motions, selection/confirmation, STOP, CANCEL, and watchdogs. It tests robot control, not webcam recognition accuracy.

Process-failure tests with the real webcam:

```bash
# Stop the HRI nodes; keep Gazebo running and the robot undocked, with your hands out of view.
source scripts/env.sh
python scripts/test_faults.py
```

This script starts its own two HRI nodes, deliberately kills processes it manages, and temporarily pauses the world to test the watchdog. Do not run it alongside a live gesture-control demo. Test data is written to `test_results/`, which is excluded from Git.

## Troubleshooting

| Symptom | What to check |
|---|---|
| Cannot import `rclpy` | Source Jazzy and use a virtual environment with `--system-site-packages` |
| `ros2 run` cannot find MediaPipe | Build with `python -m colcon` from the virtual environment |
| Camera is busy or frames cannot be read | Close other camera applications; check `/dev/video*` and `fuser /dev/video0` |
| SELECTED but no motion | Check that `THUMBS_UP` reaches the score and hold-time thresholds within 10 seconds |
| Wave is not detected | Check `Raw`, score, span, and turns; move the whole palm horizontally and keep it in frame |
| EXECUTING but no motion | Check dock status, controller activation, the velocity topic/type, and `/odom` |
| ERROR after pausing Gazebo | The odometry watchdog stopped the robot; resume, then select and confirm again |
| Clock/TF jumps or duplicate controllers | Run only one simulator and use the same `ROS_DOMAIN_ID` in all terminals |

Inspect the ROS interfaces:

```bash
ros2 topic list -t
ros2 topic info /cmd_vel -v
ros2 topic echo /odom --once
ros2 control list_controllers
```

## Repository scope

The repository contains source code, configuration, launch files, tests, usage instructions, and dependency/model download scripts. Reports, LaTeX files, PDFs, webcam images, videos, logs, archives, downloaded models, Python environments, and build/install directories are excluded from Git.

## References and license

- [TurtleBot 4 Simulator](https://turtlebot.github.io/turtlebot4-user-manual/software/simulation.html)
- [MediaPipe Gesture Recognizer](https://ai.google.dev/edge/mediapipe/solutions/vision/gesture_recognizer/python)
- Project source code is licensed under Apache-2.0; see `LICENSE`. The model downloaded from Google has separate source information in `models/README.md`.
