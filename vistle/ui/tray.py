import threading
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item
from vistle import __version__
from vistle.audio import AudioCapture
from vistle.config import VistleConfig, PhraseConfig
from vistle.engine import WakeWordEngine
from vistle.actions import ActionExecutor
from vistle.ui.enrollment_gui import EnrollmentWindow
from vistle.ui.settings_gui import SettingsWindow

class TrayApp:
    """
    Vistle background system tray host.
    Runs silently in the Windows taskbar notification area.
    """
    def __init__(self):
        self.config = VistleConfig.load()
        self.audio_capture = AudioCapture(device_name_or_index=self.config.preferred_microphone)

        self.action_executor = ActionExecutor(
            on_action_started=self._on_action_started,
            on_action_finished=self._on_action_finished
        )

        self.engine = WakeWordEngine(
            audio_capture=self.audio_capture,
            config=self.config,
            on_wake_detected=self._on_wake_detected,
            on_status_change=self._on_status_change
        )

        self._icon: pystray.Icon = None
        self._ui_ready = False

    def _create_icon_image(self, active: bool = True) -> Image.Image:
        """Draws a clean, minimalist tray icon with an active emerald dot."""
        width = 64
        height = 64
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        badge_bg = (18, 19, 25, 255)
        border_color = (255, 255, 255, 255) if active else (55, 58, 72, 255)
        draw.ellipse([4, 4, 60, 60], fill=badge_bg, outline=border_color, width=3)

        # Crisp minimalist mic silhouette
        mic_color = (244, 245, 248, 255)
        draw.rounded_rectangle([26, 14, 38, 36], radius=6, fill=mic_color)
        draw.arc([20, 24, 44, 44], start=0, end=180, fill=mic_color, width=3)
        draw.line([32, 44, 32, 52], fill=mic_color, width=3)
        draw.line([24, 52, 40, 52], fill=mic_color, width=3)

        # Status indicator
        if active:
            draw.ellipse([44, 8, 56, 20], fill=(16, 185, 129, 255), outline=(14, 15, 22, 255), width=2)
        else:
            draw.ellipse([44, 8, 56, 20], fill=(239, 68, 68, 255), outline=(14, 15, 22, 255), width=2)

        return image

    def _on_wake_detected(self, phrase: PhraseConfig):
        self.engine.pause()
        if self._icon:
            self._icon.notify(
                title=f"Vistle — '{phrase.phrase}'",
                message=f"Triggering {phrase.name}..."
            )
        self.action_executor.execute(phrase)

    def _on_action_started(self, phrase: PhraseConfig):
        pass

    def _on_action_finished(self, phrase: PhraseConfig):
        print(f"[Vistle Tray] Target application closed. Instantly resuming wake listening.")
        self.engine.resume()

    def _on_status_change(self, status: str):
        if self._icon:
            is_active = (status == "Listening")
            self._icon.icon = self._create_icon_image(active=is_active)
            self._icon.title = f"Vistle — {status}"

    def _toggle_listening(self, icon, item):
        if self.engine.is_listening:
            self.engine.stop()
        else:
            if getattr(self.engine, '_is_paused', False):
                self.engine.resume()
            else:
                self.engine.start()

    def _reload(self, *_args):
        self.config = VistleConfig.load()
        self.engine.reload_phrases()

    def _open_enrollment(self, icon=None, item=None):
        from vistle.ui.host import reveal
        if not reveal("enroll"):
            print("[Vistle] Window is not ready yet.")

    def _open_settings(self, icon=None, item=None):
        from vistle.ui.host import reveal
        if not reveal("hub"):
            print("[Vistle] Window is not ready yet.")

    def _show_about(self, icon, item):
        msg = (
            f"Vistle v{__version__}\n\n"
            "Hands-free voice triggers for Windows.\n"
            "100% on-device. Zero audio storage.\n\n"
            "Trigger Wispr Flow or any desktop action with your voice."
        )
        if self._icon:
            self._icon.notify(title="About Vistle", message=msg)

    def _exit_app(self, icon, item):
        print("[Vistle] Exiting...")
        self.engine.stop()
        self.audio_capture.stop()
        self.action_executor.stop()
        try:
            from vistle.ui.host import shutdown
            shutdown()
        except Exception:
            pass
        icon.stop()

    def run(self):
        menu = pystray.Menu(
            item("Listening", self._toggle_listening, checked=lambda item: self.engine.is_listening),
            pystray.Menu.SEPARATOR,
            item("Add Trigger...", self._open_enrollment),
            item("Dashboard...", self._open_settings),
            pystray.Menu.SEPARATOR,
            item("About Vistle", self._show_about),
            item("Exit", self._exit_app)
        )

        self._icon = pystray.Icon(
            "Vistle",
            self._create_icon_image(active=self.config.start_listening_on_launch),
            "Vistle — Voice Trigger",
            menu=menu
        )

        self.enrollment = EnrollmentWindow(
            None,
            self.audio_capture,
            self.config,
            on_phrase_saved=self._reload,
            on_config_changed=self._reload,
        )
        self.settings = SettingsWindow(
            None,
            self.audio_capture,
            self.config,
            on_config_changed=self._reload,
            enrollment=self.enrollment,
        )

        if self.config.start_listening_on_launch:
            self.engine.start()

        start_view = "enroll" if len(self.config.phrases) == 0 else "hub"
        if start_view == "enroll":
            print("[Vistle] No phrases enrolled yet. Opening calibration...")

        threading.Thread(target=self._icon.run, daemon=True).start()
        print("[Vistle] Running in system tray.")

        from vistle.ui.host import launch
        launch(self.enrollment, self.settings, start_view="hub" if start_view == "hub" else "enroll")
