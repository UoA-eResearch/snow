import sys
import editor

def patch(ctx, number, field):
    BASE_URL = ctx["BASE_URL"]
    s = ctx["s"]
    if sys.stdin.isatty():
        message = editor.edit()
    else:
        message = sys.stdin.read()
    if not message:
        print("Aborted - no message")
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
        print(r["error"]["message"])
        return
    if not r['result']:
        print("Ticket not found")
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
    r = s.patch(url, json = data, headers = {"X-no-response-body": "true"})
    if r.status_code == 204:
        print("Success")
    else:
        print(r.json()["error"])