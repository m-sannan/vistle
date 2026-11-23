import subprocess
import threading
import time
from typing import Callable, Optional
from vistle.config import PhraseConfig
from vistle.hotkey import HotkeySender, StopKeyWatcher
from vistle.window_monitor import WindowMonitor

class ActionExecutor:
    """
    Executes configured trigger actions and provides dual instant resumption:
    1. Precision WindowMonitor (detects floating pill dismiss, alpha=0, or off-screen move)
    2. StopKeyWatcher (detects user pressing the stop hotkey to submit dictation)
    Whichever detects first immediately resumes wake listening!
    """
    def __init__(
        self,
        on_action_started: Optional[Callable[[PhraseConfig], None]] = None,
        on_action_finished: Optional[Callable[[PhraseConfig], None]] = None
    ):
        self.on_action_started = on_action_started
        self.on_action_finished = on_action_finished
        self._current_monitor: Optional[WindowMonitor] = None
        self._current_key_watcher: Optional[StopKeyWatcher] = None
        self._action_in_flight = False
        self._session_id = 0
        self._lock = threading.Lock()

    def execute(self, phrase: PhraseConfig):
        """Executes the action associated with the phrase."""
        with self._lock:
            self._session_id += 1
            session_id = self._session_id
            if self._current_monitor:
                self._current_monitor.stop()
                self._current_monitor = None
            if self._current_key_watcher:
                self._current_key_watcher.stop()
                self._current_key_watcher = None
            self._action_in_flight = True

        if self.on_action_started:
            self.on_action_started(phrase)

        print(f"[Vistle Actions] Executing '{phrase.name}' action: {phrase.action_type}")

        try:
            if phrase.action_type == "hotkey":
                if phrase.hotkey_spec:
                    HotkeySender.send(phrase.hotkey_spec)
            elif phrase.action_type == "launch_app":
                if phrase.app_path:
                    subprocess.Popen([phrase.app_path], shell=True)
            else:
                print(f"[Vistle Actions] Unknown action type: {phrase.action_type}")
        except Exception as e:
            print(f"[Vistle Actions] Failed to execute action: {e}")

        # Combined completion handler
        def handle_completion():
            with self._lock:
                if not self._action_in_flight or self._session_id != session_id:
                    return
                self._action_in_flight = False
                mon = self._current_monitor
                kw = self._current_key_watcher
                self._current_monitor = None
                self._current_key_watcher = None

            if mon:
                try:
                    mon.stop()
                except Exception as e:
                    print(f"[Vistle Actions] Error stopping monitor: {e}")
            if kw:
                try:
                    kw.stop()
                except Exception as e:
                    print(f"[Vistle Actions] Error stopping key watcher: {e}")

            print(f"[Vistle Actions] Dictation session finished for '{phrase.name}'.")
            if self.on_action_finished:
                self.on_action_finished(phrase)

        # 1. Start Stop Key Watcher (if shortcut configured)
        if phrase.action_type == "hotkey" and phrase.hotkey_spec:
            key_watcher = StopKeyWatcher(phrase.hotkey_spec, on_stop_pressed=handle_completion)
            with self._lock:
                self._current_key_watcher = key_watcher
            key_watcher.start()

        # 2. Start Window Monitor
        if phrase.process_name or phrase.window_title:
            monitor = WindowMonitor(
                process_name=phrase.process_name,
                window_title=phrase.window_title,
                on_window_closed=handle_completion
            )
            with self._lock:
                self._current_monitor = monitor
            monitor.start()

            # 3. 180s Safety ceiling (prevents permanent lock if user walks away)
            def safety_timeout():
                time.sleep(180.0)
                with self._lock:
                    if self._session_id != session_id or not self._action_in_flight:
                        return
                print(f"[Vistle Actions] Safety ceiling (180s) reached for '{phrase.name}'.")
                handle_completion()
            threading.Thread(target=safety_timeout, daemon=True).start()
        else:
            def delay_finish():
                time.sleep(0.4)
                handle_completion()
            threading.Thread(target=delay_finish, daemon=True).start()

    def stop(self):
        with self._lock:
            self._action_in_flight = False
            if self._current_monitor:
                self._current_monitor.stop()
                self._current_monitor = None
            if self._current_key_watcher:
                self._current_key_watcher.stop()
                self._current_key_watcher = None
