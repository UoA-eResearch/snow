#!/usr/bin/env python3
import os
import pickle
import re
import ssl
import sys
import importlib
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup
from requests import adapters
from six.moves import input
from urllib3 import poolmanager

from .output import diag

if os.getenv("SNOW_SESSIONFILE"):
    session_cache_path = os.getenv("SNOW_SESSIONFILE")
else:
    session_cache_path = os.path.join(sys.path[0], "session_cache")

BASE_URL = "https://uoaprod.service-now.com/"
INCORRECT_CREDENTIAL_STRING = "The combination of credentials you have entered is incorrect"
INCORRECT_2FA_STRING = "The token you have entered is not correct"


def _default_timeout():
    """(connect, read) timeout in seconds for every HTTP request.

    Without it a dead or half-open connection (e.g. a stale pickled session
    whose keep-alive socket was dropped) can block forever. Override with
    SNOW_TIMEOUT (seconds).
    """
    try:
        return float(os.getenv("SNOW_TIMEOUT", "60"))
    except ValueError:
        return 60.0


class LoginRequired(Exception):
    """A human has to log in before the tool can continue.

    ``reason`` is one of:
      * ``2fa_required``        - SSO asked for a 2FA token and we may not prompt
      * ``invalid_credentials`` - SSO rejected the username/password
      * ``config_missing``      - no credentials configured
      * ``session_expired``     - ServiceNow answered 401 on an API call
      * ``login_failed``        - the SSO flow ended somewhere unexpected
    """

    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason
        self.message = message


class ConfigMissing(LoginRequired, ImportError):
    """No credentials. Still an ImportError for backwards compatibility."""

    def __init__(self, message):
        LoginRequired.__init__(self, "config_missing", message)


class TLSAdapter(adapters.HTTPAdapter):

    def init_poolmanager(self, connections, maxsize, block=False):
        """Create and initialize the urllib3 PoolManager."""
        ctx = ssl.create_default_context()
        ctx.set_ciphers('DEFAULT@SECLEVEL=1')
        self.poolmanager = poolmanager.PoolManager(
                num_pools=connections,
                maxsize=maxsize,
                block=block,
                ssl_version=ssl.PROTOCOL_TLS,
                ssl_context=ctx)

    def send(self, request, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = _default_timeout()
        return super().send(request, **kwargs)


def _new_session():
    s = requests.Session()
    s.mount('https://', TLSAdapter())
    return s


def _load_session():
    try:
        with open(session_cache_path, 'rb') as f:
            s = pickle.load(f)
    except Exception:
        # Missing, empty, truncated or incompatible cache: start fresh.
        return _new_session()
    if not isinstance(s, requests.Session):
        return _new_session()
    # Always use a fresh adapter (with timeouts) - cookies and headers are
    # what we want from the cache, not old connection pools.
    s.mount('https://', TLSAdapter())
    return s


def _load_config():
    if os.getenv("SNOW_USERNAME") and os.getenv("SNOW_PWD"):
        config = type("Config", (object,), {})
        config.username = os.getenv("SNOW_USERNAME")
        config.password = os.getenv("SNOW_PWD")
        return config
    try:
        from .. import config
        return config
    except ImportError:
        pass
    # Support running from a source checkout where config.py may be
    # at repository root rather than inside the package.
    try:
        return importlib.import_module("config")
    except ImportError as exc:
        raise ConfigMissing(
            "Snow configuration not found. Set SNOW_USERNAME and "
            "SNOW_PWD env vars, or create snow/config.py "
            "(or repo-root config.py) with username/password."
        ) from exc


def _prompt(text):
    # Prompt on stderr so stdout stays clean for results / JSON.
    diag(text, end="")
    return input()


def login(interactive=True):
    """Return an authenticated requests.Session.

    With ``interactive=False`` this never reads from stdin: if a 2FA token
    would be needed it raises LoginRequired instead of prompting.
    """
    # Load a previous session if one exists, otherwise make a new session
    s = _load_session()

    # Make a simple request to see if a login is required
    r = s.get(BASE_URL)

    if "auth_redirect" in r.url:
        config = _load_config()
        # SSO redirection - login
        parsed_url = urlparse(r.url)
        params = parse_qs(parsed_url.query)
        sysparm_url = params['sysparm_url'][0]

        r = s.get(sysparm_url)
        diag("Navigated to " + r.url)
        if r.url.startswith("https://iam.auckland.ac.nz/profile/SAML2/Redirect/SSO"):
            r = s.post(r.url, { "j_username": config.username, "j_password": config.password, "submitted": 0, "_eventId_proceed": "" })
            diag("Entered username and password")
            if INCORRECT_CREDENTIAL_STRING in r.text:
                raise LoginRequired(
                    "invalid_credentials",
                    INCORRECT_CREDENTIAL_STRING + ". Check config.py",
                )
            while "j_token" in r.text:
                if not interactive:
                    raise LoginRequired(
                        "2fa_required",
                        "ServiceNow login needs a 2FA token. Run snow "
                        "interactively in a terminal (e.g. `snow my_work`) "
                        "to log in and refresh the session cache.",
                    )
                two_factor = _prompt("Please enter your 2FA token: ")
                r = s.post(r.url, { "submitted": "", "j_token": two_factor, "rememberMe": "on", "_eventId_proceed": "" })
                if INCORRECT_2FA_STRING in r.text:
                    diag("Incorrect 2FA token, try again: ")
            soup = BeautifulSoup(r.content, 'html.parser')
            # login success, submit form
            form = {}
            form_inputs = soup.find_all("input", attrs = {'name' : True})
            for input_elem in form_inputs:
                form[input_elem['name']] = input_elem.get('value', '')
            if 'RelayState' not in form:
                raise LoginRequired(
                    "login_failed",
                    "SSO login did not complete (no SAML response at "
                    + r.url + ")",
                )
            r = s.post(form['RelayState'], form)
            diag("Navigated to " + r.url)
            match = re.search(r"g_ck = '(\w+)';", r.text)
            if not match:
                raise LoginRequired(
                    "login_failed",
                    "Logged in via SSO but could not find the ServiceNow "
                    "session token at " + r.url,
                )
            s.headers['X-UserToken'] = match.group(1)
            with open(session_cache_path, 'wb') as f:
                pickle.dump(s, f)

    return s


def raise_on_unauthenticated(r, *args, **kwargs):
    """requests response hook: a 401 from the REST API means the cached
    session is no longer valid (expired / revoked)."""
    if r.status_code == 401 and "/api/" in r.url:
        raise LoginRequired(
            "session_expired",
            "ServiceNow rejected the cached session (HTTP 401). Run snow "
            "interactively in a terminal to log in again.",
        )
    return r
