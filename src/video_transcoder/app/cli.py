import argparse
import sys
from pathlib import Path

from video_transcoder import __version__
from video_transcoder.core.transcoder_engine import (
    AUDIO_CODECS,
    CONTAINERS,
    SHARPENING_FILTERS,
    VIDEO_CODECS,
    TranscoderEngine,
)
from video_transcoder.core.transcoder_service import TranscoderService
from video_transcoder.ffmpeg.tool import FFmpegTool
from video_transcoder.settings.settings_manager import SettingsManager

RESOLUTIONS = ["default", "auto", "480p", "576p", "720p", "1080p", "1440p", "4k"]


def build_parser():
    parser = argparse.ArgumentParser(
        prog="video-transcoder",
        description="Batch video transcoder. Run without arguments to open the GUI.",
        add_help=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  mt-vtr.exe                         Open the GUI\n"
            "  mt-vtr.exe --gui                   Open the GUI explicitly\n"
            "  mt-vtr.exe -help                   Show this help\n"
            "  mt-vtr.exe -i input.mp4            Transcode with factory-default settings\n"
            "  mt-vtr.exe -i input.mp4 -o out     Choose an output directory\n"
            "  mt-vtr.exe -i input.mp4 --use-saved-settings\n"
            "                                     Reuse the GUI's last-used settings\n"
            "  mt-vtr.exe -i a.mp4 -i b.mp4       Transcode multiple files\n"
        ),
    )
    parser.add_argument("-h", "--help", "-help", action="help", help="Show this help and exit")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-i",
        "--input",
        dest="inputs",
        action="append",
        metavar="FILE",
        help="Input video file; repeat for multiple files",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        metavar="DIR",
        help="Output directory (default: saved downloads directory)",
    )
    parser.add_argument("--container", choices=list(CONTAINERS.keys()), help="Output container")
    parser.add_argument("--video-codec", choices=list(VIDEO_CODECS.keys()), help="Video codec")
    parser.add_argument("--audio-codec", choices=list(AUDIO_CODECS.keys()), help="Audio codec")
    parser.add_argument("--resolution", choices=RESOLUTIONS, help="Output resolution")
    parser.add_argument("--sharpening", choices=list(SHARPENING_FILTERS.keys()), help="Sharpening filter")
    parser.add_argument("--crf", type=int, metavar="0-51", help="Constant Rate Factor")
    parser.add_argument(
        "--download-ffmpeg",
        action="store_true",
        help="Download FFmpeg if it is not already available",
    )
    parser.add_argument(
        "--use-saved-settings",
        action="store_true",
        help="Use the last-used GUI settings instead of factory defaults",
    )
    parser.add_argument(
        "files",
        nargs="*",
        metavar="FILE",
        help="Input video files (positional alternative to -i)",
    )
    return parser


def _collect_inputs(args, parser):
    raw_inputs = list(args.inputs or []) + list(args.files or [])
    if not raw_inputs:
        parser.error("no input files provided; use -i FILE or run without arguments to open the GUI")

    inputs = []
    for value in raw_inputs:
        path = Path(value).expanduser()
        if not path.is_file():
            print(f"Error: input file not found or not a file: {value}", file=sys.stderr)
            return None
        inputs.append(str(path))
    return inputs


def _resolve_options(settings, args):
    if args.use_saved_settings:
        container = args.container or settings.get("last_container", "default")
        video_codec = args.video_codec or settings.get("last_video_codec", "default")
        audio_codec = args.audio_codec or settings.get("last_audio_codec", "default")
        resolution = args.resolution or settings.get("last_resolution", "default")
        crf = args.crf if args.crf is not None else settings.get("crf", 23)
    else:
        container = args.container or "default"
        video_codec = args.video_codec or "default"
        audio_codec = args.audio_codec or "default"
        resolution = args.resolution or "default"
        crf = args.crf if args.crf is not None else 23

    sharpening = args.sharpening or "none"

    if container not in CONTAINERS:
        container = "default"
    if video_codec not in VIDEO_CODECS:
        video_codec = "default"
    if audio_codec not in AUDIO_CODECS:
        audio_codec = "default"
    if resolution not in RESOLUTIONS:
        resolution = "default"
    if sharpening not in SHARPENING_FILTERS:
        sharpening = "none"

    try:
        crf = int(crf)
    except (TypeError, ValueError):
        crf = 23
    if not 0 <= crf <= 51:
        crf = 23

    return {
        "container": container,
        "video_codec": video_codec,
        "audio_codec": audio_codec,
        "resolution": resolution,
        "sharpening": sharpening,
        "crf": crf,
    }


def _default_output_dir(settings):
    output_dir = settings.get("downloads_dir")
    if not output_dir:
        output_dir = Path(settings.get("base_dir", ".")) / "transcoded"
    return Path(output_dir).expanduser()


def _ensure_ffmpeg(ffmpeg_tool, allow_download):
    if ffmpeg_tool.is_ffmpeg_available():
        return True

    if not allow_download:
        print(
            "Error: FFmpeg is not available. Run the GUI once to download it, "
            "install FFmpeg on PATH, or pass --download-ffmpeg.",
            file=sys.stderr,
        )
        return False

    print("FFmpeg not found. Downloading...")
    last_percent = [-10]

    def report(percent, message):
        percent = int(percent)
        if percent >= last_percent[0] + 10 or percent >= 100:
            last_percent[0] = percent
            if message:
                print(message)

    try:
        ffmpeg_tool.download_and_extract(progress_callback=report)
    except Exception as e:
        print(f"Error: failed to download FFmpeg: {e}", file=sys.stderr)
        return False

    if not ffmpeg_tool.is_ffmpeg_available():
        print("Error: FFmpeg download finished but the binaries are not available.", file=sys.stderr)
        return False
    return True


def run_cli(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.crf is not None and not 0 <= args.crf <= 51:
        parser.error("--crf must be between 0 and 51")

    inputs = _collect_inputs(args, parser)
    if inputs is None:
        return 1

    settings = SettingsManager()
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else _default_output_dir(settings)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"Error: could not create output directory '{output_dir}': {e}", file=sys.stderr)
        return 1

    options = _resolve_options(settings, args)
    ffmpeg_tool = FFmpegTool(settings)
    if not _ensure_ffmpeg(ffmpeg_tool, args.download_ffmpeg):
        return 1

    engine = TranscoderEngine(
        ffmpeg_tool.get_ffmpeg_command(),
        ffmpeg_tool.get_ffprobe_command(),
    )
    service = TranscoderService(engine, settings)

    print(f"Input files: {len(inputs)}")
    print(f"Output directory: {output_dir}")
    print(
        "Settings: "
        f"container={options['container']}, "
        f"video={options['video_codec']}, "
        f"audio={options['audio_codec']}, "
        f"resolution={options['resolution']}, "
        f"sharpening={options['sharpening']}, "
        f"crf={options['crf']}"
    )

    statuses = {}
    finish_reason = [None]
    last_progress = [-10]

    def ui_callback(kind, data):
        if kind == "status":
            print(data)
        elif kind == "progress":
            if data is not None and data >= last_progress[0] + 10:
                last_progress[0] = data
                print(f"Progress: {data}%")
        elif kind == "log":
            print(data)
        elif kind == "update_list_status":
            index, status = data
            statuses[index] = status
        elif kind == "finished":
            finish_reason[0] = data

    try:
        thread = service.start_batch(inputs, str(output_dir), options, ui_callback)
        if thread is None:
            print("Error: a transcoding batch is already active.", file=sys.stderr)
            return 1
        thread.join()
    except KeyboardInterrupt:
        print("Interrupted. Stopping FFmpeg...", file=sys.stderr)
        service.stop()
        return 130

    if finish_reason[0] != "Done":
        print(f"Transcoding did not complete (reason: {finish_reason[0]}).", file=sys.stderr)
        return 1

    if len(statuses) != len(inputs):
        print("Transcoding did not report a status for every input file.", file=sys.stderr)
        return 1

    failures = [index for index, status in statuses.items() if status != "Done"]
    if failures:
        print(f"Transcoding finished with {len(failures)} failed file(s).", file=sys.stderr)
        return 1

    print("Transcoding complete.")
    return 0
