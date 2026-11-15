import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from video_transcoder.settings.settings_manager import SettingsManager


class SettingsPathTest(unittest.TestCase):
    @unittest.skipIf(sys.platform == "win32", "POSIX path expectations")
    def test_windows_paths_are_foreign_on_posix(self):
        self.assertTrue(SettingsManager._is_foreign_path(r"E:\Projects\video-transcoder\data"))
        self.assertFalse(SettingsManager._is_foreign_path("/tmp/video-transcoder/data"))

    @unittest.skipUnless(sys.platform == "win32", "Windows path expectations")
    def test_posix_paths_are_foreign_on_windows(self):
        self.assertTrue(SettingsManager._is_foreign_path("/mnt/e/Projects/video-transcoder/data"))
        self.assertFalse(SettingsManager._is_foreign_path(r"E:\Projects\video-transcoder\data"))

    def test_portable_output_dir_is_next_to_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "mt-vtr.exe"
            exe.write_bytes(b"")
            output = SettingsManager._writable_portable_output_dir(exe)
            self.assertEqual(output, Path(tmp) / "transcoded")
            self.assertTrue(output.is_dir())


class PortableStorageTest(unittest.TestCase):
    def _manager(self):
        return object.__new__(SettingsManager)

    def _portable_tree(self, tmp, onefile=False):
        exe = Path(tmp) / "mt-vtr.exe"
        exe.write_bytes(b"")
        if onefile:
            meipass = Path(tmp) / "onefile-temp"
            meipass.mkdir()
        else:
            meipass = Path(tmp) / "_internal"
            meipass.mkdir()
        (meipass / SettingsManager.PORTABLE_MARKER).write_text(
            "portable", encoding="utf-8"
        )
        return exe, meipass

    def test_marked_onedir_uses_internal_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe, internal = self._portable_tree(tmp)
            manager = self._manager()
            with mock.patch.object(
                sys, "frozen", True, create=True
            ), mock.patch.object(
                sys, "executable", str(exe)
            ), mock.patch.object(
                sys, "_MEIPASS", str(internal), create=True
            ):
                self.assertEqual(manager._get_portable_storage_dir(), internal)
                self.assertTrue(manager._is_portable_mode())
                self.assertEqual(manager._get_storage_dir(), internal)

    def test_unmarked_build_is_not_portable(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe, internal = self._portable_tree(tmp)
            (internal / SettingsManager.PORTABLE_MARKER).unlink()
            manager = self._manager()
            with mock.patch.object(
                sys, "frozen", True, create=True
            ), mock.patch.object(
                sys, "executable", str(exe)
            ), mock.patch.object(
                sys, "_MEIPASS", str(internal), create=True
            ):
                self.assertIsNone(manager._get_portable_storage_dir())

    def test_marker_next_to_executable_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe, internal = self._portable_tree(tmp)
            (internal / SettingsManager.PORTABLE_MARKER).unlink()
            (Path(tmp) / SettingsManager.PORTABLE_MARKER).write_text(
                "portable", encoding="utf-8"
            )
            manager = self._manager()
            with mock.patch.object(
                sys, "frozen", True, create=True
            ), mock.patch.object(
                sys, "executable", str(exe)
            ), mock.patch.object(
                sys, "_MEIPASS", str(internal), create=True
            ):
                self.assertIsNone(manager._get_portable_storage_dir())

    def test_onefile_temp_directory_is_not_used_for_portable_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe, meipass = self._portable_tree(tmp, onefile=True)
            manager = self._manager()
            with mock.patch.object(
                sys, "frozen", True, create=True
            ), mock.patch.object(
                sys, "executable", str(exe)
            ), mock.patch.object(
                sys, "_MEIPASS", str(meipass), create=True
            ):
                self.assertIsNone(manager._get_portable_storage_dir())

    def test_portable_storage_does_not_create_appdata_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe, internal = self._portable_tree(tmp)
            manager = self._manager()
            with mock.patch.object(
                sys, "frozen", True, create=True
            ), mock.patch.object(
                sys, "executable", str(exe)
            ), mock.patch.object(
                sys, "_MEIPASS", str(internal), create=True
            ), mock.patch.object(
                manager,
                "get_persistent_data_dir",
                side_effect=AssertionError("AppData must not be used"),
            ):
                self.assertEqual(manager._get_storage_dir(), internal)

    def test_portable_mode_skips_resource_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe, internal = self._portable_tree(tmp)
            manager = self._manager()
            with mock.patch.object(
                sys, "frozen", True, create=True
            ), mock.patch.object(
                sys, "executable", str(exe)
            ), mock.patch.object(
                sys, "_MEIPASS", str(internal), create=True
            ), mock.patch(
                "video_transcoder.settings.settings_manager.shutil.copytree"
            ) as copytree:
                manager._extract_bundled_resources()
                copytree.assert_not_called()

    def test_initialize_writes_state_inside_internal(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe, internal = self._portable_tree(tmp)
            manager = self._manager()
            with mock.patch.object(
                sys, "frozen", True, create=True
            ), mock.patch.object(
                sys, "executable", str(exe)
            ), mock.patch.object(
                sys, "_MEIPASS", str(internal), create=True
            ), mock.patch.object(
                manager, "_get_source_root", return_value=Path(tmp)
            ), mock.patch.object(
                manager,
                "get_persistent_data_dir",
                side_effect=AssertionError("AppData must not be used"),
            ):
                manager._initialize()

            self.assertTrue((internal / "data" / "settings.json").is_file())
            self.assertTrue((internal / "bin").is_dir())
            self.assertFalse((Path(tmp) / "data").exists())


class SettingsPersistenceTest(unittest.TestCase):
    def _manager(self):
        manager = object.__new__(SettingsManager)
        manager._save_lock = threading.RLock()
        return manager

    def test_save_settings_replaces_file_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._manager()
            manager.settings_file = Path(tmp) / "data" / "settings.json"
            manager.current_settings = {"crf": 20}

            self.assertTrue(manager.save_settings())
            self.assertEqual(
                json.loads(manager.settings_file.read_text(encoding="utf-8")),
                {"crf": 20},
            )
            self.assertFalse(
                Path(str(manager.settings_file) + ".tmp").exists()
            )

    def test_failed_save_leaves_previous_settings_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._manager()
            manager.settings_file = Path(tmp) / "data" / "settings.json"
            manager.settings_file.parent.mkdir(parents=True)
            manager.settings_file.write_text('{"crf": 18}', encoding="utf-8")
            manager.current_settings = {"crf": 20}

            with mock.patch(
                "video_transcoder.settings.settings_manager.os.replace",
                side_effect=OSError("locked"),
            ):
                self.assertFalse(manager.save_settings())

            self.assertEqual(
                manager.settings_file.read_text(encoding="utf-8"),
                '{"crf": 18}',
            )
            self.assertFalse(
                Path(str(manager.settings_file) + ".tmp").exists()
            )

    def test_migrate_legacy_data_copies_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "legacy"
            storage = Path(tmp) / "storage"
            (legacy / "data").mkdir(parents=True)
            (legacy / "bin").mkdir()
            (legacy / "data" / "settings.json").write_text(
                '{"crf": 20}', encoding="utf-8"
            )
            (legacy / "data" / "queue.txt").write_text(
                "clip.mp4|Pending\n", encoding="utf-8"
            )
            (legacy / "bin" / "ffmpeg").write_text("binary", encoding="utf-8")

            manager = self._manager()
            with mock.patch.object(
                manager, "_get_storage_dir", return_value=storage
            ), mock.patch.object(
                manager, "_get_source_root", return_value=legacy
            ):
                manager._migrate_legacy_data()

            self.assertEqual(
                (storage / "data" / "settings.json").read_text(encoding="utf-8"),
                '{"crf": 20}',
            )
            self.assertEqual(
                (storage / "data" / "queue.txt").read_text(encoding="utf-8"),
                "clip.mp4|Pending\n",
            )
            self.assertEqual(
                (storage / "bin" / "ffmpeg").read_text(encoding="utf-8"),
                "binary",
            )

    def test_migrate_legacy_data_does_not_overwrite_new_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "legacy"
            storage = Path(tmp) / "storage"
            (legacy / "data").mkdir(parents=True)
            (storage / "data").mkdir(parents=True)
            (legacy / "data" / "settings.json").write_text(
                '{"crf": 20}', encoding="utf-8"
            )
            (storage / "data" / "settings.json").write_text(
                '{"crf": 30}', encoding="utf-8"
            )

            manager = self._manager()
            with mock.patch.object(
                manager, "_get_storage_dir", return_value=storage
            ), mock.patch.object(
                manager, "_get_source_root", return_value=legacy
            ):
                manager._migrate_legacy_data()

            self.assertEqual(
                (storage / "data" / "settings.json").read_text(encoding="utf-8"),
                '{"crf": 30}',
            )


if __name__ == "__main__":
    unittest.main()
