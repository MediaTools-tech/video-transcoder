import os
import platform
import subprocess
import requests
import zipfile
import tarfile
import shutil
import time
import re
from pathlib import Path

class FFmpegTool:
    # Platform-specific filenames
    LOCAL_FILENAMES_FFMPEG = {
        "Windows": "ffmpeg.exe",
        "Linux": "ffmpeg",
        "Darwin": "ffmpeg",
    }

    LOCAL_FILENAMES_FFPROBE = {
        "Windows": "ffprobe.exe",
        "Linux": "ffprobe",
        "Darwin": "ffprobe",
    }

    FFMPEG_DOWNLOAD_URLS = {
        "Windows": "https://github.com/GyanD/codexffmpeg/releases/download/8.0/ffmpeg-8.0-full_build.zip",
        "Linux": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
        "Darwin": "https://evermeet.cx/ffmpeg/ffmpeg-8.0.zip",
    }

    def __init__(self, settings_manager):
        self.settings = settings_manager
        system = platform.system().lower()
        if "windows" in system or "win32" in system:
            self.current_platform = "Windows"
        elif "darwin" in system:
            self.current_platform = "Darwin"
        else:
            self.current_platform = "Linux"

    def get_ffmpeg_path(self):
        """Always returns the LOCAL path where FFmpeg SHOULD be"""
        bin_dir = self.settings.get("bin_dir", "bin")
        return str(Path(bin_dir) / self.LOCAL_FILENAMES_FFMPEG[self.current_platform])

    def get_ffprobe_path(self):
        """Always returns the LOCAL path where FFprobe SHOULD be"""
        bin_dir = self.settings.get("bin_dir", "bin")
        return str(Path(bin_dir) / self.LOCAL_FILENAMES_FFPROBE[self.current_platform])

    def get_ffmpeg_command(self):
        """Returns local path if it exists, otherwise 'ffmpeg'"""
        path = self.get_ffmpeg_path()
        return path if os.path.exists(path) else "ffmpeg"

    def get_ffprobe_command(self):
        """Returns local path if it exists, otherwise 'ffprobe'"""
        path = self.get_ffprobe_path()
        return path if os.path.exists(path) else "ffprobe"

    def is_ffmpeg_downloaded(self):
        """Check if both binaries exist in the local bin directory"""
        return os.path.exists(self.get_ffmpeg_path()) and os.path.exists(self.get_ffprobe_path())

    def is_ffmpeg_available(self):
        """Check if FFmpeg is either downloaded locally or available system-wide"""
        if self.is_ffmpeg_downloaded():
            return True
        try:
            IS_WINDOWS = self.current_platform == "Windows"
            process_kwargs = {"capture_output": True, "check": True}
            if IS_WINDOWS:
                process_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                
            subprocess.run(["ffmpeg", "-version"], **process_kwargs)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            return False

    def get_ffmpeg_latest_url(self):
        """Return the download URL for the current platform"""
        return self.FFMPEG_DOWNLOAD_URLS.get(self.current_platform)

    def _version_tuple(self, ver_str):
        """Extract a comparable version tuple (e.g. (8, 0)) from various strings."""
        if not ver_str:
            return None
        # Handle cases like "ffmpeg version 8.0-essentials_build..." by taking
        # the first dotted-numeric group.
        match = re.search(r'(\d+)\.(\d+)(?:\.(\d+))?', str(ver_str))
        if not match:
            return None
        return tuple(int(part) if part is not None else 0 for part in match.groups())

    def get_local_version(self):
        """Get the version of the local FFmpeg binary"""
        path = self.get_ffmpeg_path()
        if not os.path.exists(path):
            return None

        try:
            IS_WINDOWS = self.current_platform == "Windows"
            process_kwargs = {"capture_output": True, "text": True}
            if IS_WINDOWS:
                process_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            result = subprocess.run([path, "-version"], **process_kwargs)
            # Example: "ffmpeg version 8.0-essentials_build..."
            first_line = result.stdout.split('\n')[0]
            match = re.search(r'version\s+([^\s,]+)', first_line)
            return match.group(1) if match else "unknown"
        except Exception:
            return "unknown"

    def get_remote_version(self):
        """Estimate the remote version from the download URL when it is versioned."""
        url = self.get_ffmpeg_latest_url()
        if not url:
            return None

        # Example URLs:
        # .../releases/download/8.0/ffmpeg-8.0-full_build.zip
        match = re.search(r'(\d+\.\d+)', url)
        return match.group(1) if match else None

    def is_up_to_date(self, local_version=None, remote_version=None):
        """Check whether the local FFmpeg version matches the remote version.

        When the remote version cannot be derived from the download URL (for
        example the unversioned Linux release URL), skip the update prompt
        instead of treating every launch as an update.
        """
        local_value = local_version if local_version is not None else self.get_local_version()
        remote_value = remote_version if remote_version is not None else self.get_remote_version()

        remote = self._version_tuple(remote_value)
        if remote is None:
            # No parseable remote version (e.g. the unversioned Linux URL):
            # skip the update prompt instead of prompting forever.
            return True

        if not local_value or str(local_value).strip().lower() == "unknown":
            return False
        local = self._version_tuple(local_value)
        if local is None:
            return False

        length = max(len(local), len(remote))
        local_padded = local + (0,) * (length - len(local))
        remote_padded = remote + (0,) * (length - len(remote))
        return local_padded >= remote_padded

    def _safe_replace(self, src_path, dst_path):
        """Safely replace a file, handling 'file in use' errors on Windows with multiple retries."""
        src = Path(src_path)
        dst = Path(dst_path)

        if not src.exists():
            return False

        if src.resolve() == dst.resolve():
            return True

        backup = dst.with_name(dst.name + ".old")
        last_error = None

        # Try up to 5 times to replace the file with increasing delay.
        for attempt in range(5):
            backup_created = False
            try:
                if dst.exists():
                    if backup.exists():
                        os.remove(backup)
                    os.replace(dst, backup)
                    backup_created = True

                os.replace(src, dst)

                if backup_created and backup.exists():
                    os.remove(backup)
                return True
            except OSError as e:
                last_error = e

                # Restore the previous binary if we moved it aside before failing.
                if backup_created and not dst.exists() and backup.exists():
                    try:
                        os.replace(backup, dst)
                    except OSError as restore_error:
                        last_error = restore_error

                if attempt < 4:
                    time.sleep(min(pow(2, attempt), 8))

        if last_error:
            raise last_error
        return False

    def _extract_zip_member(self, zip_ref, filename, destination):
        """Extract one named file from a zip archive to a fixed destination."""
        for member in zip_ref.namelist():
            if not member.endswith("/") and Path(member).name == filename:
                with zip_ref.open(member) as source, open(destination, "wb") as target:
                    shutil.copyfileobj(source, target)
                return True
        return False

    def _extract_tar_member(self, tar_ref, filename, destination):
        """Extract one named regular file from a tar archive to a fixed destination."""
        for member in tar_ref.getmembers():
            if member.isfile() and Path(member.name).name == filename:
                source = tar_ref.extractfile(member)
                if source is None:
                    return False
                with source, open(destination, "wb") as target:
                    shutil.copyfileobj(source, target)
                return True
        return False

    def download_and_extract(self, progress_callback=None):
        """Download and extract FFmpeg to the bin directory."""
        url = self.get_ffmpeg_latest_url()
        if not url:
            raise ValueError(f"No download URL for {self.current_platform}")

        bin_dir = Path(self.settings.get("bin_dir", "bin"))
        bin_dir.mkdir(parents=True, exist_ok=True)
        archive_path = bin_dir / "ffmpeg_download.tmp"
        temp_extract = bin_dir / "ffmpeg_extract_tmp"

        if temp_extract.exists():
            shutil.rmtree(temp_extract)
        temp_extract.mkdir(parents=True, exist_ok=True)

        ffmpeg_final = self.get_ffmpeg_path()
        ffprobe_final = self.get_ffprobe_path()
        ffmpeg_name = self.LOCAL_FILENAMES_FFMPEG[self.current_platform]
        ffprobe_name = self.LOCAL_FILENAMES_FFPROBE[self.current_platform]
        staged_ffmpeg = temp_extract / ffmpeg_name
        staged_ffprobe = temp_extract / ffprobe_name

        try:
            # 1. Download
            if progress_callback:
                progress_callback(0, "Downloading FFmpeg...")

            with requests.get(url, stream=True, timeout=(10, 60)) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0

                with open(archive_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback and total_size > 0:
                                percent = (downloaded / total_size) * 100
                                progress_callback(percent, f"Downloading FFmpeg: {percent:.1f}%")

            # 2. Extract only the expected binaries into fixed, safe destinations.
            if progress_callback:
                progress_callback(100, "Extracting FFmpeg...")

            if self.current_platform in ["Windows", "Darwin"]:
                with zipfile.ZipFile(archive_path, "r") as zip_ref:
                    has_ffmpeg = self._extract_zip_member(zip_ref, ffmpeg_name, staged_ffmpeg)
                    has_ffprobe = self._extract_zip_member(zip_ref, ffprobe_name, staged_ffprobe)
            else:
                with tarfile.open(archive_path, "r:xz") as tar_ref:
                    has_ffmpeg = self._extract_tar_member(tar_ref, ffmpeg_name, staged_ffmpeg)
                    has_ffprobe = self._extract_tar_member(tar_ref, ffprobe_name, staged_ffprobe)

            if not has_ffmpeg or not staged_ffmpeg.is_file() or staged_ffmpeg.stat().st_size == 0:
                raise RuntimeError("Downloaded archive does not contain a valid FFmpeg binary")
            if not has_ffprobe or not staged_ffprobe.is_file() or staged_ffprobe.stat().st_size == 0:
                raise RuntimeError("Downloaded archive does not contain a valid FFprobe binary")

            # 3. Move files into place only after both expected binaries are valid.
            # Keep a backup of the previous FFmpeg binary so that a failed
            # FFprobe replacement can roll it back and avoid a mixed-version
            # pair.
            ffmpeg_existed = Path(ffmpeg_final).exists()
            ffmpeg_backup = None
            if ffmpeg_existed:
                ffmpeg_backup = temp_extract / (ffmpeg_name + ".pre-update")
                shutil.copy2(str(ffmpeg_final), str(ffmpeg_backup))

            try:
                if not self._safe_replace(staged_ffmpeg, ffmpeg_final):
                    raise RuntimeError("Could not replace the FFmpeg binary")
                if not self._safe_replace(staged_ffprobe, ffprobe_final):
                    raise RuntimeError("Could not replace the FFprobe binary")
            except Exception:
                restored = False
                if ffmpeg_backup is not None and ffmpeg_backup.exists():
                    try:
                        restored = self._safe_replace(ffmpeg_backup, ffmpeg_final)
                        if restored:
                            print("Restored the previous FFmpeg binary after a failed update.")
                    except OSError as restore_error:
                        print(f"Could not restore the previous FFmpeg binary: {restore_error}")

                if not restored and not ffmpeg_existed:
                    # Fresh install: do not leave a new FFmpeg next to a
                    # missing/old FFprobe if the second replacement failed.
                    try:
                        Path(ffmpeg_final).unlink(missing_ok=True)
                    except OSError as cleanup_error:
                        print(f"Could not remove the partial FFmpeg install: {cleanup_error}")
                raise

            if self.current_platform != "Windows":
                try:
                    os.chmod(ffmpeg_final, 0o755)
                    os.chmod(ffprobe_final, 0o755)
                except OSError:
                    pass

            return True
        finally:
            # Clean up only the files/directories created by this operation.
            if archive_path.exists():
                archive_path.unlink()
            if temp_extract.exists():
                shutil.rmtree(temp_extract)
