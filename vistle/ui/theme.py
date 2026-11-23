import ctypes

# ==============================================================================
# Vistle — Wispr Flow Classic Warm Light Design System Tokens
# Clean, tactile alabaster/cream surfaces, warm sand borders, deep espresso text,
# and high-contrast charcoal pills. Matching the iconic original Wispr Flow look.
# ==============================================================================

# Background & Canvas Surfaces
BG_CANVAS = "#f7f5f0"          # Warm Alabaster / Cream paper canvas
BG_SIDEBAR = "#ede9e1"         # Oatmeal left navigation rail
SURFACE_BENTO = "#faf8f5"      # Intermediate warm container
SURFACE_CARD = "#ffffff"       # Crisp porcelain elevated bento card
SURFACE_CARD_HOVER = "#f3eee5" # Subtle warm sand hover highlight
SURFACE_INSET = "#ede8df"      # Inset keycaps and text inputs
BORDER_SUBTLE = "#e4ded4"      # Crisp 1px soft sand boundary stroke
BORDER_HOVER = "#cfc8bb"       # Card hover stroke
BORDER_FOCUS = "#1f1e1b"       # Active charcoal focus stroke

# Typography Colors
TEXT_PRIMARY = "#1f1e1b"       # Deep espresso / charcoal (high contrast, non-harsh)
TEXT_SECONDARY = "#757168"     # Warm taupe / slate secondary text
TEXT_MUTED = "#a09b91"         # Soft stone hint / inactive text

# Interactive & Status Accents
ACCENT_PRIMARY = "#1f1e1b"     # Signature Wispr Flow deep charcoal action pill
ACCENT_WHITE = "#ffffff"       # Pure white text / highlights
ACCENT_GREEN = "#2d7a58"       # Calming mineral forest / sage indicator
ACCENT_RED = "#dc4437"         # Warm recording terracotta / coral crimson
ACCENT_AMBER = "#d9822b"       # Warm amber / warning

# Typography Hierarchy
FONT_TITLE = ("Segoe UI Variable Display", 18, "bold")
FONT_SUBTITLE = ("Segoe UI Variable Text", 9)
FONT_HEADING = ("Segoe UI Variable Display", 12, "bold")
FONT_BODY = ("Segoe UI Variable Text", 10)
FONT_BOLD = ("Segoe UI Variable Text", 10, "bold")
FONT_SMALL = ("Segoe UI Variable Text", 8)
FONT_MONO = ("Cascadia Code", 9, "bold")

def apply_windows_light_title_bar(window):
    """Applies Windows 11 / Windows 10 native clean light title bar to match canvas."""
    try:
        window.update()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = window.winfo_id()
        dark = ctypes.c_int(0)  # 0 = Light mode title bar
        # Attribute 20 (Windows 11 / Windows 10 20H1+), fallback to 19
        hr = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark)
        )
        if hr != 0:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 19, ctypes.byref(dark), ctypes.sizeof(dark)
            )
    except Exception:
        pass

def apply_windows_dark_title_bar(window):
    """Fallback for dark mode windows."""
    try:
        window.update()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = window.winfo_id()
        dark = ctypes.c_int(1)
        hr = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark)
        )
        if hr != 0:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 19, ctypes.byref(dark), ctypes.sizeof(dark)
            )
    except Exception:
        pass
