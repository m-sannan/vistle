"""Trigger dashboard. The window is the same warm-light page as calibration."""

from vistle.audio import AudioCapture
from vistle.config import VistleConfig
from vistle.template_store import TemplateStore
from vistle.ui.enrollment_gui import EnrollmentWindow


def _phrase_payload(phrase):
    return {
        "id": phrase.id,
        "name": phrase.name,
        "phrase": phrase.phrase,
        "hotkey_spec": phrase.hotkey_spec or "",
        "enabled": bool(phrase.enabled),
        "threshold": float(phrase.threshold) if phrase.threshold is not None else 2.85,
        "action_type": phrase.action_type or "hotkey",
    }


class SettingsWindow:
    """
    Hub of saved triggers.
    Phrase changes go through list / toggle / delete / update, which the page calls.
    """

    def __init__(self, parent, audio_capture: AudioCapture, config: VistleConfig, on_config_changed=None, enrollment: EnrollmentWindow = None):
        self.audio_capture = audio_capture
        self.config = config
        self.on_config_changed = on_config_changed
        self.enrollment = enrollment or EnrollmentWindow(
            parent,
            audio_capture,
            config,
            on_phrase_saved=self._on_phrase_saved,
            on_config_changed=on_config_changed,
        )

    def _on_phrase_saved(self, phrase):
        self.config = VistleConfig.load()
        self.enrollment.config = self.config
        if self.on_config_changed:
            self.on_config_changed()

    def show(self):
        from vistle.ui.host import reveal_or_launch
        reveal_or_launch(self.enrollment, "hub", on_config_changed=self.on_config_changed)

    def _reload(self):
        self.config = VistleConfig.load()
        if self.enrollment is not None:
            self.enrollment.config = self.config
        return self.config

    def list_phrases(self):
        config = self._reload()
        return {"ok": True, "phrases": [_phrase_payload(p) for p in config.phrases]}

    def toggle_phrase(self, phrase_id):
        config = self._reload()
        found = None
        for phrase in config.phrases:
            if phrase.id == phrase_id:
                phrase.enabled = not bool(phrase.enabled)
                found = phrase
                break
        if found is None:
            return {"ok": False, "error": "Trigger not found"}
        config.save()
        self.config = config
        if self.on_config_changed:
            self.on_config_changed()
        return {"ok": True, "phrase": _phrase_payload(found), "phrases": [_phrase_payload(p) for p in config.phrases]}

    def delete_phrase(self, phrase_id):
        config = self._reload()
        before = len(config.phrases)
        config.phrases = [p for p in config.phrases if p.id != phrase_id]
        if len(config.phrases) == before:
            return {"ok": False, "error": "Trigger not found"}
        config.save()
        TemplateStore.delete(phrase_id)
        self.config = config
        if self.on_config_changed:
            self.on_config_changed()
        return {"ok": True, "phrases": [_phrase_payload(p) for p in config.phrases]}

    def update_phrase(self, phrase_id, name=None, hotkey=None, spoken=None):
        config = self._reload()
        found = None
        for phrase in config.phrases:
            if phrase.id == phrase_id:
                if name is not None and str(name).strip():
                    phrase.name = str(name).strip()
                if spoken is not None and str(spoken).strip():
                    phrase.phrase = str(spoken).strip()
                if hotkey is not None and str(hotkey).strip():
                    phrase.hotkey_spec = str(hotkey).strip()
                found = phrase
                break
        if found is None:
            return {"ok": False, "error": "Trigger not found"}
        config.save()
        self.config = config
        if self.on_config_changed:
            self.on_config_changed()
        return {"ok": True, "phrase": _phrase_payload(found), "phrases": [_phrase_payload(p) for p in config.phrases]}
