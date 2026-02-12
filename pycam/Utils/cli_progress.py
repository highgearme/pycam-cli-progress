import json
import sys


class CLIProgress:

    def __init__(self, json_output=False, stream=None, throttle=1):
        self.json_output = json_output
        self.stream = stream or sys.stderr
        self.throttle = max(1, int(throttle or 1))
        self._last_percent = None
        self._count = None
        self._current = 0
        self._base_text = None

    def _should_emit(self, percent):
        if percent is None:
            return True
        if self._last_percent is None:
            return True
        return int(percent) - int(self._last_percent) >= self.throttle

    def _emit(self, text=None, percent=None):
        if self.json_output:
            payload = {"event": "progress"}
            if text is not None:
                payload["text"] = text
            if percent is not None:
                payload["percent"] = percent
            print(json.dumps(payload), file=self.stream, flush=True)
        else:
            parts = []
            if percent is not None:
                parts.append(f"{int(percent)}%")
            if text:
                parts.append(text)
            if not parts:
                return
            print(" ".join(parts), file=self.stream, flush=True)

    def update(self, text=None, percent=None, **_kwargs):
        if percent is not None:
            percent = max(0.0, min(100.0, percent))
        if (text is None) and self._base_text:
            text = self._base_text
        if not self._should_emit(percent):
            return False
        if percent is not None:
            self._last_percent = percent
        self._emit(text=text, percent=percent)
        return True

    def finish(self):
        self._emit(text=self._base_text, percent=100)

    def set_multiple(self, count, base_text=None):
        self._count = count
        self._current = 0
        self._base_text = base_text

    def update_multiple(self):
        if (self._count is None) or (self._count <= 0):
            return
        next_value = self._current + 1
        if next_value > self._count:
            return
        self._current = next_value
        percent = 100 * float(self._current) / float(self._count)
        text = self._base_text
        if text:
            text = "{} ({}/{})".format(text, self._current, self._count)
        self.update(text=text, percent=percent)
