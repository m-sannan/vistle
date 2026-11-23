import numpy as np
from scipy.fft import dct

class MfccExtractor:
    """
    Mel-Frequency Cepstral Coefficients (MFCC) extractor.
    Operates strictly on-device with zero network and zero audio persistence.
    """
    def __init__(
        self,
        sample_rate: int = 16000,
        frame_size: int = 400,    # 25ms
        hop_size: int = 160,      # 10ms
        n_fft: int = 512,
        n_mels: int = 26,
        n_mfcc: int = 13,
        pre_emphasis: float = 0.97
    ):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.hop_size = hop_size
        self.n_fft = n_fft
        self.n_mels = n_mels
        self.n_mfcc = n_mfcc
        self.pre_emphasis = pre_emphasis

        self.hamming_window = np.hamming(self.frame_size)
        self.mel_filters = self._build_mel_filterbank()

    @staticmethod
    def _hz_to_mel(hz):
        return 2595.0 * np.log10(1.0 + hz / 700.0)

    @staticmethod
    def _mel_to_hz(mel):
        return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

    def _build_mel_filterbank(self) -> np.ndarray:
        low_mel = self._hz_to_mel(0)
        high_mel = self._hz_to_mel(self.sample_rate / 2)
        mel_points = np.linspace(low_mel, high_mel, self.n_mels + 2)
        hz_points = self._mel_to_hz(mel_points)
        bins = np.floor((self.n_fft + 1) * hz_points / self.sample_rate).astype(int)

        filters = np.zeros((self.n_mels, self.n_fft // 2 + 1))
        for m in range(1, self.n_mels + 1):
            f_m_minus = bins[m - 1]
            f_m = bins[m]
            f_m_plus = bins[m + 1]

            if f_m > f_m_minus:
                filters[m - 1, f_m_minus:f_m] = (
                    np.arange(f_m_minus, f_m) - f_m_minus
                ) / (f_m - f_m_minus)
            if f_m_plus > f_m:
                filters[m - 1, f_m:f_m_plus] = (
                    f_m_plus - np.arange(f_m, f_m_plus)
                ) / (f_m_plus - f_m)

        return filters

    def extract(self, samples: np.ndarray) -> np.ndarray:
        """
        Extract MFCC features from 1D audio sample array.
        Returns:
            2D numpy array of shape (n_frames, n_mfcc), or empty array if too short.
        """
        if len(samples) < self.frame_size:
            return np.zeros((0, self.n_mfcc), dtype=np.float32)

        # 1. Pre-emphasis filter
        emphasized = np.append(samples[0], samples[1:] - self.pre_emphasis * samples[:-1])

        # 2. Frame segmentation
        num_frames = 1 + int((len(emphasized) - self.frame_size) / self.hop_size)
        if num_frames <= 0:
            return np.zeros((0, self.n_mfcc), dtype=np.float32)

        indices = (
            np.tile(np.arange(0, self.frame_size), (num_frames, 1))
            + np.tile(np.arange(0, num_frames * self.hop_size, self.hop_size), (self.frame_size, 1)).T
        )
        frames = emphasized[indices]

        # 3. Windowing
        frames = frames * self.hamming_window

        # 4. FFT & Power Spectrum
        mag_frames = np.abs(np.fft.rfft(frames, self.n_fft))
        pow_frames = (1.0 / self.n_fft) * (mag_frames ** 2)

        # 5. Mel Filterbank energies (clamped safely above zero)
        filter_energies = np.dot(pow_frames, self.mel_filters.T)
        filter_energies = np.maximum(filter_energies, 1e-10)
        log_energies = np.log(filter_energies)

        # 6. DCT-II for MFCCs
        mfccs = dct(log_energies, type=2, axis=1, norm='ortho')[:, :self.n_mfcc]

        # 7. Cepstral Mean & Variance Normalization (CMVN)
        if mfccs.shape[0] > 1:
            mfccs -= np.mean(mfccs, axis=0, keepdims=True)
            std = np.std(mfccs, axis=0, keepdims=True)
            std = np.maximum(std, 1e-5)
            mfccs /= std

        # 8. Compute Dynamic Features: Delta (velocity) and Delta-Delta (acceleration)
        # Expands features from 13 static -> 39 dynamic dimensions (13 static + 13 delta + 13 delta-delta).
        # This captures phoneme transition trajectories, rejecting phonetically distinct
        # false positives like "open" or "hey Google" when targeting "Hey Wispr".
        deltas = self.compute_deltas(mfccs, n=2)
        delta_deltas = self.compute_deltas(deltas, n=2)

        features_39d = np.hstack([mfccs, deltas, delta_deltas])
        return features_39d.astype(np.float32)

    @staticmethod
    def compute_deltas(features: np.ndarray, n: int = 2) -> np.ndarray:
        """
        Computes delta (derivative) coefficients over time.
        d_t = sum_{i=1}^n i * (c_{t+i} - c_{t-i}) / (2 * sum_{i=1}^n i^2)
        """
        if len(features) == 0:
            return np.zeros_like(features)
        num_frames = features.shape[0]
        if num_frames < 2:
            return np.zeros_like(features)

        padded = np.pad(features, ((n, n), (0, 0)), mode='edge')
        deltas = np.zeros_like(features)
        denom = 2.0 * sum(i ** 2 for i in range(1, n + 1))

        for i in range(1, n + 1):
            deltas += i * (padded[n + i : n + i + num_frames] - padded[n - i : n - i + num_frames])

        return (deltas / denom).astype(np.float32)
