#!/usr/bin/env python3
"""Integration tests against a RUNNING real Gazebo TurtleBot4. Injected ROS labels,
not recognition tests, not demo teleoperation. Do not run alongside webcam node.
"""

import json
import math
import time
from pathlib import Path

import rclpy
from geometry_msgs.msg import TwistStamped
from hri_gesture_control.qos import event_qos
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import Bool, String


def main():
    rclpy.init()
    n = Node("week6_integration_test")
    root = Path(__file__).resolve().parents[1]
    (root / "test_results").mkdir(exist_ok=True)
    log = []
    state = {}
    pose = None
    velocity = (0.0, 0.0)
    hb = True
    samples = []
    commands = []
    g = n.create_publisher(String, "/detected_gesture", event_qos())
    h = n.create_publisher(Bool, "/gesture_system/heartbeat", qos_profile_sensor_data)

    def status(m):
        nonlocal state
        state = json.loads(m.data)

    def odom(m):
        nonlocal pose, velocity
        p, q = m.pose.pose.position, m.pose.pose.orientation
        pose = (p.x, p.y, math.atan2(2 * q.w * q.z, 1 - 2 * q.z * q.z))
        velocity = (m.twist.twist.linear.x, m.twist.twist.angular.z)
        samples.append((time.monotonic(), *pose, *velocity))

    def cmd(m):
        commands.append((time.monotonic(), m.twist.linear.x, m.twist.angular.z))

    n.create_subscription(String, "/gesture_system/status", status, 1)
    n.create_subscription(Odometry, "/odom", odom, qos_profile_sensor_data)
    n.create_subscription(TwistStamped, "/cmd_vel", cmd, 10)

    def pump(duration):
        end = time.monotonic() + duration
        while time.monotonic() < end:
            if hb:
                h.publish(Bool(data=True))
            rclpy.spin_once(n, timeout_sec=0.02)

    def report(name, **data):
        item = dict(test=name, **data)
        log.append(item)
        print(json.dumps(item), flush=True)

    def event(label):
        g.publish(String(data=label))
        pump(0.15)

    def stationary():
        return abs(velocity[0]) < 0.015 and abs(velocity[1]) < 0.03

    def move(label, expected_cycles):
        event(label)
        assert state.get("state") == "SELECTED", state
        before = pose
        pump(0.6)
        assert math.hypot(pose[0] - before[0], pose[1] - before[1]) < 0.01
        event("THUMBS_UP")
        assert state.get("state") == "EXECUTING", state
        start = time.monotonic()
        start_pose = pose
        begin = len(samples)
        seen_segments = set()
        while state.get("state") == "EXECUTING" and time.monotonic() - start < 100:
            seen_segments.add(state.get("segment"))
            pump(0.1)
        assert state.get("state") == "IDLE", state
        pump(0.7)
        assert stationary(), velocity
        trace = samples[begin:]
        yaw_sum = sum(
            math.atan2(math.sin(b[3] - a[3]), math.cos(b[3] - a[3]))
            for a, b in zip(trace, trace[1:])
        )
        displacement = math.hypot(pose[0] - start_pose[0], pose[1] - start_pose[1])
        assert state.get("completed_cycles") == expected_cycles, state
        if label == "VICTORY":
            assert abs(yaw_sum - 2 * math.pi) < 0.15, yaw_sum
        if label == "POINTING_UP":
            assert displacement < 0.05, displacement
        if label == "WAVE":
            assert abs(yaw_sum) < 0.10, yaw_sum
        report(
            label,
            result="PASS",
            elapsed_s=round(time.monotonic() - start, 3),
            net_distance_m=round(displacement, 4),
            yaw_accumulated_rad=round(yaw_sum, 4),
            cycles=expected_cycles,
            segments=sorted(seen_segments),
        )

    try:
        pump(2)
        assert pose is not None, "No actual odometry"
        assert state, "No controller status; start robot_behavior_node first"
        event("CLOSED_FIST")
        event("THUMBS_UP")
        pump(0.4)
        assert stationary()
        report("confirmation_without_selection", result="PASS")
        for label, cycles in [("POINTING_UP", 4), ("VICTORY", 0), ("WAVE", 0)]:
            move(label, cycles)
        for label, expected in [("OPEN_PALM", "STOPPED"), ("CLOSED_FIST", "IDLE")]:
            event("VICTORY")
            event("THUMBS_UP")
            pump(1)
            assert state.get("state") == "EXECUTING", state
            t = time.monotonic()
            event(label)
            pump(0.5)
            assert state.get("state") == expected, state
            assert stationary(), velocity
            zero = next(
                (c[0] - t for c in commands if c[0] >= t and abs(c[1]) + abs(c[2]) < 1e-7), None
            )
            event("THUMBS_UP")
            pump(0.3)
            assert stationary()
            report(label, result="PASS", first_zero_command_latency_s=zero, no_resume=True)
        event("VICTORY")
        event("THUMBS_UP")
        pump(0.8)
        hb = False
        t = time.monotonic()
        pump(1.5)
        assert state.get("state") == "ERROR", state
        assert stationary(), velocity
        report(
            "heartbeat_expiry",
            result="PASS",
            wait_s=time.monotonic() - t,
            reason=state.get("reason"),
        )
        hb = True
        pump(0.3)
        event("THUMBS_UP")
        pump(0.2)
        assert stationary()
        report("heartbeat_recovery_does_not_resume", result="PASS")
        event("POINTING_UP")
        event("THUMBS_UP")
        pump(0.5)
        h.publish(Bool(data=False))
        hb = False
        pump(0.4)
        assert state.get("state") == "ERROR" and stationary(), (state, velocity)
        report("camera_error_heartbeat_false", result="PASS")
    except Exception as e:
        report("failure", result="FAIL", detail=repr(e), state=state)
        raise
    finally:
        g.publish(String(data="OPEN_PALM"))
        pump(0.3)
        (root / "test_results/integration_results.json").write_text(json.dumps(log, indent=2))
        (root / "test_results/odom_trace.json").write_text(json.dumps(samples))
        n.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
