#!/usr/bin/env python3
"""Real process-crash tests against Gazebo with actual webcam heartbeat.
Injects gesture labels only; run with hands outside webcam view.
Owns only the two HRI processes it starts, never the existing simulator.
"""

import json
import signal
import subprocess
import time
from pathlib import Path

import rclpy
from ament_index_python.packages import get_package_prefix
from geometry_msgs.msg import TwistStamped
from hri_gesture_control.qos import event_qos
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import Bool, String


def main():
    rclpy.init()
    n = Node("week6_crash_test")
    root = Path(__file__).resolve().parents[1]
    (root / "test_results").mkdir(exist_ok=True)
    prefix = Path(get_package_prefix("hri_gesture_control")) / "lib/hri_gesture_control"
    children = []
    logs = []
    results = []
    state = {}
    velocity = (0.0, 0.0)
    last_hb = 0.0
    commands = []
    g = n.create_publisher(String, "/detected_gesture", event_qos())

    def on_status(m):
        nonlocal state
        state = json.loads(m.data)

    def on_hb(m):
        nonlocal last_hb
        if m.data:
            last_hb = time.monotonic()

    def on_odom(m):
        nonlocal velocity
        velocity = m.twist.twist.linear.x, m.twist.twist.angular.z

    n.create_subscription(String, "/gesture_system/status", on_status, 1)
    n.create_subscription(Bool, "/gesture_system/heartbeat", on_hb, qos_profile_sensor_data)
    n.create_subscription(Odometry, "/odom", on_odom, qos_profile_sensor_data)
    n.create_subscription(
        TwistStamped,
        "/cmd_vel",
        lambda m: commands.append((time.monotonic(), m.twist.linear.x, m.twist.angular.z)),
        10,
    )

    def pump(d):
        end = time.monotonic() + d
        while time.monotonic() < end:
            rclpy.spin_once(n, timeout_sec=0.02)

    def start(name):
        f = open(root / "test_results" / f"fault_{name}_{len(children)}.log", "w")
        logs.append(f)
        args = [
            str(prefix / name),
            "--ros-args",
            "--params-file",
            str(root / "src/hri_gesture_control/config/gestures.yaml"),
        ]
        args += (
            ["-p", "display:=false"]
            if name == "gesture_recognition_node"
            else ["-p", "use_sim_time:=true"]
        )
        p = subprocess.Popen(args, stdout=f, stderr=subprocess.STDOUT)
        children.append(p)
        return p

    def event(label):
        g.publish(String(data=label))
        pump(0.2)

    def select_move():
        event("CLOSED_FIST")
        event("VICTORY")
        event("THUMBS_UP")
        pump(0.9)
        assert state.get("state") == "EXECUTING" and abs(velocity[0]) > 0.03, (state, velocity)

    def stopped():
        return abs(velocity[0]) < 0.015 and abs(velocity[1]) < 0.03

    def result(name, **info):
        r = dict(test=name, result="PASS", **info)
        results.append(r)
        print(json.dumps(r), flush=True)

    try:
        b = start("robot_behavior_node")
        r = start("gesture_recognition_node")
        end = time.monotonic() + 15
        while time.monotonic() < end and time.monotonic() - last_hb > 1:
            pump(0.2)
        assert time.monotonic() - last_hb < 1, "No live webcam/inference heartbeat"
        pump(1)
        result("actual_webcam_node_heartbeat")
        select_move()
        t = time.monotonic()
        r.kill()
        r.wait()
        while time.monotonic() - t < 2 and (state.get("state") != "ERROR" or not stopped()):
            pump(0.02)
        assert state.get("state") == "ERROR" and stopped(), (state, velocity)
        result(
            "recognition_SIGKILL_stops_robot",
            stop_observed_after_s=time.monotonic() - t,
            reason=state.get("reason"),
        )
        r = start("gesture_recognition_node")
        pump(4)
        select_move()
        t = time.monotonic()
        b.kill()
        b.wait()
        while time.monotonic() - t < 3 and not stopped():
            pump(0.02)
        assert stopped(), velocity
        result("controller_SIGKILL_downstream_timeout", stop_observed_after_s=time.monotonic() - t)
        b = start("robot_behavior_node")
        pump(2)
        assert state.get("state") == "IDLE", state
        event("THUMBS_UP")
        assert stopped()
        result("controller_restart_no_stale_action")
        select_move()
        subprocess.run(
            [
                "gz",
                "service",
                "-s",
                "/world/hri_empty/control",
                "--reqtype",
                "gz.msgs.WorldControl",
                "--reptype",
                "gz.msgs.Boolean",
                "--timeout",
                "3000",
                "--req",
                "pause: true",
            ],
            check=True,
            capture_output=True,
        )
        pump(1)
        assert state.get("state") == "ERROR" and state.get("reason") == "Odometry expired", state
        assert abs(commands[-1][1]) + abs(commands[-1][2]) < 1e-6
        subprocess.run(
            [
                "gz",
                "service",
                "-s",
                "/world/hri_empty/control",
                "--reqtype",
                "gz.msgs.WorldControl",
                "--reptype",
                "gz.msgs.Boolean",
                "--timeout",
                "3000",
                "--req",
                "pause: false",
            ],
            check=True,
            capture_output=True,
        )
        pump(0.8)
        assert stopped()
        result("paused_simulator_steady_odom_watchdog")
    except Exception as e:
        results.append(dict(test="failure", result="FAIL", detail=repr(e), state=state))
        print(results[-1], flush=True)
        raise
    finally:
        g.publish(String(data="OPEN_PALM"))
        pump(0.2)
        subprocess.run(
            [
                "gz",
                "service",
                "-s",
                "/world/hri_empty/control",
                "--reqtype",
                "gz.msgs.WorldControl",
                "--reptype",
                "gz.msgs.Boolean",
                "--timeout",
                "1000",
                "--req",
                "pause: false",
            ],
            capture_output=True,
        )
        for p in reversed(children):
            if p.poll() is None:
                p.send_signal(signal.SIGINT)
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
        for f in logs:
            f.close()
        (root / "test_results/fault_results.json").write_text(json.dumps(results, indent=2))
        n.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
