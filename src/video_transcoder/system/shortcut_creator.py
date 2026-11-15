import os
import shutil
import sys
import platform
import logging
from tkinter import messagebox
from pathlib import Path

from video_transcoder import __version__


class ShortcutCreator:
    def __init__(self, settings_manager=None):
        self.app_name = f"MediaTools Video Transcoder v{__version__}"
        self.settings_manager = settings_manager
        self.logger = logging.getLogger(__name__)

        # Check Windows dependencies once at initialization
        self._check_windows_dependencies()

    def _check_windows_dependencies(self):
        """Check for Windows dependencies at initialization"""
        self.has_windows_deps = False
        if platform.system() == "Windows":
            try:
                import winshell

                self.has_windows_deps = True
                self.logger.info("Windows shortcut dependencies available")
            except ImportError:
                self.logger.info(
                    "Windows shortcut dependencies not available, using fallback methods"
                )

    def create_desktop_shortcut_cross_platform(self):
        """Cross-platform desktop shortcut creation"""
        system = platform.system()
        self.logger.info(f"Creating desktop shortcut for {system}")

        try:
            if system == "Windows":
                return self._create_windows_shortcut()
            elif system == "Darwin":
                return self._create_mac_shortcut()
            elif system == "Linux":
                return self._create_linux_shortcut()
            else:
                messagebox.showwarning(
                    "Unsupported Platform",
                    f"Shortcut creation not supported on {system}",
                )
                return False
        except Exception as e:
            self.logger.error(f"Shortcut creation failed: {e}")
            messagebox.showerror("Error", f"Could not create shortcut: {e}")
            return False

    def _get_data_dir(self):
        """Return the app's writable data directory (or a fallback)."""
        if self.settings_manager:
            try:
                configured = self.settings_manager.get("data_dir")
                if configured:
                    return Path(configured)
            except Exception as e:
                self.logger.warning(f"Could not read data_dir from settings: {e}")
        return Path.home() / ".video-transcoder"

    def _create_dev_wrapper(self):
        """Create (or reuse) a launcher script that runs the app via `python -m video_transcoder`.

        Development shortcuts cannot point at a bare `__main__.py` — that
        opens the source file instead of launching the app. The wrapper sets
        PYTHONPATH to the source tree so the module runs correctly.
        """
        source_root = Path(__file__).resolve().parents[2]  # .../src
        repo_root = source_root.parent
        wrapper_dir = self._get_data_dir() / "launchers"
        wrapper_dir.mkdir(parents=True, exist_ok=True)

        if platform.system() == "Windows":
            wrapper = wrapper_dir / "run-video-transcoder.bat"
            python_exe = Path(sys.executable)
            pythonw = python_exe.with_name("pythonw.exe")
            interpreter = str(pythonw if pythonw.exists() else python_exe)
            wrapper.write_text(
                "@echo off\n"
                f'set "PYTHONPATH={source_root}"\n'
                f'cd /d "{repo_root}"\n'
                f'start "" "{interpreter}" -m video_transcoder\n',
                encoding="utf-8",
            )
        else:
            wrapper = wrapper_dir / "run-video-transcoder.sh"
            wrapper.write_text(
                "#!/bin/bash\n"
                f'export PYTHONPATH="{source_root}"\n'
                f'cd "{repo_root}"\n'
                f'exec "{sys.executable}" -m video_transcoder "$@"\n',
                encoding="utf-8",
            )
            os.chmod(wrapper, 0o755)
        return wrapper

    def _get_executable_and_icon_paths(self):
        """Get executable path and platform-appropriate icon path"""
        system = platform.system()
        if system == "Windows":
            icon_name = "Logo_128x128.ico"
        elif system == "Darwin":
            icon_name = "Logo_128x128.icns"
        else:  # Linux
            icon_name = "Logo_128x128.png"

        if getattr(sys, "frozen", False):
            # PyInstaller executable
            exe_path = sys.executable
            if self.settings_manager:
                assets_dir = self.settings_manager._get_bundle_resource("assets")
            else:
                assets_dir = None
                self.logger.warning("No settings manager; shortcut will use the default icon.")
        else:
            # Development mode: point at a generated wrapper, not at __main__.py
            exe_path = self._create_dev_wrapper()
            assets_dir = Path(__file__).resolve().parents[3] / "assets"

        icon_path = assets_dir / icon_name if assets_dir else None
        return str(exe_path), icon_path

    def _create_windows_shortcut(self):
        """Windows shortcut creation"""
        if self.has_windows_deps:
            return self._create_windows_proper_shortcut()
        else:
            return self._create_windows_manual_shortcut()

    def _create_windows_proper_shortcut(self):
        """Create proper Windows .lnk shortcut"""
        try:
            import winshell
            from win32com.client import Dispatch

            try:
                desktop = winshell.desktop()
            except Exception as e:
                self.logger.warning(f"winshell.desktop() failed, falling back to ~/Desktop: {e}")
                desktop = str(Path.home() / "Desktop")

            shortcut_path = Path(desktop) / f"{self.app_name}.lnk"
            exe_path, icon_path = self._get_executable_and_icon_paths()

            shell = Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(str(shortcut_path))

            shortcut.Targetpath = str(exe_path)
            shortcut.WorkingDirectory = str(Path(exe_path).parent)
            shortcut.Description = f"{self.app_name} - High-quality video transcoding"

            if icon_path and icon_path.exists():
                shortcut.IconLocation = f"{str(icon_path)},0"
            else:
                shortcut.IconLocation = f"{str(exe_path)},0"

            shortcut.save()
            messagebox.showinfo("Success", "Desktop shortcut created!")
            return True

        except Exception as e:
            self.logger.error(f"Proper Windows shortcut failed: {e}")
            return self._create_windows_manual_shortcut()

    def _create_windows_manual_shortcut(self):
        """Manual Windows shortcut using batch file"""
        try:
            desktop = Path.home() / "Desktop"
            exe_path, _ = self._get_executable_and_icon_paths()

            bat_content = f"""@echo off
cd /d "{Path(exe_path).parent}"
start "" "{Path(exe_path).name}"
"""
            bat_path = desktop / f"{self.app_name}.bat"
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat_content)

            messagebox.showinfo("Success", "Desktop shortcut created as batch file!")
            return True
        except Exception as e:
            self.logger.error(f"Manual Windows shortcut failed: {e}")
            return False

    def _create_linux_shortcut(self):
        """Linux .desktop file creation"""
        try:
            desktop = Path.home() / "Desktop"
            desktop_file = (
                desktop / f"{self.app_name.replace(' ', '-').lower()}.desktop"
            )

            exe_path, icon_path = self._get_executable_and_icon_paths()

            desktop_content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name={self.app_name}
Comment=High-quality video transcoding
Exec="{exe_path}"
Path={Path(exe_path).parent}
Icon={icon_path if icon_path and icon_path.exists() else ""}
Terminal=false
StartupNotify=true
Categories=AudioVideo;Video;
"""
            with open(desktop_file, "w", encoding="utf-8") as f:
                f.write(desktop_content)

            os.chmod(desktop_file, 0o755)
            messagebox.showinfo("Success", "Desktop shortcut created!")
            return True
        except Exception as e:
            self.logger.error(f"Linux shortcut failed: {e}")
            return False

    def _create_mac_shortcut(self):
        """macOS shortcut creation: minimal .app bundle with the bundled icon.

        A plain `.command` file cannot carry a custom icon. Building a tiny
        `.app` wrapper (launcher script + Info.plist + Logo_128x128.icns)
        gives the shortcut the app's icon, per the follow-up decision.
        """
        try:
            desktop = Path.home() / "Desktop"
            exe_path, icon_path = self._get_executable_and_icon_paths()

            app_path = desktop / f"{self.app_name}.app"
            contents = app_path / "Contents"
            macos_dir = contents / "MacOS"
            resources_dir = contents / "Resources"
            macos_dir.mkdir(parents=True, exist_ok=True)
            resources_dir.mkdir(parents=True, exist_ok=True)

            launcher = macos_dir / "launcher"
            launcher.write_text(
                "#!/bin/bash\n"
                f'exec "{exe_path}" "$@"\n',
                encoding="utf-8",
            )
            os.chmod(launcher, 0o755)

            bundle_icon = ""
            if (
                icon_path
                and Path(icon_path).exists()
                and str(icon_path).lower().endswith(".icns")
            ):
                shutil.copy2(str(icon_path), str(resources_dir / "AppIcon.icns"))
                bundle_icon = "AppIcon"
            else:
                self.logger.warning("No .icns icon found; the .app will use the default icon.")

            plist_lines = [
                '<?xml version="1.0" encoding="UTF-8"?>',
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
                '<plist version="1.0">',
                '<dict>',
                '\t<key>CFBundleName</key>',
                f'\t<string>{self.app_name}</string>',
                '\t<key>CFBundleDisplayName</key>',
                f'\t<string>{self.app_name}</string>',
                '\t<key>CFBundleExecutable</key>',
                '\t<string>launcher</string>',
                '\t<key>CFBundleIdentifier</key>',
                '\t<string>com.mediatools.videotranscoder</string>',
                '\t<key>CFBundleVersion</key>',
                f'\t<string>{__version__}</string>',
                '\t<key>CFBundleShortVersionString</key>',
                f'\t<string>{__version__}</string>',
                '\t<key>CFBundlePackageType</key>',
                '\t<string>APPL</string>',
            ]
            if bundle_icon:
                plist_lines += [
                    '\t<key>CFBundleIconFile</key>',
                    f'\t<string>{bundle_icon}</string>',
                ]
            plist_lines += ['</dict>', '</plist>', '']
            (contents / "Info.plist").write_text("\n".join(plist_lines), encoding="utf-8")

            messagebox.showinfo("Success", "Desktop shortcut created!")
            return True
        except Exception as e:
            self.logger.error(f"macOS shortcut failed: {e}")
            return False

    def shortcut_exists(self):
        """Check if shortcut already exists on desktop"""
        desktop = Path.home() / "Desktop"
        system = platform.system()

        if system == "Windows":
            return (desktop / f"{self.app_name}.lnk").exists() or (
                desktop / f"{self.app_name}.bat"
            ).exists()
        elif system == "Darwin":
            return (
                (desktop / f"{self.app_name}.app").exists()
                or (desktop / f"{self.app_name}.command").exists()
            )
        elif system == "Linux":
            return (
                desktop / f"{self.app_name.replace(' ', '-').lower()}.desktop"
            ).exists()
        return False

    def first_run_setup(self):
        """Check if first run and offer shortcut creation"""
        if self.shortcut_exists():
            return

        data_dir = self._get_data_dir()

        first_run_file = data_dir / "transcoder_first_run.flag"

        if not first_run_file.exists():
            data_dir.mkdir(parents=True, exist_ok=True)
            
            response = messagebox.askyesno(
                "Create Desktop Shortcut",
                f"Would you like to create a desktop shortcut for {self.app_name}?",
            )
            if response:
                self.create_desktop_shortcut_cross_platform()

            try:
                first_run_file.touch()
            except Exception as e:
                self.logger.warning(f"Could not create first run flag: {e}")
