import ctypes
from ctypes import wintypes
import threading
import time
from typing import Callable, Optional

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
DWMWA_CLOAKED = 14
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
dwmapi = ctypes.windll.dwmapi

user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wintypes.LONG

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL


class WindowMonitor:
    """
    High-precision overlay/window detector for Wispr Flow and desktop assistants.
    Reliably tracks on-screen overlay visibility across all DPI scales and multi-monitors.
    """
    def __init__(
        self,
        process_name: Optional[str] = None,
        window_title: Optional[str] = None,
        check_interval: float = 0.05,       # Snappy 50ms polling
        startup_grace_period: float = 3.5,  # Wait up to 3.5s for target window to render
        max_active_timeout: float = 300.0, # 5-minute safety ceiling
        on_window_closed: Optional[Callable[[], None]] = None
    ):
        self.process_name = process_name.lower().strip() if process_name else None
        self.window_title = window_title.lower().strip() if window_title else None
        self.check_interval = check_interval
        self.startup_grace_period = startup_grace_period
        self.max_active_timeout = max_active_timeout
        self.on_window_closed = on_window_closed

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._is_monitoring = False

    def _is_popup_window_visible(self) -> bool:
        found = False

        def enum_windows_callback(hwnd, extra):
            nonlocal found
            # 1. User32 visibility check
            if not user32.IsWindowVisible(hwnd):
                return True

            # 2. Must not be minimized
            if user32.IsIconic(hwnd):
                return True

            # 3. Check DWM Cloaked (cloaked modern windows are hidden)
            cloaked = ctypes.c_int(0)
            try:
                hr = dwmapi.DwmGetWindowAttribute(
                    hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
                )
                if hr == 0 and cloaked.value != 0:
                    return True
            except Exception:
                pass

            # 4. Physical On-Screen Dimensions
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            width = rect.right - rect.left
            height = rect.bottom - rect.top

            # Must have non-zero physical size (ignore zero-sized helper hooks)
            if width < 30 or height < 15:
                return True

            # Ignore off-screen parked windows (-32000 coordinates used by Electron)
            if rect.left <= -25000 or rect.top <= -25000:
                return True

            # 5. Check Process Name
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            exe_name = ""
            if pid.value:
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
                if h_proc:
                    try:
                        name_buff = ctypes.create_unicode_buffer(260)
                        size = wintypes.DWORD(260)
                        if kernel32.QueryFullProcessImageNameW(h_proc, 0, name_buff, ctypes.byref(size)):
                            exe_name = name_buff.value.lower()
                    finally:
                        kernel32.CloseHandle(h_proc)

            # 6. Check Window Title
            title = ""
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.lower()

            # Target matching:
            # Matches if process matches Wispr/Flow or the configured phrase process/title
            matches_process = False
            if self.process_name and self.process_name in exe_name:
                matches_process = True
            elif "wispr" in exe_name or "flow" in exe_name:
                matches_process = True

            matches_title = False
            if self.window_title and self.window_title in title:
                matches_title = True
            elif "wispr" in title or "flow" in title:
                matches_title = True

            if matches_process or matches_title:
                found = True
                return False  # Target overlay found and active!

            return True

        cb = WNDENUMPROC(enum_windows_callback)
        user32.EnumWindows(cb, 0)
        return found

    def _monitor_loop(self):
        start_time = time.time()
        saw_popup = False

        # Phase 1: Wait for target window to appear on-screen
        while not self._stop_event.is_set():
            if self._is_popup_window_visible():
                saw_popup = True
                print("[Vistle WindowMonitor] Wispr Flow active. Vistle is safely paused while you dictate.")
                break
            if time.time() - start_time > self.startup_grace_period:
                print("[Vistle WindowMonitor] Startup grace window reached. Ensuring wake service resumes cleanly.")
                break
            time.sleep(self.check_interval)

        # Phase 2: Stay paused while user dictates
        if saw_popup:
            popup_start = time.time()
            while not self._stop_event.is_set():
                if not self._is_popup_window_visible():
                    print("[Vistle WindowMonitor] Wispr Flow dismissed! Instantly resuming wake listening.")
                    break
                if time.time() - popup_start > self.max_active_timeout:
                    print("[Vistle WindowMonitor] Maximum 5-minute timeout reached. Resuming.")
                    break
                time.sleep(self.check_interval)

            self._is_monitoring = False
            if not self._stop_event.is_set() and self.on_window_closed:
                self.on_window_closed()
        else:
            # Safe Fallback: if window hook was missed or target app is transient,
            # wait a brief dictation buffer (1.5s) then safely resume so the user is NEVER locked out!
            time.sleep(1.5)
            self._is_monitoring = False
            if not self._stop_event.is_set() and self.on_window_closed:
                self.on_window_closed()

    def start(self):
        self._stop_event.clear()
        self._is_monitoring = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._is_monitoring = False
        if self._thread and self._thread.is_alive():
            if threading.current_thread() != self._thread:
                self._thread.join(timeout=0.2)

    @property
    def is_monitoring(self) -> bool:
        return self._is_monitoring
