#!/usr/bin/env python3
"""
Clicker Tool — macOS Screen Automation
=======================================
Record mouse click sequences, set per-step delays, then replay N times.

macOS Permissions Required (System Settings > Privacy & Security):
    • Input Monitoring   — for pynput to listen to global mouse events (recording)
    • Accessibility      — for Quartz/CGEventPost to deliver synthetic clicks (replay)

Install dependencies:
    pip install pynput
"""
from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, List, Optional


# ---------------------------------------------------------------------------
# Accessibility trust check
# ---------------------------------------------------------------------------

def _ax_is_trusted() -> bool:
    """Return True if this process has the Accessibility permission."""
    try:
        axlib = ctypes.CDLL(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        axlib.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(axlib.AXIsProcessTrusted())
    except Exception:
        return False


def _open_accessibility_settings() -> None:
    subprocess.Popen(
        ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"]
    )


# ---------------------------------------------------------------------------
# Dependency bootstrap
# ---------------------------------------------------------------------------

def _check_deps() -> List[str]:
    missing = []
    for pkg in ("pynput",):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    return missing


def _offer_install(missing: List[str]) -> bool:
    root = tk.Tk()
    root.withdraw()
    pkg_str = ", ".join(missing)
    install = messagebox.askyesno(
        "Missing Dependencies",
        f"Required packages not found:\n  {pkg_str}\n\n"
        f"Install them now via pip?",
        parent=root,
    )
    if install:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install"] + missing,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            messagebox.showinfo(
                "Installed",
                "Dependencies installed.\nPlease restart the app.",
                parent=root,
            )
        else:
            messagebox.showerror(
                "Install Failed",
                f"pip failed:\n{result.stderr[:600]}\n\nInstall manually and retry.",
                parent=root,
            )
    root.destroy()
    return False  # Always restart after install attempt


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class Step:
    CLICK_TYPES = ("left", "right", "double")

    def __init__(
        self,
        x: int = 0,
        y: int = 0,
        click_type: str = "left",
        delay_before: float = 0.5,
        label: str = "",
    ) -> None:
        self.x = int(x)
        self.y = int(y)
        self.click_type = click_type if click_type in self.CLICK_TYPES else "left"
        self.delay_before = max(0.0, float(delay_before))
        self.label = str(label).strip()

    def display_label(self, index: int) -> str:
        return self.label if self.label else f"Step {index}"

    def to_dict(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "click_type": self.click_type,
            "delay_before": self.delay_before,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Step":
        return cls(
            x=d.get("x", 0),
            y=d.get("y", 0),
            click_type=d.get("click_type", "left"),
            delay_before=d.get("delay_before", 0.5),
            label=d.get("label", ""),
        )


# ---------------------------------------------------------------------------
# Edit Step dialog
# ---------------------------------------------------------------------------

class EditStepDialog(tk.Toplevel):
    """Modal dialog for creating or editing a single step."""

    def __init__(self, parent: tk.Tk, step: Step, step_num: int) -> None:
        super().__init__(parent)
        self.title(f"Edit — Step {step_num}")
        self.resizable(False, False)
        self.result: Optional[Step] = None

        self.transient(parent)
        self.grab_set()

        pad = dict(padx=14, pady=7)

        # ---- Form fields ----
        tk.Label(self, text="Label (optional):", anchor="w").grid(
            row=0, column=0, sticky="w", **pad
        )
        self._label_var = tk.StringVar(value=step.label)
        tk.Entry(self, textvariable=self._label_var, width=30).grid(
            row=0, column=1, sticky="ew", **pad
        )

        tk.Label(self, text="X  (pixels):", anchor="w").grid(
            row=1, column=0, sticky="w", **pad
        )
        self._x_var = tk.IntVar(value=step.x)
        tk.Spinbox(self, from_=0, to=10000, textvariable=self._x_var, width=10).grid(
            row=1, column=1, sticky="w", **pad
        )

        tk.Label(self, text="Y  (pixels):", anchor="w").grid(
            row=2, column=0, sticky="w", **pad
        )
        self._y_var = tk.IntVar(value=step.y)
        tk.Spinbox(self, from_=0, to=10000, textvariable=self._y_var, width=10).grid(
            row=2, column=1, sticky="w", **pad
        )

        tk.Label(self, text="Click Type:", anchor="w").grid(
            row=3, column=0, sticky="w", **pad
        )
        self._click_var = tk.StringVar(value=step.click_type)
        ttk.Combobox(
            self,
            textvariable=self._click_var,
            values=list(Step.CLICK_TYPES),
            state="readonly",
            width=12,
        ).grid(row=3, column=1, sticky="w", **pad)

        tk.Label(self, text="Delay Before (s):", anchor="w").grid(
            row=4, column=0, sticky="w", **pad
        )
        self._delay_var = tk.DoubleVar(value=step.delay_before)
        tk.Spinbox(
            self,
            from_=0.0,
            to=3600.0,
            increment=0.1,
            textvariable=self._delay_var,
            format="%.1f",
            width=10,
        ).grid(row=4, column=1, sticky="w", **pad)

        # ---- Buttons ----
        btn_frame = tk.Frame(self)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=(6, 14))
        tk.Button(btn_frame, text="Save", width=12, command=self._save).pack(
            side="left", padx=8
        )
        tk.Button(btn_frame, text="Cancel", width=12, command=self.destroy).pack(
            side="left", padx=8
        )

        self.wait_window()

    def _save(self) -> None:
        try:
            x = int(self._x_var.get())
            y = int(self._y_var.get())
            delay = float(self._delay_var.get())
            if x < 0 or y < 0 or delay < 0:
                raise ValueError("Values must be non-negative.")
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror("Invalid Input", str(exc), parent=self)
            return
        self.result = Step(
            x=x,
            y=y,
            click_type=self._click_var.get(),
            delay_before=delay,
            label=self._label_var.get(),
        )
        self.destroy()


# ---------------------------------------------------------------------------
# Execution overlay
# ---------------------------------------------------------------------------

class ExecutionOverlay(tk.Toplevel):
    """Small always-on-top window shown while executing the click sequence."""

    _BG = "#1e1e2e"
    _FG_TITLE = "#cba6f7"
    _FG_ITER = "#89dceb"
    _FG_STEP = "#a6e3a1"
    _FG_STATUS = "#f9e2af"

    def __init__(
        self,
        parent: tk.Tk,
        total_steps: int,
        total_iterations: int,
        stop_callback: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self.title("Clicker Tool — Running")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # disallow manual close

        self._total_steps = total_steps
        self._total_iters = total_iterations
        self._stop_cb = stop_callback

        # Position: top-right of screen
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        self.geometry(f"310x210+{sw - 330}+30")
        self.configure(bg=self._BG)

        tk.Label(
            self,
            text="CLICKER TOOL  \u25B6  RUNNING",
            bg=self._BG, fg=self._FG_TITLE,
            font=("Helvetica", 13, "bold"),
        ).pack(pady=(14, 4))

        self._iter_lbl = tk.Label(
            self, text=f"Iteration: — / {total_iterations}",
            bg=self._BG, fg=self._FG_ITER, font=("Helvetica", 10),
        )
        self._iter_lbl.pack()

        self._step_lbl = tk.Label(
            self, text=f"Step: — / {total_steps}",
            bg=self._BG, fg=self._FG_STEP, font=("Helvetica", 10),
        )
        self._step_lbl.pack()

        self._status_lbl = tk.Label(
            self, text="Starting…",
            bg=self._BG, fg=self._FG_STATUS,
            font=("Helvetica", 9), wraplength=290,
        )
        self._status_lbl.pack(pady=5)

        self._progress = ttk.Progressbar(self, length=270, mode="determinate")
        self._progress.pack(pady=4)

        tk.Button(
            self,
            text="    STOP    ",
            bg="#f38ba8", fg="#111111", activebackground="#e64553",
            activeforeground="#111111",
            font=("Helvetica", 12, "bold"),
            relief="flat", padx=18, pady=5,
            command=self._stop_cb,
        ).pack(pady=(5, 14))

    def update_status(self, iteration: int, step: int, status: str) -> None:
        self._iter_lbl.config(text=f"Iteration: {iteration} / {self._total_iters}")
        self._step_lbl.config(text=f"Step: {step} / {self._total_steps}")
        self._status_lbl.config(text=status)
        total = self._total_iters * self._total_steps
        done = (iteration - 1) * self._total_steps + step
        self._progress["value"] = (done / total * 100) if total else 0
        self.update_idletasks()


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class ClickerToolApp:
    """Clicker Tool — main application window."""

    _WIN_SIZE = "820x580"
    _WIN_TITLE = "Clicker Tool"

    # Colours
    _C_HEADER_BG = "#2b2d42"
    _C_HEADER_FG = "#edf2f4"
    _C_ACCENT = "#2ec4b6"
    _C_DANGER = "#e63946"
    _C_RUN = "#2dc653"
    _C_BAR_BG = "#eaeaea"
    _C_EXEC_BG = "#dde1e7"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(self._WIN_TITLE)
        self.root.geometry(self._WIN_SIZE)
        self.root.minsize(700, 480)

        self.steps: List[Step] = []
        self._is_recording = False
        self._mouse_listener = None
        self._stop_exec = threading.Event()
        self._overlay: Optional[ExecutionOverlay] = None

        # Lazy lib references (imported after dep-check)
        self._pynput_mouse = None
        self._mouse_controller = None
        self._pyautogui = None
        self._quartz = None
        self._load_libs()

        self._build_ui()
        self.root.after(200, self._check_accessibility_at_startup)

    # ------------------------------------------------------------------
    # Accessibility permission helpers
    # ------------------------------------------------------------------

    def _check_accessibility_at_startup(self) -> None:
        if not _ax_is_trusted():
            self._show_accessibility_dialog(
                "Accessibility permission is required for replay.\n"
                "Recording will still work, but clicks will not be delivered\n"
                "until you grant access and restart the app."
            )

    def _show_accessibility_dialog(self, context: str = "") -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("Accessibility Permission Needed")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.configure(bg="#fff8e7")

        tk.Label(
            dlg,
            text="\u26A0\uFE0F  Accessibility Permission Required",
            bg="#fff8e7", fg="#b45309",
            font=("Helvetica", 13, "bold"),
        ).pack(padx=24, pady=(18, 6))

        msg = (
            (context + "\n\n" if context else "") +
            "Steps to fix:\n"
            "  1. Click \"Open System Settings\" below\n"
            "  2. Find Terminal (or your Python app) in the list\n"
            "     and toggle it ON\n"
            "  3. If it\u2019s not listed, click the + button and add:\n"
            "       /Applications/Utilities/Terminal.app\n"
            "  4. Quit and re-run this script"
        )
        tk.Label(
            dlg, text=msg,
            bg="#fff8e7", fg="#1a1a1a",
            font=("Helvetica", 10),
            justify="left", wraplength=400,
        ).pack(padx=24, pady=6)

        btn_frame = tk.Frame(dlg, bg="#fff8e7")
        btn_frame.pack(pady=(10, 18))
        tk.Button(
            btn_frame,
            text="Open System Settings",
            bg="#2563eb", fg="#111111", activebackground="#1d4ed8",
            activeforeground="#111111",
            font=("Helvetica", 11, "bold"),
            relief="flat", padx=14, pady=6,
            command=lambda: (_open_accessibility_settings(), dlg.destroy()),
        ).pack(side="left", padx=8)
        tk.Button(
            btn_frame,
            text="Dismiss",
            bg="#6b7280", fg="#111111", activebackground="#4b5563",
            activeforeground="#111111",
            font=("Helvetica", 11),
            relief="flat", padx=14, pady=6,
            command=dlg.destroy,
        ).pack(side="left", padx=8)

        dlg.wait_window()

    # ------------------------------------------------------------------
    # Library loading
    # ------------------------------------------------------------------

    def _load_libs(self) -> None:
        try:
            import pynput.mouse as pm
            self._pynput_mouse = pm
            self._mouse_controller = pm.Controller()
        except ImportError:
            pass
        try:
            import Quartz
            self._quartz = Quartz
        except ImportError:
            pass
        try:
            import pyautogui as pag
            pag.FAILSAFE = True
            pag.PAUSE = 0.0
            self._pyautogui = pag
        except ImportError:
            pass

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")  # "aqua" ignores custom bg on tk.Button → white text invisible

        self.root.configure(bg="#f5f5f5")
        self._build_header()
        self._build_toolbar()
        self._build_table()
        self._build_exec_bar()
        self._build_statusbar()

    def _build_header(self) -> None:
        hdr = tk.Frame(self.root, bg=self._C_HEADER_BG, pady=10)
        hdr.pack(fill="x")

        tk.Label(
            hdr, text="Clicker Tool",
            bg=self._C_HEADER_BG, fg=self._C_HEADER_FG,
            font=("Helvetica", 18, "bold"),
        ).pack(side="left", padx=16)

        tk.Label(
            hdr, text="Record  \u2022  Arrange  \u2022  Replay",
            bg=self._C_HEADER_BG, fg="#8d99ae",
            font=("Helvetica", 11),
        ).pack(side="left", padx=4)

        self._rec_indicator = tk.Label(
            hdr, text="",
            bg=self._C_HEADER_BG, fg="#ff6b6b",
            font=("Helvetica", 11, "bold"),
        )
        self._rec_indicator.pack(side="right", padx=6)

        self._record_btn = tk.Button(
            hdr,
            text=" Start Recording ",
            bg=self._C_ACCENT, fg="#111111",
            activebackground="#21a1a1",
            activeforeground="#111111",
            font=("Helvetica", 11, "bold"),
            relief="flat", padx=10, pady=5,
            command=self.toggle_recording,
        )
        self._record_btn.pack(side="right", padx=16)

    def _build_toolbar(self) -> None:
        bar = tk.Frame(self.root, bg=self._C_BAR_BG, pady=4)
        bar.pack(fill="x")

        def btn(text: str, cmd: Callable, bg: str = "#555577") -> tk.Button:
            return tk.Button(
                bar, text=text, command=cmd,
                bg=bg, fg="#111111", activebackground="#333355",
                activeforeground="#111111",
                font=("Helvetica", 10), relief="flat", padx=9, pady=3,
            )

        btn("Edit",       self.edit_selected,          "#5e60ce").pack(side="left", padx=3, pady=4)
        btn("Delete",     self.delete_selected,        "#e63946").pack(side="left", padx=3, pady=4)
        btn("Move Up",    lambda: self.move_step(-1),  "#6a4c93").pack(side="left", padx=3, pady=4)
        btn("Move Down",  lambda: self.move_step(1),   "#6a4c93").pack(side="left", padx=3, pady=4)
        btn("Add Step",   self.add_manual_step,        "#457b9d").pack(side="left", padx=3, pady=4)

        tk.Frame(bar, bg="#bbbbbb", width=1).pack(side="left", fill="y", padx=8, pady=4)

        btn("Clear All",  self.clear_all,              "#d62828").pack(side="left", padx=3, pady=4)

        tk.Frame(bar, bg="#bbbbbb", width=1).pack(side="left", fill="y", padx=8, pady=4)

        btn("Save JSON",  self.save_sequence,          "#2a9d8f").pack(side="left", padx=3, pady=4)
        btn("Load JSON",  self.load_sequence,          "#2a9d8f").pack(side="left", padx=3, pady=4)

        tk.Frame(bar, bg="#bbbbbb", width=1).pack(side="left", fill="y", padx=8, pady=4)

        btn("Permissions Help", self._show_permissions_help, "#888899").pack(
            side="left", padx=3, pady=4
        )

    def _build_table(self) -> None:
        frame = tk.Frame(self.root, bg="#f5f5f5")
        frame.pack(fill="both", expand=True, padx=10, pady=(8, 4))

        cols = ("#", "Label", "X", "Y", "Click Type", "Delay Before (s)")
        self._tree = ttk.Treeview(
            frame, columns=cols, show="headings", selectmode="browse"
        )

        col_cfg = [
            ("#",               40,  "center"),
            ("Label",          190,  "w"),
            ("X",               70,  "center"),
            ("Y",               70,  "center"),
            ("Click Type",     110,  "center"),
            ("Delay Before (s)", 140, "center"),
        ]
        for col, width, anchor in col_cfg:
            self._tree.heading(col, text=col)
            self._tree.column(
                col, width=width, anchor=anchor, stretch=(col == "Label")
            )

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._tree.tag_configure("even", background="#f0f4ff")
        self._tree.tag_configure("odd",  background="#fafafa")

        self._tree.bind("<Double-1>", lambda _: self.edit_selected())

    def _build_exec_bar(self) -> None:
        bar = tk.Frame(
            self.root, bg=self._C_EXEC_BG, pady=8, relief="groove", bd=1
        )
        bar.pack(fill="x", padx=10, pady=(0, 4))

        tk.Label(
            bar, text="Iterations:", bg=self._C_EXEC_BG,
            fg="#1f2937", font=("Helvetica", 11, "bold"),
        ).pack(side="left", padx=(14, 4))

        self._iter_var = tk.IntVar(value=1)
        tk.Spinbox(
            bar, from_=1, to=9999, width=7,
            textvariable=self._iter_var, font=("Helvetica", 11),
        ).pack(side="left")

        self._run_btn = tk.Button(
            bar,
            text="  Run  ",
            bg=self._C_RUN, fg="#111111", activebackground="#1a9e3e",
            activeforeground="#111111",
            font=("Helvetica", 12, "bold"),
            relief="flat", padx=18, pady=5,
            command=self.execute_sequence,
        )
        self._run_btn.pack(side="left", padx=14)

        self._step_count_lbl = tk.Label(
            bar, text="0 steps recorded", bg=self._C_EXEC_BG,
            fg="#555555", font=("Helvetica", 10),
        )
        self._step_count_lbl.pack(side="right", padx=14)

    def _build_statusbar(self) -> None:
        self._status_var = tk.StringVar(
            value="Ready — press 'Start Recording' to begin capturing clicks."
        )
        tk.Label(
            self.root,
            textvariable=self._status_var,
            bd=1, relief="sunken", anchor="w",
            font=("Helvetica", 9), bg="#e0e0e0", fg="#333333",
        ).pack(side="bottom", fill="x")

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def toggle_recording(self) -> None:
        if self._is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        if self._pynput_mouse is None:
            messagebox.showerror(
                "pynput Not Found",
                "pynput is required for recording.\n\n"
                "Install:  pip install pynput\n\n"
                "Then grant Accessibility + Input Monitoring permissions\n"
                "(System Settings › Privacy & Security).\n\n"
                "Click 'Permissions Help' in the toolbar for details.",
                parent=self.root,
            )
            return

        self._is_recording = True
        self._record_btn.config(
            text=" Stop Recording ",
            bg=self._C_DANGER, activebackground="#c62828",
            fg="#111111", activeforeground="#111111",
        )
        self._rec_indicator.config(text="\u25CF REC")
        self._status("Recording active — click anywhere on screen to capture steps.")

        self._mouse_listener = self._pynput_mouse.Listener(
            on_click=self._on_global_click
        )
        self._mouse_listener.start()

    def _stop_recording(self) -> None:
        self._is_recording = False
        if self._mouse_listener is not None:
            self._mouse_listener.stop()
            self._mouse_listener = None
        self._record_btn.config(
            text=" Start Recording ",
            bg=self._C_ACCENT, activebackground="#21a1a1",
            fg="#111111", activeforeground="#111111",
        )
        self._rec_indicator.config(text="")
        n = len(self.steps)
        self._status(f"Recording stopped — {n} step{'s' if n != 1 else ''} captured.")

    def _on_global_click(
        self, x: int, y: int, button: object, pressed: bool
    ) -> None:
        """Called by pynput in a background thread on every mouse event."""
        if not pressed:
            return

        # Ignore clicks that land inside the app window itself
        try:
            wx = self.root.winfo_rootx()
            wy = self.root.winfo_rooty()
            ww = self.root.winfo_width()
            wh = self.root.winfo_height()
            if wx <= x <= wx + ww and wy <= y <= wy + wh:
                return
        except Exception:
            pass

        click_type = (
            "right" if button == self._pynput_mouse.Button.right else "left"
        )
        step = Step(x=int(x), y=int(y), click_type=click_type, delay_before=0.5)
        self.steps.append(step)

        self.root.after(0, self._refresh_tree)
        self.root.after(
            0,
            lambda cx=x, cy=y, ct=click_type, n=len(self.steps): self._status(
                f"Captured ({int(cx)}, {int(cy)}) — {ct} click   [{n} total]"
            ),
        )

    # ------------------------------------------------------------------
    # Steps table management
    # ------------------------------------------------------------------

    def _refresh_tree(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for i, step in enumerate(self.steps):
            tag = "even" if i % 2 == 0 else "odd"
            self._tree.insert(
                "", "end",
                iid=str(i),
                tags=(tag,),
                values=(
                    i + 1,
                    step.display_label(i + 1),
                    step.x,
                    step.y,
                    step.click_type,
                    f"{step.delay_before:.1f} s",
                ),
            )
        n = len(self.steps)
        self._step_count_lbl.config(
            text=f"{n} step{'s' if n != 1 else ''} recorded"
        )

    def _selected_index(self) -> Optional[int]:
        sel = self._tree.selection()
        return int(sel[0]) if sel else None

    def edit_selected(self) -> None:
        idx = self._selected_index()
        if idx is None:
            self._status("Select a step to edit.")
            return
        dlg = EditStepDialog(self.root, self.steps[idx], idx + 1)
        if dlg.result is not None:
            self.steps[idx] = dlg.result
            self._refresh_tree()
            self._tree.selection_set(str(idx))

    def delete_selected(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        del self.steps[idx]
        self._refresh_tree()
        self._status(f"Deleted step {idx + 1}.")

    def move_step(self, direction: int) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        new_idx = idx + direction
        if 0 <= new_idx < len(self.steps):
            self.steps[idx], self.steps[new_idx] = (
                self.steps[new_idx],
                self.steps[idx],
            )
            self._refresh_tree()
            self._tree.selection_set(str(new_idx))

    def add_manual_step(self) -> None:
        dlg = EditStepDialog(self.root, Step(), len(self.steps) + 1)
        if dlg.result is not None:
            self.steps.append(dlg.result)
            self._refresh_tree()

    def clear_all(self) -> None:
        if not self.steps:
            return
        if messagebox.askyesno(
            "Clear All", f"Delete all {len(self.steps)} step(s)?", parent=self.root
        ):
            self.steps.clear()
            self._refresh_tree()
            self._status("All steps cleared.")

    # ------------------------------------------------------------------
    # Save / Load
    # ------------------------------------------------------------------

    def save_sequence(self) -> None:
        if not self.steps:
            messagebox.showinfo("Nothing to Save", "No steps recorded yet.", parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Save Sequence",
            parent=self.root,
        )
        if not path:
            return
        payload = {"version": 1, "steps": [s.to_dict() for s in self.steps]}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        self._status(f"Saved {len(self.steps)} step(s) to {path}")

    def load_sequence(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Load Sequence",
            parent=self.root,
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.steps = [Step.from_dict(s) for s in data.get("steps", [])]
            self._refresh_tree()
            self._status(f"Loaded {len(self.steps)} step(s) from {path}")
        except Exception as exc:
            messagebox.showerror(
                "Load Error", f"Could not read file:\n{exc}", parent=self.root
            )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute_sequence(self) -> None:
        if not self.steps:
            messagebox.showinfo("No Steps", "Record or add steps first.", parent=self.root)
            return
        if not _ax_is_trusted():
            self._show_accessibility_dialog(
                "Cannot replay — Accessibility permission is not granted.\n"
                "The mouse will move but clicks will be silently dropped by macOS."
            )
            return
        if self._quartz is None and self._pynput_mouse is None:
            messagebox.showerror(
                "No Mouse Backend",
                "Neither Quartz nor pynput is available.\n\n"
                "Install:  pip install pynput pyobjc-framework-Quartz\n\n"
                "Click 'Permissions Help' in the toolbar for details.",
                parent=self.root,
            )
            return

        try:
            iterations = int(self._iter_var.get())
            if iterations < 1:
                raise ValueError
        except (ValueError, tk.TclError):
            messagebox.showwarning(
                "Invalid Iterations", "Enter a positive integer.", parent=self.root
            )
            return

        self._run_btn.config(state="disabled")
        self._stop_exec.clear()

        self._overlay = ExecutionOverlay(
            self.root,
            total_steps=len(self.steps),
            total_iterations=iterations,
            stop_callback=self._request_stop,
        )

        threading.Thread(
            target=self._exec_worker,
            args=(list(self.steps), iterations),
            daemon=True,
        ).start()

    def _request_stop(self) -> None:
        self._stop_exec.set()
        self._status("Stop requested — finishing current action…")

    # ------------------------------------------------------------------
    # Low-level mouse helpers (Quartz backend used for replay)
    # ------------------------------------------------------------------

    def _mouse_move(self, x: int, y: int) -> None:
        Q = self._quartz
        pt = Q.CGPoint(x, y)
        Q.CGWarpMouseCursorPosition(pt)
        Q.CGAssociateMouseAndMouseCursorPosition(True)

    def _mouse_click(self, x: int, y: int, click_type: str) -> None:
        Q = self._quartz
        pt = Q.CGPoint(x, y)
        if click_type == "right":
            btn = Q.kCGMouseButtonRight
            down_evt = Q.kCGEventRightMouseDown
            up_evt   = Q.kCGEventRightMouseUp
        else:
            btn = Q.kCGMouseButtonLeft
            down_evt = Q.kCGEventLeftMouseDown
            up_evt   = Q.kCGEventLeftMouseUp

        def _post(kind):
            e = Q.CGEventCreateMouseEvent(None, kind, pt, btn)
            Q.CGEventPost(Q.kCGHIDEventTap, e)

        if click_type == "double":
            _post(Q.kCGEventLeftMouseDown)
            _post(Q.kCGEventLeftMouseUp)
            time.sleep(0.05)
            e2 = Q.CGEventCreateMouseEvent(None, Q.kCGEventLeftMouseDown, pt, btn)
            Q.CGEventSetIntegerValueField(e2, Q.kCGMouseEventClickState, 2)
            Q.CGEventPost(Q.kCGHIDEventTap, e2)
            e3 = Q.CGEventCreateMouseEvent(None, Q.kCGEventLeftMouseUp, pt, btn)
            Q.CGEventSetIntegerValueField(e3, Q.kCGMouseEventClickState, 2)
            Q.CGEventPost(Q.kCGHIDEventTap, e3)
        else:
            _post(down_evt)
            time.sleep(0.02)
            _post(up_evt)

    def _exec_worker(self, steps: List[Step], iterations: int) -> None:
        use_quartz = self._quartz is not None
        mouse = self._mouse_controller  # fallback if Quartz unavailable
        Button = self._pynput_mouse.Button if self._pynput_mouse else None
        try:
            for iteration in range(1, iterations + 1):
                if self._stop_exec.is_set():
                    break
                for step_idx, step in enumerate(steps, 1):
                    if self._stop_exec.is_set():
                        break

                    # ---- Delay phase ----
                    if step.delay_before > 0:
                        status = (
                            f"Waiting {step.delay_before:.1f}s before "
                            f"{step.display_label(step_idx)}"
                        )
                        self.root.after(
                            0, self._overlay_update, iteration, step_idx, status
                        )
                        deadline = time.monotonic() + step.delay_before
                        while time.monotonic() < deadline:
                            if self._stop_exec.is_set():
                                break
                            time.sleep(0.05)

                    if self._stop_exec.is_set():
                        break

                    # ---- Click phase ----
                    status = (
                        f"{step.click_type.capitalize()} click at "
                        f"({step.x}, {step.y})  —  {step.display_label(step_idx)}"
                    )
                    self.root.after(
                        0, self._overlay_update, iteration, step_idx, status
                    )
                    try:
                        if use_quartz:
                            self._mouse_move(step.x, step.y)
                            time.sleep(0.05)
                            self._mouse_click(step.x, step.y, step.click_type)
                        else:
                            mouse.position = (step.x, step.y)
                            time.sleep(0.05)
                            if step.click_type == "left":
                                mouse.click(Button.left)
                            elif step.click_type == "right":
                                mouse.click(Button.right)
                            elif step.click_type == "double":
                                mouse.click(Button.left, 2)
                    except Exception as exc:
                        self.root.after(
                            0,
                            lambda e=exc: messagebox.showerror(
                                "Execution Error",
                                f"Mouse control failed:\n{e}\n\n"
                                "Grant Accessibility permission to Terminal\n"
                                "in System Settings › Privacy & Security.",
                                parent=self.root,
                            ),
                        )
                        return

        finally:
            self.root.after(0, self._exec_done)

    def _overlay_update(self, iteration: int, step: int, status: str) -> None:
        if self._overlay and self._overlay.winfo_exists():
            self._overlay.update_status(iteration, step, status)

    def _exec_done(self) -> None:
        if self._overlay and self._overlay.winfo_exists():
            self._overlay.destroy()
        self._overlay = None
        self._run_btn.config(state="normal")
        msg = (
            "Execution stopped by user."
            if self._stop_exec.is_set()
            else "Execution complete."
        )
        self._status(msg)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _status(self, msg: str) -> None:
        self._status_var.set(msg)

    def _show_permissions_help(self) -> None:
        messagebox.showinfo(
            "macOS Permissions Required",
            "This app needs two permissions to work:\n\n"
            "1. Input Monitoring  — lets pynput capture global mouse clicks\n"
            "   (needed for recording)\n\n"
            "2. Accessibility     — lets pynput move the mouse & click\n"
            "   (needed for execution / replay)\n\n"
            "How to grant:\n"
            "  System Settings › Privacy & Security\n"
            "  › Accessibility   → add Terminal (or your Python app)\n"
            "  › Input Monitoring → add Terminal (or your Python app)\n\n"
            "After granting, restart the terminal and re-run the script.",
            parent=self.root,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    missing = _check_deps()
    if missing:
        _offer_install(missing)
        return

    root = tk.Tk()
    ClickerToolApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
