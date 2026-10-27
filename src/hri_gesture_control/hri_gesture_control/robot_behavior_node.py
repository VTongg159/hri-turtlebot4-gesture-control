"""Nonblocking ROS adapter. All watchdog intervals use a steady clock."""

import json
import math
import time
from dataclasses import fields

import rclpy
from geometry_msgs.msg import Twist, TwistStamped
from nav_msgs.msg import Odometry
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import Bool, String

from .behavior import Behavior, Config
from .qos import event_qos


class RobotBehaviorNode(Node):
    def __init__(self):
        super().__init__("robot_behavior_node")
        for f in fields(Config):
            self.declare_parameter(f.name, f.default)
        for name, default in dict(
            cmd_vel_topic="/cmd_vel", odom_topic="/odom", velocity_type="auto", control_hz=25.0
        ).items():
            self.declare_parameter(name, default)
        self.machine = Behavior(
            Config(**{f.name: self.get_parameter(f.name).value for f in fields(Config)})
        )
        self.cmd_topic = self.resolve_topic_name(self.get_parameter("cmd_vel_topic").value)
        self.mode = self.get_parameter("velocity_type").value
        if self.mode not in ("auto", "Twist", "TwistStamped"):
            raise ValueError("velocity_type must be auto, Twist or TwistStamped")
        hz = self.get_parameter("control_hz").value
        if not 5 <= hz <= 100:
            raise ValueError("control_hz must be in [5,100]")
        self.velocity_pub = None
        self.velocity_class = None
        self.status_pub = self.create_publisher(String, "/gesture_system/status", 1)
        self.create_subscription(String, "/detected_gesture", self.gesture, event_qos())
        self.create_subscription(
            Bool, "/gesture_system/heartbeat", self.heartbeat, qos_profile_sensor_data
        )
        self.create_subscription(
            Odometry, self.get_parameter("odom_topic").value, self.odom, qos_profile_sensor_data
        )
        self.steady_clock = Clock(clock_type=ClockType.STEADY_TIME)
        self.create_timer(1.0 / hz, self.control, clock=self.steady_clock)
        self.last_discovery = float("-inf")
        self.last_status = None
        self.last_odom_stamp = None

    def discover(self):
        endpoints = self.get_subscriptions_info_by_topic(self.cmd_topic)
        types = {e.topic_type for e in endpoints}
        supported = {
            "geometry_msgs/msg/Twist": Twist,
            "geometry_msgs/msg/TwistStamped": TwistStamped,
        }
        if len(types) != 1 or not types <= supported.keys():
            self.machine.connected = False
            return
        actual = next(iter(types))
        if self.mode != "auto" and actual != "geometry_msgs/msg/" + self.mode:
            self.machine.connected = False
            self.machine.stop("ERROR", "Configured velocity type does not match robot")
            return
        cls = supported[actual]
        if self.velocity_class is not None and self.velocity_class != cls:
            self.machine.stop("ERROR", "Velocity interface changed; restart controller")
            self.machine.connected = False
            return
        if self.velocity_pub is None:
            self.velocity_class = cls
            self.velocity_pub = self.create_publisher(cls, self.cmd_topic, 1)
            self.get_logger().info(f"Verified robot subscriber: {self.cmd_topic} [{actual}]")
        self.machine.connected = self.velocity_pub.get_subscription_count() > 0

    def heartbeat(self, msg):
        if msg.data:
            self.machine.heartbeat = time.monotonic()
        else:
            self.machine.heartbeat = None
            self.machine.stop("ERROR", "Recognition reports camera/inference failure")
            self.publish_velocity(0.0, 0.0)

    def gesture(self, msg):
        self.machine.event(msg.data, time.monotonic())
        if self.machine.state != "EXECUTING":
            self.publish_velocity(0.0, 0.0)
        self.publish_status()

    def odom(self, msg):
        # Repeated old odometry does not refresh the watchdog (e.g. paused simulator).
        stamp = (msg.header.stamp.sec, msg.header.stamp.nanosec)
        if stamp == self.last_odom_stamp:
            return
        self.last_odom_stamp = stamp
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        self.machine.odometry(p.x, p.y, yaw, time.monotonic())

    def publish_velocity(self, v, w):
        if self.velocity_pub is None:
            return
        msg = self.velocity_class()
        twist = msg.twist if self.velocity_class == TwistStamped else msg
        if self.velocity_class == TwistStamped:
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = "base_link"
        twist.linear.x, twist.angular.z = float(v), float(w)
        self.velocity_pub.publish(msg)

    def publish_status(self):
        data = json.dumps(self.machine.status(), sort_keys=True)
        self.status_pub.publish(String(data=data))
        if data != self.last_status:
            self.get_logger().info(data)
            self.last_status = data

    def control(self):
        now = time.monotonic()
        if now - self.last_discovery > 0.25:
            self.discover()
            self.last_discovery = now
        if self.velocity_pub:
            self.machine.connected = (
                self.machine.connected and self.velocity_pub.get_subscription_count() > 0
            )
        self.publish_velocity(*self.machine.tick(now))
        self.publish_status()

    def close(self):
        self.machine.stop("STOPPED", "Controller shutdown")
        # Best effort while the ROS context is still valid; downstream timeout covers SIGKILL.
        if rclpy.ok():
            for _ in range(5):
                self.publish_velocity(0.0, 0.0)
            self.publish_status()


def main(args=None):
    from rclpy.signals import SignalHandlerOptions

    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    import signal

    def terminate(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminate)
    node = None
    try:
        node = RobotBehaviorNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node:
            node.close()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
