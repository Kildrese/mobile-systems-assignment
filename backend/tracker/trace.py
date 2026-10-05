"""Append-only JSONL trace: one event per model call attempt, tool call and run end.

Each line is flushed as it is written, so an interrupted run still leaves its trace.
Long fields are truncated with their original length recorded, and secrets are
removed before anything reaches the file.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

MAX_FIELD_CHARS = 2000
TRUNCATED_FIELDS = ("args", "result")
REDACTED = "[REDACTED]"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class Trace:
    def __init__(self, path: Path | None, run_id: str, secrets: list[str] | None = None) -> None:
        self.path = path
        self.run_id = run_id
        # Longest first, so a secret that contains another is redacted whole.
        self._secrets = sorted({s for s in secrets or [] if s}, key=len, reverse=True)
        self._file: TextIO | None = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._file = path.open("a", encoding="utf-8")

    def event(self, kind: str, **fields: Any) -> dict[str, Any]:
        record: dict[str, Any] = {"ts": _now(), "run_id": self.run_id, "kind": kind}
        for key, value in fields.items():
            if key.lower() == "authorization":
                continue
            if key in TRUNCATED_FIELDS:
                value, length = _truncate(value)
                if length is not None:
                    record[f"{key}_len"] = length
            record[key] = value
        line = json.dumps(record, ensure_ascii=False, default=str)
        for secret in self._secrets:
            line = line.replace(secret, REDACTED)
        if self._file is not None:
            self._file.write(line + "\n")
            self._file.flush()
        return record

    @property
    def fields(self) -> dict[str, Any]:
        """The fields `bind` adds to every event (none on the run's own trace)."""
        return {}

    def bind(self, **fields: Any) -> "BoundTrace":
        """A view that adds `fields` (such as `stage` and `agent`) to every event."""
        return BoundTrace(self, fields)

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None


class BoundTrace(Trace):
    def __init__(self, trace: Trace, fields: dict[str, Any]) -> None:
        self._trace = trace
        self._fields = fields
        self.path = trace.path
        self.run_id = trace.run_id

    @property
    def fields(self) -> dict[str, Any]:
        return self._fields

    def event(self, kind: str, **fields: Any) -> dict[str, Any]:
        return self._trace.event(kind, **{**self._fields, **fields})

    def close(self) -> None:
        pass  # the run's trace owns the file


def _truncate(value: Any) -> tuple[Any, int | None]:
    """Cut a long string, or a structure whose JSON is long, to `MAX_FIELD_CHARS`.

    Returns the value to record and, when it was cut, the original length.
    """
    if isinstance(value, str):
        text = value
    elif isinstance(value, dict | list):
        text = json.dumps(value, ensure_ascii=False, default=str)
    else:
        return value, None
    if len(text) <= MAX_FIELD_CHARS:
        return value, None
    return text[:MAX_FIELD_CHARS] + "…", len(text)
