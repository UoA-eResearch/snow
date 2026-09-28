import sys
import editor

from .output import fail, emit_json, EXIT_ERROR


def read_message(ctx, message=None):
    """Work out the text to write.

    Order: explicit ``message`` (``--message``), then piped stdin, then
    $EDITOR when a human is at a terminal. In non-interactive mode the
    editor is never opened.
    """
    if message:
        return message
    if message is not None:
        # Explicit empty --message "" : do not fall back to stdin/editor.
        return ""
    if not sys.stdin.isatty():
        return sys.stdin.read()
    if ctx.get("non_interactive"):
        return ""
    message = editor.edit()
    if isinstance(message, bytes):
        message = message.decode("utf-8")
    return message


def patch(ctx, number, field, message=None):
    BASE_URL = ctx["BASE_URL"]
    s = ctx["s"]
    if ctx.get("api"):
        # Library mode (util/api.py): historical behaviour, no --message.
        if not message:
            if sys.stdin.isatty():
                message = editor.edit()
            else:
                message = sys.stdin.read()
    else:
        message = read_message(ctx, message)
    if isinstance(message, bytes):
        message = message.decode("utf-8")
    if not message or not message.strip():
        msg = "Aborted - no message"
        if ctx.get("api"):
            print(msg)
            return
        return fail(ctx, "no_message", msg, EXIT_ERROR,
                    extra={"ok": False, "ticket_number": number, "field": field})
    query = "number=" + number
    url = BASE_URL + "/api/now/table/task"
    # No sysparm_display_value here: sys_class_name must come back as the raw
    # table name ("sc_task"), not its display label ("Catalog Task"), because
    # it is used in the PATCH URL.
    params = {
        "sysparm_query": query,
        "sysparm_fields": "sys_id,sys_class_name"
    }
    r = s.get(url, params=params)
    r = r.json()
    if 'error' in r:
        error_msg = r["error"]["message"]
        if ctx.get("api"):
            print(error_msg)
            return
        return fail(ctx, "api_error", error_msg, EXIT_ERROR,
                    extra={"ok": False, "ticket_number": number, "field": field})
    if not r['result']:
        msg = "Ticket not found"
        if ctx.get("api"):
            print(msg)
            return
        return fail(ctx, "ticket_not_found", msg, EXIT_ERROR,
                    extra={"ok": False, "ticket_number": number, "field": field})
    ticket = r['result'][0]

    sys_id = ticket["sys_id"]

    if field == "resolve":
        # The closing state depends on the ticket type, so PATCH the child
        # table endpoint: display values are converted against the record's
        # own choice lists.  Patching the base `task` table is broken for
        # state: "Resolved" converts against the base table's list (stored
        # as 6, which has no label on sc_task - shown as "(6)" and not
        # Closed Complete), and it cannot close changes at all ("Update
        # Operation failed", close_code never written).  Verified: a change
        # closes with state "Closed" + close_code "Successful" via
        # /api/now/table/change_request/.
        sys_class_name = ticket.get("sys_class_name")
        if isinstance(sys_class_name, dict):
            sys_class_name = sys_class_name.get("value")
        table = sys_class_name or "task"
        if table == "change_request":
            data = {
                "state": "Closed",
                "close_code": "Successful",
                "close_notes": message
            }
        else:
            data = {
                "state": {
                    "sc_task": "Closed Complete",
                    "sc_req_item": "Closed Complete",
                    "incident": "Resolved",
                }.get(table, "Resolved"),
                "close_notes": message
            }
    else:
        table = "task"
        data = {
            field: message
        }

    url = BASE_URL + "/api/now/table/" + table + "/" + sys_id
    r = s.patch(url, json=data, headers={"X-no-response-body": "true"})

    if r.status_code == 204:
        if ctx.get("api") or ctx["format"] != "json":
            print("Success")
        else:
            emit_json({
                "ok": True,
                "ticket_number": number,
                "field": field,
                "table": table,
                "status": "success",
            })
        return True

    try:
        sn_error = r.json()["error"]
    except Exception:
        sn_error = {"message": "HTTP %d" % r.status_code, "detail": r.text[:500]}
    if ctx.get("api"):
        print(sn_error)
        return False
    if ctx["format"] != "json":
        # Historical text output: the ServiceNow error object.
        print(sn_error)
        sys.exit(EXIT_ERROR)
    message = sn_error.get("message") if isinstance(sn_error, dict) else str(sn_error)
    return fail(ctx, "update_failed", message or "HTTP %d" % r.status_code, EXIT_ERROR,
                extra={
                    "ok": False,
                    "ticket_number": number,
                    "field": field,
                    "table": table,
                    "status": "error",
                    "http_status": r.status_code,
                    "detail": sn_error,
                })
