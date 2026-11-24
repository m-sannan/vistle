"""One native window for the life of the tray app.

Edge WebView2 on Windows. The page is the warm-light hub. pywebview's
loop can be started once, so the window is created hidden and shown again
from the tray. The harness never reaches this module.
"""

import sys
import threading
from pathlib import Path

_lock = threading.Lock()
_state = {
    "window": None,
    "enrollment": None,
    "settings": None,
    "started": False,
}


def _page_url(view: str) -> str:
    html = Path(__file__).resolve().parent / "assets" / "app.html"
    return html.as_uri() + "?view=" + view


def _edge_or_default(start):
    if sys.platform == "win32":
        try:
            start(gui="edgechromium")
            return
        except Exception as exc:
            print(f"[Vistle] Edge WebView2 unavailable ({exc}). Falling back.")
    start()


class VistleApi:
    """Methods the page calls. Names match the product contract."""

    def __init__(self, enrollment, settings):
        self._enrollment = enrollment
        self._settings = settings

    def list_phrases(self):
        return self._settings.list_phrases()

    def toggle_phrase(self, phrase_id):
        return self._settings.toggle_phrase(phrase_id)

    def delete_phrase(self, phrase_id):
        return self._settings.delete_phrase(phrase_id)

    def update_phrase(self, phrase_id, name=None, hotkey=None, spoken=None):
        return self._settings.update_phrase(phrase_id, name=name, hotkey=hotkey, spoken=spoken)

    def start_enrollment(self):
        return self._enrollment.start_enrollment()

    def stop_sample(self):
        return self._enrollment.stop_sample()

    def reset_enrollment(self):
        return self._enrollment.reset_enrollment()

    def save_phrase(self, name, spoken, hotkey):
        result = self._enrollment.save_phrase(name, spoken, hotkey)
        if result.get("ok"):
            self._settings.config = self._enrollment.config
        return result

    def close(self):
        window = _state.get("window")
        if window is not None:
            try:
                window.hide()
            except Exception:
                try:
                    window.destroy()
                except Exception:
                    pass
        return {"ok": True}


def reveal(view: str):
    """Show the already-running window on the hub or on calibration."""
    window = _state.get("window")
    if window is None:
        return False
    try:
        window.show()
        window.evaluate_js(f"window.vistleShow && window.vistleShow({view!r})")
    except Exception as exc:
        print(f"[Vistle] Could not show window: {exc}")
        return False
    return True


def shutdown():
    window = _state.get("window")
    _state["quitting"] = True
    if window is None:
        return
    try:
        window.destroy()
    except Exception:
        pass
    _state["window"] = None


def reveal_or_launch(enrollment, view: str, on_config_changed=None):
    """
    If the tray already started the Edge loop, just show the window.
    A direct show() with no loop yet starts one and blocks until it closes.
    """
    with _lock:
        already = _state["started"]
    if already and _state.get("window") is not None:
        _state["enrollment"] = enrollment
        if _state.get("settings") is not None:
            _state["settings"].enrollment = enrollment
            _state["settings"].on_config_changed = on_config_changed or _state["settings"].on_config_changed
        reveal(view)
        return

    from vistle.ui.settings_gui import SettingsWindow

    settings = SettingsWindow(
        None,
        enrollment.audio_capture,
        enrollment.config,
        on_config_changed=on_config_changed or enrollment.on_config_changed,
        enrollment=enrollment,
    )
    launch(enrollment, settings, start_view=view)


def launch(enrollment, settings, start_view="hub"):
    """Blocking. Call from the main thread. Returns when the window is destroyed."""
    import webview

    with _lock:
        if _state["started"]:
            reveal(start_view)
            return
        _state["started"] = True
        _state["enrollment"] = enrollment
        _state["settings"] = settings

    api = VistleApi(enrollment, settings)
    window = webview.create_window(
        "Vistle",
        _page_url(start_view),
        js_api=api,
        width=980,
        height=720,
        min_size=(860, 620),
        background_color="#F7F5F0",
        hidden=(start_view != "enroll"),
        text_select=True,
    )
    _state["window"] = window

    def _on_closing():
        if _state.get("quitting"):
            return True
        try:
            window.hide()
        except Exception:
            pass
        return False

    window.events.closing += _on_closing

    try:
        _edge_or_default(webview.start)
    finally:
        with _lock:
            _state["started"] = False
            _state["window"] = None
