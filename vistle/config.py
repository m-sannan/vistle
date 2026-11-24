import json
import os
import tempfile
import uuid
from dataclasses import dataclass, field, asdict
from typing import List, Optional

def _resolve_data_dir() -> str:
    # 1. Explicit environment variable
    env_dir = os.environ.get("VISTLE_DATA_DIR") or os.environ.get("WHISTLE_DATA_DIR")
    if env_dir:
        try:
            os.makedirs(env_dir, exist_ok=True)
            return env_dir
        except (PermissionError, OSError):
            pass

    # 2. Try AppData/Local/Vistle (or migrate legacy Whistle)
    appdata = os.environ.get("LOCALAPPDATA")
    if appdata:
        target = os.path.join(appdata, "Vistle")
        legacy = os.path.join(appdata, "Vistle")
        if not os.path.exists(target) and os.path.exists(legacy):
            try:
                import shutil
                shutil.copytree(legacy, target, dirs_exist_ok=True)
            except Exception:
                target = legacy
        try:
            os.makedirs(target, exist_ok=True)
            # Test write access
            test_file = os.path.join(target, ".perm_test")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            return target
        except (PermissionError, OSError):
            pass

    # 3. Fallback to user home directory ~/.vistle
    user_home = os.path.expanduser("~")
    home_vistle = os.path.join(user_home, ".vistle")
    try:
        os.makedirs(home_vistle, exist_ok=True)
        return home_vistle
    except (PermissionError, OSError):
        pass

    # 4. Fallback to local directory
    local_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".vistle_data")
    try:
        os.makedirs(local_dir, exist_ok=True)
        return local_dir
    except (PermissionError, OSError):
        return os.path.dirname(os.path.abspath(__file__))

APPDATA_DIR = _resolve_data_dir()
CONFIG_PATH = os.path.join(APPDATA_DIR, "config.json")
TEMPLATES_DIR = os.path.join(APPDATA_DIR, "templates")

@dataclass
class PhraseConfig:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = ""
    phrase: str = ""
    action_type: str = "hotkey"  # "hotkey" or "launch_app"
    hotkey_spec: Optional[str] = "ctrl+shift+space"
    app_path: Optional[str] = None
    process_name: Optional[str] = None
    window_title: Optional[str] = None
    threshold: float = 2.85  # Sweet spot for natural conversational tempo & 39-D dynamic MFCC distance
    enabled: bool = True
    enrollment_count: int = 3

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            return cls()
        cleaned = {}
        for k, v in data.items():
            if k in cls.__dataclass_fields__:
                if k == "threshold":
                    try:
                        cleaned[k] = float(v)
                    except (ValueError, TypeError):
                        cleaned[k] = 2.85
                elif k == "enabled":
                    cleaned[k] = bool(v)
                elif k in ("name", "phrase", "action_type"):
                    cleaned[k] = str(v) if v is not None else ""
                elif k in ("hotkey_spec", "app_path", "process_name", "window_title"):
                    cleaned[k] = str(v) if v is not None else None
                else:
                    cleaned[k] = v
        return cls(**cleaned)


@dataclass
class VistleConfig:
    phrases: List[PhraseConfig] = field(default_factory=list)
    start_with_windows: bool = False
    start_listening_on_launch: bool = True
    preferred_microphone: Optional[str] = None
    cooldown_ms: int = 400  # Snappy 400ms cooldown (down from 2000ms)

    @classmethod
    def template_path(cls, phrase_id: str) -> str:
        return os.path.join(TEMPLATES_DIR, f"{phrase_id}.json")

    @classmethod
    def load(cls) -> "VistleConfig":
        try:
            os.makedirs(APPDATA_DIR, exist_ok=True)
            os.makedirs(TEMPLATES_DIR, exist_ok=True)
        except (PermissionError, OSError):
            pass

        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                raw_phrases = [PhraseConfig.from_dict(p) for p in data.get("phrases", [])]

                # Automatic deduplication: purge stale duplicate ghost phrases
                seen_keys = {}
                phrases = []
                changed = False
                for p in reversed(raw_phrases):
                    key = (p.name.strip().lower(), p.phrase.strip().lower())
                    if key not in seen_keys:
                        seen_keys[key] = p
                        phrases.append(p)
                    else:
                        changed = True
                        print(f"[Vistle Config] Purging duplicate ghost phrase '{p.name}' ({p.id})")
                        try:
                            from vistle.template_store import TemplateStore
                            TemplateStore.delete(p.id)
                        except Exception:
                            pass
                phrases = list(reversed(phrases))
                
                changed = False
                for p in phrases:
                    # Ensure threshold is set to the natural conversational tempo sweet spot (2.85)
                    if p.threshold > 3.2 or p.threshold < 1.8:
                        p.threshold = 2.85
                        changed = True

                cooldown = data.get("cooldown_ms", 400)
                if cooldown > 800:
                    cooldown = 400
                    changed = True

                cfg = cls(
                    phrases=phrases,
                    start_with_windows=data.get("start_with_windows", False),
                    start_listening_on_launch=data.get("start_listening_on_launch", True),
                    preferred_microphone=data.get("preferred_microphone"),
                    cooldown_ms=cooldown,
                )
                if changed:
                    try:
                        cfg.save()
                    except Exception:
                        pass
                return cfg
            except Exception as e:
                print(f"[Vistle Config] Error loading config: {e}. Starting fresh.")
        return cls()

    def save(self):
        try:
            os.makedirs(APPDATA_DIR, exist_ok=True)
            os.makedirs(TEMPLATES_DIR, exist_ok=True)
            data = {
                "phrases": [p.to_dict() for p in self.phrases],
                "start_with_windows": self.start_with_windows,
                "start_listening_on_launch": self.start_listening_on_launch,
                "preferred_microphone": self.preferred_microphone,
                "cooldown_ms": self.cooldown_ms,
            }
            tmp_fd, tmp_path = tempfile.mkstemp(dir=APPDATA_DIR, prefix="cfg_", suffix=".tmp")
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, CONFIG_PATH)
        except Exception as e:
            print(f"[Vistle Config] Save config error: {e}")

# Backward-compatibility alias
WhistleConfig = VistleConfig

