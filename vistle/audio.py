import queue
import threading
import numpy as np
import sounddevice as sd
from typing import Callable, Optional, List, Dict

SAMPLE_RATE = 16000

class AudioRingBuffer:
    """Thread-safe circular buffer for float32 audio samples."""
    def __init__(self, capacity: int = 48000): # 3.0 seconds at 16kHz
        self.capacity = capacity
        self.buffer = np.zeros(capacity, dtype=np.float32)
        self.write_pos = 0
        self.total_written = 0
        self._lock = threading.RLock() # RLock permits re-entrant calls from read_last

    def write(self, samples: np.ndarray):
        with self._lock:
            n = len(samples)
            if n == 0:
                return
            if n >= self.capacity:
                self.buffer[:] = samples[-self.capacity:]
                self.write_pos = 0
            else:
                end_pos = self.write_pos + n
                if end_pos <= self.capacity:
                    self.buffer[self.write_pos:end_pos] = samples
                    self.write_pos = end_pos % self.capacity
                else:
                    first_chunk = self.capacity - self.write_pos
                    self.buffer[self.write_pos:] = samples[:first_chunk]
                    second_chunk = n - first_chunk
                    self.buffer[:second_chunk] = samples[first_chunk:]
                    self.write_pos = second_chunk
            self.total_written += n

    def read_all(self) -> np.ndarray:
        with self._lock:
            if self.total_written < self.capacity:
                return self.buffer[:self.write_pos].copy()
            return np.concatenate((self.buffer[self.write_pos:], self.buffer[:self.write_pos]))

    def read_last(self, count: int) -> np.ndarray:
        with self._lock:
            available = min(self.count, count)
            if available == 0:
                return np.zeros(0, dtype=np.float32)
            all_samples = self.read_all()
            return all_samples[-available:]

    @property
    def count(self) -> int:
        with self._lock:
            return min(self.total_written, self.capacity)

    def clear(self):
        with self._lock:
            self.buffer.fill(0)
            self.write_pos = 0
            self.total_written = 0


class AudioCapture:
    """Microphone audio capture using sounddevice (WASAPI/DirectSound)."""
    def __init__(self, device_name_or_index=None, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate
        self.device = device_name_or_index
        self._stream: Optional[sd.InputStream] = None
        self._callbacks: List[Callable[[np.ndarray], None]] = []
        self._lock = threading.RLock()
        self._running = False
        self._queue = queue.Queue(maxsize=100)
        self._worker_thread: Optional[threading.Thread] = None

    def add_callback(self, cb: Callable[[np.ndarray], None]):
        with self._lock:
            if cb not in self._callbacks:
                self._callbacks.append(cb)

    def remove_callback(self, cb: Callable[[np.ndarray], None]):
        with self._lock:
            if cb in self._callbacks:
                self._callbacks.remove(cb)

    def _audio_callback(self, indata, frames, time_info, status):
        if status and status.input_overflow:
            print("[Vistle Audio] Audio buffer overflow in WASAPI")
        samples = indata[:, 0].copy()
        try:
            self._queue.put_nowait(samples)
        except queue.Full:
            pass # Drop frame rather than blocking high-priority audio callback

    def _dispatch_loop(self):
        while self._running:
            try:
                samples = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            with self._lock:
                callbacks = list(self._callbacks)
            for cb in callbacks:
                try:
                    cb(samples)
                except Exception as e:
                    print(f"[Vistle Audio] Callback error: {e}")
            self._queue.task_done()

    def start(self):
        with self._lock:
            if self._running:
                return
            try:
                device_idx = None
                if self.device is not None:
                    if isinstance(self.device, int):
                        device_idx = self.device
                    else:
                        devices = sd.query_devices()
                        for i, d in enumerate(devices):
                            if d['max_input_channels'] > 0 and self.device.lower() in d['name'].lower():
                                device_idx = i
                                break

                while not self._queue.empty():
                    try:
                        self._queue.get_nowait()
                    except queue.Empty:
                        break

                self._running = True
                self._worker_thread = threading.Thread(target=self._dispatch_loop, daemon=True)
                self._worker_thread.start()

                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype='float32',
                    blocksize=512,
                    device=device_idx,
                    callback=self._audio_callback
                )
                self._stream.start()
                print(f"[Vistle Audio] Started capture at {self.sample_rate}Hz")
            except Exception as e:
                self._running = False
                print(f"[Vistle Audio] Failed to start stream: {e}")
                raise

    def stop(self):
        with self._lock:
            if not self._running:
                return
            self._running = False
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
            if self._worker_thread and self._worker_thread.is_alive():
                if threading.current_thread() != self._worker_thread:
                    self._worker_thread.join(timeout=0.3)
                self._worker_thread = None
            print("[Vistle Audio] Stopped capture")

    @property
    def is_running(self) -> bool:
        return self._running

    @staticmethod
    def list_input_devices() -> List[Dict]:
        try:
            devices = sd.query_devices()
            inputs = []
            for i, d in enumerate(devices):
                if d['max_input_channels'] > 0:
                    inputs.append({
                        "index": i,
                        "name": d['name'],
                        "channels": d['max_input_channels'],
                        "sample_rate": d['default_samplerate']
                    })
            return inputs
        except Exception as e:
            print(f"[Vistle Audio] Error enumerating devices: {e}")
            return []
