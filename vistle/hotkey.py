import ctypes
from ctypes import wintypes
import time
import threading
from typing import List, Callable, Optional

user32 = ctypes.windll.user32
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = wintypes.SHORT
user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
user32.SendInput.restype = wintypes.UINT

PUL = ctypes.POINTER(ctypes.c_ulong)

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_short),
        ("wParamH", ctypes.c_ushort),
    ]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
        ("hi", HARDWAREINPUT),
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("union", INPUT_UNION),
    ]

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001

VK_MAP = {
    "ctrl": 0x11, "control": 0x11,
    "shift": 0x10,
    "alt": 0x12, "menu": 0x12,
    "win": 0x5B, "windows": 0x5B, "super": 0x5B, "meta": 0x5B,
    "space": 0x20,
    "enter": 0x0D, "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B, "escape": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E, "del": 0x2E,
    "insert": 0x2D,
    "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "capslock": 0x14,
}

for i in range(1, 25):
    VK_MAP[f"f{i}"] = 0x70 + (i - 1)

for c in "abcdefghijklmnopqrstuvwxyz":
    VK_MAP[c] = ord(c.upper())
for d in "0123456789":
    VK_MAP[d] = ord(d)

class HotkeySender:
    """Sends keystrokes via native Win32 SendInput API."""

    @staticmethod
    def _send_input(inputs: List[INPUT]):
        n = len(inputs)
        arr = (INPUT * n)(*inputs)
        ctypes.windll.user32.SendInput(n, ctypes.byref(arr), ctypes.sizeof(INPUT))

    @staticmethod
    def _create_key_input(vk: int, is_up: bool) -> INPUT:
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki.wVk = vk
        inp.union.ki.wScan = 0
        inp.union.ki.dwFlags = KEYEVENTF_KEYUP if is_up else 0
        inp.union.ki.time = 0
        inp.union.ki.dwExtraInfo = ctypes.POINTER(ctypes.c_ulong)()
        return inp

    @classmethod
    def send(cls, hotkey_spec: str):
        """Sends a hotkey combo like 'ctrl+shift+space' or 'alt+f4'."""
        if not hotkey_spec:
            return

        parts = [p.strip().lower() for p in hotkey_spec.split("+") if p.strip()]
        if not parts:
            return

        vk_codes = []
        for part in parts:
            vk = VK_MAP.get(part)
            if vk is None:
                print(f"[Vistle Hotkey] Warning: Unknown key '{part}' in '{hotkey_spec}'")
                return
            vk_codes.append(vk)

        print(f"[Vistle Hotkey] Sending: {hotkey_spec} (VKs: {[hex(v) for v in vk_codes]})")

        down_inputs = [cls._create_key_input(vk, is_up=False) for vk in vk_codes]
        cls._send_input(down_inputs)

        time.sleep(0.04)

        up_inputs = [cls._create_key_input(vk, is_up=True) for vk in reversed(vk_codes)]
        cls._send_input(up_inputs)


class StopKeyWatcher:
    """
    Watches for the user to press the stop hotkey (or Escape) to submit dictation.
    Triggers an instant resume without waiting for window detection.
    """
    def __init__(self, hotkey_spec: str, on_stop_pressed: Callable[[], None]):
        self.hotkey_spec = hotkey_spec
        self.on_stop_pressed = on_stop_pressed
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        parts = [p.strip().lower() for p in hotkey_spec.split("+") if p.strip()]
        self.target_vks = [VK_MAP[p] for p in parts if p in VK_MAP]
        self.dismiss_vks = [0x1B, 0x0D]  # Escape, Enter

    def _watch_loop(self):
        # Grace delay to ignore the keys that Vistle itself just simulated
        time.sleep(0.5)

        while not self._stop_event.is_set():
            # 1. Check toggle chord
            if self.target_vks:
                all_down = all(
                    bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
                    for vk in self.target_vks
                )
                if all_down:
                    print(f"[Vistle StopKeyWatcher] Toggle hotkey detected! Instantly resuming wake listening.")
                    if self.on_stop_pressed:
                        self.on_stop_pressed()
                    break

            # 2. Check dismiss keys (Escape / Enter)
            for d_vk in self.dismiss_vks:
                if bool(ctypes.windll.user32.GetAsyncKeyState(d_vk) & 0x8000):
                    print(f"[Vistle StopKeyWatcher] Dismissal key (Esc/Enter) detected! Instantly resuming wake listening.")
                    if self.on_stop_pressed:
                        self.on_stop_pressed()
                    return

            time.sleep(0.03) # 30ms check

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            if threading.current_thread() != self._thread:
                self._thread.join(timeout=0.1)
