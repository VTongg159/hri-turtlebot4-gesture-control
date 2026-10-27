"""Temporal event filter and horizontal landmark wave detector."""

from collections import deque
from dataclasses import dataclass

MAPPING = {
    "Pointing_Up": "POINTING_UP",
    "Victory": "VICTORY",
    "Thumb_Up": "THUMBS_UP",
    "Open_Palm": "OPEN_PALM",
    "Closed_Fist": "CLOSED_FIST",
}


@dataclass
class FilterConfig:
    """Confidence, timing and motion thresholds for gesture events."""

    confidence: float = 0.7
    thumb_confidence: float = 0.60
    thumb_hold_time: float = 0.60
    consecutive_frames: int = 4
    smoothing_window: int = 5
    debounce: float = 0.25
    release_time: float = 0.5
    stop_confidence: float = 0.6
    wave_confidence: float = 0.55
    wave_amplitude: float = 0.10
    wave_window: float = 2.0
    wave_reversals: int = 3
    wave_cooldown: float = 2.5
    wave_min_duration: float = 0.45
    wave_gap: float = 0.20

    def __post_init__(self):
        if any(
            not 0 < v <= 1
            for v in (
                self.confidence,
                self.stop_confidence,
                self.thumb_confidence,
                self.wave_confidence,
            )
        ):
            raise ValueError("Confidence must be in (0,1]")
        if not 1 <= self.consecutive_frames <= self.smoothing_window:
            raise ValueError("consecutive_frames must fit smoothing_window")
        for name in (
            "thumb_hold_time",
            "debounce",
            "release_time",
            "wave_amplitude",
            "wave_window",
            "wave_cooldown",
            "wave_min_duration",
            "wave_gap",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.wave_reversals < 2:
            raise ValueError("wave_reversals must be >=2")

    def wave_palm(self, label, confidence):
        return label == "OPEN_PALM" and confidence >= self.wave_confidence

    def threshold_for(self, label):
        if label == "OPEN_PALM":
            return self.stop_confidence
        if label == "THUMBS_UP":
            return self.thumb_confidence
        return self.confidence


class GestureFilter:
    """Validate stable gestures and emit one event per held gesture."""

    def __init__(self, config=None):
        self.c = config or FilterConfig()
        self.history = deque(maxlen=self.c.smoothing_window)
        self.last_event = None
        self.candidate = None
        self.count = 0
        self.candidate_since = 0.0
        self.last_emit = float("-inf")
        self.last_seen = float("-inf")
        self.confirmed = "NONE"

    def update(self, label, confidence, now, hand_present=None):
        # Display current validation, independently of the event latch.
        self.confirmed = "NONE"
        if hand_present is None:
            hand_present = label is not None
        if hand_present:
            self.last_seen = now
        threshold = self.c.threshold_for(label)
        if confidence < threshold or label not in MAPPING.values():
            self.history.clear()
            self.candidate, self.count = None, 0
            if not hand_present and now - self.last_seen >= self.c.release_time:
                self.last_event = None
                self.confirmed = "NONE"
            return None
        self.history.append(label)
        if label != self.candidate:
            self.candidate_since = now
            self.count = 0
        self.count += 1
        self.candidate = label
        # STOP bypasses temporal delay and debounce, but remains edge-triggered.
        valid = label == "OPEN_PALM" or (
            self.count >= self.c.consecutive_frames
            and self.history.count(label) >= self.c.consecutive_frames
            and (label != "THUMBS_UP" or now - self.candidate_since >= self.c.thumb_hold_time)
        )
        if valid:
            self.confirmed = label
        if (
            valid
            and self.last_event != label
            and (label == "OPEN_PALM" or now - self.last_emit >= self.c.debounce)
        ):
            self.last_event, self.last_emit = label, now
            return label
        return None


class WaveDetector:
    """Count horizontal direction reversals with amplitude hysteresis."""

    def __init__(self, config=None):
        self.c = config or FilterConfig()
        self.points = deque()
        self.cooldown_until = 0.0
        self.reversals = 0
        self.span = 0.0
        self.reason = "need_open_palm"

    def reset(self):
        self.points.clear()
        self.reversals, self.span = 0, 0.0

    def update(self, x, y, now, open_palm=True):
        if not open_palm or x is None:
            self.reason = "need_open_palm"
            if self.points and now - self.points[-1][0] <= self.c.wave_gap:
                return False
            self.reset()
            return False
        if self.points and now - self.points[-1][0] > self.c.wave_gap:
            self.reset()
        self.points.append((now, x, y))
        while self.points and now - self.points[0][0] > self.c.wave_window:
            self.points.popleft()
        self.span = max(p[1] for p in self.points) - min(p[1] for p in self.points)
        if now < self.cooldown_until or len(self.points) < 5:
            self.reason = "cooldown" if now < self.cooldown_until else "collecting"
            return False
        if max(p[2] for p in self.points) - min(p[2] for p in self.points) > 0.25:
            self.reset()
            self.reason = "vertical_motion"
            return False
        # Hysteresis counts only full amplitude legs, not frame-level jitter.
        pivot = self.points[0][1]
        direction, reversals = 0, 0
        for _, px, _ in self.points:
            delta = px - pivot
            if direction == 0:
                if abs(delta) >= self.c.wave_amplitude:
                    direction = 1 if delta > 0 else -1
                    pivot = px
            elif direction > 0:
                if px > pivot:
                    pivot = px
                elif pivot - px >= self.c.wave_amplitude:
                    reversals += 1
                    direction, pivot = -1, px
            else:
                if px < pivot:
                    pivot = px
                elif px - pivot >= self.c.wave_amplitude:
                    reversals += 1
                    direction, pivot = 1, px
        self.reversals = reversals
        self.reason = "tracking"
        if (
            reversals >= self.c.wave_reversals
            and now - self.points[0][0] >= self.c.wave_min_duration
        ):
            self.reason = "detected"
            self.cooldown_until = now + self.c.wave_cooldown
            self.reset()
            return True
        return False
