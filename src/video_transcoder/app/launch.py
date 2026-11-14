import sys


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)

    if not args or args in (["--gui"], ["-g"]):
        return run_gui()

    from video_transcoder.app.cli import run_cli

    return run_cli(args)


def run_gui():
    try:
        import tkinter as tk
        from video_transcoder.gui.main_window import VideoTranscoderApp
    except ImportError as e:
        print(f"GUI unavailable: {e}", file=sys.stderr)
        return 1

    try:
        root = tk.Tk()
    except tk.TclError as e:
        print(f"GUI unavailable: {e}", file=sys.stderr)
        return 1

    VideoTranscoderApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
