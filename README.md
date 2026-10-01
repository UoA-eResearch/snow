# snow
A simple command line interface to Service Now, written in Python. Supports SSO / 2FA.

## Installation
Copy config.py.example to config.py and replace with your SSO credentials.  
`sudo pip3 install -r requirements.txt`

## Usage

`./snow.py --help`  
or
`python snow.py --help`  

To show my groups work:
`./snow.py my_groups_work`

Output of `./snow.py --help`

```
Usage: snow [OPTIONS] COMMAND [ARGS]...

Options:
  -d, --debug
  -f, --format TEXT  Output format (text or json)
  --non-interactive  Never prompt (2FA token, $EDITOR). Exit 3 if a login is
                     required. Implied when stdin is not a TTY or
                     SNOW_NON_INTERACTIVE=1.
  --help             Show this message and exit.

Commands:
  add_to_watchlist           Add a user to a ticket's watch list
  assign_to_me               Assign a ticket to yourself
  comment                    Add a comment
  email_check                Check missing emails for the latest comment
  extract_yaml               Write original request to file
  get_ticket_status          Get ticket status
  get_user_comments          Get only msg from users, not automation
  my_groups_work             Show tickets in your groups
  my_work                    Show your tickets
  queue                      Your triage queue: unassigned group tickets...
  resolve                    Resolve a ticket
  set_customer_promise       Set customer promise
  set_third_party_reference  Set third party reference
  show                       Show a ticket
  worknotes                  Add worknotes
  ```

## Driving snow from another program

### JSON mode guarantees (`-f json`)

Global flags go **before** the command: `snow -f json my_work`.

* stdout carries **exactly one JSON document** per invocation, on success and
  on failure. Login progress ("Navigated to ...", "Entered username and
  password"), the 2FA prompt, warnings and tracebacks go to **stderr**.
* Any error is a JSON object with at least `"error"` (a machine-readable code)
  and `"message"` (human-readable text), and the exit code is non-zero.
* `--help` never logs in or touches the network.

Success documents:

| Command | stdout on success |
|---|---|
| `my_work`, `my_groups_work` | array of task records |
| `email_check` | array of `{"ticket_number", "has_comments", "status", ...}` |
| `show NUMBER` | `{"ticket": {...}, "user": {...}}` |
| `get_user_comments NUMBER` | array of `{"name", "date", "comment"}` |
| `get_ticket_status NUMBER` | `{"ticket_number", "property": "state", "value"}` |
| `extract_yaml NUMBER` | `{"ticket_number", "file", "content"}` |
| `comment`, `worknotes`, `resolve`, `set_third_party_reference`, `set_customer_promise` | `{"ok": true, "ticket_number", "field", "table", "status": "success"}` |
| `queue` | array of queue items (see below) |
| `assign_to_me NUMBER [--if-unassigned]` | `{"ok": true, "ticket_number", "assigned_to", "already_mine"}` |
| `add_to_watchlist NUMBER --user USER` | `{"ok": true, "ticket_number", "user", "user_sys_id", "already_watching"}` |

`my_work` / `my_groups_work` records include `sys_updated_on` in json mode.

Error codes (`"error"` value):

| `error` | Exit | Meaning |
|---|---|---|
| `login_required` | 3 | A human must log in. Extra key `"reason"`: `2fa_required`, `invalid_credentials`, `config_missing`, `session_expired` (API returned 401) or `login_failed` |
| `ticket_not_found` | 1 | No task with that number |
| `api_error` | 1 | ServiceNow returned an error for the lookup/query |
| `update_failed` | 1 | ServiceNow rejected a write. Extra keys: `ok: false`, `ticket_number`, `field`, `table`, `status: "error"`, `http_status`, `detail` (ServiceNow's error object). `assign_to_me` / `add_to_watchlist` send `ok`, `ticket_number`, `table`, `http_status`, `detail` |
| `no_message` | 1 | A write command got an empty message |
| `already_assigned` | 1 | `assign_to_me --if-unassigned`: someone else has the ticket; nothing was changed. Extra keys: `ok: false`, `ticket_number`, `assigned_to` (their display name) |
| `user_not_found` | 1 | `add_to_watchlist`: no `sys_user` with that username/email (extra keys `ok: false`, `user`); `assign_to_me`: the logged-in user could not be resolved |
| `user_ambiguous` | 1 | `add_to_watchlist`: more than one `sys_user` matches |
| `general_section_not_found` | 1 | `extract_yaml` found no `General` section |
| `network_error` | 1 | Connection failure or timeout |
| `unexpected_error` | 1 | Anything else (traceback on stderr) |
| `usage_error` | 2 | Bad arguments to a command (click's usage text is also on stderr) |

Errors in the global options themselves (e.g. an unknown global flag) are
reported by click on stderr only, with exit code 2 and no JSON.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Error (see table above) |
| 2 | Usage error |
| 3 | Login required - run `snow` once interactively in a terminal to log in (2FA) and refresh the session cache |

Text mode uses the same exit codes; its output is unchanged except that login
progress messages and the 2FA prompt now go to stderr.

### Non-interactive mode

snow never prompts (no 2FA `input()`, no `$EDITOR`) when any of these holds:

* the global flag `--non-interactive` is given,
* `SNOW_NON_INTERACTIVE=1` (or `true`/`yes`/`on`) is set,
* stdin is not a TTY (piped, `/dev/null`, run from a service).

If a login would then need a 2FA token, or the credentials are rejected, snow
exits immediately with code 3 (json: `{"error": "login_required", "reason":
"...", "message": "..."}`). An expired cached session is detected either by
the SSO redirect on the first request or by a 401 from the REST API; both end
in exit 3 rather than a hang. Every HTTP request has a timeout
(`SNOW_TIMEOUT`, seconds, default 60). A missing or corrupt session cache is
ignored and a fresh login is attempted.

Set `SNOW_SESSIONFILE` to a fixed path so interactive and unattended runs
share the same session cache.

### Triage: `queue`, `assign_to_me`, `add_to_watchlist`

`snow queue` lists your triage view: open tickets in your groups that are
**unassigned** (the `my_groups_work` query) followed by open tickets
**assigned to you** (the `my_work` query). Tickets assigned to other people
are not included. In json mode it prints one array; each item is flat:

```json
{
    "assigned_to": null,
    "assignment_group": "CeR Research Storage",
    "number": "SCTASK0123456",
    "opened_at": "01/09/2026 10:15:00",
    "priority": "4 - Low",
    "queue": "unassigned",
    "short_description": "...",
    "state": "Open",
    "sys_class_name": "sc_task",
    "sys_id": "0123456789abcdef0123456789abcdef",
    "sys_updated_on": "02/09/2026 08:00:00"
}
```

`queue` is `"unassigned"` or `"mine"`. `assigned_to` is the display name or
`null`. `sys_class_name` and `sys_id` are raw values (the table name, e.g.
`sc_task`); the other fields are ServiceNow display values, as in `my_work`.

`snow assign_to_me NUMBER` assigns the ticket to the logged-in user (PATCH on
the ticket's own table, e.g. `incident` or `sc_task`). If it is already yours
nothing is written and `"already_mine": true`. Without a flag it takes the
ticket over from whoever has it. With `--if-unassigned` it reads
`assigned_to` and immediately PATCHes (no other request in between); if
someone else has the ticket nothing changes and it fails with
`already_assigned` (exit 1). The Table API has no conditional update, so a
very small window between that read and the write remains.

`snow add_to_watchlist NUMBER --user USER` adds a user (UPI/username, or an
email address if `USER` contains `@`) to the ticket's watch list. It is
idempotent: if the user is already watching, nothing is written and
`"already_watching": true`. `"user"` in the result is the resolved username.

```bash
snow -f json --non-interactive queue
snow -f json --non-interactive assign_to_me INC1234567 --if-unassigned
snow -f json --non-interactive add_to_watchlist INC1234567 --user abcd123
```

### Messages for write commands

`comment`, `worknotes`, `resolve`, `set_third_party_reference` and
`set_customer_promise` take the text from, in order:

1. `--message/-m TEXT`
2. stdin, when piped: `printf '%s' "text" | snow comment INC1234567`
3. `$EDITOR`, when a human is at a terminal (never in non-interactive mode)

An empty or whitespace-only message aborts with `no_message` (exit 1).

```bash
snow -f json --non-interactive worknotes INC1234567 -m "Checked quota, raised to 2TB"
```

### Tests

```bash
pip install pytest && python -m pytest tests
```

The tests are offline: all HTTP traffic goes to a fake session.
