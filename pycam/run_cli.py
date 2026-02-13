#!/usr/bin/env python3
"""

Copyright 2017 Lars Kruse <devel@sumpfralle.de>

This file is part of PyCAM.

PyCAM is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

PyCAM is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with PyCAM.  If not, see <http://www.gnu.org/licenses/>.
"""

import argparse
import logging
import os
import re
import sys

try:
    from pycam import VERSION
except ImportError:
    # running locally (without a proper PYTHONPATH) requires manual intervention
    sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                     os.pardir)))
    from pycam import VERSION

import pycam.errors
from pycam.Flow.parser import parse_yaml
import pycam.Utils
import pycam.Utils.log
from pycam.Utils.cli_progress import CLIProgress
from pycam.Utils.events import get_event_handler
import pycam.workspace.data_models
from pycam.Utils.progress import HeadlessProgressTracker


_log = pycam.Utils.log.get_logger()


class HeadlessProgressBridge:
    """Bridge internal PathGenerator progress callbacks to HeadlessProgressTracker.

    When registered as the ``"progress"`` event handler, this class receives
    ``update(text=..., percent=...)`` calls from ProgressContext (which wraps
    the draw_callback used by PushCutter, ContourFollow, DropCutter, etc.).

    PyCAM's ProgressCounter in each PathGenerator already computes a fine-grained
    ``percent`` based on individual triangles / grid lines processed.  We use
    that directly for smooth progress, and parse the ``text`` for layer info
    to include as human-readable context in the status message.

    The JSON output consumed by worker.py therefore contains:
      - ``progress_percent``: smooth 0-100 from triangle/grid-line level
      - ``message``: "Export 1/1: layer 3/10 (45%)" for display
    """

    _LAYER_RE = re.compile(r"processing (?:layer|line)\s+(\d+)/(\d+)", re.IGNORECASE)

    def __init__(self, tracker, export_step, total_exports=1, current_export_idx=0):
        """
        Args:
            tracker: HeadlessProgressTracker instance
            export_step: The step number for the export phase
            total_exports: Total number of exports in this run
            current_export_idx: Zero-based index of the current export
        """
        self._tracker = tracker
        self._export_step = export_step
        self._total_exports = max(1, total_exports)
        self._current_export_idx = current_export_idx
        self._last_layer_text = ""  # Cache layer info from text= calls

    def update(self, text=None, percent=None, **_kwargs):
        """Called by ProgressContext.update() with path-generator status text.

        PathGenerators call draw_callback in two patterns:
          1) text="PushCutter: processing layer 3/10"  (layer-level, no percent)
          2) percent=45.2  (fine-grained from ProgressCounter, no text)

        We cache the layer info from (1) and use the percent from (2) to
        build a combined message with smooth progress.  The percent from
        ProgressCounter is the single source of truth for numeric progress;
        the layer text is only used in the human-readable status message.
        """
        # Cache layer/line text when available
        if text:
            m = self._LAYER_RE.search(text)
            if m:
                current_layer = int(m.group(1))
                total_layers = int(m.group(2))
                self._last_layer_text = "layer %d/%d" % (current_layer, total_layers)

        # Use the fine-grained percent from ProgressCounter (triangle/grid-line level)
        if percent is not None:
            # Scale this export's percent into the overall multi-export range
            export_frac = (self._current_export_idx + percent / 100.0) / self._total_exports
            # Build message with layer context if available
            export_label = "Export %d/%d" % (self._current_export_idx + 1, self._total_exports)
            if self._last_layer_text:
                msg = "%s: %s" % (export_label, self._last_layer_text)
            else:
                msg = "%s: processing" % export_label
            self._tracker.update(
                step=self._export_step,
                message=msg,
                sub_progress=export_frac,
                force=False,  # Respect throttle interval — ProgressCounter fires often
            )
        return False  # Never request cancellation

    def finish(self):
        """No-op — HeadlessProgressTracker.complete() handles finalization."""
        pass

    def set_multiple(self, count, base_text=None):
        """No-op — not used in headless mode."""
        pass

    def update_multiple(self):
        """No-op — not used in headless mode."""
        pass

LOG_LEVELS = {"debug": logging.DEBUG,
              "info": logging.INFO,
              "warning": logging.WARNING,
              "error": logging.ERROR, }


def get_args():
    parser = argparse.ArgumentParser(prog="PyCAM", description="scriptable PyCAM processing flow",
                                     epilog="PyCAM website: https://github.com/SebKuzminsky/pycam")
    parser.add_argument("--log-level", choices=LOG_LEVELS.keys(), default="warning",
                        help="choose the verbosity of log messages")
    progress_group = parser.add_mutually_exclusive_group()
    progress_group.add_argument("--progress", action="store_true",
                                help="enable textual progress output to stderr")
    progress_group.add_argument("--json-progress", action="store_true",
                                help="emit progress updates as JSON to stdout")
    parser.add_argument("sources", metavar="FLOW_SPEC", type=argparse.FileType('r'), nargs="+",
                        help="processing flow description files in yaml format")
    parser.add_argument("--version", action="version", version="%(prog)s {}".format(VERSION))
    return parser.parse_args()


def _install_dual_progress(cli_handler, bridge):
    """Register a wrapper that forwards to both the CLI progress handler and
    the headless bridge.  This keeps ``--progress`` / ``--json-progress``
    output working alongside the headless layer-progress tracking."""

    class _DualProgress:
        def update(self, text=None, percent=None, **kwargs):
            bridge.update(text=text, percent=percent, **kwargs)
            return cli_handler.update(text=text, percent=percent, **kwargs)

        def finish(self):
            bridge.finish()
            cli_handler.finish()

        def set_multiple(self, count, base_text=None):
            bridge.set_multiple(count, base_text=base_text)
            cli_handler.set_multiple(count, base_text=base_text)

        def update_multiple(self):
            bridge.update_multiple()
            cli_handler.update_multiple()

    get_event_handler().set("progress", _DualProgress())


def main_func():
    args = get_args()
    _log.setLevel(LOG_LEVELS[args.log_level])
    # --- CLI-flag progress (interactive / piped use) ---
    if args.progress or args.json_progress:
        progress_stream = sys.stdout if args.json_progress else sys.stderr
        get_event_handler().set(
            "progress", CLIProgress(json_output=args.json_progress, stream=progress_stream))

    # --- Env-var headless progress (service / worker use) ---
    # total_steps: N (parse per source) + 1 (export phase)
    # complete() is called separately and forces 100%.
    progress = HeadlessProgressTracker(
        operation_id="pycam_flow",
        total_steps=len(args.sources) + 1,  # parse + export phase
    )
    progress.update(step=0, message="Initializing PyCAM flow", force=True)

    # Phase 1: Parse all YAML flow specifications
    for i, fname in enumerate(args.sources, start=1):
        try:
            progress.update(step=i, message=f"Parsing {fname.name if hasattr(fname, 'name') else 'flow'}")
            parse_yaml(fname)
        except pycam.errors.PycamBaseException as exc:
            progress.error(f"Flow parse failed: {exc}")
            print("Flow description parse failure ({}): {}".format(fname, exc), file=sys.stderr)
            sys.exit(1)
    
    pycam.Utils.set_application_key("pycam-cli")
    
    # Phase 2: Run all exports
    # The export phase is the heavy one (toolpath generation) so we set
    # the progress message to include export count for client visibility.
    exports = list(pycam.workspace.data_models.Export.get_collection())
    export_step = len(args.sources) + 1
    # Save the existing CLI progress handler (if any) so we can restore
    # it after installing the headless bridge.
    cli_progress = get_event_handler().get("progress")
    if exports:
        progress.update(
            step=export_step,
            message=f"Generating toolpaths ({len(exports)} export(s))...",
            force=True,
        )
        for idx, export in enumerate(exports, start=1):
            try:
                progress.update(
                    step=export_step,
                    message=f"Export {idx}/{len(exports)}: generating toolpath",
                    sub_progress=0.0,
                    force=True,
                )
                # Install bridge so path generators' layer progress
                # flows through to HeadlessProgressTracker.  If the
                # user also requested --progress / --json-progress we
                # wrap the CLI handler so both outputs stay active.
                bridge = HeadlessProgressBridge(
                    progress, export_step,
                    total_exports=len(exports),
                    current_export_idx=idx - 1,
                )
                if cli_progress is not None:
                    # Wrap: forward to both bridge and CLI handler
                    _install_dual_progress(cli_progress, bridge)
                else:
                    get_event_handler().set("progress", bridge)
                export.run_export()
                progress.update(
                    step=export_step,
                    message=f"Export {idx}/{len(exports)}: complete",
                    force=True,
                )
            except Exception as exc:
                progress.error(f"Export {idx} failed: {exc}")
                raise
    # Restore original progress handler
    get_event_handler().set("progress", cli_progress)
    
    progress.complete("PyCAM flow completed successfully")


if __name__ == "__main__":
    main_func()
