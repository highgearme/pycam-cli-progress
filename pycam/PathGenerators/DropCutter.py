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

import json
import os
import sys
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
    positions, minz, maxz, model, cutter, max_depth, num_positions, line_index, num_lines = extra_args
    return get_max_height_dynamic(model, cutter, positions, minz, maxz, max_depth=max_depth,
                                  num_positions=num_positions, line_index=line_index,
                                  num_lines=num_lines)


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

        args = []
        for idx, one_grid_line in enumerate(lines):
            # simplify the data (useful for remote processing)
            xy_coords = [(pos[0], pos[1]) for pos in one_grid_line]
            args.append((xy_coords, minz, maxz, model, cutter, dynamic_fill_max_depth,
                         len(xy_coords), idx, num_of_lines))
        _start_time = time.monotonic()
        print("DropCutter: %d grid lines, max_depth=%d"
              % (num_of_lines, dynamic_fill_max_depth), file=sys.stderr, flush=True)
        for points in run_in_parallel(_process_one_grid_line, args,
                                      callback=progress_counter.increment):
            if draw_callback and draw_callback(
                    text="DropCutter: processing line %d/%d" % (current_line + 1, num_of_lines)):
                # cancel requested
                quit_requested = True
                break
            # Build toolpath from computed points (83-98%)
            _num_pts = len(points)
            _bt_last_emit = 0
            for _pi, point in enumerate(points):
                if point is None:
                    # exceeded maxz - the cutter has to skip this point
                    path.append(MoveSafety())
                else:
                    path.append(MoveStraight(point))
                _bt_now = time.monotonic()
                if _num_pts > 0 and (_bt_now - _bt_last_emit) >= 2.0:
                    _bt_last_emit = _bt_now
                    _bt_pct = 83.0 + 15.0 * (_pi + 1) / _num_pts
                    print(json.dumps({
                        "operation": "dropcutter",
                        "status": "running",
                        "progress_percent": int(_bt_pct),
                        "message": "Building toolpath (%d / %d points)" % (_pi + 1, _num_pts),
                        "elapsed_seconds": round(_bt_now - _start_time, 1),
                        "final": False,
                    }), file=sys.stderr, flush=True)
                # The progress counter may return True, if cancel was requested.
                if draw_callback and draw_callback(tool_position=point, toolpath=path):
                    quit_requested = True
                    break
            # add a move to safety height after each line of moves
            path.append(MoveSafety())
            current_line += 1

            # Emit per-line progress (only useful when there are multiple lines)
            if num_of_lines > 1:
                _pct = 50.0 + 50.0 * current_line / num_of_lines
                print(json.dumps({
                    "operation": "dropcutter",
                    "status": "running",
                    "step": 2,
                    "total_steps": 2,
                    "progress_percent": int(_pct),
                    "message": "Processing line %d/%d" % (current_line, num_of_lines),
                    "elapsed_seconds": round(time.monotonic() - _start_time, 1),
                    "final": False,
                }), file=sys.stderr, flush=True)
            
            if quit_requested:
                break
        return path
