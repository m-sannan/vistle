import numpy as np
from collections import deque
from typing import Callable, Optional

class VoiceActivityDetector:
    """
    Energy-based Voice Activity Detector (VAD).
    Identifies utterance boundaries and extracts speech segments.
    """
    def __init__(
        self,
        sample_rate: int = 16000,
        speech_threshold: float = 0.02,
        silence_threshold: float = 0.01,
        min_speech_duration_ms: int = 250,
        silence_timeout_ms: int = 400,
        max_speech_duration_ms: int = 3500,
        on_speech_segment: Optional[Callable[[np.ndarray], None]] = None
    ):
        self.sample_rate = sample_rate
        self.speech_threshold = speech_threshold
        self.silence_threshold = silence_threshold
        self.min_speech_samples = int(sample_rate * min_speech_duration_ms / 1000)
        self.silence_timeout_samples = int(sample_rate * silence_timeout_ms / 1000)
        self.max_speech_samples = int(sample_rate * max_speech_duration_ms / 1000)
        self.on_speech_segment = on_speech_segment

        # Keep the onset that sits just under the energy threshold. A fast
        # phrase loses its first consonant otherwise, and then only a slow
        # take still matches enrollment.
        self._preroll_max = int(sample_rate * 0.120)
        self._preroll = deque()
        self._preroll_count = 0

        self._in_speech = False
        self._speech_buffer = []
        self._silent_samples_count = 0
        self._total_speech_samples = 0

    def reset(self):
        self._in_speech = False
        self._speech_buffer.clear()
        self._silent_samples_count = 0
        self._total_speech_samples = 0
        self._preroll.clear()
        self._preroll_count = 0

    def _push_preroll(self, chunk: np.ndarray):
        self._preroll.append(chunk)
        self._preroll_count += len(chunk)
        while self._preroll and (self._preroll_count - len(self._preroll[0])) >= self._preroll_max:
            self._preroll_count -= len(self._preroll.popleft())

    def process(self, chunk: np.ndarray):
        """Process a chunk of float32 audio samples."""
        if len(chunk) == 0:
            return

        # Subtract DC bias offset before computing RMS
        centered = chunk - np.mean(chunk)
        rms = float(np.sqrt(np.mean(centered ** 2)))

        if not self._in_speech:
            if rms >= self.speech_threshold:
                self._in_speech = True
                self._speech_buffer = list(self._preroll) + [chunk]
                self._total_speech_samples = sum(len(c) for c in self._speech_buffer)
                self._preroll.clear()
                self._preroll_count = 0
                self._silent_samples_count = 0
            else:
                self._push_preroll(chunk)
        else:
            self._speech_buffer.append(chunk)
            self._total_speech_samples += len(chunk)

            if rms < self.silence_threshold:
                self._silent_samples_count += len(chunk)
            else:
                self._silent_samples_count = 0

            # Check if silence timeout reached or max speech duration exceeded
            if (self._silent_samples_count >= self.silence_timeout_samples or 
                self._total_speech_samples >= self.max_speech_samples):
                
                if self._total_speech_samples >= self.min_speech_samples:
                    speech_segment = np.concatenate(self._speech_buffer)
                    # Trim trailing silence
                    if self._silent_samples_count > 0:
                        keep_len = max(self.min_speech_samples, len(speech_segment) - self._silent_samples_count)
                        speech_segment = speech_segment[:keep_len]

                    if self.on_speech_segment:
                        try:
                            self.on_speech_segment(speech_segment)
                        except Exception as e:
                            print(f"[Vistle VAD] Callback error: {e}")

                self.reset()
