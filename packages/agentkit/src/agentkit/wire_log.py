"""One JSON line per cross-service request received or call made.

Every service writes the same fields, so `run_id` and `request_id` follow one request
across all logs. Latency is measured by whoever made the call.
"""

import json
import sys
from datetime import UTC, datetime
from typing import Any, TextIO

FIELDS = (
    "ts",
    "service",
    "run_id",
    "request_id",
    "step",
    "direction",
    "endpoint_or_tool",
    "status",
    "latency_ms",
    "attempt",
    "tokens",
)


def log_line(out: TextIO | None = None, **fields: Any) -> dict[str, Any]:
    """Write and return one line. Only the contract's fields are kept, so a token or
    header passed by mistake never reaches the log."""
    line = {name: fields.get(name) for name in FIELDS}
    line["ts"] = line["ts"] or datetime.now(UTC).isoformat(timespec="milliseconds")
    print(json.dumps(line, default=str), file=out or sys.stdout, flush=True)
    return line
