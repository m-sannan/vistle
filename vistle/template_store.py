import json
import os
import numpy as np
from typing import List, Optional
from vistle.config import VistleConfig, TEMPLATES_DIR

class TemplateStore:
    """
    Saves and loads numerical MFCC templates.
    Strict privacy: only feature matrices are persisted; raw audio is NEVER saved.
    """
    @staticmethod
    def save(phrase_id: str, sample_mfccs: List[np.ndarray]):
        """
        Saves a list of 2D MFCC arrays (one per enrollment recording) to disk.
        """
        os.makedirs(TEMPLATES_DIR, exist_ok=True)
        path = VistleConfig.template_path(phrase_id)
        # Convert numpy arrays to nested lists of floats
        data = {
            "phrase_id": phrase_id,
            "samples": [mfcc.tolist() for mfcc in sample_mfccs]
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        print(f"[Vistle TemplateStore] Saved {len(sample_mfccs)} templates for {phrase_id}")

    @staticmethod
    def load(phrase_id: str) -> Optional[List[np.ndarray]]:
        """
        Loads 2D MFCC arrays for a given phrase ID.
        """
        path = VistleConfig.template_path(phrase_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            valid_templates = []
            for sample in data.get("samples", []):
                arr = np.array(sample, dtype=np.float32)
                if arr.ndim == 2 and arr.shape[0] > 0 and arr.shape[1] in (13, 39):
                    valid_templates.append(arr)
            return valid_templates if valid_templates else None
        except Exception as e:
            print(f"[Vistle TemplateStore] Failed to load template for {phrase_id}: {e}")
            return None

    @staticmethod
    def delete(phrase_id: str):
        path = VistleConfig.template_path(phrase_id)
        if os.path.exists(path):
            try:
                os.remove(path)
                print(f"[Vistle TemplateStore] Deleted template for {phrase_id}")
            except Exception as e:
                print(f"[Vistle TemplateStore] Failed to delete template {phrase_id}: {e}")

    @staticmethod
    def exists(phrase_id: str) -> bool:
        return os.path.exists(VistleConfig.template_path(phrase_id))
