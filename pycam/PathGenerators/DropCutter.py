"""
Copyright 2010-2011 Lars Kruse <devel@sumpfralle.de>
Copyright 2008-2009 Lode Leroy

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

import os
import time

import pycam.Geometry.Model
from pycam.PathGenerators import get_max_height_dynamic
from pycam.Toolpath.Steps import MoveStraight, MoveSafety
from pycam.Utils import ProgressCounter
from pycam.Utils.threading import run_in_parallel
import pycam.Utils.log

log = pycam.Utils.log.get_logger()


# We need to use a global function here - otherwise it does not work with
# the multiprocessing Pool.
def _process_one_grid_line(extra_args):
    """ This function assumes, that the positions are next to each other.
    Otherwise the dynamic over-sampling (in get_max_height_dynamic) is
    pointless.
    """
    positions, minz, maxz, model, cutter, max_depth = extra_args
    return get_max_height_dynamic(model, cutter, positions, minz, maxz, max_depth=max_depth)


class DropCutter:

    def generate_toolpath(self, cutter, models, motion_grid, minz=None, maxz=None,
                          draw_callback=None):
        # Dynamic fill max_depth: default=5 (GUI), set to 2 for headless CNC via env var
        # to prevent point explosion with dense grids (step <1mm).  max_depth=2 allows
        # up to 4x intermediate points; max_depth=5 allows up to 32x.
        try:
            dynamic_fill_max_depth = int(os.environ.get("PYCAM_DYNAMIC_FILL_MAX_DEPTH", "2"))
        except (ValueError, TypeError):
            dynamic_fill_max_depth = 2
        
        path = []
        quit_requested = False
        model = pycam.Geometry.Model.get_combined_model(models)

        # Transfer the grid (a generator) into a list of lists and count the
        # items.
        lines = []
        # usually there is only one layer - but an xy-grid consists of two
        for layer in motion_grid:
            for line in layer:
                lines.append(line)

        num_of_lines = len(lines)
        progress_counter = ProgressCounter(len(lines), draw_callback)
        current_line = 0

        # Diagnostic: report grid size so worker logs can explain slow progress.
        # Use print(stderr) not log.warning() — PyCAM's logging system may not
        # have a handler configured for stderr in headless mode, but the worker's
        # progress monitor reads stderr directly.
        import sys as _sys
        if lines:
            avg_positions = sum(len(line) for line in lines) / len(lines)
            print("DropCutter: %d grid lines, ~%d positions/line, max_depth=%d (before dynamic fill)"
                  % (num_of_lines, int(avg_positions), dynamic_fill_max_depth), file=_sys.stderr, flush=True)
        else:
            print("DropCutter: 0 grid lines — nothing to process", file=_sys.stderr, flush=True)

        args = []
        for one_grid_line in lines:
            # simplify the data (useful for remote processing)
            xy_coords = [(pos[0], pos[1]) for pos in one_grid_line]
            args.append((xy_coords, minz, maxz, model, cutter, dynamic_fill_max_depth))
        
        # Disable multiprocessing when draw_callback exists (progress reporting needed).
        # Multiprocessing workers can't invoke callbacks during execution, so progress
        # only updates after ALL lines complete (defeats the purpose). Serial execution
        # allows callback after each line for smooth progress: 5% → 6% → 7% ... → 100%.
        disable_parallel = draw_callback is not None
        
        _line_start_time = time.monotonic()
        for points in run_in_parallel(_process_one_grid_line, args,
                                      callback=progress_counter.update,
                                      disable_multiprocessing=disable_parallel):
            if draw_callback and draw_callback(
                    text="DropCutter: processing line %d/%d" % (current_line + 1, num_of_lines)):
                # cancel requested
                quit_requested = True
                break
            for point in points:
                if point is None:
                    # exceeded maxz - the cutter has to skip this point
                    path.append(MoveSafety())
                else:
                    path.append(MoveStraight(point))
                # The progress counter may return True, if cancel was requested.
                if draw_callback and draw_callback(tool_position=point, toolpath=path):
                    quit_requested = True
                    break
            # add a move to safety height after each line of moves
            path.append(MoveSafety())
            progress_counter.increment()
            current_line += 1
            
            # Emit progress percentage after each line completes
            # ProgressCounter.increment() doesn't pass percent to callback, so we do it manually
            if draw_callback and num_of_lines > 0:
                percent = 100.0 * current_line / num_of_lines
                draw_callback(percent=percent)
            
            # Diagnostic: log line completion timing
            _line_elapsed = time.monotonic() - _line_start_time
            print("DropCutter: line %d/%d done in %.1fs (%.1f%% complete)"
                  % (current_line, num_of_lines, _line_elapsed, 
                     100.0 * current_line / num_of_lines if num_of_lines > 0 else 0),
                  file=_sys.stderr, flush=True)
            _line_start_time = time.monotonic()
            
            if quit_requested:
                break
        return path
