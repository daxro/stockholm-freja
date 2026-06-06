import json
import re
import time
from typing import Callable
from urllib.parse import unquote, urlencode, urlparse, urlunparse

import requests

HTTP_TIMEOUT = 30
ALLOWED_HOSTS = {"login001.stockholm.se", "login003.stockholm.se"}
ALLOWED_PATH_PREFIXES = ("/NECSadc/freja/", "/NECSadcfreja/")


class FrejaError(Exception):
    """Base error for Stockholms stad Freja authentication."""


class FrejaInputError(FrejaError):
    """Invalid local input for Freja authentication."""


class FrejaRejectedError(FrejaError):
    """Freja authentication was rejected."""


class FrejaTimeoutError(FrejaError):
    """Freja authentication timed out or expired."""


class FrejaRedirectError(FrejaError):
    """Freja returned an unexpected redirect."""


class FrejaHttpError(FrejaError):
    """Freja returned an unexpected HTTP status."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def freja_login(
    session: requests.Session,
    freja_url: str,
    personnummer: str,
    *,
    poll_interval: float = 2.0,
    timeout: float = 180.0,
    on_started: Callable[[], None] | None = None,
) -> None:
    pn = validate_personnummer(personnummer)
    parsed = _validate_freja_url(freja_url)
    base_url = _base_url(parsed)
    poll_referer = _url_without_fragment(parsed)

    _init_auth(session, base_url, pn)
    if on_started:
        on_started()
    _poll_until_done(session, parsed, poll_referer, poll_interval, timeout)


def validate_personnummer(personnummer: str) -> str:
    if not isinstance(personnummer, str) or not re.fullmatch(r"[0-9]{12}", personnummer):
        raise FrejaInputError("Personnummer must contain exactly 12 digits.")
    return personnummer


def _validate_freja_url(freja_url: str):
    try:
        parsed = urlparse(freja_url)
        port = parsed.port
    except (TypeError, ValueError):
        raise FrejaInputError("Freja URL is not allowed.") from None

    decoded_path = unquote(parsed.path)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or port not in (None, 443)
        or parsed.username
        or parsed.password
        or ".." in decoded_path.split("/")
        or not decoded_path.startswith(ALLOWED_PATH_PREFIXES)
    ):
        raise FrejaInputError("Freja URL is not allowed.")
    return parsed


def _base_url(parsed) -> str:
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def _url_without_fragment(parsed) -> str:
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, ""))


def _init_auth(session: requests.Session, base_url: str, personnummer: str) -> None:
    init_url = f"{base_url}?{urlencode({'action': 'init', 'userInput': personnummer})}"
    try:
        resp = session.post(
            init_url,
            headers=_ajax_headers(base_url),
            allow_redirects=False,
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException:
        raise FrejaHttpError("Freja init request failed.") from None
    _raise_for_unexpected_response(resp, "Freja init request")


def _poll_until_done(
    session: requests.Session,
    parsed,
    referer: str,
    poll_interval: float,
    timeout: float,
) -> None:
    poll_url = _poll_url(parsed)
    headers = _ajax_headers(referer)
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        time.sleep(poll_interval)
        try:
            resp = session.get(
                poll_url,
                headers=headers,
                allow_redirects=False,
                timeout=HTTP_TIMEOUT,
            )
        except requests.RequestException:
            raise FrejaHttpError("Freja status request failed.") from None
        _raise_for_unexpected_response(resp, "Freja status request")
        status = _parse_status(resp.text)
        if status == "APPROVED":
            return
        if status in ("CANCELED", "REJECTED"):
            raise FrejaRejectedError("Authentication was rejected in Freja.")
        if status in ("EXPIRED", "TIMEOUT"):
            raise FrejaTimeoutError(f"Authentication expired in Freja: {status}.")
        if status in ("ERROR", "RP_CANCELED"):
            raise FrejaError(f"Authentication failed in Freja: {status}.")
    raise FrejaTimeoutError(f"Authentication timed out after {timeout}s.")


def _raise_for_unexpected_response(response, action: str) -> None:
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int) and 300 <= status_code < 400:
        raise FrejaRedirectError(f"{action} returned an unexpected redirect.")
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        status = getattr(getattr(exc, "response", None), "status_code", status_code)
        if isinstance(status, int):
            raise FrejaHttpError(f"{action} failed with HTTP status {status}.", status_code=status) from None
        raise FrejaHttpError(f"{action} failed.") from None


def _poll_url(parsed) -> str:
    query = parsed.query + ("&" if parsed.query else "") + "action=checkstatus"
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, ""))


def _parse_status(text: str) -> str:
    text = text.strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text
    return data.get("status", text) if isinstance(data, dict) else text


def _ajax_headers(referer: str) -> dict[str, str]:
    return {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "*/*",
        "Referer": referer,
    }
