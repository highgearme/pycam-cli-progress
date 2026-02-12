# Headless Progress Monitoring for PyCAM

PyCAM now provides optional progress monitoring for headless (non-GUI) operations via the CLI. This is useful for job queue systems, service integrations, and automated processing pipelines.

## Overview

The headless progress tracker outputs progress information to **stderr** in multiple formats:
- **simple** - Human-readable single-line format
- **json** - Structured JSON for programmatic parsing
- **structured** - Key=value pairs for log aggregation systems

Progress output is **optional** and controlled by environment variables, so headless operations remain clean by default.

## Quick Start

### Enable progress monitoring (simple format):

```bash
PYCAM_PROGRESS_ENABLED=1 pycam flow.yaml
```

### Enable progress monitoring (JSON format):

```bash
PYCAM_PROGRESS_ENABLED=1 PYCAM_PROGRESS_FORMAT=json pycam flow.yaml
```

Output example:
```json
{"timestamp":"2025-01-23T10:30:45.123456","operation":"pycam_flow","status":"running","step":1,"total_steps":2,"message":"Parsing flow.yaml","elapsed_seconds":0.45,"progress_percent":50.0,"final":false}
```

### Enable progress monitoring (structured format):

```bash
PYCAM_PROGRESS_ENABLED=1 PYCAM_PROGRESS_FORMAT=structured pycam flow.yaml
```

Output example:
```
op=pycam_flow | status=running | step=1/2 | msg=Parsing flow.yaml | time=0.5s | pct=50.0%
```

## Environment Variables

### PYCAM_PROGRESS_ENABLED
- **Default**: `false` (disabled)
- **Values**: `1`, `true`, `yes` (case-insensitive)
- **Purpose**: Enable/disable progress output
- **Example**: `PYCAM_PROGRESS_ENABLED=1`

### PYCAM_PROGRESS_FORMAT
- **Default**: `simple`
- **Values**: `simple`, `json`, `structured`
- **Purpose**: Choose output format for different integrations
- **Examples**:
  - `PYCAM_PROGRESS_FORMAT=json` - For log aggregation systems
  - `PYCAM_PROGRESS_FORMAT=structured` - For service monitoring
  - `PYCAM_PROGRESS_FORMAT=simple` - For humans (default)

### PYCAM_PROGRESS_INTERVAL
- **Default**: `1.0` (seconds)
- **Values**: Float number ≥ 0.1
- **Purpose**: Minimum time between progress updates to avoid spam
- **Example**: `PYCAM_PROGRESS_INTERVAL=0.5`

## Output Formats

### Simple Format
```
[pycam_flow] 1/2: Parsing flow.yaml (0.5s)
[pycam_flow] 2/2: Running 1 export(s) (1.2s)
[pycam_flow] 2/2: PyCAM flow completed successfully (2.3s)
```

**Breakdown**:
- `[operation_id]` - Identifies the operation
- `step/total_steps` - Progress indicator
- `message` - Current status
- `(time)` - Elapsed time in human-readable format

### JSON Format
```json
{
  "timestamp": "2025-01-23T10:30:45.123456",
  "operation": "pycam_flow",
  "status": "running",
  "step": 1,
  "total_steps": 2,
  "message": "Parsing flow.yaml",
  "elapsed_seconds": 0.45,
  "progress_percent": 50.0,
  "final": false
}
```

**Fields**:
- `timestamp` - ISO 8601 UTC timestamp
- `operation` - Operation identifier
- `status` - `running`, `complete`, or `error`
- `step` - Current step number (1-based)
- `total_steps` - Total steps (or `null` if indeterminate)
- `message` - Current status message
- `elapsed_seconds` - Seconds elapsed since start
- `progress_percent` - Percentage complete (only if `total_steps` known)
- `final` - `true` for the final update

### Structured Format
```
op=pycam_flow | status=running | step=1/2 | msg=Parsing flow.yaml | time=0.5s | pct=50.0%
```

**Fields**:
- `op` - Operation identifier
- `status` - `running`, `complete`, or `error`
- `step` - `current/total` or just `current` if indeterminate
- `msg` - Status message
- `time` - Elapsed time in human-readable format
- `pct` - Percentage complete (only if determinable)

## Integration Examples

### systemd Service with JSON logging

```ini
[Service]
Type=oneshot
ExecStart=/usr/bin/pycam /path/to/flow.yaml
Environment="PYCAM_PROGRESS_ENABLED=1"
Environment="PYCAM_PROGRESS_FORMAT=json"
StandardOutput=journal
StandardError=journal
```

Parse JSON from systemd journal:
```bash
journalctl -u pycam.service -o json | jq 'select(.MESSAGE | test("pycam_flow")) | .MESSAGE | fromjson'
```

### Job Queue with Simple Progress

```bash
#!/bin/bash
operation_id="job_$JOB_ID"

export PYCAM_PROGRESS_ENABLED=1
export PYCAM_PROGRESS_FORMAT=simple
export PYCAM_PROGRESS_INTERVAL=0.5

pycam /path/to/flow.yaml 2>&1 | while read line; do
    echo "[$(date)] $line" >> /var/log/pycam-jobs.log
done
```

### Container Monitoring

```dockerfile
FROM pycam-base

ENV PYCAM_PROGRESS_ENABLED=1
ENV PYCAM_PROGRESS_FORMAT=json

RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
```

```bash
#!/bin/bash
# entrypoint.sh
pycam /config/flow.yaml 2>&1 | jq -r '.message' 2>/dev/null || echo "Processing..."
```

## Stdout/Stderr Handling

- **Stdout**: Remains clean for actual PyCAM output (models, exports)
- **Stderr**: Reserved for progress information and log messages

This keeps progress separate from data, allowing:
```bash
# Capture only exported data
pycam flow.yaml 2>/dev/null > output.stl

# Monitor progress in real-time
pycam flow.yaml | cat  # Shows both stderr (progress) and stdout (if any)
```

## Performance Considerations

### Update Interval
- Default `1.0s` minimizes overhead
- Reduce to `0.1s` for fine-grained tracking
- Increase to `5.0s` or more for very long operations

### Format Performance
- **simple**: Minimal overhead (string formatting)
- **json**: Slight overhead (JSON serialization)
- **structured**: Similar to simple
- All formats are negligible compared to actual processing time

### Disabling Progress
Default behavior (disabled) has **zero overhead**—progress tracking code doesn't run.

## Troubleshooting

### Progress not appearing

1. Check if enabled: `echo $PYCAM_PROGRESS_ENABLED`
2. Ensure flag is set: `PYCAM_PROGRESS_ENABLED=1 pycam ...`
3. Check stderr is available: `pycam flow.yaml 2>&1 | cat`

### Wrong format showing

1. Verify environment variable: `echo $PYCAM_PROGRESS_FORMAT`
2. Valid formats: `simple`, `json`, `structured` (case-insensitive)
3. Default is `simple` if not specified

### JSON parsing fails

1. Ensure each line is valid JSON (one per update)
2. Progress outputs to stderr, check for mixed stdout/stderr
3. Use shell redirects to separate: `pycam flow.yaml 2>progress.log 1>output.stl`

## Implementation Details

### HeadlessProgressTracker Class

Located in `pycam/Utils/progress.py`, this provides:

```python
from pycam.Utils.progress import HeadlessProgressTracker

# Create tracker
progress = HeadlessProgressTracker(
    operation_id="my_operation",
    total_steps=10,
    enabled=True  # or auto-detect from env
)

# Update progress
progress.update(step=1, message="Starting", force=False)

# Mark complete
progress.complete("Finished successfully")

# Mark error
progress.error("Something went wrong")
```

### Integration Points

The progress tracker is automatically integrated into:
- `pycam run_cli.py` - CLI flow processing
- Phase 1: YAML parsing (steps 1 to N)
- Phase 2: Export execution (step N+1)

### Programmatic Usage

Services can also use the tracker directly:

```python
from pycam.Utils.progress import HeadlessProgressTracker

# In a worker thread or background job
progress = HeadlessProgressTracker("stl_processing", total_steps=3)
progress.update(1, "Loading STL")
# ... do work ...
progress.update(2, "Optimizing mesh")
# ... do work ...
progress.update(3, "Exporting result")
progress.complete("STL processing finished")
```

## Contributing

To add progress tracking in other PyCAM modules:

```python
from pycam.Utils.progress import HeadlessProgressTracker
import os

# Check if progress should be enabled
if os.environ.get("PYCAM_PROGRESS_ENABLED", "").lower() in ("1", "true", "yes"):
    progress = HeadlessProgressTracker("my_module", total_steps=N)
    progress.update(i, f"Processing step {i}")
```
