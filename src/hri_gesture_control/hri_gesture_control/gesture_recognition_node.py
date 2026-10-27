"""Real webcam + MediaPipe Tasks VIDEO mode; heartbeat follows successful inference."""

import json
import time
from dataclasses import fields
from pathlib import Path

import cv2
import mediapipe as mp
import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import Bool, String

from .gesture_filters import MAPPING, FilterConfig, GestureFilter, WaveDetector
from .qos import event_qos


class GestureRecognitionNode(Node):
    def __init__(self):
        super().__init__("gesture_recognition_node")
        for f in fields(FilterConfig):
            self.declare_parameter(f.name, f.default)
        defaults = dict(
            camera_device=0,
            width=640,
            height=480,
            inference_hz=15.0,
            display=True,
            model_path="",
            mirror=True,
        )
        for name, value in defaults.items():
            self.declare_parameter(name, value)
        self.cfg = FilterConfig(
            **{f.name: self.get_parameter(f.name).value for f in fields(FilterConfig)}
        )
        self.filter, self.wave = GestureFilter(self.cfg), WaveDetector(self.cfg)
        self.event_pub = self.create_publisher(String, "/detected_gesture", event_qos())
        self.diagnostic_pub = self.create_publisher(
            String, "/gesture_system/recognition", qos_profile_sensor_data
        )
        self.hb_pub = self.create_publisher(
            Bool, "/gesture_system/heartbeat", qos_profile_sensor_data
        )
        self.status = dict(state="UNKNOWN", selected=None, active=None, reason="Connecting")
        self.create_subscription(String, "/gesture_system/status", self.on_status, 1)
        self.cap = None
        self.recognizer = None
        self.show = self.get_parameter("display").value
        self.last_timestamp = 0
        self.previous_time = time.monotonic()
        self.fps = 0.0
        self.wave_latched = False
        self.last_hand_seen = float("-inf")
        model = self.get_parameter("model_path").value
        if not model:
            model = str(
                Path(get_package_share_directory("hri_gesture_control"))
                / "models/gesture_recognizer.task"
            )
        if not Path(model).is_file():
            raise FileNotFoundError(
                f"Missing model: {model}; run scripts/download_model.sh then rebuild"
            )
        options = mp.tasks.vision.GestureRecognizerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=model),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=self.cfg.confidence,
            min_hand_presence_confidence=self.cfg.confidence,
            min_tracking_confidence=self.cfg.confidence,
        )
        self.recognizer = mp.tasks.vision.GestureRecognizer.create_from_options(options)
        self.cap = cv2.VideoCapture(self.get_parameter("camera_device").value, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            self.close()
            raise RuntimeError(
                "Cannot open webcam (check /dev/video*, access or other camera apps)"
            )
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.get_parameter("width").value)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.get_parameter("height").value)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        hz = self.get_parameter("inference_hz").value
        if not 1 <= hz <= 60:
            self.close()
            raise ValueError("inference_hz must be in [1,60]")
        if self.show:
            cv2.namedWindow("HRI Week 6 - TurtleBot 4", cv2.WINDOW_AUTOSIZE)
        self.steady = Clock(clock_type=ClockType.STEADY_TIME)
        self.create_timer(1.0 / hz, self.frame, clock=self.steady)
        self.get_logger().info(f"Camera opened; MediaPipe model: {model}")

    def on_status(self, msg):
        try:
            self.status = json.loads(msg.data)
        except (ValueError, TypeError):
            pass

    def emit(self, label):
        self.event_pub.publish(String(data=label))
        self.get_logger().info("Gesture event: " + label)

    def frame(self):
        try:
            ok, frame = self.cap.read()
            if not ok:
                raise RuntimeError("Webcam frame read failed")
            if self.get_parameter("mirror").value:
                frame = cv2.flip(frame, 1)
            now = time.monotonic()
            ts = max(self.last_timestamp + 1, int(now * 1000))
            self.last_timestamp = ts
            result = self.recognizer.recognize_for_video(
                mp.Image(
                    image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                ),
                ts,
            )
            # Never send heartbeat from an independent timer: a blocked camera/inference must time out.
            self.hb_pub.publish(Bool(data=True))
            raw, score, label = "None", 0.0, None
            if result.gestures and result.gestures[0]:
                category = result.gestures[0][0]
                raw, score = category.category_name, float(category.score)
                label = MAPPING.get(raw)
            hand_present = bool(result.hand_landmarks)
            if hand_present:
                self.last_hand_seen = now
            event = self.filter.update(label, score, now, hand_present=hand_present)
            if event:
                self.emit(event)
            palm = self.cfg.wave_palm(label, score)
            if (not hand_present and now - self.last_hand_seen >= self.cfg.release_time) or (
                event and event != "OPEN_PALM"
            ):
                self.wave_latched = False
            if label not in (None, "OPEN_PALM") and score >= self.cfg.confidence:
                self.wave.reset()
            wave = False
            x = y = None
            if result.hand_landmarks:
                hand = result.hand_landmarks[0]
                # MCP centres are less sensitive to finger articulation than fingertips.
                x = sum(hand[i].x for i in (0, 5, 9, 13, 17)) / 5
                y = sum(hand[i].y for i in (0, 5, 9, 13, 17)) / 5
                wave = self.wave.update(x, y, now, palm)
                h, w = frame.shape[:2]
                for a, b in mp.solutions.hands.HAND_CONNECTIONS:
                    pa, pb = hand[a], hand[b]
                    cv2.line(
                        frame,
                        (int(pa.x * w), int(pa.y * h)),
                        (int(pb.x * w), int(pb.y * h)),
                        (0, 220, 0),
                        2,
                    )
                for p in hand:
                    cv2.circle(frame, (int(p.x * w), int(p.y * h)), 3, (0, 0, 255), -1)
            else:
                self.wave.update(None, None, now, False)
            if wave and not self.wave_latched and self.status.get("state") != "EXECUTING":
                self.emit("WAVE")
                self.wave_latched = True
            self.diagnostic_pub.publish(
                String(
                    data=json.dumps(
                        dict(
                            raw=raw,
                            score=score,
                            hand_present=hand_present,
                            x=x,
                            y=y,
                            wave_span=self.wave.span,
                            wave_reversals=self.wave.reversals,
                            wave_reason=self.wave.reason,
                            wave_samples=len(self.wave.points),
                            wave_gate_confidence=self.cfg.wave_confidence,
                            threshold=self.cfg.threshold_for(label),
                            stable_for_s=max(0.0, now - self.filter.candidate_since)
                            if self.filter.candidate
                            else 0.0,
                            landmarks=[[p.x, p.y, p.z] for p in result.hand_landmarks[0]]
                            if hand_present
                            else [],
                        )
                    )
                )
            )
            self.fps = 0.8 * self.fps + 0.2 / max(0.001, now - self.previous_time)
            self.previous_time = now
            if self.show:
                hint = str(self.status.get("reason", ""))[:75]
                if self.status.get("state") == "SELECTED":
                    hint = f"Confirm: THUMB UP | score >= {self.cfg.thumb_confidence:.2f}, hold {self.cfg.thumb_hold_time:.1f}s"
                lines = [
                    f"Raw: {raw}  score={score:.2f}  threshold={self.cfg.threshold_for(label):.2f}",
                    f"Wave: span={self.wave.span:.2f}/{self.cfg.wave_amplitude:.2f} turns={self.wave.reversals}/{self.cfg.wave_reversals} min_score={self.cfg.wave_confidence:.2f}",
                    f"Filtered: {'WAVE' if self.wave_latched else self.filter.confirmed}",
                    f"State: {self.status.get('state')}  FPS: {self.fps:.1f}",
                    f"Selected: {self.status.get('selected')}",
                    f"Executing: {self.status.get('active')}  cycles: {self.status.get('completed_cycles', 0)}",
                    hint,
                    "OPEN PALM=STOP | FIST=CANCEL | close window=shutdown",
                ]
                cv2.rectangle(frame, (0, 0), (frame.shape[1], 200), (20, 20, 20), -1)
                for i, line in enumerate(lines):
                    color = (
                        (0, 100, 255)
                        if self.status.get("state") in ("STOPPED", "ERROR")
                        else (255, 255, 255)
                    )
                    cv2.putText(
                        frame,
                        line,
                        (8, 22 + 23 * i),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.47,
                        color,
                        1,
                        cv2.LINE_AA,
                    )
                cv2.imshow("HRI Week 6 - TurtleBot 4", frame)
                cv2.waitKey(1)  # GUI refresh only; no keyboard velocity commands.
                if cv2.getWindowProperty("HRI Week 6 - TurtleBot 4", cv2.WND_PROP_VISIBLE) < 1:
                    raise KeyboardInterrupt
        except Exception:
            self.hb_pub.publish(Bool(data=False))
            raise

    def close(self):
        if rclpy.ok() and hasattr(self, "hb_pub"):
            self.hb_pub.publish(Bool(data=False))
        if self.cap is not None:
            self.cap.release()
        if self.recognizer is not None:
            self.recognizer.close()
        if self.show:
            cv2.destroyAllWindows()


def main(args=None):
    import signal

    from rclpy.signals import SignalHandlerOptions

    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)

    def terminate(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminate)
    node = None
    try:
        node = GestureRecognitionNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node:
            node.close()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
