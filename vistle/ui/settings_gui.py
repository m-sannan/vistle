import tkinter as tk
from tkinter import messagebox
from typing import Optional, Callable
from vistle.audio import AudioCapture
from vistle.config import VistleConfig, PhraseConfig
from vistle.template_store import TemplateStore
from vistle.ui.enrollment_gui import EnrollmentWindow
from vistle.ui.theme import (
    BG_CANVAS, BG_SIDEBAR, SURFACE_CARD, SURFACE_INSET, BORDER_SUBTLE, BORDER_HOVER,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_PRIMARY, ACCENT_WHITE, ACCENT_GREEN, ACCENT_RED,
    FONT_TITLE, FONT_HEADING, FONT_BODY, FONT_BOLD, FONT_SMALL, FONT_MONO,
    apply_windows_light_title_bar
)

class EditPhraseDialog:
    """Minimalist modal to edit shortcut keys."""
    def __init__(self, parent: tk.Tk, phrase: PhraseConfig, on_saved: Callable[[PhraseConfig], None]):
        self.phrase = phrase
        self.on_saved = on_saved

        self.root = tk.Toplevel(parent)
        self.root.title(f"Edit Trigger — {phrase.name}")
        self.root.geometry("440x360")
        self.root.resizable(False, False)
        self.root.configure(bg=BG_CANVAS)

        apply_windows_light_title_bar(self.root)

        self._is_capturing = False
        self._current_keys = set()

        self._build_ui()
        self.root.lift()
        self.root.focus_force()

    def _build_ui(self):
        pad = tk.Frame(self.root, bg=BG_CANVAS, padx=24, pady=20)
        pad.pack(fill="both", expand=True)

        lbl_t = tk.Label(pad, text="Edit Trigger Action", font=FONT_TITLE, bg=BG_CANVAS, fg=TEXT_PRIMARY)
        lbl_t.pack(anchor="w", pady=(0, 14))

        card = tk.Frame(pad, bg=SURFACE_CARD, padx=16, pady=16, highlightthickness=1, highlightbackground=BORDER_SUBTLE)
        card.pack(fill="x", pady=(0, 16))

        lbl_n = tk.Label(card, text="Label", font=FONT_SMALL, bg=SURFACE_CARD, fg=TEXT_SECONDARY)
        lbl_n.pack(anchor="w")
        self.ent_name = tk.Entry(card, font=FONT_BODY, bg=SURFACE_INSET, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat", highlightthickness=1, highlightbackground=BORDER_SUBTLE)
        self.ent_name.pack(fill="x", pady=(3, 10), ipady=4)
        self.ent_name.insert(0, self.phrase.name)

        lbl_hk = tk.Label(card, text="Dispatched Shortcut", font=FONT_SMALL, bg=SURFACE_CARD, fg=TEXT_SECONDARY)
        lbl_hk.pack(anchor="w")

        hk_row = tk.Frame(card, bg=SURFACE_CARD)
        hk_row.pack(fill="x", pady=(3, 0))

        self.ent_hk = tk.Entry(hk_row, font=FONT_MONO, bg=SURFACE_INSET, fg=TEXT_PRIMARY, relief="flat", highlightthickness=1, highlightbackground=BORDER_SUBTLE)
        self.ent_hk.pack(side="left", fill="x", expand=True, ipady=4)
        self.ent_hk.insert(0, self.phrase.hotkey_spec or "")

        self.btn_capture = tk.Button(hk_row, text="Press Keys...", font=FONT_BOLD, bg=SURFACE_INSET, fg=TEXT_PRIMARY, activebackground=SURFACE_CARD, relief="flat", cursor="hand2", command=self._start_capture)
        self.btn_capture.pack(side="right", padx=(8, 0), ipadx=8, ipady=4)

        # Buttons
        btns = tk.Frame(pad, bg=BG_CANVAS)
        btns.pack(side="bottom", fill="x")

        btn_save = tk.Button(btns, text="Save Changes", font=FONT_BOLD, bg=ACCENT_PRIMARY, fg=ACCENT_WHITE, activebackground=TEXT_SECONDARY, activeforeground=ACCENT_WHITE, relief="flat", cursor="hand2", command=self._save)
        btn_save.pack(side="right", padx=(8, 0), ipadx=16, ipady=6)

        btn_canc = tk.Button(btns, text="Cancel", font=FONT_BODY, bg=BG_CANVAS, fg=TEXT_SECONDARY, relief="flat", cursor="hand2", command=self.root.destroy)
        btn_canc.pack(side="right", ipadx=10, ipady=6)

        self.root.bind("<KeyPress>", self._on_key_press)
        self.root.bind("<KeyRelease>", self._on_key_release)

    def _start_capture(self):
        self._is_capturing = True
        self._current_keys.clear()
        self.btn_capture.config(text="Press Keys Now...", bg=ACCENT_RED, fg="#ffffff")
        self.ent_hk.delete(0, tk.END)
        self.ent_hk.insert(0, "Waiting for keys...")
        self.root.focus_set()

    def _on_key_press(self, event):
        if not self._is_capturing:
            return
        keysym = event.keysym.lower()
        key_name = None
        if keysym in ("control_l", "control_r"): key_name = "ctrl"
        elif keysym in ("shift_l", "shift_r"): key_name = "shift"
        elif keysym in ("alt_l", "alt_r"): key_name = "alt"
        elif keysym in ("win_l", "win_r", "super_l", "super_r"): key_name = "windows"
        elif keysym == "space": key_name = "space"
        elif keysym in ("return", "enter"): key_name = "enter"
        elif keysym == "escape": key_name = "esc"
        elif keysym.startswith("f") and keysym[1:].isdigit(): key_name = keysym
        elif len(keysym) == 1 and keysym.isalnum(): key_name = keysym

        if key_name:
            self._current_keys.add(key_name)
            order = ["ctrl", "alt", "shift", "windows"]
            mods = [m for m in order if m in self._current_keys]
            others = [k for k in sorted(self._current_keys) if k not in order]
            chord = "+".join(mods + others)
            self.ent_hk.delete(0, tk.END)
            self.ent_hk.insert(0, chord)

    def _on_key_release(self, event):
        if not self._is_capturing:
            return
        if self._current_keys:
            order = ["ctrl", "alt", "shift", "windows"]
            mods = [m for m in order if m in self._current_keys]
            others = [k for k in sorted(self._current_keys) if k not in order]
            chord = "+".join(mods + others)
            self.ent_hk.delete(0, tk.END)
            self.ent_hk.insert(0, chord)

            self._is_capturing = False
            self.btn_capture.config(text="Press Keys...", bg="#2a2c38", fg=TEXT_PRIMARY)

    def _save(self):
        self.phrase.name = self.ent_name.get().strip() or self.phrase.name
        self.phrase.hotkey_spec = self.ent_hk.get().strip()
        self.on_saved(self.phrase)
        self.root.destroy()


class SettingsWindow:
    """
    Vistle Modern Dashboard.
    Matches Wispr Flow desktop app layout (Image 4) with left sidebar rail and clean cards.
    """
    def __init__(
        self,
        parent: Optional[tk.Tk],
        audio_capture: AudioCapture,
        config: VistleConfig,
        on_config_changed: Optional[Callable[[], None]] = None
    ):
        self.audio_capture = audio_capture
        self.config = config
        self.on_config_changed = on_config_changed

        self.root = tk.Toplevel(parent) if parent else tk.Tk()
        self.root.title("Vistle — Dashboard")
        self.root.geometry("780x560")
        self.root.minsize(700, 480)
        self.root.configure(bg=BG_CANVAS)

        apply_windows_light_title_bar(self.root)

        self._build_ui()

    def _build_ui(self):
        # 1. LEFT SIDEBAR RAIL (Wispr Flow style)
        sidebar = tk.Frame(self.root, bg=BG_SIDEBAR, width=56, highlightthickness=1, highlightbackground=BORDER_SUBTLE)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Brand mark
        lbl_logo = tk.Label(sidebar, text="V", font=("Segoe UI Variable Display", 14, "bold"), bg=BG_SIDEBAR, fg=TEXT_PRIMARY)
        lbl_logo.pack(pady=(16, 24))

        # Nav icons
        btn_nav_dash = tk.Label(sidebar, text="●", font=FONT_TITLE, bg=BG_SIDEBAR, fg=TEXT_PRIMARY, cursor="hand2")
        btn_nav_dash.pack(pady=8)

        # 2. MAIN WORKSPACE
        main_area = tk.Frame(self.root, bg=BG_CANVAS, padx=24, pady=20)
        main_area.pack(side="left", fill="both", expand=True)

        # Header
        top_row = tk.Frame(main_area, bg=BG_CANVAS)
        top_row.pack(fill="x", pady=(0, 16))

        lbl_hi = tk.Label(top_row, text="Vistle Hub", font=FONT_TITLE, bg=BG_CANVAS, fg=TEXT_PRIMARY)
        lbl_hi.pack(side="left")

        # Status badge pill
        status_frame = tk.Frame(top_row, bg=SURFACE_CARD, padx=10, pady=4, highlightthickness=1, highlightbackground=BORDER_SUBTLE)
        status_frame.pack(side="right")
        lbl_dot = tk.Label(status_frame, text="●", font=FONT_BOLD, bg=SURFACE_CARD, fg=ACCENT_GREEN)
        lbl_dot.pack(side="left", padx=(0, 4))
        lbl_stat = tk.Label(status_frame, text="Engine Listening", font=FONT_SMALL, bg=SURFACE_CARD, fg=TEXT_PRIMARY)
        lbl_stat.pack(side="left")

        # Two-column layout
        cols = tk.Frame(main_area, bg=BG_CANVAS)
        cols.pack(fill="both", expand=True)

        # Left Column: Active Triggers List
        left_col = tk.Frame(cols, bg=BG_CANVAS)
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 12))

        lbl_t_header = tk.Label(left_col, text="Active Voice Triggers", font=FONT_HEADING, bg=BG_CANVAS, fg=TEXT_PRIMARY)
        lbl_t_header.pack(anchor="w", pady=(0, 8))

        self.triggers_container = tk.Frame(left_col, bg=BG_CANVAS)
        self.triggers_container.pack(fill="both", expand=True)
        self._populate_triggers()

        # Add Trigger Pill Button
        btn_add = tk.Button(
            left_col,
            text="+ Add Voice Trigger",
            font=FONT_BOLD,
            bg=ACCENT_PRIMARY,
            fg=ACCENT_WHITE,
            activebackground=TEXT_SECONDARY,
            activeforeground=ACCENT_WHITE,
            relief="flat",
            cursor="hand2",
            command=self._open_enrollment
        )
        btn_add.pack(fill="x", pady=(12, 0), ipady=6)

        # Right Column: System Info Cards (like Wispr Flow stats in Image 4)
        right_col = tk.Frame(cols, bg=BG_CANVAS, width=220)
        right_col.pack(side="right", fill="y", padx=(12, 0))
        right_col.pack_propagate(False)

        # Stat Card 1
        card_stat1 = tk.Frame(right_col, bg=SURFACE_CARD, padx=14, pady=14, highlightthickness=1, highlightbackground=BORDER_SUBTLE)
        card_stat1.pack(fill="x", pady=(0, 10))

        tk.Label(card_stat1, text="Privacy Engine", font=FONT_SMALL, bg=SURFACE_CARD, fg=TEXT_MUTED).pack(anchor="w")
        tk.Label(card_stat1, text="100% Local", font=FONT_HEADING, bg=SURFACE_CARD, fg=TEXT_PRIMARY).pack(anchor="w", pady=(2, 0))
        tk.Label(card_stat1, text="Zero audio stored or sent", font=FONT_SMALL, bg=SURFACE_CARD, fg=TEXT_SECONDARY).pack(anchor="w")

        # Stat Card 2
        card_stat2 = tk.Frame(right_col, bg=SURFACE_CARD, padx=14, pady=14, highlightthickness=1, highlightbackground=BORDER_SUBTLE)
        card_stat2.pack(fill="x", pady=(0, 10))

        tk.Label(card_stat2, text="Matching Speed", font=FONT_SMALL, bg=SURFACE_CARD, fg=TEXT_MUTED).pack(anchor="w")
        tk.Label(card_stat2, text="< 40ms", font=FONT_HEADING, bg=SURFACE_CARD, fg=TEXT_PRIMARY).pack(anchor="w", pady=(2, 0))
        tk.Label(card_stat2, text="MFCC + Fast DTW", font=FONT_SMALL, bg=SURFACE_CARD, fg=TEXT_SECONDARY).pack(anchor="w")

    def _populate_triggers(self):
        for widget in self.triggers_container.winfo_children():
            widget.destroy()

        if not self.config.phrases:
            empty_card = tk.Frame(self.triggers_container, bg=SURFACE_CARD, padx=20, pady=30, highlightthickness=1, highlightbackground=BORDER_SUBTLE)
            empty_card.pack(fill="x")
            tk.Label(empty_card, text="No wake phrases enrolled yet.", font=FONT_BODY, bg=SURFACE_CARD, fg=TEXT_SECONDARY).pack()
            return

        for phrase in self.config.phrases:
            card = tk.Frame(self.triggers_container, bg=SURFACE_CARD, padx=16, pady=16, highlightthickness=1, highlightbackground=BORDER_SUBTLE)
            card.pack(fill="x", pady=(0, 10))

            top = tk.Frame(card, bg=SURFACE_CARD)
            top.pack(fill="x")

            lbl_name = tk.Label(top, text=phrase.name, font=FONT_HEADING, bg=SURFACE_CARD, fg=TEXT_PRIMARY)
            lbl_name.pack(side="left")

            status_txt = "● Active" if phrase.enabled else "○ Paused"
            status_col = ACCENT_GREEN if phrase.enabled else TEXT_MUTED
            lbl_st = tk.Label(top, text=status_txt, font=FONT_SMALL, bg=SURFACE_CARD, fg=status_col)
            lbl_st.pack(side="right")

            # Callout row: Wake Phrase + Keycaps
            mid = tk.Frame(card, bg=SURFACE_INSET, padx=12, pady=10, highlightthickness=1, highlightbackground=BORDER_SUBTLE)
            mid.pack(fill="x", pady=(10, 8))

            lbl_sp = tk.Label(mid, text=f"Wake phrase: \"{phrase.phrase}\"", font=FONT_BODY, bg=SURFACE_INSET, fg=TEXT_PRIMARY)
            lbl_sp.pack(side="left")

            # Keycaps container
            hk_wrap = tk.Frame(mid, bg=SURFACE_INSET)
            hk_wrap.pack(side="right")

            keys = (phrase.hotkey_spec or "").split("+")
            for i, k in enumerate(keys):
                if not k.strip(): continue
                k_label = k.strip().capitalize()
                if k.lower() == "windows": k_label = "⊞ Win"
                elif k.lower() == "ctrl": k_label = "Ctrl"
                
                k_frame = tk.Frame(hk_wrap, bg=SURFACE_CARD, padx=6, pady=2, highlightthickness=1, highlightbackground=BORDER_SUBTLE)
                k_frame.pack(side="left", padx=2)
                tk.Label(k_frame, text=k_label, font=FONT_MONO, bg=SURFACE_CARD, fg=TEXT_PRIMARY).pack()

                if i < len(keys) - 1:
                    tk.Label(hk_wrap, text="+", font=FONT_SMALL, bg=SURFACE_INSET, fg=TEXT_MUTED).pack(side="left", padx=1)

            # Actions row
            act_row = tk.Frame(card, bg=SURFACE_CARD)
            act_row.pack(fill="x", pady=(4, 0))

            btn_ed = tk.Button(
                act_row,
                text="Edit Shortcut",
                font=FONT_SMALL,
                bg=SURFACE_INSET,
                fg=TEXT_PRIMARY,
                activebackground=BORDER_HOVER,
                activeforeground=TEXT_PRIMARY,
                relief="flat",
                cursor="hand2",
                command=lambda p=phrase: self._edit_phrase(p)
            )
            btn_ed.pack(side="left", padx=(0, 6), ipadx=8, ipady=3)

            btn_del = tk.Button(
                act_row,
                text="Delete",
                font=FONT_SMALL,
                bg=SURFACE_INSET,
                fg=ACCENT_RED,
                activebackground=BORDER_HOVER,
                activeforeground=ACCENT_RED,
                relief="flat",
                cursor="hand2",
                command=lambda p=phrase: self._delete_phrase(p.id)
            )
            btn_del.pack(side="left", ipadx=8, ipady=3)

    def _edit_phrase(self, phrase: PhraseConfig):
        def handle_saved(updated: PhraseConfig):
            self.config = VistleConfig.load()
            for i, p in enumerate(self.config.phrases):
                if p.id == updated.id:
                    self.config.phrases[i] = updated
                    break
            self.config.save()
            self._populate_triggers()
            if self.on_config_changed:
                self.on_config_changed()

        EditPhraseDialog(self.root, phrase, on_saved=handle_saved)

    def _open_enrollment(self):
        def handle_saved(new_p: PhraseConfig):
            self.config = VistleConfig.load()
            self._populate_triggers()
            if self.on_config_changed:
                self.on_config_changed()

        EnrollmentWindow(self.root, self.audio_capture, self.config, on_phrase_saved=handle_saved)

    def _delete_phrase(self, phrase_id: str):
        if messagebox.askyesno("Confirm Delete", "Remove this trigger?", parent=self.root):
            self.config = VistleConfig.load()
            self.config.phrases = [p for p in self.config.phrases if p.id != phrase_id]
            self.config.save()
            TemplateStore.delete(phrase_id)
            self._populate_triggers()
            if self.on_config_changed:
                self.on_config_changed()
