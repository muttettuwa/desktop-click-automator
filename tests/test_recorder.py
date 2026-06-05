"""Unit tests for recorder.py."""

import sys
import time
import threading
import unittest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Stub out pynput before importing recorder so the tests run without a
# real display / Accessibility permission.
# ---------------------------------------------------------------------------


class _FakeListener:
    """Minimal pynput.mouse.Listener stand-in."""

    _instance = None  # most-recently created instance

    def __init__(self, on_click=None):
        self._on_click = on_click
        self.running = False
        _FakeListener._instance = self

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def fire(self, x, y, button, pressed):
        """Helper to simulate a click event in tests."""
        if self._on_click:
            self._on_click(x, y, button, pressed)


class _FakeButton:
    left = "left"


_mock_mouse_module = MagicMock()
_mock_mouse_module.Button = _FakeButton
_mock_mouse_module.Listener = _FakeListener

_mock_pynput = MagicMock()
_mock_pynput.mouse = _mock_mouse_module

sys.modules["pynput"] = _mock_pynput
sys.modules["pynput.mouse"] = _mock_mouse_module

from recorder import ClickRecorder  # noqa: E402  (import after stub)


class TestClickRecorder(unittest.TestCase):
    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _make_recorder(self, cb=None):
        return ClickRecorder(on_click_callback=cb)

    def _fire_left_press(self, recorder, x=100, y=200):
        """Fire a left-button press event through the fake listener."""
        listener = _FakeListener._instance
        listener.fire(x, y, "left", True)

    # ------------------------------------------------------------------
    # tests
    # ------------------------------------------------------------------

    def test_start_clears_previous_clicks(self):
        rec = self._make_recorder()
        rec.start()
        self._fire_left_press(rec, 10, 20)
        rec.stop()
        self.assertEqual(len(rec.get_clicks()), 1)

        rec.start()  # should clear the previous click
        self.assertEqual(rec.get_clicks(), [])
        rec.stop()

    def test_left_press_recorded(self):
        rec = self._make_recorder()
        rec.start()
        self._fire_left_press(rec, 300, 400)
        rec.stop()
        clicks = rec.get_clicks()
        self.assertEqual(len(clicks), 1)
        self.assertEqual(clicks[0]["x"], 300)
        self.assertEqual(clicks[0]["y"], 400)

    def test_right_press_ignored(self):
        rec = self._make_recorder()
        rec.start()
        _FakeListener._instance.fire(10, 20, "right", True)
        rec.stop()
        self.assertEqual(rec.get_clicks(), [])

    def test_release_ignored(self):
        rec = self._make_recorder()
        rec.start()
        _FakeListener._instance.fire(10, 20, "left", False)  # release
        rec.stop()
        self.assertEqual(rec.get_clicks(), [])

    def test_first_click_has_zero_delay(self):
        rec = self._make_recorder()
        rec.start()
        self._fire_left_press(rec, 1, 1)
        rec.stop()
        self.assertEqual(rec.get_clicks()[0]["delay_ms"], 0)

    def test_subsequent_click_has_positive_delay(self):
        rec = self._make_recorder()
        rec.start()
        listener = _FakeListener._instance

        listener.fire(10, 10, "left", True)
        time.sleep(0.05)
        listener.fire(20, 20, "left", True)

        rec.stop()
        clicks = rec.get_clicks()
        self.assertEqual(len(clicks), 2)
        self.assertEqual(clicks[0]["delay_ms"], 0)
        self.assertGreater(clicks[1]["delay_ms"], 0)

    def test_callback_called_for_each_click(self):
        received = []
        rec = self._make_recorder(cb=received.append)
        rec.start()
        listener = _FakeListener._instance
        listener.fire(1, 2, "left", True)
        listener.fire(3, 4, "left", True)
        rec.stop()
        self.assertEqual(len(received), 2)
        self.assertEqual(received[0]["x"], 1)
        self.assertEqual(received[1]["x"], 3)

    def test_get_clicks_returns_copy(self):
        rec = self._make_recorder()
        rec.start()
        self._fire_left_press(rec, 5, 5)
        rec.stop()
        snap = rec.get_clicks()
        snap.clear()
        self.assertEqual(len(rec.get_clicks()), 1)

    def test_stop_sets_recording_false(self):
        rec = self._make_recorder()
        rec.start()
        self.assertTrue(rec.recording)
        rec.stop()
        self.assertFalse(rec.recording)


if __name__ == "__main__":
    unittest.main()
