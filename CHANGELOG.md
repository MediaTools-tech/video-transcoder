# Changelog

All notable changes to the MediaTools Video Transcoder will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Added `576p` (1024x576) resolution support across the desktop GUI, CLI,
  API, and Docker web UI; the desktop resolution list now also exposes
  `1440p`.
- Added headless CLI mode: no arguments opens the GUI, while `-help`,
  `-i/--input`, `-o/--output-dir`, codec/resolution overrides,
  `--use-saved-settings`, and `--download-ffmpeg` run from the terminal.
- Added CLI support to `python -m video_transcoder` and the PyInstaller
  executable.
- CLI mode stays headless: FFmpeg update, queue, and shortcut prompts remain
  GUI-only, and FFmpeg download requires `--download-ffmpeg`.
- Added `assets/Logo_128x128.icns` for macOS shortcuts and packaged assets.
- Added a FastAPI/web layer in `src/video_transcoder/api` that reuses the
  desktop `core` engine for Docker deployments.
- Added `docker/video-transcoder/` with a multi-stage Dockerfile, Compose
  deployment, health checks, and container documentation.
- Added Docker build/test/push automation with GHCR and optional Docker Hub
  publishing.
- Added focused FFmpeg tool, CLI, and API tests.

### Changed
- Sharpening remains None/Light/Medium/Strong/Adaptive; the user guide now
  documents that Light/Medium/Strong use `unsharp` and Adaptive uses `cas`.
- Switched the Docker runtime to Alpine with Alpine's FFmpeg package, reducing
  the image size substantially while keeping the existing API and web UI.
- The Docker web UI now hides **Cancel Job** after a job finishes and offers
  **Delete** for completed, failed, or cancelled jobs. Deleting removes the
  server-side upload and output; browser downloads are untouched.
- PyInstaller builds now default output to `transcoded` next to the
  executable when writable, with a per-user fallback.
- Marked portable onedir builds keep settings, queue state, and downloaded
  FFmpeg binaries inside `_internal`, avoiding AppData/Local. The build script
  adds `_internal/portable.flag` to the portable folder.
- Refactored the repository from a monorepo app/library split into a standalone
  single-app layout under `src/video_transcoder/`.
- Replaced all `mediatools.*` imports with `video_transcoder.*`.
- Moved runtime assets, docs, scripts, and build tooling to their new top-level
  locations.
- Repointed PyInstaller builds at the new package and resource paths.
- Removed machine-specific absolute paths from the migrated settings file.
  Stored paths from another operating system are now replaced with the current
  platform's defaults on load.
- Frozen and non-editable installs now keep mutable state in the per-user data
  directory instead of the install directory.
- Worker threads now marshal all Tk updates through a main-thread queue.
- FFmpeg startup checks run in the background and avoid duplicate version calls.
- Docker installs the same package as PyInstaller (`pip install .[api]`) and
  serves the same frontend/API code; the engine is not duplicated.

### Removed
- Removed the 500 MB API upload limit and the unused Docker `.env.example`;
  uploads are now streamed without an application-level size limit.
- Removed the `python -m video-transcoder` compatibility shim; use
  `python -m video_transcoder` from source or the `video-transcoder` console
  command.
- Removed the application update checker, `resources/version.txt`, and the
  `last_app_update_check` setting. FFmpeg updates are the only update feature.
- Removed the global `taskkill` behavior that terminated every FFmpeg process
  on the machine.

### Fixed
- Hardened FFmpeg downloads with network timeouts, archive validation, safe
  extraction, replacement checks, and scoped temporary-file cleanup.
- Fixed Linux FFmpeg checks when the download URL does not expose a version.
- Fixed CRF value `0` being ignored by truthiness checks.
- Fixed PyInstaller builds to bundle the existing `docs/UserGuide.md`
  instead of a missing PDF file.
- Made settings writes atomic, backed up unreadable settings files, and
  migrated legacy settings, queue, and FFmpeg binaries into relocated storage.
- Hardened FFmpeg version ordering, executable availability checks, and update
  rollback when an FFprobe replacement fails.
- Fixed worker cleanup after EXIT, CLI Ctrl+C subprocess termination, queue
  round-tripping for paths containing `|`, duplicate GUI batch starts, and
  development/macOS shortcut launchers.
- Removed duplicate engine assignments and unused imports/state.

## [1.0.1] - 2026-02-05

### Changed
- Renamed **STOP** button to **CANCEL** for better clarity.
- Added **EXIT** button for a dedicated way to close the application.
- Expanded queue context menu with **Move to Bottom**.
- Added **Enqueue Again** option for "Cancelled" tasks to quickly retry them.

## [1.0.0] - 2026-02-04

### Added
- **Initial Release**: Full-featured batch video transcoding application.
- **Hardware-Friendly Codecs**: Support for H.264, H.265 (HEVC), AV1, and VP9.
- **Container Selection**: Choice of MP4, MKV, WebM, AVI, and MOV.
- **Queue Management**: 
  - Right-click context menu (Move to Top, Up, Down, Remove).
  - Persistence across sessions (`queue.txt`).
- **Auto-FFmpeg Management**:
  - Automatic detection and 28-day update checks.
  - Background download and extraction.
- **UI/UX Refinements**:
  - Silent subprocess execution (no CMD windows on Windows).
  - "Downloads Folder" quick access button.
  - Intelligent status feedback during startup checks.
- **Robustness**:
  - Graceful exit handling (kills FFmpeg processes).
  - Smart collision handling for output filenames (no `_transcoded` suffix unless needed).
  - Exponential backoff for file handle management during extraction.

### Technical
- Modular architecture with `TranscoderEngine` and `TranscoderService`.
- Cross-platform path resolution compatible with PyInstaller `onedir` and `onefile` modes.
- Multi-threaded transcoding with real-time progress parsing.
