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
import pycam.workspace.data_models
from pycam.Utils.progress import HeadlessProgressTracker


_log = pycam.Utils.log.get_logger()

LOG_LEVELS = {"debug": logging.DEBUG,
              "info": logging.INFO,
              "warning": logging.WARNING,
              "error": logging.ERROR, }


def get_args():
    parser = argparse.ArgumentParser(prog="PyCAM", description="scriptable PyCAM processing flow",
                                     epilog="PyCAM website: https://github.com/SebKuzminsky/pycam")
    parser.add_argument("--log-level", choices=LOG_LEVELS.keys(), default="warning",
                        help="choose the verbosity of log messages")
    parser.add_argument("sources", metavar="FLOW_SPEC", type=argparse.FileType('r'), nargs="+",
                        help="processing flow description files in yaml format")
    parser.add_argument("--version", action="version", version="%(prog)s {}".format(VERSION))
    return parser.parse_args()


def main_func():
    args = get_args()
    _log.setLevel(LOG_LEVELS[args.log_level])
    
    # Initialize headless progress tracking (if enabled via env var)
    progress = HeadlessProgressTracker(
        operation_id="pycam_flow",
        total_steps=len(args.sources) + 1,  # +1 for export phase
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
    exports = list(pycam.workspace.data_models.Export.get_collection())
    if exports:
        progress.update(step=len(args.sources) + 1, message=f"Running {len(exports)} export(s)", force=True)
        for export in exports:
            try:
                export.run_export()
            except Exception as exc:
                progress.error(f"Export failed: {exc}")
                raise
    
    progress.complete("PyCAM flow completed successfully")


if __name__ == "__main__":
    main_func()
