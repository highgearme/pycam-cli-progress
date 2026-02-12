import os
import sys
import json
import time
from datetime import datetime
from typing import Optional

import pycam.Utils.log
from pycam.Utils.events import get_event_handler, get_mainloop

log = pycam.Utils.log.get_logger()


class HeadlessProgressTracker:
    """
    Progress monitoring for headless PyCAM operations.
    
    Outputs progress via stderr in various formats for job queue systems
    and service integrations. Control via environment variables:
      PYCAM_PROGRESS_ENABLED    - Enable progress output (default: false)
      PYCAM_PROGRESS_FORMAT     - Output format: simple|json|structured
      PYCAM_PROGRESS_INTERVAL   - Update interval in seconds (default: 1.0)
    """

    def __init__(self,
                 operation_id: str = "pycam_process",
                 total_steps: Optional[int] = None,
                 enabled: Optional[bool] = None):
        """
        Initialize headless progress tracker.

        Args:
            operation_id: Identifier for this operation (used in output)
            total_steps: Total number of steps (if known), else None for indeterminate
            enabled: Enable progress output (if None, auto-detect from environment)
        """
        self.operation_id = operation_id
        self.total_steps = total_steps
        self.current_step = 0
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.current_message = ""
        self.last_message = ""
        
        # Auto-detect if not specified
        if enabled is None:
            self.enabled = os.environ.get("PYCAM_PROGRESS_ENABLED", "").lower() in ("1", "true", "yes")
        else:
            self.enabled = enabled
        
        # Get output format from environment
        self.output_format = os.environ.get("PYCAM_PROGRESS_FORMAT", "simple").lower()
        if self.output_format not in ("simple", "json", "structured"):
            self.output_format = "simple"
        
        # Update interval in seconds
        self.update_interval = float(os.environ.get("PYCAM_PROGRESS_INTERVAL", "1.0"))
        
        if self.enabled:
            log.debug(f"Headless progress tracking: {operation_id} "
                     f"(format={self.output_format})")

    def update(self,
               step: Optional[int] = None,
               message: str = "",
               force: bool = False) -> None:
        """
        Update progress.

        Args:
            step: Current step number (if None, auto-increment)
            message: Status message to display
            force: Force output regardless of time interval
        """
        if not self.enabled:
            return
        
        now = time.time()
        should_update = force or (now - self.last_update_time) >= self.update_interval
        
        if not should_update:
            return
        
        if step is not None:
            self.current_step = step
        else:
            self.current_step += 1
        
        self.current_message = message
        self.last_update_time = now
        
        # Output if message changed or forced
        if force or message != self.last_message:
            self._output_progress()
            self.last_message = message

    def complete(self, message: str = "Complete") -> None:
        """Mark operation as complete."""
        if not self.enabled:
            return
        
        if self.total_steps and self.current_step < self.total_steps:
            self.current_step = self.total_steps
        
        self.current_message = message
        self._output_progress(status="complete", final=True)

    def error(self, message: str = "Error") -> None:
        """Report an error."""
        if not self.enabled:
            return
        
        self.current_message = message
        self._output_progress(status="error", final=True)

    def _output_progress(self, status: str = "running", final: bool = False) -> None:
        """Output progress in configured format."""
        elapsed = time.time() - self.start_time
        
        if self.output_format == "json":
            output = self._format_json(status, elapsed, final)
        elif self.output_format == "structured":
            output = self._format_structured(status, elapsed, final)
        else:  # simple
            output = self._format_simple(status, elapsed, final)
        
        # Output to stderr so stdout remains clean
        print(output, file=sys.stderr, flush=True)

    def _format_simple(self, status: str, elapsed: float, final: bool) -> str:
        """Simple format: [op] step/total: message (time)"""
        step_str = f"{self.current_step}/{self.total_steps}" if self.total_steps else f"{self.current_step}"
        time_str = self._format_time(elapsed)
        return f"[{self.operation_id}] {step_str}: {self.current_message} ({time_str})"

    def _format_json(self, status: str, elapsed: float, final: bool) -> str:
        """JSON output with all metrics."""
        data = {
            "timestamp": datetime.utcnow().isoformat(),
            "operation": self.operation_id,
            "status": status,
            "step": self.current_step,
            "total_steps": self.total_steps,
            "message": self.current_message,
            "elapsed_seconds": round(elapsed, 2),
            "final": final,
        }
        
        if self.total_steps and self.total_steps > 0:
            data["progress_percent"] = round(100.0 * self.current_step / self.total_steps, 1)
        
        return json.dumps(data, separators=(',', ':'))

    def _format_structured(self, status: str, elapsed: float, final: bool) -> str:
        """Structured format: key=value | key=value"""
        time_str = self._format_time(elapsed)
        step_str = f"{self.current_step}/{self.total_steps}" if self.total_steps else f"{self.current_step}"
        
        parts = [
            f"op={self.operation_id}",
            f"status={status}",
            f"step={step_str}",
            f"msg={self.current_message}",
            f"time={time_str}",
        ]
        
        if self.total_steps and self.total_steps > 0:
            percent = round(100.0 * self.current_step / self.total_steps, 1)
            parts.append(f"pct={percent}%")
        
        return " | ".join(parts)

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds as human-readable time."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}m{secs}s"
        else:
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            return f"{hours}h{mins}m"


class ProgressContext:

    def __init__(self, title):
        self._title = title
        self._progress = get_event_handler().get("progress")

    def __enter__(self):
        if self._progress:
            self._progress.update(text=self._title, percent=0)
            # start an indefinite pulse (until we receive more details)
            self._progress.update()
        else:
            self._progress = None
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self._progress:
            self._progress.finish()

    def update(self, *args, **kwargs):
        if not self._progress:
            return False
        mainloop = get_mainloop()
        if mainloop is not None:
            mainloop.update()
        return self._progress.update(*args, **kwargs)

    def set_multiple(self, count, base_text=None):
        if self._progress:
            self._progress.set_multiple(count, base_text=base_text)

    def update_multiple(self):
        if self._progress:
            self._progress.update_multiple()
