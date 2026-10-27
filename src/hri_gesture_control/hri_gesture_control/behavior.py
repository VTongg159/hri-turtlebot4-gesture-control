"""ROS-independent safety state machine and odometry motion controller."""

import math
from dataclasses import dataclass


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


@dataclass
class Config:
    """Safe motion limits and watchdog timeouts."""

    linear_speed: float = 0.12
    angular_speed: float = 0.45
    distance: float = 0.30
    radius: float = 0.45
    greeting_angle: float = 0.55
    position_tolerance: float = 0.025
    angle_tolerance: float = 0.035
    heartbeat_timeout: float = 0.8
    odom_timeout: float = 0.6
    selection_timeout: float = 10.0
    segment_timeout: float = 45.0

    def __post_init__(self):
        for k, v in vars(self).items():
            if not math.isfinite(v) or v <= 0:
                raise ValueError(f"{k} must be positive and finite")
        if self.linear_speed > 0.25 or self.angular_speed > 0.8:
            raise ValueError("Velocity exceeds classroom safety limits")
        if self.distance <= self.position_tolerance or self.greeting_angle <= self.angle_tolerance:
            raise ValueError("Motion must exceed tolerance")


class Behavior:
    """Manage one selection and one odometry-driven motion at a time."""

    choices = {"WAVE": "GREETING", "POINTING_UP": "BACK_AND_FORTH", "VICTORY": "CIRCLE"}

    def __init__(self, config=None):
        self.c = config or Config()
        self.state, self.selected, self.active = "IDLE", None, None
        self.reason = "Waiting for selection"
        self.heartbeat = self.odom_time = None
        self.pose = None
        self.yaw = 0.0
        self.previous_yaw = None
        self.connected = False
        self.segments = []
        self.segment = 0
        self.completed_cycles = 0
        self.selected_at = self.started_at = 0.0

    def health(self, now):
        if self.heartbeat is None or now - self.heartbeat > self.c.heartbeat_timeout:
            return "Recognition/camera heartbeat expired"
        if self.odom_time is None or now - self.odom_time > self.c.odom_timeout:
            return "Odometry expired"
        if not self.connected:
            return "Velocity subscriber disconnected"
        return ""

    def odometry(self, x, y, yaw, now):
        if not all(math.isfinite(v) for v in (x, y, yaw)):
            self.stop("ERROR", "Invalid odometry")
            return
        if self.previous_yaw is not None:
            delta = wrap(yaw - self.previous_yaw)
            if self.state == "EXECUTING" and (
                abs(delta) > 0.7 or math.hypot(x - self.pose[0], y - self.pose[1]) > 0.5
            ):
                self.stop("ERROR", "Odometry discontinuity")
            self.yaw += delta
        self.previous_yaw = yaw
        self.pose = (x, y, yaw)
        self.odom_time = now

    def stop(self, state, reason):
        self.state, self.reason = state, reason
        self.active = self.selected = None
        self.segments = []
        self.segment = 0

    def event(self, label, now):
        if label == "OPEN_PALM":
            self.stop("STOPPED", "OPEN_PALM: immediate stop; select again to restart")
            return
        if label == "CLOSED_FIST":
            self.stop("CANCELLED", "CLOSED_FIST: cancelled")
            return
        if self.state == "EXECUTING":
            return
        if label in self.choices:
            self.selected, self.selected_at = self.choices[label], now
            self.state, self.reason = "SELECTED", "Waiting for THUMBS_UP"
        elif label == "THUMBS_UP" and self.state == "SELECTED":
            problem = self.health(now)
            if now - self.selected_at > self.c.selection_timeout:
                self.stop("IDLE", "Selection expired")
            elif problem:
                self.stop("ERROR", problem)
            else:
                self.start(now)

    def start(self, now):
        self.active, self.selected = self.selected, None
        self.state, self.reason = "EXECUTING", "Motion in progress"
        x, y, heading = self.pose
        self.anchor = (x, y, heading)
        self.completed_cycles = 0
        if self.active == "GREETING":
            self.segments = [
                ("turn", self.yaw + a) for a in (self.c.greeting_angle, -self.c.greeting_angle, 0.0)
            ]
        elif self.active == "CIRCLE":
            self.segments = [("circle", self.yaw + 2 * math.pi)]
        else:
            far = (x + self.c.distance * math.cos(heading), y + self.c.distance * math.sin(heading))
            self.segments = [("position", far), ("position", (x, y))] * 4
        self.segment, self.started_at = 0, now

    def tick(self, now):
        if self.state == "CANCELLED":
            self.state = "IDLE"
        if self.state == "SELECTED" and now - self.selected_at > self.c.selection_timeout:
            self.stop("IDLE", "Selection expired")
        if self.state != "EXECUTING":
            return 0.0, 0.0
        problem = self.health(now)
        if problem:
            self.stop("ERROR", problem)
            return 0.0, 0.0
        if now - self.started_at > self.c.segment_timeout:
            self.stop("ERROR", "Motion timeout / robot stalled")
            return 0.0, 0.0
        kind, target = self.segments[self.segment]
        v = w = 0.0
        if kind == "position":
            x, y, heading = self.pose
            dx, dy = target[0] - x, target[1] - y
            remaining = dx * math.cos(self.anchor[2]) + dy * math.sin(self.anchor[2])
            reached = math.hypot(dx, dy) < self.c.position_tolerance
            # Fail closed if the robot strays sideways instead of counting a cycle.
            lateral = -dx * math.sin(self.anchor[2]) + dy * math.cos(self.anchor[2])
            if abs(lateral) > 0.12:
                self.stop("ERROR", "Excessive lateral tracking error")
                return 0.0, 0.0
            v = max(-self.c.linear_speed, min(self.c.linear_speed, 1.2 * remaining))
            w = max(
                -self.c.angular_speed,
                min(self.c.angular_speed, 1.5 * wrap(self.anchor[2] - heading)),
            )
        else:
            error = target - self.yaw
            reached = abs(error) < self.c.angle_tolerance or (kind == "circle" and error < 0)
            w = max(-self.c.angular_speed, min(self.c.angular_speed, 1.5 * error))
            if kind == "circle":
                w = min(self.c.linear_speed / self.c.radius, self.c.angular_speed, max(0.05, error))
                v = self.c.radius * w
        if reached:
            self.segment += 1
            if self.active == "BACK_AND_FORTH":
                self.completed_cycles = self.segment // 2
            self.started_at = now
            if self.segment == len(self.segments):
                self.stop("IDLE", "Motion completed")
            return 0.0, 0.0
        return v, w

    def status(self):
        return dict(
            state=self.state,
            selected=self.selected,
            active=self.active,
            segment=self.segment,
            completed_cycles=self.completed_cycles,
            reason=self.reason,
        )
