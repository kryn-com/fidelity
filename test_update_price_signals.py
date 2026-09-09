import requests

from scripts.update_price_signals import classify_price_signal_error


def test_classify_price_signal_error_marks_unsupported_finnhub_response():
    response = requests.Response()
    response.status_code = 403
    response._content = b'{"error":"unsupported symbol"}'
    exc = requests.HTTPError("403 Client Error", response=response)

    assert classify_price_signal_error(exc) == "finnhub_unsupported"


def test_classify_price_signal_error_keeps_generic_exceptions_as_raw_error():
    exc = ValueError("temporary network failure")

    assert classify_price_signal_error(exc) == "temporary network failure"
