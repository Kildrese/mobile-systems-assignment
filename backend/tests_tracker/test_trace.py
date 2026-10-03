"""trace-log: JSONL events, truncation and redaction."""

from tests_tracker.conftest import MODEL_KEY, read_trace
from tracker.trace import MAX_FIELD_CHARS, Trace


def test_events_are_written_and_flushed(tmp_path):
    path = tmp_path / "traces" / "run.jsonl"
    trace = Trace(path, "run-1")
    trace.event(
        "model",
        step=1,
        tool="m",
        args={"a": 1},
        status="ok",
        latency_ms=3.2,
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
    )
    # Readable before close: an interrupted run still leaves its trace.
    (event,) = read_trace(path)
    assert event["kind"] == "model"
    assert event["run_id"] == "run-1"
    for key in ("ts", "step", "tool", "args", "status", "latency_ms", "total_tokens"):
        assert key in event
    trace.summary(outcome="complete", steps=1)
    assert read_trace(path)[-1]["kind"] == "summary"
    trace.close()


def test_long_fields_are_truncated(tmp_path):
    path = tmp_path / "t.jsonl"
    trace = Trace(path, "r")
    trace.event("tool", args={"query": "x" * 5000}, result="y" * 3000, status="ok")
    (event,) = read_trace(path)
    assert len(event["args"]) == MAX_FIELD_CHARS + 1
    assert event["args_len"] > 5000
    assert event["result_len"] == 3000


def test_secrets_never_reach_the_file(tmp_path):
    path = tmp_path / "t.jsonl"
    trace = Trace(path, "r", [MODEL_KEY])
    trace.event(
        "model",
        args={"echo": f"Bearer {MODEL_KEY}"},
        Authorization=f"Bearer {MODEL_KEY}",
        detail=f"key {MODEL_KEY} rejected",
    )
    text = path.read_text()
    assert MODEL_KEY not in text
    assert "[REDACTED]" in text
    assert "Authorization" not in text


def test_null_trace_writes_nothing(tmp_path):
    Trace(None, "r").event("tool", status="ok")
    assert list(tmp_path.iterdir()) == []
