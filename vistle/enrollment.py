import numpy as np
import threading
from typing import List, Callable, Optional
from vistle.audio import AudioCapture
from vistle.mfcc import MfccExtractor

class EnrollmentSession:
    """
    Manages interactive enrollment of a wake phrase.
    Records N samples, extracts MFCCs, and discards audio waveforms immediately.
    """
    def __init__(
        self,
        audio_capture: AudioCapture,
        target_count: int = 3,
        on_sample_recorded: Optional[Callable[[int, int], None]] = None,
        on_enrollment_complete: Optional[Callable[[], None]] = None
    ):
        self.audio_capture = audio_capture
        self.target_count = target_count
        self.on_sample_recorded = on_sample_recorded
        self.on_enrollment_complete = on_enrollment_complete

        self.mfcc_extractor = MfccExtractor()
        self.recorded_mfccs: List[np.ndarray] = []
        self._current_recording_buffer: List[np.ndarray] = []
        self._is_recording = False
        self._lock = threading.Lock()

    def _audio_callback(self, samples: np.ndarray):
        with self._lock:
            if self._is_recording:
                self._current_recording_buffer.append(samples)

    def start_sample_recording(self):
        """Starts recording one enrollment utterance."""
        with self._lock:
            self._current_recording_buffer.clear()
            self._is_recording = True

        self.audio_capture.add_callback(self._audio_callback)
        if not self.audio_capture.is_running:
            self.audio_capture.start()

    @staticmethod
    def _trim_silence(audio: np.ndarray, threshold: float = 0.012, pad_samples: int = 2400) -> np.ndarray:
        """
        Trims leading and trailing silence from the enrollment audio
        so that the template matches the speech boundaries segmented by VAD.
        pad_samples=2400 is 150ms of context.
        """
        if len(audio) < 1600:
            return audio
        frame_len = 320  # 20ms at 16kHz
        n_frames = len(audio) // frame_len
        if n_frames < 2:
            return audio

        frames = audio[:n_frames * frame_len].reshape(n_frames, frame_len)
        rms = np.sqrt(np.mean(frames ** 2, axis=1))

        peak = float(np.max(rms)) if len(rms) > 0 else 0.0
        effective_threshold = max(threshold, peak * 0.15)

        active_indices = np.where(rms >= effective_threshold)[0]
        if len(active_indices) == 0:
            return audio

        start_idx = max(0, int(active_indices[0] * frame_len - pad_samples))
        end_idx = min(len(audio), int((active_indices[-1] + 1) * frame_len + pad_samples))
        trimmed = audio[start_idx:end_idx]
        print(f"[Vistle Enrollment] Trimmed silence: {len(audio)/16000:.2f}s -> {len(trimmed)/16000:.2f}s pure speech")
        return trimmed

    def stop_sample_recording(self) -> bool:
        """
        Stops recording the current utterance, extracts MFCCs,
        and immediately discards the raw audio.
        Returns True if sample was valid, False otherwise.
        """
        with self._lock:
            if not self._is_recording:
                return False
            self._is_recording = False
            raw_audio = np.concatenate(self._current_recording_buffer) if self._current_recording_buffer else np.zeros(0, dtype=np.float32)
            # Memory scrub
            self._current_recording_buffer.clear()

        # Trim silence around utterance
        clean_audio = self._trim_silence(raw_audio)

        # Validate minimum length (at least ~0.3s)
        if len(clean_audio) < 16000 * 0.3:
            print("[Vistle Enrollment] Sample too short or silent, discarding")
            return False

        # Extract numerical features
        mfcc = self.mfcc_extractor.extract(clean_audio)
        if mfcc.shape[0] < 5:
            print("[Vistle Enrollment] MFCC extraction produced too few frames")
            return False

        self.recorded_mfccs.append(mfcc)
        count = len(self.recorded_mfccs)
        print(f"[Vistle Enrollment] Recorded sample {count}/{self.target_count}")

        if self.on_sample_recorded:
            self.on_sample_recorded(count, self.target_count)

        if count >= self.target_count:
            self.audio_capture.remove_callback(self._audio_callback)
            if self.on_enrollment_complete:
                self.on_enrollment_complete()

        return True

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._is_recording

    @property
    def recorded_count(self) -> int:
        return len(self.recorded_mfccs)

    @property
    def is_complete(self) -> bool:
        return len(self.recorded_mfccs) >= self.target_count

    def get_templates(self) -> List[np.ndarray]:
        return list(self.recorded_mfccs)

    def reset(self):
        with self._lock:
            self._is_recording = False
            self._current_recording_buffer.clear()
            self.recorded_mfccs.clear()
        self.audio_capture.remove_callback(self._audio_callback)
