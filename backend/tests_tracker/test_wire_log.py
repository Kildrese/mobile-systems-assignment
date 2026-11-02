import io
import json

from agentkit.wire_log import FIELDS, log_line


def test_only_contract_fields_are_written():
    out = io.StringIO()
    log_line(out, service="verifier", authorization="Bearer s3cret", token="s3cret", status=200)
    line = json.loads(out.getvalue())
    assert set(line) == set(FIELDS)
    assert "s3cret" not in out.getvalue()
    assert line["status"] == 200 and line["ts"]
