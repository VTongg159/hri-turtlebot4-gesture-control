"""Shared ROS quality-of-service profile for short-lived gesture events."""

from rclpy.duration import Duration
from rclpy.qos import QoSProfile, ReliabilityPolicy


def event_qos():
    """Keep only the newest event and expire queued events after 0.3 seconds."""
    return QoSProfile(
        depth=1,
        reliability=ReliabilityPolicy.RELIABLE,
        lifespan=Duration(seconds=0.3),
    )
