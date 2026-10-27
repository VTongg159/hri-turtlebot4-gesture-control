# TurtleBot 4 Gesture Control — HRI Week 06

Điều khiển TurtleBot 4 trong Gazebo Harmonic bằng webcam, MediaPipe Gesture Recognizer và ROS 2 Jazzy. Người dùng chọn hành vi bằng cử chỉ và xác nhận bằng ngón cái. Robot dùng odometry để thực hiện chuyển động và dừng khi nhận STOP, CANCEL hoặc mất tín hiệu giám sát.

## Môi trường

- Ubuntu 24.04 LTS, ROS 2 Jazzy, Gazebo Harmonic.
- TurtleBot 4 Simulator chính thức; mặc định dùng model Lite.
- Python 3.12, OpenCV và MediaPipe Tasks.
- Webcam tích hợp hoặc USB. Không cần Nav2, SLAM hoặc bản đồ.

## Cấu trúc source

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
    ├── models/                 # Hướng dẫn model; file .task được tải riêng
    ├── resource/
    ├── test/
    ├── worlds/
    ├── package.xml
    ├── setup.cfg
    └── setup.py
```

## Cài đặt và build

Clone repository vào `~/hri_week6_ws`, hoặc dùng một thư mục workspace riêng khác. Các script xác định đường dẫn từ vị trí project, không phụ thuộc tên tài khoản.

Kiểm tra môi trường trước khi cài:

```bash
source /opt/ros/jazzy/setup.bash
ros2 pkg list | rg 'turtlebot4|irobot'
gz sim --version
python3 --version
ls -l /dev/video*
apt-get -s install ros-jazzy-turtlebot4-simulator
```

Cài những dependency còn thiếu bằng package chính thức:

```bash
sudo apt install ros-jazzy-turtlebot4-simulator python3-venv \
  python3-opencv python3-pytest python3-colcon-common-extensions curl
```

Tạo môi trường Python riêng, tải model rồi build:

```bash
cd ~/hri_week6_ws
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
bash scripts/download_model.sh
source scripts/env.sh
python -m colcon build --symlink-install --packages-select hri_gesture_control
source install/local_setup.bash
```

Dùng `--system-site-packages` để truy cập `rclpy` của Jazzy. Dùng `python -m colcon` trong venv để các node có đúng Python interpreter. Model được kiểm SHA256 khi tải; thông tin nguồn ở `src/hri_gesture_control/models/README.md`.

### Phương án local khi không có sudo

Nếu máy đã có các dependency ROS/Gazebo nền, có thể giải nén các package simulator chính thức vào `vendor/`:

```bash
python3 scripts/fetch_simulator.py
source scripts/env.sh
python -m colcon build --symlink-install --packages-select hri_gesture_control
source install/local_setup.bash
```

Script đối chiếu SHA256 theo metadata apt rồi giải nén, không cài package vào hệ thống. Cách này phụ thuộc các thư viện nền đang có trên máy; cài bằng apt vẫn là phương án chính. `scripts/env.sh` chỉ thay đổi môi trường của shell hiện tại.

## Khởi chạy

### Chạy toàn bộ

Terminal 1:

```bash
cd ~/hri_week6_ws
./scripts/run.sh demo
```

Chờ robot spawn và `diffdrive_controller` active. Terminal 2:

```bash
cd ~/hri_week6_ws
source scripts/env.sh
ros2 topic echo /dock_status --once
ros2 action send_goal /undock irobot_create_msgs/action/Undock '{}'
```

Chờ `SUCCEEDED`, sau đó dùng tay. Nếu robot đã undock thì bỏ qua bước undock. Cần đợi simulator khởi tạo xong; gửi goal quá sớm có thể bị từ chối.

### Chạy Gazebo và HRI riêng

```bash
# Terminal 1
./scripts/run.sh sim

# Terminal 2, sau khi đã undock
./scripts/run.sh hri
```

`run.sh sim` và `run.sh demo` từ chối mở simulator thứ hai nếu đã có Gazebo server. `run.sh hri` chỉ chạy hai node HRI; chỉ dùng khi các node HRI chưa chạy.

Có thể dùng ROS launch trực tiếp sau khi source:

```bash
ros2 launch hri_gesture_control simulation.launch.py
ros2 launch hri_gesture_control hri_gesture_control.launch.py
ros2 launch hri_gesture_control demo.launch.py
```

Giữ các terminal đang chạy. Ctrl+C trong terminal khởi chạy dừng cả nhóm tiến trình. Đóng webcam cũng ngừng heartbeat, khiến controller dừng robot.

## Cách tương tác

| Cử chỉ | Nhãn | Thao tác |
|---|---|---|
| Một ngón trỏ | `POINTING_UP` | Chọn tiến–lùi bốn chu kỳ |
| Hai ngón | `VICTORY` | Chọn một vòng tròn |
| Vẫy tay | `WAVE` | Chọn chào trái–phải–về |
| Ngón cái | `THUMBS_UP` | Xác nhận hành vi đã chọn |
| Xòe tay | `OPEN_PALM` | Dừng, xóa lựa chọn, chuyển STOPPED |
| Nắm tay | `CLOSED_FIST` | Hủy, xóa lựa chọn, về IDLE |

Giữ cử chỉ chọn khoảng một giây, hạ tay 0,5 giây, rồi giơ ngón cái khoảng một giây. Xác nhận trong 10 giây sau khi chọn. Chỉ chọn chưa làm robot chạy; ngón cái khi chưa chọn không tạo chuyển động.

Với Wave, mở lòng bàn tay hướng camera và dịch ngang rõ 3–4 nhịp trong khoảng hai giây. Chờ `WAVE` / `Selected: GREETING` rồi hạ tay và xác nhận. Khi robot đang chạy, xòe tay ưu tiên STOP. Sau STOP/CANCEL cần chọn lại và xác nhận; robot không tự tiếp tục.

## Kiến trúc và topics

```text
Webcam → OpenCV → MediaPipe → bộ lọc / Wave landmarks
                                      ↓
                            /detected_gesture
                                      ↓
                            Robot behavior FSM
                         ↙                     ↘
                    /odom                  /cmd_vel
```

- `gesture_recognition_node`: đọc camera, nhận diện, lọc sự kiện, vẽ landmarks và UI.
- `robot_behavior_node`: chọn/xác nhận, FSM, phản hồi odometry và watchdog bằng timer không blocking.
- `behavior.py`, `gesture_filters.py`: logic thuần Python, kiểm thử không cần ROS.
- `qos.py`: cấu hình sự kiện depth 1, volatile và lifespan 0,3 giây.

| Topic | Message type | Nội dung |
|---|---|---|
| `/detected_gesture` | `std_msgs/msg/String` | Nhãn cử chỉ theo sự kiện |
| `/gesture_system/heartbeat` | `std_msgs/msg/Bool` | Camera và inference hoạt động |
| `/gesture_system/status` | `std_msgs/msg/String` | JSON trạng thái robot |
| `/gesture_system/recognition` | `std_msgs/msg/String` | JSON nhãn, score, landmarks và chẩn đoán Wave |
| `/cmd_vel` | Thực tế `geometry_msgs/msg/TwistStamped` | Lệnh vận tốc |
| `/odom` | `nav_msgs/msg/Odometry` | Phản hồi vị trí và hướng |
| `/clock` | `rosgraph_msgs/msg/Clock` | Thời gian mô phỏng |

Node điều khiển kiểm tra subscriber thực tế để chọn đúng `TwistStamped` hoặc `Twist`. Heartbeat được gửi sau khi đọc ảnh và inference thành công, kể cả lúc không có bàn tay. Không dùng việc thiếu gesture event để suy ra mất camera.

## Cấu hình

File mặc định: `src/hri_gesture_control/config/gestures.yaml`.

| Tham số | Mặc định |
|---|---|
| Camera / inference | Device 0, 640×480, 15 Hz |
| Cử chỉ chọn | Confidence 0,70, bốn frame liên tiếp |
| Xác nhận ngón cái | Confidence 0,60, giữ liên tục 0,60 s |
| STOP | Confidence 0,60, bỏ qua temporal delay |
| Wave | Confidence 0,55, biên độ 0,10 ảnh, ba đảo chiều / 2 s |
| Wave cooldown | 2,5 s |
| Vận tốc lệnh tối đa mặc định | 0,12 m/s; 0,45 rad/s |
| Tiến–lùi / vòng tròn | Khoảng tiến 0,30 m; bán kính 0,45 m |
| Heartbeat / odom timeout | 0,8 s / 0,6 s |

Ví dụ ghi đè khi launch:

```bash
./scripts/run.sh hri camera_device:=2
./scripts/run.sh hri cmd_vel_topic:=/robot1/cmd_vel odom_topic:=/robot1/odom
./scripts/run.sh hri params_file:=/path/to/gestures.yaml
./scripts/run.sh sim gui:=false
./scripts/run.sh hri display:=false
```

Launch argument trống giữ giá trị YAML. Các topic gesture/status/heartbeat dùng chung cho một robot; không chạy nhiều bộ HRI trên cùng topics.

## Kiểm thử và kiểm tra code

Unit test thuần Python:

```bash
.venv/bin/python -m pytest
```

Build và ROS package tests:

```bash
source scripts/env.sh
python -m colcon build --symlink-install --packages-select hri_gesture_control
python -m colcon test --packages-select hri_gesture_control --event-handlers console_direct+
colcon test-result --verbose
```

Lint và format:

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/ruff check src scripts
.venv/bin/ruff format --check src scripts
```

### Test tích hợp trong Gazebo

Giữ simulator đang chạy và robot đã undock. Dừng các node HRI trước. Chạy riêng controller ở terminal 1:

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

Script tiêm nhãn và heartbeat để kiểm tra ba chuyển động, chọn/xác nhận, STOP, CANCEL và watchdog. Đây là test điều khiển, không phải test độ chính xác nhận diện webcam.

Test lỗi tiến trình với webcam thật:

```bash
# Dừng các node HRI; giữ Gazebo và robot đã undock, để tay ngoài camera.
source scripts/env.sh
python scripts/test_faults.py
```

Script này tự tạo hai node HRI, cố ý kill những tiến trình do nó quản lý và tạm pause world để kiểm tra watchdog. Không chạy cùng demo đang điều khiển bằng tay. Dữ liệu test được ghi vào `test_results/`, nằm ngoài Git.

## Xử lý lỗi thường gặp

| Hiện tượng | Cách kiểm tra |
|---|---|
| Không import `rclpy` | Source Jazzy, dùng venv với `--system-site-packages` |
| `ros2 run` không tìm MediaPipe | Build bằng `python -m colcon` từ venv |
| Camera bận hoặc không đọc ảnh | Đóng ứng dụng khác; kiểm tra `/dev/video*` và `fuser /dev/video0` |
| SELECTED nhưng chưa chạy | Kiểm tra có `THUMBS_UP` đủ score/thời gian giữ trong 10 giây |
| Wave chưa nhận | Xem `Raw`, score, span và turns; dịch cả lòng bàn tay ngang, giữ tay trong frame |
| EXECUTING nhưng robot không đi | Kiểm tra dock, controller active, đúng topic/type và `/odom` |
| ERROR sau khi pause Gazebo | Odom watchdog đã dừng robot; resume rồi chọn và xác nhận lại |
| Clock/TF nhảy hoặc controller bị trùng | Chỉ chạy một simulator, cùng `ROS_DOMAIN_ID` ở các terminal |

Kiểm tra ROS interface:

```bash
ros2 topic list -t
ros2 topic info /cmd_vel -v
ros2 topic echo /odom --once
ros2 control list_controllers
```

## Phạm vi repository

Repository chỉ chứa source, cấu hình, launch, tests, hướng dẫn chạy và script tải dependency/model. Báo cáo, LaTeX, PDF, ảnh webcam, video, log, archive, model đã tải, môi trường Python và thư mục build/install đều không đưa vào Git.

## Tài liệu gốc và giấy phép

- [TurtleBot 4 Simulator](https://turtlebot.github.io/turtlebot4-user-manual/software/simulation.html)
- [MediaPipe Gesture Recognizer](https://ai.google.dev/edge/mediapipe/solutions/vision/gesture_recognizer/python)
- Source của project dùng giấy phép Apache-2.0, xem `LICENSE`. Model tải từ Google có thông tin nguồn riêng trong `models/README.md`.
