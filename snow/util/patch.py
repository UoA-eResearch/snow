import sys
import editor

from .output import fail, emit_json, diag, EXIT_ERROR


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


# The "Awaiting Customer" state label per ticket table.  ServiceNow at UoA
# only emails a customer-visible comment to the requester when the same
# update moves the ticket to Awaiting Customer.  Only tables whose choice
# list is known to have that label are listed: a label that is not in the
# record's choice list would be stored as a bogus value.  "Awaiting
# Customer" is a state seen on sc_task records on this instance.  Other
# types get the comment without a state change ("state": null in json).
AWAITING_CUSTOMER_STATE = {
    "sc_task": "Awaiting Customer",
}


def _table_name(ticket):
    sys_class_name = ticket.get("sys_class_name")
    if isinstance(sys_class_name, dict):
        sys_class_name = sys_class_name.get("value")
    return sys_class_name or "task"


def patch(ctx, number, field, message=None, awaiting_customer=False):
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
        table = _table_name(ticket)
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
    elif field == "comments" and awaiting_customer:
        # Comment and state change in one update, on the child table
        # endpoint so the state label converts against the record's own
        # choice list (as resolve does).
        new_state = AWAITING_CUSTOMER_STATE.get(_table_name(ticket))
        if new_state:
            table = _table_name(ticket)
            data = {"comments": message, "state": new_state}
        else:
            table = "task"
            data = {"comments": message}
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
            if awaiting_customer and "state" not in data:
                diag("State not changed: no Awaiting Customer state is known "
                     "for this ticket type.")
        else:
            result = {
                "ok": True,
                "ticket_number": number,
                "field": field,
                "table": table,
                "status": "success",
            }
            if awaiting_customer:
                result["state"] = data.get("state")
            emit_json(result)
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
