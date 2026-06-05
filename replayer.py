"""Click replayer – executes a recorded click sequence with per-step delays."""

import threading
import time

import pyautogui

# Move mouse to a corner to abort replay (pyautogui safety feature).
pyautogui.FAILSAFE = True

_MS_TO_SECONDS = 1000.0
_STOP_CHECK_INTERVAL_S = 0.05


class ClickReplayer:
    """Replays a list of click dicts produced by ClickRecorder."""

    def __init__(self, on_step_callback=None, on_done_callback=None):
        """
        Args:
            on_step_callback: Optional callable(step_index, click_dict) called
                              after each click is executed.
            on_done_callback: Optional callable() called when replay finishes
                              (normally or after stop()).
        """
        self._on_step = on_step_callback
        self._on_done = on_done_callback
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def replay(self, clicks):
        """Replay *clicks* synchronously in the calling thread.

        Each click dict must contain::

            {"x": int, "y": int, "delay_ms": int}

        The ``delay_ms`` value is waited **before** the click is fired,
        matching the inter-click timing captured during recording.
        """
        self._stop_event.clear()
        try:
            for i, click in enumerate(clicks):
                if self._stop_event.is_set():
                    break
                delay_s = max(0, click.get("delay_ms", 0)) / _MS_TO_SECONDS
                if delay_s > 0:
                    # Use small slices so we can respond to stop() quickly.
                    deadline = time.monotonic() + delay_s
                    while time.monotonic() < deadline:
                        if self._stop_event.is_set():
                            break
                        time.sleep(min(_STOP_CHECK_INTERVAL_S, deadline - time.monotonic()))
                if self._stop_event.is_set():
                    break
                pyautogui.click(click["x"], click["y"])
                if self._on_step:
                    self._on_step(i, click)
        finally:
            if self._on_done:
                self._on_done()

    def stop(self):
        """Request an in-progress replay to stop after the current step."""
        self._stop_event.set()
