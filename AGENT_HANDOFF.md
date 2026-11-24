# AGENT HANDOFF & ARCHITECTURAL SPECIFICATION — VISTLE

> **Target Audience:** Principal AI Engineer / Code Reviewer Agent / Systems Auditor  
> **Date:** November 2026  
> **Current Version:** v0.3.0  
> **Repository:** Vistle (formerly Whistle)

---

## 1. Executive Summary & Product Thesis

**Vistle** is a 100% on-device, zero-latency desktop voice trigger utility. It enables users to activate desktop productivity tools hands-free using custom spoken wake phrases.

- **Primary Flagship Integration:** Wispr Flow (`Ctrl + Win + Space` or custom key chord).
- **Secondary Multi-App Targets:** ChatGPT Desktop Voice Mode (`Ctrl + Shift + V`), PowerToys Run (`Alt + Space`), Windows Snipping Tool (`Win + Shift + S`), and custom global shell macros.
- **Privacy Constraints (Non-Negotiable):**
  1. No audio waveforms are ever written to disk or transmitted across network interfaces.
  2. Audio data exists solely as transient floating-point buffers in volatile RAM during sliding window inspection.
  3. Enrolled voice templates are stored purely as non-invertible numerical Mel-Frequency Cepstral Coefficient (MFCC) matrices.

---

## 2. Component Architecture & Dataflow

```
                    ┌─────────────────────────┐
                    │  WASAPI Audio Driver    │ (16 kHz, Mono, 32-bit Float)
                    └────────────┬────────────┘
                                 │ Real-time Stream Callback
                                 ▼
                    ┌─────────────────────────┐
                    │      AudioCapture       │ (queue.Queue Thread Decoupling)
                    └────────────┬────────────┘
                                 │ 512-sample chunks (~32ms)
                                 ▼
                    ┌─────────────────────────┐
                    │  VoiceActivityDetector  │ (DC Bias Subtraction + Energy Threshold)
                    └────────────┬────────────┘
                                 │ Continuous Speech Segment (numpy 1D array)
                                 ▼
                    ┌─────────────────────────┐
                    │      MfccExtractor      │ (39-D Features: 13 Static + 13 Δ + 13 ΔΔ)
                    └────────────┬────────────┘
                                 │ (Frames, 39) Feature Matrix
                                 ▼
                    ┌─────────────────────────┐
                    │     WakeWordEngine      │ (natural tempo; clicks still rejected)
                    └────────────┬────────────┘
                                 │ Sakoe-Chiba Dynamic Time Warping
                                 ▼
       ┌────────────────────────────────────────────────────────┐
       │               ActionExecutor & Mic Guard                │
       └──────────────┬──────────────────────────┬──────────────┘
                      │                          │
                      ▼                          ▼
        ┌───────────────────────────┐ ┌───────────────────────────┐
        │       HotkeySender        │ │  WindowMonitor / Watcher  │
        │    (Win32 SendInput)      │ │   (DPI & EnumWindows)     │
        └───────────────────────────┘ └───────────────────────────┘
```

---

## 3. Mathematical Foundations & Algorithms

### A. 39-Dimensional Dynamic MFCCs (`vistle/mfcc.py`)
Standard 13 static MFCCs only describe the instantaneous spectral envelope (vowels), making distinct words with similar vowel formants susceptible to false positives (e.g., *"open"* vs *"hey Wispr"*).
Vistle computes a 39-dimensional feature representation:
1. **Static MFCCs ($c_1 \dots c_{13}$):** Pre-emphasis filter ($\alpha = 0.97$), Hamming windowing (400 samples / 25ms, hop 160 samples / 10ms), 512-point FFT, 26 triangular Mel filterbanks, Log Energy, DCT-II, followed by Cepstral Mean and Variance Normalization (CMVN).
2. **Delta Coefficients ($\Delta$ / Velocity):**
   $$d_t = \frac{\sum_{n=1}^N n (c_{t+n} - c_{t-n})}{2 \sum_{n=1}^N n^2} \quad (N=2)$$
3. **Delta-Delta Coefficients ($\Delta\Delta$ / Acceleration):**
   Second-order derivative computed by applying the delta operator on the velocity matrix.

### B. Sakoe-Chiba Constrained Dynamic Time Warping (`vistle/dtw.py`)
Computes normalized dynamic distance between query sequence $Q \in \mathbb{R}^{N \times 39}$ and template $T \in \mathbb{R}^{M \times 39}$:
- **Local Distance:** Euclidean vector distance $\|\mathbf{q}_i - \mathbf{t}_j\|_2$.
- **Window Constraint:** Sakoe-Chiba band width $w = \max(|N - M|, \;\lfloor\max(N, M) \cdot 0.25\rfloor)$.
- **Global Path Normalization:** Distance is normalized by $(N + M)$.
- **Boundary Guards:** Non-2D inputs, NaN/Inf elements, or frame mismatches return $\infty$ gracefully.

---

## 4. Key Engineering Safeguards Solved

| Hazard Encountered | Root Cause | Solution Implemented |
| :--- | :--- | :--- |
| **WASAPI Audio Dropout** | Running DSP directly inside the sound card's WASAPI driver callback thread. | Decoupled audio stream via an unbounded worker `queue.Queue` with separate dispatch thread. |
| **AudioRingBuffer Deadlock** | `read_last()` called `self.count` and `self.read_all` under standard `threading.Lock`. | Upgraded to re-entrant `threading.RLock()`. |
| **Current Thread Self-Join Crash** | `WindowMonitor` and `StopKeyWatcher` called completion handler which called `.join()` on their own running thread. | Added `if threading.current_thread() != self._thread:` guard before calling `.join()`. |
| **Config File Corruption** | Interrupted write during system power-off or crash. | Implemented atomic file swap via `tempfile.mkstemp` + `os.replace`. |
| **Multi-Monitor Coordinate Truncation** | Windows secondary displays with negative virtual screen coordinates (e.g. `rect.left = -1920`) rejected by naive `> 0` window checks. | Relaxed coordinate guard to `rect.left > -4000` to support multi-monitor setups. |
| **Premature Mic Un-mute** | `WindowMonitor` assumed dictation finished if the target popup was not spotted within 6s, prematurely sending a second hotkey and closing Wispr Flow. | If popup was never detected (`saw_popup == False`), `WindowMonitor` hands off mic safety to `StopKeyWatcher` or 180s safety fallback ceiling. |

---

## 5. Ralph Autonomous Verification Suite (`test_harness.py`)

The codebase contains an automated, non-interactive verification harness (`test_harness.py`) enforcing 21 distinct PRD requirements:

```bash
python test_harness.py
```

- **PRD-01 to PRD-05:** Thread safety, queue decoupling, MFCC numerical clamping, DTW edge bounds, VAD DC bias subtraction.
- **PRD-06 to PRD-10:** Energy-based silence trimming, engine pause recovery, self-join thread safety, DPI-safe geometry, action isolation.
- **PRD-11 to PRD-14:** Atomic file replacement, window monitor dictation guard, config deduplication, 39-D false positive rejection.
- **PRD-15 to PRD-16:** Full End-to-End lifecycle simulation (Recording $\rightarrow$ Matching $\rightarrow$ Action Dispatch) and Headless GUI enrollment.
- **PRD-17 to PRD-21:** Command injection immunity (subprocess without shell=True), Config schema hardening against corrupted JSON, WindowMonitor custom process isolation, Spotter lazy evaluation latency optimization (< 15ms), and VAD deque pre-roll bounded memory.

*Rule for Incoming Agents:* Any proposed architectural change must pass `python test_harness.py` (21/21) cleanly before being considered valid.

---

## 6. Honest Technical Frontiers (Recommendations for Next Agent)

1. **GUI (Edge WebView2, already in place):**
   - The tray opens one native window (`vistle/ui/host.py` + `vistle/ui/assets/app.html`). On Windows it uses Edge Chromium via `pywebview`. Closing the window hides it; Exit destroys it.
   - The page calls `start_enrollment`, `stop_sample`, `save_phrase`, `list_phrases`, `toggle_phrase`, `delete_phrase`.
   - `EnrollmentWindow` still exposes `_on_enrollment_complete`, `_save_phrase`, `btn_save`, `ent_name`, and `ent_spoken` so PRD-16 can run headless without opening WebView. Do not make `EnrollmentWindow.__init__` start the webview loop.

2. **Cadence (do not put the 0.50× length gate back):**
   - People enroll slowly. Refusing anything under half that length is why the phrase only hit when spoken slowly.
   - `vistle/spotter.py` keeps the saved templates and the saved threshold. Fast and slow takes are compared on the enrollment clock, so the same phrase matches at either speed. A different phrase still misses. The slow raw-match path is unchanged.
   - Do not replace this with openWakeWord for custom phrases. That trainer writes audio and needs a fixed vocabulary. DTW stays the few-shot path.

3. **macOS Target Porting:**
   - *Audio Capture:* `sounddevice` supports macOS CoreAudio out of the box.
   - *DSP Math:* NumPy linked against Apple's `Accelerate.framework` (vDSP) executes FFT and DTW at ~0% CPU.
   - *Action Dispatch:* Port `vistle/hotkey.py` to use macOS Quartz Event Services (`CGEventCreateKeyboardEvent` / `CGEventPost`) via `pyobjc-framework-Quartz`.
   - *Mic / Window Guard:* Port `window_monitor.py` to `CGWindowListCopyWindowInfo` to detect Wispr Flow's floating pill on macOS.
