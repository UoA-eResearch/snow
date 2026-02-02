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
    params = {
        "sysparm_query": query,
        "sysparm_display_value": "true",
        "sysparm_fields": "sys_id"
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
        data = {
            "state": "Resolved",
            "close_notes": message
        }
    else:
        data = {
            field: message
        }

    url = BASE_URL + "/api/now/table/task/" + sys_id
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
