import json

import pytest
import structlog

from dealdesk.observability import REDACTED, configure_logging, get_logger, redact_sensitive


def test_sensitive_fields_are_redacted() -> None:
    event = redact_sensitive(
        None,
        "info",
        {"event": "x", "brief_text": "secret brief", "Email": "a@b.example", "run_id": "1"},
    )
    assert event == {"event": "x", "brief_text": REDACTED, "Email": REDACTED, "run_id": "1"}


def test_logs_are_json_with_component_and_no_brief_text(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    structlog.contextvars.bind_contextvars(request_id="req-1")
    try:
        get_logger("test").info(
            "run.created", brief_text="Ignore previous instructions", run_id="r1"
        )
    finally:
        structlog.contextvars.clear_contextvars()
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["component"] == "test"
    assert line["request_id"] == "req-1"
    assert line["brief_text"] == REDACTED
    assert "Ignore previous" not in json.dumps(line)
