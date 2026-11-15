import json
import ntpath
import os
import shutil
import sys
import threading
from pathlib import Path
from typing import Dict, Any

class SettingsManager:
    _instance = None
    PORTABLE_MARKER = "portable.flag"

    _default_settings = {
        "bin_dir": "",
        "downloads_dir": "", # Default output dir
        "data_dir": "",
        "queue_file": "",
        "gui_theme": "Default",
        "auto_update": True,
        "multi_session_enabled": True,
        "use_defaults": True,
        "last_ffmpeg_update_check": 0,
        "last_container": "mp4",
        "last_video_codec": "h264",
        "last_audio_codec": "aac",
        "last_resolution": "default",
        "crf": 23,
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SettingsManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self._save_lock = threading.RLock()
        self.dynamic_paths = self._calculate_dynamic_paths()
        self.settings_file = self._get_settings_path()
        self._migrate_legacy_data()
        self.current_settings = self._load_settings()
        
        # Ensure path defaults, replacing paths produced on a different OS.
        for key, default_path in self.dynamic_paths.items():
            current_value = self.current_settings.get(key)
            if not current_value or self._is_foreign_path(current_value):
                self.current_settings[key] = default_path
        
        self._extract_bundled_resources() # Copy bundled stuff to storage
        self.save_settings()
        self._ensure_directories()

    def _extract_bundled_resources(self):
        """Copy bundled bin/assets to the storage directory on first run"""
        if not getattr(sys, "frozen", False) or self._is_portable_mode():
            return

        bundle_root = Path(sys._MEIPASS)
        storage_root = Path(self.get("base_dir"))

        # We only want to copy if the destination doesn't exist or is empty
        for folder in ["bin", "data", "assets"]:
            src = bundle_root / folder
            if not src.exists(): # Try _internal fallback for modern PyInstaller
                src = bundle_root / "_internal" / folder

            if not src.exists():
                continue

            dst = storage_root / folder
            if dst.exists() and os.listdir(str(dst)):
                # Never overwrite user data; keep what's already there.
                continue

            try:
                shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
            except OSError as e:
                print(f"Could not extract bundled folder '{folder}': {e}")

    def _get_bundle_resource(self, relative_path: str) -> Path:
        """Find a read-only bundled resource from source, PyInstaller, or pip installs."""
        if getattr(sys, "frozen", False):
            root = Path(sys._MEIPASS)
            # Case 1: Root (onefile or old onedir)
            path = root / relative_path
            if path.exists():
                return path
            # Case 2: Inside _internal (modern onedir)
            internal_path = root / "_internal" / relative_path
            if internal_path.exists():
                return internal_path
            return path

        # Source checkout / editable install.
        source_candidate = self._get_source_root() / relative_path
        if source_candidate.exists():
            return source_candidate

        # Package-relative fallback for future package-data layouts.
        package_candidate = Path(__file__).resolve().parent.parent / relative_path
        if package_candidate.exists():
            return package_candidate

        # Non-editable install data-files (see pyproject.toml).
        installed_candidate = Path(sys.prefix) / "share" / "video-transcoder" / relative_path
        if installed_candidate.exists():
            return installed_candidate

        return source_candidate

    def _get_source_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    @staticmethod
    def _is_foreign_path(value) -> bool:
        """Detect a stored path that belongs to a different operating system."""
        if not isinstance(value, str) or not value:
            return True
        if sys.platform == "win32":
            return value.startswith("/")
        drive, _ = ntpath.splitdrive(value)
        return bool(drive)

    def _is_source_checkout(self) -> bool:
        root = self._get_source_root()
        return (root / "pyproject.toml").is_file() and (root / "src" / "video_transcoder").is_dir()

    def _get_portable_storage_dir(self) -> Path | None:
        """Return ``_internal`` for a marked onedir portable build."""
        if not getattr(sys, "frozen", False):
            return None

        internal = Path(sys.executable).resolve().parent / "_internal"
        if (internal / self.PORTABLE_MARKER).is_file():
            return internal
        return None

    def _is_portable_mode(self) -> bool:
        return self._get_portable_storage_dir() is not None

    def _get_storage_dir(self) -> Path:
        """Return the writable app directory for the current runtime mode.

        A marked portable onedir build keeps state inside its bundled
        ``_internal`` directory. Other frozen builds and non-editable installs
        use the per-user data directory. A source checkout keeps runtime state
        at the repo root for development.
        """
        portable_dir = self._get_portable_storage_dir()
        if portable_dir is not None:
            return portable_dir

        if getattr(sys, "frozen", False) or not self._is_source_checkout():
            return self.get_persistent_data_dir()
        return self._get_source_root()

    @staticmethod
    def _writable_portable_output_dir(exe_path: Path) -> Path | None:
        """Return ``transcoded`` next to a frozen executable when writable."""
        exe_dir = exe_path.resolve().parent
        if (
            sys.platform == "darwin"
            and exe_dir.name == "MacOS"
            and exe_dir.parent.name == "Contents"
        ):
            return None

        candidate = exe_dir / "transcoded"
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / f".write-test-{os.getpid()}"
            probe.write_text("", encoding="utf-8")
            probe.unlink()
        except OSError:
            return None
        return candidate

    def _get_portable_output_dir(self) -> Path | None:
        if not getattr(sys, "frozen", False):
            return None
        return self._writable_portable_output_dir(Path(sys.executable))

    def _calculate_dynamic_paths(self):
        base_dir = self._get_storage_dir()

        downloads_dir = self._get_portable_output_dir() or (base_dir / "transcoded")
        data_dir = base_dir / "data"
        bin_dir = base_dir / "bin"
        
        return {
            "base_dir": str(base_dir),
            "downloads_dir": str(downloads_dir),
            "data_dir": str(data_dir),
            "bin_dir": str(bin_dir),
            "queue_file": str(data_dir / "queue.txt"),
        }

    def get_persistent_data_dir(self):
        app_name = "Video Transcoder"
        if sys.platform == "win32":
            local_app_data = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            data_dir = Path(local_app_data) / "MediaTools" / app_name
        elif sys.platform == "darwin":
            data_dir = Path.home() / "Library" / "Application Support" / "MediaTools" / app_name
        else:
            data_dir = Path.home() / ".local" / "share" / "MediaTools" / app_name
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    def _get_settings_path(self):
        return self._get_storage_dir() / "data" / "settings.json"

    def _migrate_legacy_data(self):
        """One-time migration from the pre-relocation storage layout.

        Frozen builds and non-editable installs used to resolve the storage
        directory to the install/source root (``parents[3]`` of this file).
        Copy settings, the queue, and any downloaded FFmpeg binaries into the
        current storage directory when they are missing there, so upgrading
        users do not silently lose their data.
        """
        storage_dir = self._get_storage_dir()
        source_root = self._get_source_root()
        if storage_dir == source_root:
            return  # Source checkout: nothing moved, nothing to migrate.

        candidates = [source_root]
        if getattr(sys, "frozen", False):
            # Onedir installs: legacy data lived next to the executable.
            candidates.append(Path(sys.executable).resolve().parent)

        storage = Path(storage_dir)
        for base in candidates:
            for relative in ("data/settings.json", "data/queue.txt"):
                legacy_file = base / relative
                new_file = storage / relative
                if legacy_file.is_file() and not new_file.exists():
                    try:
                        new_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(legacy_file), str(new_file))
                        print(f"Migrated {relative} to {new_file}")
                    except OSError as e:
                        print(f"Could not migrate {legacy_file}: {e}")

            for binary in ("bin/ffmpeg", "bin/ffprobe", "bin/ffmpeg.exe", "bin/ffprobe.exe"):
                legacy_bin = base / binary
                new_bin = storage / binary
                if legacy_bin.is_file() and not new_bin.exists():
                    try:
                        new_bin.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(legacy_bin), str(new_bin))
                        print(f"Migrated {binary} to {new_bin}")
                    except OSError as e:
                        print(f"Could not migrate {legacy_bin}: {e}")

    def _load_settings(self) -> Dict[str, Any]:
        """Load settings and filter out irrelevant/junk keys"""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    user_settings = json.load(f)
                
                # Filter to only keep transcoder-relevant keys
                valid_keys = set(self._default_settings.keys()) | set(self.dynamic_paths.keys()) | {"base_dir"}
                filtered = {k: v for k, v in user_settings.items() if k in valid_keys}
                
                merged = self._default_settings.copy()
                merged.update(filtered)
                return merged
        except Exception as e:
            print(f"Error loading settings: {e}")
            # Keep the unreadable file for recovery instead of silently
            # overwriting it with factory defaults on the next save.
            try:
                if self.settings_file.exists():
                    backup = self.settings_file.with_name(self.settings_file.name + ".bak")
                    shutil.copy2(str(self.settings_file), str(backup))
                    print(f"Backed up unreadable settings to {backup}")
            except OSError as backup_error:
                print(f"Could not back up unreadable settings: {backup_error}")
        return self._default_settings.copy()

    def save_settings(self):
        temp_file = self.settings_file.with_name(self.settings_file.name + ".tmp")
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            with self._save_lock:
                # Write to a temp file and atomically replace so a crash or a
                # concurrent reader never sees a half-written settings.json.
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(self.current_settings, f, indent=4)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_file, self.settings_file)
            return True
        except Exception as e:
            print(f"Error saving settings: {e}")
            try:
                temp_file.unlink(missing_ok=True)
            except OSError:
                pass
            return False

    def get(self, key: str, default: Any = None) -> Any:
        with self._save_lock:
            return self.current_settings.get(key, default)

    def set(self, key: str, value: Any):
        with self._save_lock:
            self.current_settings[key] = value
            self.save_settings()

    def _ensure_directories(self):
        for path_key in ["downloads_dir", "data_dir", "bin_dir"]:
            path = self.get(path_key)
            if path:
                os.makedirs(path, exist_ok=True)
