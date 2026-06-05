"""Main tkinter GUI for Desktop Click Automator."""

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from recorder import ClickRecorder
from replayer import ClickReplayer

_COL_STEP = "#"
_COL_X = "X"
_COL_Y = "Y"
_COL_DELAY = "Delay (ms)"
_COLUMNS = (_COL_STEP, _COL_X, _COL_Y, _COL_DELAY)

_STATE_IDLE = "idle"
_STATE_RECORDING = "recording"
_STATE_REPLAYING = "replaying"


class App(tk.Tk):
    """Root window of the Desktop Click Automator application."""

    def __init__(self):
        super().__init__()
        self.title("Desktop Click Automator")
        self.geometry("620x420")
        self.minsize(500, 320)

        self._clicks = []
        self._queue = queue.Queue()
        self._state = _STATE_IDLE

        self._recorder = ClickRecorder(on_click_callback=self._enqueue_click)
        self._replayer = ClickReplayer(
            on_step_callback=self._on_replay_step,
            on_done_callback=self._on_replay_done,
        )
        self._replay_thread = None

        self._build_ui()
        self._poll_queue()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        self._build_toolbar()
        self._build_table()
        self._build_statusbar()

    def _build_toolbar(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=6, pady=6)

        self._btn_record = ttk.Button(
            toolbar, text="⏺  Record", width=12, command=self._toggle_record
        )
        self._btn_record.pack(side=tk.LEFT, padx=2)

        self._btn_replay = ttk.Button(
            toolbar, text="▶  Replay", width=12, command=self._toggle_replay
        )
        self._btn_replay.pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6, pady=2
        )

        self._btn_delete = ttk.Button(
            toolbar, text="✕  Delete Step", width=14, command=self._delete_selected
        )
        self._btn_delete.pack(side=tk.LEFT, padx=2)

        self._btn_clear = ttk.Button(
            toolbar, text="🗑  Clear All", width=12, command=self._clear_all
        )
        self._btn_clear.pack(side=tk.LEFT, padx=2)

    def _build_table(self):
        frame = ttk.Frame(self)
        frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=(0, 4))

        self._tree = ttk.Treeview(
            frame, columns=_COLUMNS, show="headings", selectmode="browse"
        )
        col_widths = {_COL_STEP: 50, _COL_X: 120, _COL_Y: 120, _COL_DELAY: 150}
        for col in _COLUMNS:
            self._tree.heading(col, text=col)
            self._tree.column(col, width=col_widths[col], anchor=tk.CENTER)

        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self._tree.bind("<Double-1>", self._on_row_double_click)

    def _build_statusbar(self):
        self._status_var = tk.StringVar(value="Ready")
        bar = ttk.Label(
            self,
            textvariable=self._status_var,
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding=(4, 2),
        )
        bar.pack(side=tk.BOTTOM, fill=tk.X)

    # ------------------------------------------------------------------
    # Queue / thread-safe UI updates
    # ------------------------------------------------------------------

    def _enqueue_click(self, click):
        """Called from the pynput listener thread."""
        self._queue.put(click)

    def _poll_queue(self):
        """Drain the queue on the main thread (runs every 50 ms)."""
        try:
            while True:
                click = self._queue.get_nowait()
                self._clicks.append(click)
                self._append_row(click, len(self._clicks))
                self._status_var.set(f"Recording…  {len(self._clicks)} click(s) captured")
        except queue.Empty:
            pass
        self.after(50, self._poll_queue)

    # ------------------------------------------------------------------
    # Table helpers
    # ------------------------------------------------------------------

    def _append_row(self, click, step_num):
        self._tree.insert(
            "",
            tk.END,
            values=(step_num, click["x"], click["y"], click["delay_ms"]),
        )

    def _refresh_table(self):
        self._tree.delete(*self._tree.get_children())
        for i, click in enumerate(self._clicks, 1):
            self._tree.insert(
                "", tk.END, values=(i, click["x"], click["y"], click["delay_ms"])
            )

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _toggle_record(self):
        if self._state == _STATE_RECORDING:
            self._recorder.stop()
            self._state = _STATE_IDLE
            self._btn_record.config(text="⏺  Record")
            self._status_var.set(
                f"Stopped.  {len(self._clicks)} click(s) recorded.  "
                "Double-click a row to edit."
            )
        elif self._state == _STATE_IDLE:
            self._recorder.start()
            self._state = _STATE_RECORDING
            self._btn_record.config(text="⏹  Stop")
            self._status_var.set("Recording…  Click anywhere to capture.")

    def _toggle_replay(self):
        if self._state == _STATE_REPLAYING:
            self._replayer.stop()
            # State will be reset by _on_replay_done via after()
            return
        if self._state != _STATE_IDLE:
            return
        if not self._clicks:
            messagebox.showinfo("Nothing to replay", "Record some clicks first.")
            return
        self._state = _STATE_REPLAYING
        self._btn_replay.config(text="⏹  Stop")
        self._status_var.set("Replaying…")
        clicks = list(self._clicks)
        self._replay_thread = threading.Thread(
            target=self._replayer.replay, args=(clicks,), daemon=True
        )
        self._replay_thread.start()

    def _delete_selected(self):
        sel = self._tree.selection()
        if not sel:
            return
        idx = self._tree.index(sel[0])
        del self._clicks[idx]
        self._refresh_table()

    def _clear_all(self):
        if self._state == _STATE_RECORDING:
            self._recorder.stop()
        if self._state == _STATE_REPLAYING:
            self._replayer.stop()
        self._clicks.clear()
        self._state = _STATE_IDLE
        self._btn_record.config(text="⏺  Record")
        self._btn_replay.config(text="▶  Replay")
        self._refresh_table()
        self._status_var.set("Cleared.")

    # ------------------------------------------------------------------
    # Replay callbacks (called from background thread)
    # ------------------------------------------------------------------

    def _on_replay_step(self, idx, click):
        self.after(
            0,
            lambda: self._status_var.set(
                f"Replaying step {idx + 1}/{len(self._clicks)}: "
                f"({click['x']}, {click['y']})"
            ),
        )

    def _on_replay_done(self):
        self.after(0, self._replay_finished)

    def _replay_finished(self):
        self._state = _STATE_IDLE
        self._btn_replay.config(text="▶  Replay")
        self._status_var.set("Replay complete.")

    # ------------------------------------------------------------------
    # Edit dialog
    # ------------------------------------------------------------------

    def _on_row_double_click(self, event):
        item = self._tree.identify_row(event.y)
        if not item:
            return
        idx = self._tree.index(item)
        dlg = _EditDialog(self, self._clicks[idx])
        self.wait_window(dlg)
        if dlg.result is not None:
            self._clicks[idx] = dlg.result
            self._refresh_table()


class _EditDialog(tk.Toplevel):
    """Modal dialog for editing a single click step."""

    def __init__(self, parent, click):
        super().__init__(parent)
        self.title("Edit Step")
        self.resizable(False, False)
        self.result = None

        pad = {"padx": 10, "pady": 6}

        ttk.Label(self, text="X coordinate:").grid(row=0, column=0, sticky=tk.E, **pad)
        self._x_var = tk.StringVar(value=str(click["x"]))
        ttk.Entry(self, textvariable=self._x_var, width=10).grid(row=0, column=1, **pad)

        ttk.Label(self, text="Y coordinate:").grid(row=1, column=0, sticky=tk.E, **pad)
        self._y_var = tk.StringVar(value=str(click["y"]))
        ttk.Entry(self, textvariable=self._y_var, width=10).grid(row=1, column=1, **pad)

        ttk.Label(self, text="Delay before (ms):").grid(
            row=2, column=0, sticky=tk.E, **pad
        )
        self._delay_var = tk.StringVar(value=str(click["delay_ms"]))
        ttk.Entry(self, textvariable=self._delay_var, width=10).grid(
            row=2, column=1, **pad
        )

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=8)
        ttk.Button(btn_frame, text="OK", width=8, command=self._ok).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(btn_frame, text="Cancel", width=8, command=self.destroy).pack(
            side=tk.LEFT, padx=4
        )

        self.grab_set()
        self.focus_set()

    def _ok(self):
        try:
            x = int(self._x_var.get())
            y = int(self._y_var.get())
            delay_ms = int(self._delay_var.get())
            if delay_ms < 0:
                raise ValueError("delay_ms must be non-negative")
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc), parent=self)
            return
        self.result = {"x": x, "y": y, "delay_ms": delay_ms}
        self.destroy()
