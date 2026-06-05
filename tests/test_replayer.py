"""Unit tests for replayer.py."""

import sys
import time
import threading
import unittest
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Stub pyautogui before importing replayer.
# ---------------------------------------------------------------------------
_mock_pyautogui = MagicMock()
_mock_pyautogui.FAILSAFE = True
sys.modules["pyautogui"] = _mock_pyautogui

from replayer import ClickReplayer  # noqa: E402


def _make_clicks(*coords):
    """Return a list of click dicts with zero delay."""
    return [{"x": x, "y": y, "delay_ms": 0} for x, y in coords]


class TestClickReplayer(unittest.TestCase):
    def setUp(self):
        _mock_pyautogui.reset_mock()

    # ------------------------------------------------------------------

    def test_replay_calls_click_for_each_step(self):
        rep = ClickReplayer()
        clicks = _make_clicks((100, 200), (300, 400))
        rep.replay(clicks)
        self.assertEqual(_mock_pyautogui.click.call_count, 2)
        _mock_pyautogui.click.assert_any_call(100, 200)
        _mock_pyautogui.click.assert_any_call(300, 400)

    def test_replay_empty_list(self):
        rep = ClickReplayer()
        rep.replay([])
        _mock_pyautogui.click.assert_not_called()

    def test_on_step_callback_called(self):
        steps = []
        rep = ClickReplayer(on_step_callback=lambda i, c: steps.append((i, c["x"])))
        clicks = _make_clicks((10, 20), (30, 40))
        rep.replay(clicks)
        self.assertEqual(steps, [(0, 10), (1, 30)])

    def test_on_done_callback_called(self):
        done = []
        rep = ClickReplayer(on_done_callback=lambda: done.append(True))
        rep.replay(_make_clicks((1, 2)))
        self.assertEqual(done, [True])

    def test_on_done_called_even_when_stopped(self):
        done = []
        rep = ClickReplayer(on_done_callback=lambda: done.append(True))
        rep.stop()  # pre-set stop flag
        rep.replay(_make_clicks((1, 2)))
        self.assertEqual(done, [True])

    def test_stop_interrupts_replay(self):
        """Stop the replayer mid-sequence from another thread."""
        step_count = []
        barrier = threading.Barrier(2)

        def on_step(i, c):
            step_count.append(i)
            if i == 0:
                barrier.wait()   # signal stopper thread
                time.sleep(0.1)  # give stopper time to set flag

        # 5 clicks each with 0 delay so only the step callback delays things
        clicks = [{"x": j, "y": j, "delay_ms": 0} for j in range(5)]
        rep = ClickReplayer(on_step_callback=on_step)

        def stopper():
            barrier.wait()
            rep.stop()

        t = threading.Thread(target=stopper, daemon=True)
        t.start()
        rep.replay(clicks)
        t.join(timeout=2)

        # At most 2 steps should have executed (step 0 and possibly step 1)
        self.assertLessEqual(len(step_count), 2)

    def test_delay_applied_between_clicks(self):
        """delay_ms causes a measurable pause before the click."""
        rep = ClickReplayer()
        clicks = [
            {"x": 0, "y": 0, "delay_ms": 0},
            {"x": 1, "y": 1, "delay_ms": 100},  # 100 ms delay
        ]
        t0 = time.monotonic()
        rep.replay(clicks)
        elapsed_ms = (time.monotonic() - t0) * 1000
        self.assertGreaterEqual(elapsed_ms, 90)  # allow small timing slack

    def test_negative_delay_treated_as_zero(self):
        """Negative delay_ms must not raise an error."""
        rep = ClickReplayer()
        clicks = [{"x": 5, "y": 5, "delay_ms": -50}]
        rep.replay(clicks)  # should not raise
        _mock_pyautogui.click.assert_called_once_with(5, 5)


if __name__ == "__main__":
    unittest.main()
