"""Few-shot wake spotting for both a fast phrase and a slow one.

Enrollment is careful, so those takes are long. Matching the live audio
against that clock makes a quicker "hey wispr" look like a different
phrase. This puts every utterance on the enrollment length first, then
asks one question: is it the same speech?

A clear raw match is still accepted, so the slow way that already works
keeps working. Clicks, long stretches of unrelated speech, and phrases
that only sound similar are refused.
"""

import numpy as np

from vistle.dtw import dtw_distance
from vistle.mfcc import MfccExtractor

# Tempo-normalized true phrases cluster under this. Similar-but-wrong
# phrases stay above it, at a loose saved threshold of 2.5–3.0.
MATCH_CAP = 2.00
# A match this far under the saved threshold is the phrase, not a near miss.
CLEAR_FRACTION = 0.78
CLEAR_CAP = 2.05
# Near misses must be this much closer to the real takes than to the
# time-reversed takes, or they are the old "sounds similar" false accept.
GRAY_REVERSE_MARGIN = 0.65
MIN_FRAMES = 20
# Still refuse coughs that are far shorter than the enrolled phrase.
MIN_FAST_FRACTION = 0.18
MAX_SLOW_FRACTION = 2.80
MAX_FRAMES = 340


class SpotResult:
    def __init__(self, accept: bool, distance: float, reason: str):
        self.accept = accept
        self.distance = distance
        self.reason = reason


def _as_39(mfcc: np.ndarray) -> np.ndarray:
    if mfcc.ndim != 2 or mfcc.shape[0] == 0:
        return mfcc
    if mfcc.shape[1] == 39:
        return mfcc
    if mfcc.shape[1] == 13:
        delta = MfccExtractor.compute_deltas(mfcc)
        delta2 = MfccExtractor.compute_deltas(delta)
        return np.hstack([mfcc, delta, delta2]).astype(np.float32)
    return mfcc


def _resample_frames(seq: np.ndarray, target_len: int) -> np.ndarray:
    n, dim = seq.shape
    if n == target_len:
        return seq.astype(np.float32, copy=False)
    if n < 1 or target_len < 1:
        return np.zeros((max(target_len, 0), dim), dtype=np.float32)
    src = seq if n > 1 else np.repeat(seq, 2, axis=0)
    x_old = np.linspace(0.0, 1.0, src.shape[0])
    x_new = np.linspace(0.0, 1.0, target_len)
    out = np.empty((target_len, dim), dtype=np.float32)
    for k in range(dim):
        out[:, k] = np.interp(x_new, x_old, src[:, k])
    return out


def _on_enrollment_clock(mfcc: np.ndarray, target_len: int) -> np.ndarray:
    """Static cepstra warped to the enrolled length, then deltas recomputed.

    Deltas taken on the original clock get larger when the same phrase is
    said faster. Recomputing them after the warp removes that tempo penalty
    without throwing away the phonetic shape.
    """
    feat = _as_39(mfcc)
    static = feat[:, :13]
    warped = _resample_frames(static, target_len)
    delta = MfccExtractor.compute_deltas(warped)
    delta2 = MfccExtractor.compute_deltas(delta)
    # Shape carries identity. Velocity is down-weighted so leftover timing
    # error cannot outvote a correct phrase.
    return np.hstack([warped, delta * 0.65, delta2 * 0.35]).astype(np.float32)


def _robust_distance(query: np.ndarray, templates) -> float:
    """Mean of the two nearest takes. One lucky template cannot fire alone."""
    dists = []
    for tmpl in templates:
        if tmpl.ndim != 2 or tmpl.shape[0] == 0 or tmpl.shape[1] != query.shape[1]:
            continue
        dists.append(dtw_distance(query, tmpl))
    if not dists:
        return float("inf")
    dists.sort()
    if len(dists) == 1:
        return float(dists[0])
    return float(np.mean(dists[:2]))


def _normalized_distance(query: np.ndarray, templates) -> float:
    lengths = [t.shape[0] for t in templates if getattr(t, "ndim", 0) == 2 and t.shape[0] > 0]
    if not lengths:
        return float("inf")
    target = int(np.clip(int(np.median(lengths)), 40, 140))
    q = _on_enrollment_clock(query, target)
    warped = [_on_enrollment_clock(t, target) for t in templates]
    return _robust_distance(q, warped)


def evaluate(query_mfcc: np.ndarray, templates, threshold: float, avg_frames: float) -> SpotResult:
    if query_mfcc is None or getattr(query_mfcc, "ndim", 0) != 2 or query_mfcc.shape[0] == 0:
        return SpotResult(False, float("inf"), "empty")

    query = _as_39(query_mfcc)
    bank = [_as_39(t) for t in templates]
    frames = int(query.shape[0])
    enrolled = float(avg_frames) if avg_frames and avg_frames > 0 else float(frames)

    lo = max(float(MIN_FRAMES), enrolled * MIN_FAST_FRACTION)
    hi = min(float(MAX_FRAMES), max(enrolled * MAX_SLOW_FRACTION, lo + 30.0))
    if frames < lo or frames > hi:
        return SpotResult(False, float("inf"), "duration")

    raw = _robust_distance(query, bank)
    # Same speech, one clock. A fast take and a slow take of the phrase
    # land next to each other here. A different phrase does not.
    norm = _normalized_distance(query, bank)
    match_bar = min(float(threshold) * 0.82, MATCH_CAP)
    if np.isfinite(norm) and norm < match_bar:
        return SpotResult(True, norm, "match")

    # Slow, careful speech already sits close before any time warp.
    # Keep that path so a working slow trigger cannot regress.
    clear_bar = min(float(threshold) * CLEAR_FRACTION, CLEAR_CAP)
    if np.isfinite(raw) and raw < clear_bar:
        return SpotResult(True, raw, "clear")

    if np.isfinite(raw) and raw < float(threshold):
        reversed_bank = [np.ascontiguousarray(t[::-1]) for t in bank]
        margin = _robust_distance(query, reversed_bank) - raw
        if margin > GRAY_REVERSE_MARGIN and np.isfinite(norm) and norm < match_bar:
            return SpotResult(True, raw, "checked")
        return SpotResult(False, raw, "near-miss")

    return SpotResult(False, raw if np.isfinite(raw) else float("inf"), "far")
