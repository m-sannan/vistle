"""Voice calibration. The window is the warm-light web UI.

The Python methods below are the same ones the headless harness calls.
They do not open a window. `show()` does.
"""

from tkinter import messagebox
import numpy as np

from vistle.audio import AudioCapture
from vistle.config import PhraseConfig, VistleConfig
from vistle.dtw import dtw_distance
from vistle.enrollment import EnrollmentSession
from vistle.template_store import TemplateStore


class _Field:
    """Stand-in for the old text boxes. The harness types into these."""

    def __init__(self, value=""):
        self.value = "" if value is None else str(value)

    def delete(self, start, end=None):
        self.value = ""

    def insert(self, index, text):
        text = "" if text is None else str(text)
        if not self.value:
            self.value = text
        elif index in (0, "0"):
            self.value = text + self.value
        else:
            self.value += text

    def get(self):
        return self.value

    def set(self, value):
        self.value = "" if value is None else str(value)


class _Button:
    def __init__(self, state="normal"):
        self._state = state

    def __getitem__(self, key):
        if key == "state":
            return self._state
        raise KeyError(key)

    def config(self, **kwargs):
        if "state" in kwargs:
            self._state = kwargs["state"]


class _QuietRoot:
    """The harness and older callers expect a window handle. It does nothing."""

    def destroy(self):
        pass

    def lift(self):
        pass

    def focus_force(self):
        pass

    def attributes(self, *args, **kwargs):
        pass

    def after(self, *args, **kwargs):
        return None

    def after_idle(self, *args, **kwargs):
        pass

    def after_cancel(self, *args, **kwargs):
        pass

    def bind(self, *args, **kwargs):
        pass

    def protocol(self, *args, **kwargs):
        pass

    def mainloop(self):
        self_show = getattr(self, "_show", None)
        if self_show:
            self_show()


class EnrollmentWindow:
    """
    Three-take calibration for one wake phrase.
    `show()` opens the Edge window. The test never calls it.
    """

    def __init__(
        self,
        parent,
        audio_capture: AudioCapture,
        config: VistleConfig,
        on_phrase_saved=None,
        on_config_changed=None,
    ):
        self.audio_capture = audio_capture
        self.config = config
        self.on_phrase_saved = on_phrase_saved
        self.on_config_changed = on_config_changed

        self.root = _QuietRoot()
        self.root._show = self.show

        self.session = EnrollmentSession(
            audio_capture=self.audio_capture,
            target_count=3,
            on_sample_recorded=self._on_sample_recorded,
            on_enrollment_complete=self._on_enrollment_complete,
        )

        self.ent_name = _Field("Open Wispr Flow")
        self.ent_spoken = _Field("Hey Wispr")
        self.ent_hotkey = _Field("ctrl+windows+space")
        self.btn_save = _Button("disabled")
        self.btn_record = _Button("normal")
        self._calibrated_threshold = None

    def show(self):
        from vistle.ui.host import reveal_or_launch
        reveal_or_launch(self, "enroll", on_config_changed=self.on_config_changed)

    def _on_sample_recorded(self, count: int, total: int):
        pass

    def _on_enrollment_complete(self):
        self.btn_record.config(state="disabled")
        templates = self.session.get_templates()
        if len(templates) >= 2:
            dists = []
            for i in range(len(templates)):
                for j in range(i + 1, len(templates)):
                    dists.append(dtw_distance(templates[i], templates[j]))
            valid = [d for d in dists if np.isfinite(d)]
            max_d = max(valid) if valid else 1.8
            calibrated = round(max(2.5, min(3.0, max_d * 1.35)), 2)
        else:
            calibrated = 2.85
        self._calibrated_threshold = calibrated
        self.btn_save.config(state="normal")

    def start_enrollment(self):
        """Begin the next take. The page calls this when Record is pressed."""
        if self.session.recorded_count >= self.session.target_count:
            return {
                "ok": False,
                "error": "Already calibrated",
                "ready": True,
                "recording": False,
                "count": self.session.recorded_count,
                "total": self.session.target_count,
                "threshold": self._calibrated_threshold,
            }
        if self.session.is_recording:
            return {
                "ok": True,
                "recording": True,
                "count": self.session.recorded_count,
                "total": self.session.target_count,
                "sample": self.session.recorded_count + 1,
            }
        try:
            self.session.start_sample_recording()
        except Exception as exc:
            return {"ok": False, "error": str(exc), "recording": False, "count": self.session.recorded_count, "total": 3}
        return {
            "ok": True,
            "recording": True,
            "count": self.session.recorded_count,
            "sample": self.session.recorded_count + 1,
            "total": self.session.target_count,
        }

    def stop_sample(self):
        """End the current take and score it. Called when Record is pressed again."""
        if not self.session.is_recording:
            count = self.session.recorded_count
            return {
                "ok": False,
                "error": "Not recording",
                "recording": False,
                "count": count,
                "total": 3,
                "ready": count >= 3,
                "threshold": self._calibrated_threshold,
            }
        success = bool(self.session.stop_sample_recording())
        count = self.session.recorded_count
        ready = count >= 3
        if success:
            message = "Model ready." if ready else f"{count} of 3 samples calibrated"
        else:
            message = "That take was too short or too quiet. Try again."
        return {
            "ok": success,
            "recording": False,
            "count": count,
            "total": 3,
            "ready": ready,
            "threshold": self._calibrated_threshold,
            "message": message,
        }

    def reset_enrollment(self):
        if self.session.is_recording:
            try:
                self.session.stop_sample_recording()
            except Exception:
                pass
        self.session.reset()
        self._calibrated_threshold = None
        self.btn_save.config(state="disabled")
        self.btn_record.config(state="normal")
        return {"ok": True, "count": 0, "total": 3, "ready": False, "recording": False}

    def save_phrase(self, name=None, spoken=None, hotkey=None):
        """Page entry. Does not pop a Tk dialog and does not close the hub."""
        if name is not None:
            self.ent_name.set(name)
        if spoken is not None:
            self.ent_spoken.set(spoken)
        if hotkey is not None:
            self.ent_hotkey.set(hotkey)
        return self._save_phrase(notify=False, close=False)

    def _save_phrase(self, notify=True, close=True):
        name = self.ent_name.get().strip()
        spoken = self.ent_spoken.get().strip()
        if not name or not spoken:
            if notify:
                try:
                    messagebox.showwarning("Incomplete", "Please provide a label and spoken trigger.")
                except Exception:
                    pass
            return {"ok": False, "error": "Please provide a label and spoken trigger."}

        if self.session.recorded_count < 1 and not self.session.get_templates():
            return {"ok": False, "error": "Record the phrase three times first."}

        threshold = getattr(self, "_calibrated_threshold", None) or 3.8
        phrase = PhraseConfig(
            name=name,
            phrase=spoken,
            action_type="hotkey",
            hotkey_spec=self.ent_hotkey.get().strip() or "ctrl+windows+space",
            app_path=None,
            window_title="Wispr",
            process_name="Wispr",
            threshold=threshold,
            enabled=True,
            enrollment_count=3,
        )

        templates = self.session.get_templates()
        TemplateStore.save(phrase.id, templates)

        existing_idx = None
        for i, existing in enumerate(self.config.phrases):
            same_name = existing.name.strip().lower() == phrase.name.strip().lower()
            same_phrase = existing.phrase.strip().lower() == phrase.phrase.strip().lower()
            if same_name or same_phrase:
                existing_idx = i
                break

        if existing_idx is not None:
            old = self.config.phrases[existing_idx]
            if old.id != phrase.id:
                TemplateStore.delete(old.id)
            self.config.phrases[existing_idx] = phrase
        else:
            self.config.phrases.append(phrase)

        self.config.save()

        if self.on_phrase_saved:
            self.on_phrase_saved(phrase)

        if notify:
            try:
                messagebox.showinfo("Saved", f"Trigger '{phrase.name}' is active!")
            except Exception:
                pass
        if close:
            self._on_close()

        return {
            "ok": True,
            "phrase": {
                "id": phrase.id,
                "name": phrase.name,
                "phrase": phrase.phrase,
                "hotkey_spec": phrase.hotkey_spec or "",
                "enabled": True,
                "threshold": phrase.threshold,
            },
        }

    def _on_close(self):
        try:
            self.session.reset()
        except Exception:
            pass
        self.root.destroy()
