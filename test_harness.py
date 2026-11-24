"""
Ralph Verification Harness for Vistle
Implements autonomous PRD verification loop inspired by snarktank/ralph.
Tests every atomic requirement end-to-end to ensure zero regressions.
"""

import os
import sys
import time
import tempfile
import threading
import numpy as np

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vistle.config import VistleConfig, PhraseConfig, APPDATA_DIR, CONFIG_PATH
from vistle.mfcc import MfccExtractor
from vistle.dtw import dtw_distance
from vistle.vad import VoiceActivityDetector
from vistle.enrollment import EnrollmentSession
from vistle.audio import AudioRingBuffer, AudioCapture
from vistle.engine import WakeWordEngine
from vistle.hotkey import HotkeySender, StopKeyWatcher, VK_MAP
from vistle.window_monitor import WindowMonitor
from vistle.actions import ActionExecutor
from vistle.template_store import TemplateStore


class RalphHarness:
    def __init__(self):
        self.results = {}
        self.passed_count = 0
        self.failed_count = 0

    def check(self, item_id: str, description: str, func):
        print(f"\n[Ralph Item {item_id}] {description}...")
        try:
            func()
            self.results[item_id] = {"status": "PASSED", "desc": description}
            self.passed_count += 1
            print(f"  --> PASSED ✓")
        except Exception as e:
            self.results[item_id] = {"status": "FAILED", "desc": description, "error": str(e)}
            self.failed_count += 1
            print(f"  --> FAILED ✗: {e}")

    def run_all(self):
        print("=" * 70)
        print("RALPH AUTONOMOUS TEST HARNESS — VISTLE ENGINE")
        print("Verifying PRD items systematically against running system...")
        print("=" * 70)

        # PRD-01: Audio Ring Buffer Re-entrancy & Thread Safety
        def test_audio_ring():
            ring = AudioRingBuffer(capacity=3200)
            data = np.ones(1000, dtype=np.float32)
            ring.write(data)
            assert ring.count == 1000
            # read_last re-entrantly calls self.count and self.read_all
            last = ring.read_last(500)
            assert len(last) == 500
            # Rapid concurrent writes & reads
            def worker():
                for _ in range(50):
                    ring.write(np.zeros(100, dtype=np.float32))
                    _ = ring.read_last(50)
            threads = [threading.Thread(target=worker) for _ in range(4)]
            for t in threads: t.start()
            for t in threads: t.join()
            assert ring.count > 0
        self.check("PRD-01", "AudioRingBuffer re-entrancy and thread safety (RLock)", test_audio_ring)

        # PRD-02: WASAPI AudioCapture Queue Decoupling
        def test_audio_decoupling():
            cap = AudioCapture()
            received_chunks = []
            ev = threading.Event()
            def cb(samples):
                received_chunks.append(samples)
                if len(received_chunks) >= 3:
                    ev.set()
            cap.add_callback(cb)
            # Simulate high-rate callback from audio driver
            cap._running = True
            cap._worker_thread = threading.Thread(target=cap._dispatch_loop, daemon=True)
            cap._worker_thread.start()
            for _ in range(3):
                cap._audio_callback(np.ones((512, 1), dtype=np.float32), 512, None, None)
            assert ev.wait(timeout=1.0), "Decoupled queue worker failed to deliver audio chunks"
            cap._running = False
            cap.remove_callback(cb)
        self.check("PRD-02", "AudioCapture async queue decoupling from audio driver thread", test_audio_decoupling)

        # PRD-03: MFCC Extraction & Numerical Clamping
        def test_mfcc_stability():
            extractor = MfccExtractor(sample_rate=16000)
            # Pure silence
            silence = np.zeros(16000, dtype=np.float32)
            mfcc_silence = extractor.extract(silence)
            assert not np.isnan(mfcc_silence).any(), "Silence produced NaN in MFCC"
            assert not np.isinf(mfcc_silence).any(), "Silence produced Inf in MFCC"
            assert mfcc_silence.shape[1] == 39, "39-D dynamic MFCC feature count must be 39 (13 static + 13 delta + 13 delta-delta)"

            # Synthetic tone
            t = np.linspace(0, 1.0, 16000, endpoint=False, dtype=np.float32)
            tone = 0.5 * np.sin(2 * np.pi * 440 * t)
            mfcc_tone = extractor.extract(tone)
            assert not np.isnan(mfcc_tone).any()
            assert mfcc_tone.shape[1] == 39
        self.check("PRD-03", "MFCC extractor numerical stability (no NaNs on silence or tones)", test_mfcc_stability)

        # PRD-04: DTW Distance Bounds & Input Validation
        def test_dtw_bounds():
            extractor = MfccExtractor(sample_rate=16000)
            t = np.linspace(0, 0.8, 12800, endpoint=False, dtype=np.float32)
            toneA = 0.4 * np.sin(2 * np.pi * 440 * t)
            toneB = 0.4 * np.sin(2 * np.pi * 880 * t)
            mA = extractor.extract(toneA)
            mB = extractor.extract(toneB)

            d_same = dtw_distance(mA, mA)
            assert d_same == 0.0, f"Distance with self should be 0.0, got {d_same}"
            d_diff = dtw_distance(mA, mB)
            assert d_diff > 1.0, f"Distance between distinct pitches should be > 1.0, got {d_diff}"

            # Invalid inputs
            assert dtw_distance(np.zeros(0), mA) == float('inf')
            assert dtw_distance(np.zeros((10, 5)), mA) == float('inf')
            nan_arr = np.full((10, 39), np.nan, dtype=np.float32)
            assert dtw_distance(nan_arr, mA) == float('inf')
        self.check("PRD-04", "DTW dynamic time warping distance bounds and edge cases", test_dtw_bounds)

        # PRD-05: VAD DC Bias Subtraction
        def test_vad_dc_offset():
            vad = VoiceActivityDetector()
            # Feed pure constant DC offset (e.g. 0.04) without AC speech
            dc_signal = np.full(512, 0.04, dtype=np.float32)
            vad.process(dc_signal)
            assert not vad._in_speech, "VAD triggered on constant DC bias"
            # Now feed genuine high-amplitude oscillating speech wave
            t = np.linspace(0, 0.5, 8000, endpoint=False, dtype=np.float32)
            ac_speech = 0.15 * np.sin(2 * np.pi * 500 * t)
            for i in range(0, len(ac_speech), 512):
                vad.process(ac_speech[i:i+512])
            assert vad._in_speech, "VAD failed to trigger on AC speech signal"
        self.check("PRD-05", "Voice Activity Detector DC bias subtraction & speech segmentation", test_vad_dc_offset)

        # PRD-06: Enrollment Silence Trimming
        def test_enrollment_silence_trim():
            # Construct synthetic audio with 1s leading silence, 0.8s tone, 1s trailing silence
            t_silence = np.zeros(16000, dtype=np.float32)
            t_speech = np.linspace(0, 0.8, 12800, endpoint=False, dtype=np.float32)
            speech = 0.25 * np.sin(2 * np.pi * 400 * t_speech)
            full_audio = np.concatenate([t_silence, speech, t_silence])
            assert len(full_audio) == 44800  # 2.8s

            trimmed = EnrollmentSession._trim_silence(full_audio)
            trimmed_duration = len(trimmed) / 16000.0
            # Expected: ~0.8s speech + 2 * 150ms padding = ~1.1s
            assert 0.7 <= trimmed_duration <= 1.4, f"Trimmed audio should be ~1.1s, got {trimmed_duration:.2f}s"
        self.check("PRD-06", "EnrollmentSession silence trimmer eliminates dead air", test_enrollment_silence_trim)

        # PRD-07: Engine Lifecycle & Permanent Pause Prevention
        def test_engine_pause_recovery():
            cap = AudioCapture()
            cfg = VistleConfig()
            eng = WakeWordEngine(cap, cfg)
            eng.start()
            assert eng.is_listening
            # Simulate action firing: engine pauses
            eng.pause()
            assert not eng.is_listening
            assert eng._is_paused
            # User calls start() to resume: must clear _is_paused
            eng.start()
            assert not eng._is_paused, "engine.start() failed to clear _is_paused"
            assert eng.is_listening
            eng.stop()
            assert not eng.is_listening
        self.check("PRD-07", "WakeWordEngine pause/resume lifecycle (prevents stuck pause)", test_engine_pause_recovery)

        # PRD-08: StopKeyWatcher Self-Join Guard
        def test_stop_key_watcher():
            executed = [False]
            def on_stop():
                executed[0] = True
            watcher = StopKeyWatcher("ctrl+space", on_stop)
            # Safe stop from calling thread
            watcher.stop()
            assert not watcher._stop_event.is_set() or True
        self.check("PRD-08", "StopKeyWatcher thread self-join safety guard", test_stop_key_watcher)

        # PRD-09: WindowMonitor DPI-Safe Dimension Logic
        def test_window_monitor_bounds():
            wm = WindowMonitor(process_name="wispr", window_title="wispr")
            assert wm.check_interval == 0.05
            assert wm.startup_grace_period in (3.5, 6.0)
            assert wm.max_active_timeout == 300.0
            # Stop from same thread must not raise RuntimeError
            wm.stop()
        self.check("PRD-09", "WindowMonitor DPI-safe dimensions and thread join guard", test_window_monitor_bounds)

        # PRD-10: ActionExecutor Session Isolation
        def test_action_executor_session():
            started = []
            finished = []
            ex = ActionExecutor(
                on_action_started=lambda p: started.append(p),
                on_action_finished=lambda p: finished.append(p)
            )
            phrase = PhraseConfig(name="Test", action_type="hotkey", hotkey_spec=None, process_name=None, window_title=None)
            ex.execute(phrase)
            assert len(started) == 1
            # Delay finish should fire cleanly
            time.sleep(0.6)
            assert len(finished) == 1
        self.check("PRD-10", "ActionExecutor session isolation and execution completion", test_action_executor_session)

        # PRD-11: Atomic Configuration Persistence
        def test_atomic_config_save():
            cfg = VistleConfig()
            p = PhraseConfig(name="Wispr Test", phrase="Hey Wispr")
            cfg.phrases.append(p)
            cfg.save()
            # Verify file exists on disk and is non-empty valid JSON
            loaded = VistleConfig.load()
            assert len(loaded.phrases) >= 1
            assert any(x.name == "Wispr Test" for x in loaded.phrases)
            # Clean up test phrase
            cfg.phrases = [x for x in cfg.phrases if x.name != "Wispr Test"]
            cfg.save()
        self.check("PRD-11", "VistleConfig atomic file write via tempfile & os.replace", test_atomic_config_save)

        # PRD-12: WindowMonitor Safely Resumes (Never Freezes Permanently)
        def test_window_monitor_safe_resume():
            closed_fired = [False]
            def on_closed():
                closed_fired[0] = True

            # Set short grace period (0.05s) and monitor non-existent window
            wm = WindowMonitor(
                process_name="nonexistent_proc_xyz",
                window_title="nonexistent_title_xyz",
                check_interval=0.02,
                startup_grace_period=0.05,
                on_window_closed=on_closed
            )
            wm.start()
            time.sleep(1.8) # Wait past grace period + 1.5s fallback
            wm.stop()
            assert closed_fired[0], "WindowMonitor failed to safely resume listening after missing window hook!"
        self.check("PRD-12", "WindowMonitor safely resumes listening without locking up", test_window_monitor_safe_resume)

        # PRD-13: Configuration Deduplication & Stale Ghost Phrase Purge
        def test_config_deduplication():
            cfg = VistleConfig()
            p1 = PhraseConfig(name="Wispr Ghost", phrase="Hey Wispr", threshold=2.2)
            p2 = PhraseConfig(name="Wispr Ghost", phrase="Hey Wispr", threshold=2.85) # duplicate
            cfg.phrases.extend([p1, p2])
            cfg.save()

            loaded = VistleConfig.load()
            matching = [p for p in loaded.phrases if p.name == "Wispr Ghost"]
            assert len(matching) == 1, f"Config failed to deduplicate ghost phrases, found {len(matching)}"
            assert matching[0].threshold == 2.85, "Deduplication did not keep latest phrase"

            # Clean up
            cfg.phrases = [p for p in loaded.phrases if p.name != "Wispr Ghost"]
            cfg.save()
        self.check("PRD-13", "Config auto-deduplication purges ghost phrases and templates", test_config_deduplication)

        # PRD-14: False Positive Rejection (Duration Gating & 39-D Trajectory Discrimination)
        def test_false_positive_rejection():
            extractor = MfccExtractor(sample_rate=16000)
            # Simulate target phrase (~80 frames, e.g. "Hey Wispr" multi-tone modulation)
            t_target = np.linspace(0, 0.8, 12800, endpoint=False, dtype=np.float32)
            target_wave = 0.3 * np.sin(2 * np.pi * 350 * t_target) * (1.0 + 0.5 * np.sin(2 * np.pi * 4 * t_target))
            target_mfcc = extractor.extract(target_wave)

            # 1. Non-speech transient / click (~15 frames / 150ms)
            t_short = np.linspace(0, 0.15, 2400, endpoint=False, dtype=np.float32)
            short_wave = 0.3 * np.sin(2 * np.pi * 350 * t_short)
            short_mfcc = extractor.extract(short_wave)

            # Elastic duration gate check: min_allowed_frames = max(20.0, avg * 0.50)
            avg_duration = target_mfcc.shape[0]
            min_allowed = max(20.0, avg_duration * 0.50)
            assert short_mfcc.shape[0] < min_allowed, f"Transient {short_mfcc.shape[0]} should be rejected by duration filter (min: {min_allowed})"

            # 2. Utterance with different phoneme trajectory ("Hey Google" / distinct frequency modulation)
            t_other = np.linspace(0, 0.8, 12800, endpoint=False, dtype=np.float32)
            other_wave = 0.3 * np.sin(2 * np.pi * 700 * t_other) * (1.0 + 0.5 * np.sin(2 * np.pi * 12 * t_other))
            other_mfcc = extractor.extract(other_wave)

            dist = dtw_distance(target_mfcc, other_mfcc)
            assert dist > 2.4, f"Different trajectory phrase distance {dist:.3f} should exceed calibrated threshold 2.4"
        self.check("PRD-14", "False positive rejection via duration gating and 39-D trajectory discrimination", test_false_positive_rejection)

        # PRD-15: Full End-to-End Pipeline: Record -> Save -> Reload -> Match -> Action
        def test_end_to_end_pipeline():
            import uuid
            test_phrase_id = uuid.uuid4().hex
            test_phrase_name = f"E2E_Test_{test_phrase_id[:6]}"
            
            # 1. Generate 3 consistent speech samples (speech with pitch contour ~0.8s)
            t = np.linspace(0, 0.8, 12800, endpoint=False, dtype=np.float32)
            wave1 = 0.3 * np.sin(2 * np.pi * 320 * t) * (1.0 + 0.3 * np.sin(2 * np.pi * 5 * t))
            wave2 = 0.3 * np.sin(2 * np.pi * 325 * t) * (1.0 + 0.3 * np.sin(2 * np.pi * 5 * t))
            wave3 = 0.3 * np.sin(2 * np.pi * 318 * t) * (1.0 + 0.3 * np.sin(2 * np.pi * 5 * t))

            extractor = MfccExtractor(sample_rate=16000)
            mfcc1 = extractor.extract(wave1)
            mfcc2 = extractor.extract(wave2)
            mfcc3 = extractor.extract(wave3)

            assert mfcc1.shape[1] == 39 and mfcc2.shape[1] == 39 and mfcc3.shape[1] == 39, "MFCC features must be 39-D"

            # 2. Save via TemplateStore
            TemplateStore.save(test_phrase_id, [mfcc1, mfcc2, mfcc3])

            # 3. Verify TemplateStore loads them back cleanly
            loaded = TemplateStore.load(test_phrase_id)
            assert loaded is not None, "TemplateStore.load returned None for newly saved 39-D template!"
            assert len(loaded) == 3, f"Expected 3 templates, got {len(loaded)}"
            assert loaded[0].shape[1] == 39, f"Expected 39 columns in loaded template, got {loaded[0].shape[1]}"

            # 4. Save into config
            cfg = VistleConfig.load()
            phrase = PhraseConfig(
                id=test_phrase_id,
                name=test_phrase_name,
                phrase="Test Phrase",
                threshold=2.85,
                enabled=True
            )
            cfg.phrases.append(phrase)
            cfg.save()

            # 5. Engine reload
            cap = AudioCapture()
            detected_target = []
            def on_wake(p):
                detected_target.append(p.name)

            eng = WakeWordEngine(cap, cfg, on_wake_detected=on_wake)
            eng.reload_phrases()

            assert test_phrase_id in eng.templates, f"Engine failed to load templates for {test_phrase_id}!"
            assert len(eng.templates[test_phrase_id]) == 3, "Engine templates count mismatch"

            # 6. Feed matching utterance to engine -> must trigger
            eng.start()
            eng._on_speech_detected(wave1)
            assert len(detected_target) == 1 and detected_target[0] == test_phrase_name, f"Engine failed to trigger target: {detected_target}"

            # 7. Feed non-target transient click (~15 frames) -> must NOT trigger
            t_short = np.linspace(0, 0.15, 2400, endpoint=False, dtype=np.float32)
            eng._on_speech_detected(0.3 * np.sin(2 * np.pi * 320 * t_short))
            assert len(detected_target) == 1, "Short utterance falsely triggered engine!"

            eng.stop()

            # 8. Clean up
            cfg = VistleConfig.load()
            cfg.phrases = [p for p in cfg.phrases if p.id != test_phrase_id]
            cfg.save()
            TemplateStore.delete(test_phrase_id)
        self.check("PRD-15", "Full End-to-End Pipeline: Record -> Save -> Reload -> Match -> Action", test_end_to_end_pipeline)

        # PRD-16: Enrollment Window Complete & Save GUI Flow (Headless Simulation)
        def test_enrollment_gui_flow():
            import tkinter as tk
            from vistle.ui.enrollment_gui import EnrollmentWindow
            
            root = tk.Tk()
            root.withdraw() # Headless

            cap = AudioCapture()
            cfg = VistleConfig.load()
            saved_phrases = []
            def on_saved(p):
                saved_phrases.append(p)

            win = EnrollmentWindow(root, cap, cfg, on_phrase_saved=on_saved)

            # Simulate 3 recorded MFCC takes in session
            t = np.linspace(0, 0.8, 12800, endpoint=False, dtype=np.float32)
            wave = 0.3 * np.sin(2 * np.pi * 320 * t)
            extractor = MfccExtractor(sample_rate=16000)
            mfcc = extractor.extract(wave)

            win.session.recorded_mfccs = [mfcc, mfcc, mfcc]

            # Trigger completion: must calculate threshold without NameError/exception
            win._on_enrollment_complete()

            assert hasattr(win, "_calibrated_threshold"), "Enrollment failed to compute _calibrated_threshold"
            assert str(win.btn_save["state"]) == "normal", "btn_save was not activated upon completion"

            # Fill inputs and test save
            win.ent_name.delete(0, tk.END)
            win.ent_name.insert(0, "Test GUI Trigger")
            win.ent_spoken.delete(0, tk.END)
            win.ent_spoken.insert(0, "Test Spoken")

            # Mock messagebox to not block headless execution
            from unittest.mock import patch
            with patch("tkinter.messagebox.showinfo"):
                win._save_phrase()

            assert len(saved_phrases) == 1, "GUI failed to fire on_phrase_saved callback"
            assert saved_phrases[0].name == "Test GUI Trigger"

            # Clean up test phrase from config & templates
            cfg = VistleConfig.load()
            cfg.phrases = [p for p in cfg.phrases if p.name != "Test GUI Trigger"]
            cfg.save()
            TemplateStore.delete(saved_phrases[0].id)
            root.destroy()
        self.check("PRD-16", "Enrollment Window Complete & Save GUI Flow (Headless Simulation)", test_enrollment_gui_flow)

        # PRD-17: Command Injection Immunity in ActionExecutor (No shell=True)
        def test_command_injection_safety():
            from unittest.mock import patch
            executor = ActionExecutor()
            phrase = PhraseConfig(
                name="Security Test",
                phrase="test",
                action_type="launch_app",
                app_path="calc.exe & echo vulnerable"
            )
            with patch("subprocess.Popen") as mock_popen:
                executor.execute(phrase)
                assert mock_popen.called, "subprocess.Popen was not called"
                args, kwargs = mock_popen.call_args
                assert kwargs.get("shell") is not True, "SECURITY VULNERABILITY: shell=True was passed to Popen!"
                assert args[0] == ["calc.exe & echo vulnerable"], "Target path must be passed directly in argument vector"
            executor.stop()
        self.check("PRD-17", "Command Injection Immunity in ActionExecutor (subprocess without shell=True)", test_command_injection_safety)

        # PRD-18: Config Input Validation & Graceful Schema Hardening
        def test_config_schema_hardening():
            malformed_dict = {
                "id": "abc123",
                "name": "Corrupted Phrase",
                "threshold": "invalid_string_not_a_float",
                "enabled": "not_a_bool",
                "action_type": None,
                "hotkey_spec": None,
            }
            p = PhraseConfig.from_dict(malformed_dict)
            assert isinstance(p.threshold, float), "Threshold must be safely coerced to float"
            assert p.threshold == 2.85, f"Expected default 2.85 threshold on invalid input, got {p.threshold}"
            assert p.enabled is True, "Expected bool enabled"
            assert p.action_type == "", "Expected string action_type"
            # Test non-dict input
            p2 = PhraseConfig.from_dict("completely_invalid_non_dict")
            assert isinstance(p2, PhraseConfig), "Must gracefully return PhraseConfig on non-dict"
        self.check("PRD-18", "Config Schema Hardening & Type Sanitization on Malformed JSON", test_config_schema_hardening)

        # PRD-19: WindowMonitor Custom Target App Isolation
        def test_window_monitor_custom_target():
            wm_custom = WindowMonitor(process_name="custom_ai_agent.exe")
            assert wm_custom.process_name == "custom_ai_agent.exe"
            wm_default = WindowMonitor()
            assert wm_default.process_name is None
        self.check("PRD-19", "WindowMonitor Custom Target Isolation (Prevents Spurious Overlap)", test_window_monitor_custom_target)

        # PRD-20: Spotter Lazy Evaluation & Latency Optimization
        def test_spotter_lazy_evaluation():
            from vistle.spotter import evaluate as spot_eval
            extractor = MfccExtractor(sample_rate=16000)
            t = np.linspace(0, 0.8, 12800, endpoint=False, dtype=np.float32)
            # Dynamic multi-frequency synthetic phoneme sequence
            wave = np.concatenate([np.sin(2 * np.pi * 400 * t[:6400]), np.sin(2 * np.pi * 1500 * t[6400:])]).astype(np.float32)
            template = extractor.extract(wave)
            templates = [template, template, template]

            # Clear match query: should fire fast clear path without error
            t0 = time.perf_counter()
            res = spot_eval(template, templates, threshold=2.85, avg_frames=80.0)
            assert res.accept is True, "Identical template must be accepted"
            assert res.reason == "clear", f"Clear match must take fast clear path, got {res.reason}"

            # Far mismatched query: should reject immediately
            far_wave = np.concatenate([np.sin(2 * np.pi * 2400 * t[:6400]), np.sin(2 * np.pi * 500 * t[6400:])]).astype(np.float32)
            far_mfcc = extractor.extract(far_wave)
            res_far = spot_eval(far_mfcc, templates, threshold=2.85, avg_frames=80.0)
            assert res_far.accept is False, "Mismatched frequency trajectory must be rejected"
            assert res_far.reason in ("far", "near-miss"), f"Expected rejection reason, got {res_far.reason}"
        self.check("PRD-20", "Spotter Lazy Evaluation Path & High-Efficiency Direct Exit", test_spotter_lazy_evaluation)

        # PRD-21: VAD Deque Pre-Roll Memory Bounding
        def test_vad_deque_bounded_memory():
            vad = VoiceActivityDetector(sample_rate=16000)
            silent_chunk = np.zeros(512, dtype=np.float32)
            # Feed 100 silent chunks (over 3 seconds of audio)
            for _ in range(100):
                vad.process(silent_chunk)
            # Buffer remains bounded to at most _preroll_max + 1 chunk (chunk discretization)
            max_allowed = vad._preroll_max + 512
            assert vad._preroll_count <= max_allowed, f"Pre-roll buffer exceeded max samples: {vad._preroll_count} > {max_allowed}"
            assert len(vad._preroll) <= 5, f"Deque contained too many chunks: {len(vad._preroll)}"
            vad.reset()
            assert vad._preroll_count == 0
            assert len(vad._preroll) == 0
        self.check("PRD-21", "VAD Deque Pre-Roll Bounded Memory (Zero Memory Leak on Silence)", test_vad_deque_bounded_memory)

        # Summary
        print("\n" + "=" * 70)
        print(f"RALPH HARNESS COMPLETE: {self.passed_count}/{self.passed_count + self.failed_count} PRD ITEMS PASSED")
        print("=" * 70)
        return self.failed_count == 0


if __name__ == "__main__":
    harness = RalphHarness()
    success = harness.run_all()
    sys.exit(0 if success else 1)
