# Vistle 🎙️
**The Universal, 100% On-Device, Zero-Latency Voice Trigger Layer for Desktop.**

Trigger Wispr Flow, ChatGPT Desktop Voice, PowerToys Run, or any custom hotkey with your voice. Zero cloud streaming, zero audio stored on disk, zero background LLMs.

---

## 🔒 Privacy & Architecture Principles

Unlike cloud voice assistants, Vistle is built with provable, mathematically enforced on-device privacy:
- **Zero Cloud Streaming:** Microphone audio never leaves your local machine.
- **Zero Raw Audio on Disk:** Audio waveforms are held strictly in volatile RAM rings and discarded immediately after feature extraction.
- **Numerical-Only Templates:** Enrolled triggers are stored exclusively as 39-dimensional mathematical feature vectors (`~2 KB`) that cannot be reconstructed into human speech.
- **Zero Background LLM:** Runs on a deterministic mathematical signal processing pipeline (Energy VAD + 39-D MFCC + Sakoe-Chiba Dynamic Time Warping).

```
                          ┌──► Wispr Flow (Ctrl + Win + Space)
                          ├──► ChatGPT Desktop Voice (Ctrl + Shift + V)
  [ Vistle Voice Layer ] ─┼──► PowerToys Run / Raycast (Alt + Space)
  (100% Local 39-D DTW)   ├──► Windows Snipping Tool (Win + Shift + S)
                          └──► Custom Hotkeys & App Launchers
```

---

## ⚡ Key Capabilities

- **Few-Shot Custom Calibration:** Train any custom phrase (*"Hey Wispr"*, *"Computer"*, *"Screenshot"*) in 3 quick takes without neural training or GPUs.
- **39-Dimensional Dynamic Features:** Extracts 13 static MFCC cepstral coefficients + 13 velocity ($\Delta$) + 13 acceleration ($\Delta\Delta$) features to capture phonetic trajectory and eliminate false positive triggers.
- **Elastic Tempo Timing:** Uses Sakoe-Chiba Dynamic Time Warping to warp natural variations in speech speed ($0.50\times - 1.75\times$).
- **Lifecycle Coordination & Mic Arbitration:** Automatically detects when target overlay windows (e.g. Wispr Flow's floating pill) open, safely pausing wake listening so the target application has exclusive, uninterrupted microphone access.
- **Instant System Tray Daemon:** Sits in the Windows notification area using less than 25 MB of RAM and ~0% idle CPU.

---

## 🚀 Quick Start

### 1. Requirements & Setup
- Windows 10 or 11 (64-bit)
- Python 3.10+ (or standalone executable)

```bash
# Clone the repository
git clone https://github.com/your-username/vistle.git
cd vistle

# Install dependencies
pip install -r requirements.txt
```

### 2. Launch Vistle
```bash
# Run via batch script
run.bat

# Or run directly via Python
python main.py
```

### 3. First-Run Calibration
On first launch, Vistle will automatically open the **Voice Calibration** wizard:
1. Enter your **Trigger Phrase** (e.g. `Hey Wispr`).
2. Verify the **Shortcut Chord** (default: `ctrl+windows+space`).
3. Click **Record Sample** 3 times and speak naturally into your microphone.
4. Click **Save Trigger**. Vistle will minimize to the system tray and begin listening.

---

## 🧪 Automated Ralph Test Harness

Vistle ships with a built-in automated test harness verifying all 16 core PRD requirements across threading, DSP, persistence, and execution:

```bash
python test_harness.py
```

```
======================================================================
RALPH AUTONOMOUS TEST HARNESS — VISTLE ENGINE
Verifying PRD items systematically against running system...
======================================================================
[Ralph Item PRD-01] AudioRingBuffer re-entrancy and thread safety (RLock)... --> PASSED ✓
[Ralph Item PRD-02] AudioCapture async queue decoupling from audio driver... --> PASSED ✓
[Ralph Item PRD-03] MFCC extractor numerical stability (no NaNs on silence)... --> PASSED ✓
[Ralph Item PRD-04] DTW dynamic time warping distance bounds and edge cases... --> PASSED ✓
[Ralph Item PRD-05] Voice Activity Detector DC bias subtraction... --> PASSED ✓
[Ralph Item PRD-06] EnrollmentSession silence trimmer eliminates dead air... --> PASSED ✓
[Ralph Item PRD-07] WakeWordEngine pause/resume lifecycle... --> PASSED ✓
[Ralph Item PRD-08] StopKeyWatcher thread self-join safety guard... --> PASSED ✓
[Ralph Item PRD-09] WindowMonitor DPI-safe dimensions and thread join guard... --> PASSED ✓
[Ralph Item PRD-10] ActionExecutor session isolation and execution completion... --> PASSED ✓
[Ralph Item PRD-11] VistleConfig atomic file write via tempfile & os.replace... --> PASSED ✓
[Ralph Item PRD-12] WindowMonitor never prematurely un-mutes mic if popup not seen... --> PASSED ✓
[Ralph Item PRD-13] Config auto-deduplication purges ghost phrases and templates... --> PASSED ✓
[Ralph Item PRD-14] False positive rejection via duration gating & 39-D trajectory... --> PASSED ✓
[Ralph Item PRD-15] Full End-to-End Pipeline: Record -> Save -> Reload -> Match... --> PASSED ✓
[Ralph Item PRD-16] Enrollment Window Complete & Save GUI Flow... --> PASSED ✓
======================================================================
RALPH HARNESS COMPLETE: 16/16 PRD ITEMS PASSED
======================================================================
```

---

## 📦 Building Standalone Windows Executable

To compile Vistle into a portable Windows executable that runs on any machine without Python installed:

```bash
build_exe.bat
```
The compiled output is located at `dist\Vistle\Vistle.exe`.

---

## 🗺️ Project Structure

```
Vistle/
├── vistle/
│   ├── audio.py            # 16kHz WASAPI capture with thread-decoupled Queue
│   ├── mfcc.py             # 39-D feature extractor (13 static + 13 delta + 13 delta-delta)
│   ├── dtw.py              # Sakoe-Chiba band Dynamic Time Warping distance
│   ├── vad.py              # DC bias-subtracted energy Voice Activity Detector
│   ├── config.py           # Configuration management with atomic file writes
│   ├── template_store.py   # Numerical 39-D float template persistence
│   ├── enrollment.py       # 3-sample interactive calibration session
│   ├── engine.py           # Continuous spotting engine with elastic timing
│   ├── hotkey.py           # Native Win32 SendInput dispatch & keyboard watchers
│   ├── window_monitor.py   # Multi-monitor Win32 EnumWindows overlay detector
│   ├── actions.py          # Session-tagged lifecycle coordinator
│   └── ui/
│       ├── theme.py        # Wispr Flow warm light design tokens
│       ├── tray.py         # System tray application (pystray)
│       ├── enrollment_gui.py # Voice calibration dialog with dotted radar
│       └── settings_gui.py   # Dashboard with active triggers and keycaps
├── vistle_light_preview.html # Modern Wispr Flow warm light UI design reference
├── test_harness.py         # Autonomous 16-item PRD verification harness
├── main.py                 # Single-instance application entry point
├── run.bat                 # One-click launcher
├── build_exe.bat           # Standalone executable compiler
└── AGENT_HANDOFF.md        # Technical architecture dossier for incoming agents
```

---

## 📄 License
MIT License. Built for privacy, speed, and hands-free desktop ergonomics.
