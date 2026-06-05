# desktop-click-automator

A macOS desktop automation tool to **record**, **edit**, and **replay** global mouse clicks with per-step delays.

## Features

- **Record** – captures left-button click positions and inter-click timing anywhere on screen (uses the macOS Accessibility API via pynput).
- **Edit** – double-click any row in the table to change the X/Y coordinates or the delay (in ms) before that click fires.
- **Delete / Clear** – remove individual steps or wipe the whole sequence.
- **Replay** – executes the recorded sequence with the saved per-step delays; a **Stop** button interrupts playback at any time.

## Requirements

- macOS (tested on macOS 12+)
- Python 3.9+
- The app must be granted **Accessibility** permission in *System Settings → Privacy & Security → Accessibility* so pynput can capture global clicks.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

1. Click **⏺ Record** – then click anywhere on your desktop to capture positions.
2. Click **⏹ Stop** when done recording.
3. Double-click any row in the table to adjust coordinates or the delay before that step.
4. Click **▶ Replay** to run the sequence.  Click **⏹ Stop** at any time to abort.

## Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

## Project Structure

```
desktop-click-automator/
├── main.py          # Entry point
├── app.py           # tkinter GUI
├── recorder.py      # Global mouse-click recorder (pynput)
├── replayer.py      # Click replayer with per-step delays (pyautogui)
├── requirements.txt
└── tests/
    ├── test_recorder.py
    └── test_replayer.py
```
