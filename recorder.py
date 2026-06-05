"""Mouse-click recorder using pynput global listener."""

import threading
import time

from pynput import mouse


class ClickRecorder:
    """Records global left-mouse-button click positions and inter-click delays."""

    def __init__(self, on_click_callback=None):
        """
        Args:
            on_click_callback: Optional callable(click_dict) invoked on each
                               recorded click from the listener thread.
        """
        self.clicks = []
        self.recording = False
        self._listener = None
        self._last_time = None
        self._on_click = on_click_callback
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Start recording.  Clears any previously recorded clicks."""
        with self._lock:
            self.clicks = []
            self._last_time = None
        self.recording = True
        self._listener = mouse.Listener(on_click=self._handle_click)
        self._listener.start()

    def stop(self):
        """Stop recording."""
        self.recording = False
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def get_clicks(self):
        """Return a snapshot of the recorded clicks list."""
        with self._lock:
            return list(self.clicks)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _handle_click(self, x, y, button, pressed):
        """pynput callback – only records left-button press events."""
        if not pressed or button != mouse.Button.left:
            return
        now = time.time()
        with self._lock:
            delay_ms = 0 if self._last_time is None else int((now - self._last_time) * 1000)
            self._last_time = now
            click = {"x": int(x), "y": int(y), "delay_ms": delay_ms}
            self.clicks.append(click)
        if self._on_click:
            self._on_click(click)
