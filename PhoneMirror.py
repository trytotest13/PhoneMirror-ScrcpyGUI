import os
import sys
import time
import signal
import shlex
import threading
import subprocess
import ctypes
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP_NAME = "PhoneMirror"
APP_VERSION = "5.0"
ROOT = os.path.dirname(os.path.abspath(__file__))
ADB = os.path.join(ROOT, "adb.exe")
SCRCPY = os.path.join(ROOT, "scrcpy.exe")

BG = "#071426"
CARD = "#0D2038"
CARD_2 = "#102947"
CARD_3 = "#132F50"
BORDER = "#24476D"
TEXT = "#F4F8FF"
MUTED = "#9DB1C8"
GREEN = "#25D366"
GREEN_DARK = "#159447"
BLUE = "#3A86FF"
CYAN = "#39C5FF"
ORANGE = "#FFB04A"
RED = "#FF4D5A"
PURPLE = "#9B7BFF"

def win_flags():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)

def rounded_rect(canvas, x1, y1, x2, y2, radius=18, fill=CARD, outline=BORDER, width=1):
    # Canvas rounded polygon with smooth arcs.
    pts = [
        x1+radius,y1, x2-radius,y1,
        x2,y1+radius, x2,y2-radius,
        x2-radius,y2, x1+radius,y2,
        x1,y2-radius, x1,y1+radius
    ]
    return canvas.create_polygon(
        pts, smooth=True, splinesteps=16,
        fill=fill, outline=outline, width=width
    )

class PhoneMirror(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1280x820")
        self.minsize(1040, 700)
        self.configure(bg=BG)

        self.scrcpy_proc = None
        self.owned_pids = set()
        self.adb_started_by_app = False
        self.devices = []
        self.selected_device = None
        self.quality = tk.StringVar(value="MEDIUM")
        self.source = tk.StringVar(value="Screen")
        self.show_touches = tk.BooleanVar(value=False)
        self.stay_awake = tk.BooleanVar(value=True)
        self.keep_screen_on = tk.BooleanVar(value=False)
        self.advanced_open = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Ready")
        self.ip = tk.StringVar(value="")
        self.recording = False
        self.record_path = tk.StringVar(value=os.path.join(ROOT, "Recordings"))
        self.record_next_launch = False   # set by the Record quick action
        self.rotation_state = 0           # tracks user_rotation so Rotate actually cycles
        self.device_var = tk.StringVar(value="")   # selected device, drives a picker when >1 found
        self.advanced_widgets = {}        # name -> widget, so _scrcpy_args can read live values
        self._monitor_job = None
        self._pending_fullscreen = False

        self._configure_styles()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.shutdown)
        self.after(300, self.scan_devices)

    # ---------- styling ----------
    def _configure_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TCombobox",
                        fieldbackground=CARD_2, background=CARD_2,
                        foreground=TEXT, arrowcolor=MUTED,
                        borderwidth=0, padding=7)
        style.map("TCombobox",
                  fieldbackground=[("readonly", CARD_2)],
                  foreground=[("readonly", TEXT)])
        style.configure("TCheckbutton",
                        background=CARD, foreground=TEXT,
                        font=("Segoe UI", 10), padding=4)
        style.map("TCheckbutton", background=[("active", CARD)])

    # ---------- primitive widgets ----------
    def label(self, parent, text, size=10, color=TEXT, weight="normal"):
        return tk.Label(parent, text=text, bg=parent.cget("bg"),
                        fg=color, font=("Segoe UI", size, weight))

    def card(self, parent, padx=18, pady=16, bg=CARD):
        f = tk.Frame(parent, bg=bg, highlightthickness=1,
                     highlightbackground=BORDER, padx=padx, pady=pady)
        return f

    def pill_button(self, parent, text, command, bg=CARD_2, fg=TEXT,
                    active=None, width=None, font=("Segoe UI Semibold", 10)):
        b = tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                      activebackground=active or bg, activeforeground=fg,
                      relief="flat", bd=0, cursor="hand2",
                      font=font, padx=14, pady=8)
        if width:
            b.configure(width=width)
        return b

    def _build_ui(self):
        # Top bar
        top = tk.Frame(self, bg=BG, height=82)
        top.pack(fill="x", padx=24, pady=(18, 8))
        top.pack_propagate(False)

        brand = tk.Frame(top, bg=BG)
        brand.pack(side="left", fill="y")
        tk.Label(brand, text="▣", bg=BG, fg=GREEN,
                 font=("Segoe UI", 26, "bold")).pack(side="left", padx=(0, 10))
        txt = tk.Frame(brand, bg=BG)
        txt.pack(side="left")
        tk.Label(txt, text="PHONE MIRROR", bg=BG, fg="#FFB37A",
                 font=("Segoe UI", 21, "bold")).pack(anchor="w")
        tk.Label(txt, text="Easy • Fast • Stable", bg=BG, fg=MUTED,
                 font=("Segoe UI", 10)).pack(anchor="w")

        tools = tk.Frame(top, bg=BG)
        tools.pack(side="right")
        self.pill_button(tools, "?", lambda: messagebox.showinfo(
            "PhoneMirror", "Simple Android screen mirroring using scrcpy."),
            bg=CARD_2, active=CARD_3, width=2).pack(side="left", padx=5)
        self.pill_button(tools, "⚙", self.show_settings,
                         bg=CARD_2, active=CARD_3, width=2).pack(side="left", padx=5)
        tk.Button(tools, text="—", bg=BG, fg=TEXT, bd=0,
                  font=("Segoe UI", 17), command=self.iconify).pack(side="left", padx=5)
        tk.Button(tools, text="□", bg=BG, fg=TEXT, bd=0,
                  font=("Segoe UI", 15), command=self._toggle_max).pack(side="left", padx=5)
        tk.Button(tools, text="×", bg=BG, fg=TEXT, bd=0,
                  font=("Segoe UI", 20), command=self.shutdown).pack(side="left", padx=5)

        # Main horizontal split
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=6)
        body.grid_columnconfigure(0, weight=3, minsize=350)
        body.grid_columnconfigure(1, weight=7, minsize=620)
        body.grid_rowconfigure(0, weight=1)

        self.left = tk.Frame(body, bg=BG)
        self.left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.right = tk.Frame(body, bg=BG)
        self.right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self._build_left()
        self._build_right()

        # Bottom status bar
        status = tk.Frame(self, bg="#081A2E", height=42,
                          highlightthickness=1, highlightbackground=BORDER)
        status.pack(fill="x", padx=0, pady=(8, 0))
        status.pack_propagate(False)
        self.status_dot = tk.Label(status, text="●", bg=status.cget("bg"),
                                   fg=GREEN, font=("Segoe UI", 11))
        self.status_dot.pack(side="left", padx=(24, 6))
        self.status_label = tk.Label(status, textvariable=self.status,
                                      bg=status.cget("bg"), fg=TEXT,
                                      font=("Segoe UI", 9))
        self.status_label.pack(side="left")
        self.footer = tk.Label(status, text="ADB: Checking…     Device: —     Resolution: —     FPS: —",
                               bg=status.cget("bg"), fg=MUTED,
                               font=("Segoe UI", 9))
        self.footer.pack(side="right", padx=24)

    def _build_left(self):
        self.section_title(self.left, "STEP 1: CONNECT", CYAN)

        dev = self.card(self.left)
        dev.pack(fill="x", pady=(8, 10))
        self.label(dev, "Your Device", 11, TEXT, "bold").pack(anchor="w")
        row = tk.Frame(dev, bg=CARD)
        row.pack(fill="x", pady=(12, 10))
        tk.Label(row, text="▯", bg=CARD, fg=GREEN,
                 font=("Segoe UI", 35, "bold")).pack(side="left", padx=(4, 14))
        dtext = tk.Frame(row, bg=CARD)
        dtext.pack(side="left", fill="x", expand=True)
        self.device_label = tk.Label(dtext, text="No device detected",
                                      bg=CARD, fg=TEXT, font=("Segoe UI", 13, "bold"))
        self.device_label.pack(anchor="w")
        self.device_status = tk.Label(dtext, text="Waiting for ADB",
                                      bg=CARD, fg=MUTED, font=("Segoe UI", 10))
        self.device_status.pack(anchor="w", pady=(3, 0))
        self.pill_button(row, "↻", self.scan_devices, bg=CARD_2,
                         active=CARD_3, width=2).pack(side="right")

        # Device picker — only shown/populated when more than one device is found,
        # so a second phone is never silently unreachable.
        self.device_picker = ttk.Combobox(dev, textvariable=self.device_var,
                                           state="readonly", font=("Segoe UI", 9))
        self.device_picker.bind("<<ComboboxSelected>>", self._on_device_picked)

        # Connection method
        cm = self.card(self.left, padx=12, pady=12)
        cm.pack(fill="x", pady=(0, 10))
        self.label(cm, "Connection Method", 10, TEXT, "bold").pack(anchor="w")
        methods = tk.Frame(cm, bg=CARD)
        methods.pack(fill="x", pady=(8, 8))
        self.usb_btn = self.pill_button(methods, "🔌  USB Cable\n    Recommended",
                                        self.scan_devices, bg="#163E60",
                                        active="#1E557F", font=("Segoe UI Semibold", 9))
        self.usb_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.wifi_btn = self.pill_button(methods, "⌁  Wi-Fi\n    Wireless",
                                         self.wifi_connect, bg=CARD_2,
                                         active=CARD_3, font=("Segoe UI Semibold", 9))
        self.wifi_btn.pack(side="left", fill="x", expand=True, padx=(5, 0))

        iprow = tk.Frame(cm, bg=CARD)
        iprow.pack(fill="x")
        tk.Label(iprow, text="Device IP (for Wi-Fi)", bg=CARD,
                 fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        ipline = tk.Frame(iprow, bg=CARD)
        ipline.pack(fill="x", pady=(4, 0))
        tk.Entry(ipline, textvariable=self.ip, bg=CARD_2, fg=TEXT,
                 insertbackground=TEXT, relief="flat",
                 font=("Segoe UI", 10)).pack(side="left", fill="x", expand=True, ipady=7)
        self.pill_button(ipline, "Connect", self.wifi_connect,
                         bg=BLUE, active="#2D6FDB").pack(side="left", padx=(7, 0))

        self.section_title(self.left, "QUICK ACTIONS", PURPLE)
        qa = self.card(self.left, padx=10, pady=10)
        qa.pack(fill="x", pady=(8, 10))
        actions = [
            ("📷", "Screenshot", self.screenshot, CYAN),
            ("⏺", "Record", self.record_screen, RED),
            ("⛶", "Fullscreen", self.fullscreen, BLUE),
            ("⟳", "Rotate", self.rotate, PURPLE),
            ("☀", "Stay Awake", self.toggle_stay_awake, ORANGE),
            ("▰", "Open Folder", self.open_recordings, CYAN),
        ]
        for i, (icon, name, cmd, color) in enumerate(actions):
            b = tk.Button(qa, text=f"{icon}\n{name}", command=cmd,
                          bg=CARD_2, fg=TEXT, activebackground=CARD_3,
                          activeforeground=TEXT, relief="flat", bd=0,
                          cursor="hand2", font=("Segoe UI", 9, "bold"),
                          padx=5, pady=10)
            b.grid(row=i//3, column=i%3, sticky="nsew", padx=4, pady=4)
            qa.grid_columnconfigure(i%3, weight=1)

        # Emergency kill switch
        em = tk.Frame(self.left, bg=CARD, highlightthickness=1,
                      highlightbackground="#8B2630", padx=10, pady=10)
        em.pack(fill="x", pady=(4, 0))
        tk.Label(em, text="EMERGENCY", bg=CARD, fg=RED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.pill_button(em, "✖  KILL SWITCH",
                         self.kill_switch, bg="#8F1F2A",
                         fg="white", active="#B52A36",
                         font=("Segoe UI Semibold", 12)).pack(fill="x", pady=(7, 2))
        tk.Label(em, text="Stop processes started by PhoneMirror",
                 bg=CARD, fg="#FFB4BB", font=("Segoe UI", 8)).pack()

    def section_title(self, parent, text, color):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="x", pady=(5, 0))
        tk.Label(f, text=text, bg=BG, fg=color,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")

    def _build_right(self):
        self.section_title(self.right, "STEP 2: OPTIONS", ORANGE)

        opt = self.card(self.right)
        opt.pack(fill="x", pady=(8, 10))

        # Quality
        qrow = tk.Frame(opt, bg=CARD)
        qrow.pack(fill="x")
        leftq = tk.Frame(qrow, bg=CARD)
        leftq.pack(side="left", fill="both", expand=True)
        self.label(leftq, "Quality Preset", 11, TEXT, "bold").pack(anchor="w")
        presets = tk.Frame(leftq, bg=CARD)
        presets.pack(fill="x", pady=(9, 0))
        for name, sub, spec in [
            ("LOW", "Performance", "720p • 30 FPS • 4 Mbps"),
            ("MEDIUM", "Balanced", "1080p • 60 FPS • 8 Mbps"),
            ("HIGH", "Quality", "1080p+ • 60 FPS • 12 Mbps"),
        ]:
            b = tk.Button(presets, text=f"{name}\n{sub}\n{spec}",
                          command=lambda n=name: self.set_quality(n),
                          bg=CARD_2, fg=TEXT, activebackground="#173C61",
                          activeforeground=TEXT, relief="flat", bd=0,
                          font=("Segoe UI", 9, "bold"), padx=10, pady=8,
                          cursor="hand2")
            b.pack(side="left", fill="x", expand=True, padx=4)
            setattr(self, f"preset_{name.lower()}", b)

        # Toggles
        tog = tk.Frame(qrow, bg=CARD)
        tog.pack(side="right", padx=(15, 0))
        self.label(tog, "Useful Toggles", 11, TEXT, "bold").pack(anchor="w")
        for text, var in [
            ("Show Touches", self.show_touches),
            ("Stay Awake", self.stay_awake),
            ("Keep Screen On", self.keep_screen_on),
        ]:
            ttk.Checkbutton(tog, text=text, variable=var,
                            style="TCheckbutton").pack(anchor="w", pady=2)

        # Source
        src = tk.Frame(opt, bg=CARD)
        src.pack(fill="x", pady=(18, 0))
        self.label(src, "Source", 11, TEXT, "bold").pack(anchor="w")
        sr = tk.Frame(src, bg=CARD)
        sr.pack(fill="x", pady=(7, 0))
        self.source_buttons = {}
        for value, text, color in [
            ("Screen", "▣  Screen", CYAN),
            ("Back Camera", "▣  Back Camera", CYAN),
            ("Front Camera", "▣  Front Camera", CYAN),
            ("Microphone", "♩  Microphone", ORANGE),
        ]:
            b = tk.Button(sr, text=text,
                          command=lambda v=value: self.select_source(v),
                          bg=CARD_3 if value == self.source.get() else CARD_2,
                          fg=TEXT, activebackground=CARD_3,
                          relief="flat", bd=0, padx=14, pady=7,
                          font=("Segoe UI", 9, "bold"), cursor="hand2")
            b.pack(side="left", padx=(0, 7))
            self.source_buttons[value] = b

        # Start
        self.section_title(self.right, "STEP 3: START", GREEN)
        startrow = tk.Frame(self.right, bg=BG)
        startrow.pack(fill="x", pady=(8, 10))
        self.start_btn = tk.Button(startrow, text="▶  START MIRRORING",
                                    command=self.start_mirroring,
                                    bg=GREEN, fg="#06130C",
                                    activebackground="#32E57A",
                                    activeforeground="#06130C",
                                    relief="flat", bd=0, cursor="hand2",
                                    font=("Segoe UI", 14, "bold"),
                                    padx=18, pady=14)
        self.start_btn.pack(side="left", fill="x", expand=True, padx=(0, 7))
        self.stop_btn = tk.Button(startrow, text="■  STOP MIRRORING",
                                   command=self.stop_mirroring,
                                   bg=CARD_2, fg=MUTED,
                                   activebackground=CARD_3,
                                   relief="flat", bd=0, cursor="hand2",
                                   font=("Segoe UI", 10, "bold"),
                                   padx=18, pady=14, state="disabled")
        self.stop_btn.pack(side="right", padx=(7, 0))

        stat = tk.Frame(self.right, bg=CARD_2, highlightthickness=1,
                        highlightbackground=BORDER, padx=16, pady=10)
        stat.pack(fill="x", pady=(0, 10))
        tk.Label(stat, text="●", bg=CARD_2, fg=GREEN,
                 font=("Segoe UI", 10)).pack(side="left")
        self.main_status = tk.Label(stat, text="STATUS:  Ready",
                                    bg=CARD_2, fg=TEXT,
                                    font=("Segoe UI", 10, "bold"))
        self.main_status.pack(side="left", padx=(5, 18))
        self.stat_details = tk.Label(stat, text="Click START MIRRORING to begin",
                                     bg=CARD_2, fg=MUTED, font=("Segoe UI", 9))
        self.stat_details.pack(side="left")

        # Advanced accordion
        advhead = tk.Frame(self.right, bg=CARD, highlightthickness=1,
                           highlightbackground=BORDER, padx=16, pady=10)
        advhead.pack(fill="x", pady=(2, 0))
        self.pill_button(advhead, "⌄  ADVANCED / EXPERT SETTINGS",
                         self.toggle_advanced, bg=CARD, active=CARD,
                         fg=CYAN, font=("Segoe UI Semibold", 11)).pack(side="left")
        self.adv = tk.Frame(self.right, bg=CARD, highlightthickness=1,
                            highlightbackground=BORDER, padx=16, pady=12)

    def toggle_advanced(self):
        if self.advanced_open.get():
            self.adv.pack_forget()
            self.advanced_open.set(False)
        else:
            self._fill_advanced()
            self.adv.pack(fill="both", expand=True, pady=(0, 0))
            self.advanced_open.set(True)

    def _fill_advanced(self):
        for w in self.adv.winfo_children():
            w.destroy()
        tabs = tk.Frame(self.adv, bg=CARD)
        tabs.pack(fill="x")

        self.advanced_pages = {}
        self.advanced_tab_buttons = {}
        tab_names = ["Video", "Audio", "Window", "Device", "Recording", "Performance", "Advanced"]

        for name in tab_names:
            page = tk.Frame(self.adv, bg=CARD)
            self.advanced_pages[name] = page

            btn = tk.Button(
                tabs, text=name,
                command=lambda n=name: self.show_advanced_tab(n),
                bg=BLUE if name == "Video" else CARD_2,
                fg=TEXT,
                activebackground="#286FD6",
                activeforeground=TEXT,
                relief="flat", bd=0,
                padx=13, pady=8,
                font=("Segoe UI", 9, "bold"),
                cursor="hand2"
            )
            btn.pack(side="left", padx=(0, 3))
            self.advanced_tab_buttons[name] = btn

        self._build_advanced_pages()
        self.show_advanced_tab("Video")

    def show_advanced_tab(self, name):
        for page in self.advanced_pages.values():
            page.pack_forget()

        for tab, btn in self.advanced_tab_buttons.items():
            btn.configure(bg=BLUE if tab == name else CARD_2)

        self.advanced_pages[name].pack(fill="x", pady=(12, 0))

    def _advanced_field(self, parent, row, col, label_text, values, default, key=None):
        cell = tk.Frame(parent, bg=CARD)
        cell.grid(row=row, column=col, sticky="ew", padx=5, pady=5)
        tk.Label(cell, text=label_text, bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8)).pack(anchor="w")
        cb = ttk.Combobox(cell, values=values, state="readonly",
                          font=("Segoe UI", 9))
        cb.set(default)
        cb.pack(fill="x", pady=(3, 0))
        # Register so _scrcpy_args() can actually read the chosen value —
        # previously these Comboboxes were built but never referenced again.
        if key:
            self.advanced_widgets[key] = cb
        return cb

    def _build_advanced_pages(self):
        # VIDEO
        p = self.advanced_pages["Video"]
        p.grid_columnconfigure((0, 1, 2), weight=1)
        self._advanced_field(p, 0, 0, "Video Codec",
                             ["H.264 (avc)", "H.265 (hevc)", "AV1"], "H.264 (avc)",
                             key="video_codec")
        self._advanced_field(p, 0, 1, "Resolution",
                             ["1280x720 (720p)", "1920x1080 (1080p)", "2560x1440 (1440p)"],
                             "1920x1080 (1080p)", key="resolution")
        self._advanced_field(p, 0, 2, "Max FPS",
                             ["30 FPS", "60 FPS", "90 FPS", "120 FPS"], "60 FPS",
                             key="max_fps")
        self._advanced_field(p, 1, 0, "Video Bitrate",
                             ["4 Mbps", "8 Mbps", "12 Mbps", "20 Mbps"], "8 Mbps",
                             key="video_bitrate")
        self._advanced_field(p, 1, 1, "Video Buffer",
                             ["8 MB", "16 MB", "32 MB", "64 MB"], "32 MB",
                             key="video_buffer")
        self._advanced_field(p, 1, 2, "Orientation",
                             ["Device Default", "Portrait", "Landscape"], "Device Default",
                             key="orientation")

        # AUDIO
        p = self.advanced_pages["Audio"]
        p.grid_columnconfigure((0, 1, 2), weight=1)
        self._advanced_field(p, 0, 0, "Audio Codec",
                             ["Opus", "AAC", "Raw"], "Opus", key="audio_codec")
        self._advanced_field(p, 0, 1, "Audio Bitrate",
                             ["64 Kbps", "128 Kbps", "192 Kbps", "256 Kbps"], "128 Kbps",
                             key="audio_bitrate")
        self._advanced_field(p, 0, 2, "Audio Source",
                             ["Output", "Microphone", "Playback"], "Output",
                             key="audio_source")
        enable_audio_var = tk.BooleanVar(value=True)
        self.advanced_widgets["enable_audio_var"] = enable_audio_var
        ttk.Checkbutton(p, text="Enable Audio", variable=enable_audio_var,
                        style="TCheckbutton").grid(
            row=1, column=0, sticky="w", padx=5, pady=8)

        # WINDOW
        p = self.advanced_pages["Window"]
        p.grid_columnconfigure((0, 1), weight=1)
        window_opts = [
            ("Always on top", "always_on_top_var"),
            ("Borderless window", "borderless_var"),
            ("Fullscreen on start", "fullscreen_start_var"),
            ("Disable screensaver", "disable_screensaver_var"),
        ]
        for i, (text, key) in enumerate(window_opts):
            var = tk.BooleanVar(value=False)
            self.advanced_widgets[key] = var
            ttk.Checkbutton(p, text=text, variable=var, style="TCheckbutton").grid(
                row=i//2, column=i%2, sticky="w", padx=8, pady=5)

        # DEVICE
        p = self.advanced_pages["Device"]
        p.grid_columnconfigure((0, 1, 2), weight=1)
        self._advanced_field(p, 0, 0, "Display ID",
                             ["0 (Default)", "1", "2", "3"], "0 (Default)",
                             key="display_id")
        self._advanced_field(p, 0, 1, "Orientation",
                             ["Device Default", "Portrait", "Landscape"], "Device Default",
                             key="device_orientation")
        self._advanced_field(p, 0, 2, "Control Mode",
                             ["Normal", "View Only"], "Normal", key="control_mode")
        ttk.Checkbutton(p, text="Stay awake", variable=self.stay_awake,
                        style="TCheckbutton").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Checkbutton(p, text="Show touches", variable=self.show_touches,
                        style="TCheckbutton").grid(row=1, column=1, sticky="w", padx=5, pady=5)

        # RECORDING
        p = self.advanced_pages["Recording"]
        p.grid_columnconfigure(1, weight=1)
        tk.Label(p, text="Save folder", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", padx=5, pady=6)
        folder = tk.Entry(p, textvariable=self.record_path, bg=CARD_2, fg=TEXT,
                          insertbackground=TEXT, relief="flat")
        folder.grid(row=0, column=1, sticky="ew", padx=5, pady=6)
        self.pill_button(p, "Browse", self.choose_record_folder,
                         bg=CARD_2, active=CARD_3).grid(row=0, column=2, padx=5, pady=6)
        self._advanced_field(p, 1, 0, "Format",
                             ["MP4", "MKV"], "MP4", key="record_format")
        self._advanced_field(p, 1, 1, "Recording Bitrate",
                             ["8 Mbps", "12 Mbps", "20 Mbps"], "12 Mbps",
                             key="recording_bitrate")

        # PERFORMANCE
        p = self.advanced_pages["Performance"]
        p.grid_columnconfigure((0, 1), weight=1)
        self._advanced_field(p, 0, 0, "Render Driver",
                             ["D3D11 (Windows)", "OpenGL", "Software"], "D3D11 (Windows)")
        self._advanced_field(p, 0, 1, "VSync",
                             ["Auto", "On", "Off"], "Auto")
        self._advanced_field(p, 1, 0, "Priority",
                             ["Normal", "High"], "Normal")
        ttk.Checkbutton(p, text="Show FPS counter", style="TCheckbutton").grid(
            row=1, column=1, sticky="w", padx=5, pady=8)

        # ADVANCED
        p = self.advanced_pages["Advanced"]
        p.grid_columnconfigure(1, weight=1)
        tk.Label(p, text="Custom scrcpy arguments", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", padx=5, pady=6)
        self.custom_args = tk.Entry(p, bg=CARD_2, fg=TEXT,
                                    insertbackground=TEXT, relief="flat")
        self.custom_args.grid(row=0, column=1, columnspan=2, sticky="ew", padx=5, pady=6)
        tk.Label(p, text="Use only scrcpy arguments you understand.",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8)).grid(
                     row=1, column=1, sticky="w", padx=5)
        self.pill_button(p, "Reset Custom Args",
                         lambda: self.custom_args.delete(0, "end"),
                         bg=CARD_2, active=CARD_3).grid(row=1, column=2, padx=5, pady=5)

    def choose_record_folder(self):
        folder = filedialog.askdirectory(initialdir=self.record_path.get())
        if folder:
            self.record_path.set(folder)

    # ---------- device / ADB ----------
    # scan_devices/wifi_connect used to shell out to adb with subprocess.run()
    # directly on the Tk main thread (up to ~16s combined for start-server +
    # devices). That froze the whole window on every refresh and on launch.
    # These now do the blocking work on a background thread and marshal the
    # UI update back via self.after(0, ...).
    def scan_devices(self):
        if not os.path.exists(ADB):
            self.set_status("ADB not found")
            self.device_label.config(text="ADB missing")
            self.device_status.config(text="Place adb.exe beside PhoneMirror.py")
            return
        self.set_status("Scanning for devices…")
        threading.Thread(target=self._scan_devices_worker, daemon=True).start()

    def _scan_devices_worker(self):
        try:
            subprocess.run([ADB,"start-server"],cwd=ROOT,capture_output=True,
                           text=True,timeout=8,creationflags=win_flags())
            self.adb_started_by_app=True
            r=subprocess.run([ADB,"devices"],cwd=ROOT,capture_output=True,
                             text=True,timeout=8,creationflags=win_flags())
            dev=[]
            for line in r.stdout.splitlines()[1:]:
                line=line.strip()
                if not line:
                    continue
                parts=line.split("\t")
                if len(parts)==2 and parts[1].strip()=="device":
                    dev.append(parts[0].strip())
            self.after(0, self._apply_scan_result, dev, None)
        except Exception as e:
            self.after(0, self._apply_scan_result, [], str(e))

    def _apply_scan_result(self, dev, error):
        if error:
            self.set_status(f"ADB error: {error}")
            return
        self.devices=dev
        if dev:
            # Keep the previously selected device if it's still present,
            # instead of silently jumping back to devices[0] on every scan.
            if self.selected_device not in dev:
                self.selected_device=dev[0]
            self.device_var.set(self.selected_device)
            self.device_label.config(text=self.selected_device)
            self.device_status.config(text="● Connected  •  USB / ADB",fg=GREEN)
            self.set_status("Ready")
            self.footer.config(text=f"ADB: Connected     Device: {self.selected_device}     Resolution: —     FPS: —")
        else:
            self.selected_device=None
            self.device_var.set("")
            self.device_label.config(text="No device detected")
            self.device_status.config(text="Enable USB debugging and reconnect",fg=MUTED)
            self.set_status("Waiting for device")
        self._refresh_device_picker()

    def _refresh_device_picker(self):
        # Only show the picker when there's an actual choice to make — with
        # 0 or 1 device it would just be clutter.
        if len(self.devices) > 1:
            self.device_picker.configure(values=self.devices)
            self.device_picker.pack(fill="x", pady=(6, 0))
        else:
            self.device_picker.pack_forget()

    def _on_device_picked(self, event=None):
        chosen=self.device_var.get()
        if chosen:
            self.selected_device=chosen
            self.device_label.config(text=chosen)
            self.footer.config(text=f"ADB: Connected     Device: {chosen}     Resolution: —     FPS: —")
            self.set_status(f"Selected {chosen}")

    def wifi_connect(self):
        ip=self.ip.get().strip()
        if not ip:
            messagebox.showwarning("Wi-Fi", "Enter the phone's IP address first.")
            return
        self.set_status(f"Connecting to {ip}…")
        threading.Thread(target=self._wifi_connect_worker, args=(ip,), daemon=True).start()

    def _wifi_connect_worker(self, ip):
        try:
            r=subprocess.run([ADB,"connect",ip],cwd=ROOT,capture_output=True,
                             text=True,timeout=10,creationflags=win_flags())
            out=r.stdout+r.stderr
            if "connected" in out.lower():
                self.after(0, self.scan_devices)
            else:
                self.after(0, lambda: messagebox.showerror("Wi-Fi connection failed", out))
                self.after(0, lambda: self.set_status("Wi-Fi connection failed"))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Wi-Fi connection failed", str(e)))
            self.after(0, lambda: self.set_status("Wi-Fi connection failed"))

    # ---------- source selection ----------
    def select_source(self, value):
        """Select the capture source and apply it to the running mirror.

        The old buttons only changed a StringVar, so there was no visible
        feedback and an already-running scrcpy process never received the
        new source.  Source selection is now a real action: highlight the
        selected button, update the status, and restart scrcpy when needed.
        """
        if value not in ("Screen", "Back Camera", "Front Camera", "Microphone"):
            return

        changed = self.source.get() != value
        self.source.set(value)

        for name, button in getattr(self, "source_buttons", {}).items():
            button.config(bg=CARD_3 if name == value else CARD_2)

        if not changed:
            self.set_status(f"{value} source selected")
            return

        self.set_status(f"{value} source selected")

        # A scrcpy process cannot change video-source/camera-facing after it
        # has started. Restart it automatically so the button actually takes
        # effect instead of requiring the user to stop/start manually.
        if self.scrcpy_proc is not None and self.scrcpy_proc.poll() is None:
            self.stop_mirroring()
            self.after(250, self.start_mirroring)

    # ---------- quality / controls ----------
    def set_quality(self,name):
        self.quality.set(name)
        for n in ("low","medium","high"):
            getattr(self,f"preset_{n}").config(bg=CARD_2)
        getattr(self,f"preset_{name.lower()}").config(bg="#164C36")
        self.set_status(f"{name.title()} quality preset selected")

    # Small parsing helpers for the Advanced tab's Comboboxes, which store
    # human-readable strings like "1920x1080 (1080p)" / "60 FPS" / "8 Mbps".
    @staticmethod
    def _num(text, suffix=""):
        try:
            return "".join(ch for ch in text.split()[0] if ch.isdigit())
        except Exception:
            return ""

    def _adv(self, name, default=""):
        w = self.advanced_widgets.get(name)
        if w is None:
            return default
        try:
            return w.get()
        except Exception:
            return default

    def _scrcpy_args(self):
        # Build arguments carefully by capture mode. Camera mode must not
        # inherit display-only encoding/FPS/orientation options because some
        # devices reject the mixed configuration and scrcpy exits immediately.
        args = [SCRCPY]
        if self.selected_device:
            args += ["-s", self.selected_device]

        camera_mode = self.source.get() in ("Back Camera", "Front Camera")
        mic_mode = self.source.get() == "Microphone"

        if camera_mode:
            facing = "back" if self.source.get() == "Back Camera" else "front"
            args += ["--video-source=camera", f"--camera-facing={facing}"]

            # Camera mode: let Android choose its supported default size/FPS.
            # Do NOT force --camera-fps=30; a few devices advertise different
            # camera profiles and reject an explicitly requested rate.
            # Camera mirroring automatically uses the microphone unless audio
            # is explicitly disabled.
            if self.advanced_widgets.get("enable_audio_var") and not self.advanced_widgets["enable_audio_var"].get():
                args += ["--no-audio"]
            else:
                args += ["--audio-source=mic"]

            # Only apply options that are safe and independent of display
            # capture. These are intentionally not copied from the normal
            # screen preset/advanced display settings.
            if self.advanced_widgets.get("fullscreen_start_var") and self.advanced_widgets["fullscreen_start_var"].get():
                args += ["--fullscreen"]
            if self.advanced_widgets.get("always_on_top_var") and self.advanced_widgets["always_on_top_var"].get():
                args += ["--always-on-top"]
            if self.advanced_widgets.get("borderless_var") and self.advanced_widgets["borderless_var"].get():
                args += ["--window-borderless"]
            if self.advanced_widgets.get("disable_screensaver_var") and self.advanced_widgets["disable_screensaver_var"].get():
                args += ["--disable-screensaver"]
        else:
            # Normal display/microphone modes keep the existing quality and
            # advanced settings behaviour.
            if getattr(self, "_pending_fullscreen", False):
                args += ["--fullscreen"]
                self._pending_fullscreen = False

            if self.advanced_open.get() and self.advanced_widgets:
                codec = self._adv("video_codec", "H.264 (avc)")
                if codec.startswith("H.265"):
                    args += ["--video-codec", "h265"]
                elif codec.startswith("AV1"):
                    args += ["--video-codec", "av1"]

                max_size = self._adv("resolution", "1920x1080 (1080p)").split("x")[0].strip() or "1920"
                if max_size.isdigit():
                    args += ["--max-size", max_size]

                fps = self._num(self._adv("max_fps", "60 FPS"))
                args += ["--max-fps", fps or "60"]

                bitrate = self._num(self._adv("video_bitrate", "8 Mbps"))
                args += ["--video-bit-rate", f"{bitrate or '8'}M"]

                buf = self._num(self._adv("video_buffer", "32 MB"))
                if buf:
                    args += ["--video-buffer", str(int(buf))]

                orient = self._adv("orientation", "Device Default")
                if orient == "Portrait":
                    args += ["--capture-orientation", "0"]
                elif orient == "Landscape":
                    args += ["--capture-orientation", "90"]

                if self.advanced_widgets.get("enable_audio_var") and self.advanced_widgets["enable_audio_var"].get():
                    acodec = self._adv("audio_codec", "Opus")
                    args += ["--audio-codec", acodec.lower()]
                    abitrate = self._num(self._adv("audio_bitrate", "128 Kbps"))
                    args += ["--audio-bit-rate", f"{abitrate or '128'}K"]
                else:
                    args += ["--no-audio"]

                if self.advanced_widgets.get("always_on_top_var") and self.advanced_widgets["always_on_top_var"].get():
                    args += ["--always-on-top"]
                if self.advanced_widgets.get("borderless_var") and self.advanced_widgets["borderless_var"].get():
                    args += ["--window-borderless"]
                if self.advanced_widgets.get("fullscreen_start_var") and self.advanced_widgets["fullscreen_start_var"].get():
                    args += ["--fullscreen"]
                if self.advanced_widgets.get("disable_screensaver_var") and self.advanced_widgets["disable_screensaver_var"].get():
                    args += ["--disable-screensaver"]

                display_id = self._num(self._adv("display_id", "0 (Default)"))
                if display_id and display_id != "0":
                    args += ["--display-id", display_id]

                if self._adv("control_mode", "Normal") == "View Only":
                    args += ["--no-control"]
            else:
                q = self.quality.get()
                if q == "LOW":
                    args += ["--video-bit-rate", "4M", "--max-size", "1280", "--max-fps", "30"]
                elif q == "HIGH":
                    args += ["--video-bit-rate", "12M", "--max-size", "1920", "--max-fps", "60"]
                else:
                    args += ["--video-bit-rate", "8M", "--max-size", "1920", "--max-fps", "60"]

            if mic_mode:
                if "--no-audio" in args:
                    args.remove("--no-audio")
                args += ["--audio-source", "mic"]

            if self.show_touches.get():
                args += ["--show-touches"]
            if self.stay_awake.get():
                args += ["--stay-awake"]
            if not self.keep_screen_on.get():
                pass

        if self.record_next_launch:
            fmt = self._adv("record_format", "MP4").lower()
            os.makedirs(self.record_path.get(), exist_ok=True)
            fname = time.strftime(f"record_%Y%m%d_%H%M%S.{fmt}")
            args += ["--record", os.path.join(self.record_path.get(), fname)]

        custom = self.custom_args.get().strip() if hasattr(self, "custom_args") else ""
        if custom:
            try:
                args += shlex.split(custom)
            except ValueError as e:
                messagebox.showwarning("Custom arguments", f"Couldn't parse custom scrcpy arguments ({e}). They were ignored for this launch.")
        return args

    def start_mirroring(self):
        if not self.selected_device:
            self.scan_devices()
        if not self.selected_device:
            messagebox.showwarning("No device", "Connect an Android device first.")
            return
        if self.scrcpy_proc and self.scrcpy_proc.poll() is None:
            return
        if not os.path.exists(SCRCPY):
            messagebox.showerror("scrcpy missing","Place scrcpy.exe beside PhoneMirror.py.")
            return
        try:
            os.makedirs(self.record_path.get(),exist_ok=True)
            log_path = os.path.join(ROOT, "scrcpy-error.log")
            log_file = open(log_path, "w", encoding="utf-8", errors="replace")
            p=subprocess.Popen(self._scrcpy_args(),cwd=ROOT,
                               stdout=log_file,stderr=log_file,
                               creationflags=win_flags())
            self._scrcpy_log_file = log_file
            self.scrcpy_proc=p
            self.owned_pids.add(p.pid)
            self.start_btn.config(state="disabled",bg="#155C3A")
            self.stop_btn.config(state="normal",bg="#6E2028",fg="#FFDDE0")
            label = "Recording" if self.record_next_launch else "Mirroring"
            self.main_status.config(text=f"STATUS:  {label}",fg=GREEN)
            self.stat_details.config(text=f"{self.quality.get().title()} preset • {self.source.get()}")
            self.set_status(f"{label} active")
            self._start_process_monitor()
        except Exception as e:
            messagebox.showerror("Could not start mirroring",str(e))
        finally:
            self.record_next_launch = False

    def stop_mirroring(self):
        self._stop_process_monitor()
        pid = self.scrcpy_proc.pid if self.scrcpy_proc else None
        self._kill_process_tree(pid)
        self.owned_pids.discard(pid)
        self.scrcpy_proc=None
        self.start_btn.config(state="normal",bg=GREEN)
        self.stop_btn.config(state="disabled",bg=CARD_2,fg=MUTED)
        self.main_status.config(text="STATUS:  Ready",fg=TEXT)
        self.stat_details.config(text="Click START MIRRORING to begin")
        self.set_status("Stopped")

    # ---------- process liveness monitoring ----------
    # Previously nothing polled the scrcpy process. Closing the mirror
    # window directly (the normal way people close a video window) left
    # Start disabled, Stop enabled, and the status stuck on "Mirroring
    # active" forever. This periodically checks whether the process is
    # still alive and resets the UI the moment it isn't.
    def _start_process_monitor(self):
        self._stop_process_monitor()
        self._monitor_job = self.after(1000, self._check_process_alive)

    def _stop_process_monitor(self):
        if self._monitor_job is not None:
            try:
                self.after_cancel(self._monitor_job)
            except Exception:
                pass
            self._monitor_job = None

    def _check_process_alive(self):
        if self.scrcpy_proc is not None and self.scrcpy_proc.poll() is not None:
            # Process exited on its own (window closed, device unplugged, crash).
            self.owned_pids.discard(self.scrcpy_proc.pid)
            self.scrcpy_proc=None
            self.start_btn.config(state="normal",bg=GREEN)
            self.stop_btn.config(state="disabled",bg=CARD_2,fg=MUTED)
            self.main_status.config(text="STATUS:  Ready",fg=TEXT)
            self.stat_details.config(text="Click START MIRRORING to begin")
            # If scrcpy exits immediately (common for unsupported camera
            # mode/device permissions), surface the real reason instead of
            # silently returning the UI to the initial state.
            error_text = ""
            try:
                if getattr(self, "_scrcpy_log_file", None):
                    self._scrcpy_log_file.flush()
                    self._scrcpy_log_file.close()
                    self._scrcpy_log_file = None
                log_path = os.path.join(ROOT, "scrcpy-error.log")
                if os.path.exists(log_path):
                    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                        error_text = f.read().strip()
            except Exception:
                pass
            if error_text:
                short = error_text[-1800:]
                self.set_status("scrcpy stopped — see error message")
                messagebox.showerror("scrcpy stopped", short)
            else:
                self.set_status("Mirroring ended")
            self._monitor_job = None
            return
        self._monitor_job = self.after(1000, self._check_process_alive)

    # ---------- quick actions ----------
    def screenshot(self):
        if not self.selected_device:
            self.scan_devices()
        if not self.selected_device: return
        folder=os.path.join(ROOT,"Screenshots"); os.makedirs(folder,exist_ok=True)
        path=os.path.join(folder,time.strftime("screenshot_%Y%m%d_%H%M%S.png"))
        self.set_status("Capturing screenshot…")
        threading.Thread(target=self._screenshot_worker, args=(path,), daemon=True).start()

    def _screenshot_worker(self, path):
        # Runs off the main thread (adb exec-out can take a moment) and
        # verifies the capture actually succeeded before reporting success —
        # previously a failed capture (locked screen, device unplugged) still
        # left behind a 0-byte/corrupt PNG with a "Screenshot saved" message.
        try:
            with open(path,"wb") as f:
                r=subprocess.run([ADB,"-s",self.selected_device,"exec-out","screencap","-p"],
                                 cwd=ROOT,stdout=f,stderr=subprocess.PIPE,timeout=10,
                                 creationflags=win_flags())
            ok = r.returncode == 0 and os.path.exists(path) and os.path.getsize(path) > 0
            if not ok:
                try: os.remove(path)
                except OSError: pass
                err = (r.stderr or b"").decode(errors="ignore").strip() or "empty capture"
                self.after(0, lambda: messagebox.showerror("Screenshot failed", err))
                self.after(0, lambda: self.set_status("Screenshot failed"))
            else:
                self.after(0, lambda: self.set_status("Screenshot saved"))
        except Exception as e:
            try: os.remove(path)
            except OSError: pass
            self.after(0, lambda: messagebox.showerror("Screenshot", str(e)))

    def record_screen(self):
        # Previously this just started plain mirroring and told the user to
        # "use the Recording tab" — the Recording tab's folder/format
        # settings were never actually connected to a --record flag, so no
        # video file was ever produced. This now flags the next launch as a
        # recording launch, which _scrcpy_args() picks up.
        self.record_next_launch = True
        if not self.scrcpy_proc or self.scrcpy_proc.poll() is not None:
            self.start_mirroring()
        else:
            messagebox.showinfo("Recording",
                                 "Stop the current mirror session first, then press Record "
                                 "again to start a new recording session.")
            self.record_next_launch = False

    def _scrcpy_window_hwnd(self):
        """Return the top-level window handle belonging to our scrcpy process."""
        if not self.scrcpy_proc or self.scrcpy_proc.poll() is not None:
            return None
        target_pid = self.scrcpy_proc.pid
        hwnd_result = [None]

        EnumWindows = ctypes.windll.user32.EnumWindows
        GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId
        IsWindowVisible = ctypes.windll.user32.IsWindowVisible

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def callback(hwnd, _lparam):
            if not IsWindowVisible(hwnd):
                return True
            pid = ctypes.c_ulong()
            GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == target_pid:
                hwnd_result[0] = hwnd
                return False
            return True

        EnumWindows(WNDENUMPROC(callback), 0)
        return hwnd_result[0]

    def _toggle_scrcpy_fullscreen(self):
        """Toggle fullscreen in the already-running scrcpy window (Ctrl+F)."""
        hwnd = self._scrcpy_window_hwnd()
        if not hwnd:
            return False

        user32 = ctypes.windll.user32
        VK_CONTROL = 0x11
        VK_F = 0x46
        KEYEVENTF_KEYUP = 0x0002

        user32.ShowWindow(hwnd, 5)  # SW_SHOW
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.05)
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_F, 0, 0, 0)
        user32.keybd_event(VK_F, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        return True

    def fullscreen(self):
        # Fullscreen belongs to the scrcpy video window, not PhoneMirror.
        # If mirroring is running, toggle it immediately with scrcpy's
        # standard Ctrl+F shortcut. If it is not running, remember the
        # setting for the next launch. Never open Advanced Settings here.
        if self._toggle_scrcpy_fullscreen():
            self.set_status("Fullscreen toggled")
            return

        var = self.advanced_widgets.get("fullscreen_start_var")
        if var is not None:
            var.set(not var.get())
            self.set_status("Fullscreen on start " +
                            ("enabled" if var.get() else "disabled"))
        else:
            self.set_status("Fullscreen will be enabled on next Start")
            self._pending_fullscreen = not getattr(self, "_pending_fullscreen", False)

    def rotate(self):
        if not self.selected_device: return
        self.set_status("Rotating…")
        threading.Thread(target=self._rotate_worker, daemon=True).start()

    def _rotate_worker(self):
        # Previously always sent user_rotation=1 and never disabled
        # auto-rotate first, so on most phones (auto-rotate on by default)
        # the sensor immediately overrode it and the button silently did
        # nothing. This disables auto-rotate once, then actually cycles
        # through the four rotation states on each press.
        try:
            subprocess.run([ADB,"-s",self.selected_device,"shell","settings","put",
                            "system","accelerometer_rotation","0"],cwd=ROOT,timeout=5,
                           creationflags=win_flags())
            self.rotation_state = (self.rotation_state + 1) % 4
            subprocess.run([ADB,"-s",self.selected_device,"shell","settings","put",
                            "system","user_rotation",str(self.rotation_state)],cwd=ROOT,timeout=5,
                           creationflags=win_flags())
            self.after(0, lambda: self.set_status(f"Rotated (state {self.rotation_state})"))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Rotate", str(e)))

    def toggle_stay_awake(self):
        self.stay_awake.set(not self.stay_awake.get())
        self.set_status("Stay Awake " + ("enabled" if self.stay_awake.get() else "disabled"))

    def open_recordings(self):
        os.makedirs(self.record_path.get(),exist_ok=True)
        try: os.startfile(self.record_path.get())
        except Exception: pass

    # ---------- kill switch ----------
    def _pid_is_scrcpy(self, pid):
        # owned_pids is only ever added-to on launch and cleared on
        # kill_switch/shutdown — a PID that already exited naturally (see
        # _check_process_alive) could in theory be recycled by Windows for
        # an unrelated process before kill_switch runs. Verify the PID still
        # belongs to scrcpy.exe before sending taskkill at it.
        try:
            r = subprocess.run(
                ["tasklist","/FI",f"PID eq {pid}","/FO","CSV","/NH"],
                capture_output=True, text=True, timeout=5, creationflags=win_flags())
            return "scrcpy.exe" in r.stdout.lower()
        except Exception:
            # If we can't verify, err on the side of not killing an
            # unrelated process.
            return False

    def _kill_process_tree(self,pid, trusted=False):
        if not pid:
            return False
        # A live Popen handle is authoritative: it is the process this
        # PhoneMirror instance launched. For stored PIDs without a live
        # handle, keep the scrcpy.exe safety check.
        if not trusted and not self._pid_is_scrcpy(pid):
            return False
        try:
            result = subprocess.run(
                ["taskkill","/PID",str(pid),"/T","/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=win_flags(), timeout=8)
            return result.returncode == 0
        except Exception:
            return False

    def kill_switch(self):
        # Stop the monitor first so it cannot race with cleanup.
        self._stop_process_monitor()

        killed = False

        # Prefer the live Popen process. This fixes the case where the
        # scrcpy process is still running but the stored PID verification
        # is temporarily unavailable.
        if self.scrcpy_proc is not None:
            pid = self.scrcpy_proc.pid
            if self.scrcpy_proc.poll() is None:
                killed = self._kill_process_tree(pid, trusted=True) or killed
            self.owned_pids.discard(pid)

        # Clean up any other scrcpy PIDs this instance launched.
        for pid in list(self.owned_pids):
            killed = self._kill_process_tree(pid) or killed

        self.owned_pids.clear()
        self.scrcpy_proc=None
        self.start_btn.config(state="normal",bg=GREEN)
        self.stop_btn.config(state="disabled",bg=CARD_2,fg=MUTED)
        self.main_status.config(text="STATUS:  Ready",fg=TEXT)
        self.stat_details.config(text="Kill switch stopped PhoneMirror processes")
        self.set_status("Kill switch: stopped app processes")

    # ---------- helpers ----------
    def set_status(self,text):
        self.status.set(text)
        try: self.main_status.config(text=f"STATUS:  {text}")
        except Exception: pass

    def _toggle_max(self):
        self.state("normal" if self.state()=="zoomed" else "zoomed")

    def show_settings(self):
        if not self.advanced_open.get(): self.toggle_advanced()
        self.set_status("Advanced settings opened")

    def shutdown(self):
        self.kill_switch()
        self.destroy()

if __name__=="__main__":
    app=PhoneMirror()
    app.mainloop()
