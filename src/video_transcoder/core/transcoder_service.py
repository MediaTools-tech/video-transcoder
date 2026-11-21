from pathlib import Path
from typing import List, Dict, Any, Callable
import threading
import time
from .transcoder_engine import TranscoderEngine, CONTAINERS

class TranscoderService:
    def __init__(self, engine: TranscoderEngine, settings_manager: Any):
        self.engine = engine
        self.settings = settings_manager
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.is_active = False

    def start_batch(
        self, 
        input_files: List[str], 
        output_dir: str, 
        options: Dict[str, Any],
        ui_callback: Callable[[str, Any], None]
    ):
        if self.is_active:
            return
        
        self.is_active = True
        self.stop_event.clear()
        self.pause_event.clear()
        
        thread = threading.Thread(
            target=self._worker, 
            args=(input_files, output_dir, options, ui_callback),
            daemon=True
        )
        thread.start()
        return thread

    def _get_unique_path(self, base_path: Path) -> str:
        """Add suffix if file already exists"""
        if not base_path.exists():
            return str(base_path)
        
        counter = 1
        stem = base_path.stem
        suffix = base_path.suffix
        parent = base_path.parent
        
        while True:
            new_path = parent / f"{stem}_{counter}{suffix}"
            if not new_path.exists():
                return str(new_path)
            counter += 1

    def stop(self):
        self.stop_event.set()
        self.pause_event.clear()
        self.engine.resume_active_process()

    def pause(self):
        self.pause_event.set()
        self.engine.suspend_active_process()

    def resume(self):
        self.pause_event.clear()
        self.engine.resume_active_process()

    def cleanup(self):
        """Signal stop and terminate any active engine subprocess for clean exit"""
        self.stop_event.set()
        self.pause_event.clear()
        self.engine.resume_active_process()
        self.engine.terminate_active_process()

    def _worker(
        self, 
        input_files: List[str], 
        output_dir: str, 
        options: Dict[str, Any],
        ui_callback: Callable[[str, Any], None]
    ):
        total = len(input_files)
        try:
            for i, input_path in enumerate(input_files):
                if self.stop_event.is_set():
                    break

                while self.pause_event.is_set() and not self.stop_event.is_set():
                    time.sleep(0.1)

                if self.stop_event.is_set():
                    break

                ui_callback("status", f"Processing {i+1}/{total}: {Path(input_path).name}")
                ui_callback("update_list_status", (i, "Processing"))
                
                # Determine output filename
                file_name = Path(input_path).stem
                ext = CONTAINERS.get(options.get("container", "mp4"), "mp4")
                candidate_path = Path(output_dir) / f"{file_name}.{ext}"
                output_path = self._get_unique_path(Path(candidate_path))
                
                try:
                    self.engine.transcode_video(
                        input_path,
                        output_path,
                        options,
                        progress_callback=lambda p, l: ui_callback("progress", p),
                        stop_event=self.stop_event,
                        pause_event=self.pause_event
                    )
                    
                    if self.stop_event.is_set():
                        ui_callback("log", f"Cancelled: {input_path}")
                        self._remove_partial_file(output_path)
                        ui_callback("update_list_status", (i, "Cancelled"))
                        break

                    ui_callback("log", f"Finished: {input_path}")
                    ui_callback("update_list_status", (i, "Done"))
                except Exception as e:
                    if self.stop_event.is_set():
                        ui_callback("log", f"Cancelled: {input_path}")
                        self._remove_partial_file(output_path)
                        ui_callback("update_list_status", (i, "Cancelled"))
                        break
                    ui_callback("log", f"Error processing {input_path}: {e}")
                    ui_callback("update_list_status", (i, "Error"))
        finally:
            reason = "Cancelled" if self.stop_event.is_set() else "Done"

            ui_callback("finished", reason)
            self.is_active = False

    def _remove_partial_file(self, file_path: str):
        """Delete a cancelled partial output file if it exists."""
        try:
            p = Path(file_path)
            if p.exists():
                p.unlink()
                print(f"Deleted partial file: {p}")
        except Exception as e:
            print(f"Error deleting partial file: {e}")
