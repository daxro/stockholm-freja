import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from stockholm_freja import (
    FrejaError,
    FrejaHttpError,
    FrejaInputError,
    FrejaRedirectError,
    FrejaRejectedError,
    FrejaTimeoutError,
    freja_login,
)

FREJA_URL = (
    "https://login003.stockholm.se/NECSadcfreja/authenticate/NECSadcfreja"
    "?TYPE=33554433&REALMOID=06-abc&TARGET=-SM-https%3a%2f%2fexample.com"
)
PERSONNUMMER = "198703274954"


def _response(text="APPROVED", status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.raise_for_status.return_value = None
    return resp


def _session(statuses):
    session = MagicMock()
    session.post.return_value = _response("")
    session.get.side_effect = [_response(json.dumps({"status": status})) for status in statuses]
    return session


def test_approved_after_polling():
    session = _session(["STARTED", "DELIVERED_TO_MOBILE", "APPROVED"])

    freja_login(session, FREJA_URL, PERSONNUMMER, poll_interval=0)

    assert session.post.call_count == 1
    assert session.get.call_count == 3


def test_init_request_strips_query_and_posts_personnummer_with_ajax_headers():
    session = _session(["APPROVED"])

    freja_login(session, FREJA_URL, PERSONNUMMER, poll_interval=0)

    assert session.post.call_args.args[0] == (
        "https://login003.stockholm.se/NECSadcfreja/authenticate/NECSadcfreja"
        "?action=init&userInput=198703274954"
    )
    assert session.post.call_args.kwargs["allow_redirects"] is False
    assert session.post.call_args.kwargs["timeout"] == 30
    assert session.post.call_args.kwargs["headers"] == {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "*/*",
        "Referer": "https://login003.stockholm.se/NECSadcfreja/authenticate/NECSadcfreja",
    }


def test_poll_request_keeps_query_and_uses_base_referer():
    session = _session(["APPROVED"])

    freja_login(session, FREJA_URL, PERSONNUMMER, poll_interval=0)

    assert session.get.call_args.args[0] == f"{FREJA_URL}&action=checkstatus"
    assert session.get.call_args.kwargs["allow_redirects"] is False
    assert session.get.call_args.kwargs["timeout"] == 30
    assert session.get.call_args.kwargs["headers"] == {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "*/*",
        "Referer": FREJA_URL,
    }


def test_on_started_runs_after_init_before_polling():
    session = _session(["APPROVED"])
    events = []

    freja_login(
        session,
        FREJA_URL,
        PERSONNUMMER,
        poll_interval=0,
        on_started=lambda: events.append((session.post.call_count, session.get.call_count)),
    )

    assert events == [(1, 0)]


@pytest.mark.parametrize("bad_personnummer", ["8703274954", "19870327-4954", "abc", "", None])
def test_rejects_invalid_personnummer_before_network(bad_personnummer):
    session = MagicMock()

    with pytest.raises(FrejaInputError):
        freja_login(session, FREJA_URL, bad_personnummer)

    session.post.assert_not_called()
    session.get.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "http://login003.stockholm.se/NECSadcfreja/authenticate/NECSadcfreja",
        "https://evil.example/NECSadcfreja/authenticate/NECSadcfreja",
        "https://user:secret@login003.stockholm.se/NECSadcfreja/authenticate/NECSadcfreja",
        "https://login003.stockholm.se:444/NECSadcfreja/authenticate/NECSadcfreja",
        "https://login003.stockholm.se/NECSadcfrejaevil/authenticate",
        "https://login001.stockholm.se/NECSadc/frejaevil/start",
        "https://login003.stockholm.se/NECSadcfreja/../collect",
        "https://login003.stockholm.se/NECSadcfreja/%2e%2e/collect",
    ],
)
def test_rejects_bad_freja_urls_before_network(url):
    session = MagicMock()

    with pytest.raises(FrejaInputError):
        freja_login(session, url, PERSONNUMMER)

    session.post.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "https://login001.stockholm.se/NECSadc/freja/b64startpage.jsp?startpage=x",
        "https://login003.stockholm.se:443/NECSadcfreja/authenticate/NECSadcfreja",
    ],
)
def test_accepts_allowed_freja_urls(url):
    session = _session(["APPROVED"])

    freja_login(session, url, PERSONNUMMER, poll_interval=0)

    session.post.assert_called_once()


def test_poll_request_strips_fragment_before_network_but_keeps_query_referer():
    session = _session(["APPROVED"])
    url = f"{FREJA_URL}#local-fragment"

    freja_login(session, url, PERSONNUMMER, poll_interval=0)

    assert session.get.call_args.args[0] == f"{FREJA_URL}&action=checkstatus"
    assert session.get.call_args.kwargs["headers"]["Referer"] == FREJA_URL


def test_init_redirect_is_rejected_without_secrets():
    session = MagicMock()
    session.post.return_value = _response("", status_code=302)

    with pytest.raises(FrejaRedirectError) as excinfo:
        freja_login(session, FREJA_URL, PERSONNUMMER, poll_interval=0)

    message = str(excinfo.value)
    assert "198703274954" not in message
    assert "TARGET" not in message
    session.get.assert_not_called()


def test_poll_redirect_is_rejected_without_secrets():
    session = _session(["APPROVED"])
    session.get.side_effect = [_response("", status_code=302)]

    with pytest.raises(FrejaRedirectError) as excinfo:
        freja_login(session, FREJA_URL, PERSONNUMMER, poll_interval=0)

    message = str(excinfo.value)
    assert "198703274954" not in message
    assert "TARGET" not in message


def test_http_failure_is_sanitized():
    session = MagicMock()
    resp = _response("body with 198703274954", status_code=500)
    resp.raise_for_status.side_effect = requests.HTTPError("raw secret", response=resp)
    session.post.return_value = resp

    with pytest.raises(FrejaHttpError) as excinfo:
        freja_login(session, FREJA_URL, PERSONNUMMER, poll_interval=0)

    message = str(excinfo.value)
    assert "HTTP status 500" in message
    assert "198703274954" not in message
    assert "raw secret" not in message
    assert "TARGET" not in message
    assert excinfo.value.status_code == 500


def test_transport_exception_is_sanitized():
    session = MagicMock()
    session.post.side_effect = requests.Timeout(
        "timed out for https://login003.stockholm.se/auth?action=init&userInput=198703274954"
    )

    with pytest.raises(FrejaHttpError) as excinfo:
        freja_login(session, FREJA_URL, PERSONNUMMER, poll_interval=0)

    message = str(excinfo.value)
    assert "Freja init request failed." == message
    assert "198703274954" not in message
    assert "userInput" not in message


@pytest.mark.parametrize("status", ["CANCELED", "REJECTED"])
def test_rejected_statuses(status):
    with pytest.raises(FrejaRejectedError):
        freja_login(_session([status]), FREJA_URL, PERSONNUMMER, poll_interval=0)


@pytest.mark.parametrize("status", ["EXPIRED", "TIMEOUT"])
def test_timeout_statuses(status):
    with pytest.raises(FrejaTimeoutError):
        freja_login(_session([status]), FREJA_URL, PERSONNUMMER, poll_interval=0)


@pytest.mark.parametrize("status", ["ERROR", "RP_CANCELED"])
def test_failure_statuses(status):
    with pytest.raises(FrejaError):
        freja_login(_session([status]), FREJA_URL, PERSONNUMMER, poll_interval=0)


def test_plain_text_status_response():
    session = MagicMock()
    session.post.return_value = _response("")
    session.get.return_value = _response("APPROVED")

    freja_login(session, FREJA_URL, PERSONNUMMER, poll_interval=0)


def test_unknown_status_keeps_polling():
    session = _session(["UNKNOWN", "STARTED", "APPROVED"])

    freja_login(session, FREJA_URL, PERSONNUMMER, poll_interval=0)

    assert session.get.call_count == 3


@patch("stockholm_freja.freja.time")
def test_timeout_raises_after_max_wait(mock_time):
    elapsed = [0.0]

    def fake_monotonic():
        val = elapsed[0]
        elapsed[0] += 3.0
        return val

    mock_time.monotonic = fake_monotonic
    mock_time.sleep = MagicMock()
    session = _session(["STARTED"])
    session.get.return_value = _response(json.dumps({"status": "STARTED"}))

    with pytest.raises(FrejaTimeoutError, match="timed out"):
        freja_login(session, FREJA_URL, PERSONNUMMER, timeout=5.0)
