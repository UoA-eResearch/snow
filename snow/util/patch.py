import sys
import json
import editor


def patch(ctx, number, field, message=None):
    BASE_URL = ctx["BASE_URL"]
    s = ctx["s"]
    if not message:
        if sys.stdin.isatty():
            message = editor.edit()
        else:
            message = sys.stdin.read()
    if not message:
        msg = "Aborted - no message"
        if ctx["format"] == "json":
            print(json.dumps({"error": msg}))
        else:
            print(msg)
        return
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
        if ctx["format"] == "json":
            print(json.dumps({"error": error_msg}))
        else:
            print(error_msg)
        return
    if not r['result']:
        msg = "Ticket not found"
        if ctx["format"] == "json":
            print(json.dumps({"error": msg}))
        else:
            print(msg)
        return
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

    if ctx["format"] == "json":
        if r.status_code == 204:
            output = {
                "ticket_number": number,
                "field": field,
                "status": "success"
            }
        else:
            output = {
                "ticket_number": number,
                "field": field,
                "status": "error",
                "error": r.json()["error"]
            }
        print(json.dumps(output, indent=4))
    else:
        if r.status_code == 204:
            print("Success")
        else:
            print(r.json()["error"])
