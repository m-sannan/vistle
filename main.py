import sys
import os
import ctypes
from vistle.ui.tray import TrayApp

ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "Local\\Vistle_SingleInstance_Mutex_98234"

def acquire_single_instance_mutex():
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    last_error = ctypes.windll.kernel32.GetLastError()
    if last_error == ERROR_ALREADY_EXISTS:
        if mutex:
            ctypes.windll.kernel32.CloseHandle(mutex)
        return None
    return mutex

def main():
    # Enforce single instance
    mutex = acquire_single_instance_mutex()
    if mutex is None:
        ctypes.windll.user32.MessageBoxW(
            0,
            "Vistle is already running in your system tray.\nLook for the microphone icon in your Windows taskbar.",
            "Vistle Already Running",
            0x40 # MB_ICONINFORMATION
        )
        sys.exit(0)

    try:
        app = TrayApp()
        app.run()
    except Exception as e:
        print(f"[Vistle Fatal Error] {e}")
        ctypes.windll.user32.MessageBoxW(
            0,
            f"Vistle encountered an error:\n\n{e}",
            "Vistle Error",
            0x10 # MB_ICONERROR
        )

if __name__ == "__main__":
    main()
