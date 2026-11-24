import time
import threading
import numpy as np
from typing import List, Dict, Callable, Optional
from vistle.audio import AudioCapture
from vistle.config import VistleConfig, PhraseConfig
from vistle.mfcc import MfccExtractor
from vistle.vad import VoiceActivityDetector
from vistle.template_store import TemplateStore
from vistle.spotter import evaluate as spot_phrase

class WakeWordEngine:
    """
    On-device spotter.
    1. VAD segments an utterance, keeping a short onset so fast phrases are intact.
    2. Clicks and long stretches of speech are refused before matching.
    3. Clear matches fire at a natural speed. Near misses have to beat the
       time-reversed enrollment, which is what used to false-trigger.
    4. A fast take that only looks bad because of timing is retried on the
       enrollment clock.
    Templates stay numerical. No audio is written.
    """
    def __init__(
        self,
        audio_capture: AudioCapture,
        config: VistleConfig,
        on_wake_detected: Optional[Callable[[PhraseConfig], None]] = None,
        on_status_change: Optional[Callable[[str], None]] = None
    ):
        self.audio_capture = audio_capture
        self.config = config
        self.on_wake_detected = on_wake_detected
        self.on_status_change = on_status_change

        self.mfcc_extractor = MfccExtractor()
        self.templates: Dict[str, List[np.ndarray]] = {}  # phrase_id -> list of MFCC templates
        self.avg_durations: Dict[str, float] = {}          # phrase_id -> average frame count
        self.vad = VoiceActivityDetector(on_speech_segment=self._on_speech_detected)

        self._is_listening = False
        self._is_paused = False
        self._last_trigger_time = 0.0
        self._lock = threading.Lock()

        self.reload_phrases()

    def reload_phrases(self):
        """Reloads active phrases, their numerical templates, and timing baselines."""
        with self._lock:
            self.config = VistleConfig.load()
            self.templates.clear()
            self.avg_durations.clear()

            for phrase in self.config.phrases:
                if phrase.enabled:
                    loaded = TemplateStore.load(phrase.id)
                    if loaded:
                        # Auto-upgrade any legacy 13-D templates to 39-D dynamic features
                        upgraded = []
                        for t in loaded:
                            if t.ndim == 2 and t.shape[1] == 13:
                                d = MfccExtractor.compute_deltas(t)
                                dd = MfccExtractor.compute_deltas(d)
                                t = np.hstack([t, d, dd]).astype(np.float32)
                            upgraded.append(t)
                        self.templates[phrase.id] = upgraded
                        frame_lens = [tmpl.shape[0] for tmpl in upgraded if tmpl.shape[0] > 0]
                        avg_f = float(np.mean(frame_lens)) if frame_lens else 80.0
                        self.avg_durations[phrase.id] = avg_f
                        print(f"[Vistle Engine] Loaded '{phrase.name}' ({len(upgraded)} templates, avg {avg_f:.0f} frames / ~{avg_f*10:.0f}ms)")
                    else:
                        print(f"[Vistle Engine] No template found for '{phrase.name}' ({phrase.id})")

    def _on_speech_detected(self, speech_samples: np.ndarray):
        """Called by VAD when speech ends. Applies multi-stage anti-false-positive filtering."""
        now = time.time()
        with self._lock:
            if not self._is_listening or self._is_paused:
                return
            if (now - self._last_trigger_time) * 1000 < self.config.cooldown_ms:
                return

        # 1. Extract MFCC features
        query_mfcc = self.mfcc_extractor.extract(speech_samples)
        query_frames = query_mfcc.shape[0]
        if query_frames < 5:
            return

        print(f"[Vistle Engine] Heard utterance: {query_frames} frames (~{query_frames * 10}ms)")

        best_match: Optional[PhraseConfig] = None
        best_distance = float("inf")

        with self._lock:
            enabled_phrases = [p for p in self.config.phrases if p.enabled and p.id in self.templates]
            templates_snapshot = {p.id: list(self.templates.get(p.id, [])) for p in enabled_phrases}
            durations_snapshot = dict(self.avg_durations)

        if not enabled_phrases:
            print("[Vistle Engine] No enabled phrases loaded in engine.")
            return

        for phrase in enabled_phrases:
            phrase_templates = templates_snapshot.get(phrase.id, [])
            avg_duration = durations_snapshot.get(phrase.id, 80.0)
            result = spot_phrase(query_mfcc, phrase_templates, phrase.threshold, avg_duration)
            print(
                f"[Vistle Engine] Phrase '{phrase.name}' {result.reason} "
                f"distance {result.distance:.3f} (thresh {phrase.threshold:.2f}, "
                f"enrolled ~{avg_duration:.0f}f, heard {query_frames}f)"
            )
            if result.accept and result.distance < best_distance:
                best_distance = result.distance
                best_match = phrase

        if best_match is not None:
            with self._lock:
                self._last_trigger_time = now
            print(f"🎯 [Vistle Engine] TRIGGERED: '{best_match.name}' (distance: {best_distance:.3f})")
            if self.on_wake_detected:
                try:
                    self.on_wake_detected(best_match)
                except Exception as e:
                    print(f"[Vistle Engine] Error in wake handler: {e}")

    def _audio_callback(self, samples: np.ndarray):
        if self._is_listening and not self._is_paused:
            self.vad.process(samples)

    def start(self):
        with self._lock:
            if self._is_listening and not self._is_paused:
                return
            self._is_listening = True
            self._is_paused = False
            self.vad.reset()

        self.audio_capture.add_callback(self._audio_callback)
        if not self.audio_capture.is_running:
            try:
                self.audio_capture.start()
            except Exception as e:
                print(f"[Vistle Engine] Failed to start audio: {e}")
                self._is_listening = False
                return

        print("[Vistle Engine] Started listening")
        if self.on_status_change:
            self.on_status_change("Listening")

    def stop(self):
        with self._lock:
            if not self._is_listening:
                return
            self._is_listening = False
            self._is_paused = False
            self.vad.reset()

        self.audio_capture.remove_callback(self._audio_callback)
        print("[Vistle Engine] Stopped listening")
        if self.on_status_change:
            self.on_status_change("Stopped")

    def pause(self):
        with self._lock:
            self._is_paused = True
            self.vad.reset()
        print("[Vistle Engine] Paused listening (mic freed for target app)")
        if self.on_status_change:
            self.on_status_change("Paused")

    def resume(self):
        with self._lock:
            self._is_paused = False
            self.vad.reset()
            self._last_trigger_time = time.time()
        print("[Vistle Engine] Resumed listening")
        if self.on_status_change:
            self.on_status_change("Listening")

    @property
    def is_listening(self) -> bool:
        return self._is_listening and not self._is_paused
