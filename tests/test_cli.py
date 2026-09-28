"""Offline tests for the unattended / json-mode contract.

No network: every HTTP call goes to FakeSession. Run with `pytest`.
"""
import json

import pytest
from click.testing import CliRunner

from snow import snow as cli
from snow.util import login, output


SSO_URL = "https://iam.auckland.ac.nz/profile/SAML2/Redirect/SSO?execution=e1s1"
AUTH_REDIRECT = (login.BASE_URL + "auth_redirect.do?sysparm_url="
                 "https%3A%2F%2Fsso.example%2Fstart")
SAML_FORM = (
    '<form><input name="RelayState" value="https://uoaprod.service-now.com/navpage.do">'
    '<input name="SAMLResponse" value="xyz"></form>'
)


class FakeResponse:
    def __init__(self, url="", text="", status_code=200, payload=None):
        self.url = url
        self.text = text if payload is None else json.dumps(payload)
        self.content = self.text.encode()
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            return json.loads(self.text)
        return self._payload


class FakeSession:
    """Routes (method, url-substring) -> FakeResponse; first match wins."""

    def __init__(self, routes):
        self.routes = routes
        self.headers = {}
        self.hooks = {"response": []}
        self.calls = []

    def _handle(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        for m, needle, resp in self.routes:
            if m == method and needle in url:
                r = resp(url, kwargs) if callable(resp) else resp
                if not r.url:
                    r.url = url
                for hook in self.hooks.get("response", []):
                    hook(r)
                return r
        raise AssertionError("unexpected %s %s" % (method, url))

    def get(self, url, **kw):
        return self._handle("GET", url, **kw)

    def post(self, url, data=None, **kw):
        return self._handle("POST", url, data=data, **kw)

    def patch(self, url, **kw):
        return self._handle("PATCH", url, **kw)


def runner():
    try:
        return CliRunner(mix_stderr=False)  # click < 8.2
    except TypeError:
        return CliRunner()  # click >= 8.2 always separates stderr


@pytest.fixture(autouse=True)
def no_real_io(monkeypatch, tmp_path):
    monkeypatch.setattr(login, "session_cache_path", str(tmp_path / "session_cache"))
    monkeypatch.setenv("SNOW_USERNAME", "user")
    monkeypatch.setenv("SNOW_PWD", "pw")
    monkeypatch.delenv("SNOW_NON_INTERACTIVE", raising=False)

    def no_input(*a, **k):
        raise AssertionError("input() must not be called")

    monkeypatch.setattr(login, "input", no_input)
    # FakeSession routes may hold lambdas; the cache contents are not under test.
    monkeypatch.setattr(login.pickle, "dump", lambda obj, f: None)


def use_session(monkeypatch, session):
    monkeypatch.setattr(login, "_load_session", lambda: session)


def login_routes(after_password):
    return [
        ("GET", login.BASE_URL, FakeResponse(url=AUTH_REDIRECT)),
        ("GET", "sso.example", FakeResponse(url=SSO_URL)),
        ("POST", "iam.auckland.ac.nz", after_password),
        ("POST", "navpage.do", FakeResponse(text="var g_ck = 'tok123';")),
    ]


# --- login() -------------------------------------------------------------

def test_login_non_interactive_2fa_raises_without_prompting(monkeypatch):
    use_session(monkeypatch, FakeSession(login_routes(
        FakeResponse(text='<input name="j_token">'))))
    with pytest.raises(login.LoginRequired) as e:
        login.login(interactive=False)
    assert e.value.reason == "2fa_required"


def test_login_interactive_prompts_on_stderr(monkeypatch, capsys):
    token_page = FakeResponse(text='<input name="j_token">')
    posts = iter([token_page, FakeResponse(text=SAML_FORM)])
    sess = FakeSession(login_routes(lambda url, kw: next(posts)))
    use_session(monkeypatch, sess)
    monkeypatch.setattr(login, "input", lambda *a: "123456")
    s = login.login(interactive=True)
    assert s.headers["X-UserToken"] == "tok123"
    out, err = capsys.readouterr()
    assert out == ""
    assert "Please enter your 2FA token" in err
    assert "Navigated to" in err and "Entered username and password" in err


def test_login_invalid_credentials(monkeypatch):
    use_session(monkeypatch, FakeSession(login_routes(
        FakeResponse(text=login.INCORRECT_CREDENTIAL_STRING))))
    with pytest.raises(login.LoginRequired) as e:
        login.login(interactive=False)
    assert e.value.reason == "invalid_credentials"


def test_config_missing_is_login_required_and_import_error():
    assert issubclass(login.ConfigMissing, login.LoginRequired)
    assert issubclass(login.ConfigMissing, ImportError)


def test_corrupt_session_cache_starts_fresh(tmp_path, monkeypatch):
    p = tmp_path / "bad"
    p.write_bytes(b"not a pickle")
    monkeypatch.setattr(login, "session_cache_path", str(p))
    s = login._load_session()
    assert isinstance(s.get_adapter("https://x"), login.TLSAdapter)


def test_adapter_applies_default_timeout(monkeypatch):
    seen = {}

    def fake_send(self, request, **kwargs):
        seen.update(kwargs)
        return "resp"

    monkeypatch.setattr(login.adapters.HTTPAdapter, "send", fake_send)
    monkeypatch.setenv("SNOW_TIMEOUT", "7")
    assert login.TLSAdapter().send(object()) == "resp"
    assert seen["timeout"] == 7.0


def test_401_hook_raises_session_expired():
    with pytest.raises(login.LoginRequired) as e:
        login.raise_on_unauthenticated(
            FakeResponse(url=login.BASE_URL + "api/now/table/task", status_code=401))
    assert e.value.reason == "session_expired"


# --- CLI -----------------------------------------------------------------

def test_help_does_not_log_in(monkeypatch):
    monkeypatch.setattr(login, "login", lambda **k: pytest.fail("logged in"))
    for cmd in ["comment", "show", "my_work", "resolve"]:
        r = runner().invoke(cli.snow, [cmd, "--help"])
        assert r.exit_code == 0, r.output


@pytest.mark.parametrize("argv", [
    ["-f", "json", "my_work"],
    ["-f", "json", "show", "INC1"],
    ["-f", "json", "comment", "INC1", "-m", "hi"],
])
def test_json_login_required_exit_3(monkeypatch, argv):
    use_session(monkeypatch, FakeSession(login_routes(
        FakeResponse(text='<input name="j_token">'))))
    r = runner().invoke(cli.snow, argv)
    assert r.exit_code == output.EXIT_LOGIN_REQUIRED
    doc = json.loads(r.stdout)
    assert doc["error"] == "login_required"
    assert doc["reason"] == "2fa_required"
    assert doc["message"]
    assert "Navigated to" in r.stderr


def test_non_interactive_flag_and_env(monkeypatch):
    seen = []

    def fake_login(interactive=True):
        seen.append(interactive)
        raise login.LoginRequired("2fa_required", "x")

    monkeypatch.setattr(login, "login", fake_login)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True, raising=False)
    runner().invoke(cli.snow, ["--non-interactive", "my_work"])
    monkeypatch.setenv("SNOW_NON_INTERACTIVE", "1")
    runner().invoke(cli.snow, ["my_work"])
    assert seen == [False, False]


def test_text_login_required_goes_to_stderr(monkeypatch):
    monkeypatch.setattr(login, "login", lambda **k: (_ for _ in ()).throw(
        login.LoginRequired("invalid_credentials", "bad creds")))
    r = runner().invoke(cli.snow, ["my_work"])
    assert r.exit_code == 3
    assert r.stdout == ""
    assert "bad creds" in r.stderr


def logged_in_session(extra_routes):
    # Fresh login without 2FA prompt (rememberMe cookie) - progress lines
    # must land on stderr, not in the JSON on stdout.
    return FakeSession(extra_routes + login_routes(FakeResponse(text=SAML_FORM)))


def test_json_stdout_is_pure_json_after_login(monkeypatch):
    tasks = [{"number": "INC1", "state": "New"}]
    use_session(monkeypatch, logged_in_session([
        ("GET", "/api/now/table/task", FakeResponse(payload={"result": tasks})),
    ]))
    r = runner().invoke(cli.snow, ["-f", "json", "my_work"])
    assert r.exit_code == 0
    assert json.loads(r.stdout) == tasks
    assert "Navigated to" in r.stderr


def test_comment_with_message_json_success(monkeypatch):
    sess = logged_in_session([
        ("GET", "/api/now/table/task", FakeResponse(payload={
            "result": [{"sys_id": "abc", "sys_class_name": "incident"}]})),
        ("PATCH", "/api/now/table/task/abc", FakeResponse(status_code=204)),
    ])
    use_session(monkeypatch, sess)
    r = runner().invoke(cli.snow, ["-f", "json", "comment", "INC1", "-m", "hello"])
    assert r.exit_code == 0, r.stderr
    assert json.loads(r.stdout) == {
        "ok": True, "ticket_number": "INC1", "field": "comments",
        "table": "task", "status": "success"}
    assert sess.calls[-1][2]["json"] == {"comments": "hello"}


def test_resolve_uses_child_table(monkeypatch):
    sess = logged_in_session([
        ("GET", "/api/now/table/task", FakeResponse(payload={
            "result": [{"sys_id": "abc", "sys_class_name": "sc_task"}]})),
        ("PATCH", "/api/now/table/sc_task/abc", FakeResponse(status_code=204)),
    ])
    use_session(monkeypatch, sess)
    r = runner().invoke(cli.snow, ["-f", "json", "resolve", "SCTASK1", "-m", "done"])
    assert r.exit_code == 0
    assert json.loads(r.stdout)["table"] == "sc_task"


def test_message_from_stdin_still_works(monkeypatch):
    sess = logged_in_session([
        ("GET", "/api/now/table/task", FakeResponse(payload={
            "result": [{"sys_id": "abc", "sys_class_name": "incident"}]})),
        ("PATCH", "/api/now/table/task/abc", FakeResponse(status_code=204)),
    ])
    use_session(monkeypatch, sess)
    r = runner().invoke(cli.snow, ["worknotes", "INC1"], input="from stdin")
    assert r.exit_code == 0
    assert r.stdout.strip() == "Success"
    assert sess.calls[-1][2]["json"] == {"work_notes": "from stdin"}


def test_update_rejected_json(monkeypatch):
    use_session(monkeypatch, logged_in_session([
        ("GET", "/api/now/table/task", FakeResponse(payload={
            "result": [{"sys_id": "abc", "sys_class_name": "incident"}]})),
        ("PATCH", "/api/now/table/task/abc", FakeResponse(status_code=403, payload={
            "error": {"message": "ACL Exception", "detail": "nope"}})),
    ]))
    r = runner().invoke(cli.snow, ["-f", "json", "comment", "INC1", "-m", "x"])
    assert r.exit_code == 1
    doc = json.loads(r.stdout)
    assert doc["error"] == "update_failed" and doc["message"] == "ACL Exception"
    assert doc["ok"] is False and doc["http_status"] == 403


@pytest.mark.parametrize("argv", [
    ["-f", "json", "show", "INC404"],
    ["-f", "json", "get_ticket_status", "INC404"],
    ["-f", "json", "get_user_comments", "INC404"],
    ["-f", "json", "extract_yaml", "INC404"],
    ["-f", "json", "comment", "INC404", "-m", "x"],
])
def test_ticket_not_found_json(monkeypatch, argv):
    use_session(monkeypatch, logged_in_session([
        ("GET", "/api/now/table/task", FakeResponse(payload={"result": []})),
    ]))
    r = runner().invoke(cli.snow, argv)
    assert r.exit_code == 1
    doc = json.loads(r.stdout)  # exactly one document
    assert doc["error"] == "ticket_not_found"
    assert doc["message"] == "Ticket not found"


def test_empty_message_json(monkeypatch):
    use_session(monkeypatch, logged_in_session([]))
    r = runner().invoke(cli.snow, ["-f", "json", "comment", "INC1"], input="")
    assert r.exit_code == 1
    assert json.loads(r.stdout)["error"] == "no_message"


def test_api_401_is_login_required(monkeypatch):
    use_session(monkeypatch, FakeSession([
        ("GET", "/api/now/table/task", FakeResponse(status_code=401, payload={
            "error": {"message": "User Not Authenticated"}})),
        ("GET", login.BASE_URL, FakeResponse(url=login.BASE_URL + "navpage.do")),
    ]))
    r = runner().invoke(cli.snow, ["-f", "json", "my_groups_work"])
    assert r.exit_code == 3
    assert json.loads(r.stdout)["reason"] == "session_expired"


def test_unexpected_error_json(monkeypatch):
    use_session(monkeypatch, logged_in_session([
        ("GET", "/api/now/table/task", FakeResponse(text="<html>not json</html>")),
    ]))
    r = runner().invoke(cli.snow, ["-f", "json", "my_work"])
    assert r.exit_code == 1
    assert json.loads(r.stdout)["error"] == "unexpected_error"


def test_usage_error_json(monkeypatch):
    r = runner().invoke(cli.snow, ["-f", "json", "show"])
    assert r.exit_code == 2
    assert json.loads(r.stdout)["error"] == "usage_error"
