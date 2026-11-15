import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import platform
import queue
import subprocess
import threading
from pathlib import Path

from video_transcoder.settings.settings_manager import SettingsManager
from video_transcoder.core.transcoder_engine import (
    TranscoderEngine,
    VIDEO_CODECS,
    AUDIO_CODECS,
    CONTAINERS,
    SHARPENING_LABELS,
)
from video_transcoder.core.transcoder_service import TranscoderService
from video_transcoder.ffmpeg.tool import FFmpegTool
from video_transcoder.system.shortcut_creator import ShortcutCreator
from video_transcoder import __version__
import time

class VideoTranscoderApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"MediaTools Video Transcoder v{__version__}")
        self.quality_options = {} # Initialized dynamically in _update_quality_options
        
        # Compatibility Maps (Internal keys)
        self.VIDEO_CODEC_CONTAINERS = {
            "h264": ["mp4", "mkv", "avi", "mov"],
            "h265": ["mp4", "mkv", "mov"],
            "av1":   ["mkv", "webm"],
            "vp9":   ["mkv", "webm"],
            "default": ["mp4", "mkv", "avi", "mov"] # Default maps to h264
        }

        self.CONTAINER_AUDIO = {
            "mp4":  ["aac", "mp3", "ac3"],
            "mkv":  ["aac", "mp3", "ac3", "opus", "flac", "vorbis"],
            "webm": ["opus", "vorbis"],
            "mov":  ["aac", "mp3", "ac3"],
            "avi":  ["mp3", "ac3"],
            "default": ["aac", "mp3", "ac3"] # Default maps to mp4
        }

        self.CRF_QUALITY_MATCHED = {
            'low': {
                'h264': 27,
                'h265': 29,
                'vp9': 37,
                'av1': 39,
            },
            'standard': {
                'h264': 23,
                'h265': 25,
                'vp9': 32,
                'av1': 34,
            },
            'high': {
                'h264': 19,
                'h265': 21,
                'vp9': 27,
                'av1': 29,
            },
            'visually_lossless': {
                'h264': 15,
                'h265': 17,
                'vp9': 23,
                'av1': 24,
            }
        }

        self.settings = SettingsManager()
        self.ffmpeg_tool = FFmpegTool(self.settings)
        self.shortcut_creator = ShortcutCreator(self.settings)

        self.engine = TranscoderEngine(
            self.ffmpeg_tool.get_ffmpeg_command(),
            self.ffmpeg_tool.get_ffprobe_command()
        )
        self.service = TranscoderService(self.engine, self.settings)
        self._ui_queue = queue.Queue()
        self._closing = False

        self._setup_icon()

        # Intercept window close
        self.root.protocol("WM_DELETE_WINDOW", self.exit_app)

        self.settings_widgets = []
        self._setup_ui()
        self._load_defaults()

        # Load Multi-Session Queue if enabled (must be after _setup_ui)
        if self.settings.get("multi_session_enabled", True):
            self._load_queue_from_file()

        # Check for shortcut on first run
        self.root.after(1000, self.shortcut_creator.first_run_setup)

        # Check FFmpeg and Updates on start
        self.root.after(50, self._drain_ui_queue)
        self.root.after(500, self._check_on_start)

    def _post_ui(self, callback):
        """Queue a callable for execution on the Tk main thread."""
        if self._closing:
            return
        self._ui_queue.put(callback)

    def _drain_ui_queue(self):
        """Execute queued UI callbacks on the Tk main thread only."""
        if self._closing:
            return

        try:
            while True:
                try:
                    callback = self._ui_queue.get_nowait()
                except queue.Empty:
                    break

                try:
                    callback()
                except Exception as e:
                    print(f"UI callback error: {e}")
        finally:
            if not self._closing:
                try:
                    self.root.after(50, self._drain_ui_queue)
                except tk.TclError:
                    pass

    def _check_on_start(self):
        """Check FFmpeg availability and updates without blocking the UI."""
        self.status_var.set("Checking for FFmpeg updates...")
        threading.Thread(target=self._check_on_start_worker, daemon=True).start()

    def _check_on_start_worker(self):
        try:
            if not self.ffmpeg_tool.is_ffmpeg_available():
                self._post_ui(self._on_ffmpeg_missing)
                return

            self._post_ui(self._set_ffmpeg_available)

            if not self.settings.get("auto_update", True):
                self._post_ui(lambda: self.status_var.set("Ready"))
                return

            last_check = self.settings.get("last_ffmpeg_update_check", 0)
            current_time = time.time()
            days_passed = (current_time - last_check) / (24 * 3600)

            if days_passed < 28:
                self._post_ui(lambda: self.status_var.set("Ready"))
                return

            print(f"[Auto-Update] 28-day interval reached for FFmpeg (Days since last check: {days_passed:.1f}). Checking versions...")
            local_ver = self.ffmpeg_tool.get_local_version()
            remote_ver = self.ffmpeg_tool.get_remote_version()

            if self.ffmpeg_tool.is_up_to_date(local_ver, remote_ver):
                print("[Auto-Update] FFmpeg already on the latest version. No download needed.")
                self.settings.set("last_ffmpeg_update_check", current_time)
                self._post_ui(lambda: self.status_var.set("Ready"))
                return

            print(f"[Auto-Update] New FFmpeg version detected! Local: {local_ver}, Remote: {remote_ver}")
            self._post_ui(lambda: self._prompt_ffmpeg_update(local_ver, remote_ver, current_time))
        except Exception as e:
            print(f"[Auto-Update] FFmpeg check failed: {e}")
            self._post_ui(lambda: self.status_var.set("Ready"))

    def _set_ffmpeg_available(self):
        self.ffmpeg_status_lbl.config(text="FFmpeg: OK", foreground="green")

    def _on_ffmpeg_missing(self):
        self.ffmpeg_status_lbl.config(text="FFmpeg: MISSING", foreground="red")
        self.prompt_ffmpeg_download()

    def _prompt_ffmpeg_update(self, local_ver, remote_ver, current_time):
        prompt_msg = "It's been 28 days since your last FFmpeg update check.\n\n"
        if local_ver and remote_ver:
            prompt_msg += f"Current FFmpeg version: {local_ver}\nLatest available: {remote_ver}\n\n"
        prompt_msg += "Would you like to check for and install FFmpeg updates now?"

        if messagebox.askyesno("Check for FFmpeg Updates", prompt_msg):
            print("[Auto-Update] User accepted FFmpeg update. Starting download...")
            self.settings.set("last_ffmpeg_update_check", current_time)
            self._begin_ffmpeg_download()
        else:
            print("[Auto-Update] User declined FFmpeg update.")
            self.settings.set("last_ffmpeg_update_check", current_time)
            self.status_var.set("Ready")

    def _setup_icon(self):
        """Setup application icon for the title bar"""
        try:
            # Use unified resource resolution from settings
            assets_dir = self.settings._get_bundle_resource("assets")
            
            if not assets_dir or not assets_dir.exists():
                return

            if platform.system() == "Windows":
                icon_path = assets_dir / "Logo_128x128.ico"
                if icon_path.exists():
                    self.root.iconbitmap(str(icon_path))
            else:
                icon_path = assets_dir / "Logo_128x128.png"
                if icon_path.exists():
                    img = tk.PhotoImage(file=str(icon_path))
                    self.root.iconphoto(True, img)
        except Exception as e:
            print(f"Could not load application icon: {e}")

    def _setup_ui(self):
        main_container = ttk.Frame(self.root, padding="15")
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # --- Top Header ---
        header_frame = ttk.Frame(main_container)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_frame, text=f"Video Transcoder v{__version__}", font=("Helvetica", 16, "bold")).pack(side=tk.LEFT)
        
        # Auto Update Toggle in Header
        self.auto_update_var = tk.BooleanVar(value=self.settings.get("auto_update", True))
        self.auto_update_cb = ttk.Checkbutton(header_frame, text="Auto Update FFmpeg", variable=self.auto_update_var, command=self._on_auto_update_toggle)
        self.auto_update_cb.pack(side=tk.RIGHT, padx=10)

        # Multi Session Support Toggle
        self.multi_session_var = tk.BooleanVar(value=self.settings.get("multi_session_enabled", True))
        self.multi_session_cb = ttk.Checkbutton(header_frame, text="Multi Session Support", variable=self.multi_session_var, command=self._on_multi_session_toggle)
        self.multi_session_cb.pack(side=tk.RIGHT, padx=10)

        self.ffmpeg_status_lbl = ttk.Label(header_frame, text="FFmpeg: Checking...", foreground="gray")
        self.ffmpeg_status_lbl.pack(side=tk.RIGHT)

        # --- Input List ---
        input_frame = ttk.LabelFrame(main_container, text=" Files to Process ", padding="10")
        input_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        btn_bar = ttk.Frame(input_frame)
        btn_bar.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Button(btn_bar, text="+ Add Files", command=self.add_files).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(btn_bar, text="+ Add Folder", command=self.add_folder).pack(side=tk.LEFT, padx=2)
        
        self.recursive_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(btn_bar, text="Recursive", variable=self.recursive_var).pack(side=tk.LEFT, padx=10)
        
        ttk.Button(btn_bar, text="Downloads Folder", command=self.open_downloads).pack(side=tk.RIGHT, padx=(2, 0))
        ttk.Button(btn_bar, text="Clear List", command=self.clear_list).pack(side=tk.RIGHT, padx=2)

        list_container = ttk.Frame(input_frame)
        list_container.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(list_container, columns=("path", "status"), show="headings", height=8)
        self.tree.heading("path", text="File Path", anchor=tk.W)
        self.tree.heading("status", text="Status", anchor=tk.W)
        self.tree.column("path", width=550, anchor=tk.W)
        self.tree.column("status", width=120, anchor=tk.W)
        
        sb = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Context menu for queue
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Move to Top", command=self.move_to_top)
        self.context_menu.add_command(label="Move Up", command=self.move_up)
        self.context_menu.add_command(label="Move Down", command=self.move_down)
        self.context_menu.add_command(label="Move to Bottom", command=self.move_to_bottom)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Remove from Queue", command=self.remove_selected)
        self.context_menu.add_command(label="Enqueue Again", command=self.enqueue_again)

        self.tree.bind("<Button-3>", self.show_context_menu) # Windows/Linux
        self.tree.bind("<Button-2>", self.show_context_menu) # macOS

        # --- Settings ---
        settings_frame = ttk.LabelFrame(main_container, text=" Transcoding Settings ", padding="10")
        settings_frame.pack(fill=tk.X, pady=10)
        
        self.use_defaults_var = tk.BooleanVar(value=self.settings.get("use_defaults", True))
        self.defaults_cb = ttk.Checkbutton(settings_frame, text="Use Defaults", variable=self.use_defaults_var, command=self.toggle_defaults)
        self.defaults_cb.pack(anchor=tk.W, pady=(0, 5))
        
        row1 = ttk.Frame(settings_frame)
        row1.pack(fill=tk.X, pady=2)
        
        # 1. Video Codec
        lbl1 = ttk.Label(row1, text="Video Codec:", width=12)
        lbl1.pack(side=tk.LEFT)
        self.vcodec_var = tk.StringVar()
        self.cb_vcodec = ttk.Combobox(row1, textvariable=self.vcodec_var, values=list(VIDEO_CODECS.keys()), state="readonly", width=12)
        self.cb_vcodec.pack(side=tk.LEFT, padx=5)
        self.cb_vcodec.bind("<<ComboboxSelected>>", self._on_vcodec_change)

        # 2. Container Format
        lbl2 = ttk.Label(row1, text="Container Format:", width=15)
        lbl2.pack(side=tk.LEFT, padx=(20, 0))
        self.container_var = tk.StringVar()
        self.cb_container = ttk.Combobox(row1, textvariable=self.container_var, values=list(CONTAINERS.keys()), state="readonly", width=10)
        self.cb_container.pack(side=tk.LEFT, padx=5)
        self.cb_container.bind("<<ComboboxSelected>>", self._on_container_change)
        
        # 3. Audio Codec
        lbl3 = ttk.Label(row1, text="Audio Codec:", width=12)
        lbl3.pack(side=tk.LEFT, padx=(20, 0))
        self.acodec_var = tk.StringVar()
        self.cb_acodec = ttk.Combobox(row1, textvariable=self.acodec_var, values=list(AUDIO_CODECS.keys()), state="readonly", width=12)
        self.cb_acodec.pack(side=tk.LEFT, padx=5)

        row2 = ttk.Frame(settings_frame)
        row2.pack(fill=tk.X, pady=5)
        
        lbl4 = ttk.Label(row2, text="Resolution:", width=10)
        lbl4.pack(side=tk.LEFT)
        self.res_var = tk.StringVar()
        self.cb_res = ttk.Combobox(
            row2,
            textvariable=self.res_var,
            values=["default", "auto", "480p", "576p", "720p", "1080p", "1440p", "4k"],
            state="readonly",
            width=10,
        )
        self.cb_res.pack(side=tk.LEFT, padx=5)
        
        lbl5 = ttk.Label(row2, text="Video Quality:", width=12)
        lbl5.pack(side=tk.LEFT, padx=(20, 0))
        self.crf_var = tk.StringVar()
        self.cb_crf = ttk.Combobox(row2, textvariable=self.crf_var, values=list(self.quality_options.keys()), state="readonly", width=15)
        self.cb_crf.pack(side=tk.LEFT, padx=5)
        self.cb_crf.bind("<<ComboboxSelected>>", self._on_quality_change)
        
        # Custom CRF value entry
        self.custom_crf_var = tk.StringVar()
        self.custom_crf_entry = ttk.Entry(row2, textvariable=self.custom_crf_var, width=8, state=tk.DISABLED)
        self.custom_crf_entry.pack(side=tk.LEFT, padx=2)
        
        lbl6 = ttk.Label(row2, text="Sharpening:", width=12)
        lbl6.pack(side=tk.LEFT, padx=(20, 0))
        self.sharp_var = tk.StringVar()
        self.cb_sharp = ttk.Combobox(
            row2,
            textvariable=self.sharp_var,
            values=list(SHARPENING_LABELS.values()),
            state="readonly",
            width=18,
        )
        self.cb_sharp.pack(side=tk.LEFT, padx=5)

        self.settings_widgets = [
            lbl1, self.cb_vcodec, lbl2, self.cb_container, lbl3, self.cb_acodec,
            lbl4, self.cb_res, lbl5, self.cb_crf, self.custom_crf_entry, lbl6, self.cb_sharp
        ]

        # --- Output ---
        output_frame = ttk.LabelFrame(main_container, text=" Output Directory ", padding="10")
        output_frame.pack(fill=tk.X, pady=5)
        self.out_dir_var = tk.StringVar()
        ttk.Entry(output_frame, textvariable=self.out_dir_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(output_frame, text="Browse...", command=self.browse_output).pack(side=tk.RIGHT)

        # --- Progress & Logs ---
        progress_frame = ttk.Frame(main_container, padding="5")
        progress_frame.pack(fill=tk.X, pady=5)
        
        self.progress_var = tk.DoubleVar()
        self.pb = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.pb.pack(fill=tk.X, pady=5)
        
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(progress_frame, textvariable=self.status_var, font=("Helvetica", 9, "italic")).pack(side=tk.LEFT)
        
        # --- Control Buttons ---
        ctrl_frame = ttk.Frame(main_container)
        ctrl_frame.pack(fill=tk.X, pady=10)
        
        self.start_btn = ttk.Button(ctrl_frame, text="START CONVERSION", command=self.start_transcoding, padding=10)
        self.start_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))
        
        self.pause_btn = ttk.Button(ctrl_frame, text="STOP", command=self.pause_transcoding, state=tk.DISABLED, padding=10)
        self.pause_btn.pack(side=tk.LEFT, padx=5)
        
        self.cancel_btn = ttk.Button(ctrl_frame, text="CANCEL", command=self.stop_transcoding, state=tk.DISABLED, padding=10)
        self.cancel_btn.pack(side=tk.LEFT, padx=5)

        self.exit_btn = ttk.Button(ctrl_frame, text="EXIT", command=self.exit_app, padding=10)
        self.exit_btn.pack(side=tk.LEFT, padx=(5, 0))

    def _load_defaults(self):
        self.vcodec_var.set(self.settings.get("last_video_codec", "default"))
        self.container_var.set(self.settings.get("last_container", "default"))
        self.acodec_var.set(self.settings.get("last_audio_codec", "default"))
        self.res_var.set(self.settings.get("last_resolution", "default"))
        
        # Initial filter refresh (this also sets quality options via _on_vcodec_change)
        self._on_vcodec_change()
        # Restore actual saved values if compatible
        self.container_var.set(self.settings.get("last_container", "default"))
        self._on_container_change()
        self.acodec_var.set(self.settings.get("last_audio_codec", "default"))
        
        # Determine initial quality label from saved CRF
        saved_crf = self.settings.get("crf", 23)
        initial_q = "Standard" # Default profile prefix
        
        # Find matching label for saved CRF or stick with Standard
        found = False
        for label, val in self.quality_options.items():
            if val is not None and val == saved_crf:
                initial_q = label
                found = True
                break
        
        if not found:
            # Try to match by prefix if value changed due to codec
            for label in self.quality_options.keys():
                if label.startswith("Standard"):
                    initial_q = label
                    break
                    
        self.crf_var.set(initial_q)
        
        self.sharp_var.set(SHARPENING_LABELS["none"])
        self.out_dir_var.set(self.settings.get("downloads_dir", ""))
        
        # Apply the "Use Defaults" state (disable/enable widgets)
        self.toggle_defaults()

    def toggle_defaults(self):
        enabled = self.use_defaults_var.get()
        self.settings.set("use_defaults", enabled)
        
        state = tk.DISABLED if enabled else tk.NORMAL
        for widget in self.settings_widgets:
            try:
                widget.configure(state=state)
            except tk.TclError:
                pass # Some styles might not support state on Labels
        
        if self.use_defaults_var.get():
            self.vcodec_var.set("default")
            self._on_vcodec_change()
            self.container_var.set("default")
            self._on_container_change()
            self.acodec_var.set("default")
            self.res_var.set("default")
            
            # Find Standard label
            std_label = "Standard"
            for k in self.quality_options.keys():
                if k.startswith("Standard"):
                    std_label = k
                    break
            self.crf_var.set(std_label)
            self.sharp_var.set(SHARPENING_LABELS["none"])

    def _on_vcodec_change(self, event=None):
        codec = self.vcodec_var.get()
        lookup_codec = "h264" if codec == "default" else codec
        valid_containers = self.VIDEO_CODEC_CONTAINERS.get(lookup_codec, [])
        
        # If current codec is 'default', we can also allow 'default' (mp4) in containers
        if codec == "default":
            valid_containers = ["default"] + valid_containers
            
        self.cb_container.config(values=valid_containers)
        
        if self.container_var.get() not in valid_containers:
            self.container_var.set(valid_containers[0] if valid_containers else "default")
        
        self._on_container_change()
        
        # Update dynamic quality labels
        self._update_quality_options(lookup_codec)

    def _update_quality_options(self, codec):
        """Update the quality dropdown labels and values based on the current codec"""
        std = self.CRF_QUALITY_MATCHED['standard'].get(codec, 23)
        high = self.CRF_QUALITY_MATCHED['high'].get(codec, 20)
        low = self.CRF_QUALITY_MATCHED['low'].get(codec, 27)
        vl = self.CRF_QUALITY_MATCHED['visually_lossless'].get(codec, 15)
        
        self.quality_options = {
            f"Standard CRF-{std}": std,
            f"High CRF-{high}": high,
            f"Low CRF-{low}": low,
            f"Visually Lossless CRF-{vl}": vl,
            "Custom Value": None
        }
        
        old_sel = self.crf_var.get()
        new_sel = old_sel
        
        # Try to maintain the same profile (Standard/High/Low)
        prefixes = ["Standard", "High", "Low", "Visually Lossless", "Custom Value"]
        for prefix in prefixes:
            if old_sel.startswith(prefix):
                for label in self.quality_options.keys():
                    if label.startswith(prefix):
                        new_sel = label
                        break
                break
        
        self.cb_crf.config(values=list(self.quality_options.keys()))
        self.crf_var.set(new_sel)
        
        # Update setting
        val = self._get_crf_value()
        if val is not None:
            self.settings.set("crf", val)

    def _on_container_change(self, event=None):
        container = self.container_var.get()
        lookup_container = "mp4" if container == "default" else container
        valid_audio = ["copy"] + self.CONTAINER_AUDIO.get(lookup_container, [])
        
        # If current container is 'default', we can also allow 'default' (aac) in audio
        if container == "default" and "default" not in valid_audio:
            valid_audio = ["default"] + valid_audio
            
        self.cb_acodec.config(values=valid_audio)
        
        if self.acodec_var.get() not in valid_audio:
            self.acodec_var.set(valid_audio[0] if valid_audio else "default")

    def _on_quality_change(self, event=None):
        """Handle quality dropdown change to show/hide custom CRF entry"""
        selected = self.crf_var.get()
        if selected == "Custom Value":
            self.custom_crf_entry.config(state=tk.NORMAL)
            self.custom_crf_entry.focus()
        else:
            self.custom_crf_entry.config(state=tk.DISABLED)
            self.custom_crf_var.set("")
        
        # Proactively update CRF value in settings if profile changes
        val = self._get_crf_value()
        if val is not None:
            self.settings.set("crf", val)

    def _get_crf_profile_key(self, label):
        """Map GUI labels to CRF_QUALITY_MATCHED keys"""
        if "Standard" in label: return "standard"
        if "High" in label: return "high"
        if "Low" in label: return "low"
        if "Visually Lossless" in label: return "visually_lossless"
        return None

    def _get_crf_value(self):
        """Get CRF value from quality options or custom input, with validation"""
        selected = self.crf_var.get()
        
        if selected == "Custom Value":
            custom_input = self.custom_crf_var.get().strip()
            if not custom_input:
                messagebox.showerror("Error", "Please enter a custom CRF value between 0 and 51.")
                return None
            try:
                crf_value = int(custom_input)
                if not (0 <= crf_value <= 51):
                    messagebox.showerror("Error", "CRF value must be between 0 and 51.")
                    return None
                return crf_value
            except ValueError:
                messagebox.showerror("Error", "Please enter a valid integer for CRF value.")
                return None
        else:
            profile_key = self._get_crf_profile_key(selected)
            if profile_key:
                vcodec = self.vcodec_var.get()
                lookup_codec = "h264" if vcodec == "default" else vcodec
                return self.CRF_QUALITY_MATCHED.get(profile_key, {}).get(lookup_codec, 23)
            return self.quality_options.get(selected, 23)

    def _get_sharpening_key(self):
        selected = self.sharp_var.get()
        for key, label in SHARPENING_LABELS.items():
            if label == selected:
                return key
        return "none"

    def add_files(self):
        files = filedialog.askopenfilenames(title="Select Video Files")
        existing_items = {self.tree.item(i)['values'][0]: i for i in self.tree.get_children()}
        
        for f in files:
            if f in existing_items:
                item_id = existing_items[f]
                status = self.tree.item(item_id)['values'][1]
                if status.lower() == "done":
                    if messagebox.askyesno("File Present", f"'{Path(f).name}' is already marked as Done. Do you want to enqueue it again?"):
                        self.tree.set(item_id, "status", "Pending")
                continue
            
            self.tree.insert("", tk.END, values=(f, "Pending"))
        self._save_queue_to_file()

    def add_folder(self):
        folder = filedialog.askdirectory(title="Select Folder")
        if not folder: return
        extensions = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv"}
        
        count = 0
        existing_items = {self.tree.item(i)['values'][0]: i for i in self.tree.get_children()}
        
        for root, dirs, files in os.walk(folder):
            for f in files:
                if Path(f).suffix.lower() in extensions:
                    path = str(Path(root) / f)
                    if path in existing_items:
                        item_id = existing_items[path]
                        status = self.tree.item(item_id)['values'][1]
                        if status.lower() == "done":
                            # For folders, maybe we don't want to prompt for EVERY file?
                            # Let's prompt once or just skip. The user said:
                            # "If some video is present with done status but added again, prompt user"
                            # I'll prompt for each unique file for now as it's safer.
                            if messagebox.askyesno("File Present", f"'{Path(path).name}' is already marked as Done. Do you want to enqueue it again?"):
                                self.tree.set(item_id, "status", "Pending")
                        continue
                        
                    self.tree.insert("", tk.END, values=(path, "Pending"))
                    count += 1
            if not self.recursive_var.get(): break
        
        if count > 0:
            self._save_queue_to_file()
        else:
            messagebox.showinfo("No Files", "No compatible video files found in the folder.")

    def clear_list(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        self._save_queue_to_file()

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            
            # Conditionally show/hide "Enqueue Again"
            selected_items = self.tree.selection()
            has_redoable = any(self.tree.item(i)['values'][1].lower() in ["cancelled", "done", "error"] for i in selected_items)
            
            # Clear and rebuild menu to truly hide/show items
            self.context_menu.delete(0, tk.END)
            self.context_menu.add_command(label="Move to Top", command=self.move_to_top)
            self.context_menu.add_command(label="Move Up", command=self.move_up)
            self.context_menu.add_command(label="Move Down", command=self.move_down)
            self.context_menu.add_command(label="Move to Bottom", command=self.move_to_bottom)
            self.context_menu.add_separator()
            self.context_menu.add_command(label="Remove from Queue", command=self.remove_selected)
            
            if has_redoable:
                self.context_menu.add_command(label="Enqueue Again", command=self.enqueue_again)
                
            self.context_menu.post(event.x_root, event.y_root)

    def move_to_top(self):
        selected = self.tree.selection()
        if not selected: return
        for item in reversed(selected):
            self.tree.move(item, "", 0)
        self._save_queue_to_file()

    def move_up(self):
        selected = self.tree.selection()
        if not selected: return
        for item in selected:
            idx = self.tree.index(item)
            if idx > 0:
                self.tree.move(item, "", idx - 1)
        self._save_queue_to_file()

    def move_down(self):
        selected = self.tree.selection()
        if not selected: return
        for item in reversed(selected):
            idx = self.tree.index(item)
            if idx < len(self.tree.get_children()) - 1:
                self.tree.move(item, "", idx + 1)
        self._save_queue_to_file()

    def move_to_bottom(self):
        selected = self.tree.selection()
        if not selected: return
        last_idx = len(self.tree.get_children()) - 1
        for item in selected:
            self.tree.move(item, "", last_idx)
        self._save_queue_to_file()

    def enqueue_again(self):
        selected = self.tree.selection()
        if not selected: return
        
        last_idx = len(self.tree.get_children()) - 1
        for item in selected:
            path, status = self.tree.item(item)['values']
            if status.lower() in ["cancelled", "done", "error"]:
                self.tree.set(item, "status", "Pending")
                self.tree.move(item, "", last_idx)
        
        self._save_queue_to_file()

    def remove_selected(self):
        selected = self.tree.selection()
        if not selected: return
        if messagebox.askyesno("Remove", f"Remove {len(selected)} item(s) from queue?"):
            for item in selected:
                self.tree.delete(item)
            self._save_queue_to_file()

    def open_downloads(self):
        """Open the current downloads (transcoded) folder in File Explorer"""
        path = self.settings.get("downloads_dir")
        if path and os.path.exists(path):
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])

    def exit_app(self):
        """Handle application shutdown: stop processes, cleanup, and quit"""
        try:
            # 1. Stop accepting UI callbacks and cancel pending after() jobs.
            self._closing = True
            self.cancel_all_background_tasks()

            # 2. Inform user (quick status change)
            self.status_var.set("Exiting...")
            self.root.update()

            # 3. Kill only the engine process owned by this application.
            if hasattr(self, 'service'):
                self.service.cleanup()
        except Exception as e:
            print(f"Cleanup error during exit: {e}")
        finally:
            self.root.quit()
            self.root.destroy()

    def cancel_all_background_tasks(self):
        """Cancel all pending after() tasks to prevent updates after destroy"""
        if hasattr(self, "root") and self.root:
            try:
                job_ids = self.root.tk.call("after", "info")
                for job_id in job_ids:
                    try:
                        self.root.after_cancel(job_id)
                    except Exception as inner_error:
                        print(f"Could not cancel after() job {job_id}: {inner_error}")
            except Exception as outer_error:
                print(f"Could not enumerate after() jobs: {outer_error}")

    def _on_auto_update_toggle(self):
        self.settings.set("auto_update", self.auto_update_var.get())

    def _on_multi_session_toggle(self):
        enabled = self.multi_session_var.get()
        self.settings.set("multi_session_enabled", enabled)
        if enabled:
            self._save_queue_to_file()
        else:
            # Optionally remove the file if disabled? User didn't ask, but good practice.
            # Let's just leave it for now.
            pass

    def _get_queue_file_path(self):
        return Path(self.settings.get("queue_file"))

    def _save_queue_to_file(self):
        """Save current queue to queue.txt in data folder"""
        if not self.multi_session_var.get():
            return
            
        try:
            queue_file = self._get_queue_file_path()
            with open(queue_file, "w", encoding="utf-8") as f:
                for item_id in self.tree.get_children():
                    path, status = self.tree.item(item_id)['values']
                    f.write(f"{path}|{status}\n")
        except Exception as e:
            print(f"Error saving queue: {e}")

    def _load_queue_from_file(self):
        """Load queue from queue.txt, skipping Done files"""
        try:
            queue_file = self._get_queue_file_path()
            if not queue_file.exists():
                return
                
            loaded_count = 0
            with open(queue_file, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().rsplit("|", 1)
                    if len(parts) == 2:
                        path, status = parts
                        path = path.strip()
                        if not path:
                            continue

                        # Only reload Pending, Paused, or Error files
                        if status.lower() in ["done", "cancelled"]:
                            continue
                            
                        if not os.path.exists(path):
                            continue
                            
                        # Insert into tree directly
                        self.tree.insert("", tk.END, values=(path, status))
                        loaded_count += 1
            
            if loaded_count > 0:
                print(f"[Multi-Session] Loaded {loaded_count} files from queue.")
        except Exception as e:
            print(f"Error loading queue: {e}")

    def browse_output(self):
        d = filedialog.askdirectory()
        if d: self.out_dir_var.set(d)

    def prompt_ffmpeg_download(self):
        if messagebox.askyesno("FFmpeg Missing", "FFmpeg is required for transcoding. Would you like to download it now?"):
            self._begin_ffmpeg_download()
        else:
            self.status_var.set("Ready")

    def _begin_ffmpeg_download(self):
        """Start the FFmpeg download worker without a second prompt."""
        self.start_btn.config(state=tk.DISABLED)
        self.progress_var.set(0)
        threading.Thread(target=self._download_ffmpeg_thread, daemon=True).start()

    def _download_ffmpeg_thread(self):
        try:
            def update_ui(percent, message):
                def apply_update(p=percent, s=message):
                    self.progress_var.set(p)
                    self.status_var.set(s)
                self._post_ui(apply_update)

            self.ffmpeg_tool.download_and_extract(progress_callback=update_ui)
            self._post_ui(self._ffmpeg_ready)
        except Exception as e:
            def show_error(error=e):
                self.ffmpeg_status_lbl.config(text="FFmpeg: MISSING", foreground="red")
                self.progress_var.set(0)
                self.status_var.set("FFmpeg download failed.")
                messagebox.showerror("Download Error", f"Failed to download FFmpeg: {error}")
                self.start_btn.config(state=tk.NORMAL)
            self._post_ui(show_error)

    def _ffmpeg_ready(self):
        self.ffmpeg_status_lbl.config(text="FFmpeg: OK", foreground="green")
        self.progress_var.set(0)
        self.status_var.set("FFmpeg ready.")
        self.start_btn.config(state=tk.NORMAL)
        # Update engine paths to use the newly downloaded local binaries
        self.engine.ffmpeg_path = self.ffmpeg_tool.get_ffmpeg_command()
        self.engine.ffprobe_path = self.ffmpeg_tool.get_ffprobe_command()

    def start_transcoding(self):
        items = self.tree.get_children()
        if not items:
            messagebox.showwarning("No Input", "Please add files to the list.")
            return
            
        if not os.path.exists(self.out_dir_var.get()):
            messagebox.showerror("Error", "Output directory does not exist.")
            return

        self.start_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.NORMAL)
        
        # Save settings
        self.settings.set("last_container", self.container_var.get())
        self.settings.set("last_video_codec", self.vcodec_var.get())
        self.settings.set("last_audio_codec", self.acodec_var.get())
        self.settings.set("last_resolution", self.res_var.get())
        
        selected_crf = self._get_crf_value()
        if selected_crf is None:
            # Error message already shown in _get_crf_value
            self.start_btn.config(state=tk.NORMAL)
            self.pause_btn.config(state=tk.DISABLED)
            self.cancel_btn.config(state=tk.DISABLED)
            return
        self.settings.set("crf", selected_crf)
        self.settings.set("downloads_dir", self.out_dir_var.get())

        options = {
            "container": self.container_var.get(),
            "video_codec": self.vcodec_var.get(),
            "audio_codec": self.acodec_var.get(),
            "resolution": self.res_var.get(),
            "sharpening": self._get_sharpening_key(),
            "crf": selected_crf
        }
        
        # Prepare files and items, skipping already 'Done' ones
        files = []
        process_items = []
        for i in items:
            path, status = self.tree.item(i)['values']
            if status not in ["Done", "Cancelled"]:
                files.append(path)
                process_items.append(i)
        
        if not files:
            messagebox.showinfo("Nothing to do", "All files in the list are already marked as 'Done' or 'Cancelled'.")
            self._finished()
            return

        def ui_callback(type, data):
            if type == "status":
                self._post_ui(lambda value=data: self.status_var.set(value))
            elif type == "progress":
                if data is not None:
                    self._post_ui(lambda value=data: self.progress_var.set(value))
            elif type == "log":
                print(data)
            elif type == "update_list_status":
                idx, status = data

                def update_tree(item_index=idx, item_status=status):
                    self.tree.set(process_items[item_index], "status", item_status)
                    self._save_queue_to_file()

                self._post_ui(update_tree)
            elif type == "finished":
                def on_finished(reason=data):
                    self._finished(reason)
                    self._save_queue_to_file()

                self._post_ui(on_finished)

        thread = self.service.start_batch(files, self.out_dir_var.get(), options, ui_callback)
        if thread is None:
            messagebox.showinfo("Batch Active", "A transcoding batch is already in progress.")
            self._finished()

    def pause_transcoding(self):
        self.service.pause()
        self.status_var.set("Stopping...")

    def stop_transcoding(self):
        self.service.stop()
        self.status_var.set("Stopping...")

    def _finished(self, reason="Done"):
        self.start_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.DISABLED)
        self.progress_var.set(0)
        
        status_msg = "Finished"
        if reason == "Stopped":
            status_msg = "Stopped"
        elif reason == "Cancelled":
            status_msg = "Cancelled"

        self.status_var.set(status_msg)

if __name__ == "__main__":
    root = tk.Tk()
    app = VideoTranscoderApp(root)
    root.mainloop()
