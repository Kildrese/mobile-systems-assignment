from agentkit.text import normalize, quote_found


def test_entities_and_whitespace():
    page = "Pay: $55&nbsp;/&nbsp;hour\n\n for interns"
    assert quote_found("$55 / hour", page)
    assert quote_found("PAY: $55 / HOUR FOR INTERNS", page)


def test_curly_quotes_and_dashes():
    assert normalize("\u201cSummer 2027\u201d \u2013 NYC") == '"summer 2027" - nyc'


def test_too_short_or_missing():
    assert not quote_found("$5", "pays $5")
    assert not quote_found("$60/hour", "pays $55/hour")
