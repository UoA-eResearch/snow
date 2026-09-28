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
  comment                    Add a comment
  email_check                Check missing emails for the latest comment
  extract_yaml               Write original request to file
  get_ticket_status          Get ticket status
  get_user_comments          Get only msg from users, not automation
  my_groups_work             Show tickets in your groups
  my_work                    Show your tickets
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

Error codes (`"error"` value):

| `error` | Exit | Meaning |
|---|---|---|
| `login_required` | 3 | A human must log in. Extra key `"reason"`: `2fa_required`, `invalid_credentials`, `config_missing`, `session_expired` (API returned 401) or `login_failed` |
| `ticket_not_found` | 1 | No task with that number |
| `api_error` | 1 | ServiceNow returned an error for the lookup/query |
| `update_failed` | 1 | ServiceNow rejected a write. Extra keys: `ok: false`, `ticket_number`, `field`, `table`, `status: "error"`, `http_status`, `detail` (ServiceNow's error object) |
| `no_message` | 1 | A write command got an empty message |
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
