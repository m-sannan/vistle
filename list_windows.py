import ctypes
from ctypes import wintypes

def check():
    results = []
    def cb(hwnd, _):
        if not ctypes.windll.user32.IsWindowVisible(hwnd):
            return True
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value

        rect = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top

        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pname = ""
        if pid.value:
            h_proc = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)
            if h_proc:
                nb = ctypes.create_unicode_buffer(260)
                sz = ctypes.c_ulong(260)
                if ctypes.windll.kernel32.QueryFullProcessImageNameW(h_proc, 0, nb, ctypes.byref(sz)):
                    pname = nb.value
                ctypes.windll.kernel32.CloseHandle(h_proc)

        # Check cloaked state (DwmGetWindowAttribute)
        cloaked = ctypes.c_int(0)
        DWMWA_CLOAKED = 14
        try:
            ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        except Exception:
            pass

        if "wispr" in title.lower() or "wispr" in pname.lower():
            results.append((hwnd, title, pname, w, h, cloaked.value))
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    ctypes.windll.user32.EnumWindows(WNDENUMPROC(cb), 0)
    for r in results:
        print(f"HWND: {r[0]} | Title: '{r[1]}' | Exe: {r[2]} | Size: {r[3]}x{r[4]} | Cloaked: {r[5]}")

if __name__ == "__main__":
    check()
