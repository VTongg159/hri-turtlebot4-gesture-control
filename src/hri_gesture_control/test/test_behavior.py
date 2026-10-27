import math

import pytest
from hri_gesture_control.behavior import Behavior, Config, wrap


def ready():
    b = Behavior()
    b.odometry(0, 0, 0, 0)
    b.heartbeat = 0
    b.connected = True
    return b


def test_confirm_requires_selection_and_valid_health():
    b = ready()
    b.event("THUMBS_UP", 0)
    assert b.tick(0) == (0, 0)
    b.event("POINTING_UP", 0)
    assert b.state == "SELECTED"
    assert b.tick(0) == (0, 0)
    b.event("THUMBS_UP", 0)
    assert b.state == "EXECUTING"
    assert b.tick(0)[0] > 0
    b.event("VICTORY", 0.1)
    b.event("THUMBS_UP", 0.1)
    assert b.active == "BACK_AND_FORTH"


@pytest.mark.parametrize("kind,state", [("OPEN_PALM", "STOPPED"), ("CLOSED_FIST", "CANCELLED")])
def test_interrupt_no_resume(kind, state):
    b = ready()
    b.event("VICTORY", 0)
    b.event("THUMBS_UP", 0)
    b.event(kind, 0.1)
    assert b.state == state
    assert b.active is None
    assert b.tick(0.1) == (0, 0)
    b.event("THUMBS_UP", 0.2)
    assert b.tick(0.2) == (0, 0)
    if kind == "CLOSED_FIST":
        assert b.state == "IDLE"


@pytest.mark.parametrize("failure", ["heartbeat", "odom", "connection"])
def test_watchdogs(failure):
    b = ready()
    b.event("WAVE", 0)
    b.event("THUMBS_UP", 0)
    if failure == "heartbeat":
        b.odom_time = 1
    elif failure == "odom":
        b.heartbeat = 1
    else:
        b.connected = False
        b.heartbeat = b.odom_time = 1
    assert b.tick(1) == (0, 0)
    assert b.state == "ERROR"


def test_selection_expiry_and_stale_confirm():
    b = ready()
    b.event("VICTORY", 0)
    b.event("THUMBS_UP", 11)
    assert b.state == "IDLE"
    assert b.tick(11) == (0, 0)


@pytest.mark.parametrize(
    "label,expected_segments,cycles", [("POINTING_UP", 8, 4), ("WAVE", 3, 0), ("VICTORY", 1, 0)]
)
def test_odometry_feedback_completes_motion(label, expected_segments, cycles):
    b = ready()
    b.event(label, 0)
    b.event("THUMBS_UP", 0)
    assert len(b.segments) == expected_segments
    x = y = yaw = 0.0
    dt = 0.02
    t = 0
    maximum_v = maximum_w = 0
    for _ in range(20000):
        b.heartbeat = t
        b.odometry(x, y, wrap(yaw), t)
        v, w = b.tick(t)
        maximum_v = max(maximum_v, abs(v))
        maximum_w = max(maximum_w, abs(w))
        x += v * math.cos(yaw) * dt
        y += v * math.sin(yaw) * dt
        yaw += w * dt
        t += dt
        if b.state != "EXECUTING":
            break
    assert b.state == "IDLE", b.reason
    assert b.completed_cycles == cycles
    assert b.tick(t) == (0, 0)
    assert maximum_v <= b.c.linear_speed + 1e-9
    assert maximum_w <= b.c.angular_speed + 1e-9
    if label == "POINTING_UP":
        assert math.hypot(x, y) < 0.03
    if label == "WAVE":
        assert abs(yaw) < 0.04
    if label == "VICTORY":
        assert abs(yaw - 2 * math.pi) < 0.04


def test_odom_jump_and_stall():
    b = ready()
    b.event("POINTING_UP", 0)
    b.event("THUMBS_UP", 0)
    b.odometry(5, 0, 0, 0.1)
    assert b.state == "ERROR"
    assert b.tick(0.1) == (0, 0)
    b = ready()
    b.event("VICTORY", 0)
    b.event("THUMBS_UP", 0)
    b.heartbeat = b.odom_time = 46
    assert b.tick(46) == (0, 0)
    assert b.state == "ERROR"


@pytest.mark.parametrize(
    "kwargs", [{"linear_speed": 1.0}, {"radius": 0}, {"distance": float("nan")}, {"distance": 0.01}]
)
def test_parameter_validation(kwargs):
    with pytest.raises(ValueError):
        Config(**kwargs)
