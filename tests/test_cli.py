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


def test_comment_awaiting_customer_sctask_sets_state_in_same_update(monkeypatch):
    sess = logged_in_session([
        ("GET", "/api/now/table/task", FakeResponse(payload={
            "result": [{"sys_id": "abc", "sys_class_name": "sc_task"}]})),
        ("PATCH", "/api/now/table/sc_task/abc", FakeResponse(status_code=204)),
    ])
    use_session(monkeypatch, sess)
    r = runner().invoke(cli.snow, ["-f", "json", "comment", "SCTASK1",
                                   "--awaiting-customer"], input="hello\nthere")
    assert r.exit_code == 0, r.stderr
    assert json.loads(r.stdout) == {
        "ok": True, "ticket_number": "SCTASK1", "field": "comments",
        "table": "sc_task", "status": "success", "state": "Awaiting Customer"}
    patches = [c for c in sess.calls if c[0] == "PATCH"]
    assert len(patches) == 1
    assert patches[0][2]["json"] == {"comments": "hello\nthere",
                                     "state": "Awaiting Customer"}


@pytest.mark.parametrize("table", ["incident", "sc_req_item"])
def test_comment_awaiting_customer_other_types_keep_state(monkeypatch, table):
    sess = logged_in_session([
        ("GET", "/api/now/table/task", FakeResponse(payload={
            "result": [{"sys_id": "abc", "sys_class_name": table}]})),
        ("PATCH", "/api/now/table/task/abc", FakeResponse(status_code=204)),
    ])
    use_session(monkeypatch, sess)
    r = runner().invoke(cli.snow, ["-f", "json", "comment", "INC1", "-m", "hi",
                                   "--awaiting-customer"])
    assert r.exit_code == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["state"] is None and out["table"] == "task"
    assert sess.calls[-1][2]["json"] == {"comments": "hi"}


def test_comment_awaiting_customer_text_mode(monkeypatch):
    sess = logged_in_session([
        ("GET", "/api/now/table/task", FakeResponse(payload={
            "result": [{"sys_id": "abc", "sys_class_name": "incident"}]})),
        ("PATCH", "/api/now/table/task/abc", FakeResponse(status_code=204)),
    ])
    use_session(monkeypatch, sess)
    r = runner().invoke(cli.snow, ["comment", "INC1", "-m", "hi", "--awaiting-customer"])
    assert r.exit_code == 0
    assert r.stdout.strip() == "Success"
    assert "State not changed" in r.stderr


def test_comment_awaiting_customer_empty_message_writes_nothing(monkeypatch):
    sess = logged_in_session([])
    use_session(monkeypatch, sess)
    r = runner().invoke(cli.snow, ["-f", "json", "--non-interactive", "comment",
                                   "SCTASK1", "--awaiting-customer", "-m", ""])
    assert r.exit_code == 1
    assert json.loads(r.stdout)["error"] == "no_message"
    assert not [c for c in sess.calls if c[0] == "PATCH"]


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


# --- assign_to_me / add_to_watchlist / queue -----------------------------

ME = {"sys_id": "me1", "user_name": "jdoe001", "name": "Jane Doe", "email": "j.doe@example.org"}


def ref(value, display):
    return {"value": value, "display_value": display}


def ticket_record(assigned_to=None, watch_list="", table="incident"):
    return {
        "sys_id": ref("abc", "abc"),
        "sys_class_name": ref(table, table.title()),
        "assigned_to": assigned_to or ref("", ""),
        "watch_list": ref(watch_list, watch_list),
    }


def assign_session(record, patch_status=204, user_result=None):
    return logged_in_session([
        ("GET", "/api/now/table/sys_user", FakeResponse(payload={
            "result": [ME] if user_result is None else user_result})),
        ("GET", "/api/now/table/task", FakeResponse(payload={
            "result": [record] if record else []})),
        ("PATCH", "/api/now/table/", FakeResponse(
            status_code=patch_status,
            payload=None if patch_status == 204 else {"error": {"message": "ACL Exception"}})),
    ])


def api_calls(sess):
    return [(m, u, kw) for m, u, kw in sess.calls if "/api/now/" in u]


@pytest.mark.parametrize("flag", [[], ["--if-unassigned"]])
def test_assign_to_me_unassigned_json(monkeypatch, flag):
    sess = assign_session(ticket_record())
    use_session(monkeypatch, sess)
    r = runner().invoke(cli.snow, ["-f", "json", "assign_to_me", "INC1"] + flag)
    assert r.exit_code == 0, r.stdout + r.stderr
    assert json.loads(r.stdout) == {
        "ok": True, "ticket_number": "INC1", "assigned_to": "Jane Doe", "already_mine": False}
    assert "Navigated to" in r.stderr and "Navigated to" not in r.stdout
    calls = api_calls(sess)
    # who am I, then the ticket read immediately followed by the PATCH
    assert [m for m, _, _ in calls] == ["GET", "GET", "PATCH"]
    assert "/sys_user" in calls[0][1]
    assert "/table/task" in calls[1][1]
    assert "assigned_to" in calls[1][2]["params"]["sysparm_fields"]
    assert calls[2][1].endswith("/api/now/table/incident/abc")
    assert calls[2][2]["json"] == {"assigned_to": "me1"}


def test_assign_to_me_if_unassigned_race_lost(monkeypatch):
    sess = assign_session(ticket_record(assigned_to=ref("other9", "Bob Smith")))
    use_session(monkeypatch, sess)
    r = runner().invoke(cli.snow, ["-f", "json", "assign_to_me", "INC1", "--if-unassigned"])
    assert r.exit_code == 1
    doc = json.loads(r.stdout)
    assert doc["error"] == "already_assigned"
    assert doc["assigned_to"] == "Bob Smith"
    assert doc["ok"] is False and doc["ticket_number"] == "INC1"
    assert doc["message"]
    assert not [c for c in sess.calls if c[0] == "PATCH"]


def test_assign_to_me_without_flag_takes_over(monkeypatch):
    sess = assign_session(ticket_record(assigned_to=ref("other9", "Bob Smith")))
    use_session(monkeypatch, sess)
    r = runner().invoke(cli.snow, ["-f", "json", "assign_to_me", "INC1"])
    assert r.exit_code == 0
    assert json.loads(r.stdout)["already_mine"] is False
    assert sess.calls[-1][2]["json"] == {"assigned_to": "me1"}


@pytest.mark.parametrize("flag", [[], ["--if-unassigned"]])
def test_assign_to_me_already_mine(monkeypatch, flag):
    sess = assign_session(ticket_record(assigned_to=ref("me1", "Jane Doe")))
    use_session(monkeypatch, sess)
    r = runner().invoke(cli.snow, ["-f", "json", "assign_to_me", "INC1"] + flag)
    assert r.exit_code == 0
    assert json.loads(r.stdout) == {
        "ok": True, "ticket_number": "INC1", "assigned_to": "Jane Doe", "already_mine": True}
    assert not [c for c in sess.calls if c[0] == "PATCH"]


def test_assign_to_me_text(monkeypatch):
    use_session(monkeypatch, assign_session(ticket_record(table="sc_task")))
    r = runner().invoke(cli.snow, ["assign_to_me", "SCTASK1"])
    assert r.exit_code == 0
    assert r.stdout.strip() == "Assigned SCTASK1 to Jane Doe"
    assert "Navigated to" in r.stderr


def test_assign_to_me_text_race_lost(monkeypatch):
    use_session(monkeypatch, assign_session(ticket_record(assigned_to=ref("o", "Bob Smith"))))
    r = runner().invoke(cli.snow, ["assign_to_me", "INC1", "--if-unassigned"])
    assert r.exit_code == 1
    assert "already assigned to Bob Smith" in r.stdout


def test_assign_to_me_not_found_and_rejected(monkeypatch):
    use_session(monkeypatch, assign_session(None))
    r = runner().invoke(cli.snow, ["-f", "json", "assign_to_me", "INC404"])
    assert r.exit_code == 1
    assert json.loads(r.stdout)["error"] == "ticket_not_found"

    use_session(monkeypatch, assign_session(ticket_record(), patch_status=403))
    r = runner().invoke(cli.snow, ["-f", "json", "assign_to_me", "INC1"])
    assert r.exit_code == 1
    doc = json.loads(r.stdout)
    assert doc["error"] == "update_failed" and doc["http_status"] == 403
    assert doc["table"] == "incident"


def test_add_to_watchlist_appends(monkeypatch):
    sess = assign_session(ticket_record(watch_list="w1,w2"))
    use_session(monkeypatch, sess)
    r = runner().invoke(cli.snow, ["-f", "json", "add_to_watchlist", "INC1", "--user", "jdoe001"])
    assert r.exit_code == 0, r.stdout + r.stderr
    assert json.loads(r.stdout) == {
        "ok": True, "ticket_number": "INC1", "watch_list_on": "INC1", "user": "jdoe001",
        "user_sys_id": "me1", "already_watching": False}
    calls = api_calls(sess)
    assert calls[0][2]["params"]["sysparm_query"] == "user_name=jdoe001"
    assert calls[-1][0] == "PATCH"
    assert calls[-1][1].endswith("/api/now/table/incident/abc")
    assert calls[-1][2]["json"] == {"watch_list": "w1,w2,me1"}


def test_add_to_watchlist_by_email_empty_list(monkeypatch):
    sess = assign_session(ticket_record(watch_list=""))
    use_session(monkeypatch, sess)
    r = runner().invoke(cli.snow, ["-f", "json", "add_to_watchlist", "INC1",
                                   "--user", "j.doe@example.org"])
    assert r.exit_code == 0
    assert api_calls(sess)[0][2]["params"]["sysparm_query"] == "email=j.doe@example.org"
    assert sess.calls[-1][2]["json"] == {"watch_list": "me1"}


def test_add_to_watchlist_idempotent(monkeypatch):
    sess = assign_session(ticket_record(watch_list="w1,me1"))
    use_session(monkeypatch, sess)
    r = runner().invoke(cli.snow, ["-f", "json", "add_to_watchlist", "INC1", "-u", "jdoe001"])
    assert r.exit_code == 0
    assert json.loads(r.stdout)["already_watching"] is True
    assert not [c for c in sess.calls if c[0] == "PATCH"]

    r = runner().invoke(cli.snow, ["add_to_watchlist", "INC1", "-u", "jdoe001"])
    assert r.exit_code == 0
    assert r.stdout.strip() == "jdoe001 is already watching INC1"


@pytest.mark.parametrize("user", ["nobody", "a^ORuser_nameSTARTSWITHa"])
def test_add_to_watchlist_user_not_found(monkeypatch, user):
    sess = assign_session(ticket_record(), user_result=[])
    use_session(monkeypatch, sess)
    r = runner().invoke(cli.snow, ["-f", "json", "add_to_watchlist", "INC1", "-u", user])
    assert r.exit_code == 1
    doc = json.loads(r.stdout)
    assert doc["error"] == "user_not_found" and doc["user"] == user and doc["message"]
    assert not [c for c in sess.calls if c[0] == "PATCH"]


def test_add_to_watchlist_text(monkeypatch):
    use_session(monkeypatch, assign_session(ticket_record()))
    r = runner().invoke(cli.snow, ["add_to_watchlist", "INC1", "-u", "jdoe001"])
    assert r.exit_code == 0
    assert r.stdout.strip() == "Added jdoe001 to the watch list of INC1"


def catalog_task_session(task, ritm):
    """A catalog task and its RITM, both read from the task table by number."""
    def ticket(url, kwargs):
        query = kwargs["params"]["sysparm_query"]
        return FakeResponse(payload={"result": [ritm if query == "number=RITM1" else task]})
    return logged_in_session([
        ("GET", "/api/now/table/sys_user", FakeResponse(payload={"result": [ME]})),
        ("GET", "/api/now/table/task", ticket),
        ("PATCH", "/api/now/table/", FakeResponse(status_code=204)),
    ])


def catalog_task(parent="RITM1", watch_list=""):
    record = ticket_record(watch_list=watch_list, table="sc_task")
    record["parent"] = ref("ritm9" if parent else "", parent)
    return record


def test_add_to_watchlist_catalog_task_goes_on_its_ritm(monkeypatch):
    ritm = ticket_record(watch_list="w1", table="sc_req_item")
    ritm["sys_id"] = ref("ritm9", "ritm9")
    sess = catalog_task_session(catalog_task(), ritm)
    use_session(monkeypatch, sess)
    r = runner().invoke(cli.snow, ["-f", "json", "add_to_watchlist", "SCTASK1", "-u", "jdoe001"])
    assert r.exit_code == 0, r.stdout + r.stderr
    assert json.loads(r.stdout) == {
        "ok": True, "ticket_number": "SCTASK1", "watch_list_on": "RITM1", "user": "jdoe001",
        "user_sys_id": "me1", "already_watching": False}
    calls = api_calls(sess)
    assert "parent" in calls[1][2]["params"]["sysparm_fields"]
    assert calls[2][2]["params"]["sysparm_query"] == "number=RITM1"
    assert [c for c in calls if c[0] == "PATCH"] == [calls[-1]]
    assert calls[-1][1].endswith("/api/now/table/sc_req_item/ritm9")
    assert calls[-1][2]["json"] == {"watch_list": "w1,me1"}

    use_session(monkeypatch, catalog_task_session(catalog_task(), ritm))
    r = runner().invoke(cli.snow, ["add_to_watchlist", "SCTASK1", "-u", "jdoe001"])
    assert r.stdout.strip() == \
        "Added jdoe001 to the watch list of RITM1 (the request item of SCTASK1)"


def test_add_to_watchlist_catalog_task_already_on_ritm(monkeypatch):
    # Watching the task itself does not count: the RITM's list is the one read.
    ritm = ticket_record(watch_list="me1", table="sc_req_item")
    sess = catalog_task_session(catalog_task(watch_list=""), ritm)
    use_session(monkeypatch, sess)
    r = runner().invoke(cli.snow, ["-f", "json", "add_to_watchlist", "SCTASK1", "-u", "jdoe001"])
    doc = json.loads(r.stdout)
    assert doc["already_watching"] is True and doc["watch_list_on"] == "RITM1"
    assert not [c for c in sess.calls if c[0] == "PATCH"]


def test_add_to_watchlist_catalog_task_without_parent(monkeypatch):
    sess = catalog_task_session(catalog_task(parent=""), None)
    use_session(monkeypatch, sess)
    r = runner().invoke(cli.snow, ["-f", "json", "add_to_watchlist", "SCTASK1", "-u", "jdoe001"])
    assert r.exit_code == 0
    assert json.loads(r.stdout)["watch_list_on"] == "SCTASK1"
    assert sess.calls[-1][1].endswith("/api/now/table/sc_task/abc")
    assert sess.calls[-1][2]["json"] == {"watch_list": "me1"}


def test_add_to_watchlist_requires_user(monkeypatch):
    r = runner().invoke(cli.snow, ["-f", "json", "add_to_watchlist", "INC1"])
    assert r.exit_code == 2
    assert json.loads(r.stdout)["error"] == "usage_error"


def queue_record(number, sys_id, assigned_to):
    return {
        "number": ref(number, number),
        "short_description": ref("desc", "desc"),
        "state": ref("1", "New"),
        "priority": ref("4", "4 - Low"),
        "opened_at": ref("2026-09-01 00:00:00", "01/09/2026 12:00:00"),
        "sys_updated_on": ref("2026-09-02 00:00:00", "02/09/2026 12:00:00"),
        "assigned_to": assigned_to or ref("", ""),
        "assignment_group": ref("g1", "CeR"),
        "sys_class_name": ref("sc_task", "Catalog Task"),
        "sys_id": ref(sys_id, sys_id),
    }


def queue_session():
    def tasks(url, kw):
        q = kw["params"]["sysparm_query"]
        if "getMyGroups()" in q:
            assert "assigned_toISEMPTY" in q and "active=true" in q
            result = [queue_record("SCTASK2", "s2", None)]
        else:
            assert "assigned_to=javascript:getMyAssignments()" in q
            result = [queue_record("INC1", "s1", ref("me1", "Jane Doe"))]
        return FakeResponse(payload={"result": result})
    return logged_in_session([("GET", "/api/now/table/task", tasks)])


def test_queue_json(monkeypatch):
    use_session(monkeypatch, queue_session())
    r = runner().invoke(cli.snow, ["-f", "json", "queue"])
    assert r.exit_code == 0, r.stdout + r.stderr
    items = json.loads(r.stdout)
    assert [(i["number"], i["queue"]) for i in items] == [("SCTASK2", "unassigned"), ("INC1", "mine")]
    assert items[0]["assigned_to"] is None
    assert items[1]["assigned_to"] == "Jane Doe"
    assert items[0]["sys_class_name"] == "sc_task"
    assert items[0]["sys_updated_on"] == "02/09/2026 12:00:00"
    for key in ["number", "short_description", "state", "priority", "opened_at",
                "sys_updated_on", "assigned_to", "assignment_group", "sys_class_name",
                "sys_id", "queue"]:
        assert key in items[0]
    assert "Navigated to" in r.stderr


def test_queue_text(monkeypatch):
    use_session(monkeypatch, queue_session())
    r = runner().invoke(cli.snow, ["queue"])
    assert r.exit_code == 0
    lines = r.stdout.splitlines()
    assert lines[0].split()[:2] == ["queue", "number"]
    assert any(l.startswith("unassigned") and "SCTASK2" in l for l in lines)
    assert any(l.startswith("mine") and "INC1" in l for l in lines)
    assert "Navigated to" not in r.stdout


def test_queue_api_error(monkeypatch):
    use_session(monkeypatch, logged_in_session([
        ("GET", "/api/now/table/task", FakeResponse(payload={"error": {"message": "bad"}})),
    ]))
    r = runner().invoke(cli.snow, ["-f", "json", "queue"])
    assert r.exit_code == 1
    assert json.loads(r.stdout) == {"error": "api_error", "message": "bad"}


def test_my_work_json_requests_sys_updated_on(monkeypatch):
    sess = logged_in_session([
        ("GET", "/api/now/table/task", FakeResponse(payload={"result": []})),
    ])
    use_session(monkeypatch, sess)
    for cmd in ["my_work", "my_groups_work"]:
        r = runner().invoke(cli.snow, ["-f", "json", cmd])
        assert r.exit_code == 0
        fields = api_calls(sess)[-1][2]["params"]["sysparm_fields"].split(",")
        assert "sys_updated_on" in fields
        assert len(fields) == len(set(fields))  # the field list does not grow per call

