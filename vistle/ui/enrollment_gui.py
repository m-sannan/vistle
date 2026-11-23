import tkinter as tk
from tkinter import messagebox, filedialog
from typing import Optional, Callable
import math
import numpy as np
from vistle.audio import AudioCapture
from vistle.config import PhraseConfig, VistleConfig
from vistle.enrollment import EnrollmentSession
from vistle.template_store import TemplateStore
from vistle.dtw import dtw_distance
from vistle.ui.theme import (
    BG_CANVAS, SURFACE_CARD, SURFACE_INSET, BORDER_SUBTLE, BORDER_FOCUS,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_PRIMARY, ACCENT_WHITE, ACCENT_GREEN, ACCENT_RED,
    FONT_TITLE, FONT_SUBTITLE, FONT_HEADING, FONT_BODY, FONT_BOLD, FONT_SMALL, FONT_MONO,
    apply_windows_light_title_bar
)

class EnrollmentWindow:
    """
    Vistle Voice Calibration Hub.
    Designed to reflect Wispr Flow and Apple-minimalist aesthetic:
    - Pure matte dark surfaces (zero gradients, zero visual noise)
    - Radial dotted audio matrix (fingerprint-style calibration from Image 1)
    - Keyboard shortcut recorder
    - No visible scrollbars
    """
    def __init__(
        self,
        parent: Optional[tk.Tk],
        audio_capture: AudioCapture,
        config: VistleConfig,
        on_phrase_saved: Optional[Callable[[PhraseConfig], None]] = None
    ):
        self.audio_capture = audio_capture
        self.config = config
        self.on_phrase_saved = on_phrase_saved

        self.root = tk.Toplevel(parent) if parent else tk.Tk()
        self.root.title("Vistle — Voice Calibration")
        self.root.geometry("520x680")
        self.root.minsize(480, 600)
        self.root.configure(bg=BG_CANVAS)

        apply_windows_light_title_bar(self.root)

        self.session = EnrollmentSession(
            audio_capture=self.audio_capture,
            target_count=3,
            on_sample_recorded=self._on_sample_recorded,
            on_enrollment_complete=self._on_enrollment_complete
        )

        self._is_capturing_shortcut = False
        self._current_keys = set()
        self._pulse_anim_id = None
        self._pulse_phase = 0.0

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # 1. FIXED BOTTOM ACTION BAR
        footer = tk.Frame(self.root, bg=BG_CANVAS, padx=24, pady=16)
        footer.pack(side="bottom", fill="x")

        self.btn_save = tk.Button(
            footer,
            text="Save Trigger",
            font=FONT_BOLD,
            bg=SURFACE_INSET,
            fg=TEXT_MUTED,
            activebackground=ACCENT_PRIMARY,
            activeforeground=ACCENT_WHITE,
            relief="flat",
            state="disabled",
            cursor="arrow",
            command=self._save_phrase
        )
        self.btn_save.pack(side="right", padx=(10, 0), ipadx=24, ipady=8)

        btn_cancel = tk.Button(
            footer,
            text="Cancel",
            font=FONT_BODY,
            bg=BG_CANVAS,
            fg=TEXT_SECONDARY,
            activebackground=SURFACE_CARD,
            activeforeground=TEXT_PRIMARY,
            relief="flat",
            cursor="hand2",
            command=self._on_close
        )
        btn_cancel.pack(side="right", ipadx=14, ipady=8)

        # 2. MAIN BODY (Clean layout without visible scrollbars)
        body = tk.Frame(self.root, bg=BG_CANVAS, padx=24, pady=12)
        body.pack(side="top", fill="both", expand=True)

        # Header
        lbl_brand = tk.Label(body, text="VISTLE VOICE", font=FONT_SMALL, bg=BG_CANVAS, fg=TEXT_MUTED)
        lbl_brand.pack(anchor="w")

        lbl_title = tk.Label(body, text="Voice Calibration", font=FONT_TITLE, bg=BG_CANVAS, fg=TEXT_PRIMARY)
        lbl_title.pack(anchor="w", pady=(2, 0))

        # --- CENTERPIECE: RADIAL DOTTED VOICE MATRIX (Inspo Image 1) ---
        matrix_card = tk.Frame(body, bg=SURFACE_CARD, padx=16, pady=16, highlightthickness=1, highlightbackground=BORDER_SUBTLE)
        matrix_card.pack(fill="x", pady=(14, 12))

        self.dot_canvas = tk.Canvas(matrix_card, width=170, height=170, bg=SURFACE_CARD, highlightthickness=0)
        self.dot_canvas.pack(pady=(0, 4))

        self.lbl_percentage = tk.Label(matrix_card, text="0%", font=("Segoe UI Variable Display", 22, "bold"), bg=SURFACE_CARD, fg=TEXT_PRIMARY)
        self.lbl_percentage.pack()

        self.lbl_matrix_sub = tk.Label(matrix_card, text="0 of 3 samples calibrated", font=FONT_SMALL, bg=SURFACE_CARD, fg=TEXT_SECONDARY)
        self.lbl_matrix_sub.pack(pady=(1, 10))

        self._draw_dotted_matrix(sample_count=0)

        # Record Pill Button
        self.btn_record = tk.Button(
            matrix_card,
            text="Record Sample 1",
            font=FONT_HEADING,
            bg=ACCENT_PRIMARY,
            fg=ACCENT_WHITE,
            activebackground=TEXT_SECONDARY,
            activeforeground=ACCENT_WHITE,
            relief="flat",
            cursor="hand2",
            command=self._toggle_record
        )
        self.btn_record.pack(fill="x", ipady=8)

        # --- CARD 2: TRIGGER CONFIGURATION ---
        config_card = tk.Frame(body, bg=SURFACE_CARD, padx=16, pady=14, highlightthickness=1, highlightbackground=BORDER_SUBTLE)
        config_card.pack(fill="x")

        # Row 1: Label & Spoken Words
        row1 = tk.Frame(config_card, bg=SURFACE_CARD)
        row1.pack(fill="x", pady=(0, 8))

        f_left = tk.Frame(row1, bg=SURFACE_CARD)
        f_left.pack(side="left", fill="x", expand=True, padx=(0, 6))
        lbl_n = tk.Label(f_left, text="Label", font=FONT_SMALL, bg=SURFACE_CARD, fg=TEXT_SECONDARY)
        lbl_n.pack(anchor="w")
        self.ent_name = tk.Entry(f_left, font=FONT_BODY, bg=SURFACE_INSET, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat", highlightthickness=1, highlightbackground=BORDER_SUBTLE)
        self.ent_name.pack(fill="x", pady=(3, 0), ipady=4)
        self.ent_name.insert(0, "Open Wispr Flow")

        f_right = tk.Frame(row1, bg=SURFACE_CARD)
        f_right.pack(side="right", fill="x", expand=True, padx=(6, 0))
        lbl_s = tk.Label(f_right, text="Spoken Trigger", font=FONT_SMALL, bg=SURFACE_CARD, fg=TEXT_SECONDARY)
        lbl_s.pack(anchor="w")
        self.ent_spoken = tk.Entry(f_right, font=FONT_BODY, bg=SURFACE_INSET, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat", highlightthickness=1, highlightbackground=BORDER_SUBTLE)
        self.ent_spoken.pack(fill="x", pady=(3, 0), ipady=4)
        self.ent_spoken.insert(0, "Hey Wispr")

        # Row 2: Shortcut Keycaps Preview
        lbl_hk = tk.Label(config_card, text="Dispatched Shortcut", font=FONT_SMALL, bg=SURFACE_CARD, fg=TEXT_SECONDARY)
        lbl_hk.pack(anchor="w", pady=(4, 0))

        hk_row = tk.Frame(config_card, bg=SURFACE_CARD)
        hk_row.pack(fill="x", pady=(3, 0))

        self.ent_hotkey = tk.Entry(hk_row, font=FONT_MONO, bg=SURFACE_INSET, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat", highlightthickness=1, highlightbackground=BORDER_SUBTLE)
        self.ent_hotkey.pack(side="left", fill="x", expand=True, ipady=4)
        self.ent_hotkey.insert(0, "ctrl+windows+space")

        self.btn_capture_hk = tk.Button(
            hk_row,
            text="Change Shortcut...",
            font=FONT_BOLD,
            bg="#2a2c38",
            fg=TEXT_PRIMARY,
            activebackground=ACCENT_WHITE,
            activeforeground="#000000",
            relief="flat",
            cursor="hand2",
            command=self._start_shortcut_capture
        )
        self.btn_capture_hk.pack(side="right", padx=(8, 0), ipadx=8, ipady=4)

        self.root.bind("<KeyPress>", self._on_key_press)
        self.root.bind("<KeyRelease>", self._on_key_release)

    # --- RADIAL DOTTED VOICE MATRIX RENDERER (Image 1 Inspo) ---
    def _draw_dotted_matrix(self, sample_count: int, active_pulsing: bool = False):
        self.dot_canvas.delete("all")
        cx, cy = 85, 85

        # 3 concentric rings of dots matching Image 1
        ring_defs = [
            (28, 16, 2.5),  # Inner ring
            (42, 22, 2.0),  # Middle ring
            (56, 30, 1.5),  # Outer ring
        ]

        total_dots = sum(r[1] for r in ring_defs)
        lit_ratio = min(1.0, sample_count / 3.0)
        lit_dots_target = int(total_dots * lit_ratio)

        dot_counter = 0
        for ring_idx, (radius, count, dot_r) in enumerate(ring_defs):
            for i in range(count):
                angle = (2 * math.pi * i) / count - (math.pi / 2)
                x = cx + radius * math.cos(angle)
                y = cy + radius * math.sin(angle)

                is_lit = dot_counter < lit_dots_target
                dot_counter += 1

                if is_lit:
                    fill_col = ACCENT_GREEN if sample_count >= 3 else ACCENT_PRIMARY
                    cur_r = dot_r + 0.7
                elif active_pulsing:
                    # Subtle ambient wave while recording
                    pulse = math.sin(self._pulse_phase + (i * 0.3))
                    fill_col = ACCENT_RED if pulse > 0.2 else "#dcd6cb"
                    cur_r = dot_r + (1.0 if pulse > 0.2 else 0)
                else:
                    fill_col = "#e4dfd5"
                    cur_r = dot_r

                self.dot_canvas.create_oval(
                    x - cur_r, y - cur_r, x + cur_r, y + cur_r,
                    fill=fill_col, outline=""
                )

    def _start_pulse_anim(self):
        self._pulse_phase = 0.0
        self._animate_pulse()

    def _animate_pulse(self):
        if not self.session.is_recording:
            return
        self._pulse_phase += 0.3
        self._draw_dotted_matrix(self.session.recorded_count, active_pulsing=True)
        self._pulse_anim_id = self.root.after(45, self._animate_pulse)

    def _stop_pulse_anim(self):
        if self._pulse_anim_id:
            self.root.after_cancel(self._pulse_anim_id)
            self._pulse_anim_id = None
        self._draw_dotted_matrix(self.session.recorded_count, active_pulsing=False)

    # --- SHORTCUT CAPTURE ---
    def _start_shortcut_capture(self):
        self._is_capturing_shortcut = True
        self._current_keys.clear()
        self.btn_capture_hk.config(text="Press Keys Now...", bg=ACCENT_RED, fg="#ffffff")
        self.ent_hotkey.delete(0, tk.END)
        self.ent_hotkey.insert(0, "Waiting for keys...")
        self.root.focus_set()

    def _on_key_press(self, event):
        if not self._is_capturing_shortcut:
            return

        keysym = event.keysym.lower()
        key_name = self._normalize_key(keysym)
        if key_name:
            self._current_keys.add(key_name)
            chord = self._format_chord(self._current_keys)
            self.ent_hotkey.delete(0, tk.END)
            self.ent_hotkey.insert(0, chord)

    def _on_key_release(self, event):
        if not self._is_capturing_shortcut:
            return

        if self._current_keys:
            chord = self._format_chord(self._current_keys)
            self.ent_hotkey.delete(0, tk.END)
            self.ent_hotkey.insert(0, chord)

            self._is_capturing_shortcut = False
            self.btn_capture_hk.config(text="Change Shortcut...", bg=SURFACE_INSET, fg=TEXT_PRIMARY)

    def _normalize_key(self, keysym: str) -> Optional[str]:
        if keysym in ("control_l", "control_r"): return "ctrl"
        if keysym in ("shift_l", "shift_r"): return "shift"
        if keysym in ("alt_l", "alt_r"): return "alt"
        if keysym in ("win_l", "win_r", "super_l", "super_r"): return "windows"
        if keysym == "space": return "space"
        if keysym in ("return", "enter"): return "enter"
        if keysym == "escape": return "esc"
        if keysym.startswith("f") and keysym[1:].isdigit(): return keysym
        if len(keysym) == 1 and keysym.isalnum(): return keysym
        return None

    def _format_chord(self, keys: set) -> str:
        order = ["ctrl", "alt", "shift", "windows"]
        mods = [m for m in order if m in keys]
        others = [k for k in sorted(keys) if k not in order]
        return "+".join(mods + others)

    # --- VOICE RECORDING SEQUENCE ---
    def _toggle_record(self):
        if not self.session.is_recording:
            self.session.start_sample_recording()
            sample_num = self.session.recorded_count + 1
            self.btn_record.config(text=f"Stop Sample {sample_num}", bg=ACCENT_RED, fg="#ffffff")
            self.lbl_matrix_sub.config(text=f"Listening... Say '{self.ent_spoken.get()}' clearly", fg=ACCENT_WHITE)
            self._start_pulse_anim()
        else:
            self._stop_pulse_anim()
            success = self.session.stop_sample_recording()
            count = self.session.recorded_count
            pct = int((count / 3.0) * 100)
            self.lbl_percentage.config(text=f"{pct}%")
            self._draw_dotted_matrix(count, active_pulsing=False)

            if success:
                self.lbl_matrix_sub.config(text=f"{count} of 3 samples calibrated", fg=TEXT_SECONDARY)
                if count < 3:
                    self.btn_record.config(text=f"Record Sample {count + 1}", bg=ACCENT_PRIMARY, fg=ACCENT_WHITE)
            else:
                self.lbl_matrix_sub.config(text="Sample was too short or quiet. Please retry.", fg=ACCENT_AMBER)
                self.btn_record.config(text=f"Record Sample {count + 1}", bg=ACCENT_PRIMARY, fg=ACCENT_WHITE)

    def _on_sample_recorded(self, count: int, total: int):
        pass

    def _on_enrollment_complete(self):
        self.btn_record.config(state="disabled", text="✓ Calibration Complete", bg=SURFACE_INSET, fg=TEXT_MUTED)
        self.lbl_percentage.config(text="100%", fg=ACCENT_GREEN)
        self.lbl_matrix_sub.config(text="Model ready. Click Save Trigger.", fg=ACCENT_GREEN)

        templates = self.session.get_templates()
        if len(templates) >= 2:
            dists = []
            for i in range(len(templates)):
                for j in range(i + 1, len(templates)):
                    dists.append(dtw_distance(templates[i], templates[j]))
            valid_dists = [d for d in dists if np.isfinite(d)]
            max_d = max(valid_dists) if valid_dists else 1.8
            # In 39-D space, intra-sample distances for natural speech are typically 1.2 - 2.0.
            # We set the threshold comfortably at max_d * 1.35, bounded between 2.50 and 3.00 (sweet spot 2.85).
            # This allows casual fast speech without pacing, while still cleanly rejecting false triggers (> 3.5).
            calibrated = round(max(2.5, min(3.0, max_d * 1.35)), 2)
        else:
            calibrated = 2.85

        self._calibrated_threshold = calibrated

        # Enable high-contrast Save button
        self.btn_save.config(
            state="normal",
            bg=ACCENT_PRIMARY,
            fg=ACCENT_WHITE,
            cursor="hand2"
        )

    def _save_phrase(self):
        name = self.ent_name.get().strip()
        spoken = self.ent_spoken.get().strip()
        if not name or not spoken:
            messagebox.showwarning("Incomplete", "Please provide a label and spoken trigger.", parent=self.root)
            return

        threshold = getattr(self, "_calibrated_threshold", 3.8)

        phrase = PhraseConfig(
            name=name,
            phrase=spoken,
            action_type="hotkey",
            hotkey_spec=self.ent_hotkey.get().strip(),
            app_path=None,
            window_title="Wispr",
            process_name="Wispr",
            threshold=threshold,
            enabled=True,
            enrollment_count=3
        )

        templates = self.session.get_templates()
        TemplateStore.save(phrase.id, templates)

        # Deduplicate: replace existing phrase with same name or trigger to prevent ghost duplicates
        existing_idx = None
        for i, p in enumerate(self.config.phrases):
            if p.name.strip().lower() == phrase.name.strip().lower() or p.phrase.strip().lower() == phrase.phrase.strip().lower():
                existing_idx = i
                break

        if existing_idx is not None:
            old_p = self.config.phrases[existing_idx]
            TemplateStore.delete(old_p.id)
            self.config.phrases[existing_idx] = phrase
        else:
            self.config.phrases.append(phrase)

        self.config.save()

        if self.on_phrase_saved:
            self.on_phrase_saved(phrase)

        messagebox.showinfo("Saved", f"Trigger '{phrase.name}' is active!", parent=self.root)
        self._on_close()

    def _on_close(self):
        self._stop_pulse_anim()
        self.session.reset()
        self.root.destroy()
