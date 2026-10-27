import math

import pytest
from hri_gesture_control.gesture_filters import MAPPING, FilterConfig, GestureFilter, WaveDetector


@pytest.mark.parametrize("label", list(MAPPING.values()))
def test_static_edges_and_release(label):
    f = GestureFilter()
    events = []
    for i in range(30):
        e = f.update(label, 0.95, i * 0.067)
        if e:
            events.append(e)
    assert events == [label]
    f.update(None, 0, 3)
    f.update(None, 0, 3.6)
    events = [f.update(label, 0.95, 4 + i * 0.067) for i in range(12)]
    assert events.count(label) == 1


def test_stop_immediate_bypass_debounce():
    f = GestureFilter()
    for i in range(4):
        f.update("THUMBS_UP", 0.9, i * 0.05)
    assert f.update("OPEN_PALM", 0.65, 0.16) == "OPEN_PALM"


def test_noise_low_confidence_and_alternation():
    f = GestureFilter()
    for i in range(100):
        assert f.update("VICTORY", 0.2, i * 0.1) is None
        assert f.update(["VICTORY", "THUMBS_UP"][i % 2], 0.9, i * 0.1 + 0.01) is None


def test_wave_stationary_and_small_jitter():
    w = WaveDetector()
    for i in range(100):
        assert not w.update(0.5 + 0.015 * math.sin(i), 0.5, i * 0.05)


def test_wave_large_alternating_and_cooldown():
    w = WaveDetector()
    detected = []
    for i in range(100):
        t = i * 0.05
        if w.update(0.5 + 0.15 * math.sin(2 * math.pi * 2 * t), 0.5, t):
            detected.append(t)
    assert detected
    assert all(b - a >= w.c.wave_cooldown for a, b in zip(detected, detected[1:]))


def test_wave_requires_palm_and_vertical_stability():
    w = WaveDetector()
    for i in range(100):
        assert not w.update(0.5 + 0.2 * math.sin(i), 0.5, i * 0.05, False)
    for i in range(100):
        assert not w.update(0.5 + 0.2 * math.sin(i), 0.2 if i % 2 else 0.8, 5 + i * 0.05)


def test_no_hand_resets_wave_history():
    w = WaveDetector()
    w.update(0.2, 0.5, 0)
    w.update(None, None, 0.3, False)
    assert not w.points


def test_uncertain_hand_does_not_rearm_held_gesture():
    f = GestureFilter()
    assert [f.update("VICTORY", 0.9, i * 0.1) for i in range(5)].count("VICTORY") == 1
    for i in range(20):
        assert f.update(None, 0.1, 1 + i * 0.1, hand_present=True) is None
    assert all(f.update("VICTORY", 0.9, 4 + i * 0.1) is None for i in range(8))
    f.update(None, 0, 6, hand_present=False)
    assert [f.update("VICTORY", 0.9, 7 + i * 0.1) for i in range(5)].count("VICTORY") == 1


def test_brief_palm_dropout_preserves_wave_history():
    w = WaveDetector()
    w.update(0.2, 0.5, 0)
    w.update(0.4, 0.5, 0.05)
    w.update(None, None, 0.1, False)
    assert len(w.points) == 2
    w.update(None, None, 0.4, False)
    assert not w.points


def test_filtered_display_does_not_show_stale_gesture():
    f = GestureFilter()
    for i in range(5):
        f.update("POINTING_UP", 0.95, i * 0.1)
    assert f.confirmed == "POINTING_UP"
    assert f.update("THUMBS_UP", 0.55, 0.6, hand_present=True) is None
    assert f.confirmed == "NONE"
    assert f.last_event == "POINTING_UP"
    for i in range(5):
        assert f.update("POINTING_UP", 0.95, 0.8 + i * 0.1) is None


def test_thumb_moderate_confidence_needs_sustained_hold():
    f = GestureFilter()
    for i in range(9):
        assert f.update("THUMBS_UP", 0.65, i * 0.067) is None
    assert f.update("THUMBS_UP", 0.65, 0.67) == "THUMBS_UP"
    assert f.confirmed == "THUMBS_UP"
    for i in range(20):
        assert f.update("THUMBS_UP", 0.65, 0.8 + i * 0.067) is None


def test_thumb_hold_resets_on_dropout_and_other_labels_stay_strict():
    f = GestureFilter()
    for i in range(7):
        assert f.update("THUMBS_UP", 0.65, i * 0.067) is None
    assert f.update("THUMBS_UP", 0.59, 0.5, hand_present=True) is None
    for i in range(8):
        assert f.update("THUMBS_UP", 0.65, 0.6 + i * 0.067) is None
    assert f.update("THUMBS_UP", 0.65, 1.3) == "THUMBS_UP"
    for i in range(20):
        assert f.update("POINTING_UP", 0.65, 2 + i * 0.067) is None
    assert f.update("OPEN_PALM", 0.61, 3.4) == "OPEN_PALM"


def test_wave_gate_accepts_open_palm_below_static_selection_threshold():
    cfg = FilterConfig()
    assert cfg.wave_palm("OPEN_PALM", 0.60)
    assert not cfg.wave_palm("OPEN_PALM", 0.54)
    assert not cfg.wave_palm("POINTING_UP", 0.99)
    w = WaveDetector(cfg)
    detected = []
    for i in range(45):
        t = i * 0.067
        detected.append(
            w.update(
                0.5 + 0.15 * math.sin(2 * math.pi * 2 * t), 0.5, t, cfg.wave_palm("OPEN_PALM", 0.64)
            )
        )
    assert any(detected)


def test_lower_wave_gate_does_not_create_stationary_wave_or_static_selection():
    cfg = FilterConfig()
    w = WaveDetector(cfg)
    f = GestureFilter(cfg)
    events = []
    for i in range(80):
        t = i * 0.067
        assert not w.update(0.5 + 0.01 * math.sin(i), 0.5, t, cfg.wave_palm("OPEN_PALM", 0.56))
        event = f.update("OPEN_PALM", 0.56, t)
        if event:
            events.append(event)
    assert events == []
    assert f.update("OPEN_PALM", 0.61, 6) == "OPEN_PALM"
