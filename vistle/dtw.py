import numpy as np

def dtw_distance(seq1: np.ndarray, seq2: np.ndarray, window_ratio: float = 0.25) -> float:
    """
    Computes normalized Dynamic Time Warping (DTW) distance between two MFCC sequences
    using Euclidean local distance and a Sakoe-Chiba band constraint.
    
    Args:
        seq1: (N, D) array of MFCC frames
        seq2: (M, D) array of MFCC frames
        window_ratio: Sakoe-Chiba band width as a fraction of sequence length
        
    Returns:
        Normalized distance (lower = closer match). Returns inf if invalid.
    """
    if not isinstance(seq1, np.ndarray) or not isinstance(seq2, np.ndarray):
        return float('inf')

    if seq1.ndim != 2 or seq2.ndim != 2:
        return float('inf')

    n, d1 = seq1.shape
    m, d2 = seq2.shape

    if n == 0 or m == 0 or d1 != d2:
        return float('inf')

    # Sakoe-Chiba band window
    w = max(abs(n - m), int(max(n, m) * window_ratio))

    # Cost matrix initialized to infinity
    cost = np.full((n + 1, m + 1), np.inf, dtype=np.float32)
    cost[0, 0] = 0.0

    # Euclidean distance computation with band constraint
    for i in range(1, n + 1):
        j_start = max(1, i - w)
        j_end = min(m + 1, i + w + 1)
        
        # Vectorized distance for row i
        v1 = seq1[i - 1]
        v2_slice = seq2[j_start - 1 : j_end - 1]
        dists = np.linalg.norm(v2_slice - v1, axis=1)

        for idx, j in enumerate(range(j_start, j_end)):
            dist = dists[idx]
            cost[i, j] = dist + min(
                cost[i - 1, j],       # insertion
                cost[i, j - 1],       # deletion
                cost[i - 1, j - 1]    # match
            )

    raw_dist = cost[n, m]
    if np.isinf(raw_dist) or np.isnan(raw_dist):
        return float('inf')

    # Normalize by path length
    norm = float(raw_dist / (n + m))
    return float('inf') if np.isnan(norm) else norm
