import numpy as np
import time
import threading
from vistle.config import VistleConfig, PhraseConfig
from vistle.mfcc import MfccExtractor
from vistle.dtw import dtw_distance
from vistle.hotkey import HotkeySender, VK_MAP, StopKeyWatcher
from vistle.audio import AudioRingBuffer
from vistle.vad import VoiceActivityDetector

def test_pipeline():
    print("=== Testing Vistle Core Pipeline ===")

    # 1. Config Test
    config = VistleConfig.load()
    print(f"✓ Config loaded: {len(config.phrases)} phrases")

    # 2. MFCC Extraction Test
    extractor = MfccExtractor(sample_rate=16000)
    t = np.linspace(0, 1.0, 16000, endpoint=False, dtype=np.float32)
    tone1 = 0.3 * np.sin(2 * np.pi * 440 * t) + 0.15 * np.sin(2 * np.pi * 880 * t)
    tone2 = 0.3 * np.sin(2 * np.pi * 440 * t) + 0.15 * np.sin(2 * np.pi * 880 * t) # identical
    tone3 = 0.3 * np.sin(2 * np.pi * 1200 * t) # very different pitch

    mfcc1 = extractor.extract(tone1)
    mfcc2 = extractor.extract(tone2)
    mfcc3 = extractor.extract(tone3)

    print(f"✓ MFCC extracted: shape = {mfcc1.shape} (frames, coeffs)")
    assert mfcc1.shape[1] == 39, "MFCC should have 39 dynamic coefficients (13 static + 13 delta + 13 delta-delta)"

    # 3. DTW Matching Test & Edge Cases
    dist_same = dtw_distance(mfcc1, mfcc2)
    dist_diff = dtw_distance(mfcc1, mfcc3)
    print(f"✓ DTW distance (identical audio): {dist_same:.4f}")
    print(f"✓ DTW distance (different audio): {dist_diff:.4f}")
    assert dist_same < 0.05, "Identical audio should have near-zero distance"
    assert dist_diff > dist_same, "Different audio should have higher distance"

    # DTW edge cases: 1D array, empty array, NaN inputs
    assert dtw_distance(np.zeros(0), mfcc1) == float('inf'), "Empty array must return inf"
    assert dtw_distance(np.zeros(5), mfcc1) == float('inf'), "1D array must return inf without crash"
    nan_arr = np.full((10, 39), np.nan, dtype=np.float32)
    assert dtw_distance(nan_arr, mfcc1) == float('inf'), "NaN array must return inf safely"
    print("✓ DTW edge cases (empty, 1D, NaN) verified")

    # 4. AudioRingBuffer Re-entrancy Test (RLock verify)
    ring = AudioRingBuffer(capacity=1600)
    samples = np.ones(500, dtype=np.float32)
    ring.write(samples)
    last = ring.read_last(200) # Re-entrantly calls self.count and self.read_all
    assert len(last) == 200, "read_last must return correct sample count without deadlock"
    print("✓ AudioRingBuffer re-entrancy and read_last verified")

    # 5. VAD DC Bias Rejection Test
    vad = VoiceActivityDetector()
    dc_chunk = np.full(512, 0.05, dtype=np.float32) # Pure DC bias with zero AC speech
    vad.process(dc_chunk)
    assert not vad._in_speech, "Pure DC offset must not falsely trigger speech"
    print("✓ VAD DC bias compensation verified")

    # 6. StopKeyWatcher Self-Join Thread Safety Test
    watcher = StopKeyWatcher("ctrl+space", on_stop_pressed=lambda: None)
    # Calling stop from current thread must not throw RuntimeError: cannot join current thread
    watcher.stop()
    print("✓ StopKeyWatcher thread safety verified")

    # 7. Hotkey Virtual Key mapping test
    assert "ctrl" in VK_MAP
    assert "shift" in VK_MAP
    assert "space" in VK_MAP
    print("✓ Hotkey VK mappings verified")

    print("\n🎉 ALL CORE PIPELINE TESTS & REGRESSION CHECKS PASSED!")

if __name__ == "__main__":
    test_pipeline()
