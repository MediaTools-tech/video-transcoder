#!/usr/bin/env bash
# build_onefile.sh - Cross-platform build script (single file)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SRC_DIR="$REPO_ROOT/src"
PKG_DIR="$SRC_DIR/video_transcoder"
ASSETS_DIR="$REPO_ROOT/assets"
SCRIPTS_DIR="$REPO_ROOT/scripts"
DOCS_DIR="$REPO_ROOT/docs"

# Platform detection
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
        echo "Platform: Windows (Git Bash)"
        REPO_ROOT=$(cygpath -m "$REPO_ROOT")
        SRC_DIR=$(cygpath -m "$SRC_DIR")
        PKG_DIR=$(cygpath -m "$PKG_DIR")
        ASSETS_DIR=$(cygpath -m "$ASSETS_DIR")
        SCRIPTS_DIR=$(cygpath -m "$SCRIPTS_DIR")
        DOCS_DIR=$(cygpath -m "$DOCS_DIR")
        PLATFORM_UTIL="cleanup_files.bat"
        PYTHON_CMD="python"
        SEP=";"
        EXE_NAME="mt-vtr.exe"
        APP_ICON="$ASSETS_DIR/Logo_128x128.ico"
        CONSOLE_OPTS="--console --hide-console=hide-late"
        EXTRA_IMPORTS="--hidden-import=winshell --hidden-import=win32com --hidden-import=win32com.client"
        ;;
    Darwin*)
        echo "Platform: macOS"
        PLATFORM_UTIL="cleanup_files.sh"
        PYTHON_CMD="python3"
        SEP=":"
        EXE_NAME="mt-vtr"
        APP_ICON="$ASSETS_DIR/Logo_128x128.icns"
        CONSOLE_OPTS="--windowed"
        EXTRA_IMPORTS=""
        ;;
    Linux*)
        echo "Platform: Linux"
        PLATFORM_UTIL="cleanup_files.sh"
        PYTHON_CMD="python3"
        SEP=":"
        EXE_NAME="mt-vtr"
        APP_ICON="$ASSETS_DIR/Logo_128x128.ico"
        CONSOLE_OPTS="--console"
        EXTRA_IMPORTS=""
        ;;
    *)
        echo "Platform: Unknown"
        PLATFORM_UTIL="cleanup_files.sh"
        PYTHON_CMD="python"
        SEP=":"
        EXE_NAME="mt-vtr"
        APP_ICON="$ASSETS_DIR/Logo_128x128.ico"
        CONSOLE_OPTS="--console"
        EXTRA_IMPORTS=""
        ;;
esac

echo "Repository root: $REPO_ROOT"
echo "Source directory: $SRC_DIR"
echo "Data separator: '$SEP'"
echo ""

echo "Cleaning previous builds..."
rm -rf "$REPO_ROOT/build" "$REPO_ROOT/dist"

echo "Building single-file executable..."
$PYTHON_CMD -m PyInstaller \
  --onefile \
  $CONSOLE_OPTS \
  --noupx \
  --name "mt-vtr" \
  --paths="$SRC_DIR" \
  --icon="$APP_ICON" \
  --add-data="$ASSETS_DIR${SEP}assets" \
  --add-data="$SCRIPTS_DIR/$PLATFORM_UTIL${SEP}scripts" \
  --add-data="$DOCS_DIR/UserGuide.md${SEP}docs" \
  --add-data="$REPO_ROOT/README.md${SEP}docs" \
  --add-data="$REPO_ROOT/LICENSE${SEP}docs" \
  --hidden-import=video_transcoder \
  --hidden-import=video_transcoder.app \
  --hidden-import=video_transcoder.core \
  --hidden-import=video_transcoder.ffmpeg \
  --hidden-import=video_transcoder.gui \
  --hidden-import=video_transcoder.settings \
  --hidden-import=video_transcoder.system \
  --hidden-import=video_transcoder.utils \
  $EXTRA_IMPORTS \
  --clean \
  "$PKG_DIR/__main__.py"

echo ""
echo "✓ Build complete!"
echo "Output: dist/$EXE_NAME"
